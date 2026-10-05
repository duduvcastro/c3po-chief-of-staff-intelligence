"""OP_CAPACITY_PROBE: the capacity probe of epoch R2D2-V2-SHADOW-2026-10-05, one signed step per request.
A reading source of the frozen core: it creates and changes nothing on the filesystem of the host.

Each request names ONE step and the source starts attached containers of the signed image ID (the production backend
image by its local ID, carrying the release revision label) with the core's argv: removed on exit, never a pull, an
init process, uid 0, no network, a read-only root filesystem, no capability, no new privilege. The pinned script of
the step travels on standard input to python -I -B -.
CALENDAR (A5): one container with no bind runs calendar-pin.py, carried byte for byte (sha256 5a6066ae...), and the
printed line must name the epoch, the package and the document order this source pins.
IDENT (A5): the capacity tree is walked from "/" by its signed parent rows and held; the root and its four children
must be root-owned 0700 directories; two containers, one after the other, each with the tree bound read-only at
/c3po-capacity, print the AnchoredRoot identities of documents, payload and go (and config); both runs must agree and
equal the identities this source computes from the device and inode numbers it read on the host.
LOAD (B4c): the running worker c3po-r2d2-worker-1 must be on the signed image with exactly one mount at
/c3po-capacity, a read-only bind of the signed tree; the static config file is read on the host and must have the
signed hash; then one fresh container with the same read-only bind loads Settings and CapacityConfig with the signed
config path, config hash and release hash, and must print CAPACITY_STARTUP_OK with the roots documents, go and payload
and the veto mode DISPATCH_AND_DERIVATION_ONLY.
Before any container: the executor, the boot of the evidence, the image, the tree, the worker and the container list,
under which a refusal has started nothing. After: the container list again (and the worker, and the held tree), so
that the receipt says whether anything of the run is left. Nothing is removed, retried or repaired by this process.
The caller authenticates exact request/authority/GO/source bytes first; the source accepts only a window inside the
band of its step (A2 rev 3, section 6-A).
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

# ==== BEGIN OP_CAPACITY_PROBE (this operation only) ====
OPERATION='GO_READONLY_HOSTOPS02_CAPACITY_PROBE_01'
PHASE='READONLY_CAPACITY_PROBE'
REQUEST_SCHEMA='READONLY_HOSTOPS02_CAPACITY_PROBE_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_CAPACITY_PROBE_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_CAPACITY_PROBE_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_CAPACITY_PROBE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_CAPACITY_PROBE_PLAN_V1'
SOURCE_NAME='capacity_probe.py'
# The core's naming rule: the containers this source starts write to no host path (read-only binds only), so their
# rows are of kind CONTAINER and the source is READ (CORE.md section 8, rule 1). That class says nothing about the
# signature: A2 rev 3, section 6-A, keeps A5 and B4c under the owner's individual signature by hash.
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# Per source, not per step: no operation is required by name (the boot of the evidence binds the rows). The receipt of
# the mount (K6b, GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01) is a signed member of the LOAD plan instead (an open question).
EVIDENCE_OPERATIONS=()
# A2 rev 3 lines 66 and 113: a read has the window of its own line, at most 3600 s, on one UTC day.
MAX_GATE_SPAN_SECONDS=3600
STEPS=('CALENDAR','IDENT','LOAD')
# A2 rev 3, section 6-A: A5 (CALENDAR and IDENT) Sunday 04/10 16:26-23:30Z and Monday 05/10 to Thursday 08/10
# 20:38-23:30Z; B4c (LOAD) "the same band, after B4", and B4 has Monday to Thursday 20:38-23:30Z only.
A5_BANDS=(('2026-10-04','16:26:00','23:30:00'),('2026-10-05','20:38:00','23:30:00'),('2026-10-06','20:38:00','23:30:00'),
          ('2026-10-07','20:38:00','23:30:00'),('2026-10-08','20:38:00','23:30:00'))
B4C_BANDS=(('2026-10-05','20:38:00','23:30:00'),('2026-10-06','20:38:00','23:30:00'),('2026-10-07','20:38:00','23:30:00'),
           ('2026-10-08','20:38:00','23:30:00'))
STEP_BANDS={'CALENDAR':A5_BANDS,'IDENT':A5_BANDS,'LOAD':B4C_BANDS}
BAND_SOURCE='A2 rev 3 (A2_AUTORIDADE_CINCO_SESSOES.md), section 6-A, rows A5 and B4c (B4c: the band of B4)'
CALENDAR_OUTCOME='CALENDAR_LINE_READ_IN_THE_IMAGE_AS_PINNED'
IDENT_OUTCOME='ROOT_IDENTITIES_READ_TWICE_EQUAL_TO_THE_HOST'
COMPLETE_OUTCOME='STATIC_CONFIG_LOADED_WITH_THE_WORKER_BIND'
NOT_AS_EXPECTED_OUTCOME='STEP_RAN_ANSWER_NOT_AS_EXPECTED'
WITH_FINDINGS_OUTCOME='STEP_RAN_EXPECTED_ANSWER_WITH_FINDINGS'
PARTIAL_OUTCOME='PARTIAL_STEP_RESULT_UNKNOWN'
REFUSED_OUTCOME='REFUSED_NO_CONTAINER_STARTED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STEP_NOT_COMPLETE'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_CONTAINER_MAY_REMAIN'
STEP_OUTCOMES={'CALENDAR':CALENDAR_OUTCOME,'IDENT':IDENT_OUTCOME,'LOAD':COMPLETE_OUTCOME}
PLAN_KEYS=frozenset(('step','image_id','image_revision','capacity','load','evidence_boot_id_sha256'))
# The release whose image is deployed for the epoch (main at dd4ec4bb), and what its code says of the epoch: EPOCH and
# DOCUMENT_ORDER_SHA of c3po/backend/app/r2d2_v2_epoch_assembler.py lines 9 and 12, and implementation_package_sha()
# computed from that tree (tests/test_static_pins.py reads all three from a tree of the release).
RELEASE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'
PACKAGE_SHA='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
DOCUMENT_ORDER='1a5253bf23f5006224b79527da06697646c34c6f5a3a4f820af5da2b13d7a118'
# The tree: bound at a top-level target, read-only (capacity-mount README, "What it is"); four private children.
CAPACITY_TARGET='/c3po-capacity'
CAPACITY_TARGET_NAME='c3po-capacity'
CAPACITY_CHILDREN=('config','documents','go','payload')
CAPACITY_ROOTS=('documents','go','payload')
PRIVATE_DIRECTORY=(0,0,0o700)
CAPACITY_ROOT_NAME='[a-z0-9][a-z0-9._-]{0,62}'
CONFIG_FILE=CAPACITY_TARGET+'/config/[A-Za-z0-9][A-Za-z0-9._-]{0,99}'
CONFIG_LIMIT=4*1024*1024                  # AnchoredRoot.read's limit
WORKER_NAME='c3po-r2d2-worker-1'
VETO_MODE='DISPATCH_AND_DERIVATION_ONLY'
MOUNT_OPERATION='GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01'
MAX_MOUNT_ROWS=32
MAX_ROOT_ENTRIES=64
# The worker's settings as the host .env gives them to it (env_file of the backend services; K6b writes the capacity
# block, K6a the release pin): read as booleans only, by the core's container_environment template.
ENV_RELEASE_SHA='C3PO_R2D2_V2_SHADOW_RELEASE_SHA'
ENV_MOUNT_SOURCE='C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE'
ENV_CONFIG_FILE='C3PO_R2D2_V2_CAPACITY_CONFIG_FILE'
ENV_CONFIG_SHA='C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'
ENV_VETO_MODE='C3PO_R2D2_V2_CAPACITY_VETO_MODE'
ENV_REQUIRED='C3PO_R2D2_V2_CAPACITY_REQUIRED'
ENV_SETTINGS=(ENV_CONFIG_FILE,ENV_CONFIG_SHA,ENV_VETO_MODE,ENV_REQUIRED)   # each absent, or equal to the signed value
REQUIRED_TRUE='true'
STARTED_AT='([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:[.]([0-9]{1,9}))?Z'
MAX_NEW_CONTAINER_ROWS=8
CONTAINER_PREFIX='hostops02-probe-'
RUN_COMMAND=['python','-I','-B','-']
ALARM_STATUS=142                          # 128 + SIGALRM, as docker-init reports a child its alarm ended
SCRIPT_SECONDS={'IDENT':14,'LOAD':34}     # the alarm each own script arms first; CALENDAR carries none (verbatim bytes)
CLASS_NAME='[A-Z][A-Za-z0-9_]{0,79}'      # what a script prints for an exception: a constant code or a class name
# docker container inspect of the worker: its mounts as one JSON object, four members per mount, nothing else (no
# environment, no label). Only constructs the post-deploy family ran on this host: a variable declared before a range
# and assigned inside it, if, not, json.
MOUNTS_FORMAT=('{{ $first := true }}{"mounts":[{{ range .Mounts }}{{ if not $first }},{{ end }}{{ $first = false }}'
               '{"type":{{json .Type}},"source":{{json .Source}},"destination":{{json .Destination}},"rw":{{json .RW}}}{{ end }}]}')
# calendar-pin.py, byte for byte: the lines between the markers calendar-pin-script:begin and :end of
# c3po/deployment/capacity-day/README.documents.md (opsart), inside the python fence, each ended by a newline.
CALENDAR_SCRIPT=r'''import json, sys
APPLICATION_ROOT = '/app'
sys.path.insert(0, APPLICATION_ROOT)
try:
    from app.r2d2_v2_calendar import ShadowCalendar
    from app.r2d2_v2_capacity_authority import calendar_pin
    from app.r2d2_v2_earnings_package import implementation_package_sha
    from app.r2d2_v2_epoch_assembler import DOCUMENT_ORDER_SHA, EPOCH, SESSIONS
    calendar = ShadowCalendar()
    receipt = {'status': 'CALENDAR_PIN', 'epoch': EPOCH, 'calendar_version': calendar.version,
               'calendar_pin_sha': calendar_pin(calendar, {'authorized_sessions': list(SESSIONS)}),
               'package_sha': implementation_package_sha(), 'document_order_sha': DOCUMENT_ORDER_SHA}
except Exception as error:
    print(json.dumps({'status': 'CALENDAR_PIN_REFUSED', 'code': type(error).__name__}, sort_keys=True))
    raise SystemExit(1)
print(json.dumps(receipt, sort_keys=True))
'''
CALENDAR_SCRIPT_SHA256='5a6066ae2925453a0def335d8f8ac7e802e149b56cf9e61ea3fe8843fe582b5f'
CALENDAR_SCRIPT_BYTES=876
IDENT_SCRIPT=r'''import signal
signal.alarm(14)
import json, re, sys
# HOSTOPS02 capacity probe, step IDENT. The identities of the capacity roots as the release computes them
# (AnchoredRoot: every component from '/' opened without following a link, the leaf a directory of this uid closed to
# group and other), read under the read-only bind at /c3po-capacity. One JSON line; nothing is written.
APPLICATION_ROOT = '/app'
TARGET = '/c3po-capacity'
NAMES = ('config', 'documents', 'go', 'payload')
CODE = re.compile('[A-Z][A-Z0-9_]{0,79}')
sys.path.insert(0, APPLICATION_ROOT)


def finish(line, status):
    sys.stdout.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
    sys.stdout.flush()
    raise SystemExit(status)


def code_of(error):
    text = str(error)
    if type(error).__name__ == 'ShadowIntegrityError' and CODE.fullmatch(text):
        return text
    return type(error).__name__


try:
    from app.r2d2_v2_capacity_anchored import AnchoredRoot
    identities = {}
    for name in NAMES:
        root = AnchoredRoot(TARGET + '/' + name)
        try:
            identities[name] = root.identity
        finally:
            root.close()
except Exception as error:
    finish({'status': 'ROOT_IDENTITIES_REFUSED', 'code': code_of(error)}, 1)
finish({'status': 'ROOT_IDENTITIES', 'identities': identities}, 0)
'''
IDENT_SCRIPT_SHA256='0b8b12216903b698b29a970f9e257e6e5f16e417102a637fda539dfde10545d1'
IDENT_SCRIPT_BYTES=1330
LOAD_SCRIPT=r'''import signal
signal.alarm(34)
import hashlib, json, re, sys
# HOSTOPS02 capacity probe, step LOAD: the startup checks of the worker (capacity-mount README, step 2) in a fresh
# container with the worker's read-only bind. Settings and CapacityConfig of the release, the signed values passed as
# arguments (the last line of standard input, after this text); the config is opened read-only and nothing is written.
APPLICATION_ROOT = '/app'
VETO_MODE = 'DISPATCH_AND_DERIVATION_ONLY'
CODE = re.compile('[A-Z][A-Z0-9_]{0,79}')
sys.path.insert(0, APPLICATION_ROOT)


def finish(line, status):
    sys.stdout.write(json.dumps(line, sort_keys=True, separators=(',', ':')) + '\n')
    sys.stdout.flush()
    raise SystemExit(status)


def code_of(error):
    text = str(error)
    if type(error).__name__ == 'ShadowIntegrityError' and CODE.fullmatch(text):
        return text
    return type(error).__name__


def run(values):
    try:
        from app.config import Settings
        from app.r2d2_v2_capacity_bootstrap import CapacityConfig
        settings = Settings(r2d2_v2_capacity_required=True,
                            r2d2_v2_capacity_config_file=values['config_file'],
                            r2d2_v2_capacity_config_sha=values['config_sha256'],
                            r2d2_v2_capacity_veto_mode=VETO_MODE,
                            r2d2_v2_shadow_release_sha=values['release_sha'])
        config = CapacityConfig(settings)
    except Exception as error:
        finish({'status': 'CAPACITY_STARTUP_REFUSED', 'code': code_of(error)}, 1)
    try:
        line = {'status': 'CAPACITY_STARTUP_OK', 'roots': sorted(config.roots), 'veto_mode': config.veto_mode,
                'identities': {name: config.roots[name].identity for name in sorted(config.roots)},
                'config_sha256': hashlib.sha256(config.config_root.read(config.name)).hexdigest()}
    except Exception as error:
        config.close()
        finish({'status': 'CAPACITY_STARTUP_REFUSED', 'code': code_of(error)}, 1)
    config.close()
    finish(line, 0)
'''
LOAD_SCRIPT_SHA256='c3019efaf1d51fea5188af9860f093faba4eb830f19220e222bc80b8aeaba99c'
LOAD_SCRIPT_BYTES=2050
LOAD_CALL="run(json.loads('%s'))\n"         # the one line appended to the pinned LOAD script: the signed values as JSON
# The lines the scripts print, member by member. A line is copied into the receipt only when it meets its grammar.
CALENDAR_KEYS=frozenset(('status','epoch','calendar_version','calendar_pin_sha','package_sha','document_order_sha'))
CALENDAR_VERSION='[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}'
EPOCH_TEXT='[A-Z0-9][A-Z0-9_-]{0,79}'
LOAD_KEYS=frozenset(('status','roots','veto_mode','identities','config_sha256'))
LOAD_ROOT_NAMES=('documents','go','payload','restore_revocation')
VETO_MODES=('CONTINUOUS','DISPATCH_AND_DERIVATION_ONLY')
REFUSED_LINE_STATUS={'CALENDAR':'CALENDAR_PIN_REFUSED','IDENT':'ROOT_IDENTITIES_REFUSED','LOAD':'CAPACITY_STARTUP_REFUSED'}
OK_LINE_STATUS={'CALENDAR':'CALENDAR_PIN','IDENT':'ROOT_IDENTITIES','LOAD':'CAPACITY_STARTUP_OK'}
REFUSED_CODES={'CALENDAR':'CALENDAR_PIN_REFUSED_IN_THE_IMAGE','IDENT':'ROOT_IDENTITIES_REFUSED_IN_THE_IMAGE','LOAD':'CAPACITY_STARTUP_REFUSED_IN_THE_IMAGE'}
# The rows: the core's reads, one more read of the worker's mounts, and one attached run per step (IDENT twice). IDENT
# runs in the short class so that both of its runs fit the payload's 60 s: 2 x 20 + 4 = 44 s must be left before the
# first; CALENDAR and LOAD import the application and take the long class (40 + 4 = 44 s).
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the name c3po-r2d2-worker-1 (LOAD only)','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template of the six signed names, then the ID of the worker read by the precheck (LOAD only)','QUICK','READ'),
          'worker_mounts':command_row('docker',['container','inspect','--format',MOUNTS_FORMAT],'the ID of the worker read by the precheck (LOAD only)','QUICK','READ'),
          'calendar':command_row('docker',RUN_PREFIX,'--name hostops02-probe-calendar-<16 hex of the GO>, the signed image ID, python -I -B -; '
                                 'calendar-pin.py on standard input; no bind','RUN','CONTAINER',stdin=True),
          'ident':command_row('docker',RUN_PREFIX,'--name hostops02-probe-ident-<16 hex of the GO>-<1 or 2>, the read-only bind of the signed '
                              'capacity root at /c3po-capacity, the signed image ID, python -I -B -; the pinned IDENT script on standard input',
                              'RUN_SHORT','CONTAINER',stdin=True),
          'load':command_row('docker',RUN_PREFIX,'--name hostops02-probe-load-<16 hex of the GO>, the read-only bind of the signed capacity '
                             'root at /c3po-capacity, the signed image ID, python -I -B -; the pinned LOAD script and one line of the signed '
                             'values on standard input','RUN','CONTAINER',stdin=True)}
STEP_ROWS={'CALENDAR':('calendar',),'IDENT':('ident','ident'),'LOAD':('load',)}
SIGNATURE_REGIME=('individual, by the hash of its own request (A2 rev 3, section 6-A: A5 and B4c are IND); a container run, never '
                  'a read of any grid')
SCOPE_STATEMENT=('The capacity probe of epoch R2D2-V2-SHADOW-2026-10-05, one signed step per request (A2 rev 3, section 6-A). CALENDAR '
                 '(A5): one attached container of the signed image ID with no bind runs calendar-pin.py (sha256 5a6066ae...) and its '
                 'line must name the epoch, the package and the document order pinned here. IDENT (A5): the capacity tree is walked '
                 'from / by its signed parent rows and held; two containers, one after the other, each with the tree bound read-only '
                 'at /c3po-capacity, print the AnchoredRoot identities, which must agree and equal those computed from the device and '
                 'inode numbers read on the host. LOAD (B4c): the running worker c3po-r2d2-worker-1 is on the signed image with one '
                 'read-only bind of the signed tree at /c3po-capacity, the static config on the host has the signed hash, and one '
                 'fresh container with the same bind loads Settings and CapacityConfig with the signed config path, config hash and '
                 'release hash and must print CAPACITY_STARTUP_OK, the roots documents, go and payload and the veto mode '
                 'DISPATCH_AND_DERIVATION_ONLY. Every container: removed on exit, never a pull, an init process, uid 0, no network, '
                 'read-only root filesystem, no capability, no new privilege, no environment file, no DOCKER_CONFIG. Nothing on the '
                 'filesystem of the host is created, changed or removed; no unit is touched; no container is removed by this '
                 'process; a timeout stops the docker CLI, not the container. Its signature is individual by the hash of its request.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'steps':{'CALENDAR':{'rows':list(STEP_ROWS['CALENDAR']),'success':CALENDAR_OUTCOME,'bands':[list(band) for band in A5_BANDS]},
                'IDENT':{'rows':list(STEP_ROWS['IDENT']),'success':IDENT_OUTCOME,'bands':[list(band) for band in A5_BANDS]},
                'LOAD':{'rows':list(STEP_ROWS['LOAD']),'success':COMPLETE_OUTCOME,'bands':[list(band) for band in B4C_BANDS]},
                'band_source':BAND_SOURCE},
       'release':{'revision':RELEASE_REVISION,'epoch':EPOCH_NAME,'package_sha':PACKAGE_SHA,'document_order_sha':DOCUMENT_ORDER},
       'scripts':{'CALENDAR':{'sha256':CALENDAR_SCRIPT_SHA256,'bytes':CALENDAR_SCRIPT_BYTES,'carried_byte_for_byte':True,'alarm_seconds':None},
                  'IDENT':{'sha256':IDENT_SCRIPT_SHA256,'bytes':IDENT_SCRIPT_BYTES,'alarm_seconds':SCRIPT_SECONDS['IDENT']},
                  'LOAD':{'sha256':LOAD_SCRIPT_SHA256,'bytes':LOAD_SCRIPT_BYTES,'alarm_seconds':SCRIPT_SECONDS['LOAD'],
                          'appended_line':LOAD_CALL.strip()},
                  'command':RUN_COMMAND,'alarm_exit_status':ALARM_STATUS},
       'capacity':{'target':CAPACITY_TARGET,'children':list(CAPACITY_CHILDREN),'roots':list(CAPACITY_ROOTS),
                   'children_owner_mode':'root:root 0700','config_file':CONFIG_FILE,'config_limit_bytes':CONFIG_LIMIT},
       'worker':{'name':WORKER_NAME,'mounts_format':MOUNTS_FORMAT,'veto_mode':VETO_MODE,'mount_operation':MOUNT_OPERATION},
       'container':{'prefix':RUN_PREFIX,'names':CONTAINER_PREFIX+'<step>-<first 16 hex of the GO sha256>[-1|-2]','command':RUN_COMMAND,
                    'network':'none','environment_file':None,'docker_config':None},
       'signature':SIGNATURE_REGIME,
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the static config file of a LOAD plan, by descriptor under the held tree (hashed in memory)'],
       'side_effects':['one attached docker run --rm per container (CALENDAR and LOAD one, IDENT two, one after the other): the engine '
                       'creates the container under the name of the step and the GO and removes it when its process ends',
                       'IDENT and LOAD bind the signed capacity root read-only at /c3po-capacity: the container reads the tree; '
                       'nothing in it is written by this process or by the scripts',
                       'the IDENT and LOAD scripts arm an alarm as their first statement (14 s and 34 s) so that their process ends '
                       'before the class limit of the docker CLI; calendar-pin.py is carried byte for byte and arms none',
                       'the docker CLI runs with the fixed environment of the core and no DOCKER_CONFIG'],
       'never':['a writable bind, or a bind of anything but the signed capacity root','a network','docker exec','a shell','systemctl',
                'a pull','an image by tag','--privileged, a device or a capability','the removal of any container',
                'any write on the filesystem of the host','a value of an environment','an environment file'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'mount_rows':MAX_MOUNT_ROWS,'new_container_rows':MAX_NEW_CONTAINER_ROWS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner):
    """Everything this source can do to the host: the read primitives and the signed commands."""


def pinned(script,digest,size):
    """The bytes of one pinned script, from the constant this source carries, compared with its pins."""
    raw=script.encode('ascii')
    need(len(raw)==size and sha(raw)==digest,'SCRIPT_NOT_THE_PINNED_HASH');return raw

def scripts():
    """The three pinned scripts, each checked."""
    return {'CALENDAR':pinned(CALENDAR_SCRIPT,CALENDAR_SCRIPT_SHA256,CALENDAR_SCRIPT_BYTES),
            'IDENT':pinned(IDENT_SCRIPT,IDENT_SCRIPT_SHA256,IDENT_SCRIPT_BYTES),
            'LOAD':pinned(LOAD_SCRIPT,LOAD_SCRIPT_SHA256,LOAD_SCRIPT_BYTES)}

def load_values(plan):
    load=plan['load'];return {'config_file':load['config_file'],'config_sha256':load['config_sha256'],'release_sha':load['release_sha']}

def stdin_of(plan):
    """What the container of the step gets on standard input: the pinned script; for LOAD one more line that passes
    the signed values as a JSON literal (paths and hashes of a fixed grammar: no quote, no backslash)."""
    raw=scripts()[plan['step']]
    if plan['step']!='LOAD':return raw
    literal=canonical(load_values(plan)).decode('ascii')
    need("'" not in literal and '\\' not in literal,'LOAD_VALUES_INVALID')
    return raw+(LOAD_CALL%literal).encode('ascii')

def container_names(plan,go16):
    """One name per container of the step: the prefix, the step, the first 16 hex of the GO (IDENT adds -1 and -2)."""
    base=CONTAINER_PREFIX+plan['step'].lower()+'-'+go16
    return [base+'-1',base+'-2'] if plan['step']=='IDENT' else [base]

def mounts_of(plan):
    """The one read-only bind of IDENT and LOAD: the signed capacity root at /c3po-capacity; none for CALENDAR."""
    if plan['step']=='CALENDAR':return []
    return [{'source':plan['capacity']['root_path'],'target':CAPACITY_TARGET,'read_only':True}]

def validate_window(window,step):
    """The signed window lies in one band of the step: its day, between its two instants (UTC)."""
    start,end=instant(window['not_before']),instant(window['expires_at'])
    bands={day:(begin,stop) for day,begin,stop in STEP_BANDS[step]};day=start.date().isoformat()
    need(day in bands,'STEP_DAY_NOT_IN_SCOPE')
    need(instant(day+'T'+bands[day][0]+'+00:00')<=start and end<=instant(day+'T'+bands[day][1]+'+00:00'),'STEP_WINDOW_OUTSIDE_THE_BAND')

def validate_capacity(capacity):
    need(type(capacity) is dict and set(capacity)=={'root_path','parent_rows'},'CAPACITY_UNBOUND')
    path=capacity['root_path']
    need(text(path,MOUNT_PATH) and clean_path(path) and len(prefixes(path))>=3
         and text(PurePosixPath(path).name,CAPACITY_ROOT_NAME),'CAPACITY_ROOT_INVALID')
    validate_chain(capacity['parent_rows'],str(PurePosixPath(path).parent))

def validate_load(load):
    need(type(load) is dict and set(load)=={'config_file','config_sha256','release_sha','mount_receipt_sha256'},'LOAD_UNBOUND')
    need(text(load['config_file'],CONFIG_FILE),'CONFIG_FILE_INVALID')                 # one name, no '/': clean by its grammar
    need(hexpin(load['config_sha256']),'CONFIG_SHA_INVALID')
    need(hexpin(load['release_sha']),'RELEASE_SHA_INVALID')
    need(hexpin(load['mount_receipt_sha256']),'MOUNT_RECEIPT_UNBOUND')
    need(len({load['config_sha256'],load['release_sha'],load['mount_receipt_sha256']})==3,'LOAD_HASH_REUSED')

def validate_members(plan):
    """Every member of the plan but the step and the window: refused from the bytes, before any claim."""
    step=plan['step']
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(type(plan['image_revision']) is str and plan['image_revision']==RELEASE_REVISION,'IMAGE_REVISION_NOT_THE_RELEASE')
    if step=='CALENDAR':need(plan['capacity'] is None,'CAPACITY_NOT_OF_THE_STEP')
    else:validate_capacity(plan['capacity'])
    if step=='LOAD':validate_load(plan['load'])
    else:need(plan['load'] is None,'LOAD_NOT_OF_THE_STEP')
    for row,name in zip(STEP_ROWS[step],container_names(plan,'0'*16)):
        run_arguments(row,plan['image_id'],mounts_of(plan),RUN_COMMAND,name)
    stdin_of(plan)                       # checks the three pinned scripts, and the LOAD values

def validate_plan(plan):
    need(type(plan['step']) is str and plan['step'] in STEPS,'STEP_INVALID')
    validate_window(plan['window'],plan['step'])
    validate_members(plan)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    step=plan['step'];raw=stdin_of(plan);capacity=plan['capacity'];load=plan['load']
    containers=[]
    for row,name in zip(STEP_ROWS[step],container_names(plan,'<first 16 hex of the GO sha256>')):
        containers.append({'name':name,'docker_arguments':COMMANDS[row]['argv']+['--name',name]+run_arguments(row,plan['image_id'],mounts_of(plan),RUN_COMMAND),
                           'binds':mounts_of(plan),'network':'none','environment_file':None,'docker_config_variable':None,
                           'standard_input':{'sha256':sha(raw),'bytes':len(raw),'pinned_script_sha256':sha(scripts()[step])},
                           'time_limit_seconds':COMMAND_CLASSES[COMMANDS[row]['class']]['seconds'],'alarm_seconds':SCRIPT_SECONDS.get(step),
                           'removed_by_the_engine':True})
    out={'operation':OPERATION,'step':step,'success_outcome':success_of(plan),
         'bands':[list(band) for band in STEP_BANDS[step]],'band_source':BAND_SOURCE,
         'image':{'id':plan['image_id'],'revision':plan['image_revision'],'by_id_never_a_tag':True},
         'containers':containers,'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
         'signature':SIGNATURE_REGIME,'writes':0,'removes':[],'activation':False,'containers_run':len(containers)}
    out['capacity']=None if capacity is None else {'root_path':capacity['root_path'],'parents':chain_effects(capacity['parent_rows']),
                                                   'children':list(CAPACITY_CHILDREN),'children_owner_mode':'root:root 0700','target':CAPACITY_TARGET}
    out['load']=None if load is None else {'config_file':load['config_file'],'config_sha256':load['config_sha256'],'release_sha':load['release_sha'],
                                           'mount_receipt':{'operation':MOUNT_OPERATION,'receipt_sha256':load['mount_receipt_sha256']},
                                           'veto_mode':VETO_MODE,'worker':WORKER_NAME,
                                           'expected':{'status':'CAPACITY_STARTUP_OK','roots':list(CAPACITY_ROOTS),'veto_mode':VETO_MODE}}
    if step=='CALENDAR':out['expected_line']={'status':'CALENDAR_PIN','epoch':EPOCH_NAME,'package_sha':PACKAGE_SHA,'document_order_sha':DOCUMENT_ORDER}
    return out
def success_of(plan):return STEP_OUTCOMES[plan['step']]


# ---------------------------------------------------------------- the tree, held from "/"
def held_child(host,parent,name,gate,missing,not_directory):
    """A directory by name in a held parent, never through a link: lstat, open without following, fstat equal."""
    gate()
    try:named=host.lstat(name,parent.fd)
    except FileNotFoundError:raise Refused(missing) from None
    need(stat.S_ISDIR(named.st_mode),not_directory)
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
    try:
        info=host.fstat(fd)
        need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'CAPACITY_CHANGED_DURING_WALK')
        return Pinned(host,fd,parent=parent,name=name),info
    except BaseException:
        host.close(fd);raise

def private(info):return (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==PRIVATE_DIRECTORY

def root_identity(root,name,child):
    """AnchoredRoot's identity of /c3po-capacity/<name>, as the release computes it (r2d2_v2_store.digest of the list of
    [part, device, inode] of each component below '/'), from the numbers read on the host."""
    return sha(canonical([[CAPACITY_TARGET_NAME,root.st_dev,root.st_ino],[name,child.st_dev,child.st_ino]]))

def hold_tree(host,plan,gate,held):
    """The parents by their signed rows, the root and its four children; each held. Returns the report and the identities."""
    capacity=plan['capacity'];path=capacity['root_path']
    fd=walk_pinned(host,capacity['parent_rows'],gate,[])
    try:parents=Pinned(host,fd,rows=capacity['parent_rows'])
    except BaseException:
        host.close(fd);raise
    held.append(parents)
    root,info=held_child(host,parents,PurePosixPath(path).name,gate,'CAPACITY_ROOT_ABSENT','CAPACITY_ROOT_NOT_A_DIRECTORY');held.append(root)
    need(private(info),'CAPACITY_ROOT_NOT_PRIVATE')
    names=[]
    for name in host.names(root.fd):
        names.append(name);need(len(names)<=MAX_ROOT_ENTRIES,'CAPACITY_ROOT_ENTRY_LIMIT')
    others=sorted(name for name in names if name not in CAPACITY_CHILDREN)
    for name in others:                        # nothing but directories directly in the bound root (a socket or a file is never bound unseen)
        gate();need(stat.S_ISDIR(host.lstat(name,root.fd).st_mode),'CAPACITY_ROOT_ENTRY_NOT_A_DIRECTORY')
    children={};identities={}
    for name in CAPACITY_CHILDREN:
        child,found=held_child(host,root,name,gate,'CAPACITY_CHILD_ABSENT','CAPACITY_CHILD_NOT_A_DIRECTORY');held.append(child)
        need(private(found),'CAPACITY_CHILD_NOT_PRIVATE')
        children[name]={'device':found.st_dev,'inode':found.st_ino,'same_device_as_root':found.st_dev==info.st_dev}
        identities[name]=root_identity(info,name,found)
    report={'parents_as_signed':True,'root':{'device':info.st_dev,'inode':info.st_ino,'private':True,'other_directories':len(others),'ctime_ns':info.st_ctime_ns},
            'children':children,'identities':identities}
    return report,identities,{name:held[-len(CAPACITY_CHILDREN)+index] for index,name in enumerate(CAPACITY_CHILDREN)}

def config_file_facts(host,plan,config,gate):
    """The static config as the worker would read it, on the host: by name in the held config directory, regular, owned
    by root, one link, closed to group and other (AnchoredRoot.read's policy), its SHA-256 equal to the signed one."""
    name=PurePosixPath(plan['load']['config_file']).name
    try:raw,info=read_regular(host,name,config.fd,gate,CONFIG_LIMIT)
    except FileNotFoundError:raise Refused('CONFIG_FILE_ABSENT') from None
    except OSError:raise Refused('CONFIG_FILE_UNREADABLE') from None
    need(info.st_uid==0 and info.st_nlink==1 and not stat.S_IMODE(info.st_mode)&0o077,'CONFIG_FILE_NOT_PRIVATE')
    need(sha(raw)==plan['load']['config_sha256'],'CONFIG_FILE_HASH_MISMATCH')
    return {'regular':True,'private':True,'sha256_as_signed':True,'bytes':len(raw)}

def worker_mounts(commands,worker_id):
    """The mounts of the worker: type, source, destination and RW of each, nothing else."""
    try:row=decode(commands.output('worker_mounts',worker_id))
    except CommandFailed:raise Refused('WORKER_MOUNTS_UNREADABLE') from None
    need(set(row)=={'mounts'} and type(row['mounts']) is list and len(row['mounts'])<=MAX_MOUNT_ROWS,'WORKER_MOUNTS_INVALID')
    for item in row['mounts']:
        need(type(item) is dict and set(item)=={'type','source','destination','rw'} and type(item['type']) is str and type(item['source']) is str
             and type(item['destination']) is str and type(item['rw']) is bool,'WORKER_MOUNTS_INVALID')
    return row['mounts']

def worker_facts(commands,plan):
    """The running worker: on the signed image, exactly one mount at /c3po-capacity, a read-only bind of the signed root."""
    try:worker=container_facts(commands,WORKER_NAME,expected_name=WORKER_NAME)
    except CommandFailed:raise Refused('WORKER_ABSENT_OR_UNREADABLE') from None
    need(worker['running'] is True and worker['state']=='running','WORKER_NOT_RUNNING')
    need(worker['image_id']==plan['image_id'],'WORKER_NOT_ON_THE_SIGNED_IMAGE')
    mounts=worker_mounts(commands,worker['id'])
    at=[item for item in mounts if item['destination']==CAPACITY_TARGET]
    need(at,'WORKER_CAPACITY_MOUNT_ABSENT');need(len(at)==1,'WORKER_CAPACITY_MOUNT_NOT_ONE')
    need(at[0]['type']=='bind','WORKER_CAPACITY_MOUNT_NOT_A_BIND')
    need(at[0]['source']==plan['capacity']['root_path'],'WORKER_CAPACITY_MOUNT_OTHER_SOURCE')
    need(at[0]['rw'] is False,'WORKER_CAPACITY_MOUNT_WRITABLE')
    root=plan['capacity']['root_path']
    for item in mounts:
        if item is at[0]:continue
        need(not inside(item['destination'],CAPACITY_TARGET),'WORKER_MOUNT_INSIDE_THE_CAPACITY_TARGET')
        need(not (item['source'].startswith('/') and (inside(item['source'],root) or inside(root,item['source']))),'WORKER_OTHER_MOUNT_REACHES_THE_TREE')
    settings=worker_settings(commands,plan,worker['id'])
    return worker,{'id':worker['id'],'started_at':worker['started_at'],'restarts':worker['restarts'],'running':True,'image_as_signed':True,
                   'mounts':len(mounts),'capacity_mount':{'type':'bind','source_as_signed':True,'read_only':True},'other_mounts_clear_of_the_tree':True,
                   'settings':settings}

def worker_settings(commands,plan,worker_id):
    """The worker's environment against the signed values, as booleans: the release pin present and equal, the mount
    source present and equal to the signed root, each capacity setting absent or equal (REQUIRED true, the veto mode)."""
    load=plan['load']
    expected={ENV_RELEASE_SHA:load['release_sha'],ENV_MOUNT_SOURCE:plan['capacity']['root_path'],ENV_CONFIG_FILE:load['config_file'],
              ENV_CONFIG_SHA:load['config_sha256'],ENV_VETO_MODE:VETO_MODE,ENV_REQUIRED:REQUIRED_TRUE}
    try:found=container_environment(commands,worker_id,expected)
    except CommandFailed:raise Refused('WORKER_ENVIRONMENT_UNREADABLE') from None
    need(found[ENV_RELEASE_SHA]['present'] and found[ENV_RELEASE_SHA]['equal'],'WORKER_RELEASE_SHA_NOT_AS_SIGNED')
    need(found[ENV_MOUNT_SOURCE]['present'] and found[ENV_MOUNT_SOURCE]['equal'],'WORKER_MOUNT_SOURCE_NOT_AS_SIGNED')
    for name in ENV_SETTINGS:need(found[name]['equal'] or not found[name]['present'],'WORKER_CAPACITY_SETTING_NOT_AS_SIGNED')
    return found

def started_ns(value):
    """The engine's StartedAt (RFC 3339, UTC, up to nanoseconds) as nanoseconds since the epoch; None for any other text."""
    match=re.fullmatch(STARTED_AT,value) if type(value) is str else None
    if match is None:return None
    try:moment=datetime(*[int(item) for item in match.groups()[:6]],tzinfo=timezone.utc)
    except ValueError:return None
    return int(moment.timestamp())*10**9+int((match.group(7) or '').ljust(9,'0'))

def changed_after(ctime_ns,started):
    """Reported, never judged: whether the root of the tree changed (status change time) after the worker started."""
    begun=started_ns(started)
    return None if begun is None or type(ctime_ns) is not int else ctime_ns>begun


# ---------------------------------------------------------------- the lines the scripts print
def line_grammar(step,row):
    """True when the printed object is exactly what the step's script prints. Pure; never raises for a dict."""
    if row.get('status')==REFUSED_LINE_STATUS[step]:
        return set(row)=={'status','code'} and text(row['code'],CLASS_NAME)
    if row.get('status')!=OK_LINE_STATUS[step]:return False
    if step=='CALENDAR':
        return (set(row)==CALENDAR_KEYS and text(row['epoch'],EPOCH_TEXT) and text(row['calendar_version'],CALENDAR_VERSION)
                and hexpin(row['calendar_pin_sha']) and hexpin(row['package_sha']) and hexpin(row['document_order_sha']))
    if step=='IDENT':
        identities=row.get('identities')
        return (set(row)=={'status','identities'} and type(identities) is dict and set(identities)==set(CAPACITY_CHILDREN)
                and all(hexpin(value) for value in identities.values()))
    roots,identities=row.get('roots'),row.get('identities')
    return (set(row)==LOAD_KEYS and type(roots) is list and all(type(name) is str and name in LOAD_ROOT_NAMES for name in roots)
            and roots==sorted(set(roots)) and type(row['veto_mode']) is str and row['veto_mode'] in VETO_MODES
            and type(identities) is dict and set(identities)==set(roots) and all(hexpin(value) for value in identities.values())
            and hexpin(row['config_sha256']))

def line_of(step,result):
    """What a container printed, reduced to what may leave this process: a line that meets the grammar is copied (codes,
    hashes, a version name, booleans); of any other output nothing but two booleans (some output, one JSON line)."""
    output=result['output'] if type(result.get('output')) is bytes else b''
    out={'returncode':result['returncode'],'output_present':len(output)>0,'one_json_line':False,'valid':False,'line':None}
    try:row=single_line(output)
    except Refused:return out
    out['one_json_line']=True
    if not line_grammar(step,row):return out
    out.update(valid=True,line=dict(row,identities=dict(row['identities'])) if 'identities' in row else dict(row))
    return out

def answer_code(step,result,line):
    """None when the run returned one valid line with the exit status that line implies; else the constant code."""
    if not result['returned']:return result['code'] or 'COMMAND_FAILED'
    if not line['valid']:
        if result['returncode'] in RUN_ENGINE_STATUSES:return 'ENGINE_COULD_NOT_RUN_THE_CONTAINER'
        if result['returncode']==ALARM_STATUS:return 'SCRIPT_ENDED_BY_ITS_ALARM'
        if not line['one_json_line']:return 'OUTPUT_NOT_ONE_LINE'
        return 'LINE_NOT_AS_SPECIFIED'
    expected=0 if line['line']['status']==OK_LINE_STATUS[step] else 1
    if result['returncode']!=expected:return 'EXIT_STATUS_NOT_AS_THE_LINE'
    return None

def expectation_code(step,lines,host_identities,plan_config_sha=None):
    """None when the valid line(s) say what the step must find; else the constant code of the first difference."""
    first=lines[0]['line']
    if any(line['line']['status']==REFUSED_LINE_STATUS[step] for line in lines):return REFUSED_CODES[step]
    if step=='CALENDAR':
        if first['epoch']!=EPOCH_NAME:return 'CALENDAR_EPOCH_MISMATCH'
        if first['package_sha']!=PACKAGE_SHA:return 'CALENDAR_PACKAGE_MISMATCH'
        if first['document_order_sha']!=DOCUMENT_ORDER:return 'CALENDAR_DOCUMENT_ORDER_MISMATCH'
        return None
    if step=='IDENT':
        if lines[0]['line']['identities']!=lines[1]['line']['identities']:return 'IDENTITIES_DIFFER_BETWEEN_THE_TWO_RUNS'
        if any(first['identities'][name]!=host_identities[name] for name in CAPACITY_ROOTS):return 'IDENTITIES_DIFFER_FROM_THE_HOST'
        return None
    if first['roots']!=list(CAPACITY_ROOTS):return 'CAPACITY_ROOTS_NOT_THE_THREE'
    if first['veto_mode']!=VETO_MODE:return 'CAPACITY_VETO_MODE_NOT_AS_SIGNED'
    if first['config_sha256']!=plan_config_sha:return 'CAPACITY_CONFIG_SHA_NOT_EQUAL'
    if any(first['identities'][name]!=host_identities[name] for name in CAPACITY_ROOTS):return 'LOAD_IDENTITIES_DIFFER_FROM_THE_HOST'
    return None

def finding_code(after,worker_after,tree):
    """None when nothing is left and nothing moved; else the first finding beside an expected answer."""
    if after['status']!='COMPLETE':return 'CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'
    if after['names_present']:return 'CONTAINER_OF_THE_STEP_STILL_LISTED'
    if after['not_there_before']:return 'CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE'
    if worker_after is not None:
        if worker_after['status']!='COMPLETE':return 'WORKER_UNAVAILABLE_AFTER_THE_STEP'
        if not worker_after['unchanged']:return 'WORKER_CHANGED_DURING_THE_STEP'
    if tree is not None:
        if tree['status']!='COMPLETE':return 'CAPACITY_TREE_UNAVAILABLE_AFTER_THE_STEP'
        if not tree['unchanged']:return 'CAPACITY_TREE_CHANGED_DURING_THE_STEP'
    return None

def step_verdict(step,results,lines,host_identities,after,worker_after,tree,plan_config_sha=None):
    """(status, outcome, code) once a container of the step was started."""
    for result,line in zip(results,lines):
        code=answer_code(step,result,line)
        if code is not None:return PARTIAL_STATUS,PARTIAL_OUTCOME,code
    if len(results)<len(STEP_ROWS[step]):return PARTIAL_STATUS,PARTIAL_OUTCOME,'SECOND_RUN_NOT_STARTED'
    code=expectation_code(step,lines,host_identities,plan_config_sha)
    if code is not None:return PARTIAL_STATUS,NOT_AS_EXPECTED_OUTCOME,code
    code=finding_code(after,worker_after,tree)
    if code is not None:return PARTIAL_STATUS,WITH_FINDINGS_OUTCOME,code
    return COMPLETE_STATUS,STEP_OUTCOMES[step],None

def comparison(step,lines,host_identities):
    """Booleans beside the lines: whether the two IDENT runs agree, and each printed identity against the host's (the
    config directory's too, reported and not required). None when there is nothing to compare."""
    valid=[line['line'] for line in lines if line is not None and line['valid'] and line['line']['status']==OK_LINE_STATUS[step]]
    if step=='CALENDAR' or not valid:return None
    first=valid[0]['identities']
    return {'runs_agree':(len(valid)==2 and valid[1]['identities']==first) if step=='IDENT' else None,
            'equal_to_the_host':{name:first[name]==host_identities[name] for name in sorted(first) if name in host_identities}}

def tree_after(held,gate):
    """Every held directory of the tree proved again from '/': unchanged, changed, or not observed (a constant code)."""
    try:
        for item in held:item.verify(gate)
        return {'status':'COMPLETE','unchanged':True,'code':None}
    except Exception as error:
        if isinstance(error,Refused) and str(error)=='PARENT_REPLACED':return {'status':'COMPLETE','unchanged':False,'code':'PARENT_REPLACED'}
        return {'status':'UNAVAILABLE','unchanged':None,'code':safe(error)['code']}

def worker_again(commands,worker):
    """The worker after the container: the same container (ID), still running, on the same image."""
    try:again=container_facts(commands,WORKER_NAME,expected_name=WORKER_NAME)
    except Exception as error:return {'status':'UNAVAILABLE','unchanged':None,'code':safe(error)['code']}
    same=again['id']==worker['id'] and again['running'] is True and again['image_id']==worker['image_id'] and again['restarts']==worker['restarts']
    return {'status':'COMPLETE','unchanged':same,'code':None}

REDUCTIONS=[]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    step=plan['step'];raw=stdin_of(plan);names=container_names(plan,bound['go_sha256'][:16]);rows=STEP_ROWS[step]   # pure
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);held=[]
    precheck={'image':None,'capacity':None,'config_file':None,'worker':None,'containers_before':None,'names_free':None}
    facts={'containers':[],'lines':[],'host_identities':None,'containers_after':None,'worker_after':None,'tree_after':None}
    def finish(status,outcome,code,phase):
        lines=facts['lines']
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),step=step,effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            precheck=precheck,containers=facts['containers'],lines=lines,host_identities=facts['host_identities'],
            comparison=comparison(step,lines,facts['host_identities']),containers_after=facts['containers_after'],worker_after=facts['worker_after'],tree_after=facts['tree_after'],
            step_succeeded=status==COMPLETE_STATUS,writes=0,containers_run=commands.started['CONTAINER'],phase_reached=phase)))
    try:
        # ---- everything is looked at before the first container: a refusal up to here has started nothing
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            try:image=image_facts(commands,plan['image_id'])
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            need(image['id']==plan['image_id'],'IMAGE_ID_MISMATCH')
            need(image['revision_label']==plan['image_revision'],'IMAGE_REVISION_MISMATCH')
            precheck['image']={'id_as_signed':True,'revision_as_signed':True}
            if step!='CALENDAR':
                report,identities,children=hold_tree(host,plan,gate,held)
                precheck['capacity']=report;facts['host_identities']=identities
            if step=='LOAD':
                precheck['config_file']=config_file_facts(host,plan,children['config'],gate)
                worker,precheck['worker']=worker_facts(commands,plan)
                precheck['worker']['root_changed_after_the_worker_started']=changed_after(report['root']['ctime_ns'],worker['started_at'])
            try:before=container_list(commands)
            except CommandFailed:raise Refused('CONTAINER_LISTING_FAILED') from None
            precheck['containers_before']=len(before)
            precheck['names_free']=not any(row['name'] in names for row in before)
            need(precheck['names_free'],'CONTAINER_NAME_TAKEN')
            # The last refusal that costs nothing: every container of the step, by its class, and the reserve.
            need(gate()>=effects_budget(*rows),'BUDGET_INSUFFICIENT_BEFORE_THE_CONTAINER')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,'PRECHECK')
        # ---- the containers of the step, one after the other; the second IDENT run only after the first returned
        results=[]
        for row,name in zip(rows,names):
            if results and not results[-1]['returned']:break
            record={'name':name,'state':'NOT_STARTED','returncode':None,'code':None,'seconds':None};facts['containers'].append(record)
            started=attempt(monotonic)
            result=container_run(commands,row,plan['image_id'],mounts_of(plan),RUN_COMMAND,raw,container_name=name)
            ended=attempt(monotonic)
            record.update(code=result['code'],returncode=result['returncode'],
                          seconds=round(ended-started,3) if type(started) in (int,float) and type(ended) in (int,float) else None)
            if not result['started']:
                if not results:return finish(REFUSED_STATUS,REFUSED_OUTCOME,result['code'] or 'COMMAND_NOT_STARTED','CONTAINER_NOT_STARTED')
                break
            record['state']='RETURNED' if result['returned'] else 'DID_NOT_RETURN'
            results.append(result);facts['lines'].append(line_of(step,result) if result['returned'] else None)
        # ---- after them: what the engine still lists, the worker, the tree, whatever the runs said
        listing=attempt(lambda:container_list(commands))
        if type(listing) is list:
            known=set(row['id'] for row in before);new=[row for row in listing if row['id'] not in known]
            facts['containers_after']={'status':'COMPLETE','code':None,'before':len(before),'after':len(listing),'not_there_before':len(new),
                                       'names_present':any(row['name'] in names for row in listing),
                                       'rows':[{'id':row['id'],'state':row['state'],'of_this_step':row['name'] in names} for row in new[:MAX_NEW_CONTAINER_ROWS]]}
        else:facts['containers_after']={'status':'UNAVAILABLE','code':listing.get('code'),'before':len(before),'after':None,'not_there_before':None,
                                        'names_present':None,'rows':[]}
        if step=='LOAD':facts['worker_after']=worker_again(commands,worker)
        if step!='CALENDAR':facts['tree_after']=tree_after(held,gate)
        status,outcome,code=step_verdict(step,results,facts['lines'],facts['host_identities'],facts['containers_after'],
                                         facts['worker_after'],facts['tree_after'],plan['load']['config_sha256'] if step=='LOAD' else None)
        return finish(status,outcome,code,'CONTAINER')
    finally:
        for item in reversed(held):item.close()
# ==== END OP_CAPACITY_PROBE ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
