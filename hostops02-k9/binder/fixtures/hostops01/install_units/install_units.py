"""OP_INSTALL_UNITS: exclusive creation of rendered unit files in /etc/systemd/system. No activation.

Supervisor README operation 3 without daemon-reload, generic over a signed list of (template bytes hash,
destination name, rendered hash). This source starts no process: it does not import subprocess and has no systemctl
or docker call. Each file is written under a dot-prefixed temporary name that systemd does not load, fsynced,
verified, linked to its final name (a link never replaces anything) and the temporary is removed once its identity
is proved; a temporary whose file could not be completed is withdrawn the same way. Nothing else is ever removed.
No chmod, chown or rename exists in this source. Everything is looked at before the first creation, including
drop-in directories, dependency directories and alias links in every unit lookup directory. The caller authenticates exact
request/authority/GO/source bytes first; every mutating call is preceded by the signed UTC window and a monotonic
deadline. A run that changed anything and did not finish is PARTIAL, never a refusal. No action on import.
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

# ==== BEGIN OP_INSTALL_UNITS (this operation only) ====
OPERATION='GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01'
PHASE='WRITE_INSTALL_UNITS_NO_ACTIVATION'
REQUEST_SCHEMA='WRITE_HOSTOPS_INSTALL_UNITS_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS_INSTALL_UNITS_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS_INSTALL_UNITS_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS_INSTALL_UNITS_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS_INSTALL_UNITS_PLAN_V1'
SOURCE_NAME='install_units.py'
WRITES_ALLOWED=True
DATES=WRITE_DATES
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CREATED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('unit_directory','units','network_allowlist','journal_placement','data_volume_path','deploy_tree_path',
                     'template_revision','acknowledged_leftovers','daemon_reload_owner','evidence_boot_id_sha256'))
UNIT_KEYS=frozenset(('key','destination_name','mode','profile','template_b64','template_sha256','placeholders',
                     'rendered_sha256','rendered_bytes','expect'))
UNIT_MODE=0o644
TEMPORARY='.hostops-%s-%d.partial'
MAX_LEFTOVERS=16
SCOPE_STATEMENT=('Creates only the listed unit files in /etc/systemd/system, root:root, mode 0644, each written under a '
                 'dot-prefixed temporary name that systemd does not load, fsynced, then linked to its final name (a link never '
                 'replaces anything), after which the temporary of this run is removed once its identity is proved; a temporary '
                 'whose file could not be completed is withdrawn the same way, and nothing else is ever removed. No process '
                 'is started: no systemctl verb, no daemon-reload, no enablement, no drop-in, no overwrite, no chmod, chown or '
                 'rename. The manager is reloaded by the owner named in effects.daemon_reload, under that owner\'s own GO, never '
                 'by this operation. A spent GO is never retried; after anything other than the success criterion the host '
                 'state is established by a read-only operation under its own GO.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,
       'unit_directory':UNIT_DIRECTORY,'unit_name_pattern':UNIT_NAME,'max_units':MAX_UNITS,
       'every_file':{'type':'regular file','uid':0,'gid':0,'mode_octal':'0644','umask_octal':'0022','links':1},
       'temporary_name':TEMPORARY%('<first 16 hex of the GO hash>',0),'leftover_pattern':LEFTOVER,
       'expect':['ABSENT: created exclusively','PRESENT with signed device, inode and link count: verified against the signed render, never touched'],
       'profiles':{'frozen_templates':FROZEN_TEMPLATES,'required_for_name':REQUIRED_PROFILE,'all':list(PROFILES),
                   'supervisor_occurrences':OCCURRENCES,'generic_kinds':list(KINDS)},
       'grammar':{'path':VALUE_PATH,'network':NETWORK,'forbidden_networks':list(FORBIDDEN_NETWORKS),'image_id':IMAGE_ID,
                  'placeholder':PLACEHOLDER,'container_data':CONTAINER_DATA,'path_length':MAX_PATH_LENGTH,
                  'component_length':MAX_COMPONENT_LENGTH},
       'journal_placement':{'signed':list(PLACEMENTS),'provided_top_level_directories':list(PROVIDED_TOP_LEVEL),'fixed_container_targets':list(FIXED_TARGETS),
                            'every_placement':'the host journal root neither equals, contains nor is contained in the state root or the configuration '
                                              'directory; the container journal root likewise against the fixed targets; neither private root inside the data volume',
                            'A':'host journal root outside the data volume and outside the signed deploy tree; container journal root exactly one new '
                                'top-level directory, none of the provided ones',
                            'B':'host journal root a leaf of the data volume; container journal root '+CONTAINER_DATA+'/<the same leaf>',
                            'not_checked_here':'that the host journal root is not a mount point: this operation does not open it (OP_PROVISION creates it '
                                               'on its parent\'s device; OP_READBACK compares the devices)'},
       'conflict_scan':CONFLICT_SCAN_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'a regular file found at a signed destination name, only to say whether its bytes equal the signed render: '
                             'of a file that is not the signed render no digest and no size is reported',
                             'the text of symbolic links of a unit type in the lookup directories (alias detection)',
                             'the unit files this run installed (readback inside the run)'],
       'external_processes':0,
       'never':['a process','systemctl','daemon-reload','enablement link','drop-in','overwrite','chmod','chown','rename',
                'removal of anything but the temporary this run created and proved by identity','repair of an existing object',
                'docker','container environment','shell','network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'template_bytes':MAX_TEMPLATE_BYTES,
                 'template_bytes_total':MAX_TEMPLATE_BYTES_TOTAL,'render_bytes':MAX_RENDER_BYTES,'scan_names':MAX_SCAN_NAMES,
                 'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeScan):
    """Everything this operation can do to the host: the read primitives and these six calls. It starts no process."""
    def umask(self,mask):return os.umask(mask)
    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)
    def write(self,fd,data):return os.write(fd,data)
    def fsync(self,fd):os.fsync(fd)
    def link(self,source,target,dir_fd):os.link(source,target,src_dir_fd=dir_fd,dst_dir_fd=dir_fd,follow_symlinks=False)
    def unlink(self,name,dir_fd):os.unlink(name,dir_fd=dir_fd)


def validate_plan(plan):
    rows=chain_rows(plan['unit_directory'],UNIT_DIRECTORY)
    need(all(row_root_safe(row) for row in rows),'CHAIN_ROW_UNSAFE')
    need(not rows[-1]['mode']&stat.S_ISGID,'PARENT_SETGID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(text(plan['template_revision'],'[0-9a-f]{40}'),'TEMPLATE_REVISION_UNBOUND')
    need(text(plan['daemon_reload_owner'],'[A-Z][A-Z0-9_]{2,63}') and plan['daemon_reload_owner']!='UNBOUND','RELOAD_OWNER_UNBOUND')
    validate_allowlist(plan['network_allowlist'])
    units=plan['units']
    need(type(units) is list and 0<len(units)<=MAX_UNITS,'UNITS_INVALID')
    for unit in units:
        need(type(unit) is dict and set(unit)==set(UNIT_KEYS) and text(unit['key'],'[A-Z][A-Z0-9_]{0,31}')
             and type(unit['mode']) is int and unit['mode']==UNIT_MODE and type(unit['placeholders']) is dict,'UNITS_INVALID')
        need(unit_name(unit['destination_name']),'UNIT_NAME_INVALID')
        expect=unit['expect']
        need(expect=='ABSENT' or (type(expect) is dict and set(expect)=={'device','inode','links'} and integer(expect['device'])
                                  and integer(expect['inode'],1) and integer(expect['links'],1,2)),'EXPECT_INVALID')
    need(len({unit['key'] for unit in units})==len(units)
         and len({unit['destination_name'] for unit in units})==len(units),'UNIT_NAME_DUPLICATE')
    volume,placement,tree=plan['data_volume_path'],plan['journal_placement'],plan['deploy_tree_path']
    supervisor=any(unit['profile']==SERVICE_PROFILE for unit in units)
    need((volume is not None)==supervisor,'DATA_VOLUME_PATH')
    # The placement and the deploy tree belong to the supervisor service alone; a list without it signs neither.
    need(supervisor or (placement is None and tree is None),'PLACEMENT_UNKNOWN')
    total=0
    for unit in units:
        render_unit(unit,plan['network_allowlist'],volume,placement,tree);total+=len(decode_template(unit))
    need(total<=MAX_TEMPLATE_BYTES_TOTAL,'TEMPLATE_TOO_LARGE')
    leftovers=plan['acknowledged_leftovers']
    need(type(leftovers) is list and len(leftovers)<=MAX_LEFTOVERS,'LEFTOVERS_INVALID')
    for item in leftovers:
        need(type(item) is dict and set(item)=={'name','device','inode'} and text(item['name'],LEFTOVER)
             and integer(item['device']) and integer(item['inode'],1),'LEFTOVERS_INVALID')
    need(len({item['name'] for item in leftovers})==len(leftovers),'LEFTOVERS_INVALID')
    need(any(unit['expect']=='ABSENT' for unit in units),'NOTHING_TO_CREATE')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'directory':UNIT_DIRECTORY,'directory_row':plan['unit_directory'][-1],
            'chain_sha256':sha(canonical(plan['unit_directory'])),
            'units':[{'destination_name':unit['destination_name'],'mode_octal':'%04o'%unit['mode'],'profile':unit['profile'],
                      'template_sha256':unit['template_sha256'],'rendered_sha256':unit['rendered_sha256'],
                      'rendered_bytes':unit['rendered_bytes'],'substitutions':unit['placeholders'],
                      'expect':'ABSENT' if unit['expect']=='ABSENT' else 'PRESENT'} for unit in plan['units']],
            'files_to_create':sum(1 for unit in plan['units'] if unit['expect']=='ABSENT'),
            'network_allowlist':plan['network_allowlist'],'journal_placement':plan['journal_placement'],
            'data_volume_path':plan['data_volume_path'],'deploy_tree_path':plan['deploy_tree_path'],
            'template_revision':plan['template_revision'],
            'acknowledged_leftovers':[item['name'] for item in plan['acknowledged_leftovers']],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'daemon_reload':{'performed_by_this_operation':False,'owner':plan['daemon_reload_owner']},
            'external_processes':0,'pre_existing_objects_modified':False,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME


def precheck(plan,host,gate,rendered,detail,go16):
    """Everything is looked at before the first creation, by lstat (and, for a regular file already at a destination
    name, by reading it to say whether it is the signed render). Returns (pinned directory, refusal code or None)."""
    observed=[];detail['unit_directory']=observed
    fd=walk_pinned(host,plan['unit_directory'],gate,observed)
    directory=Pinned(host,fd,rows=plan['unit_directory'])
    rows=[];states=set()
    for unit,content in zip(plan['units'],rendered):
        name=unit['destination_name'];expect=unit['expect']
        row={'key':unit['key'],'destination_name':name,'expected':'ABSENT' if expect=='ABSENT' else 'PRESENT'}
        rows.append(row);gate()
        try:named=host.lstat(name,fd)
        except FileNotFoundError:named=None
        if named is None:
            row['observed']='ABSENT';row['state']='OK_ABSENT' if expect=='ABSENT' else 'EXPECTED_PRESENT_ABSENT'
        else:
            facts=file_row(named);size=facts.pop('size');row['observed']='PRESENT';row.update(facts);equal=None
            if stat.S_ISREG(named.st_mode):
                try:
                    raw,info=read_regular(host,name,fd,gate,MAX_RENDER_BYTES)
                    equal=raw==content and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino)
                except Refused as error:row['read_code']=code_of(error,'FILE_UNREADABLE')
                row['bytes_equal_signed_render']=equal
                # A digest or a size is reported only for bytes proved equal to the signed render (they are then the
                # signed values). A foreign unit may carry an inline secret; its digest would be an offline test for it.
                if equal:row.update(sha256=sha(raw),size=size)
            conforms=bool(equal and named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==UNIT_MODE)
            if not stat.S_ISREG(named.st_mode):row['state']='OCCUPIED_NOT_REGULAR'
            elif expect=='ABSENT':row['state']='PRESENT_EQUAL_NOT_SIGNED' if conforms and named.st_nlink in (1,2) else 'PRESENT_FOREIGN'
            elif conforms and (named.st_dev,named.st_ino,named.st_nlink)==(expect['device'],expect['inode'],expect['links']):
                row['state']='OK_PRESENT'
            else:row['state']='PRESENT_IDENTITY_MISMATCH'
        states.add(row['state'])
    scan=conflict_scan(host,[unit['destination_name'] for unit in plan['units']],gate)
    signed={item['name']:(item['device'],item['inode']) for item in plan['acknowledged_leftovers']}
    seen={item['name']:(item['device'],item['inode']) for item in scan['leftovers']}
    own={TEMPORARY%(go16,index) for index,unit in enumerate(plan['units']) if unit['expect']=='ABSENT'}
    scan['leftovers_acknowledged']=sorted(name for name in seen if signed.get(name)==seen[name])
    scan['leftovers_not_acknowledged']=sorted(name for name in seen if signed.get(name)!=seen[name])
    detail['precheck']={'units':rows,'conflicts':scan}
    present=[row['observed']=='PRESENT' for row in rows];code=None
    # Fixed precedence. None of these says that an installation happened: they say what exists.
    if 'OCCUPIED_NOT_REGULAR' in states:code='UNIT_NAME_OCCUPIED'
    elif 'PRESENT_FOREIGN' in states:code='UNIT_PRESENT_FOREIGN_CONTENT'
    elif states&{'EXPECTED_PRESENT_ABSENT','PRESENT_IDENTITY_MISMATCH'} or set(signed)-set(seen):code='EXPECTATION_MISMATCH'
    elif 'PRESENT_EQUAL_NOT_SIGNED' in states:
        # "All present" is said only of one-link files with no unacknowledged temporary beside them; a name that still
        # shares its inode with a temporary is the state an interrupted run leaves.
        settled=all(present) and all(row['links']==1 for row in rows) and not scan['leftovers_not_acknowledged'] and scan['leftover_count']<=MAX_FINDINGS
        code='ALL_UNITS_PRESENT' if settled else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
    elif scan['leftover_count']>MAX_FINDINGS or scan['leftovers_not_acknowledged']:
        code='TEMPORARY_NAME_OCCUPIED' if own&set(scan['leftovers_not_acknowledged']) else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
    elif own&set(seen):code='TEMPORARY_NAME_OCCUPIED'
    elif 'DROP_IN_PRESENT' in scan['finding_codes']:code='DROP_IN_PRESENT'
    elif 'OWN_DEPENDENCY_DIRECTORY_PRESENT' in scan['finding_codes']:code='OWN_DEPENDENCY_DIRECTORY_PRESENT'
    elif 'ENABLEMENT_LINK_PRESENT' in scan['finding_codes']:code='ENABLEMENT_LINK_PRESENT'
    elif 'ALIAS_LINK_PRESENT' in scan['finding_codes']:code='ALIAS_LINK_PRESENT'
    elif 'UNIT_SHADOWED_IN_OTHER_PATH' in scan['finding_codes']:code='UNIT_SHADOWED_IN_OTHER_PATH'
    elif scan['status']!='COMPLETE':code='CONFLICT_SCAN_UNAVAILABLE'
    return directory,code

def number(error):return error.errno if isinstance(error,OSError) and type(error.errno) is int else None

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

def install_unit(index,unit,content,directory,host,gate,state,go16):
    """One unit: exclusive temporary, unbuffered writes, fsync, exact metadata, link to the final name, fsync of the
    directory, removal of the temporary. Returns the ledger row. Nothing is repaired and nothing raises past here."""
    name=unit['destination_name'];temp=TEMPORARY%(go16,index)
    entry={'key':unit['key'],'path':UNIT_DIRECTORY+'/'+name,'state':'NOT_ATTEMPTED','code':None,'errno':None,'bytes':None,
           'sha256_signed':unit['rendered_sha256'],'sha256_observed':None,'mode_octal':None,'uid':None,'gid':None,'links':None,
           'device':None,'inode':None,'temporary_name':temp,'temporary_removed':False,'temporary_removal_code':None,
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
    try:directory.verify(gate)
    except Refused as error:return failed(code_of(error,'PARENT_REPLACED'))
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    try:fd=mutate(state,gate,lambda:host.create(temp,flags,UNIT_MODE,directory.fd))
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
                    and stat.S_IMODE(info.st_mode)==UNIT_MODE and info.st_size==len(content)
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
        # Complete, fsynced bytes are the only thing that ever appears under a name systemd loads.
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

def readback(plan,rendered,directory,host,gate,ledger):
    """Inside the run: each final name opened again without following a link; same inode as created, one link, exact
    owner and mode, bytes equal to the signed render."""
    result={'status':'COMPLETE','code':None}
    try:
        directory.verify(gate)
        for unit,content,entry in zip(plan['units'],rendered,ledger):
            raw,info=read_regular(host,unit['destination_name'],directory.fd,gate,MAX_RENDER_BYTES)
            entry['sha256_observed']=sha(raw)
            same=entry['state']!='INSTALLED_DURABLE' or (info.st_dev,info.st_ino)==(entry['device'],entry['inode'])
            need(raw==content and same and info.st_uid==0 and info.st_gid==0 and stat.S_IMODE(info.st_mode)==UNIT_MODE
                 and (info.st_nlink==1 or entry['state']!='INSTALLED_DURABLE'),'READBACK_HASH_MISMATCH')
    except Exception as error:
        result.update(status='UNAVAILABLE',code=code_of(error,'READBACK_UNAVAILABLE'))
    return result

def _reduce_scan(receipt):
    scan=(receipt.get('precheck') or {}).get('conflicts')
    if type(scan) is dict:scan['directories']={name:item.get('status') for name,item in scan.get('directories',{}).items()}
def _reduce_precheck(receipt):
    table=receipt.get('precheck') or {}
    receipt['precheck']={'units':[{'key':row.get('key'),'state':row.get('state')} for row in table.get('units',[])],
                         'finding_codes':(table.get('conflicts') or {}).get('finding_codes')}
REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('PRECHECK_REDUCED_TO_STATES',_reduce_precheck)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    # Pure step: every unit is rendered again from the signed bytes and values and must hash to the signed render.
    rendered=[render_unit(unit,plan['network_allowlist'],plan['data_volume_path'],plan['journal_placement'],plan['deploy_tree_path']) for unit in plan['units']]
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'unit_directory':[],'precheck':None};ledger=[];directory=None;go16=bound['go_sha256'][:16]
    def finish(status,outcome,code,extra):
        try:
            ended,elapsed=clock(),monotonic()-mark
            timing={'utc_start':begun.isoformat(),'utc_end':ended.isoformat(),'monotonic_elapsed_ms':int(elapsed*1000)}
        except Exception:timing=None
        left=sum(1 for row in ledger if row['state'] in ('TEMPORARY_ONLY','INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'))
        left+=2*sum(1 for row in ledger if row['state']=='LINKED_TEMPORARY_PRESENT')
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing,
            mutating_calls=state.counts(),unit_directory=detail['unit_directory'],precheck=detail['precheck'],ledger=ledger,
            external_processes=0,daemon_reload_owner=plan['daemon_reload_owner'],objects_left_by_this_run=left,
            pre_existing_objects_modified=False,**extra))
        return seal(receipt)
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o022)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            directory,code=precheck(plan,host,gate,rendered,detail,go16)
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:
            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        stop=None
        for index,(unit,content) in enumerate(zip(plan['units'],rendered)):
            if unit['expect']!='ABSENT' or stop is not None:
                ledger.append({'key':unit['key'],'path':UNIT_DIRECTORY+'/'+unit['destination_name'],'code':None,
                               'state':'NOT_ATTEMPTED' if unit['expect']=='ABSENT' else 'PRESENT_VERIFIED_NOT_TOUCHED',
                               'sha256_signed':unit['rendered_sha256'],'sha256_observed':None});continue
            entry=install_unit(index,unit,content,directory,host,gate,state,go16);ledger.append(entry)
            if entry['state']!='INSTALLED_DURABLE':stop=entry['code'] or 'INSTALL_FAILED'
        check=None
        if stop is None:
            check=readback(plan,rendered,directory,host,gate,ledger)
            if check['status']!='COMPLETE':stop=check['code'] or 'READBACK_UNAVAILABLE'
        extra={'phase_reached':'CREATION','readback':check}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        if directory is not None:
            try:directory.close()
            except Exception:pass
# ==== END OP_INSTALL_UNITS ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
