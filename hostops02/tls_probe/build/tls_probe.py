"""OP_TLS_PROBE: rehearsal item 2 of the supervisor README at dd4ec4bb ("A TLS connection to socket.massive.com:443
succeeds from @NETWORK@, without a token"), for the network the owner's sheet chose, the engine's default network
bridge. A reading source of the frozen core: it creates and changes nothing on the filesystem of the host.

It starts ONE attached container of the signed image ID (the production backend image by its local ID, carrying the
release revision label and the signed retention tag) on the network bridge, removed by the engine when its process
ends, with no bind, no environment file, no DOCKER_CONFIG and no token, a read-only root filesystem, uid 0 and no
capability, and gives it on standard input the pinned probe script that this source carries. The script resolves the
provider host, opens one TCP connection to port 443 and makes one TLS handshake with Python's default verifying
context (server name socket.massive.com), then closes. It sends no application byte and no HTTP request, and prints
one JSON line of counts, booleans, constant codes, the SHA-256 of the leaf certificate and timings. Before the
container: the executor, the boot of the evidence, the image by ID and by its retention tag, and the container list,
under which a refusal has started nothing. After it: the container list again, so that the receipt says whether a
container of its name, or any container that was not there before, is still listed. Success is one outcome: TLS
verified to the provider host, and the container removed. Nothing is removed, retried or repaired by this process.
The caller authenticates exact request/authority/GO/source bytes first; the source accepts only a window inside the
band of the weekend authority (2026-10-04, 11:45 to 12:30 UTC).
No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
CORE_PARTS={'core': 'ecf72edaf2bae478186e642bc93804bd567384c5d13dfab2bb4c4d55d00eef7a', 'runner': '2a1cc5bc73a0d456eb596aea65caaffcf7dd3834cbbd844a02a69486bbdacaa7', 'docker': '4602f6f07a4502a3decec99cd415737efb429e3b1a188b368939a090bc3b3aa5'}
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

# ==== BEGIN OP_TLS_PROBE (this operation only) ====
OPERATION='GO_READONLY_HOSTOPS02_TLS_PROBE_01'
PHASE='READONLY_SUPERVISOR_TLS_PROBE'
REQUEST_SCHEMA='READONLY_HOSTOPS02_TLS_PROBE_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_TLS_PROBE_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_TLS_PROBE_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_TLS_PROBE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_TLS_PROBE_PLAN_V1'
SOURCE_NAME='tls_probe.py'
# The core's classes decide the name. The container this source starts writes to no host path (no bind at all), so its
# row is of kind CONTAINER, which a reading source may carry (CORE.md section 8, rule 1); a source that writes nothing is
# READ and named GO_READONLY_... (assemble.py refuses any other pairing). That class says nothing about the signature:
# the weekend authority (A1 rev 2, section 4.2, row C3) keeps this run under the owner's individual signature by hash.
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The image ID is read on the host by the precheck (README line 281: read after the deploy); the retention tag that
# must name that ID is the one supervisor operation 2 created (hostops01 provision, ledger of the tag).
PROVISION_OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)
# A1 section 5: the GO of an operation of its section 4 has a short window of at most 900 seconds inside the band.
MAX_GATE_SPAN_SECONDS=900
# A1 rev 2 (sha256 909573aa7431c5340711716fa0702e2d3dde58cbbe10b9b68da0fcca109e95ba), section 4.2, row C3: Sunday
# 04/10, 08:45 to 09:30 BRT, before the installation of the units (E3). The class READ allows nine days; this source
# narrows them to that one band, checked on the signed window in validate_plan, so at both layers (the dispatcher runs
# authenticate() before any claim). Saturday is not allowed: the authority gives C3 no band that day, its reserves are
# for reads only, and its section 5 never changes the day of a request.
PROBE_DAY='2026-10-04'
PROBE_BAND=('2026-10-04T11:45:00+00:00','2026-10-04T12:30:00+00:00')
COMPLETE_OUTCOME='TLS_VERIFIED_TO_THE_PROVIDER_HOST'
VERIFIED_WITH_FINDINGS_OUTCOME='TLS_VERIFIED_WITH_FINDINGS'
NOT_VERIFIED_OUTCOME='PROBE_RAN_TLS_NOT_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_PROBE_RESULT_UNKNOWN'
REFUSED_OUTCOME='REFUSED_NO_CONTAINER_STARTED'
REDUCED_OUTCOME='RECEIPT_REDUCED_PROBE_NOT_COMPLETE'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_CONTAINER_MAY_REMAIN'
PLAN_KEYS=frozenset(('image_id','image_revision','retention_tag','script_sha256','evidence_boot_id_sha256'))
# The release whose image is in production (main at dd4ec4bb), and the grammar of the retention tag of supervisor
# operation 2 (hostops01 rev 3, provision/provision_dirs.py lines 632 and 633: REPOSITORY and TAG).
RELEASE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
RETENTION_TAG='c3po/backend:massive-supervisor-[a-z0-9][a-z0-9.-]{0,40}'
# The provider host and port the supervisor connects to, from the release code, never typed: the transport opens
# wss://socket.massive.com/stocks (c3po/backend/app/r2d2_v2_massive_transport.py line 99 at dd4ec4bb) with no port in
# the URI, so the port is the wss default 443 (the websockets client: uri.py, "443 if secure"); the README's rehearsal
# item 2 names the same pair (c3po/deployment/massive-supervisor/README.md line 580).
PROVIDER_HOST='socket.massive.com'
PROVIDER_PORT=443
PROVIDER_SOURCE=('c3po/backend/app/r2d2_v2_massive_transport.py:99 (wss://socket.massive.com/stocks, wss default port 443) and '
                 'c3po/deployment/massive-supervisor/README.md:580 at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858')
CONTAINER_PREFIX='hostops02-tls-'
PROBE_COMMAND=['python','-I','-B','-']
PROBE_NETWORK='bridge'
# The core's RUN_PREFIX (the README's catalog argv) with one word changed: the network is bridge, the network of the
# owner's sheet (line 7) for the unit, instead of none. Same options, nothing added: removed on exit, standard input
# attached, never a pull, an init process, uid 0, read-only root filesystem, no capability, no new privilege.
PROBE_PREFIX=['run','--rm','-i','--pull','never','--init','--user','0:0','--network',PROBE_NETWORK,'--read-only','--cap-drop','ALL',
              '--security-opt','no-new-privileges']
# Seconds of the script (constants of its text, compared by a test): each step bounded, the whole ended by the
# kernel at ALARM, before the 20 s of the class RUN_SHORT at which the docker CLI is killed.
PROBE_SECONDS={'dns':4,'connect':4,'handshake':4,'alarm':14}
PROBE_ALARM_STATUS=142                        # 128 + SIGALRM, as docker-init reports a child the alarm killed
# The pinned probe script, given to the container on standard input and nothing else. Its bytes are part of this
# signed source; the SHA-256 and the size below are compared before anything is looked at.
PROBE_SCRIPT=r'''import signal
signal.alarm(14)
import hashlib, json, os, socket, ssl, sys, threading, time
# HOSTOPS02 C3, the TLS probe of supervisor rehearsal item 2. It resolves the provider host, opens ONE TCP connection
# and makes ONE TLS handshake with the default verifying context, then closes. It sends no application byte, no HTTP
# request and no credential, and it prints one JSON line of counts, booleans, constant codes, a hash and timings.
HOST = 'socket.massive.com'
PORT = 443
DNS_SECONDS = 4.0
CONNECT_SECONDS = 4.0
HANDSHAKE_SECONDS = 4.0
MAX_ADDRESSES = 16
NOT_FOUND = tuple(getattr(socket, name) for name in ('EAI_NONAME', 'EAI_NODATA') if hasattr(socket, name))
started = time.monotonic()
line = {'schema': 'HOSTOPS02_TLS_PROBE_LINE_V1', 'host': HOST, 'port': PORT,
        'context': {'verify_mode_required': False, 'check_hostname': False},
        'dns': {'answered': False, 'addresses': 0, 'ipv4': 0, 'ipv6': 0, 'code': None, 'ms': None},
        'tcp': {'connected': False, 'attempts': 0, 'family': None, 'code': None, 'ms': None},
        'tls': {'handshake': False, 'verified': False, 'version': None, 'cipher': None, 'leaf_sha256': None,
                'verify_code': None, 'code': None, 'ms': None},
        'application_bytes_sent': 0, 'status': None, 'total_ms': None}


def elapsed(since):
    return int((time.monotonic() - since) * 1000)


def finish(status):
    line['status'] = status
    line['total_ms'] = elapsed(started)
    sys.stdout.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
    sys.stdout.flush()
    os._exit(0)


def probe():
    context = ssl.create_default_context()
    line['context'] = {'verify_mode_required': context.verify_mode == ssl.CERT_REQUIRED,
                       'check_hostname': context.check_hostname is True}
    if not (line['context']['verify_mode_required'] and line['context']['check_hostname']):
        finish('TLS_CONTEXT_NOT_VERIFYING')
    found = {}

    def resolve():
        try:
            found['rows'] = socket.getaddrinfo(HOST, PORT, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        except socket.gaierror as error:
            found['code'] = 'DNS_NAME_NOT_RESOLVED' if error.errno in NOT_FOUND else 'DNS_FAILED'
        except Exception:
            found['code'] = 'DNS_FAILED'

    began = time.monotonic()
    worker = threading.Thread(target=resolve)
    worker.daemon = True
    worker.start()
    worker.join(DNS_SECONDS)
    line['dns']['ms'] = elapsed(began)
    if worker.is_alive():
        line['dns']['code'] = 'DNS_TIMEOUT'
        finish('DNS_NOT_ANSWERED')
    if 'rows' not in found:
        line['dns']['code'] = found.get('code', 'DNS_FAILED')
        finish('DNS_NOT_ANSWERED')
    addresses = []
    for family, _, _, _, address in found['rows']:
        if family in (socket.AF_INET, socket.AF_INET6) and (family, address) not in addresses:
            addresses.append((family, address))
    addresses = addresses[:MAX_ADDRESSES]
    line['dns']['addresses'] = len(addresses)
    line['dns']['ipv4'] = len([item for item in addresses if item[0] == socket.AF_INET])
    line['dns']['ipv6'] = len([item for item in addresses if item[0] == socket.AF_INET6])
    if not addresses:
        line['dns']['code'] = 'DNS_NO_ADDRESS'
        finish('DNS_NOT_ANSWERED')
    line['dns']['answered'] = True
    began = time.monotonic()
    deadline = began + CONNECT_SECONDS
    connection = None
    code = None
    for family, address in addresses:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        line['tcp']['attempts'] += 1
        candidate = socket.socket(family, socket.SOCK_STREAM)
        candidate.settimeout(left)
        try:
            candidate.connect(address)
        except socket.timeout:
            code = 'TCP_TIMEOUT'
        except ConnectionRefusedError:
            code = 'TCP_REFUSED'
        except OSError:
            code = 'TCP_UNREACHABLE'
        else:
            connection = candidate
            line['tcp']['family'] = 'ipv4' if family == socket.AF_INET else 'ipv6'
            break
        candidate.close()
    line['tcp']['ms'] = elapsed(began)
    if connection is None:
        line['tcp']['code'] = code or 'TCP_TIMEOUT'
        finish('TCP_NOT_CONNECTED')
    line['tcp']['connected'] = True
    began = time.monotonic()
    connection.settimeout(HANDSHAKE_SECONDS)
    try:
        tls = context.wrap_socket(connection, server_hostname=HOST, do_handshake_on_connect=False)
        tls.do_handshake()
    except ssl.SSLCertVerificationError as error:
        line['tls']['ms'] = elapsed(began)
        line['tls']['code'] = 'TLS_CERTIFICATE_NOT_VERIFIED'
        number = getattr(error, 'verify_code', None)
        line['tls']['verify_code'] = number if type(number) is int and 0 <= number <= 1000 else None
        finish('TLS_NOT_VERIFIED')
    except socket.timeout:
        line['tls']['ms'] = elapsed(began)
        line['tls']['code'] = 'TLS_HANDSHAKE_TIMEOUT'
        finish('TLS_HANDSHAKE_FAILED')
    except ssl.SSLError:
        line['tls']['ms'] = elapsed(began)
        line['tls']['code'] = 'TLS_PROTOCOL_ERROR'
        finish('TLS_HANDSHAKE_FAILED')
    except OSError:
        line['tls']['ms'] = elapsed(began)
        line['tls']['code'] = 'TLS_CONNECTION_ERROR'
        finish('TLS_HANDSHAKE_FAILED')
    line['tls']['ms'] = elapsed(began)
    leaf = tls.getpeercert(binary_form=True)
    cipher = tls.cipher()
    line['tls'].update(handshake=True, verified=True, version=tls.version(), cipher=cipher[0] if cipher else None,
                       leaf_sha256=hashlib.sha256(leaf).hexdigest() if leaf else None)
    tls.close()
    finish('TLS_VERIFIED')


try:
    probe()
except Exception:
    finish('PROBE_FAILED')
'''
PROBE_SCRIPT_SHA256='d625d84f41bdf91396211025afbb80afa0a42e960bc1a19cb9e95428c0619566'
PROBE_SCRIPT_BYTES=5746
# The one line the script prints, member by member. A line is copied into the receipt only after every member was
# checked against this grammar and the members agree with its status; otherwise only its size and hash are kept.
LINE_SCHEMA='HOSTOPS02_TLS_PROBE_LINE_V1'
LINE_KEYS=frozenset(('schema','host','port','context','dns','tcp','tls','application_bytes_sent','status','total_ms'))
LINE_CONTEXT_KEYS=frozenset(('verify_mode_required','check_hostname'))
LINE_DNS_KEYS=frozenset(('answered','addresses','ipv4','ipv6','code','ms'))
LINE_TCP_KEYS=frozenset(('connected','attempts','family','code','ms'))
LINE_TLS_KEYS=frozenset(('handshake','verified','version','cipher','leaf_sha256','verify_code','code','ms'))
LINE_STATUSES=('TLS_VERIFIED','DNS_NOT_ANSWERED','TCP_NOT_CONNECTED','TLS_NOT_VERIFIED','TLS_HANDSHAKE_FAILED','TLS_CONTEXT_NOT_VERIFYING','PROBE_FAILED')
DNS_CODES=('DNS_TIMEOUT','DNS_NAME_NOT_RESOLVED','DNS_FAILED','DNS_NO_ADDRESS')
TCP_CODES=('TCP_TIMEOUT','TCP_REFUSED','TCP_UNREACHABLE')
TLS_CODES=('TLS_CERTIFICATE_NOT_VERIFIED','TLS_HANDSHAKE_TIMEOUT','TLS_PROTOCOL_ERROR','TLS_CONNECTION_ERROR')
TLS_VERSIONS=('TLSv1.2','TLSv1.3')
CIPHER_NAME='[A-Z0-9][A-Z0-9_-]{0,63}'
MAX_ADDRESSES_COUNTED=16
MAX_LINE_MILLISECONDS=60000
MAX_VERIFY_CODE=1000
MAX_NEW_CONTAINER_ROWS=8
RUN_ROW='probe'
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID, then the signed retention tag','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          RUN_ROW:command_row('docker',PROBE_PREFIX,'--name hostops02-tls-<16 hex of the GO>, the signed image ID, python -I -B -; '
                              'the pinned probe script on standard input; no bind','RUN_SHORT','CONTAINER',stdin=True)}
SCOPE_STATEMENT=('Rehearsal item 2 of the supervisor README at dd4ec4bb: a TLS connection to socket.massive.com:443 from the network '
                 'bridge, without a token, before the supervisor units are installed. Starts one attached container of the signed image '
                 'ID (the production backend image by its local ID, with the release revision label and the signed retention tag) on the '
                 'network bridge: removed on exit, never a pull, an init process, uid 0, read-only root filesystem, no capability, no bind, '
                 'no environment file, no DOCKER_CONFIG and no token. Its standard input is the probe script whose SHA-256 is pinned in '
                 'this source: it resolves socket.massive.com, opens one TCP connection to port 443 and makes one TLS handshake with the '
                 'default verifying context for that host name, then closes; it sends no application byte and no HTTP request. The '
                 'receipt holds counts, booleans, constant codes, the SHA-256 of the leaf certificate, the TLS version and cipher names '
                 'and timings, never an address. Nothing on the filesystem of the host is created, changed or removed; no unit is '
                 'touched; no container is removed by this process; a timeout stops the docker CLI, not the container. Success is one '
                 'outcome: TLS verified to the provider host and the container gone.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'band':{'day':PROBE_DAY,'not_before':PROBE_BAND[0],'not_after':PROBE_BAND[1],
               'source':'A1 rev 2 (909573aa7431c5340711716fa0702e2d3dde58cbbe10b9b68da0fcca109e95ba), section 4.2, row C3'},
       'provider':{'host':PROVIDER_HOST,'port':PROVIDER_PORT,'source':PROVIDER_SOURCE},
       'container':{'prefix':PROBE_PREFIX,'name':CONTAINER_PREFIX+'<first 16 hex of the GO sha256>','command':PROBE_COMMAND,
                    'network':PROBE_NETWORK,'binds':[],'environment_file':None,'docker_config':None,'token':None},
       'script':{'sha256':PROBE_SCRIPT_SHA256,'bytes':PROBE_SCRIPT_BYTES,'carried_in_this_source':True,'seconds':PROBE_SECONDS,
                 'exit_status_of_its_alarm':PROBE_ALARM_STATUS,'context':'ssl.create_default_context(), server name '+PROVIDER_HOST,
                 'sends':'the TCP and TLS handshake only; no application byte, no HTTP request, no credential'},
       'line':{'schema':LINE_SCHEMA,'statuses':list(LINE_STATUSES),'dns_codes':list(DNS_CODES),'tcp_codes':list(TCP_CODES),
               'tls_codes':list(TLS_CODES),'tls_versions':list(TLS_VERSIONS),'cipher':CIPHER_NAME},
       'image':{'revision':RELEASE_REVISION,'retention_tag':RETENTION_TAG},
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH],
       'side_effects':['one attached docker run --rm: the engine creates a container named '+CONTAINER_PREFIX+'<first 16 hex of the GO sha256>, '
                       'attaches it to the network bridge and removes it when its process ends; it writes the output of the container to its log '
                       'driver, removed with the container',
                       'the container asks the DNS servers the engine gives the network bridge for socket.massive.com, opens one TCP connection '
                       'to port 443 of one of the answers and makes one TLS handshake (ClientHello with the server name socket.massive.com): '
                       'the provider sees a connection without any credential from the public address of the host',
                       'the script arms a 14 s alarm as its first statement, so its process ends by itself before the 20 s limit of the docker '
                       'CLI; a run whose CLI is killed first may leave the container to the engine until its process ends, and the receipt says '
                       'whether one of that name is listed; a container created and never started stays in the state created, and no source '
                       'of this family removes a container',
                       'the docker CLI runs with the fixed environment of the core and no DOCKER_CONFIG: it reads the configuration of root, as '
                       'the precheck of this family did'],
       'never':['a bind or mount of any host path','an environment file or a variable given to the container','the token or any path of '
                '/etc/c3po-bar','an HTTP request or any application byte to the provider','a second connection or a retry','docker exec',
                'a shell','systemctl','a pull','a network other than bridge','--privileged, a device or a capability',
                'the removal of any container','any write on the filesystem of the host','an address in the receipt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'addresses_counted':MAX_ADDRESSES_COUNTED,'line_milliseconds':MAX_LINE_MILLISECONDS,'new_container_rows':MAX_NEW_CONTAINER_ROWS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this source can do to the host: the read primitives and the three signed commands."""


def script_bytes():
    """The pinned probe script, from the constant this source carries. Nothing else is ever given to the container."""
    raw=PROBE_SCRIPT.encode('ascii')
    need(len(raw)==PROBE_SCRIPT_BYTES and sha(raw)==PROBE_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');return raw

def container_name(bound):
    """The name the engine gives the container: the prefix and the first 16 hex of the GO hash (one name per GO)."""
    return CONTAINER_PREFIX+bound['go_sha256'][:16]

def validate_window(window):
    """The signed window lies in the band of the authority: the one day, from 11:45 to 12:30 UTC."""
    start,end=instant(window['not_before']),instant(window['expires_at'])
    need(start.date().isoformat()==PROBE_DAY,'PROBE_DAY_NOT_IN_SCOPE')
    need(instant(PROBE_BAND[0])<=start and end<=instant(PROBE_BAND[1]),'PROBE_WINDOW_OUTSIDE_THE_BAND')

def validate_members(plan):
    """Every member of the plan but the window: refused from the bytes, before any claim."""
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(type(plan['script_sha256']) is str and plan['script_sha256']==PROBE_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');script_bytes()
    need(type(plan['image_revision']) is str and plan['image_revision']==RELEASE_REVISION,'IMAGE_REVISION_NOT_THE_RELEASE')
    need(text(plan['retention_tag'],RETENTION_TAG),'RETENTION_TAG_INVALID')
    run_arguments(RUN_ROW,plan['image_id'],[],PROBE_COMMAND,CONTAINER_PREFIX+'0'*16)

def validate_plan(plan):
    validate_window(plan['window'])
    validate_members(plan)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,
            'container':{'image_id':plan['image_id'],'image_revision':plan['image_revision'],'retention_tag':plan['retention_tag'],
                         'docker_arguments':PROBE_PREFIX+['--name',CONTAINER_PREFIX+'<first 16 hex of the GO sha256>',plan['image_id']]+PROBE_COMMAND,
                         'network':PROBE_NETWORK,'binds':[],'environment_file':None,'docker_config_variable':None,'token':None,
                         'standard_input':{'sha256':PROBE_SCRIPT_SHA256,'bytes':PROBE_SCRIPT_BYTES},
                         'time_limit_seconds':COMMAND_CLASSES[COMMANDS[RUN_ROW]['class']]['seconds'],'alarm_seconds':PROBE_SECONDS['alarm'],
                         'removed_by_the_engine':True},
            'provider':{'host':PROVIDER_HOST,'port':PROVIDER_PORT,'source':PROVIDER_SOURCE,'connections':1,'tls_handshakes':1,
                        'application_bytes':0,'http_request':False,'credential':False},
            'probe_seconds':PROBE_SECONDS,
            'band':{'day':PROBE_DAY,'not_before':PROBE_BAND[0],'not_after':PROBE_BAND[1]},
            'success_outcome':success_of(plan),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'writes':0,'removes':[],'activation':False,'containers_run':1}
def success_of(plan):return COMPLETE_OUTCOME


def line_grammar(row):
    """True when the printed object is exactly what the script prints: every member of its type and range, and the
    members in agreement with its status. Pure; never raises for a dict."""
    def flag(value):return type(value) is bool
    def milliseconds(value):return value is None or integer(value,0,MAX_LINE_MILLISECONDS)
    def code(value,codes):return value is None or (type(value) is str and value in codes)
    if not (set(row)==LINE_KEYS and row['schema']==LINE_SCHEMA and row['host']==PROVIDER_HOST and type(row['port']) is int
            and row['port']==PROVIDER_PORT and type(row['application_bytes_sent']) is int and row['application_bytes_sent']==0
            and type(row['status']) is str and row['status'] in LINE_STATUSES and integer(row['total_ms'],0,MAX_LINE_MILLISECONDS)):return False
    context,dns,tcp,tls=row['context'],row['dns'],row['tcp'],row['tls']
    if not (type(context) is dict and set(context)==LINE_CONTEXT_KEYS and flag(context['verify_mode_required']) and flag(context['check_hostname'])):return False
    if not (type(dns) is dict and set(dns)==LINE_DNS_KEYS and flag(dns['answered']) and integer(dns['addresses'],0,MAX_ADDRESSES_COUNTED)
            and integer(dns['ipv4'],0,MAX_ADDRESSES_COUNTED) and integer(dns['ipv6'],0,MAX_ADDRESSES_COUNTED)
            and dns['ipv4']+dns['ipv6']==dns['addresses'] and code(dns['code'],DNS_CODES) and milliseconds(dns['ms'])):return False
    if not (type(tcp) is dict and set(tcp)==LINE_TCP_KEYS and flag(tcp['connected']) and integer(tcp['attempts'],0,MAX_ADDRESSES_COUNTED)
            and tcp['attempts']<=dns['addresses'] and (tcp['family'] is None or tcp['family'] in ('ipv4','ipv6'))
            and code(tcp['code'],TCP_CODES) and milliseconds(tcp['ms'])):return False
    if not (type(tls) is dict and set(tls)==LINE_TLS_KEYS and flag(tls['handshake']) and flag(tls['verified'])
            and (tls['version'] is None or (type(tls['version']) is str and tls['version'] in TLS_VERSIONS))
            and (tls['cipher'] is None or text(tls['cipher'],CIPHER_NAME)) and (tls['leaf_sha256'] is None or hexpin(tls['leaf_sha256']))
            and (tls['verify_code'] is None or integer(tls['verify_code'],0,MAX_VERIFY_CODE)) and code(tls['code'],TLS_CODES)
            and milliseconds(tls['ms'])):return False
    verifying=context['verify_mode_required'] and context['check_hostname']
    nothing_after_dns=not tcp['connected'] and tcp['attempts']==0 and tcp['family'] is None and tcp['code'] is None
    no_handshake=not tls['handshake'] and not tls['verified'] and tls['version'] is None and tls['cipher'] is None and tls['leaf_sha256'] is None
    untouched_tls=no_handshake and tls['code'] is None and tls['verify_code'] is None
    answered=dns['answered'] and dns['addresses']>=1 and dns['code'] is None
    connected=tcp['connected'] and tcp['attempts']>=1 and tcp['family'] is not None and tcp['code'] is None
    status=row['status']
    if status=='TLS_VERIFIED':
        return (verifying and answered and connected and tls['handshake'] and tls['verified'] and tls['version'] is not None
                and tls['cipher'] is not None and tls['leaf_sha256'] is not None and tls['code'] is None and tls['verify_code'] is None)
    if status=='DNS_NOT_ANSWERED':return verifying and not dns['answered'] and dns['code'] is not None and nothing_after_dns and untouched_tls
    if status=='TCP_NOT_CONNECTED':
        return verifying and answered and not tcp['connected'] and tcp['family'] is None and tcp['code'] is not None and untouched_tls
    if status=='TLS_NOT_VERIFIED':return verifying and answered and connected and no_handshake and tls['code']=='TLS_CERTIFICATE_NOT_VERIFIED'
    if status=='TLS_HANDSHAKE_FAILED':
        return (verifying and answered and connected and no_handshake and tls['code'] in TLS_CODES and tls['code']!='TLS_CERTIFICATE_NOT_VERIFIED'
                and tls['verify_code'] is None)
    if status=='TLS_CONTEXT_NOT_VERIFYING':return not verifying and not dns['answered'] and dns['code'] is None and nothing_after_dns and untouched_tls
    return True                                                       # PROBE_FAILED: the script's own catch-all, members as they were

def probe_line(result):
    """What the container printed, reduced to what may leave this process. Every member of a line that meets the
    grammar is copied (counts, booleans, constant codes, the TLS version and cipher names, a hash, timings); of any other
    output only its size and hash are kept, never a byte of it."""
    output=result['output'] if type(result.get('output')) is bytes else b''
    out={'returncode':result['returncode'],'bytes':len(output),'sha256':sha(output) if output else None,'one_json_line':False,'valid':False,
         'status':None,'context':None,'dns':None,'tcp':None,'tls':None,'application_bytes_sent':None,'total_ms':None}
    try:row=single_line(output)
    except Refused:return out
    out['one_json_line']=True
    if not line_grammar(row):return out
    out.update(valid=True,status=row['status'],context=dict(row['context']),dns=dict(row['dns']),tcp=dict(row['tcp']),tls=dict(row['tls']),
               application_bytes_sent=row['application_bytes_sent'],total_ms=row['total_ms'])
    return out

def probe_code(probe):
    """The constant code of a valid line that is not a verified TLS: the step that failed, else the status."""
    return probe['dns']['code'] or probe['tcp']['code'] or probe['tls']['code'] or probe['status']

def run_verdict(result,probe,after):
    """(status, outcome, code) once the container was started. A verified TLS that left anything behind, or whose CLI
    reported one of docker's own statuses, is a finding beside the verified line; a valid line that is not a verified TLS
    is the probe's own answer; anything else leaves the result unknown."""
    if not result['returned']:return PARTIAL_STATUS,PARTIAL_OUTCOME,result['code'] or 'COMMAND_FAILED'
    engine=result['returncode'] in RUN_ENGINE_STATUSES
    if not probe['valid']:
        if engine:code='ENGINE_COULD_NOT_RUN_THE_CONTAINER'
        elif result['returncode']==PROBE_ALARM_STATUS:code='PROBE_ENDED_BY_ITS_ALARM'
        elif not probe['one_json_line']:code='PROBE_OUTPUT_NOT_ONE_LINE'
        else:code='PROBE_LINE_NOT_AS_SPECIFIED'
        return PARTIAL_STATUS,PARTIAL_OUTCOME,code
    if result['returncode']!=0 and not engine:return PARTIAL_STATUS,PARTIAL_OUTCOME,'PROBE_EXIT_STATUS_NOT_ZERO'
    if probe['status']!='TLS_VERIFIED':return PARTIAL_STATUS,NOT_VERIFIED_OUTCOME,probe_code(probe)
    if engine:return PARTIAL_STATUS,VERIFIED_WITH_FINDINGS_OUTCOME,'ENGINE_STATUS_AFTER_A_VERIFIED_PROBE'
    if after['status']!='COMPLETE':return PARTIAL_STATUS,VERIFIED_WITH_FINDINGS_OUTCOME,'CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'
    if after['name_present']:return PARTIAL_STATUS,VERIFIED_WITH_FINDINGS_OUTCOME,'CONTAINER_OF_THE_PROBE_STILL_LISTED'
    if after['not_there_before']:return PARTIAL_STATUS,VERIFIED_WITH_FINDINGS_OUTCOME,'CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE'
    return COMPLETE_STATUS,COMPLETE_OUTCOME,None

REDUCTIONS=[]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    script=script_bytes();name=container_name(bound)                                     # pure
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate)
    precheck={'image':None,'retention_tag':None,'containers_before':None,'name_free':None}
    facts={'container':None,'probe':None,'containers_after':None}
    def finish(status,outcome,code,phase):
        probe,after=facts['probe'],facts['containers_after']
        verified=probe is not None and probe['valid'] and probe['status']=='TLS_VERIFIED'
        removed=None if after is None or after['status']!='COMPLETE' else (not after['name_present'] and after['not_there_before']==0)
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            precheck=precheck,container=facts['container'],probe=probe,containers_after=after,tls_verified=verified,container_removed=removed,
            writes=0,containers_run=commands.started['CONTAINER'],phase_reached=phase)))
    # ---- everything is looked at before the container is started: a refusal up to here has started nothing
    try:
        need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
        need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
        try:image=image_facts(commands,plan['image_id'])
        except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
        need(image['id']==plan['image_id'],'IMAGE_ID_MISMATCH')
        need(image['revision_label']==plan['image_revision'],'IMAGE_REVISION_MISMATCH')
        precheck['image']={'id_as_signed':True,'revision_as_signed':True}
        try:tagged=image_facts(commands,plan['retention_tag'])
        except CommandFailed:raise Refused('RETENTION_TAG_ABSENT_OR_UNREADABLE') from None
        need(tagged['id']==plan['image_id'] and tagged['reference_among_repo_tags'],'RETENTION_TAG_NOT_ON_THE_SIGNED_IMAGE')
        precheck['retention_tag']={'resolves_to_the_signed_image':True}
        try:before=container_list(commands)
        except CommandFailed:raise Refused('CONTAINER_LISTING_FAILED') from None
        precheck['containers_before']=len(before)
        precheck['name_free']=not any(row['name']==name for row in before)
        need(precheck['name_free'],'CONTAINER_NAME_TAKEN')
        # The last refusal that costs nothing: the whole class of the run and the reserve for the listing after it.
        need(gate()>=effects_budget(RUN_ROW),'BUDGET_INSUFFICIENT_BEFORE_THE_CONTAINER')
        code=None
    except Exception as error:
        code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
    if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,'PRECHECK')
    # ---- the one container
    container={'name':name,'state':'NOT_STARTED','returncode':None,'code':None,'seconds':None};facts['container']=container
    started=attempt(monotonic)
    result=container_run(commands,RUN_ROW,plan['image_id'],[],PROBE_COMMAND,script,container_name=name)
    ended=attempt(monotonic)
    container.update(code=result['code'],returncode=result['returncode'],
                     seconds=round(ended-started,3) if type(started) in (int,float) and type(ended) in (int,float) else None)
    if not result['started']:return finish(REFUSED_STATUS,REFUSED_OUTCOME,result['code'] or 'COMMAND_NOT_STARTED','CONTAINER_NOT_STARTED')
    container['state']='RETURNED' if result['returned'] else 'DID_NOT_RETURN'
    if result['returned']:facts['probe']=probe_line(result)
    # ---- after it: what the engine still lists, whatever the run said
    listing=attempt(lambda:container_list(commands))
    if type(listing) is list:
        known=set(row['id'] for row in before);new=[row for row in listing if row['id'] not in known]
        facts['containers_after']={'status':'COMPLETE','code':None,'before':len(before),'after':len(listing),'not_there_before':len(new),
                                   'name_present':any(row['name']==name for row in listing),
                                   'rows':[{'id':row['id'],'state':row['state'],'is_the_probe':row['name']==name} for row in new[:MAX_NEW_CONTAINER_ROWS]]}
    else:facts['containers_after']={'status':'UNAVAILABLE','code':listing.get('code'),'before':len(before),'after':None,'not_there_before':None,
                                    'name_present':None,'rows':[]}
    status,outcome,code=run_verdict(result,facts['probe'],facts['containers_after'])
    return finish(status,outcome,code,'CONTAINER')
# ==== END OP_TLS_PROBE ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
