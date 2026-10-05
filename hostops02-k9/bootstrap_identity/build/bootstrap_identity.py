"""BOOTSTRAP_IDENTITY: own epoch claim and observed first-night worker identity.

Own core; exactly one durable exclusive claim outside SECRETS. No secret contents opened; Docker inspect emits only five LIVE comparison booleans. Docker CLI/daemon receive the inspect object. No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='5c39111b58ed47cbac4420d94db7ddaf8e4e145f150c30e62ab4352633382a25'
CORE_PARTS={'core': '958c28f1fb3dd88d8c608101a87688cce136544b95df31b4f2df7a7c51e29fa7', 'runner': '2a1cc5bc73a0d456eb596aea65caaffcf7dd3834cbbd844a02a69486bbdacaa7', 'docker': '3d22e8ad6577b3391bff6a43e815fb7bdb9487dafb07733eb2bb8eaa8b910ccb', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'claim': 'c98e36f93acde05e6426737eac0a9a10204c7b5743b0539203bc812000347147'}
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
           'WRITE_EPOCH':EPOCH_DAYS[1:],
           'WRITE_BOOTSTRAP':('2026-10-06',)}                      # a write that may fall on the weekend or on a session day
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
                                              'activation_performed','daemon_reload_performed','claim','mode','boot_id_sha256')}
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
        fragments.append('{{ $p := false }}{{ $e := false }}{{ $duplicate := false }}{{ range .Config.Env }}{{ $pieces := split . "=" }}'
                         '{{ if eq (index $pieces 0) "'+key+'" }}{{ if $p }}{{ $duplicate = true }}{{ end }}{{ $p = true }}{{ if eq . "'+key+'='+expected[key]+'" }}{{ $e = true }}{{ end }}{{ end }}{{ end }}'
                         '"'+key+'":{"present":{{json $p}},"equal":{{json (and $e (not $duplicate))}}}')
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

# ==== BEGIN CLAIM (shared part, byte-identical in every source that carries it) ====
# Own primitive set for the bootstrap claim; no unlink, mkdir, rename, chmod, chown or truncate.
class NativeClaim:
    def create(self,name,flags,mode,dir_fd):return os.open(name,flags,mode,dir_fd=dir_fd)
    def write(self,fd,data):return os.write(fd,data)
    def fsync(self,fd):os.fsync(fd)
# ==== END CLAIM ====

# ==== BEGIN OP_BOOTSTRAP_IDENTITY (this operation only) ====
OPERATION='GO_WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_01'
PHASE='WRITE_BOOTSTRAP_IDENTITY_EPOCH_CLAIM'
REQUEST_SCHEMA='WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_BOOTSTRAP_IDENTITY_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_BOOTSTRAP_IDENTITY_PLAN_V1'
SOURCE_NAME='bootstrap_identity.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_BOOTSTRAP'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_WRITE_HOSTOPS02_K4_E0_01','GO_READONLY_HOSTOPS02_EPOCH_READBACK_01','GO_READONLY_HOSTOPS02_K9_PHASE_READ_01')
MAX_GATE_SPAN_SECONDS=300
COMPLETE_OUTCOME='BOOTSTRAP_IDENTITY_AND_EPOCH_CLAIM_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_BOOTSTRAP_CLAIM_CONSUMED_REQUIRES_REVIEW'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='PARTIAL_BOOTSTRAP_CLAIM_CONSUMED_REQUIRES_REVIEW'
ESCAPED_OUTCOME='PARTIAL_BOOTSTRAP_CLAIM_CONSUMED_REQUIRES_REVIEW'
BOOTSTRAP_MODE='BOOTSTRAP_IDENTITY'
BOOTSTRAP_EPOCH='R2D2-V2-SHADOW-2026-10-05'
BOOTSTRAP_SLOT='FIRST_NIGHT_20261006'
BOOTSTRAP_START='2026-10-06T20:43:00+00:00'
BOOTSTRAP_END='2026-10-06T20:48:00+00:00'
K9_PACKAGE_SHA256='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
K9_CODE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
PLAN_KEYS=frozenset(('mode','epoch','slot','attempt_key','constants','parent_rows','data_volume_chain','source_rows','evidence_boot_id_sha256','policy_read'))

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

K9_PRIVATE_DIRECTORY_MODE=0o700
K9_PRIVATE_FILE_MODE=0o600
K9_DISK_FLOOR_BYTES=214748364800
K9_MAX_COUNT=10000000
K9_MAX_PLAN_FILE=16777216
K9_MAX_RUNNER_FILE=4194304
K9_MAX_POLICY_FILE=8192
K9_MAX_RELEASE_FILE=65536
K9_ENTRY='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
K9_EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
K9_WALK_FINDINGS=('PARENT_MISSING','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_IDENTITY_MISMATCH','SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY')
K9_ROW_FIELDS=('device','inode','uid','gid','mode')
BOOTSTRAP_CONSTANT_KEYS=frozenset(('package_sha256','code_revision','release_sha256','policy_sha256','image_id','runner_sha256','disk_floor_bytes','placement'))
SOURCE_PATHS=tuple(K9_DATA_VOLUME+'/'+part for part in ('.r2d2-v2-risk-secrets','.r2d2-v2-risk-secrets/risk-database-url','.c3po-role-executor-20260908-r2','.c3po-role-executor-20260908-r2/secret','.c3po-role-executor-20260908-r2/secret/password'))
SOURCE_ROW_KEYS=frozenset(('path','device','inode','uid','gid','mode','mtime_ns','ctime_ns'))
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the compiled worker name or its observed ID','QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the five approved LIVE booleans template then the observed worker ID','QUICK','READ')}
CLAIM_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
class Native(NativeRead,NativeRunner,NativeClaim):
    pass

def k9_free_inodes(host,fd):
    """Inodes a non-root writer can still take on the filesystem of a held descriptor; None where none are counted."""
    numbers=host.fstatvfs(fd);total,free=getattr(numbers,'f_files',0),getattr(numbers,'f_favail',None)
    return free if integer(total,1) and integer(free) else None

def k9_root_group_rows(rows):
    """Every component of a K9 chain in the group of root and not setgid (K4-E0's rule for the same chain)."""
    return all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows)

def k9_chain(item,path,receives_entry,code):
    """One signed directory of the placement: exactly {path, rows, open_root}, the compiled path, open_root null (N-8 and
    decision 6: no open root anywhere in these chains), rows from a read of the same boot, every component uid 0, gid 0,
    not setgid, not group/other-writable."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and item['path']==path and item['open_root'] is None and item['rows'] is not None,code)
    validate_chain(item['rows'],path,None,receives_entry)
    need(k9_root_group_rows(item['rows']),'CHAIN_ROW_NOT_ROOT_GROUP')
    return item

def k9_free_chain(item,code):
    """A signed directory whose path the plan gives (the policy and the release directories)."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and type(item['path']) is str and clean_path(item['path']) and item['path']!='/'
         and item['rows'] is not None,code)
    root=item['open_root']
    need(root is None or (type(root) is str and clean_path(root) and root!='/' and inside(item['path'],root)),code)
    validate_chain(item['rows'],item['path'],root)
    return item

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

class BootstrapReader:
    def __init__(self,plan,host,gate,commands,bound,clock,monotonic):
        self.plan,self.host,self.gate,self.commands,self.clock,self.monotonic=plan,host,gate,commands,clock,monotonic
        self.mode=BOOTSTRAP_MODE;self.values=plan['constants'];self.held={};self.same_boot=True
        self.image_ok=False;self.worker_id=None;self.boot_hash=None
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
        leaf=observed[-1]
        # judged as the K9 requests judge their chains: no open root (POLICY's directories on the data volume carry signed
        # rows and are compared with them; for them this is a fact only)
        try:validate_chain([dict(row) for row in observed],path);acceptable=k9_root_group_rows(observed)
        except Refused:acceptable=False
        root_private=(leaf['uid'],leaf['gid'],leaf['mode'])==(0,0,K9_PRIVATE_DIRECTORY_MODE)
        if private and not root_private:findings.append('DIRECTORY_NOT_ROOT_PRIVATE')
        if spec is None and not acceptable:findings.append('ROWS_NOT_ACCEPTABLE_TO_THE_K9_REQUESTS')
        # every component from "/": owned by root and closed to group and other writes (outside an open root)
        loose=[row['path'] for row in observed if not row_root_safe(row) or not k9_root_group_rows([row])]
        available=free_bytes(host,fd)
        facts.update(as_signed=None if spec is None else True,owner_uid=leaf['uid'],owner_gid=leaf['gid'],mode_octal='%04o'%leaf['mode'],
                     root_private=root_private,rows_acceptable_to_the_k9_requests=acceptable,
                     open_root=None,components_not_root_controlled=loose,
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

    def image(self):
        found=image_facts(self.commands,self.values['image_id']);equal=found['id']==self.values['image_id'];revision=found['revision_label']==K9_CODE_REVISION
        self.image_ok=equal and revision
        return k9_item(findings=([] if equal else ['IMAGE_ID_MISMATCH'])+([] if revision else ['IMAGE_REVISION_MISMATCH']),id_equal_signed=equal,
                       revision_equal_signed=revision,repo_tag_count=found['repo_tag_count'])

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
                       container=signed['container'],container_id=found['id'],image_id_equal_signed=equal,running=running,state=found['state'],restarts=found['restarts'],
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


# ---- Positive empty-tree observations, limited to compiled entries under the held SECRETS descriptor.
def bootstrap_key():return sha(canonical([BOOTSTRAP_EPOCH,BOOTSTRAP_SLOT]))
def claim_name():return 'bootstrap-'+bootstrap_key()+'.claim'

def validate_plan(plan):
    need(plan['mode']==BOOTSTRAP_MODE,'BOOTSTRAP_MODE_INVALID')
    need(plan['epoch']==BOOTSTRAP_EPOCH,'BOOTSTRAP_EPOCH_INVALID')
    need(plan['slot']==BOOTSTRAP_SLOT and plan['attempt_key']==bootstrap_key(),'BOOTSTRAP_SLOT_OR_KEY_INVALID')
    need(instant(plan['window']['not_before'])==instant(BOOTSTRAP_START) and instant(plan['window']['expires_at'])==instant(BOOTSTRAP_END),'BOOTSTRAP_WINDOW_NOT_COMPILED')
    values=plan['constants'];need(type(values) is dict and set(values)==BOOTSTRAP_CONSTANT_KEYS,'CONSTANTS_INVALID')
    need(values['package_sha256']==K9_PACKAGE_SHA256 and values['code_revision']==K9_CODE_REVISION and values['placement']==K9_PLACEMENT,'CONSTANTS_NOT_COMPILED')
    need(values['disk_floor_bytes']==K9_DISK_FLOOR_BYTES,'DISK_FLOOR_NOT_COMPILED')
    need(all(hexpin(values[key]) for key in ('release_sha256','policy_sha256','runner_sha256')) and text(values['image_id'],IMAGE_ID),'CONSTANTS_INVALID')
    rows=plan['parent_rows'];need(type(rows) is dict and set(rows)==set(K9_PARENT_CHAINS),'PARENT_ROWS_INVALID')
    for name in K9_PARENT_CHAINS:k9_chain(rows[name],K9_PLACEMENT[name],name in K9_RECEIVES_ENTRY,'PARENT_ROWS_INVALID')
    root_rows=rows['secrets']['rows'];need((root_rows[-2]['uid'],root_rows[-2]['gid'],root_rows[-2]['mode'])==(0,0,0o700),'K9_ROOT_NOT_ROOT_PRIVATE')
    need(all((rows[name]['rows'][-1]['uid'],rows[name]['rows'][-1]['gid'],rows[name]['rows'][-1]['mode'])==(0,0,0o700) for name in K9_PARENT_CHAINS),'PARENT_NOT_ROOT_PRIVATE')
    volume=validate_chain(plan['data_volume_chain'],K9_DATA_VOLUME,K9_DATA_VOLUME)
    need(mount_point_of(volume)==K9_DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    sources=plan['source_rows']
    need(type(sources) is list and len(sources)==len(SOURCE_PATHS) and all(type(row) is dict and set(row)==set(SOURCE_ROW_KEYS) and row['path']==path and integer(row['device']) and integer(row['inode'],1) and integer(row['uid']) and integer(row['gid']) and integer(row['mode'],0,0o7777) and integer(row['mtime_ns']) and integer(row['ctime_ns']) for row,path in zip(sources,SOURCE_PATHS)),'SOURCE_ROWS_INVALID')
    need(all(row['device']==volume[-1]['device'] and not row['mode']&0o022 and row['uid'] in (0,volume[-1]['uid']) for row in sources),'SOURCE_ROWS_UNSAFE')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    k9_policy_read(plan)
    need(all(plan['policy_read'][key]['directory']['open_root'] in (None,K9_DATA_VOLUME) for key in ('policy','release')),'BOOTSTRAP_NEW_OPEN_ROOT_NOT_ALLOWED')
    need(plan['policy_read']['worker']['container']=='c3po-r2d2-worker-1','WORKER_NAME_NOT_COMPILED')


def effects_of(plan):
    return {'operation':OPERATION,'mode':BOOTSTRAP_MODE,'epoch':BOOTSTRAP_EPOCH,'slot':BOOTSTRAP_SLOT,'attempt_key':bootstrap_key(),
            'constants':plan['constants'],'parent_rows':{name:dict(chain_effects(item['rows']),open_root=None) for name,item in plan['parent_rows'].items()},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'reads':{'policy':k9_host_file(plan,'policy'),'release':k9_host_file(plan,'release'),'expected_live_environment':k9_expected_environment(plan),'secret_contents':False,'september_sources':'metadata_only','worker':'c3po-r2d2-worker-1'},
            'claim':{'path':K9_PLACEMENT['claims']+'/'+claim_name(),'key':bootstrap_key(),'name':claim_name(),'schema':'HOSTOPS02_BOOTSTRAP_EPOCH_CLAIM_V1','uid':0,'gid':0,'mode_octal':'0600','links':1,'file_fsync':True,'directory_fsync':True,'never_remove':True,'key_uses_go_hash':False},
            'writes_at_most':1,'claims_at_most':1,'other_files_changed':False,'containers_run':0,'containers_removed':0,'activation':False,
            'uncertain_creation_consumes_slot':True,'receipt_reuse_not_same_as_execution':True,
            'environment_read_limit':'Python receives five LIVE booleans only; Docker CLI/daemon process Config.Env internally'}

def success_of(plan):return COMPLETE_OUTCOME

SCOPE_STATEMENT=('First-night bootstrap: observes boot and worker identity, installed policy/release hashes, image/revision and five LIVE comparison booleans; verifies held root-controlled chains, runner and September source metadata. Positively verifies SECRETS empty and EMITTER/provider.env/risk-db.env absent by lstat of fixed names under the held SECRETS descriptor; derives password ABSENT_PARENT_CONFIRMED without opening a nonexistent directory. The only host effect is one durable exclusive 0600 claim in the compiled CLAIMS directory, keyed by epoch and bootstrap slot, independent of GO. Never removes a claim, repairs a mode or retries after possible creation. Does not open secret contents. Docker CLI/daemon process the inspect object including Config.Env; this Python process receives only five approved presence/equality booleans, never secret values. This is not a claim that no other process reads environment entries.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,'writes_allowed':True,'activation_allowed':False,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,'command_variables':COMMAND_VARIABLES,
       'epoch':BOOTSTRAP_EPOCH,'mode':BOOTSTRAP_MODE,'slot':BOOTSTRAP_SLOT,'window':{'not_before':BOOTSTRAP_START,'expires_at':BOOTSTRAP_END},'placement':K9_PLACEMENT,
       'claim':{'key':bootstrap_key(),'name':claim_name(),'outside_secrets':True,'independent_of_go':True,'mode_octal':'0600','never_remove':True,'possible_creation_is_consumed':True},
       'never':['secret contents opened','secret values in this Python process or receipt','unlink','mkdir','chmod','chown','rename','truncate','claim removal','claim repair','SPARE','daily policy attempt','docker run','docker exec','activation'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,'runner_bytes':K9_MAX_RUNNER_FILE,'policy_bytes':K9_MAX_POLICY_FILE,'release_bytes':K9_MAX_RELEASE_FILE,'claim_bytes':4096,'claim_count':1}}
SCOPE_SHA256=sha(canonical(SCOPE))


def private_directory(reader,key,name,spec):
    item=reader.directory(key,K9_PLACEMENT[name],spec)
    handle=reader.held.get(key)
    if handle is not None:
        item['pinned']=True;item['observed_rows']=[dict(row) for row in handle.rows]
        item['rows_acceptable_to_the_k9_requests']=k9_root_group_rows(handle.rows)
    return item


def empty_secrets(reader):
    parent=reader.held.get('SECRETS');need(parent is not None,'DIRECTORY_NOT_HELD');parent.verify(reader.gate)
    count=count_entries(reader.host,parent.fd,reader.gate,K9_MAX_COUNT);parent.verify(reader.gate)
    return k9_item(findings=[] if count==0 else ['SECRETS_DIRECTORY_NOT_EMPTY'],entries=count,held=True,pinned=True,root_private=True,
                   path=K9_PLACEMENT['secrets'],observed_rows=[dict(row) for row in parent.rows],rows_acceptable_to_the_k9_requests=True)


def absent_entry(reader,name):
    parent=reader.held.get('SECRETS');need(parent is not None,'DIRECTORY_NOT_HELD');parent.verify(reader.gate);reader.gate()
    try:reader.host.lstat(name,parent.fd)
    except FileNotFoundError as error:
        need(error.errno==errno.ENOENT,'ABSENCE_ERRNO_NOT_ENOENT');parent.verify(reader.gate)
        return k9_item(exists=False,absence_confirmed=True,errno=errno.ENOENT,parent_item='directory:SECRETS',name=name,
                       code='ABSENT_FROM_HELD_SECRETS' if name=='emitter' else 'ABSENT_ENTRY_CONFIRMED',held=False if name=='emitter' else None,
                       path=K9_PLACEMENT['secrets']+'/'+name)
    return k9_item(findings=['BOOTSTRAP_ENTRY_ALREADY_PRESENT'],exists=True,absence_confirmed=False,parent_item='directory:SECRETS',name=name)


def absent_password(emitter):
    need(emitter.get('status')=='COMPLETE' and emitter.get('matches') is True and emitter.get('exists') is False and emitter.get('absence_confirmed') is True,'EMITTER_ABSENCE_NOT_CONFIRMED')
    return k9_item(exists=False,parent_absent_confirmed=True,code='ABSENT_PARENT_CONFIRMED',path=K9_PLACEMENT['emitter_password'],parent_item='directory:EMITTER')


def september_pinned(reader):
    item=reader.september_sources()
    if item.get('status')!='COMPLETE' or item.get('findings'):return item
    expected=reader.plan['source_rows'];seen=item.get('components') or []
    valid=len(seen)==len(expected) and item.get('data_volume_rows')==reader.plan['data_volume_chain']
    for observed,signed in zip(seen,expected):
        valid=valid and all(observed.get(key)==value for key,value in signed.items() if key!='mode') and observed.get('mode_octal')=='%04o'%signed['mode']
    leaves=[row for row in seen if row.get('path') in (SOURCE_PATHS[1],SOURCE_PATHS[4])]
    valid=valid and len(leaves)==2 and all(row.get('type')=='file' and row.get('nlink')==1 for row in leaves)
    return dict(item,findings=[] if valid else ['SEPTEMBER_SOURCE_NOT_THE_PINNED_ROWS'],matches=bool(valid),rows_equal_signed=bool(valid))


def claim_record():
    return {'state':'NOT_ATTEMPTED','code':None,'errno':None,'key':bootstrap_key(),'name':claim_name(),'path':K9_PLACEMENT['claims']+'/'+claim_name(),
            'possible_creation':False,'created_by_this_run':False,'usage_consumed':False,'file_fsync':False,'directory_fsync':False,'readback_verified':False,'parent_stable':False,'metadata':None}


def exclusive_epoch_claim(host,parent,gate,state,bound,boot,worker,row):
    fd=None;failed=None
    content=canonical({'schema':'HOSTOPS02_BOOTSTRAP_EPOCH_CLAIM_V1','epoch':BOOTSTRAP_EPOCH,'slot':BOOTSTRAP_SLOT,'attempt_key':bootstrap_key(),
                       'request_sha256':bound['request_sha256'],'go_sha256':bound['go_sha256'],'payload_sha256':bound['payload_sha256'],
                       'boot_id_sha256':boot,'worker_container_id':worker})
    need(len(content)<=4096,'CLAIM_CONTENT_LIMIT')
    try:
        parent.verify(gate);need(gate()>=15,'BUDGET_INSUFFICIENT_BEFORE_CLAIM')
        # Existence before our creating call is a proved no-effect refusal; never open or remove it.
        try:host.lstat(row['name'],parent.fd)
        except FileNotFoundError as error:need(error.errno==errno.ENOENT,'CLAIM_ABSENCE_ERRNO')
        else:
            row.update(state='EXISTING',code='BOOTSTRAP_EPOCH_ALREADY_CLAIMED',usage_consumed=True);return row
        parent.verify(gate);gate();row.update(state='CREATE_UNCERTAIN',possible_creation=True,created_by_this_run=None,usage_consumed=True)
        state.issue()
        try:fd=host.create(row['name'],CLAIM_FLAGS,0o600,parent.fd)
        except OSError as error:
            if error.errno==errno.EEXIST:
                state.fail();row.update(state='EXISTING',possible_creation=False,created_by_this_run=False,usage_consumed=True,code='BOOTSTRAP_EPOCH_ALREADY_CLAIMED',errno=error.errno);return row
            state.unknown();row.update(code='CLAIM_CREATE_UNCERTAIN',errno=error.errno);return row
        except BaseException:
            state.unknown();raise
        state.done();row.update(state='CREATED',created_by_this_run=True)
        gate();info=host.fstat(fd);named=host.lstat(row['name'],parent.fd)
        row['metadata']=dict(shape(info),links=info.st_nlink)
        need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o600,1),'CLAIM_METADATA_INVALID')
        need(info.st_dev==parent.identity[0] and (named.st_dev,named.st_ino)==(info.st_dev,info.st_ino),'CLAIM_NAME_OR_DEVICE_CHANGED')
        offset=0
        while offset<len(content):
            gate();state.issue()
            try:written=host.write(fd,content[offset:])
            except BaseException:state.unknown();raise
            state.done();need(type(written) is int and 0<written<=len(content)-offset,'CLAIM_WRITE_INCOMPLETE');offset+=written
        row['state']='WRITTEN';parent.verify(gate);gate();state.issue()
        try:host.fsync(fd)
        except BaseException:state.unknown();raise
        state.done();row.update(state='FILE_SYNCED',file_fsync=True)
        parent.verify(gate);gate();state.issue()
        try:host.fsync(parent.fd)
        except BaseException:state.unknown();raise
        state.done();row.update(state='DIRECTORY_SYNCED',directory_fsync=True)
        parent.verify(gate);row['parent_stable']=True
        readback,after=read_regular(host,row['name'],parent.fd,gate,4096);named_after=host.lstat(row['name'],parent.fd)
        need(readback==content and (after.st_dev,after.st_ino)==(info.st_dev,info.st_ino)==(named_after.st_dev,named_after.st_ino),'CLAIM_READBACK_INVALID')
        need((after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode),after.st_nlink)==(0,0,0o600,1),'CLAIM_READBACK_METADATA_INVALID')
        row.update(readback_verified=True,content_sha256=sha(content));parent.verify(gate);gate();row['state']='VERIFIED'
    except BaseException as error:
        failed=error;row['code']=code_of(error,'CLAIM_EFFECT_FAILED')
        if isinstance(error,OSError):row['errno']=error.errno
    finally:
        if fd is not None:
            try:host.close(fd)
            except BaseException as error:
                row['close_error']=safe(error)
                if row['code'] is None:row['code']='CLAIM_DESCRIPTOR_CLOSE_FAILED'
                if row['state']=='VERIFIED':row['state']='DIRECTORY_SYNCED'
    return row


def _reduce_bootstrap_items(receipt):
    receipt['expectations_met']=False;receipt['dependents_hold']=True
    receipt['items']={name:{key:item.get(key) for key in ('status','matches','findings','code','errno')} for name,item in (receipt.get('items') or {}).items()}
REDUCTIONS=[('BOOTSTRAP_ITEMS_REDUCED_TO_STATUS',_reduce_bootstrap_items)]


def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic();items={};row=claim_record();failure=None
    commands=Commands(host,gate);reader=BootstrapReader(plan,host,gate,commands,bound,clock,monotonic)
    first_worker=None;first_environment=None
    def observe(label,action):
        gate()
        try:found=action()
        except Exception as error:found=safe(error)
        items[label]=found
        if found.get('status')!='COMPLETE' or found.get('matches') is not True or found.get('findings'):
            raise Refused(found.get('code') if text(found.get('code'),CODE) else (found.get('findings') or ['BOOTSTRAP_OBSERVATION_INCOMPLETE'])[0])
        return found
    try:
        gate();state.started=True;need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
        validate_plan(plan)
        observe('boot',reader.boot)
        # All reads occur before the first possible claim effect.
        rows=plan['parent_rows']
        root_spec=dict(rows['secrets'],path=K9_ROOT,rows=rows['secrets']['rows'][:-1])
        observe('directory:K9_ROOT',lambda:private_directory(reader,'K9_ROOT','k9_root',root_spec))
        for key,name in K9_TREE_DIRECTORIES:
            if key in ('K9_ROOT','EMITTER'):continue
            observe('directory:'+key,lambda key=key,name=name:private_directory(reader,key,name,rows[name]))
        observe('directory:SECRETS',lambda:empty_secrets(reader))
        emitter=observe('directory:EMITTER',lambda:absent_entry(reader,'emitter'))
        observe('secret:EMITTER/password',lambda:absent_password(emitter))
        for name in ('provider.env','risk-db.env'):observe('secret:SECRETS/'+name,lambda name=name:absent_entry(reader,name))
        observe('k9_filesystem',lambda:reader.k9_filesystem(K9_DISK_FLOOR_BYTES))
        observe('runner_file',reader.runner_file)
        observe('september_sources',lambda:september_pinned(reader))
        for key in ('policy','release'):
            spec=plan['policy_read'][key]['directory']
            observe('directory:'+key.upper(),lambda key=key,spec=spec:reader.directory(key.upper(),spec['path'],spec,private=False))
            observe(key+'_file',lambda key=key:reader.installed(key))
        first_worker=observe('worker',reader.worker)
        first_environment=observe('worker_environment',reader.worker_environment)
        observe('image',reader.image)
        # Confirm the observed identity and environment have not changed while other items were read.
        worker=observe('worker_stable',reader.worker)
        need(worker==first_worker,'WORKER_CHANGED_DURING_BOOTSTRAP')
        environment=observe('worker_environment_stable',reader.worker_environment)
        need(environment==first_environment,'WORKER_ENVIRONMENT_CHANGED_DURING_BOOTSTRAP')
        seen_boot=boot_id_sha256(host,gate)
        observe('boot_stable',lambda:k9_item(findings=[] if seen_boot==reader.boot_hash else ['BOOT_CHANGED_DURING_BOOTSTRAP'],equal_to_first=seen_boot==reader.boot_hash))
        # Repeat the positive absence/emptiness checks immediately before the claim.
        observe('directory:SECRETS',lambda:empty_secrets(reader));emitter=observe('directory:EMITTER',lambda:absent_entry(reader,'emitter'))
        observe('secret:EMITTER/password',lambda:absent_password(emitter))
        for name in ('provider.env','risk-db.env'):observe('secret:SECRETS/'+name,lambda name=name:absent_entry(reader,name))
        observe('directories_stable',reader.stable)
        parent=reader.held['CLAIMS']
        exclusive_epoch_claim(host,parent,gate,state,bound,reader.boot_hash,reader.worker_id,row)
        if row['state']!='VERIFIED':raise Refused(row['code'] or 'BOOTSTRAP_CLAIM_NOT_VERIFIED')
        # After the effect, these are readbacks: a change consumes the claim and holds every dependent.
        worker=observe('worker_postclaim',reader.worker)
        need(worker==first_worker,'WORKER_CHANGED_AFTER_CLAIM')
        environment=observe('worker_environment_postclaim',reader.worker_environment)
        need(environment==first_environment,'WORKER_ENVIRONMENT_CHANGED_AFTER_CLAIM')
        observe('image_postclaim',reader.image)
        for key in ('policy','release'):observe(key+'_file_postclaim',lambda key=key:reader.installed(key))
        observe('runner_file_postclaim',reader.runner_file)
        observe('september_sources_postclaim',lambda:september_pinned(reader))
        observe('k9_filesystem_postclaim',lambda:reader.k9_filesystem(K9_DISK_FLOOR_BYTES))
        last_boot=boot_id_sha256(host,gate)
        observe('boot_postclaim',lambda:k9_item(findings=[] if last_boot==reader.boot_hash else ['BOOT_CHANGED_AFTER_CLAIM'],equal_to_first=last_boot==reader.boot_hash))
        observe('directory:SECRETS_postclaim',lambda:empty_secrets(reader))
        emitter_after=observe('directory:EMITTER_postclaim',lambda:absent_entry(reader,'emitter'))
        observe('secret:EMITTER/password_postclaim',lambda:absent_password(emitter_after))
        for name in ('provider.env','risk-db.env'):observe('secret:SECRETS/'+name+'_postclaim',lambda name=name:absent_entry(reader,name))
        observe('directories_stable_postclaim',reader.stable)
        gate()
    except BaseException as error:
        failure=code_of(error,'BOOTSTRAP_FAILED');items['failure']=safe(error)
    finally:
        cleanup=[]
        for key,handle in reader.held.items():
            try:handle.close()
            except BaseException as error:cleanup.append(dict(item=key,**safe(error)))
        if cleanup:
            items['descriptor_cleanup']={'status':'UNAVAILABLE','code':'BOOTSTRAP_DESCRIPTOR_CLOSE_FAILED','failures':cleanup}
            if failure is None:failure='BOOTSTRAP_DESCRIPTOR_CLOSE_FAILED'
    final_mono=None
    try:
        final_wall,final_mono=clock(),monotonic()
        final_clock={'utc_start':begun.isoformat(),'utc_end':final_wall.isoformat(),'monotonic_elapsed_ms':int((final_mono-mark)*1000)}
    except BaseException as error:
        final_clock=None;items['final_clock_failure']=safe(error)
    valid_clock=False
    if type(final_clock) is dict:
        try:
            end=instant(final_clock['utc_end']);start=instant(final_clock['utc_start'])
            last_wall=getattr(gate,'wall',None);last_mono=getattr(gate,'mono',None)
            valid_clock=(instant(BOOTSTRAP_START)<=start<=end<instant(BOOTSTRAP_END) and integer(final_clock['monotonic_elapsed_ms'],0,MAX_SECONDS*1000-1)
                         and (last_wall is None or end>=last_wall)
                         and (last_mono is None or (final_mono is not None and final_mono>=last_mono)))
        except (Refused,KeyError,TypeError):valid_clock=False
    if not valid_clock and failure is None:failure='BOOTSTRAP_FINAL_CLOCK_INVALID'
    effect=row['possible_creation'] or row['created_by_this_run'] is True or not state.clean()
    if failure is None and row['state']=='VERIFIED':status,outcome,code=COMPLETE_STATUS,COMPLETE_OUTCOME,None
    elif effect:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,failure or row['code'] or 'BOOTSTRAP_CLAIM_UNCERTAIN'
    else:status,outcome,code=REFUSED_STATUS,REFUSED_OUTCOME,failure or row['code'] or 'BOOTSTRAP_REFUSED'
    findings=sorted({code for item in items.values() for code in item.get('findings') or []})
    return seal(envelope(status,outcome,code,dict(bound,mode=BOOTSTRAP_MODE,epoch=BOOTSTRAP_EPOCH,slot=BOOTSTRAP_SLOT,attempt_key=bootstrap_key(),
        boot_id_sha256=reader.boot_hash,claim=row,effects=effects_of(plan),items=items,findings=findings,
        items_not_complete=sorted(name for name,item in items.items() if item.get('status')!='COMPLETE'),
        expectations_met=status==COMPLETE_STATUS,mutating_calls=state.counts(),clock=final_clock,
        commands_started=dict(commands.started),phase_reached='CLAIM' if row['state']!='NOT_ATTEMPTED' else 'PRECHECK',
        nothing_changed_by_this_run=not effect,dependents_hold=status!=COMPLETE_STATUS,secret_contents_opened=False,
        environment_inspection_scope='Docker CLI/daemon process Config.Env; Python receives five approved LIVE booleans only')))
# ==== END OP_BOOTSTRAP_IDENTITY ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
