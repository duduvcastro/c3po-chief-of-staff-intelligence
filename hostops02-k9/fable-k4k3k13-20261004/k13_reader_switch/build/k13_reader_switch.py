"""OP_K13_READER_SWITCH: the switch of the V2 shadow reader unit of epoch R2D2-V2-SHADOW-2026-10-05.

One payload, three modes signed in the plan. ACTIVATE: every guard of the reader README (operation 4) that this core
can express is read first (executor, boot, the session day and the launch window, the three reader unit files, the
producer unit file, the launcher and pins.env by signed SHA-256, the shape of secret.env by metadata only, the release
file, the journal root, its catalog file, its device against the data volume's, its free space, the root-only chains
of the bind sources (Codex decision 6; the data volume bind is reported as not meeting it), the engine's security
options, the pinned image, no other reader container or process); then /etc/c3po-reader/activation.env is created
exclusively with its two constant lines (or, when it already holds exactly those bytes, accepted: reconcile), then
"systemctl enable --now c3po-reader.timer" and "systemctl start --no-block c3po-reader.service", each read back.
RESTART: the same guards with the activation file required, then "systemctl reset-failed" and "systemctl start
--no-block" of the service. DEACTIVATE: no file is read, then "systemctl disable --now c3po-reader.timer" and
"systemctl stop --no-block c3po-reader.service"; nothing is deleted. The only file this source can create is
activation.env (constant, not secret); it never reads, hashes, sizes or prints secret.env, never prints a container's
environment or its command line, never runs docker run, docker exec, docker stop or docker rm, never runs
daemon-reload by itself (enable and disable reload the manager as systemd documents), never waits for a unit to
settle and never retries. The caller authenticates exact request/authority/GO/source bytes first. No action on import.
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

# ==== BEGIN OP_K13_READER_SWITCH (this operation only) ====
OPERATION='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'
PHASE='WRITE_K13_READER_SWITCH'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K13_READER_SWITCH_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K13_READER_SWITCH_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K13_READER_SWITCH_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K13_READER_SWITCH_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K13_READER_SWITCH_PLAN_V1'
SOURCE_NAME='k13_reader_switch.py'
WRITES_ALLOWED=True
# systemctl enable, start, reset-failed, disable and stop switch a unit: the rows that run them are EFFECT rows and the
# source must carry the flag (CORE.md rule 8.2). The receipt says what the run did (activation_performed,
# daemon_reload_performed).
ACTIVATION_ALLOWED=True
# M6 (Monday 05/10), M6-s (Tuesday to Friday), RST (any session day) and X1 (Friday 09/10 after the close) all fall on
# 10-05 ... 10-09 UTC: the class of the core that holds them is WRITE_SESSIONS (10-05 ... 10-10). The session days and
# the launch window are this source's own guard on top of it (READER_NOT_A_SESSION_DAY, READER_OUTSIDE_LAUNCH_WINDOW).
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,)
MAX_GATE_SPAN_SECONDS=900
# The success outcome follows the signed mode (SUCCESS_IN_TEMPLATE=False in spec.py). COMPLETE_OUTCOME is ACTIVATE's.
COMPLETE_OUTCOME='RETURNED_REQUIRES_LIVENESS_READBACK'
RESTART_OUTCOME='RESTART_RETURNED_REQUIRES_LIVENESS_READBACK'
DEACTIVATE_OUTCOME='DEACTIVATED_REQUIRES_STOP_READBACK'
PARTIAL_OUTCOME='PARTIAL_SWITCH_STATE_REQUIRES_READBACK'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_SWITCH_STATE_REQUIRES_READBACK'
READER_MODES=('ACTIVATE','RESTART','DEACTIVATE')
MODE_OUTCOMES={'ACTIVATE':COMPLETE_OUTCOME,'RESTART':RESTART_OUTCOME,'DEACTIVATE':DEACTIVATE_OUTCOME}
PLAN_KEYS=frozenset(('mode','evidence_boot_id_sha256','unit_rows','config_rows','launcher_rows','journal_rows','release_rows','release',
                     'files','image_id','journal_free_floor_bytes','source_rows','capacity_rows'))
FILE_KEYS=('reader_service','reader_timer','reader_alert','producer_service','launcher','pins')
# What DEACTIVATE does not look at: null in its plan (anything else is refused, so a signer never signs a value that is
# not used). Revision 2 (review finding 7): stopping the reader is not blocked by the bytes of its unit files; the
# switch acts on the two unit names, and the states systemd reports for them are written in the receipt as read.
NOT_USED_BY_DEACTIVATE=('unit_rows','config_rows','launcher_rows','journal_rows','release_rows','release','files','image_id','journal_free_floor_bytes',
                        'source_rows','capacity_rows')

# ---- the reader of this epoch, as the reader README (installation candidate) and the installed producer unit fix it
READER_EPOCH='R2D2-V2-SHADOW-2026-10-05'
SESSION_DAYS=('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09')
# New York is UTC-4 for the whole epoch (daylight time ends on 2026-11-01); none of the five sessions closes early.
# The launch window of README operation 4 is open - 6 h (03:30 New York) to the close (16:00 New York); a launch at
# or after 09:28:30 New York (the handover) is allowed and marked LATE. Seconds of the UTC day:
LAUNCH_FROM_SECONDS=7*3600+30*60
LAUNCH_UNTIL_SECONDS=20*3600
LATE_FROM_SECONDS=13*3600+28*60+30
UNIT_DIRECTORY='/etc/systemd/system'
SERVICE_UNIT='c3po-reader.service'
TIMER_UNIT='c3po-reader.timer'
ALERT_UNIT='c3po-reader-alert.service'
PRODUCER_UNIT='c3po-massive.service'
CONFIG_DIRECTORY='/etc/c3po-reader'
LAUNCHER_DIRECTORY=CONFIG_DIRECTORY+'/launcher'
LAUNCHER_NAME='reader_launcher.py'
PINS_NAME='pins.env'
SECRET_NAME='secret.env'
ACTIVATION_NAME='activation.env'
DOCKER_CLI_NAME='docker-cli'
ACTIVATION_PATH=CONFIG_DIRECTORY+'/'+ACTIVATION_NAME
# README, "Environment files" 3: constant bytes, two lines, each ended by one newline; not secret.
ACTIVATION_BYTES=b'C3PO_R2D2_V2_SHADOW_ENABLED=true\nC3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true\n'
ACTIVATION_SHA256='2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b'
# The two journal values of the installed producer unit (e3-20261004-a): the host root on the root filesystem and its
# container path. The reader's journal bind is the producer's with ,readonly added.
JOURNAL_HOST_ROOT='/var/lib/c3po-bar/journal'
JOURNAL_CONTAINER_ROOT='/c3po-bar-journal'
CATALOG_SCHEMA_NAME='MASSIVE_SESSION_ROOT_V1'
EPOCH_FILE_NAME='epoch.json'
CATALOG_LOCK_NAME='maintenance.lock'
DATA_VOLUME='/mnt/day-d-data'
DATA_TARGET='/app/day-d-data'
CAPACITY_ROOT='/var/lib/c3po-capacity'
CAPACITY_TARGET='/c3po-capacity'
LAUNCHER_TARGET='/c3po-reader'
# Codex decision 6 (W/codex-six-design-decisions-20261004.txt item 6): every docker bind source and all its ancestors
# root-controlled. The epoch's source root moved under /var/lib/c3po and the reader binds it read-only at a top-level
# target named in pins.env (C3PO_R2D2_V2_SHADOW_SOURCE_DIR, K4 PINS): a fifth bind. The data volume bind (uid 1000)
# for the release file does NOT meet decision 6: it is read and reported (binds_not_root_controlled), not accepted
# silently and not refused here (moving the release is K10's and the signers' decision).
SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
SOURCE_TARGET='/c3po-[a-z0-9][a-z0-9-]*'
SOURCE_TARGETS_TAKEN=(CAPACITY_TARGET,LAUNCHER_TARGET,JOURNAL_CONTAINER_ROOT)
READER_CONTAINER='c3po-reader'
PRODUCER_FLOOR_BYTES=53687091200
# README operation 4: the signed floor is at least the producer's floor plus this for each session still to be retained
# (from the signed day to the last session, that day included: 56,706,990,080 bytes on 10-05), plus the GO's allowance.
SESSION_RETENTION_BYTES=603979776
MAX_UNIT_FILE_BYTES=65536
MAX_LAUNCHER_BYTES=65536
MAX_PINS_BYTES=4096
MAX_RELEASE_BYTES=1048576
MAX_EPOCH_FILE_BYTES=4096
MAX_COMMAND_WORDS=256
# pins.env, README "Environment files" 2, with L1: exactly these names, in this order.
PINS_NAMES=('C3PO_BUILD_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA','C3PO_R2D2_V2_SHADOW_SOURCE_DIR',
            'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR','C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR','C3PO_R2D2_V2_CAPACITY_REQUIRED','C3PO_R2D2_V2_CAPACITY_VETO_MODE',
            'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA','C3PO_R2D2_V2_SHADOW_POLL_SECONDS','C3PO_READER_LAUNCHER_SHA256')
PINS_VALUE='[A-Za-z0-9._=/:-]{1,200}'
# A process is a reader when a word of its command names the worker module or the launcher; a capacity-day process is not.
READER_MARKERS=('app.r2d2_v2_shadow_worker','reader_launcher.py')
NOT_A_READER_MARKER='--prepare-capacity-day'
SCAN_STATES=('running','paused','restarting')
# The main command of the reader container, as the installed unit runs it (docker-init is not the main process).
READER_COMMAND_WORDS=('python','-I','-B','/c3po-reader/reader_launcher.py')
ACTIVE_STATES=('active','activating','reloading')
STOPPED_STATES=('inactive','failed')
# Seconds that must be left, beyond the effects' own classes (effects_budget), when the first effect starts: the
# creation of activation.env (milliseconds) and nothing else runs between the first effect and the last.
SWITCH_FILE_ALLOWANCE_SECONDS=3
UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','NeedDaemonReload','Result')
# The fixed template of the process scan: identity, the main command (path and arguments) and the exec sessions of a
# container. Nothing of the environment. The words stay in memory: only booleans and counts leave.
CONTAINER_COMMAND_FORMAT='{"id":{{json .Id}},"path":{{json .Path}},"args":{{json .Args}},"exec_ids":{{json .ExecIDs}}}'
SECURITY_OPTIONS_FORMAT='{{json .SecurityOptions}}'

BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the name c3po-reader','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_command':command_row('docker',['container','inspect','--format',CONTAINER_COMMAND_FORMAT],'one container ID of the listing','QUICK','READ'),
          'engine_security':command_row('docker',['info','--format',SECURITY_OPTIONS_FORMAT],None,'QUICK','READ'),
          'service_state':command_row('systemctl',['show',SERVICE_UNIT],None,'QUICK','READ',tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)]),
          'timer_state':command_row('systemctl',['show',TIMER_UNIT],None,'QUICK','READ',tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)]),
          'timer_enabled':command_row('systemctl',['is-enabled',TIMER_UNIT],None,'QUICK','READ'),
          # enable --now and disable --now reload the manager and start or stop the timer: the class of the core for a
          # verb that reloads the manager (30 s). --no-block returns once the job is queued; reset-failed clears a state:
          # QUICK (8 s). A call killed by its limit leaves its effect unknown and the run PARTIAL (rule 4.1).
          'enable_now_timer':command_row('systemctl',['enable','--now',TIMER_UNIT],None,'SWITCH','EFFECT'),
          'start_service':command_row('systemctl',['start','--no-block',SERVICE_UNIT],None,'QUICK','EFFECT'),
          'reset_failed_service':command_row('systemctl',['reset-failed',SERVICE_UNIT],None,'QUICK','EFFECT'),
          'disable_now_timer':command_row('systemctl',['disable','--now',TIMER_UNIT],None,'SWITCH','EFFECT'),
          'stop_service':command_row('systemctl',['stop','--no-block',SERVICE_UNIT],None,'QUICK','EFFECT')}
MODE_EFFECTS={'ACTIVATE':('enable_now_timer','start_service'),'RESTART':('reset_failed_service','start_service'),
              'DEACTIVATE':('disable_now_timer','stop_service')}
RELOADING_ROWS=('enable_now_timer','disable_now_timer')

SCOPE_STATEMENT=('Switches the V2 shadow reader unit of epoch '+READER_EPOCH+' in the one mode the request signs. ACTIVATE: after '
                 'every guard is read (the session day and the launch window 07:30-20:00 UTC, the four unit files and the launcher and '
                 'pins.env by signed SHA-256, the shape of secret.env by metadata only, the release file, the journal root, its catalog '
                 'file, its device against the data volume, its free space, the engine security options, the pinned image, no other '
                 'reader container or process), creates '+ACTIVATION_PATH+' exclusively with its two constant lines (or accepts it when it '
                 'already holds exactly those bytes), then runs systemctl enable --now '+TIMER_UNIT+' and systemctl start --no-block '
                 +SERVICE_UNIT+'. RESTART: the same guards with that file required, then systemctl reset-failed and systemctl start '
                 '--no-block of the service. DEACTIVATE: no file is read, then systemctl disable --now of the timer and systemctl '
                 'stop --no-block of the service. Every switch is read back in the run. Nothing is deleted, overwritten, renamed, '
                 'chmodded or chowned; secret.env is never opened; no environment value and no command line of a container is printed; '
                 'no container is run, executed into, stopped or removed by docker; no retry, no wait for a unit to settle.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':READER_EPOCH,'modes':MODE_OUTCOMES,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'mode_effects':MODE_EFFECTS,
       'sessions':{'days':list(SESSION_DAYS),'launch_window_utc':['07:30:00','20:00:00'],'late_from_utc':'13:28:30',
                   'new_york':'UTC-4 for the whole epoch','applies_to':['ACTIVATE','RESTART']},
       'paths':{'unit_directory':UNIT_DIRECTORY,'units':[SERVICE_UNIT,TIMER_UNIT,ALERT_UNIT,PRODUCER_UNIT],'config_directory':CONFIG_DIRECTORY,
                'launcher':LAUNCHER_DIRECTORY+'/'+LAUNCHER_NAME,'pins':CONFIG_DIRECTORY+'/'+PINS_NAME,'secret':CONFIG_DIRECTORY+'/'+SECRET_NAME,
                'activation':ACTIVATION_PATH,'docker_cli':CONFIG_DIRECTORY+'/'+DOCKER_CLI_NAME,'journal_host_root':JOURNAL_HOST_ROOT,
                'journal_container_root':JOURNAL_CONTAINER_ROOT,'data_volume':DATA_VOLUME,'data_target':DATA_TARGET,
                'capacity_root':CAPACITY_ROOT,'capacity_target':CAPACITY_TARGET,'launcher_target':LAUNCHER_TARGET,'container':READER_CONTAINER,
                'source_root':SOURCE_ROOT,'source_target':SOURCE_TARGET,'source_targets_taken':list(SOURCE_TARGETS_TAKEN)},
       'codex_decision_6':'bind sources root-controlled; the data volume bind is reported as not meeting it (binds_not_root_controlled)',
       'activation_env':{'sha256':ACTIVATION_SHA256,'bytes':len(ACTIVATION_BYTES),'mode_octal':'0600','uid':0,'gid':0,'links':1,
                         'if_absent':'CREATE_EXCLUSIVE (ACTIVATE only)','if_present':'ACCEPTED ONLY WITH THE CONSTANT BYTES, 0:0, 0600, ONE LINK'},
       'pins_names':list(PINS_NAMES),'catalog':{'schema':CATALOG_SCHEMA_NAME,'files':[EPOCH_FILE_NAME,CATALOG_LOCK_NAME]},
       'unit_properties':list(UNIT_PROPERTIES),'reader_markers':list(READER_MARKERS),'not_a_reader_marker':NOT_A_READER_MARKER,
       'scan_states':list(SCAN_STATES),'reader_command':list(READER_COMMAND_WORDS),'producer_floor_bytes':PRODUCER_FLOOR_BYTES,
       'session_retention_bytes':SESSION_RETENTION_BYTES,'files':FILES_SCOPE,
       'secret_env':'lstat only: regular, 0:0, 0600, one link; never opened, read, hashed or sized',
       'file_contents_read':[BOOT_ID_PATH,'the four unit files','the launcher','pins.env','activation.env','the release file',
                             'epoch.json of the journal root'],
       'never':['docker run','docker exec','docker stop','docker rm','docker logs','daemon-reload of its own','a drop-in','overwrite','chmod',
                'chown','rename','truncate','removal of anything but the temporary of this run','secret.env opened','an environment value printed',
                'a container command line printed','a wait for a unit to settle','a retry','a shell'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'switch_file_allowance_seconds':SWITCH_FILE_ALLOWANCE_SECONDS,'unit_file_bytes':MAX_UNIT_FILE_BYTES,
                 'launcher_bytes':MAX_LAUNCHER_BYTES,'pins_bytes':MAX_PINS_BYTES,'release_bytes':MAX_RELEASE_BYTES,
                 'epoch_file_bytes':MAX_EPOCH_FILE_BYTES,'containers':MAX_CONTAINERS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the fixed commands, the creating calls."""


# ---------------------------------------------------------------- the plan (pure)
def root_controlled(row):
    """Beyond validate_chain without an open root (uid 0, no write bit for group or other): group 0 and no setgid."""
    return row['gid']==0 and not row['mode']&stat.S_ISGID

def private_directory_row(row):return (row['uid'],row['gid'],row['mode'])==(0,0,0o700)

def data_volume_row(rows):
    """The row of the data volume root in the signed chain of the release directory."""
    return [row for row in rows if row['path']==DATA_VOLUME][0]          # validate_plan proved it is a component of the chain

def validate_plan(plan):
    need(plan['mode'] in READER_MODES,'MODE_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    if plan['mode']=='DEACTIVATE':
        need(all(plan[key] is None for key in NOT_USED_BY_DEACTIVATE),'PLAN_MEMBER_NOT_USED_BY_MODE')
        return
    validate_chain(plan['unit_rows'],UNIT_DIRECTORY)
    need(all(root_controlled(row) for row in plan['unit_rows']),'UNIT_CHAIN_NOT_ROOT_CONTROLLED')
    files=exact(plan['files'],FILE_KEYS,'FILE_PINS_INVALID')
    need(all(hexpin(files[key]) for key in FILE_KEYS),'FILE_PINS_INVALID')
    validate_chain(plan['config_rows'],CONFIG_DIRECTORY,receives_entry=True)
    need(all(root_controlled(row) for row in plan['config_rows']) and private_directory_row(plan['config_rows'][-1]),'CONFIG_DIRECTORY_NOT_PRIVATE')
    validate_chain(plan['launcher_rows'],LAUNCHER_DIRECTORY)
    need(plan['launcher_rows'][:-1]==plan['config_rows'] and private_directory_row(plan['launcher_rows'][-1]),'LAUNCHER_DIRECTORY_NOT_PRIVATE')
    validate_chain(plan['journal_rows'],JOURNAL_HOST_ROOT)
    need(all(root_controlled(row) for row in plan['journal_rows']) and private_directory_row(plan['journal_rows'][-1]),'JOURNAL_ROOT_NOT_PRIVATE')
    validate_chain(plan['source_rows'],SOURCE_ROOT)
    need(all(root_controlled(row) for row in plan['source_rows']) and private_directory_row(plan['source_rows'][-1]),'SOURCE_ROOT_NOT_PRIVATE')
    validate_chain(plan['capacity_rows'],CAPACITY_ROOT)
    need(all(root_controlled(row) for row in plan['capacity_rows']) and private_directory_row(plan['capacity_rows'][-1]),'CAPACITY_ROOT_NOT_PRIVATE')
    rows=plan['release_rows']
    need(type(rows) is list and rows and type(rows[-1]) is dict and type(rows[-1].get('path')) is str and clean_path(rows[-1]['path'])
         and inside(rows[-1]['path'],DATA_VOLUME) and rows[-1]['path']!=DATA_VOLUME,'RELEASE_NOT_IN_THE_DATA_VOLUME')
    validate_chain(rows,rows[-1]['path'],open_root=DATA_VOLUME)
    need(mount_point_of(rows[:len(prefixes(DATA_VOLUME))])==DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    need(plan['journal_rows'][-1]['device']!=data_volume_row(rows)['device'],'JOURNAL_ON_THE_DATA_VOLUME')
    release=exact(plan['release'],('name','sha256'),'RELEASE_PLAN_INVALID')
    need(text(release['name'],FILE_NAME) and hexpin(release['sha256']),'RELEASE_PLAN_INVALID')
    need(text(plan['image_id'],IMAGE_ID),'IMAGE_ID_INVALID')
    need(integer(plan['journal_free_floor_bytes'],floor_minimum(plan)),'FREE_FLOOR_BELOW_PRODUCER_FLOOR')

def floor_minimum(plan):
    """The producer's floor plus the retention of every session from the signed day on (the plan's window was proved a
    UTC instant of that day before validate_plan runs)."""
    day=instant(plan['window']['not_before']).date().isoformat()
    return PRODUCER_FLOOR_BYTES+SESSION_RETENTION_BYTES*len([item for item in SESSION_DAYS if item>=day])

def release_path_of(plan):return plan['release_rows'][-1]['path']+'/'+plan['release']['name']

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    mode=plan['mode'];files=plan['files'] or {}
    out={'operation':OPERATION,'epoch':READER_EPOCH,'mode':mode,'success_outcome':MODE_OUTCOMES[mode],
         'switches':[COMMANDS[name]['argv'] for name in MODE_EFFECTS[mode]],
         'activation_env':{'path':ACTIVATION_PATH,'sha256':ACTIVATION_SHA256,
                           'action':{'ACTIVATE':'CREATE_IF_ABSENT_ACCEPT_IF_CONSTANT','RESTART':'REQUIRED_CONSTANT','DEACTIVATE':'NOT_LOOKED_AT'}[mode]},
         'unit_names':[SERVICE_UNIT,TIMER_UNIT],
         'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'files_deleted':False,'daemon_reload':'BY_ENABLE_OR_DISABLE_ONLY'}
    if mode=='DEACTIVATE':
        out.update(unit_directory=None,unit_files=None,bind_sources=None,launch_window=None,launcher=None,pins_sha256=None,journal=None,release=None,image_id=None);return out
    out.update(unit_directory=chain_effects(plan['unit_rows']),
               unit_files={SERVICE_UNIT:files['reader_service'],TIMER_UNIT:files['reader_timer'],ALERT_UNIT:files['reader_alert'],
                           PRODUCER_UNIT:files['producer_service']},
               launch_window={'days':list(SESSION_DAYS),'utc':['07:30:00','20:00:00'],'late_from_utc':'13:28:30'},
               launcher={'directory':chain_effects(plan['launcher_rows']),'sha256':files['launcher']},
               pins_sha256=files['pins'],
               journal={'root':chain_effects(plan['journal_rows']),'container_root':JOURNAL_CONTAINER_ROOT,
                        'free_floor_bytes':plan['journal_free_floor_bytes'],'data_volume_device':data_volume_row(plan['release_rows'])['device']},
               release={'path':release_path_of(plan),'sha256':plan['release']['sha256'],'directory':chain_effects(plan['release_rows'])},
               bind_sources={'source_root':chain_effects(plan['source_rows']),'capacity_root':chain_effects(plan['capacity_rows']),
                             'not_root_controlled':[DATA_VOLUME]},
               image_id=plan['image_id'])
    return out

def success_of(plan):return MODE_OUTCOMES[plan['mode']]


# ---------------------------------------------------------------- what is read
def launch_window(now):
    """The session day and the launch window (README operation 4): seconds of the UTC day, New York being UTC-4."""
    point=now.astimezone(timezone.utc);day=point.date().isoformat()
    need(day in SESSION_DAYS,'READER_NOT_A_SESSION_DAY')
    seconds=point.hour*3600+point.minute*60+point.second
    need(LAUNCH_FROM_SECONDS<=seconds<LAUNCH_UNTIL_SECONDS,'READER_OUTSIDE_LAUNCH_WINDOW')
    return {'session':day,'late':seconds>=LATE_FROM_SECONDS}

def entry_of(host,name,parent,gate):
    """One lstat of a plain name in a held, pinned directory; no link followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return info

def pinned_file(host,name,parent,gate,mode,limit,code):
    """A regular file of a held directory, root:root, the given mode, one link, read through a descriptor that must be
    the object the lstat saw. Returns its bytes. code is the refusal for every way it is not so."""
    info=entry_of(host,name,parent,gate)
    need(info is not None and stat.S_ISREG(info.st_mode) and info.st_size<=limit,code)
    try:raw,held=read_regular(host,name,parent.fd,gate,limit)
    except FileNotFoundError:raise Refused(code) from None
    need((held.st_dev,held.st_ino)==(info.st_dev,info.st_ino),code)
    need((held.st_uid,held.st_gid,stat.S_IMODE(held.st_mode),held.st_nlink)==(0,0,mode,1),code)
    return raw

def unit_values(commands,row,unit):
    """systemctl show of one unit: the properties of UNIT_PROPERTIES, each exactly once (any order)."""
    raw=commands.output(row)
    need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'UNIT_PROPERTIES_INVALID');values={}
    for line in raw.decode('ascii').splitlines():
        if not line:continue
        key,separator,value=line.partition('=');need(separator=='=','UNIT_PROPERTIES_INVALID')
        if key in UNIT_PROPERTIES:
            need(key not in values and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'UNIT_PROPERTIES_INVALID');values[key]=value
    need(set(values)==set(UNIT_PROPERTIES) and values['Id']==unit,'UNIT_PROPERTIES_INVALID')
    return values

def timer_enabled_word(commands):
    """systemctl is-enabled of the timer: the one word it prints. Its exit status (0 for enabled and for several other
    words, non-zero for disabled) adds nothing to the word and is not judged."""
    _,raw=commands.call('timer_enabled')
    need(re.fullmatch(rb'[a-z-]{1,32}\n?',raw) is not None,'TIMER_ENABLED_INVALID')
    return raw.decode('ascii').strip()

def unit_fit(values,unit):
    """The unit the manager has loaded is the installed file, with no drop-in."""
    need(values['LoadState']=='loaded','READER_UNIT_NOT_LOADED')
    need(values['FragmentPath']==UNIT_DIRECTORY+'/'+unit and values['DropInPaths']=='','READER_UNIT_NOT_THE_INSTALLED_FILE')

def engine_options(commands):
    """docker info SecurityOptions: true when neither user-namespace remapping nor rootless mode is named."""
    value=strict(commands.output('engine_security'))
    need(value is None or (type(value) is list and len(value)<=64 and all(type(item) is str and len(item)<=256 for item in value)),
         'ENGINE_SECURITY_OPTIONS_INVALID')
    need(not [item for item in value or [] if 'userns' in item.lower() or 'rootless' in item.lower()],'ENGINE_USERNS_OR_ROOTLESS')
    return {'options':len(value or []),'userns_or_rootless':False}

def reader_like(words):
    return any(marker in word for word in words for marker in READER_MARKERS) and not any(NOT_A_READER_MARKER in word for word in words)

def process_scan(commands,containers):
    """The main command of every container that can hold a process (README: a docker top of every running container;
    docker top is not a verb this core can run, see DESIGN.md). Booleans and counts only."""
    out=[]
    for row in containers:
        if row['state'] not in SCAN_STATES:continue
        value=decode(commands.output('container_command',row['id']))
        need(set(value)=={'id','path','args','exec_ids'} and value['id']==row['id'] and type(value['path']) is str
             and (value['args'] is None or (type(value['args']) is list and len(value['args'])<=MAX_COMMAND_WORDS and all(type(word) is str for word in value['args'])))
             and (value['exec_ids'] is None or (type(value['exec_ids']) is list and all(type(item) is str for item in value['exec_ids']))),
             'CONTAINER_COMMAND_INVALID')
        words=[value['path']]+list(value['args'] or [])
        out.append({'id':row['id'],'name':row['name'],'state':row['state'],'reader_like':reader_like(words),'launcher_command':words==list(READER_COMMAND_WORDS),
                    'exec_sessions':len(value['exec_ids'] or [])})
    return out

def pins_values(raw):
    """pins.env: ASCII, exactly the twelve names in order, one NAME=value per line, each ended by one newline."""
    need(type(raw) is bytes and re.fullmatch(rb'[ -~\n]*',raw) is not None and raw.endswith(b'\n'),'PINS_CONTENT_NOT_AS_SIGNED')
    lines=raw.decode('ascii').split('\n')[:-1]
    need(len(lines)==len(PINS_NAMES),'PINS_CONTENT_NOT_AS_SIGNED');values={}
    for line,name in zip(lines,PINS_NAMES):
        key,_,value=line.partition('=')            # a line with no '=' has an empty value, which the grammar refuses
        need(key==name and text(value,PINS_VALUE),'PINS_CONTENT_NOT_AS_SIGNED');values[key]=value
    return values

def unit_text_checks(service,producer,image_id,source_target):
    """The installed texts compared as text (README operation 4, parameters and mounts): the five read-only binds of
    the reader (README's four and the source root of decision 6), its image twice and no placeholder left; the
    producer's journal bind and argument, the same two values."""
    mounts=[(DATA_VOLUME,DATA_TARGET),(JOURNAL_HOST_ROOT,JOURNAL_CONTAINER_ROOT),(CAPACITY_ROOT,CAPACITY_TARGET),(LAUNCHER_DIRECTORY,LAUNCHER_TARGET),
            (SOURCE_ROOT,source_target)]
    need(all(service.count(('  --mount type=bind,source=%s,target=%s,readonly \\\n'%pair).encode('ascii'))==1 for pair in mounts)
         and service.count(b'--mount ')==len(mounts),'READER_UNIT_MOUNTS_NOT_AS_SIGNED')
    need(service.count(image_id.encode('ascii'))==2 and b'@' not in service,'READER_UNIT_IMAGE_NOT_THE_PIN')
    need(producer.count(('  --mount type=bind,source=%s,target=%s \\\n'%(JOURNAL_HOST_ROOT,JOURNAL_CONTAINER_ROOT)).encode('ascii'))==1
         and producer.count((' --journal-root %s '%JOURNAL_CONTAINER_ROOT).encode('ascii'))==1,'PRODUCER_UNIT_JOURNAL_NOT_AS_SIGNED')


# ---------------------------------------------------------------- settling a switch by its readback
# What each switch changes, as positions of (timer enabled word, timer ActiveState, service ActiveState): a failed switch
# proved nothing changed only when these read as before the run.
TARGET_WORD={'enable_now_timer':'enabled','disable_now_timer':'disabled'}
SETTLED_BY={'enable_now_timer':(0,1),'disable_now_timer':(0,1),'start_service':(2,),'reset_failed_service':(2,),'stop_service':(2,)}
def settle(state,name,result,before,after):
    """Exactly one of done / fail / unknown for a switch that started and returned, from what was read after it.
    before and after are (timer enabled word, timer ActiveState, service ActiveState); after is None when the readback
    failed. Returns the label written in the receipt."""
    if after is None:
        state.unknown();return 'UNKNOWN'
    word,timer,service=after
    reached={'enable_now_timer':word=='enabled' and timer=='active',
             'start_service':service in ('active','activating'),
             'reset_failed_service':result['returncode']==0 and service!='failed',
             'disable_now_timer':word=='disabled' and timer=='inactive',
             'stop_service':service not in ACTIVE_STATES}[name]
    if reached:
        state.done();return 'DONE'
    # enable --now and disable --now create or remove the symlinks, then reload the manager, then start or stop the
    # timer. When the word read before was already the target word, a failure may have come after the reload: nothing
    # read can prove that nothing changed (review finding 2).
    reloaded=name in TARGET_WORD and before[0]==TARGET_WORD[name]
    if result['returncode']!=0 and not reloaded and [after[index] for index in SETTLED_BY[name]]==[before[index] for index in SETTLED_BY[name]]:
        state.fail();return 'FAILED_NOTHING_CHANGED'
    state.unknown();return 'UNKNOWN'

def _reduce_scan(receipt):
    precheck=receipt.get('precheck') or {}
    if type(precheck.get('process_scan')) is list:precheck['process_scan']={'containers':len(precheck['process_scan']),
                                                                             'reader_like':sum(1 for row in precheck['process_scan'] if row.get('reader_like'))}
def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
REDUCTIONS=[('PROCESS_SCAN_REDUCED_TO_COUNTS',_reduce_scan),('PRECHECK_DROPPED',_reduce_precheck)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    mode=plan['mode'];switches=MODE_EFFECTS[mode];files=plan['files']        # pure: what will be compared and run
    gate()                                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);go16=bound['go_sha256'][:16]
    seen={'chains':{}};held=[];ledger=[];results={};after={}
    found={'activation_env':None,'window':None,'reconcile':False,'before':None}
    def finish(status,outcome,code,extra):
        labels=[item.get('settled') for item in results.values()]
        switched=True if 'DONE' in labels else (None if 'UNKNOWN' in labels else False)
        reloads=[results[name] for name in RELOADING_ROWS if name in results and results[name]['started']]
        reloaded=(True if [item for item in reloads if item.get('returncode')==0] else
                  None if [item for item in reloads if item['settled'] in ('UNKNOWN','DONE')] else False)
        changes=[item.get('changed') for item in results.values()]
        changed=True if True in changes else (None if None in changes else False)
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),mode=mode,effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            precheck=seen,activation_env=found['activation_env'],launch=found['window'],reconcile=found['reconcile'],
            ledger=ledger,switches=results,after=after,objects_left_by_this_run=objects_left([],ledger),
            binds_not_root_controlled=[] if mode=='DEACTIVATE' else [DATA_VOLUME],switches_changed_state=changed,activation_performed=switched,daemon_reload_performed=reloaded,files_deleted=False,**extra)))
    try:
        # ---- everything is looked at before the first effect
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            texts={}
            if mode!='DEACTIVATE':
                found['window']=launch_window(clock())
                units=Pinned(host,walk_pinned(host,plan['unit_rows'],gate,seen['chains'].setdefault('units',[])),rows=plan['unit_rows']);held.append(units)
                for key,unit in (('reader_service',SERVICE_UNIT),('reader_timer',TIMER_UNIT),('reader_alert',ALERT_UNIT),('producer_service',PRODUCER_UNIT)):
                    texts[key]=pinned_file(host,unit,units,gate,0o644,MAX_UNIT_FILE_BYTES,'UNIT_FILE_NOT_AS_SIGNED')
                    need(sha(texts[key])==files[key],'UNIT_FILE_NOT_AS_SIGNED')
                seen['unit_files']='EQUAL_TO_THE_SIGNED_HASHES'
            service=unit_values(commands,'service_state',SERVICE_UNIT);timer=unit_values(commands,'timer_state',TIMER_UNIT)
            word=timer_enabled_word(commands)
            seen['units']={'service':service,'timer':timer,'timer_enabled':word}
            if mode!='DEACTIVATE':
                unit_fit(service,SERVICE_UNIT);unit_fit(timer,TIMER_UNIT)
            found['before']=(word,timer['ActiveState'],service['ActiveState'])
            if mode!='DEACTIVATE':
                config=Pinned(host,walk_pinned(host,plan['config_rows'],gate,seen['chains'].setdefault('config',[])),rows=plan['config_rows']);held.append(config)
                launcher=Pinned(host,walk_pinned(host,plan['launcher_rows'],gate,seen['chains'].setdefault('launcher',[])),rows=plan['launcher_rows']);held.append(launcher)
                need(sha(pinned_file(host,LAUNCHER_NAME,launcher,gate,0o600,MAX_LAUNCHER_BYTES,'LAUNCHER_NOT_AS_SIGNED'))==files['launcher'],'LAUNCHER_NOT_AS_SIGNED')
                pins=pinned_file(host,PINS_NAME,config,gate,0o600,MAX_PINS_BYTES,'PINS_NOT_AS_SIGNED')
                need(sha(pins)==files['pins'],'PINS_NOT_AS_SIGNED')
                # secret.env: metadata only, never opened (its content cannot be signed; README asks for its shape)
                secret=entry_of(host,SECRET_NAME,config,gate)
                need(secret is not None and stat.S_ISREG(secret.st_mode) and (secret.st_uid,secret.st_gid,stat.S_IMODE(secret.st_mode),secret.st_nlink)==(0,0,0o600,1),
                     'SECRET_ENV_SHAPE')
                cli=entry_of(host,DOCKER_CLI_NAME,config,gate)
                need(cli is not None and stat.S_ISDIR(cli.st_mode) and (cli.st_uid,cli.st_gid,stat.S_IMODE(cli.st_mode))==(0,0,0o700),'DOCKER_CLI_DIRECTORY_NOT_PRIVATE')
                present=entry_of(host,ACTIVATION_NAME,config,gate)
                if present is None:found['activation_env']='ABSENT'
                else:
                    need(pinned_file(host,ACTIVATION_NAME,config,gate,0o600,len(ACTIVATION_BYTES),'ACTIVATION_ENV_NOT_THE_CONSTANT')==ACTIVATION_BYTES,
                         'ACTIVATION_ENV_NOT_THE_CONSTANT')
                    found['activation_env']='CONSTANT'
                need(mode=='ACTIVATE' or found['activation_env']=='CONSTANT','ACTIVATION_ENV_ABSENT')
                # the journal root: owner and mode by its signed rows, the catalog of this epoch bound to its identity
                journal=Pinned(host,walk_pinned(host,plan['journal_rows'],gate,seen['chains'].setdefault('journal',[])),rows=plan['journal_rows']);held.append(journal)
                expected=canonical({'schema':CATALOG_SCHEMA_NAME,'epoch':READER_EPOCH,'device':journal.identity[0],'inode':journal.identity[1]})
                need(pinned_file(host,EPOCH_FILE_NAME,journal,gate,0o600,MAX_EPOCH_FILE_BYTES,'CATALOG_FILE_NOT_PRIVATE')==expected,'CATALOG_NOT_THIS_EPOCH_AND_ROOT')
                lock=entry_of(host,CATALOG_LOCK_NAME,journal,gate)
                need(lock is not None and stat.S_ISREG(lock.st_mode) and (lock.st_uid,lock.st_gid,stat.S_IMODE(lock.st_mode),lock.st_nlink)==(0,0,0o600,1),
                     'CATALOG_FILE_NOT_PRIVATE')
                release=Pinned(host,walk_pinned(host,plan['release_rows'],gate,seen['chains'].setdefault('release',[])),rows=plan['release_rows']);held.append(release)
                # decision 6: the source root and the capacity tree, bind sources of the reader, walked by root-only chains
                held.append(Pinned(host,walk_pinned(host,plan['source_rows'],gate,seen['chains'].setdefault('source',[])),rows=plan['source_rows']))
                held.append(Pinned(host,walk_pinned(host,plan['capacity_rows'],gate,seen['chains'].setdefault('capacity',[])),rows=plan['capacity_rows']))
                # the journal's device differs from the data volume's: refused from the signed rows (validate_plan), and
                # both walks above held each directory equal to its signed row, device included
                free=free_bytes(host,journal.fd)
                seen['journal']={'device':journal.identity[0],'inode':journal.identity[1],'free_bytes':free,'catalog':'EPOCH_JSON_EQUAL','maintenance_lock':'PRIVATE'}
                need(free>=plan['journal_free_floor_bytes'],'JOURNAL_FREE_SPACE_BELOW_FLOOR')
                need(sha(pinned_file(host,plan['release']['name'],release,gate,0o600,MAX_RELEASE_BYTES,'RELEASE_NOT_AS_SIGNED'))==plan['release']['sha256'],
                     'RELEASE_NOT_AS_SIGNED')
                seen['files']={'launcher':files['launcher'],'pins':files['pins'],'release':plan['release']['sha256'],'secret_env':'SHAPE_ONLY_AS_REQUIRED',
                               'docker_cli':'PRIVATE_DIRECTORY','activation_env':found['activation_env']}
                seen['engine']=engine_options(commands)
                image=image_facts(commands,plan['image_id'])
                need(image['id']==plan['image_id'],'IMAGE_NOT_PRESENT')
                seen['image']={'id':image['id'],'revision_label':image['revision_label']}
                values=pins_values(pins)
                need(values['C3PO_R2D2_V2_SHADOW_RELEASE_FILE']==DATA_TARGET+release_path_of(plan)[len(DATA_VOLUME):]
                     and values['C3PO_R2D2_V2_SHADOW_RELEASE_SHA']==plan['release']['sha256']
                     and values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR']==JOURNAL_CONTAINER_ROOT
                     and values['C3PO_READER_LAUNCHER_SHA256']==files['launcher'],'PINS_CONTENT_NOT_AS_SIGNED')
                need(values['C3PO_BUILD_SHA']==image['revision_label'],'PINS_BUILD_SHA_NOT_THE_IMAGE_REVISION')
                target=values['C3PO_R2D2_V2_SHADOW_SOURCE_DIR']
                need(text(target,SOURCE_TARGET) and target not in SOURCE_TARGETS_TAKEN,'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET')
                unit_text_checks(texts['reader_service'],texts['producer_service'],plan['image_id'],target)
                containers=container_list(commands)
                scan=process_scan(commands,containers);seen['process_scan']=scan
                own=[row for row in containers if row['name']==READER_CONTAINER]
                active=service['ActiveState'] in ACTIVE_STATES
                if mode=='ACTIVATE' and found['activation_env']=='ABSENT':
                    need(word=='disabled' and timer['ActiveState']=='inactive','TIMER_ENABLED_BEFORE_ACTIVATION')
                    need(service['ActiveState'] in STOPPED_STATES,'SERVICE_ACTIVE_BEFORE_ACTIVATION')
                elif mode=='ACTIVATE':
                    need(service['ActiveState'] in STOPPED_STATES+ACTIVE_STATES,'SERVICE_STATE_UNEXPECTED')
                    found['reconcile']=True
                else:
                    need(word=='enabled','TIMER_NOT_ENABLED')
                    need(service['ActiveState'] in STOPPED_STATES,'SERVICE_NOT_STOPPED')
                    need(service['NeedDaemonReload']=='no','READER_UNIT_NEEDS_DAEMON_RELOAD')
                if mode=='ACTIVATE' and found['reconcile'] and active and own:
                    # the reader being reconciled: its own container, running the pinned image, and no reader elsewhere
                    facts=container_facts(commands,READER_CONTAINER,expected_name=READER_CONTAINER)
                    need(facts['id']==own[0]['id'],'READER_CONTAINER_CHANGED')
                    need(facts['running'] is True and facts['image_id']==plan['image_id'],'READER_CONTAINER_NOT_THE_PINNED_READER')
                    need([row['launcher_command'] for row in scan if row['id']==facts['id']]==[True],'READER_CONTAINER_NOT_THE_PINNED_READER')
                    need(service['NeedDaemonReload']=='no','READER_UNIT_NEEDS_DAEMON_RELOAD')
                    seen['reconciled_container']={'id':facts['id'],'started_at':facts['started_at'],'restarts':facts['restarts']}
                    need(not [row for row in scan if row['reader_like'] and row['name']!=READER_CONTAINER],'READER_PROCESS_FOUND')
                else:
                    need(not own,'READER_CONTAINER_PRESENT')
                    need(not [row for row in scan if row['reader_like']],'READER_PROCESS_FOUND')
            # the last refusal that costs nothing on the host: every switch of the mode fits, with the file allowance
            left=gate();seen['seconds_left_before_first_effect']=int(left)
            need(left>=effects_budget(*switches)+SWITCH_FILE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- effects: from here on nothing refuses unless nothing has changed
        stop=None
        if mode=='ACTIVATE' and found['activation_env']=='ABSENT':
            row=create_file(0,'ACTIVATION_ENV',ACTIVATION_PATH,ACTIVATION_BYTES,0o600,config,host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'ACTIVATION_ENV_NOT_CREATED'
        for name in switches:
            if stop is not None:
                results[name]={'started':False,'settled':'NOT_ATTEMPTED'};continue          # 'changed' is set after the readback
            result=effect(state,commands,name)
            results[name]={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],
                           'settled':None if result['returned'] else ('NOT_STARTED' if not result['started'] else 'UNKNOWN')}
            if not result['started']:stop=result['code'] or 'SWITCH_NOT_STARTED'
            elif not result['returned']:stop=result['code'] or 'SWITCH_UNCERTAIN'
            elif result['returncode']!=0:stop='SWITCH_COMMAND_FAILED'
        # ---- readback inside the run: the unit states, then the file this run created or accepted
        read=None
        try:
            word=timer_enabled_word(commands);timer=unit_values(commands,'timer_state',TIMER_UNIT);service=unit_values(commands,'service_state',SERVICE_UNIT)
            read=(word,timer['ActiveState'],service['ActiveState'])
            after.update(timer_enabled=word,timer={key:timer[key] for key in ('ActiveState','SubState','UnitFileState')},
                         service={key:service[key] for key in ('ActiveState','SubState','Result')})
        except Exception as error:
            after['units']=safe(error)
            if stop is None:stop=code_of(error,'READBACK_UNAVAILABLE')
        for name,item in results.items():
            if item['settled'] is None:item['settled']=settle(state,name,item,found['before'],read)
            # what the switch changed, as read (README reconcile: "the starts then change nothing and the receipt says so")
            item['changed']=(False if not item['started'] else None if read is None or not item.get('returned') else
                             [read[index] for index in SETTLED_BY[name]]!=[found['before'][index] for index in SETTLED_BY[name]])
        if mode=='ACTIVATE':
            if ledger:
                failed=readback_file(ledger[0],ACTIVATION_BYTES,0o600,config,host,gate) if ledger[0]['state']=='INSTALLED_DURABLE' else None
                if failed is not None and stop is None:stop=failed
            elif found['activation_env']=='CONSTANT':
                try:
                    need(pinned_file(host,ACTIVATION_NAME,config,gate,0o600,len(ACTIVATION_BYTES),'ACTIVATION_ENV_CHANGED')==ACTIVATION_BYTES,'ACTIVATION_ENV_CHANGED')
                    after['activation_env']='CONSTANT'
                except Exception as error:
                    after['activation_env']=safe(error)
                    if stop is None:stop=code_of(error,'READBACK_UNAVAILABLE')
        if mode!='DEACTIVATE':
            # a fact, not a gate: with --no-block the container may not exist yet
            def container_after():
                rows=[row for row in container_list(commands) if row['name']==READER_CONTAINER]
                if not rows:return {'status':'COMPLETE','exists':False}
                facts=container_facts(commands,READER_CONTAINER,expected_name=READER_CONTAINER)
                return {'status':'COMPLETE','exists':True,'id':facts['id'],'state':facts['state'],'started_at':facts['started_at'],
                        'image_equal_the_pin':facts['image_id']==plan['image_id'],'restarts':facts['restarts']}
            after['container']=attempt(container_after)
        if stop is None and [name for name,item in results.items() if item['settled']!='DONE']:stop='SWITCH_NOT_READ_BACK_AS_DONE'
        extra={'phase_reached':'EFFECTS'}
        if stop is None:return finish(COMPLETE_STATUS,MODE_OUTCOMES[mode],None,extra)
        # REFUSED only while no call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in held:
            try:handle.close()
            except Exception:pass
# ==== END OP_K13_READER_SWITCH ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
