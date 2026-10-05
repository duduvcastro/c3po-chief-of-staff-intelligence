"""OP_READBACK: the complete readback of supervisor README operation 4. Read-only.

Observations only. This source has no call that creates, changes or removes anything. The token is looked at with
one lstat and is never opened; its size, a digest or a timestamp never enter the receipt. The only file contents
read are the two unit files and the kernel boot identifier; of symbolic links of a unit type in the lookup
directories the link text is read. Each item is observed on its own: a failed observation
is UNAVAILABLE with a constant code, never an absence, and a mismatch is a finding that leaves every other item in
the receipt. Exit 0 exists for one outcome only; a reconciliation readback never reaches it. The caller
authenticates exact request/authority/GO/source bytes first. No action on import.
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

# ==== BEGIN RENDER (shared part, byte-identical in every source that carries it) ====
import base64

# Validation and rendering of the supervisor unit: validate_substitutions() and the render loop are Codex's
# (supervisor-installer-rev2, installer.py sha256 c53732b0be2469344c3b39bd182c401c13dff52dc0d33430cdd838df02751356),
# judged correct by the audit, with the audit's corrections: item types are checked before set(), containment is
# refused in both directions, and paths, components and the rendered text have length limits.
# The journal placement is the README's "Substitution grammar" as it stands at repository revision a6dd2b1 (README
# sha256 27bf0e5a...dc2b): the placement (A outside the data volume, B a leaf of it) is signed, and the path rules
# follow it. The codes and their order are those of the repository's own reading of that prose (placement_refusal in
# backend/tests/test_r2d2_v2_massive_supervisor.py), so the two can be compared case by case.
SERVICE_PROFILE='MASSIVE_SUPERVISOR_SERVICE_V1'
TIMER_PROFILE='MASSIVE_SUPERVISOR_TIMER_V1'
PROFILES=(SERVICE_PROFILE,TIMER_PROFILE,'VERBATIM_V1','GENERIC_KINDS_V1')
FROZEN_TEMPLATES={SERVICE_PROFILE:'9e7de1c6eaf937e5b1fc9540986fdbdf2a2f821a9c57b944f9534a605d07f04a',
                  TIMER_PROFILE:'ec61b1d6cbd1d604e5c2177d186f9045e67bf21ecc092498691591dfd9164ee6'}
# The supervisor's two names can only be installed from the frozen templates, and the frozen profiles serve no other name.
REQUIRED_PROFILE={'c3po-massive.service':SERVICE_PROFILE,'c3po-massive.timer':TIMER_PROFILE}
OCCURRENCES={'IMAGE_ID':2,'HOST_JOURNAL_ROOT':2,'CONTAINER_JOURNAL_ROOT':2,
             'HOST_STATE_ROOT':2,'HOST_CONFIG_DIR':3,'NETWORK':1}
PATH_VALUES=('HOST_JOURNAL_ROOT','CONTAINER_JOURNAL_ROOT','HOST_STATE_ROOT','HOST_CONFIG_DIR')
PLACEMENTS=('A','B')
CONTAINER_DATA='/app/day-d-data'
# Under placement A the container journal root is exactly one new top-level directory: none of these, which the image
# or the runtime provides at "/" (the README's list; it calls the list a floor).
PROVIDED_TOP_LEVEL=('app','bin','boot','dev','etc','home','lib','lib64','media','mnt','opt','proc','root','run','sbin','srv','sys','tmp','usr','var')
# The unit's own container targets, literal in the frozen template: the state root, the configuration directory, the tmpfs.
FIXED_TARGETS=('/var/lib/c3po-bar/supervisor','/etc/c3po-bar','/tmp')
VALUE_PATH='/[A-Za-z0-9_./-]+'
NETWORK='[A-Za-z0-9][A-Za-z0-9_.-]{0,127}'
FORBIDDEN_NETWORKS=('host','none')
KINDS=('IMAGE_ID','ABSOLUTE_PATH','NETWORK')
PLACEHOLDER='[A-Z][A-Z0-9_]{0,63}'
MAX_PATH_LENGTH=200
MAX_COMPONENT_LENGTH=64
MAX_TEMPLATE_BYTES=16384
MAX_TEMPLATE_BYTES_TOTAL=24576
MAX_RENDER_BYTES=65536
MAX_PLACEHOLDERS=16

def safe_path(value):
    need(type(value) is str and re.fullmatch(VALUE_PATH,value) is not None,'PATH_INVALID')
    need(len(value)<=MAX_PATH_LENGTH,'PATH_TOO_LONG')
    parts=value.split('/')[1:]
    need(all(part not in ('','.','..') for part in parts),'PATH_COMPONENT')
    need(all(len(part)<=MAX_COMPONENT_LENGTH for part in parts),'PATH_TOO_LONG')
    return PurePosixPath(value)

def validate_allowlist(network_allowlist):
    need(type(network_allowlist) is list and 0<len(network_allowlist)<=16
         and all(type(name) is str for name in network_allowlist)
         and len(set(network_allowlist))==len(network_allowlist),'NETWORK_ALLOWLIST')
    for name in network_allowlist:
        need(re.fullmatch(NETWORK,name) is not None and name not in FORBIDDEN_NETWORKS,'NETWORK_FORBIDDEN')

def overlaps(one,other):return one==other or one in other.parents or other in one.parents
def within(path,tree):return path==tree or tree in path.parents

def validate_substitutions(values,network_allowlist,data_volume,placement,deploy_tree):
    """The six values, in the signed placement. The data volume and (under placement A) the deploy tree are signed
    strings used for the path rules only; nothing here touches the host."""
    need(type(values) is dict and set(values)==set(OCCURRENCES),'SUBSTITUTION_KEYS')
    for name in PATH_VALUES:safe_path(values[name])
    need(type(values['IMAGE_ID']) is str and re.fullmatch(IMAGE_ID,values['IMAGE_ID']) is not None,'IMAGE_ID')
    validate_allowlist(network_allowlist)
    need(type(values['NETWORK']) is str and values['NETWORK'] in network_allowlist,'NETWORK_NOT_AUTHORIZED')
    placement_rules(values,data_volume,placement,deploy_tree)

def placement_rules(values,data_volume,placement,deploy_tree):
    """Where the journal root may be, for the four path values: the README's placement rules and nothing else. Also
    applied by the readback to the values it parses from the installed unit."""
    need(type(placement) is str and placement in PLACEMENTS,'PLACEMENT_UNKNOWN')
    volume=safe_path(data_volume);journal=safe_path(values['HOST_JOURNAL_ROOT'])
    container=safe_path(values['CONTAINER_JOURNAL_ROOT']);state=safe_path(values['HOST_STATE_ROOT']);config=safe_path(values['HOST_CONFIG_DIR'])
    # In every placement.
    need(not any(overlaps(journal,private) for private in (state,config)),'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT')
    need(not any(overlaps(container,PurePosixPath(target)) for target in FIXED_TARGETS),'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET')
    need(not any(within(private,volume) for private in (state,config)),'PRIVATE_ROOT_INSIDE_DATA_VOLUME')
    if placement=='A':
        need(type(deploy_tree) is str,'DEPLOY_TREE_PATH');tree=safe_path(deploy_tree)
        need(not within(journal,volume),'A_HOST_JOURNAL_INSIDE_DATA_VOLUME')
        need(not within(journal,tree),'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE')
        need(len(container.parts)==2,'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL')
        need(container.name not in PROVIDED_TOP_LEVEL,'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY')
    else:
        need(deploy_tree is None,'DEPLOY_TREE_PATH')
        need(journal.parent==volume,'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME')
        need(container==PurePosixPath(CONTAINER_DATA)/journal.name,'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF')
    # Beyond the README, from the installer audit: the data volume is not inside a private root either, and the two
    # private roots do not overlap each other.
    need(not any(private in volume.parents for private in (state,config)),'DATA_INSIDE_PRIVATE')
    need(not overlaps(state,config),'PRIVATE_PATH_OVERLAP')

def render_service(template,values):
    """Six substitutions into the frozen bytes (the caller has pinned them); fails if any '@' survives. No host access."""
    unit=template.decode('ascii')
    tokens=re.findall(r'@([A-Z_]+)@',unit)
    need(set(tokens)==set(OCCURRENCES) and all(tokens.count(key)==count for key,count in OCCURRENCES.items()),'PLACEHOLDER_COUNTS')
    for key in OCCURRENCES:unit=unit.replace('@'+key+'@',values[key])
    need('@' not in unit,'UNRESOLVED_PLACEHOLDER')
    return unit.encode('ascii')

def render_generic(template,placeholders,network_allowlist):
    """Units other than the supervisor's (the reader's, under their own GO): the signed placeholder set, each value
    in the grammar of its kind, exact occurrence counts. The binding guard is the signed rendered hash."""
    need(type(placeholders) is dict and 0<len(placeholders)<=MAX_PLACEHOLDERS
         and all(text(name,PLACEHOLDER) for name in placeholders),'SUBSTITUTION_KEYS')
    for name,item in placeholders.items():
        need(type(item) is dict and set(item)=={'kind','value','occurrences'} and item['kind'] in KINDS
             and integer(item['occurrences'],1,64),'SUBSTITUTION_KEYS')
        if item['kind']=='ABSOLUTE_PATH':safe_path(item['value'])
        elif item['kind']=='IMAGE_ID':need(text(item['value'],IMAGE_ID),'IMAGE_ID')
        else:need(type(item['value']) is str and item['value'] in network_allowlist,'NETWORK_NOT_AUTHORIZED')
    unit=template.decode('ascii')
    tokens=re.findall('@('+PLACEHOLDER+')@',unit)
    need(set(tokens)==set(placeholders) and all(tokens.count(name)==item['occurrences'] for name,item in placeholders.items()),
         'PLACEHOLDER_COUNTS')
    for name in sorted(placeholders):unit=unit.replace('@'+name+'@',placeholders[name]['value'])
    need('@' not in unit,'UNRESOLVED_PLACEHOLDER')
    return unit.encode('ascii')

def decode_template(unit):
    value=unit['template_b64']
    need(type(value) is str and len(value)<=4*((MAX_TEMPLATE_BYTES+2)//3),'TEMPLATE_TOO_LARGE')
    try:raw=base64.b64decode(value.encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('TEMPLATE_ENCODING') from None
    need(base64.b64encode(raw).decode('ascii')==value,'TEMPLATE_ENCODING')
    need(0<len(raw)<=MAX_TEMPLATE_BYTES,'TEMPLATE_TOO_LARGE')
    need(hexpin(unit['template_sha256']) and sha(raw)==unit['template_sha256'],'TEMPLATE_HASH_MISMATCH')
    need(re.fullmatch(rb'[\t\n -~]*',raw) is not None,'TEMPLATE_NOT_ASCII')
    return raw

def render_unit(unit,network_allowlist,data_volume,placement=None,deploy_tree=None):
    """One signed unit -> the exact bytes to install. Pure: nothing here touches the host."""
    name,profile=unit['destination_name'],unit['profile']
    need(type(profile) is str and profile in PROFILES,'PROFILE_UNKNOWN')
    need(REQUIRED_PROFILE.get(name,profile)==profile and (profile not in FROZEN_TEMPLATES or REQUIRED_PROFILE.get(name)==profile),
         'PROFILE_NAME_MISMATCH')
    template=decode_template(unit)
    if profile in FROZEN_TEMPLATES:need(sha(template)==FROZEN_TEMPLATES[profile],'FROZEN_TEMPLATE_HASH')
    if profile==SERVICE_PROFILE:
        validate_substitutions(unit['placeholders'],network_allowlist,data_volume,placement,deploy_tree)
        rendered=render_service(template,unit['placeholders'])
    elif profile=='GENERIC_KINDS_V1':rendered=render_generic(template,unit['placeholders'],network_allowlist)
    else:
        need(unit['placeholders']=={},'SUBSTITUTION_KEYS')
        need(b'@' not in template,'TIMER_PLACEHOLDER' if profile==TIMER_PROFILE else 'UNRESOLVED_PLACEHOLDER')
        rendered=template
    need(len(rendered)<=MAX_RENDER_BYTES,'RENDER_TOO_LARGE')
    need(hexpin(unit['rendered_sha256']) and sha(rendered)==unit['rendered_sha256'],'RENDERED_HASH_MISMATCH')
    need(type(unit['rendered_bytes']) is int and len(rendered)==unit['rendered_bytes'],'RENDERED_SIZE_MISMATCH')
    return rendered

VALUE_PATTERNS={'IMAGE_ID':IMAGE_ID,'HOST_JOURNAL_ROOT':VALUE_PATH,'CONTAINER_JOURNAL_ROOT':VALUE_PATH,
                'HOST_STATE_ROOT':VALUE_PATH,'HOST_CONFIG_DIR':VALUE_PATH,'NETWORK':NETWORK}
def extract_values(template,installed):
    """The six values as they stand in installed bytes: the template is cut at its placeholders and the installed text
    must match literal segment by literal segment, a repeated placeholder repeating its value. A parse of what is on
    disk, not a second run of the renderer. None when the bytes are not this template with six well-formed values."""
    try:pattern_text,candidate=template.decode('ascii'),installed.decode('ascii')
    except UnicodeDecodeError:return None
    parts=re.split(r'@([A-Z_]+)@',pattern_text);seen=[];out=[]
    for index,part in enumerate(parts):
        if index%2==0:out.append(re.escape(part))
        elif part not in VALUE_PATTERNS:return None
        elif part in seen:out.append('(?P=%s)'%part)
        else:seen.append(part);out.append('(?P<%s>%s)'%(part,VALUE_PATTERNS[part]))
    match=re.fullmatch(''.join(out),candidate)
    if match is None or set(seen)!=set(VALUE_PATTERNS):return None
    return {name:match.group(name) for name in sorted(seen)}
# ==== END RENDER ====

# ==== BEGIN OP_READBACK (this operation only) ====
OPERATION='GO_READONLY_SUPERVISOR_READBACK_01'
PHASE='READONLY_SUPERVISOR_READBACK'
REQUEST_SCHEMA='READONLY_HOSTOPS_READBACK_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS_READBACK_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS_READBACK_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS_READBACK_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS_READBACK_PLAN_V1'
SOURCE_NAME='readback_readonly.py'
WRITES_ALLOWED=False
DATES=READ_DATES
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
COMPLETE_OUTCOME='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
MISMATCH_OUTCOME='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
RECONCILIATION_OUTCOME='RECONCILIATION_OBSERVED_NOTHING_GATED'
PARTIAL_OUTCOME='PARTIAL_OBSERVED'
EXPIRED_OUTCOME='PARTIAL_OR_WINDOW_EXPIRED'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_OBSERVED'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
INSTALL_COMPLETE='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
PLAN_KEYS=frozenset(('mode','install','provision','evidence_boot_id_sha256','unit_directory','service','timer','substitutions',
                     'network_allowlist','journal_placement','journal_mount_point','deploy_tree_path','data_volume','layout','retention_reference','image_revision','free_space_floor_bytes',
                     'sessions_retained','other_writers_allowance_bytes','catalog'))
UNIT_FILE_KEYS=frozenset(('template_b64','rendered_sha256','rendered_bytes','device','inode'))
SERVICE_NAME='c3po-massive.service'
TIMER_NAME='c3po-massive.timer'
UNITS=[SERVICE_NAME,TIMER_NAME]
UNIT_MODE=0o644
DIRECTORY_MODE=0o700
TOKEN_MODE=0o600
LAYOUT_KEYS=('SUP_CONFIG','SUP_MANIFESTS','SUP_DOCKER_CLI','SUP_STATE_PARENT','SUP_STATE','SUP_JOURNAL')
REPOSITORY='c3po/backend'
PRODUCTION_REFERENCE=REPOSITORY+':production'
TAG='massive-supervisor-[a-z0-9][a-z0-9.-]{0,40}'
# README "Activation gate" item 4: the producer's floor, plus one session's own budget for each session retained before
# space is next freed, plus the signed allowance for every other writer of that filesystem. Recomputed here.
PRODUCER_FLOOR_BYTES=53687091200
SESSION_BYTES=603979776
MAX_SESSIONS_RETAINED=366
MAX_ALLOWANCE_BYTES=1<<50
# Wrong at any reload state: the manager refused the unit text, could not read it, or the name is masked.
BAD_LOAD_STATES=('bad-setting','error','masked')
INIT_COUNTED='a regular file owned by uid 0, not writable by group or other, with an execute bit'
MINIMUM_SYSTEMD=240
MINIMUM_DOCKER=[20,10]
DOCKER_UNIT='docker.service'
CATALOG_NAMES=('epoch.json','maintenance.lock')
MAX_CATALOG_ENTRIES=64
MAX_COUNT=100000
INIT_CANDIDATES=['/usr/bin/docker-init','/usr/libexec/docker/docker-init','/usr/local/bin/docker-init','/usr/sbin/docker-init']
REBOOT_MARKER='/run/reboot-required'
EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl']}
VERSION_FORMAT='{{json .Server.Version}}'
INFO_FIELDS=[('security_options','SecurityOptions'),('driver','Driver'),('driver_status','DriverStatus'),
             ('docker_root_dir','DockerRootDir'),('init_binary','InitBinary'),('server_version','ServerVersion')]
# One docker info call for all six fields, as in the reviewed read-only family.
INFO_FORMAT='{'+','.join('"'+key+'":{{json .'+field+'}}' for key,field in INFO_FIELDS)+'}'
UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','WantedBy','RequiredBy','TriggeredBy')
def _show(unit,keys):return ['show',unit]+[part for key in keys for part in ('-p',key)]
# The exact fixed argv prefixes. The signed request carries this table. No command here changes anything.
COMMANDS={'systemd_version':['systemctl',['--version'],None],
          'docker_unit':['systemctl',_show(DOCKER_UNIT,('Id','ActiveState','SubState','UnitFileState')),None],
          'timer_enabled':['systemctl',['is-enabled',TIMER_NAME],None],
          'image':['docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID, or the signed retention reference'],
          'info':['docker',['info','--format',INFO_FORMAT],None],
          'version':['docker',['version','--format',VERSION_FORMAT],None]}
COMMANDS.update({'unit:'+unit:['systemctl',_show(unit,UNIT_PROPERTIES),None] for unit in UNITS})
SCOPE_STATEMENT=('Reads and changes nothing: the two installed unit files (bytes and metadata), the six values as they stand in the '
                 'installed service, owner, group and mode of every path of the layout and, under placement B only, of the data volume '
                 'root (under placement A the data volume is not read), the filesystem of the journal root, the token by one '
                 'lstat (never opened; never its size, a digest or a timestamp), the names and metadata of the catalog files, free '
                 'space against the signed floor, drop-in and dependency directories, the docker-init candidates, and the fixed '
                 'systemctl and docker commands of the scope. No systemctl verb other than show, is-enabled and --version. '
                 'Only the outcome named as success criterion satisfies the readback half of the activation gate; a '
                 'reconciliation readback never does. This operation authorises no installation and no activation.')
SIDE_EFFECTS=['docker info, run once: the Docker CLI executes every installed CLI plugin binary as root with the single argument '
              'docker-cli-plugin-metadata, and the daemon answers by running its init and runtime binaries with --version; no setting is changed',
              'every docker command runs with DOCKER_CONFIG set to the unit\'s own configuration directory, and only after that directory was '
              'seen to exist, root:root 0700 and empty; whether the Docker CLI writes into an empty configuration directory was never observed '
              'on this host, so the directory is counted before and after and a change is reported as its own finding',
              'systemctl show of a unit the manager has not loaded makes the manager load it from disk; no daemon-reload is run, so of LoadState '
              'only bad-setting, error and masked are findings (they are wrong at any reload state); loaded, not-found and stub are reported',
              'the docker and systemctl entries are known from the upstream sources; systemctl is-enabled and the five extra show properties were never run by this family on this host']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,
       'binaries':BINARIES,'commands':COMMANDS,'command_environment':COMMAND_ENVIRONMENT,
       'docker_config':'<HOST_CONFIG_DIR>/docker-cli, passed as DOCKER_CONFIG to the docker commands only',
       'units':UNITS,'unit_directory':UNIT_DIRECTORY,'frozen_templates':FROZEN_TEMPLATES,
       'layout':{'keys':list(LAYOUT_KEYS),'every_directory':{'type':'dir','uid':0,'gid':0,'mode_octal':'0700'},
                 'unit_file':{'uid':0,'gid':0,'mode_octal':'0644','links':1},
                 'token':{'path':'<HOST_CONFIG_DIR>/token','uid':0,'gid':0,'mode_octal':'0600','links':1,
                          'reported':['type','uid','gid','mode_octal','links','size_within_1_4096'],'opened':False},
                 'configuration_directory_entries':'counted, names never reported: manifests, docker-cli and the token, nothing else',
                 'catalog':{'names':list(CATALOG_NAMES),'uid':0,'gid':0,'mode_octal':'0600','links':1,'opened':False}},
       'minimums':{'systemd':MINIMUM_SYSTEMD,'docker':MINIMUM_DOCKER},
       'free_space_floor':{'formula':'producer_floor_bytes + bytes_per_session * sessions_retained + other_writers_allowance_bytes',
                           'producer_floor_bytes':PRODUCER_FLOOR_BYTES,'bytes_per_session':SESSION_BYTES,'sessions_retained_at_least':1,
                           'measured':'f_bavail * f_frsize of the filesystem of the journal root, on the journal root itself'},
       'lstat_only':{'docker_init':INIT_CANDIDATES,'docker_init_counted':INIT_COUNTED,'reboot_marker':REBOOT_MARKER},
       'conflict_scan':CONFLICT_SCAN_SCOPE,
       'image':{'revision_label':REVISION_LABEL+' of the pinned image must equal the signed revision',
                'production_reference':PRODUCTION_REFERENCE+' among the tags of the pinned image is reported, not gated'},
       'modes':{'GATE':COMPLETE_OUTCOME,'RECONCILIATION':RECONCILIATION_OUTCOME+' (never exit 0)'},
       'file_contents_read':[BOOT_ID_PATH,UNIT_DIRECTORY+'/'+SERVICE_NAME,UNIT_DIRECTORY+'/'+TIMER_NAME],
       'reported_not_gated':['LoadState loaded, not-found and stub','docker rootless and user-namespace flags','reboot marker',
                             'whether the pinned image still carries '+PRODUCTION_REFERENCE],
       'load_states_that_are_findings':list(BAD_LOAD_STATES),
       'side_effects':SIDE_EFFECTS,
       'never':['any write','the token content, size, digest or timestamps','the content of a catalog file or of a manifest',
                'container environment','docker exec or run','systemctl verbs other than show, is-enabled and --version',
                'daemon-reload','shell','network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'call_seconds':CALL_SECONDS,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,
                 'command_output_bytes':MAX_COMMAND_BYTES,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,
                 'unit_bytes':MAX_RENDER_BYTES,'catalog_entries':MAX_CATALOG_ENTRIES,'scan_names':MAX_SCAN_NAMES,
                 'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeScan):
    """Read primitives and the fixed commands. This source has no call that creates, changes or removes anything."""


def render_of(plan,name):
    """The signed unit rendered again, with the signed placement."""
    return render_unit(unit_of(plan,name),plan['network_allowlist'],plan['data_volume']['path'],plan['journal_placement'],plan['deploy_tree_path'])
def unit_of(plan,name):
    """The signed description of one of the two supervisor units, in the shape the shared renderer validates."""
    item=plan['service'] if name==SERVICE_NAME else plan['timer'];profile=REQUIRED_PROFILE[name]
    return {'destination_name':name,'profile':profile,'template_b64':item['template_b64'],'template_sha256':FROZEN_TEMPLATES[profile],
            'placeholders':plan['substitutions'] if name==SERVICE_NAME else {},'rendered_sha256':item['rendered_sha256'],
            'rendered_bytes':item['rendered_bytes']}
def identity_pair(item,strict_mode,code):
    """device and inode copied from an earlier receipt: integers, or both null in a reconciliation readback."""
    numbers=integer(item['device']) and integer(item['inode'],1)
    need(numbers or (not strict_mode and item['device'] is None and item['inode'] is None),code)

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in ('GATE','RECONCILIATION'),'MODE_INVALID');gated=mode=='GATE'
    install,provision=plan['install'],plan['provision']
    need(type(install) is dict and set(install)=={'receipt_sha256','outcome'} and type(provision) is dict
         and set(provision)=={'receipt_sha256'},'RECEIPTS_INVALID')
    if gated:
        need(hexpin(install['receipt_sha256']) and install['outcome']==INSTALL_COMPLETE,'INSTALL_RECEIPT_UNBOUND')
        need(hexpin(provision['receipt_sha256']),'PROVISION_RECEIPT_UNBOUND')
        need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    else:
        need((install['receipt_sha256'] is None or hexpin(install['receipt_sha256']))
             and (install['outcome'] is None or text(install['outcome'],CODE)),'INSTALL_RECEIPT_UNBOUND')
        need(provision['receipt_sha256'] is None or hexpin(provision['receipt_sha256']),'PROVISION_RECEIPT_UNBOUND')
        need(plan['evidence_boot_id_sha256'] is None or hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    chain_rows(plan['unit_directory'],UNIT_DIRECTORY)
    volume,placement=plan['data_volume'],plan['journal_placement']
    need(type(volume) is dict and set(volume)=={'path','rows'} and type(volume['path']) is str,'DATA_VOLUME_INVALID')
    validate_allowlist(plan['network_allowlist'])
    validate_substitutions(plan['substitutions'],plan['network_allowlist'],volume['path'],placement,plan['deploy_tree_path'])
    # The filesystem the authorisation names for the journal root: its mount point ("/" when /var/lib is on the root
    # filesystem, as the receipt of 2026-10-02 read it in an earlier boot and OP_PRECHECK reads it again in the boot of
    # the write; the data volume root under placement B).
    point=plan['journal_mount_point']
    need(type(point) is str and (point=='/' or clean_path(point)),'JOURNAL_MOUNT_POINT_UNBOUND')
    need(inside(plan['substitutions']['HOST_JOURNAL_ROOT'],point) and point!=plan['substitutions']['HOST_JOURNAL_ROOT'],'JOURNAL_MOUNT_POINT_UNBOUND')
    # Under placement A the data volume is not part of the layout: its path is signed for the path rules only, no row
    # of it is signed and nothing of it is read.
    if placement=='B':chain_rows(volume['rows'],volume['path'])
    else:need(volume['rows'] is None,'DATA_VOLUME_INVALID')
    for name in UNITS:
        item=plan['service'] if name==SERVICE_NAME else plan['timer']
        need(type(item) is dict and set(item)==set(UNIT_FILE_KEYS),'UNITS_INVALID')
        identity_pair(item,gated,'UNITS_INVALID')
        render_of(plan,name)
    layout=plan['layout']
    need(type(layout) is dict and set(layout)==set(LAYOUT_KEYS),'LAYOUT_INVALID')
    for key in LAYOUT_KEYS:
        need(type(layout[key]) is dict and set(layout[key])=={'device','inode'},'LAYOUT_INVALID')
        identity_pair(layout[key],gated,'LAYOUT_INVALID')
    need(type(plan['retention_reference']) is str and re.fullmatch(re.escape(REPOSITORY)+':'+TAG,plan['retention_reference']) is not None,
         'TAG_INVALID')
    need(text(plan['image_revision'],'[0-9a-f]{40}'),'IMAGE_REVISION_UNBOUND')
    sessions,allowance=plan['sessions_retained'],plan['other_writers_allowance_bytes']
    need(integer(sessions,1,MAX_SESSIONS_RETAINED) and integer(allowance,0,MAX_ALLOWANCE_BYTES),'FLOOR_TERMS_INVALID')
    # The floor is not a free number: it is the gate's formula on the two signed terms, and both are in the effects.
    need(type(plan['free_space_floor_bytes']) is int
         and plan['free_space_floor_bytes']==PRODUCER_FLOOR_BYTES+SESSION_BYTES*sessions+allowance,'FLOOR_NOT_THE_GATE_FORMULA')
    catalog=plan['catalog']
    need(type(catalog) is dict and set(catalog)=={'expected','receipt_sha256','device','inode'}
         and type(catalog['expected']) is str and catalog['expected'] in ('INITIALISED','NOT_YET'),'CATALOG_INVALID')
    if catalog['expected']=='INITIALISED':
        need(hexpin(catalog['receipt_sha256']) and integer(catalog['device']) and integer(catalog['inode'],1),'CATALOG_INVALID')
    else:need(catalog['receipt_sha256'] is None and catalog['device'] is None and catalog['inode'] is None,'CATALOG_INVALID')

def layout_paths(values):
    config,state=values['HOST_CONFIG_DIR'],values['HOST_STATE_ROOT']
    return {'SUP_CONFIG':config,'SUP_MANIFESTS':config+'/manifests','SUP_DOCKER_CLI':config+'/docker-cli',
            'SUP_STATE_PARENT':str(PurePosixPath(state).parent),'SUP_STATE':state,'SUP_JOURNAL':values['HOST_JOURNAL_ROOT']}

def identities_of(plan):
    """Every identity this readback compares, copied from earlier receipts. Its hash is in the effects, so a GO cannot
    stay the same while a pinned device or inode in the request changes."""
    pair=lambda item:{'device':item['device'],'inode':item['inode']}
    return {'unit_directory':plan['unit_directory'],'service':pair(plan['service']),'timer':pair(plan['timer']),
            'layout':{key:pair(plan['layout'][key]) for key in LAYOUT_KEYS},'data_volume_rows':plan['data_volume']['rows'],
            'catalog':pair(plan['catalog'])}

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'mode':plan['mode'],'install_receipt_sha256':plan['install']['receipt_sha256'],
            'install_outcome':plan['install']['outcome'],'provision_receipt_sha256':plan['provision']['receipt_sha256'],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'units':{SERVICE_NAME:plan['service']['rendered_sha256'],TIMER_NAME:plan['timer']['rendered_sha256']},
            'substitutions':plan['substitutions'],'network_allowlist':plan['network_allowlist'],
            'journal_placement':plan['journal_placement'],'journal_mount_point':plan['journal_mount_point'],
            'deploy_tree_path':plan['deploy_tree_path'],'data_volume_read':plan['journal_placement']=='B',
            'layout_paths':layout_paths(plan['substitutions']),'data_volume_path':plan['data_volume']['path'],
            'token_path':plan['substitutions']['HOST_CONFIG_DIR']+'/token',
            'image_id':plan['substitutions']['IMAGE_ID'],'image_revision':plan['image_revision'],
            'retention_reference':plan['retention_reference'],
            'free_space_floor_bytes':plan['free_space_floor_bytes'],'sessions_retained':plan['sessions_retained'],
            'other_writers_allowance_bytes':plan['other_writers_allowance_bytes'],
            'unit_directory_row':plan['unit_directory'][-1],
            'data_volume_root_row':plan['data_volume']['rows'][-1] if plan['data_volume']['rows'] else None,
            'identities_sha256':sha(canonical(identities_of(plan))),
            'catalog':{'expected':plan['catalog']['expected'],'receipt_sha256':plan['catalog']['receipt_sha256']},
            'gates_activation_readback':plan['mode']=='GATE','writes':0,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME if plan['mode']=='GATE' else RECONCILIATION_OUTCOME


def properties(raw,keys):
    need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'PROPERTY_OUTPUT_INVALID')
    found={}
    for line in raw.decode('ascii').splitlines():
        if not line:continue
        key,separator,value=line.partition('=')
        need(separator=='=','PROPERTY_LINE_INVALID')
        if key in keys:
            need(key not in found and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'PROPERTY_VALUE_INVALID');found[key]=value
    return {key:found.get(key) for key in keys},sorted(set(keys)-set(found))

def done(status='COMPLETE',findings=(),**fields):
    """One observation: whether it could be made (status) and, separately, whether what was seen is what was signed."""
    codes=sorted(set(findings))
    return dict(fields,status=status,findings=codes,matches=(not codes) if status=='COMPLETE' else None)

class Reader:
    """The observations of one readback. Each method is one item of the receipt and fails on its own."""
    def __init__(self,plan,host,gate):
        self.plan,self.host,self.gate=plan,host,gate;self.commands=Commands(host,gate)
        self.values=plan['substitutions'];self.paths=layout_paths(self.values)
        self.same_boot=True;self.service_bytes=None;self.docker_config=None;self.init_present=None
        self.unit_file_state=None

    def boot(self):
        seen=boot_id_sha256(self.host,self.gate);signed=self.plan['evidence_boot_id_sha256']
        self.same_boot=signed is None or seen==signed
        # Device numbers may be renumbered by a reboot: one finding here instead of one per row, and rows compare without the device.
        return done(findings=[] if self.same_boot else ['EVIDENCE_FROM_EARLIER_BOOT'],boot_id_sha256=seen,
                    evidence_boot_id_sha256=signed,device_numbers_compared=self.same_boot)

    def identity(self,info,signed):
        """True, False, or None when the request carries no identity (reconciliation)."""
        if signed['inode'] is None:return None
        return info.st_ino==signed['inode'] and (not self.same_boot or info.st_dev==signed['device'])

    def units(self):
        rows=[];findings=[];files={}
        fd=descend(self.host,UNIT_DIRECTORY,self.gate,rows)
        try:
            signed=self.plan['unit_directory']
            directory_equal=len(rows)==len(signed) and all(row_equal(seen,row,self.same_boot) for seen,row in zip(rows,signed))
            if not directory_equal:findings.append('UNIT_DIRECTORY_IDENTITY_MISMATCH')
            for name in UNITS:
                item=self.plan['service'] if name==SERVICE_NAME else self.plan['timer'];self.gate()
                try:named=self.host.lstat(name,fd)
                except FileNotFoundError:
                    files[name]={'exists':False};findings.append('UNIT_ABSENT');continue
                row=dict(file_row(named),exists=True,sha256_signed=item['rendered_sha256']);files[name]=row
                if not stat.S_ISREG(named.st_mode):
                    findings.append('UNIT_NOT_REGULAR');continue
                try:raw,info=read_regular(self.host,name,fd,self.gate,MAX_RENDER_BYTES)
                except Refused as error:
                    if str(error)=='FILE_CHANGED_DURING_READ':raise Refused('UNIT_CHANGED_DURING_READ') from None
                    raise
                need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'UNIT_CHANGED_DURING_READ')
                row.update(sha256=sha(raw),bytes=len(raw),bytes_equal_signed_render=sha(raw)==item['rendered_sha256'],
                           identity_equal_install_receipt=self.identity(info,item))
                if name==SERVICE_NAME:self.service_bytes=raw
                if not (info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==UNIT_MODE and info.st_nlink==1):
                    findings.append('UNIT_METADATA')
                if row['identity_equal_install_receipt'] is False:findings.append('UNIT_IDENTITY_CHANGED')
                if not row['bytes_equal_signed_render']:findings.append('UNIT_BYTES_MISMATCH')
            return done(findings=findings,unit_directory=rows,unit_directory_equal_signed=directory_equal,files=files)
        finally:self.host.close(fd)

    def values_in_installed_bytes(self):
        need(self.service_bytes is not None,'SERVICE_BYTES_UNAVAILABLE')
        template=decode_template(unit_of(self.plan,SERVICE_NAME))
        extracted=extract_values(template,self.service_bytes)
        placement=self.plan['journal_placement']
        if extracted is None:return done(findings=['VALUES_NOT_EXTRACTABLE'],extracted=None,signed=self.values,signed_placement=placement)
        # The placement the values on disk correspond to: the signed placement's own path rules, applied to what was extracted.
        try:
            placement_rules(extracted,self.plan['data_volume']['path'],placement,self.plan['deploy_tree_path'])
            conform,rule=True,None
        except Refused as error:conform,rule=False,code_of(error,'PLACEMENT_RULE')
        findings=([] if extracted==self.values else ['VALUES_MISMATCH'])+([] if conform else ['PLACEMENT_MISMATCH'])
        return done(findings=findings,extracted=extracted,signed=self.values,signed_placement=placement,
                    extracted_values_conform_to_the_signed_placement=conform,placement_rule_broken=rule,
                    basis='parsed from the installed bytes against the literal segments of the frozen template')

    def layout(self):
        rows={};findings=[];unavailable=False
        for key in LAYOUT_KEYS:
            found=attempt(lambda key=key:probe(self.host,self.paths[key],self.gate));found['path']=self.paths[key]
            rows[key]=found
            if found.get('status')!='COMPLETE':unavailable=True;continue
            if not found['exists']:
                findings.append('LAYOUT_ENTRY_ABSENT');continue
            found.pop('links',None)
            found['metadata_matches']=(found['type'],found['uid'],found['gid'],found['mode_octal'])==('dir',0,0,'%04o'%DIRECTORY_MODE)
            signed=self.plan['layout'][key]
            found['identity_equal_provision_receipt']=None if signed['inode'] is None else (
                found['inode']==signed['inode'] and (not self.same_boot or found['device']==signed['device']))
            if not found['metadata_matches']:findings.append('LAYOUT_METADATA')
            if found['identity_equal_provision_receipt'] is False:findings.append('LAYOUT_IDENTITY_CHANGED')
        counts={}
        for key in ('SUP_DOCKER_CLI','SUP_MANIFESTS','SUP_STATE'):
            if rows[key].get('exists') and rows[key].get('type')=='dir':
                counts[key]=attempt(lambda key=key:{'status':'COMPLETE','entries':self.count(self.paths[key])})
                if counts[key].get('status')!='COMPLETE':unavailable=True
        cli=rows['SUP_DOCKER_CLI']
        if counts.get('SUP_DOCKER_CLI',{}).get('status')=='COMPLETE':
            if counts['SUP_DOCKER_CLI']['entries']:findings.append('DOCKER_CONFIG_NOT_EMPTY')
            elif cli.get('metadata_matches'):self.docker_config=self.paths['SUP_DOCKER_CLI']
        # The filesystem the journal root is on: one row per component from "/", and from the device numbers its mount
        # point, which must be the one the authorisation names; and the journal root is not itself a mount point (its
        # device is the device of the directory it is in). Read only when the journal root was seen to exist.
        journal=rows['SUP_JOURNAL'];signed_point=self.plan['journal_mount_point']
        filesystem={'placement':self.plan['journal_placement'],'signed_mount_point':signed_point,'status':'NOT_OBSERVED'}
        if journal.get('exists') and journal.get('type')=='dir':
            chain=[]
            try:
                self.host.close(descend(self.host,self.paths['SUP_JOURNAL'],self.gate,chain))
                point=mount_point_of(chain);own=chain[-1]['device']!=chain[-2]['device']
                filesystem.update(status='COMPLETE',device=chain[-1]['device'],parent_device=chain[-2]['device'],mount_point_by_device_change=point,
                                  mount_point_equals_signed=point==signed_point,journal_root_is_a_mount_point=own)
                if own:findings.append('JOURNAL_ROOT_IS_A_MOUNT_POINT')
                elif point!=signed_point:findings.append('JOURNAL_FILESYSTEM_MISMATCH')
            except Exception as error:
                filesystem.update(safe(error));unavailable=True
        if self.plan['journal_placement']!='B':
            observed={'status':'COMPLETE','read':False,'reason':'placement A: the data volume is not part of the layout and nothing of it is read'}
            return done('PARTIAL' if unavailable else 'COMPLETE',findings,paths=rows,entry_counts=counts,journal_filesystem=filesystem,data_volume=observed)
        volume=self.plan['data_volume'];seen=[]
        try:
            self.host.close(descend(self.host,volume['path'],self.gate,seen))
            equal=len(seen)==len(volume['rows']) and all(row_equal(a,b,self.same_boot) for a,b in zip(seen,volume['rows']))
            observed={'status':'COMPLETE','read':True,'rows':seen,'equal_signed_rows':equal,'recorded_not_required_to_be_root':True}
            if not equal:findings.append('DATA_VOLUME_ROW_CHANGED')
        except Exception as error:
            observed=dict(safe(error),rows=seen);unavailable=True
        return done('PARTIAL' if unavailable else 'COMPLETE',findings,paths=rows,entry_counts=counts,journal_filesystem=filesystem,data_volume=observed)

    def count(self,path):
        fd=descend(self.host,path,self.gate)
        try:return count_entries(self.host,fd,self.gate,MAX_COUNT)
        finally:self.host.close(fd)

    def token(self):
        """One lstat through the configuration directory, and a count of that directory's entries. The file is never
        opened; no size, digest, timestamp or name leaves here."""
        fd=descend(self.host,self.paths['SUP_CONFIG'],self.gate)
        try:
            self.gate()
            # Entries of the configuration directory, on the descriptor held: the two directories and the token, nothing
            # else (an abandoned token.new, an editor backup). Names never leave this function.
            entries=count_entries(self.host,fd,self.gate,MAX_COUNT)
            try:named=self.host.lstat('token',fd)
            except FileNotFoundError:
                return done(findings=['TOKEN_ABSENT']+(['CONFIG_DIRECTORY_ENTRIES'] if entries!=2 else []),exists=False,
                            configuration_directory_entries=entries,configuration_directory_entries_expected=2)
            regular=stat.S_ISREG(named.st_mode);findings=[] if entries==3 else ['CONFIG_DIRECTORY_ENTRIES']
            within=bool(1<=named.st_size<=4096) if regular else None
            if not regular:findings.append('TOKEN_NOT_REGULAR')
            if not (named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==TOKEN_MODE and named.st_nlink==1):
                findings.append('TOKEN_METADATA')
            if regular and not within:findings.append('TOKEN_SIZE_POLICY')
            return done(findings=findings,exists=True,type=kind(named.st_mode),uid=named.st_uid,gid=named.st_gid,
                        mode_octal='%04o'%stat.S_IMODE(named.st_mode),links=named.st_nlink,size_within_1_4096=within,
                        configuration_directory_entries=entries,configuration_directory_entries_expected=3)
        finally:self.host.close(fd)

    def journal(self):
        """Catalog names and metadata, and free space, on one descriptor of the journal root. No catalog file is opened."""
        catalog=self.plan['catalog'];fd=descend(self.host,self.paths['SUP_JOURNAL'],self.gate)
        try:
            held=self.host.fstat(fd);names=[]
            for name in self.host.names(fd):
                names.append(name);need(len(names)<=MAX_CATALOG_ENTRIES,'CATALOG_ENTRY_LIMIT')
            files={};findings=[]
            for name in CATALOG_NAMES:
                if name not in names:continue
                self.gate();named=self.host.lstat(name,fd)
                files[name]={'type':kind(named.st_mode),'uid':named.st_uid,'gid':named.st_gid,
                             'mode_octal':'%04o'%stat.S_IMODE(named.st_mode),'links':named.st_nlink}
                if not (stat.S_ISREG(named.st_mode) and named.st_uid==0 and named.st_gid==0
                        and stat.S_IMODE(named.st_mode)==TOKEN_MODE and named.st_nlink==1):findings.append('CATALOG_METADATA')
            foreign=len([name for name in names if name not in CATALOG_NAMES])
            if catalog['expected']=='INITIALISED':
                if set(names)!=set(CATALOG_NAMES):findings.append('CATALOG_ENTRIES')
                # The catalog binds device and inode of its root: a renumbered device is a real finding, in any boot.
                if (held.st_dev,held.st_ino)!=(catalog['device'],catalog['inode']):findings.append('CATALOG_IDENTITY_MISMATCH')
            elif names:findings=[code for code in findings if code!='CATALOG_METADATA']+['CATALOG_UNEXPECTED']
            section=done(findings=findings,expected=catalog['expected'],entries=len(names),known_files=files,other_entries=foreign,
                         root_device=held.st_dev,root_inode=held.st_ino)
            def space():
                v=self.host.fstatvfs(fd);values=(v.f_frsize,v.f_blocks,v.f_bfree,v.f_bavail)
                need(all(type(value) is int and value>=0 for value in values) and v.f_frsize>0,'STATVFS_INVALID')
                available=v.f_bavail*v.f_frsize;floor=self.plan['free_space_floor_bytes']
                return done(findings=[] if available>=floor else ['FREE_SPACE_BELOW_FLOOR'],
                            bytes_available_to_non_root_f_bavail=available,bytes_free_for_root_f_bfree=v.f_bfree*v.f_frsize,
                            bytes_total=v.f_blocks*v.f_frsize,signed_floor_bytes=floor,at_or_above_signed_floor=available>=floor,
                            sessions_retained=self.plan['sessions_retained'],other_writers_allowance_bytes=self.plan['other_writers_allowance_bytes'],
                            bytes_above_signed_floor=available-floor,filesystem_device=held.st_dev)
            return section,attempt(space)
        finally:self.host.close(fd)

    def conflicts(self):
        scan=conflict_scan(self.host,UNITS,self.gate)
        findings=list(scan['finding_codes'])+(['PRIOR_TEMPORARY_PRESENT'] if scan['leftover_count'] else [])
        return done(scan['status'],findings,conflict_rows=scan['findings'],
                    **{key:value for key,value in scan.items() if key not in ('status','findings')})

    def docker_init(self):
        candidates={path:attempt(lambda path=path:probe(self.host,path,self.gate)) for path in INIT_CANDIDATES}
        status=combined(candidates.values())
        def counted(value):
            # A name that merely exists (a dangling link, a directory, a file nobody can execute) is not an init binary.
            if value.get('exists') is not True or value.get('type')!='file' or value.get('uid')!=0:return False
            mode=int(value['mode_octal'],8);return not mode&0o022 and bool(mode&0o111)
        present=sorted(path for path,value in candidates.items() if counted(value))
        other=sorted(path for path,value in candidates.items() if value.get('exists') is True and not counted(value))
        self.init_present=True if present else False if status=='COMPLETE' else None
        return done(status,candidates={path:{key:value for key,value in item.items() if key!='links'} for path,item in candidates.items()},
                    present_paths=present,present_not_counted_paths=other,counted=INIT_COUNTED,any_present=self.init_present,lstat_only=True)

    def reboot_marker(self):
        found=probe(self.host,REBOOT_MARKER,self.gate)
        if found.get('status')!='COMPLETE':return found
        return done(exists=found['exists'],reported_not_gated=True)

    def systemd_version(self):
        raw=self.commands.output('systemd_version').split(b'\n',1)[0]
        need(re.fullmatch(rb'[ -~]{1,200}',raw) is not None,'VERSION_LINE_INVALID')
        line=raw.decode('ascii');match=re.match(r'systemd ([0-9]{1,5})(?![0-9])',line)
        need(match is not None,'VERSION_LINE_INVALID');number=int(match.group(1))
        return done(findings=[] if number>=MINIMUM_SYSTEMD else ['SYSTEMD_TOO_OLD'],first_line=line,number=number,minimum=MINIMUM_SYSTEMD)

    def docker_unit(self):
        values,missing=properties(self.commands.output('docker_unit'),('Id','ActiveState','SubState','UnitFileState'))
        need(not missing,'PROPERTY_MISSING')
        return done(findings=[] if (values['Id'],values['ActiveState'])==(DOCKER_UNIT,'active') else ['DOCKER_UNIT_NOT_ACTIVE'],properties=values)

    def unit(self,name):
        values,missing=properties(self.commands.output('unit:'+name),UNIT_PROPERTIES)
        need(not missing,'PROPERTY_MISSING');need(values['Id']==name,'UNIT_ID_MISMATCH');findings=[]
        if values['ActiveState']!='inactive':findings.append('UNIT_NOT_INACTIVE')
        if values['LoadState'] in BAD_LOAD_STATES:findings.append('UNIT_LOAD_STATE')
        if values['FragmentPath'] not in ('',UNIT_DIRECTORY+'/'+name):findings.append('FRAGMENT_PATH_MISMATCH')
        if values['DropInPaths']:findings.append('DROP_IN_REPORTED_BY_MANAGER')
        if values['WantedBy'] or values['RequiredBy']:findings.append('REVERSE_DEPENDENCY_REPORTED_BY_MANAGER')
        if values['TriggeredBy'] not in ('',TIMER_NAME if name==SERVICE_NAME else ''):findings.append('TRIGGER_REPORTED_BY_MANAGER')
        if name==TIMER_NAME:
            self.unit_file_state=values['UnitFileState']
            if values['UnitFileState'] not in ('','disabled'):findings.append('TIMER_NOT_DISABLED')
        return done(findings=findings,properties=values,load_state=values['LoadState'],load_states_that_are_findings=list(BAD_LOAD_STATES))

    def timer_enabled(self):
        returncode,raw=self.commands.call('timer_enabled')
        need(re.fullmatch(rb'[a-z-]{1,32}\n?',raw) is not None,'IS_ENABLED_NO_ANSWER')
        word=raw.decode('ascii').strip();findings=[]
        if word!='disabled':findings.append('TIMER_NOT_DISABLED')
        if self.unit_file_state not in (None,'',word):findings.append('ENABLEMENT_SOURCES_DISAGREE')
        # is-enabled exits non-zero for "disabled": the status is recorded and is not a command failure here.
        return done(findings=findings,word=word,returncode=returncode,unit_file_state_from_show=self.unit_file_state)

    def docker_config_count(self):
        need(self.docker_config is not None,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE')
        return self.count(self.docker_config)

    def image(self,reference,mismatch):
        need(self.docker_config is not None,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE')
        try:facts=image_facts(self.commands,reference,self.docker_config)
        except CommandFailed as error:raise CommandFailed('IMAGE_ABSENT_OR_UNREADABLE',error.returncode) from None
        equal=facts['id']==self.values['IMAGE_ID'];findings=[] if equal else [mismatch]
        if reference!=self.values['IMAGE_ID'] and equal and not facts['reference_among_repo_tags']:findings.append(mismatch)
        extra={}
        if reference==self.values['IMAGE_ID']:
            # The pinned image itself: its revision label against the signed one (a finding), and whether it still is
            # the production image (reported: after a later deploy the unit keeps its ID by design).
            signed=self.plan['image_revision'];listed=PRODUCTION_REFERENCE in facts['repo_tags']
            extra={'signed_revision':signed,'revision_equal_signed':facts['revision_label']==signed,
                   'production_reference_among_repo_tags':True if listed else False if facts['repo_tag_count']==len(facts['repo_tags']) else None,
                   'production_reference_reported_not_gated':True}
            if not extra['revision_equal_signed']:findings.append('IMAGE_REVISION_MISMATCH')
        return done(findings=findings,reference=reference,signed_image_id=self.values['IMAGE_ID'],id_equal=equal,**facts,**extra)

    def daemon(self):
        need(self.docker_config is not None,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE')
        row=decode(self.commands.output('info',docker_config=self.docker_config))
        need(set(row)=={key for key,_ in INFO_FIELDS},'DAEMON_INFO_INVALID')
        # A CLI that cannot reach the daemon may still print zero values and exit 0: an empty version is no answer.
        need(type(row['server_version']) is str and row['server_version']!='','DAEMON_INFO_EMPTY')
        options=row['security_options']
        need(options is None or (type(options) is list and len(options)<=16
                                 and all(text(item,'[A-Za-z0-9_.,=:/-]{1,128}') for item in options)),'DAEMON_FIELD_INVALID')
        need(text(row['init_binary'],'[A-Za-z0-9_./-]{0,128}'),'DAEMON_FIELD_INVALID')
        version=strict(self.commands.output('version',docker_config=self.docker_config))
        need(text(version,'[0-9A-Za-z.+~_-]{1,64}'),'DAEMON_FIELD_INVALID')
        match=re.match(r'([0-9]{1,4})\.([0-9]{1,4})(?![0-9])',version);need(match is not None,'DAEMON_FIELD_INVALID')
        number=[int(match.group(1)),int(match.group(2))];names=[item.split(',')[0] for item in options or []];findings=[]
        if number<MINIMUM_DOCKER:findings.append('DOCKER_TOO_OLD')
        if row['init_binary']=='' or self.init_present is False:findings.append('INIT_BINARY_MISSING')
        return done('COMPLETE' if self.init_present is not None else 'PARTIAL',findings,init_binary=row['init_binary'],
                    init_executable_present_on_host=self.init_present,server_version=version,server_version_number=number,
                    minimum=MINIMUM_DOCKER,rootless_reported='name=rootless' in names,userns_remap_reported='name=userns' in names,
                    rootless_and_userns_reported_not_gated=True)


def _reduce_scan(receipt):
    scan=receipt['items'].get('conflicts')
    if type(scan) is dict and type(scan.get('directories')) is dict:
        scan['directories']={name:item.get('status') for name,item in scan['directories'].items()}
def _reduce_items(receipt):
    receipt['items']={name:{key:item.get(key) for key in ('status','matches','findings','code')} for name,item in receipt['items'].items()}
REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    reader=Reader(plan,host,gate);items={}
    def run(name,action):
        try:
            gate();items[name]=action()
        except Exception as error:items[name]=safe(error)
    items['actor']=attempt(lambda:done(findings=[] if tuple(host.identity())==(0,0) else ['EXECUTOR_IDENTITY'],
                                       **dict(zip(('uid','gid'),host.identity()))))
    run('boot',reader.boot)
    run('units',reader.units)
    run('values',reader.values_in_installed_bytes)
    run('layout',reader.layout)
    run('token',reader.token)
    try:
        gate();items['catalog'],items['free_space']=reader.journal()
    except Exception as error:items['catalog']=safe(error);items['free_space']=safe(error)
    run('conflicts',reader.conflicts)
    run('docker_init',reader.docker_init)
    run('systemd_version',reader.systemd_version)
    run('docker_unit',reader.docker_unit)
    for name in UNITS:run('unit:'+name,lambda name=name:reader.unit(name))
    run('timer_enabled',reader.timer_enabled)
    before=attempt(reader.docker_config_count)
    run('image',lambda:reader.image(reader.values['IMAGE_ID'],'IMAGE_ID_MISMATCH'))
    run('retention_tag',lambda:reader.image(plan['retention_reference'],'RETENTION_TAG_MISMATCH'))
    run('docker_daemon',reader.daemon)
    after=attempt(reader.docker_config_count)
    if type(before) is int and type(after) is int:
        # Counted before and after the docker commands, separately: a change during this run has its own code.
        items['docker_config']=done(findings=(['DOCKER_CONFIG_NOT_EMPTY'] if before else [])+(['DOCKER_CONFIG_CHANGED_DURING_RUN'] if after!=before else []),
                                    path=reader.docker_config,entries_before=before,entries_after=after)
    else:items['docker_config']=before if type(before) is dict else after
    run('reboot_marker',reader.reboot_marker)
    try:
        ended,elapsed=clock(),monotonic()-mark
        need(ended>=begun and elapsed>=0,'CLOCK_REVERSED')
        items['clock']=done(utc_start=begun.isoformat(),utc_end=ended.isoformat(),monotonic_elapsed_ms=int(elapsed*1000))
    except Exception as error:items['clock']=safe(error)
    findings=sorted({code for item in items.values() for code in item.get('findings') or []})
    incomplete=sorted(name for name,item in items.items() if item.get('status')!='COMPLETE')
    expired=any(item.get('code') in EXPIRED for item in items.values())
    try:gate()
    except Refused:expired=True
    reconciliation=plan['mode']!='GATE'
    if reconciliation:findings=sorted(set(findings)|{'INSTALL_RECEIPT_NOT_COMPLETE'})
    if expired:outcome=EXPIRED_OUTCOME
    elif incomplete:outcome=PARTIAL_OUTCOME
    elif reconciliation:outcome=RECONCILIATION_OUTCOME
    elif findings:outcome=MISMATCH_OUTCOME
    else:outcome=COMPLETE_OUTCOME
    # Exit 0 exists for exactly one outcome; a reconciliation readback takes its own branch above and never reaches it.
    status=COMPLETE_STATUS if outcome==COMPLETE_OUTCOME else PARTIAL_STATUS
    receipt=envelope(status,outcome,None if status==COMPLETE_STATUS else findings[0] if findings else 'ITEMS_NOT_COMPLETE',
        dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),mode=plan['mode'],items=items,findings=findings,
             items_not_complete=incomplete,expectations_met=outcome==COMPLETE_OUTCOME,
             commands_started=reader.commands.calls,mutating_calls=state.counts(),writes=0,secret_bytes_read=0,
             file_contents_read=['the two signed unit files',BOOT_ID_PATH],activation_authorized=False,
             installation_authorized=False))
    return seal(receipt)
# ==== END OP_READBACK ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
