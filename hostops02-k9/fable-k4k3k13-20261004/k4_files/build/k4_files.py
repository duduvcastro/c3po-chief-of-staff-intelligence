"""OP_K4_FILES: private, non-secret file deliveries of epoch R2D2-V2-SHADOW-2026-10-05, one signed mode per request.

CHAIN_STATIC (plan row B5): the seven chain documents (Act A's three signatures, Act B, its three approvals), whose bytes
are compiled into this source, into the documents root of the capacity tree, and the reader's static capacity config
week.static.capacity.json, whose bytes the request carries, into its config root. PINS (B6): /etc/c3po-reader/pins.env,
twelve lines rendered by this source from the twelve signed values, after the static config, the launcher and the two
installed units it names were read on the host and found to be the signed bytes. LAUNCHER (A8): the directory
/etc/c3po-reader/launcher and in it reader_launcher.py, the bytes the request carries.
Every file root:root 0600, every directory root:root 0700, created exclusively (temporary, fsync, link, removal of the
temporary proved by identity) relative to a held descriptor of a parent walked from "/" against signed rows, then
read back through descriptors inside the run. Everything is looked at before the first creation. This source starts
no process, opens no socket, reads no environment and no secret, never activates anything, never touches a container
and never changes, renames or removes an object that exists. The caller authenticates exact request/authority/GO/
source bytes first. No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
CORE_PARTS={'core': 'ecf72edaf2bae478186e642bc93804bd567384c5d13dfab2bb4c4d55d00eef7a', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'files': '6b96ad64fe8ce5a9a2293b109964e069c2ad32169e7d421449da3f88516b60ba'}
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

# ==== BEGIN OP_K4_FILES (this operation only) ====
import base64

OPERATION='GO_WRITE_HOSTOPS02_K4_FILES_01'
PHASE='WRITE_K4_FILES_PRIVATE_DELIVERY'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K4_FILES_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K4_FILES_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K4_FILES_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K4_FILES_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K4_FILES_PLAN_V1'
SOURCE_NAME='k4_files.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
# B5, B6 and A8 run in the bands of A2 rev3 (Sunday 04/10 13:26-20:30 BRT, i.e. 2026-10-04 UTC, and Monday 05/10 to
# Thursday 08/10 17:38-20:30 BRT, the same UTC day each). The narrowest class of the core that holds all of those days
# is WRITE_EPOCH (10-03 ... 10-10 UTC); the bands themselves are the binder's and the signer's.
DATE_CLASS='WRITE_EPOCH'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The rows of /etc/c3po-reader and of the capacity tree were created by the provisioning (E2, 2026-10-03) and are
# copied from its ledger; the rows above them and the boot come from a read-only precheck of the same boot.
PROVISION_OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='K4_FILES_DELIVERED_READ_BACK'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('mode','delivery','evidence_boot_id_sha256'))
K4_MODES=('CHAIN_STATIC','PINS','LAUNCHER','WRITER')
K4_BYTES_KEYS=frozenset(('content_b64','sha256','bytes'))

# ---- PLACEMENT, as provisioned on 2026-10-03 (E2, GO_WRITE_SUPERVISOR_READER_PROVISION_01, KNOWN_COMPLETE) and as the
# ---- reader's README names the files. Every path below derives from these lines.
K4_EPOCH='R2D2-V2-SHADOW-2026-10-05'
READER_CONFIG_DIRECTORY='/etc/c3po-reader'
CAPACITY_ROOT='/var/lib/c3po-capacity'
UNIT_DIRECTORY='/etc/systemd/system'
# Codex decision 6 (W/codex-six-design-decisions-20261004.txt, 4b169599...9c55): every docker bind source and its
# ancestors root-controlled; the epoch's source root is no longer on the data volume.
K4_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
K4_JOURNAL_HOST='/var/lib/c3po-bar/journal'            # the installed producer unit's HOST_JOURNAL_ROOT (E3, 2026-10-04)
# ---- end of the placement

DOCUMENTS_DIRECTORY=CAPACITY_ROOT+'/documents'
CAPACITY_CONFIG_DIRECTORY=CAPACITY_ROOT+'/config'
STATIC_CONFIG_NAME='week.static.capacity.json'
LAUNCHER_DIRECTORY_NAME='launcher'
LAUNCHER_DIRECTORY=READER_CONFIG_DIRECTORY+'/'+LAUNCHER_DIRECTORY_NAME
LAUNCHER_NAME='reader_launcher.py'
PINS_NAME='pins.env'
PRODUCER_UNIT_NAME='c3po-massive.service'
READER_UNIT_NAME='c3po-reader.service'
CONTAINER_DATA_ROOT='/app/day-d-data'
CONTAINER_CAPACITY_ROOT='/c3po-capacity'
CONTAINER_LAUNCHER_ROOT='/c3po-reader'
WRITER_STEM='manifest_writer-'
WRITER_EXTENSION='.py'

# The release of the epoch, approved by Codex (DOC-C final, PASS_SCOPED, comment 5970623207) and the package and code
# revision it was built from (W/fable-actb03-20261004/chain/ACTB_BUILD_RECORD.json; tests compare these with that file).
K4_RELEASE_SHA='fc2f64ea252f9996ba62cd8bb10411ea0cbc3a351c15b8612de88390ccbdcaa1'
K4_PACKAGE_SHA='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
K4_CODE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
K4_SESSIONS=('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09')

# What a static capacity config is made of (capacity_day_documents.py: CONFIG_KEYS, CONFIG_SCHEMA, VETO_MODE, CHAIN).
STATIC_CONFIG_KEYS=frozenset(('schema','r2d2_v2_capacity_veto_mode','identity','calendar_pin_sha','release_sha','package_sha','roots',
                              'document_pins','veto_views','restore_revocation'))
STATIC_CONFIG_SCHEMA='R2D2_CAPACITY_BOOTSTRAP_V3'
K4_VETO_MODE='DISPATCH_AND_DERIVATION_ONLY'
CAPACITY_ROOT_NAMES=('documents','payload','go')
STATIC_IDENTITY_KEYS=('epoch','namespace','first_session','authorized_sessions','document_order_sha','runtime_order_sha')   # validate_identity
K4_DOCUMENT_FILE='[A-Za-z0-9][A-Za-z0-9._=-]{0,127}'   # the documents tool's file names (_FILE)
MAX_STATIC_CONFIG_BYTES=16384
MAX_LAUNCHER_BYTES=32768
FREE_BYTES_FLOOR=1048576                  # bytes a non-root writer must still have on the target filesystem
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the first creation

# ---- CHAIN BLOCK BEGIN (written by chain_block.py from the signed chain; never edited by hand) ----
K4_CHAIN_DOCUMENTS=(
    ('CODEX','CODEX_ORDEM_EPOCA_03_SIGNATURE.rev2.json','c7b8bfe13fff0231b5bc12736886818b4208f8492998f4528319606f5f556a1c',542,
     ('ewogICJzY2hlbWEiOiAiQ09ERVhfRE9DVU1FTlRBUllfU0lHTkFUVVJFX1YxIiwKICAiZG9jdW1lbnQiOiAiT1JERU1fRVBP'
      'Q0FfMDMucmV2Mi5tZCIsCiAgImRvY3VtZW50X3NoYTI1NiI6ICIxYTUyNTNiZjIzZjUwMDYyMjRiNzk1MjdkYTA2Njk3NjQ2'
      'YzM0YzZmNWEzYTRmODIwYWY1ZGEyYjEzZDdhMTE4IiwKICAic2lnbmVyIjogIkNPREVYIiwKICAidmVyZGljdCI6ICJBQ1Rf'
      'QV9TQ09QRV9BUFBST1ZFRF9QRU5ESU5HX0ZBQkxFX0RVRFVfU0FNRV9SRVZJU0lPTiIsCiAgImF1dGhvcml0eV9jb21tZW50'
      'IjogNTk0MzgyNDA1MCwKICAicmV2aWV3X3NoYTI1NiI6ICJkMWIxZGM4Nzk0MjFhMGMyOTYwODFjZTMzYzkwY2M1NmYwM2Yw'
      'OGY3NDY4Y2I1M2EzZGUwYjM5NDYzZTkxYTFkIiwKICAiZXhlY3V0aW9uX2F1dGhvcml6ZWQiOiBmYWxzZSwKICAib3BlcmF0'
      'aW9uYWxfZXZpZGVuY2VfY2xhaW1lZCI6IGZhbHNlLAogICJpbXBsZW1lbnRhdGlvbl9jZXJ0aWZpZWQiOiBmYWxzZSwKICAi'
      'YWN0X2JfcmVxdWlyZWRfZm9yX3RlbXBsYXRlcyI6IHRydWUKfQo=')),
    ('FABLE','FABLE_ORDEM_EPOCA_03_SIGNATURE.rev2.json','69ce6f18151c3511d8963252a113c1c806aebe128b7876d962ab391a5994558c',495,
     ('ewogICJhY3RfYl9yZXF1aXJlZF9mb3JfdGVtcGxhdGVzIjogdHJ1ZSwKICAiY29kZXhfc2lnbmF0dXJlX3NoYTI1Nl92ZXJp'
      'ZmllZF9ieV9jb21tYW5kIjogImM3YjhiZmUxM2ZmZjAyMzFiNWJjMTI3MzY4ODY4MThiNDIwOGY4NDkyOTk4ZjQ1MjgzMTk2'
      'MDZmNWY1NTZhMWMiLAogICJkb2N1bWVudCI6ICJPUkRFTV9FUE9DQV8wMy5yZXYyLm1kIiwKICAiZG9jdW1lbnRfc2hhMjU2'
      'IjogIjFhNTI1M2JmMjNmNTAwNjIyNGI3OTUyN2RhMDY2OTc2NDZjMzRjNmY1YTNhNGY4MjBhZjVkYTJiMTNkN2ExMTgiLAog'
      'ICJleGVjdXRpb25fYXV0aG9yaXplZCI6IGZhbHNlLAogICJzY2hlbWEiOiAiRkFCTEVfRE9DVU1FTlRBUllfU0lHTkFUVVJF'
      'X1YxIiwKICAic2lnbmVkX2F0X3V0YyI6ICIyMDI2LTEwLTAyVDAxOjI4OjI0WiIsCiAgInNpZ25lciI6ICJGQUJMRSIsCiAg'
      'InZlcmRpY3QiOiAiQUNUX0FfU0NPUEVfQVBQUk9WRURfUEVORElOR19EVURVX1NBTUVfUkVWSVNJT04iCn0K')),
    ('DUDU','DUDU_ORDEM_EPOCA_03_SIGNATURE.rev2.json','2ee6de217316df6577f751e208be5239c34839f606ab12bb39235e65c2948f5c',391,
     ('eyJzY2hlbWEiOiJPV05FUl9ET0NVTUVOVEFSWV9TSUdOQVRVUkVfVjEiLCJkb2N1bWVudCI6Ik9SREVNX0VQT0NBXzAzLnJl'
      'djIubWQiLCJkb2N1bWVudF9zaGEyNTYiOiIxYTUyNTNiZjIzZjUwMDYyMjRiNzk1MjdkYTA2Njk3NjQ2YzM0YzZmNWEzYTRm'
      'ODIwYWY1ZGEyYjEzZDdhMTE4IiwicHJpb3Jfc2lnbmF0dXJlcyI6WyJGQUJMRSA2OWNlNmYxODE1MWMzNTExZDg5NjMyNTJh'
      'MTEzYzFjODA2YWViZTEyOGI3ODc2ZDk2MmFiMzkxYTU5OTQ1NThjIl0sInNpZ25lciI6IkRVRFUiLCJvd25lcl9hbnN3ZXJf'
      'dmVyYmF0aW0iOiJBc3Npbm8gYSByZXYyIiwiY2hhbm5lbCI6IkFza1VzZXJRdWVzdGlvbiB2aWEgRmFibGUiLCJzaWduZWRf'
      'YXRfdXRjIjoiMjAyNi0xMC0wMlQwMTozMToyMVoifQ==')),
    ('ACT_B','ADENDO_EPOCA_03.md','ab241993da959b22a91e840547c6ab1133491d558043756e3af532bd8d46aaaf',32329,
     ('IyBBREVORE9fRVBPQ0FfMDMg4oCUIGF0byAoYikgZGEgT1JERU1fRVBPQ0FfMDMgcmV2aXPDo28gMgoKRXN0YWRvOiBhdG8g'
      'KGIpIHBhcmEgYXNzaW5hdHVyYSBDT0RFWCDihpIgRkFCTEUg4oaSIERVRFUuIE7Do28gw6kgR08gZGUgZmFzZSwgbsOjbyBl'
      'eGVjdXRhIG5hZGEgZSBuw6NvIGRpc3BlbnNhIG5lbmh1bSBHTyBpbmRpdmlkdWFsLCBuZW5odW1hIGF1dG9yaWRhZGUgZG8g'
      'ZG9ubyBuZW0gbmVuaHVtYSBhc3NpbmF0dXJhIHBvciBoYXNoIHF1ZSBhIG9yZGVtIG91IGFzIGRlY2lzw7VlcyBkbyBkb25v'
      'IGV4aWphbS4KCiMjIDEuIERlIG9uZGUgdmVtCgotIEF0byAoYSk6IGBPUkRFTV9FUE9DQV8wMy5yZXYyLm1kYCwgU0hBLTI1'
      'NiBgMWE1MjUzYmYyM2Y1MDA2MjI0Yjc5NTI3ZGEwNjY5NzY0NmMzNGM2ZjVhM2E0ZjgyMGFmNWRhMmIxM2Q3YTExOGAsIGFz'
      'c2luYWRhIENPREVYIGBjN2I4YmZlMTNmZmYwMjMxYjViYzEyNzM2ODg2ODE4YjQyMDhmODQ5Mjk5OGY0NTI4MzE5NjA2ZjVm'
      'NTU2YTFjYCDihpIgRkFCTEUgYDY5Y2U2ZjE4MTUxYzM1MTFkODk2MzI1MmExMTNjMWM4MDZhZWJlMTI4Yjc4NzZkOTYyYWIz'
      'OTFhNTk5NDU1OGNgIOKGkiBEVURVIGAyZWU2ZGUyMTczMTZkZjY1NzdmNzUxZTIwOGJlNTIzOWMzNDgzOWY2MDZhYjEyYmIz'
      'OTIzNWU2NWMyOTQ4ZjVjYCAocmVzcG9zdGEgZG8gZG9ubyAiQXNzaW5vIGEgcmV2MiIsIDIwMjYtMTAtMDJUMDE6MzE6MjFa'
      'KS4gQSBsaW5oYSAzNyBkYSBvcmRlbSAoT1JEOjM3KSBjcmlhIGVzdGUgYXRvOiB0ZW1wbGF0ZXMgZXhhdG9zIGRhcyBvcmRl'
      'bnMgZGnDoXJpYXMgZGVyaXZhZGFzLCBwb3IgZmFzZSBlIHBvciBEQVksIHVtIHbDrW5jdWxvIGRlIHRlbXBsYXRlIHBhcmEg'
      'Y2FkYSB1bWEgZGFzIGNpbmNvIHNlc3PDtWVzIG51bSBzw7MgYXRvLCBvIHNjcmlwdCBkZXRlcm1pbsOtc3RpY28gZGUgZGVy'
      'aXZhw6fDo28gZSBvcyBjYW1wb3Mgc3Vic3RpdHXDrXZlaXM7IHNlbSBlc3RlIGF0byBhc3NpbmFkbyBlIHN1YSBjYWRlaWEg'
      'Y29tcGxldGEgbmVuaHVtYSBmYXNlIGRpw6FyaWEgw6kgZXhlY3V0YWRhLgotIMOJcG9jYSBgUjJEMi1WMi1TSEFET1ctMjAy'
      'Ni0xMC0wNWA7IDHCqiBzZXNzw6NvIDIwMjYtMTAtMDU7IHNlc3PDtWVzIGF1dG9yaXphZGFzIDIwMjYtMTAtMDUsIDIwMjYt'
      'MTAtMDYsIDIwMjYtMTAtMDcsIDIwMjYtMTAtMDgsIDIwMjYtMTAtMDkgKE9SRDo3KS4KLSBDw7NkaWdvOiByZXZpc8OjbyBg'
      'ZGQ0ZWM0YmI4ZGFiNGQ4YjAzNzJiMGY5ZWFiYzkwYmY2NDQzZTg1OGAsIHBhY290ZSBkZSBpbXBsZW1lbnRhw6fDo28gYGI1'
      'Y2U1MjdhNTQ0Y2EwZWIwOGYwNzE4ZDgzNTQ2ZDdiNDZmOWU5Nzc0YmU4ZTQzNTFhZmNlMjEyZTcyYmRiODRgLiBSZWxlYXNl'
      'IGBmYzJmNjRlYTI1MmY5OTk2YmE2MmNkOGJiMTA0MTFlYTBjYmMzYTM1MWMxNWI4NjEyZGU4ODM5MGNjYmRjYWExYC4gUG9s'
      'aWN5IGBkMmZiM2U3NzRjMWRmN2I0YTgwZjY3MGQxYmRmZGIzZjIzZjkwYjIyMWQ3YmY0NWE3Y2VkOTYxNjRiZTczOGZlYCAo'
      'NzQ1IGJ5dGVzLCBKU09OIGNhbsO0bmljbzogbyBTSEEtMjU2IGRvIGFycXVpdm8gw6kgbyBkaWdlc3QgZG8gY29udGXDumRv'
      'LCBvIG1lc21vIHZhbG9yIHF1ZSBvIGNvbnRyb2xhZG9yLCBvIG1vbnRhZG9yIGUgZXN0ZSBhdG8gY29tcGFyYW0pLCB2w6Fs'
      'aWRhIGRlIDIwMjYtMTAtMDVUMDA6MDA6MDBaIChkb20gMDQvMTAgMjE6MDAgQlJUKSBhdMOpIDIwMjYtMTAtMDlUMjA6MDA6'
      'MDBaIChzZXggMDkvMTAgMTc6MDAgQlJULCBleGNsdXNpdm8pLgotIE9iamV0byBPUkRFUiBkbyBhdG8gKGIpOiBxdWF0cm8g'
      'Y2hhdmVzIOKAlCBhcyBjaW5jbyBzZXNzw7VlcywgYGNhcGFjaXR5YCA1NTAsIGEgw6lwb2NhIGUgYG93bmVyX3NoYWAgPSBT'
      'SEEtMjU2IGRhIGFzc2luYXR1cmEgZG8gZG9ubyBubyBhdG8gKGEpLiBgb3JkZXJfc2hhYCA9IGA1MTg2Mjc5MTk3NTRmNzk1'
      'ZmY1NTFjOWQ4MzNhM2IxMDAwZmI5MzBiNTU1ZGY2NDdlN2UwMGUyYjE5ZTc3NWZlYC4gw4kgbyBgc2lnbmVkX2Vwb2NoX29y'
      'ZGVyX3NoYWAgZGUgdG9kbyBwbGFubyBlIG8gYHNpZ25lZF9vcmRlcl9zaGFgIGRlIHRvZG8gR08gZGEgw6lwb2NhOyBuw6Nv'
      'IHNlIGNvbmZ1bmRlIGNvbSBvIGhhc2ggZG8gYXJxdWl2byBkYSBvcmRlbSAoYGRvY3VtZW50X29yZGVyX3NoYWApIG5lbSBj'
      'b20gYSBjb25zdGFudGUgZG8gY29udHJvbGFkb3IgKGBydW50aW1lX29yZGVyX3NoYWAgYDFhZDhiOTBjZmFiNjUxODIzZWI2'
      'NzdiODMwYTAwNzhkMTBjMTc0NDc1NzVjOGQ4MTNjMzg4M2E3MTg1NzlkOGVgLCBxdWUgYSBwb2xpY3kgY2FycmVnYSkuCi0g'
      'SW50ZXJmYWNlIGRhcyBmYXNlcyBkacOhcmlhcyAobm90YSBLOSwgcGxhbm8gbWVzdHJlIEMjNSk6IG5vdGEgYGFiNTE1OWJl'
      'YTM0YjMyMzkzNzllODdjMjUwMGQzODNmMDc3N2NjNjE4NjYxODQzNWJhMGVhOWY2MWUzZDU5NmNgOyBsaXN0YSBmZWNoYWRh'
      'IGRlIG9wZXJhw6fDtWVzIHBvciBmYXNlIGBiYzc5NmNiN2Q2ZDhhYjI5ZTMxNGFkMjljNzI2ZjMzZjE2ZjNiODNkZmNlZGU3'
      'NzcxZWMyYjJjZGFlMGU3ZDA4YCwgY29waWFkYSBlbSBjYWRhIHRlbXBsYXRlIGRhIHNlw6fDo28gNS4gQ29uZ2VsYSBvcyBu'
      'b21lcyBkYXMgb3BlcmHDp8O1ZXMsIG7Do28gbyBjw7NkaWdvLgotIERlY2lzw7VlcyBkbyBkb25vIGrDoSBlbSByZWdpc3Ry'
      'bywgcXVlIGVzdGUgYXRvIHRyYW5zY3JldmUgc2VtIGFtcGxpYXI6IHJlZ3JhcyAx4oCTNCBlIHJvbGxiYWNrIGAzNDQ5YzI1'
      'OWNlMTk2ZTNmNTY5NGI4NmY1NmQ1MzVmZTA4MzE0YWFkNjQ2YjQ2Mzc4NjY4OGQ5MDM5YWFmNGI5YDsgZW1lbmRhIGRvIHZl'
      'dG8gYDU3ODY2YWEzZmIyZThmMTYzZjIxZWI5NmY0ZjNkZWQ1MTgzZDkxYjk0MTU1NjU5MmJiYTgyOTA3MTFkZmU1MWVgOyBG'
      'YWJsZSBleGVjdXRhIGFzIGVzY3JpdGFzLCBjYWRhIHVtYSBjb20gYSBhc3NpbmF0dXJhIGluZGl2aWR1YWwgZG8gZG9ubyBw'
      'b3IgaGFzaCBgOTBmYzQ5YWY5ZGI5ZjVhMDZlYmFmZTNlMWQ4OTZmOTgwZDRjYmQzNTVmM2RhYjU0N2ZmZWRjMjUwMTg3MTk5'
      'ZWA7IGFzc2luYXR1cmEgw7puaWNhIHBvciBoYXNoIGRlIGNhZGEgcHJvZ3JhbWEgZGnDoXJpbyBgMTk4NDA5NDJhMzQxMTE3'
      'NmFjZDMxNTNmY2EzNjAzNmE3NmVlMTYyZWI0YmFjZGNkM2E0NmYwYWYwNWY1OGJiMmAgKHPDsyB2YWxlIGRlcG9pcyBkZSBv'
      'IENvZGV4IGVzY3JldmVyIG5vIGNhbmFsIHF1ZSBsw6ogYSByZWdyYSBkbyBtZXNtbyBqZWl0byk7IGVuY2VycmFtZW50byBk'
      'YSDDqXBvY2EgMjggYDNjOTZkN2M2Nzg4Nzc5MmFkZGEyMWFhMjkxZWFjNzAyOGY0OTI0Nzk4ZmVmNWNlMDUxOGFmZTUzNTgw'
      'NGFlNjBgIChPUkQ6MjYpLgotIFJlc3Bvc3RhcyBkbyBDb2RleCBubyBjYW5hbCBkZSBjb29yZGVuYcOnw6NvOiBmb3JtYSBk'
      'ZXN0ZSBhdG8gKEItMSksIGNvbWVudMOhcmlvIDU5ODI0MzgyOTU7IG9iamV0byBPUkRFUiAoTy0yKSwgY29tZW50w6FyaW8g'
      'NTk4MjQzODI5NS4KCiMjIDIuIE8gcXVlIGVzdGUgYXRvIGF1dG9yaXphCgoxLiAqKlbDrW5jdWxvIHBvciBESUEgZG8gY29u'
      'dHJhdG8gZGUgY2FwYWNpZGFkZS4qKiBQYXJhIGNhZGEgdW1hIGRhcyBjaW5jbyBzZXNzw7VlcywgbyBjb250cmF0byBkbyBk'
      'aWEgc8OzIMOpIGFjZWl0byBjb20gbyB0ZW1wbGF0ZSBkYXF1ZWxlIGRpYSAobWFwYSBgdGVtcGxhdGVfc2hhc2A7IHNlw6fD'
      'o28gNCkuIFVtIGRpYSBuw6NvIHVzYSBvIHRlbXBsYXRlIGRlIG91dHJvLCBlIHVtIGRpYSBmb3JhIGRhcyBjaW5jbyBuw6Nv'
      'IHRlbSB0ZW1wbGF0ZS4KMi4gKipPYmpldG8gT1JERVIsIHBvbGljeSBlIGVzY29wby4qKiBGaXhhIG8gYG9yZGVyX3NoYWAs'
      'IGEgcG9saWN5ICh2YWxpZGFkZSBkZSDDqXBvY2EsIHJldmFsaWRhZGEgZGlhcmlhbWVudGUgc8OzIHBvciBsZWl0dXJhOiBP'
      'UkQ6MjcpLCBhIMOpcG9jYSwgYSAxwqogc2Vzc8OjbyBlIGFzIGNpbmNvIHNlc3PDtWVzLiBRdWFscXVlciB0cm9jYSBkZSB1'
      'bSBkZWxlcyBhbnVsYSBlc3RlIGF0byBlIGFzIHN1YXMgdHLDqnMgYXByb3Zhw6fDtWVzLgozLiAqKkRlbGVnYcOnw6NvIHBv'
      'ciB0ZW1wbGF0ZSAoT1JEOjE1KS4qKiBDb20gZXN0ZSBhdG8gZSBhIHN1YSBjYWRlaWEgY29tcGxldGEsIGEgRmFibGUgcG9k'
      'ZSBlbWl0aXIgR08gZGVsZWdhZG8gKGBERUxFR0FURURfQUNUX0JgKSBwYXJhIGFzIGZhc2VzIGRlbGVnw6F2ZWlzIOKAlCBm'
      'b250ZXMsIGxpc3RhIGNhdXNhbCwgY29tcG9uZW50ZXMsIHJpc2NvLCBtYW5pZmVzdG8gZG8gcHJvZHV0b3IsIGNhcHR1cmEg'
      'ZGnDoXJpYSBlIHJldmFsaWRhw6fDo28gc29tZW50ZS1sZWl0dXJhIGRhIHBvbGljeS93b3JrZXIg4oCULCBjYWRhIEdPIHB1'
      'YmxpY2FkbyBubyBjYW5hbCBwZWxvIG1lbm9zIDE1IG1pbnV0b3MgYW50ZXMgZG8gaW7DrWNpbyBkYSBqYW5lbGEsIHNvYiB2'
      'ZXRvIGRvIGRvbm8gYXTDqSBvIGRlc3BhY2hvOyBubyBtYW5pZmVzdG8gZG8gcHJvZHV0b3IsIGF0w6kgbyBpbnN0YW50ZSBk'
      'YSB2aXPDo28gZGUgdmV0byBkZSBjYWRhIGphbmVsYSwgY29tIGEgcGFyYWRhIGRvIGNvbnTDqmluZXIgZW0gZXNwZXJhIChP'
      'UkQ6MTcpOgogICAtIG1hbmlmZXN0byBkbyBwcm9kdXRvciAoYGJhcl9tYW5pZmVzdGApOiBwZWxvIHRlbXBsYXRlIGRlIGNh'
      'cGFjaWRhZGUgZG8gZGlhIChzZcOnw6NvIDQpLCBjb20gbyBzZXUgcmVnaXN0cm8gZGUgcHVibGljYcOnw6NvIChPUkQ6MTYp'
      'OwogICAtIGFzIG91dHJhcyBzZWlzOiBwZWxvcyB0ZW1wbGF0ZXMgZGEgc2XDp8OjbyA1LCBkZXJpdmFkb3MgcGVsbyBzY3Jp'
      'cHQgZGEgc2XDp8OjbyA2LCBjb20gYSBsaXN0YSBmZWNoYWRhIGRlIGNhbXBvcyBzdWJzdGl0dcOtdmVpcy4KNC4gKipSZWdy'
      'YXMgZG8gZG9ubyoqIChyZWdpc3RybyBkZSByZWdyYXMgMeKAkzQgZSByb2xsYmFjaywgY29tIGEgZW1lbmRhIGRvIHZldG8p'
      'OiBhIEZhYmxlIMOpIGEgw7puaWNhIGVtaXNzb3JhIGRlIEdPIGluZGl2aWR1YWw7IG8gZG9ubyBjb250cmEtYXNzaW5hIGBi'
      'YXJfbWVyZ2VfZGVwbG95X3JlY2VydGlmeWAsIGBpbnN0YWxsX3JlbGVhc2VgLCBgYWN0aXZhdGVgIGUgYHdpbmRfZG93bl8y'
      'OGA7IGNhcGFjaWRhZGUgNTUwLCBwb3Npw6fDtWVzIGFiZXJ0YXMgcHJpbWVpcm8sIG5vdmFzIGVudHJhZGFzIHBvciBBRFYg'
      'ZGVjcmVzY2VudGUgZSBzw61tYm9sbyBjcmVzY2VudGUgbm8gZW1wYXRlLCBjb3J0ZSBzw7MgbmEgY2F1ZGEgZGFzIG5vdmFz'
      'IChPUkQ6MTQpOyBzZW0gc3ViZmFzZXM7IGByb2xsYmFja19kaXNwb3NpdGlvbmAgYFJFVkFMSURBVEVfVU5DT01NSVRURURf'
      'T05MWWAg4oCUIHJldmFsaWRhIHPDsyB1bWEgZGVyaXZhw6fDo28gZGUgY2FwYWNpZGFkZSBuw6NvIGNvbmZpcm1hZGEsIG51'
      'bmNhIHJlcGV0ZSBpbnN0YWxhw6fDo28sIGNhcHR1cmEsIHNlc3PDo28gcGVyZGlkYSBvdSBlZmVpdG8gZXh0ZXJubzsgYGF1'
      'dG9tYXRpY19yZXRyeWAgZmFsc28uIFVtIHZldG8gZGFkbyBkZXBvaXMgZGUgY29uZmlybWFkYSBhIGFkbWlzc8OjbyBkbyBk'
      'aWEgbsOjbyBkZXNmYXogZXNzYSBhZG1pc3PDo28sIHF1ZSB2YWxlIGF0w6kgbyB2w61uY3VsbyBkbyBkaWEgc2VndWludGUg'
      'KGVtZW5kYSBgNTc4NjZhYTNmYjJlOGYxNjNmMjFlYjk2ZjRmM2RlZDUxODNkOTFiOTQxNTU2NTkyYmJhODI5MDcxMWRmZTUx'
      'ZWApOyBlbGUgdmFsZSBwYXJhIG8gZGlhIGludGVpcm86IG5lbmh1bWEgamFuZWxhIHBvc3RlcmlvciDDqSBkZXNwYWNoYWRh'
      'IGUgYSBzZXNzw6NvIHNlZ3VlIHNlbSBtYW5pZmVzdG8gZSBzZW0gYmFycmFzIChPUkQ6MTcpLiBOYSDDqXBvY2EgMDMsIGB3'
      'aW5kX2Rvd25fMjhgIMOpIG8gcmVnaXN0cm8gZGUgZW5jZXJyYW1lbnRvIGRhIMOpcG9jYSAyOCAoT1JEOjI2KTogbmVuaHVt'
      'YSBhw6fDo28gZGUgd2luZC1kb3duIMOpIGF1dG9yaXphZGEuCgojIyAzLiBPIHF1ZSBlc3RlIGF0byBOw4NPIGF1dG9yaXph'
      'CgotICoqTmVuaHVtYSBlc2NyaXRhIG5vIHNlcnZpZG9yIHBvciBzaS4qKiBUb2RhIGVzY3JpdGEgY29udGludWEgY29tIG8g'
      'c2V1IHBlZGlkbyBkZSB1c28gw7puaWNvLCBvIEdPIGluZGl2aWR1YWwgcG9yIGhhc2ggZSBhIGFzc2luYXR1cmEgZG8gZG9u'
      'byBxdWUgYSBvcmRlbSBlIGFzIGRlY2lzw7VlcyBkbyBkb25vIGV4aWdlbTsgbmFkYSBhcXVpIGRpc3BlbnNhIGEgYXV0b3Jp'
      'ZGFkZSBkZSBwcmVwYXJhw6fDo28gKEExKSBuZW0gYSBkYXMgY2luY28gc2Vzc8O1ZXMgKEEyKSwgcXVlIGVudW1lcmFtIG9w'
      'ZXJhw6fDtWVzLCBkaWFzIGUgamFuZWxhcyAoT1JEOjIyKS4KLSBgaW5zdGFsbF9yZWxlYXNlYCwgYHJlYWRiYWNrYCBlIGBh'
      'Y3RpdmF0ZWA6IHPDsyBuYSAxwqogc2Vzc8Ojbywgc29iIEdPIGluZGl2aWR1YWwgZSwgcGFyYSBpbnN0YWxhw6fDo28gZSBh'
      'dGl2YcOnw6NvLCBjb250cmEtYXNzaW5hdHVyYSBkbyBkb25vIChPUkQ6NywgT1JEOjE5LCBPUkQ6MjIpLiBFc3RlIGF0byBu'
      'w6NvIG9zIGRlbGVnYS4KLSBgYWRtaXNzaW9uYCwgYHF1b3RlX3JlZnJlc2hgIGUgYHF1b3RlX2NhcHR1cmVgOiBzw7MgcG9y'
      'IEdPIGluZGl2aWR1YWwgZGEgRmFibGUgcG9yIHNlc3PDo28sIG51bmNhIHBvciBkZWxlZ2HDp8OjbyAoT1JEOjE2KS4gTyB0'
      'ZW1wbGF0ZSBkZSBjYXBhY2lkYWRlIHPDsyBsaGVzIGTDoSBvIHbDrW5jdWxvIGRvIGNvbnRyYXRvLgotIE1vbnRhZ2VtIGUg'
      'aGFiaWxpdGHDp8OjbyBkYSBjYXBhY2lkYWRlIG5vIHdvcmtlciBkbyBjb21wb3NlLCBsYW7Dp2FtZW50byBlIHJlbGFuw6dh'
      'bWVudG8gZG8gbGVpdG9yLCBvcGVyYcOnw7VlcyBkbyBzdXBlcnZpc29yIGRvIHByb2R1dG9yLCByZWluw61jaW9zLCBwaW5v'
      'IGRlIG1hbnV0ZW7Dp8OjbywgbWVyZ2UgZSBkZXBsb3kgKE9SRDoxOOKAkzIzLCBPUkQ6MzEpLgotIFNleHRhIHNlc3PDo28s'
      'IG91dHJhIMOpcG9jYSwgb3V0cmEgcmVsZWFzZSwgb3V0cmEgcG9saWN5LCBvdXRybyBvYmpldG8gT1JERVIsIG91dHJvIHRl'
      'bXBsYXRlLgotIFJldHJ5IGltcGzDrWNpdG8gb3Ugbm92YSB0ZW50YXRpdmEgZm9yYSBkYXMgZXhjZcOnw7VlcyBleHByZXNz'
      'YXMgZGEgT1JEOjMzOyBjb21wZW5zYcOnw6NvIGRlIHNlc3PDo28gcGVyZGlkYS4KLSBPcmRlbSByZWFsIG91IG1vdmltZW50'
      'YcOnw6NvIGRlIGRpbmhlaXJvOyBleGNsdXPDo28gb3UgbW92aW1lbnRhw6fDo28gZGUgZGFkb3MgKE9SRDozMykuCi0gQ8Oz'
      'ZGlnbyBmaW5hbCBkYXMgZmFzZXMgZGnDoXJpYXM6IG8gcGFjb3RlIG9wZXJhY2lvbmFsIGRlIGNhZGEgb3BlcmHDp8OjbyDD'
      'qSBjYW1wbyBzdWJzdGl0dcOtdmVsIGRhIG9yZGVtIGRlcml2YWRhIChgb3BlcmF0aW9uX3BheWxvYWRfc2hhMjU2YCksIHJl'
      'dmlzYWRvIHBvciBoYXNoIHBlbG8gQ29kZXggZSBwZWxhIEZhYmxlIG5vIEdPIHF1ZSBvIHVzYSAoT1JEOjMxKSBlIGFzc2lu'
      'YWRvIHBlbG8gZG9ubyBjb21vIGEgZGVjaXPDo28gZW0gdmlnb3IgZXhpZ2U6IHBvciBleGVjdcOnw6NvIChgOTBmYzQ5YWY5'
      'ZGI5ZjVhMDZlYmFmZTNlMWQ4OTZmOTgwZDRjYmQzNTVmM2RhYjU0N2ZmZWRjMjUwMTg3MTk5ZWApIG91LCBzZSBvIENvZGV4'
      'IHRpdmVyIGVzY3JpdG8gcXVlIGzDqiBhIGVtZW5kYSBgMTk4NDA5NDJhMzQxMTE3NmFjZDMxNTNmY2EzNjAzNmE3NmVlMTYy'
      'ZWI0YmFjZGNkM2E0NmYwYWYwNWY1OGJiMmAgZG8gbWVzbW8gamVpdG8sIHVtYSB2ZXogcG9yIHByb2dyYW1hIGRpw6FyaW8u'
      'IE9zIHRlbXBsYXRlcyBkYSBzZcOnw6NvIDUgY29uZ2VsYW0gYSBpbnRlcmZhY2UgKG5vdGEgSzkpLCBuw6NvIG8gY8OzZGln'
      'by4KCiMjIDQuIFRlbXBsYXRlcyBkZSBjYXBhY2lkYWRlIOKAlCB1bSB2w61uY3VsbyBwb3IgRElBCgpPIHRlbXBsYXRlIGRv'
      'IGNvbnRyYXRvIGRlIGNhZGEgZGlhIMOpIG8gb2JqZXRvIGB7b3duZXJfc2hhLCBlcG9jaCwgZGF5LCBwaGFzZXMsIHJ1bGV9'
      'YCBjb20gYHBoYXNlc2AgPSBgYWRtaXNzaW9uYCwgYGJhcl9tYW5pZmVzdGAsIGBxdW90ZV9yZWZyZXNoYCwgYHF1b3RlX2Nh'
      'cHR1cmVgIGUgYHJ1bGVgID0gYE9QRU5fRklSU1RfVEhFTl9FWElTVElOR19DQVVTQUxfT1JERVJfVjFfUFJPUE9TRURgIChg'
      'cjJkMl92Ml9jYXBhY2l0eV9hdXRob3JpdHkucHk6NDQtNDlgKS4gTyBjw7NkaWdvIGRhIHJlbGVhc2UgZXhpZ2UgcXVlIG8g'
      'ZGlnZXN0IGRlc3NlIG9iamV0byBzZWphIG8gZGVzdGUgbWFwYSBwYXJhIG8gZGlhIChgcjJkMl92Ml9kb2N1bWVudF9hdXRo'
      'b3JpdHkucHk6MTA3LTExNGApIGUgcXVlIGEgZW50cmFkYSBkbyBtYXBhIHRlbmhhIHPDsyBhcXVlbGUgZGlhIChgOjk5LTEw'
      'NGApLiBHZXJhZG9zIHBlbGEgZmVycmFtZW50YSBgY2FwYWNpdHlfZGF5X2RvY3VtZW50cy5weSB0ZW1wbGF0ZXNgIChTSEEt'
      'MjU2IGA4ODhhNDhlNjY1NGFmZjkwZTJmMzA1YjQxMGVhNmM1NjE0NDg1ZTVhYzc3ODM1NGJhNzIxYjc5MGJmZWFkMTgzYCkg'
      'c29icmUgbyBjw7NkaWdvIGRlc3RhIHJlbGVhc2UsIGEgcGFydGlyIGRvIG9iamV0byBPUkRFUjsgY29uanVudG8gZGUgYXJx'
      'dWl2b3MgYDYwOWE0ZDU1ODg4Nzk5OGU2Zjc1OTcyYjNlMjE5YzNhNzZkY2NkMmJiNzVjNDM1ZTNkOTZmN2IzNmViYmNiMjNg'
      'OyByZWNhbGN1bGFkb3MgcGVsbyBjw7NkaWdvIGRhIHJlbGVhc2UgYW50ZXMgZGVzdGUgYXJxdWl2byBzZXIgZXNjcml0by4K'
      'CnwgU2Vzc8OjbyB8IFNIQS0yNTYgZG8gdGVtcGxhdGUgZG8gY29udHJhdG8gfAp8LS0tfC0tLXwKfCAyMDI2LTEwLTA1IHwg'
      'YGQwYzY4Mjg2N2I1Y2RjYTZmNTJhNGU5YTg4ZGJjN2RjOTNlYjdmYjgxOTI4Y2M1MmIwNTk5ODlhZmM2NjIyNTVgIHwKfCAy'
      'MDI2LTEwLTA2IHwgYDg1ZWY0NjBhYWU2OGRlMDQ5YWU3NTgxMGFiYmYyYmQwNTMxYzA4ZTY1ZTg0ZjEyMzNmMDM4ODBmMjMz'
      'ZDU1ZDNgIHwKfCAyMDI2LTEwLTA3IHwgYDAwMmI0N2Y2ZGFmMjBkNDQ1NTE0Njg0ZDQ1ZjQ1NTk5NTQ4Y2Q1ZjQ5ODQyNGEw'
      'NTVjN2Q0NGQ0YTRmZTlmNjBgIHwKfCAyMDI2LTEwLTA4IHwgYDA5ODBiMmEwMmJhN2MwNzc0MDIwNDIwNWU0ZGZkOGI4ZTkx'
      'ODZhYTdjOGY4ODNiZTYxNzIxNWZkMTlmN2E5MTZgIHwKfCAyMDI2LTEwLTA5IHwgYDhhODUyYWFjMDY5MzdmYjZhZTE4Mzcz'
      'YzUzNWEwZWIxODBlOTQ5ZjM1ZDBmMDU2YmI5ZmEyYzkxMzJmY2JkOTRgIHwKCmB0ZW1wbGF0ZV9zZXRfc2hhYCA9IGA2ODcw'
      'NWIzYmEzMjY5ZGRkYWIzNzVjYmZmYjllODQ0NTNmNTQyYWZjYTMyOWEzODU0YmM1Y2I5MjNiZDJkYzVmYCAoZGlnZXN0IGRh'
      'IGxpc3RhIGRlIGNpbmNvIGVudHJhZGFzKS4KCiMjIDUuIFRlbXBsYXRlcyBkYXMgb3JkZW5zIGRpw6FyaWFzIGRhcyBzZWlz'
      'IGZhc2VzIGRlbGVnYWRhcyBwb3IgdGVtcGxhdGUgKE9SRDoxNSwgT1JEOjM3KQoKQ2FkYSB0ZW1wbGF0ZSDDqSB1bWEgbGlu'
      'aGEgZGUgSlNPTiBjYW7DtG5pY28gKGNoYXZlcyBvcmRlbmFkYXMsIHNlcGFyYWRvcmVzIGAsYCBlIGA6YCwgc8OzIEFTQ0lJ'
      'KSwgbG9nbyBkZXBvaXMgZG8gbWFyY2Fkb3IgZGEgZmFzZTsgbyBTSEEtMjU2IGRvcyBieXRlcyBkYSBsaW5oYSBlc3TDoSBp'
      'bmRpY2Fkby4gQ2FtcG9zIGZpeG9zOiBlc3F1ZW1hLCBmYXNlLCBtb2RvIGBERUxFR0FURURfQUNUX0JgLCBlbWlzc29yYSBG'
      'QUJMRSwgZXNjb3BvIGRhIGZhc2UsIGNsYXNzZSBkZSBqYW5lbGEsIHVzbyDDum5pY28gY29tIGEgY2hhdmUgYGF0dGVtcHRf'
      'a2V5YCwgYXMgdmFnYXMgYFBSSU1BUllgIGUgYFNQQVJFYCwgc2VtIHJldHJ5LCB2ZXRvIGRvIGRvbm8gcGVsYSByZXRpcmFk'
      'YSBkbyBkZXNwYWNobywgYXZpc28gbcOtbmltbyBkZSA5MDAgc2VndW5kb3MsIGphbmVsYSBudW0gc8OzIGRpYSBVVEMgZSBk'
      'ZSBubyBtw6F4aW1vIDM2MDAgc2VndW5kb3MgbnVtYSBsZWl0dXJhIGUgOTAwIG51bWEgZXNjcml0YSwgbyBtw61uaW1vIGRl'
      'IHJlY2lib3MgZGUgZW50cmFkYSBkYSBmYXNlLCBhIGxpc3RhIGZlY2hhZGEgZGFzIG9wZXJhw6fDtWVzIGRhIGZhc2UgY29t'
      'IG8gdGlwbyBkZSBjYWRhIHVtYSAoYFJFQURgIG91IGBXUklURWApIGUgbyBTSEEtMjU2IGRhIG5vdGEgSzkgZGUgb25kZSBl'
      'bGEgdmVtLCDDqXBvY2EsIDHCqiBzZXNzw6NvLCBhcyBjaW5jbyBzZXNzw7VlcywgYXMgdHLDqnMgIm9yZGVucyIgKGhhc2gg'
      'ZG8gYXJxdWl2byBkYSBvcmRlbSwgY29uc3RhbnRlIGRvIGNvbnRyb2xhZG9yIGUgYG9yZGVyX3NoYWAgZGVzdGUgYXRvKSwg'
      'cG9saWN5LCByZWxlYXNlLCBwYWNvdGUsIHJldmlzw6NvIGUgYSB2YWxpZGFkZSBkYSBwb2xpY3kuIENhbXBvcyBgVU5CT1VO'
      'RF8qYDogYSBsaXN0YSBmZWNoYWRhIGRhIHNlw6fDo28gNi4gQ2FtcG9zIGBERVJJVkVEXypgOiBwcmVlbmNoaWRvcyBwZWxv'
      'IHNjcmlwdCBjb20gbyBTSEEtMjU2IGRlc3RlIGFycXVpdm8sIG8gZG8gdGVtcGxhdGUgZSBhIGNoYXZlIGRlIHVzbyDDum5p'
      'Y28uIEVzY29wb3M6IGZvbnRlcyBgUE9TVF9BRE1JU1NJT05fUkVBRF9QUk9WSURFUlNfQU5EX1JFU1RSSUNURURfREFUQUJB'
      'U0VgIGUgcmlzY28gYFBPU1RfQURNSVNTSU9OX0FSVElGQUNUX09OTFlgIChPUkQ6MTMpOyBjb21wb25lbnRlcyBkYSBsaXN0'
      'YSBjb25maXJtYWRhIChPUkQ6MTIpOyBjYXB0dXJhIGRpw6FyaWEgZGlzdGludGEgZGUgYHF1b3RlX2NhcHR1cmVgIChPUkQ6'
      'MTYpOyByZXZhbGlkYcOnw6NvIHPDsyBwb3IgbGVpdHVyYSAoT1JEOjE1LCBPUkQ6MjcpLiBgUE9TVF9BRE1JU1NJT05gIMOp'
      'IGEgYWRtaXNzw6NvIChjb25maXJtYcOnw6NvKSBkYSBsaXN0YSBjYXVzYWwgZG8gZGlhLCBuw6NvIGEgYWRtaXNzw6NvIGRl'
      'IGNhcGFjaWRhZGUsIHF1ZSDDqSBkZSBtYW5ow6M6IGZvbnRlcywgY29tcG9uZW50ZXMgZSByaXNjbyByb2RhbSBkZXBvaXMg'
      'ZGVsYSwgZSBhIG9yZGVtIGRlcml2YWRhIGRlc3NhcyB0csOqcyBmYXNlcyBub21laWEgcGVsbyBtZW5vcyB1bSByZWNpYm8g'
      'ZGUgZW50cmFkYSAobyBkYSBjb25maXJtYcOnw6NvIG91IHVtIHBvc3RlcmlvcikuCgojIyMgc291cmNlcyDigJQgU0hBLTI1'
      'NiBgZDk2ZTA1ODM1Yjk1MzdiN2Q1MTdkYWI1OTVkMTRmZjlkOTE5ZTgwNmRmOTdiN2M0OTQyZjZlZTdlMDE3YzQ5OGAKCjwh'
      'LS0gUjJEMi1FUE9DSDAzLVBIQVNFLVRFTVBMQVRFOnNvdXJjZXMgLS0+CmBgYGpzb24KeyJhY3RfYl9vcmRlcl9zaGEiOiI1'
      'MTg2Mjc5MTk3NTRmNzk1ZmY1NTFjOWQ4MzNhM2IxMDAwZmI5MzBiNTU1ZGY2NDdlN2UwMGUyYjE5ZTc3NWZlIiwiYXR0ZW1w'
      'dF9rZXkiOiJERVJJVkVEX0FUVEVNUFRfS0VZIiwiYXV0aG9yaXplZF9zZXNzaW9ucyI6WyIyMDI2LTEwLTA1IiwiMjAyNi0x'
      'MC0wNiIsIjIwMjYtMTAtMDciLCIyMDI2LTEwLTA4IiwiMjAyNi0xMC0wOSJdLCJhdXRvbWF0aWNfcmV0cnkiOmZhbHNlLCJj'
      'b2RlX3JldmlzaW9uIjoiZGQ0ZWM0YmI4ZGFiNGQ4YjAzNzJiMGY5ZWFiYzkwYmY2NDQzZTg1OCIsImRheSI6IlVOQk9VTkRf'
      'REFZIiwiZG9jdW1lbnRfb3JkZXJfc2hhIjoiMWE1MjUzYmYyM2Y1MDA2MjI0Yjc5NTI3ZGEwNjY5NzY0NmMzNGM2ZjVhM2E0'
      'ZjgyMGFmNWRhMmIxM2Q3YTExOCIsImVwb2NoIjoiUjJEMi1WMi1TSEFET1ctMjAyNi0xMC0wNSIsImZpcnN0X3Nlc3Npb24i'
      'OiIyMDI2LTEwLTA1IiwiZml2ZV9zZXNzaW9uX2F1dGhvcml0eV9zaGEyNTYiOiJVTkJPVU5EX0ZJVkVfU0VTU0lPTl9BVVRI'
      'T1JJVFlfU0hBMjU2IiwiaW5wdXRfcmVjZWlwdF9zaGEyNTZzIjoiVU5CT1VORF9JTlBVVF9SRUNFSVBUX1NIQTI1NlMiLCJp'
      'c3N1ZXIiOiJGQUJMRSIsIms5X2ludGVyZmFjZV9ub3RlX3NoYTI1NiI6ImFiNTE1OWJlYTM0YjMyMzkzNzllODdjMjUwMGQz'
      'ODNmMDc3N2NjNjE4NjYxODQzNWJhMGVhOWY2MWUzZDU5NmMiLCJtaW5faW5wdXRfcmVjZWlwdHMiOjEsIm1vZGUiOiJERUxF'
      'R0FURURfQUNUX0IiLCJub3RfYWZ0ZXIiOiJVTkJPVU5EX05PVF9BRlRFUiIsIm5vdF9iZWZvcmUiOiJVTkJPVU5EX05PVF9C'
      'RUZPUkUiLCJvcGVyYXRpb24iOiJVTkJPVU5EX09QRVJBVElPTiIsIm9wZXJhdGlvbl9wYXlsb2FkX3NoYTI1NiI6IlVOQk9V'
      'TkRfT1BFUkFUSU9OX1BBWUxPQURfU0hBMjU2Iiwib3BlcmF0aW9ucyI6eyJzb3VyY2VzX2xhdW5jaCI6IldSSVRFIiwic291'
      'cmNlc19yZXN1bHQiOiJSRUFEIn0sIm93bmVyX3BheWxvYWRfc2lnbmF0dXJlX3NoYTI1NiI6IlVOQk9VTkRfT1dORVJfUEFZ'
      'TE9BRF9TSUdOQVRVUkVfU0hBMjU2Iiwib3duZXJfdmV0byI6IldJVEhEUkFXQUxfQkVGT1JFX0RJU1BBVENIIiwicGFja2Fn'
      'ZV9zaGEyNTYiOiJiNWNlNTI3YTU0NGNhMGViMDhmMDcxOGQ4MzU0NmQ3YjQ2ZjllOTc3NGJlOGU0MzUxYWZjZTIxMmU3MmJk'
      'Yjg0IiwicGhhc2UiOiJzb3VyY2VzIiwicG9saWN5X3NoYTI1NiI6ImQyZmIzZTc3NGMxZGY3YjRhODBmNjcwZDFiZGZkYjNm'
      'MjNmOTBiMjIxZDdiZjQ1YTdjZWQ5NjE2NGJlNzM4ZmUiLCJwb2xpY3lfdmFsaWRfZnJvbSI6IjIwMjYtMTAtMDVUMDA6MDA6'
      'MDBaIiwicG9saWN5X3ZhbGlkX3VudGlsIjoiMjAyNi0xMC0wOVQyMDowMDowMFoiLCJwdWJsaWNhdGlvbl9ub3RpY2Vfc2Vj'
      'b25kc19taW4iOjkwMCwicHVibGlzaGVkX2F0IjoiVU5CT1VORF9QVUJMSVNIRURfQVQiLCJyZWxlYXNlX3NoYTI1NiI6ImZj'
      'MmY2NGVhMjUyZjk5OTZiYTYyY2Q4YmIxMDQxMWVhMGNiYzNhMzUxYzE1Yjg2MTJkZTg4MzkwY2NiZGNhYTEiLCJydW50aW1l'
      'X29yZGVyX3NoYSI6IjFhZDhiOTBjZmFiNjUxODIzZWI2NzdiODMwYTAwNzhkMTBjMTc0NDc1NzVjOGQ4MTNjMzg4M2E3MTg1'
      'NzlkOGUiLCJzY2hlbWEiOiJSMkQyX1YyX0VQT0NIMDNfREVMRUdBVEVEX1BIQVNFX09SREVSX1YyIiwic2NvcGUiOiJQT1NU'
      'X0FETUlTU0lPTl9SRUFEX1BST1ZJREVSU19BTkRfUkVTVFJJQ1RFRF9EQVRBQkFTRSIsInNpZ25lZF9hY3RfYl9zaGEyNTYi'
      'OiJERVJJVkVEX1NJR05FRF9BQ1RfQl9TSEEyNTYiLCJzaW5nbGVfdXNlIjp0cnVlLCJzaW5nbGVfdXNlX2tleSI6ImF0dGVt'
      'cHRfa2V5Iiwic2xvdCI6IlVOQk9VTkRfU0xPVCIsInNsb3RzIjpbIlBSSU1BUlkiLCJTUEFSRSJdLCJ0ZW1wbGF0ZV9zaGEy'
      'NTYiOiJERVJJVkVEX1RFTVBMQVRFX1NIQTI1NiIsIndpbmRvd19jbGFzcyI6IkJFRk9SRV9PUEVOIiwid2luZG93X21heF9z'
      'ZWNvbmRzIjp7IlJFQUQiOjM2MDAsIldSSVRFIjo5MDB9LCJ3aW5kb3dfc2luZ2xlX3V0Y19kYXkiOnRydWV9CmBgYAoKIyMj'
      'IGNhdXNhbF9saXN0IOKAlCBTSEEtMjU2IGA3Y2Q5OWVmZTljZWRhOWM1YTI5ODA5NGViZWU3NjdkNDA3MmVkYTI2ZDRjYzg4'
      'YzM1ODMzOWNkNWZmMmIwMjAzYAoKPCEtLSBSMkQyLUVQT0NIMDMtUEhBU0UtVEVNUExBVEU6Y2F1c2FsX2xpc3QgLS0+CmBg'
      'YGpzb24KeyJhY3RfYl9vcmRlcl9zaGEiOiI1MTg2Mjc5MTk3NTRmNzk1ZmY1NTFjOWQ4MzNhM2IxMDAwZmI5MzBiNTU1ZGY2'
      'NDdlN2UwMGUyYjE5ZTc3NWZlIiwiYXR0ZW1wdF9rZXkiOiJERVJJVkVEX0FUVEVNUFRfS0VZIiwiYXV0aG9yaXplZF9zZXNz'
      'aW9ucyI6WyIyMDI2LTEwLTA1IiwiMjAyNi0xMC0wNiIsIjIwMjYtMTAtMDciLCIyMDI2LTEwLTA4IiwiMjAyNi0xMC0wOSJd'
      'LCJhdXRvbWF0aWNfcmV0cnkiOmZhbHNlLCJjb2RlX3JldmlzaW9uIjoiZGQ0ZWM0YmI4ZGFiNGQ4YjAzNzJiMGY5ZWFiYzkw'
      'YmY2NDQzZTg1OCIsImRheSI6IlVOQk9VTkRfREFZIiwiZG9jdW1lbnRfb3JkZXJfc2hhIjoiMWE1MjUzYmYyM2Y1MDA2MjI0'
      'Yjc5NTI3ZGEwNjY5NzY0NmMzNGM2ZjVhM2E0ZjgyMGFmNWRhMmIxM2Q3YTExOCIsImVwb2NoIjoiUjJEMi1WMi1TSEFET1ct'
      'MjAyNi0xMC0wNSIsImZpcnN0X3Nlc3Npb24iOiIyMDI2LTEwLTA1IiwiZml2ZV9zZXNzaW9uX2F1dGhvcml0eV9zaGEyNTYi'
      'OiJVTkJPVU5EX0ZJVkVfU0VTU0lPTl9BVVRIT1JJVFlfU0hBMjU2IiwiaW5wdXRfcmVjZWlwdF9zaGEyNTZzIjoiVU5CT1VO'
      'RF9JTlBVVF9SRUNFSVBUX1NIQTI1NlMiLCJpc3N1ZXIiOiJGQUJMRSIsIms5X2ludGVyZmFjZV9ub3RlX3NoYTI1NiI6ImFi'
      'NTE1OWJlYTM0YjMyMzkzNzllODdjMjUwMGQzODNmMDc3N2NjNjE4NjYxODQzNWJhMGVhOWY2MWUzZDU5NmMiLCJtaW5faW5w'
      'dXRfcmVjZWlwdHMiOjAsIm1vZGUiOiJERUxFR0FURURfQUNUX0IiLCJub3RfYWZ0ZXIiOiJVTkJPVU5EX05PVF9BRlRFUiIs'
      'Im5vdF9iZWZvcmUiOiJVTkJPVU5EX05PVF9CRUZPUkUiLCJvcGVyYXRpb24iOiJVTkJPVU5EX09QRVJBVElPTiIsIm9wZXJh'
      'dGlvbl9wYXlsb2FkX3NoYTI1NiI6IlVOQk9VTkRfT1BFUkFUSU9OX1BBWUxPQURfU0hBMjU2Iiwib3BlcmF0aW9ucyI6eyJj'
      'b2xsZWN0X2xhdW5jaCI6IldSSVRFIiwiY29sbGVjdF9yZXN1bHQiOiJSRUFEIiwiY29tbWl0X2xhdW5jaCI6IldSSVRFIiwi'
      'Y29tbWl0X3Jlc3VsdCI6IlJFQUQiLCJwdWJsaXNoX2xhdW5jaCI6IldSSVRFIiwicHVibGlzaF9yZXN1bHQiOiJSRUFEIiwi'
      'cmVhZGluZXNzX3Byb2JlIjoiUkVBRCIsInJlYWRpbmVzc19yZWNoZWNrIjoiUkVBRCJ9LCJvd25lcl9wYXlsb2FkX3NpZ25h'
      'dHVyZV9zaGEyNTYiOiJVTkJPVU5EX09XTkVSX1BBWUxPQURfU0lHTkFUVVJFX1NIQTI1NiIsIm93bmVyX3ZldG8iOiJXSVRI'
      'RFJBV0FMX0JFRk9SRV9ESVNQQVRDSCIsInBhY2thZ2Vfc2hhMjU2IjoiYjVjZTUyN2E1NDRjYTBlYjA4ZjA3MThkODM1NDZk'
      'N2I0NmY5ZTk3NzRiZThlNDM1MWFmY2UyMTJlNzJiZGI4NCIsInBoYXNlIjoiY2F1c2FsX2xpc3QiLCJwb2xpY3lfc2hhMjU2'
      'IjoiZDJmYjNlNzc0YzFkZjdiNGE4MGY2NzBkMWJkZmRiM2YyM2Y5MGIyMjFkN2JmNDVhN2NlZDk2MTY0YmU3MzhmZSIsInBv'
      'bGljeV92YWxpZF9mcm9tIjoiMjAyNi0xMC0wNVQwMDowMDowMFoiLCJwb2xpY3lfdmFsaWRfdW50aWwiOiIyMDI2LTEwLTA5'
      'VDIwOjAwOjAwWiIsInB1YmxpY2F0aW9uX25vdGljZV9zZWNvbmRzX21pbiI6OTAwLCJwdWJsaXNoZWRfYXQiOiJVTkJPVU5E'
      'X1BVQkxJU0hFRF9BVCIsInJlbGVhc2Vfc2hhMjU2IjoiZmMyZjY0ZWEyNTJmOTk5NmJhNjJjZDhiYjEwNDExZWEwY2JjM2Ez'
      'NTFjMTViODYxMmRlODgzOTBjY2JkY2FhMSIsInJ1bnRpbWVfb3JkZXJfc2hhIjoiMWFkOGI5MGNmYWI2NTE4MjNlYjY3N2I4'
      'MzBhMDA3OGQxMGMxNzQ0NzU3NWM4ZDgxM2MzODgzYTcxODU3OWQ4ZSIsInNjaGVtYSI6IlIyRDJfVjJfRVBPQ0gwM19ERUxF'
      'R0FURURfUEhBU0VfT1JERVJfVjIiLCJzY29wZSI6IkNBVVNBTF9MSVNUX0NPTU1JVF9BTkRfUFVCTElDQVRJT04iLCJzaWdu'
      'ZWRfYWN0X2Jfc2hhMjU2IjoiREVSSVZFRF9TSUdORURfQUNUX0JfU0hBMjU2Iiwic2luZ2xlX3VzZSI6dHJ1ZSwic2luZ2xl'
      'X3VzZV9rZXkiOiJhdHRlbXB0X2tleSIsInNsb3QiOiJVTkJPVU5EX1NMT1QiLCJzbG90cyI6WyJQUklNQVJZIiwiU1BBUkUi'
      'XSwidGVtcGxhdGVfc2hhMjU2IjoiREVSSVZFRF9URU1QTEFURV9TSEEyNTYiLCJ3aW5kb3dfY2xhc3MiOiJCRUZPUkVfT1BF'
      'TiIsIndpbmRvd19tYXhfc2Vjb25kcyI6eyJSRUFEIjozNjAwLCJXUklURSI6OTAwfSwid2luZG93X3NpbmdsZV91dGNfZGF5'
      'Ijp0cnVlfQpgYGAKCiMjIyBjb21wb25lbnRzIOKAlCBTSEEtMjU2IGBhZDQ4NTcwYzBhNjJmMzc5OTVhOGRkOGJhZTlmZmQ4'
      'NjEwNzRlYjg0YzhiMGVjOTZjMGY1MDcxMjQ3Mjg2Yzg0YAoKPCEtLSBSMkQyLUVQT0NIMDMtUEhBU0UtVEVNUExBVEU6Y29t'
      'cG9uZW50cyAtLT4KYGBganNvbgp7ImFjdF9iX29yZGVyX3NoYSI6IjUxODYyNzkxOTc1NGY3OTVmZjU1MWM5ZDgzM2EzYjEw'
      'MDBmYjkzMGI1NTVkZjY0N2U3ZTAwZTJiMTllNzc1ZmUiLCJhdHRlbXB0X2tleSI6IkRFUklWRURfQVRURU1QVF9LRVkiLCJh'
      'dXRob3JpemVkX3Nlc3Npb25zIjpbIjIwMjYtMTAtMDUiLCIyMDI2LTEwLTA2IiwiMjAyNi0xMC0wNyIsIjIwMjYtMTAtMDgi'
      'LCIyMDI2LTEwLTA5Il0sImF1dG9tYXRpY19yZXRyeSI6ZmFsc2UsImNvZGVfcmV2aXNpb24iOiJkZDRlYzRiYjhkYWI0ZDhi'
      'MDM3MmIwZjllYWJjOTBiZjY0NDNlODU4IiwiZGF5IjoiVU5CT1VORF9EQVkiLCJkb2N1bWVudF9vcmRlcl9zaGEiOiIxYTUy'
      'NTNiZjIzZjUwMDYyMjRiNzk1MjdkYTA2Njk3NjQ2YzM0YzZmNWEzYTRmODIwYWY1ZGEyYjEzZDdhMTE4IiwiZXBvY2giOiJS'
      'MkQyLVYyLVNIQURPVy0yMDI2LTEwLTA1IiwiZmlyc3Rfc2Vzc2lvbiI6IjIwMjYtMTAtMDUiLCJmaXZlX3Nlc3Npb25fYXV0'
      'aG9yaXR5X3NoYTI1NiI6IlVOQk9VTkRfRklWRV9TRVNTSU9OX0FVVEhPUklUWV9TSEEyNTYiLCJpbnB1dF9yZWNlaXB0X3No'
      'YTI1NnMiOiJVTkJPVU5EX0lOUFVUX1JFQ0VJUFRfU0hBMjU2UyIsImlzc3VlciI6IkZBQkxFIiwiazlfaW50ZXJmYWNlX25v'
      'dGVfc2hhMjU2IjoiYWI1MTU5YmVhMzRiMzIzOTM3OWU4N2MyNTAwZDM4M2YwNzc3Y2M2MTg2NjE4NDM1YmEwZWE5ZjYxZTNk'
      'NTk2YyIsIm1pbl9pbnB1dF9yZWNlaXB0cyI6MSwibW9kZSI6IkRFTEVHQVRFRF9BQ1RfQiIsIm5vdF9hZnRlciI6IlVOQk9V'
      'TkRfTk9UX0FGVEVSIiwibm90X2JlZm9yZSI6IlVOQk9VTkRfTk9UX0JFRk9SRSIsIm9wZXJhdGlvbiI6IlVOQk9VTkRfT1BF'
      'UkFUSU9OIiwib3BlcmF0aW9uX3BheWxvYWRfc2hhMjU2IjoiVU5CT1VORF9PUEVSQVRJT05fUEFZTE9BRF9TSEEyNTYiLCJv'
      'cGVyYXRpb25zIjp7ImNvbXBvbmVudHNfbGF1bmNoIjoiV1JJVEUiLCJjb21wb25lbnRzX3Jlc3VsdCI6IlJFQUQifSwib3du'
      'ZXJfcGF5bG9hZF9zaWduYXR1cmVfc2hhMjU2IjoiVU5CT1VORF9PV05FUl9QQVlMT0FEX1NJR05BVFVSRV9TSEEyNTYiLCJv'
      'd25lcl92ZXRvIjoiV0lUSERSQVdBTF9CRUZPUkVfRElTUEFUQ0giLCJwYWNrYWdlX3NoYTI1NiI6ImI1Y2U1MjdhNTQ0Y2Ew'
      'ZWIwOGYwNzE4ZDgzNTQ2ZDdiNDZmOWU5Nzc0YmU4ZTQzNTFhZmNlMjEyZTcyYmRiODQiLCJwaGFzZSI6ImNvbXBvbmVudHMi'
      'LCJwb2xpY3lfc2hhMjU2IjoiZDJmYjNlNzc0YzFkZjdiNGE4MGY2NzBkMWJkZmRiM2YyM2Y5MGIyMjFkN2JmNDVhN2NlZDk2'
      'MTY0YmU3MzhmZSIsInBvbGljeV92YWxpZF9mcm9tIjoiMjAyNi0xMC0wNVQwMDowMDowMFoiLCJwb2xpY3lfdmFsaWRfdW50'
      'aWwiOiIyMDI2LTEwLTA5VDIwOjAwOjAwWiIsInB1YmxpY2F0aW9uX25vdGljZV9zZWNvbmRzX21pbiI6OTAwLCJwdWJsaXNo'
      'ZWRfYXQiOiJVTkJPVU5EX1BVQkxJU0hFRF9BVCIsInJlbGVhc2Vfc2hhMjU2IjoiZmMyZjY0ZWEyNTJmOTk5NmJhNjJjZDhi'
      'YjEwNDExZWEwY2JjM2EzNTFjMTViODYxMmRlODgzOTBjY2JkY2FhMSIsInJ1bnRpbWVfb3JkZXJfc2hhIjoiMWFkOGI5MGNm'
      'YWI2NTE4MjNlYjY3N2I4MzBhMDA3OGQxMGMxNzQ0NzU3NWM4ZDgxM2MzODgzYTcxODU3OWQ4ZSIsInNjaGVtYSI6IlIyRDJf'
      'VjJfRVBPQ0gwM19ERUxFR0FURURfUEhBU0VfT1JERVJfVjIiLCJzY29wZSI6IkNPTVBPTkVOVFNfT0ZfVEhFX0NPTU1JVFRF'
      'RF9MSVNUIiwic2lnbmVkX2FjdF9iX3NoYTI1NiI6IkRFUklWRURfU0lHTkVEX0FDVF9CX1NIQTI1NiIsInNpbmdsZV91c2Ui'
      'OnRydWUsInNpbmdsZV91c2Vfa2V5IjoiYXR0ZW1wdF9rZXkiLCJzbG90IjoiVU5CT1VORF9TTE9UIiwic2xvdHMiOlsiUFJJ'
      'TUFSWSIsIlNQQVJFIl0sInRlbXBsYXRlX3NoYTI1NiI6IkRFUklWRURfVEVNUExBVEVfU0hBMjU2Iiwid2luZG93X2NsYXNz'
      'IjoiQkVGT1JFX09QRU4iLCJ3aW5kb3dfbWF4X3NlY29uZHMiOnsiUkVBRCI6MzYwMCwiV1JJVEUiOjkwMH0sIndpbmRvd19z'
      'aW5nbGVfdXRjX2RheSI6dHJ1ZX0KYGBgCgojIyMgcmlzayDigJQgU0hBLTI1NiBgYjE3NmU0N2FlZDlkY2E5Y2QxYzJiZmQ2'
      'ZDM2NTU2M2Y4ZTExYTg1MWQ3NzE5MTAzODAzYWM4MWI0MzkxOTIwNWAKCjwhLS0gUjJEMi1FUE9DSDAzLVBIQVNFLVRFTVBM'
      'QVRFOnJpc2sgLS0+CmBgYGpzb24KeyJhY3RfYl9vcmRlcl9zaGEiOiI1MTg2Mjc5MTk3NTRmNzk1ZmY1NTFjOWQ4MzNhM2Ix'
      'MDAwZmI5MzBiNTU1ZGY2NDdlN2UwMGUyYjE5ZTc3NWZlIiwiYXR0ZW1wdF9rZXkiOiJERVJJVkVEX0FUVEVNUFRfS0VZIiwi'
      'YXV0aG9yaXplZF9zZXNzaW9ucyI6WyIyMDI2LTEwLTA1IiwiMjAyNi0xMC0wNiIsIjIwMjYtMTAtMDciLCIyMDI2LTEwLTA4'
      'IiwiMjAyNi0xMC0wOSJdLCJhdXRvbWF0aWNfcmV0cnkiOmZhbHNlLCJjb2RlX3JldmlzaW9uIjoiZGQ0ZWM0YmI4ZGFiNGQ4'
      'YjAzNzJiMGY5ZWFiYzkwYmY2NDQzZTg1OCIsImRheSI6IlVOQk9VTkRfREFZIiwiZG9jdW1lbnRfb3JkZXJfc2hhIjoiMWE1'
      'MjUzYmYyM2Y1MDA2MjI0Yjc5NTI3ZGEwNjY5NzY0NmMzNGM2ZjVhM2E0ZjgyMGFmNWRhMmIxM2Q3YTExOCIsImVwb2NoIjoi'
      'UjJEMi1WMi1TSEFET1ctMjAyNi0xMC0wNSIsImZpcnN0X3Nlc3Npb24iOiIyMDI2LTEwLTA1IiwiZml2ZV9zZXNzaW9uX2F1'
      'dGhvcml0eV9zaGEyNTYiOiJVTkJPVU5EX0ZJVkVfU0VTU0lPTl9BVVRIT1JJVFlfU0hBMjU2IiwiaW5wdXRfcmVjZWlwdF9z'
      'aGEyNTZzIjoiVU5CT1VORF9JTlBVVF9SRUNFSVBUX1NIQTI1NlMiLCJpc3N1ZXIiOiJGQUJMRSIsIms5X2ludGVyZmFjZV9u'
      'b3RlX3NoYTI1NiI6ImFiNTE1OWJlYTM0YjMyMzkzNzllODdjMjUwMGQzODNmMDc3N2NjNjE4NjYxODQzNWJhMGVhOWY2MWUz'
      'ZDU5NmMiLCJtaW5faW5wdXRfcmVjZWlwdHMiOjEsIm1vZGUiOiJERUxFR0FURURfQUNUX0IiLCJub3RfYWZ0ZXIiOiJVTkJP'
      'VU5EX05PVF9BRlRFUiIsIm5vdF9iZWZvcmUiOiJVTkJPVU5EX05PVF9CRUZPUkUiLCJvcGVyYXRpb24iOiJVTkJPVU5EX09Q'
      'RVJBVElPTiIsIm9wZXJhdGlvbl9wYXlsb2FkX3NoYTI1NiI6IlVOQk9VTkRfT1BFUkFUSU9OX1BBWUxPQURfU0hBMjU2Iiwi'
      'b3BlcmF0aW9ucyI6eyJhY3F1aXJlX2xhdW5jaCI6IldSSVRFIiwiYWNxdWlyZV9yZXN1bHQiOiJSRUFEIiwiYmluZCI6IldS'
      'SVRFIiwiZXhlY3V0ZV9sYXVuY2giOiJXUklURSIsImV4ZWN1dGVfcmVzdWx0IjoiUkVBRCIsInByZWZsaWdodCI6IldSSVRF'
      'Iiwic3RhZ2UiOiJXUklURSJ9LCJvd25lcl9wYXlsb2FkX3NpZ25hdHVyZV9zaGEyNTYiOiJVTkJPVU5EX09XTkVSX1BBWUxP'
      'QURfU0lHTkFUVVJFX1NIQTI1NiIsIm93bmVyX3ZldG8iOiJXSVRIRFJBV0FMX0JFRk9SRV9ESVNQQVRDSCIsInBhY2thZ2Vf'
      'c2hhMjU2IjoiYjVjZTUyN2E1NDRjYTBlYjA4ZjA3MThkODM1NDZkN2I0NmY5ZTk3NzRiZThlNDM1MWFmY2UyMTJlNzJiZGI4'
      'NCIsInBoYXNlIjoicmlzayIsInBvbGljeV9zaGEyNTYiOiJkMmZiM2U3NzRjMWRmN2I0YTgwZjY3MGQxYmRmZGIzZjIzZjkw'
      'YjIyMWQ3YmY0NWE3Y2VkOTYxNjRiZTczOGZlIiwicG9saWN5X3ZhbGlkX2Zyb20iOiIyMDI2LTEwLTA1VDAwOjAwOjAwWiIs'
      'InBvbGljeV92YWxpZF91bnRpbCI6IjIwMjYtMTAtMDlUMjA6MDA6MDBaIiwicHVibGljYXRpb25fbm90aWNlX3NlY29uZHNf'
      'bWluIjo5MDAsInB1Ymxpc2hlZF9hdCI6IlVOQk9VTkRfUFVCTElTSEVEX0FUIiwicmVsZWFzZV9zaGEyNTYiOiJmYzJmNjRl'
      'YTI1MmY5OTk2YmE2MmNkOGJiMTA0MTFlYTBjYmMzYTM1MWMxNWI4NjEyZGU4ODM5MGNjYmRjYWExIiwicnVudGltZV9vcmRl'
      'cl9zaGEiOiIxYWQ4YjkwY2ZhYjY1MTgyM2ViNjc3YjgzMGEwMDc4ZDEwYzE3NDQ3NTc1YzhkODEzYzM4ODNhNzE4NTc5ZDhl'
      'Iiwic2NoZW1hIjoiUjJEMl9WMl9FUE9DSDAzX0RFTEVHQVRFRF9QSEFTRV9PUkRFUl9WMiIsInNjb3BlIjoiUE9TVF9BRE1J'
      'U1NJT05fQVJUSUZBQ1RfT05MWSIsInNpZ25lZF9hY3RfYl9zaGEyNTYiOiJERVJJVkVEX1NJR05FRF9BQ1RfQl9TSEEyNTYi'
      'LCJzaW5nbGVfdXNlIjp0cnVlLCJzaW5nbGVfdXNlX2tleSI6ImF0dGVtcHRfa2V5Iiwic2xvdCI6IlVOQk9VTkRfU0xPVCIs'
      'InNsb3RzIjpbIlBSSU1BUlkiLCJTUEFSRSJdLCJ0ZW1wbGF0ZV9zaGEyNTYiOiJERVJJVkVEX1RFTVBMQVRFX1NIQTI1NiIs'
      'IndpbmRvd19jbGFzcyI6IkJFRk9SRV9PUEVOIiwid2luZG93X21heF9zZWNvbmRzIjp7IlJFQUQiOjM2MDAsIldSSVRFIjo5'
      'MDB9LCJ3aW5kb3dfc2luZ2xlX3V0Y19kYXkiOnRydWV9CmBgYAoKIyMjIGNhcHR1cmUg4oCUIFNIQS0yNTYgYDk5MjdhMmNh'
      'NmJhMzlmMmZlMDA1MWFjMjZiMDUyMTE1YjM0MTk5MzZlNWE5Zjk3YjNlY2FhNjViZGM0OTIxNTFgCgo8IS0tIFIyRDItRVBP'
      'Q0gwMy1QSEFTRS1URU1QTEFURTpjYXB0dXJlIC0tPgpgYGBqc29uCnsiYWN0X2Jfb3JkZXJfc2hhIjoiNTE4NjI3OTE5NzU0'
      'Zjc5NWZmNTUxYzlkODMzYTNiMTAwMGZiOTMwYjU1NWRmNjQ3ZTdlMDBlMmIxOWU3NzVmZSIsImF0dGVtcHRfa2V5IjoiREVS'
      'SVZFRF9BVFRFTVBUX0tFWSIsImF1dGhvcml6ZWRfc2Vzc2lvbnMiOlsiMjAyNi0xMC0wNSIsIjIwMjYtMTAtMDYiLCIyMDI2'
      'LTEwLTA3IiwiMjAyNi0xMC0wOCIsIjIwMjYtMTAtMDkiXSwiYXV0b21hdGljX3JldHJ5IjpmYWxzZSwiY29kZV9yZXZpc2lv'
      'biI6ImRkNGVjNGJiOGRhYjRkOGIwMzcyYjBmOWVhYmM5MGJmNjQ0M2U4NTgiLCJkYXkiOiJVTkJPVU5EX0RBWSIsImRvY3Vt'
      'ZW50X29yZGVyX3NoYSI6IjFhNTI1M2JmMjNmNTAwNjIyNGI3OTUyN2RhMDY2OTc2NDZjMzRjNmY1YTNhNGY4MjBhZjVkYTJi'
      'MTNkN2ExMTgiLCJlcG9jaCI6IlIyRDItVjItU0hBRE9XLTIwMjYtMTAtMDUiLCJmaXJzdF9zZXNzaW9uIjoiMjAyNi0xMC0w'
      'NSIsImZpdmVfc2Vzc2lvbl9hdXRob3JpdHlfc2hhMjU2IjoiVU5CT1VORF9GSVZFX1NFU1NJT05fQVVUSE9SSVRZX1NIQTI1'
      'NiIsImlucHV0X3JlY2VpcHRfc2hhMjU2cyI6IlVOQk9VTkRfSU5QVVRfUkVDRUlQVF9TSEEyNTZTIiwiaXNzdWVyIjoiRkFC'
      'TEUiLCJrOV9pbnRlcmZhY2Vfbm90ZV9zaGEyNTYiOiJhYjUxNTliZWEzNGIzMjM5Mzc5ZTg3YzI1MDBkMzgzZjA3NzdjYzYx'
      'ODY2MTg0MzViYTBlYTlmNjFlM2Q1OTZjIiwibWluX2lucHV0X3JlY2VpcHRzIjowLCJtb2RlIjoiREVMRUdBVEVEX0FDVF9C'
      'Iiwibm90X2FmdGVyIjoiVU5CT1VORF9OT1RfQUZURVIiLCJub3RfYmVmb3JlIjoiVU5CT1VORF9OT1RfQkVGT1JFIiwib3Bl'
      'cmF0aW9uIjoiVU5CT1VORF9PUEVSQVRJT04iLCJvcGVyYXRpb25fcGF5bG9hZF9zaGEyNTYiOiJVTkJPVU5EX09QRVJBVElP'
      'Tl9QQVlMT0FEX1NIQTI1NiIsIm9wZXJhdGlvbnMiOnsiY2FwdHVyZV9jbGVhbnVwIjoiV1JJVEUiLCJjYXB0dXJlX2xhdW5j'
      'aCI6IldSSVRFIiwiY2FwdHVyZV9yZXN1bHQiOiJSRUFEIn0sIm93bmVyX3BheWxvYWRfc2lnbmF0dXJlX3NoYTI1NiI6IlVO'
      'Qk9VTkRfT1dORVJfUEFZTE9BRF9TSUdOQVRVUkVfU0hBMjU2Iiwib3duZXJfdmV0byI6IldJVEhEUkFXQUxfQkVGT1JFX0RJ'
      'U1BBVENIIiwicGFja2FnZV9zaGEyNTYiOiJiNWNlNTI3YTU0NGNhMGViMDhmMDcxOGQ4MzU0NmQ3YjQ2ZjllOTc3NGJlOGU0'
      'MzUxYWZjZTIxMmU3MmJkYjg0IiwicGhhc2UiOiJjYXB0dXJlIiwicG9saWN5X3NoYTI1NiI6ImQyZmIzZTc3NGMxZGY3YjRh'
      'ODBmNjcwZDFiZGZkYjNmMjNmOTBiMjIxZDdiZjQ1YTdjZWQ5NjE2NGJlNzM4ZmUiLCJwb2xpY3lfdmFsaWRfZnJvbSI6IjIw'
      'MjYtMTAtMDVUMDA6MDA6MDBaIiwicG9saWN5X3ZhbGlkX3VudGlsIjoiMjAyNi0xMC0wOVQyMDowMDowMFoiLCJwdWJsaWNh'
      'dGlvbl9ub3RpY2Vfc2Vjb25kc19taW4iOjkwMCwicHVibGlzaGVkX2F0IjoiVU5CT1VORF9QVUJMSVNIRURfQVQiLCJyZWxl'
      'YXNlX3NoYTI1NiI6ImZjMmY2NGVhMjUyZjk5OTZiYTYyY2Q4YmIxMDQxMWVhMGNiYzNhMzUxYzE1Yjg2MTJkZTg4MzkwY2Ni'
      'ZGNhYTEiLCJydW50aW1lX29yZGVyX3NoYSI6IjFhZDhiOTBjZmFiNjUxODIzZWI2NzdiODMwYTAwNzhkMTBjMTc0NDc1NzVj'
      'OGQ4MTNjMzg4M2E3MTg1NzlkOGUiLCJzY2hlbWEiOiJSMkQyX1YyX0VQT0NIMDNfREVMRUdBVEVEX1BIQVNFX09SREVSX1Yy'
      'Iiwic2NvcGUiOiJEQUlMWV9DQVBUVVJFX0RJU1RJTkNUX0ZST01fUVVPVEVfQ0FQVFVSRSIsInNpZ25lZF9hY3RfYl9zaGEy'
      'NTYiOiJERVJJVkVEX1NJR05FRF9BQ1RfQl9TSEEyNTYiLCJzaW5nbGVfdXNlIjp0cnVlLCJzaW5nbGVfdXNlX2tleSI6ImF0'
      'dGVtcHRfa2V5Iiwic2xvdCI6IlVOQk9VTkRfU0xPVCIsInNsb3RzIjpbIlBSSU1BUlkiLCJTUEFSRSJdLCJ0ZW1wbGF0ZV9z'
      'aGEyNTYiOiJERVJJVkVEX1RFTVBMQVRFX1NIQTI1NiIsIndpbmRvd19jbGFzcyI6IklOX1NFU1NJT04iLCJ3aW5kb3dfbWF4'
      'X3NlY29uZHMiOnsiUkVBRCI6MzYwMCwiV1JJVEUiOjkwMH0sIndpbmRvd19zaW5nbGVfdXRjX2RheSI6dHJ1ZX0KYGBgCgoj'
      'IyMgcG9saWN5X3JlYWRvbmx5IOKAlCBTSEEtMjU2IGAxYWI4ZWNiNjNhMzAwNDhkNTVkNzNjYjg1NWI5ZTRmOGZhYmQwMzBk'
      'YmM3NGYyZjE3MGRiODFlNDE2YTUxZmUzYAoKPCEtLSBSMkQyLUVQT0NIMDMtUEhBU0UtVEVNUExBVEU6cG9saWN5X3JlYWRv'
      'bmx5IC0tPgpgYGBqc29uCnsiYWN0X2Jfb3JkZXJfc2hhIjoiNTE4NjI3OTE5NzU0Zjc5NWZmNTUxYzlkODMzYTNiMTAwMGZi'
      'OTMwYjU1NWRmNjQ3ZTdlMDBlMmIxOWU3NzVmZSIsImF0dGVtcHRfa2V5IjoiREVSSVZFRF9BVFRFTVBUX0tFWSIsImF1dGhv'
      'cml6ZWRfc2Vzc2lvbnMiOlsiMjAyNi0xMC0wNSIsIjIwMjYtMTAtMDYiLCIyMDI2LTEwLTA3IiwiMjAyNi0xMC0wOCIsIjIw'
      'MjYtMTAtMDkiXSwiYXV0b21hdGljX3JldHJ5IjpmYWxzZSwiY29kZV9yZXZpc2lvbiI6ImRkNGVjNGJiOGRhYjRkOGIwMzcy'
      'YjBmOWVhYmM5MGJmNjQ0M2U4NTgiLCJkYXkiOiJVTkJPVU5EX0RBWSIsImRvY3VtZW50X29yZGVyX3NoYSI6IjFhNTI1M2Jm'
      'MjNmNTAwNjIyNGI3OTUyN2RhMDY2OTc2NDZjMzRjNmY1YTNhNGY4MjBhZjVkYTJiMTNkN2ExMTgiLCJlcG9jaCI6IlIyRDIt'
      'VjItU0hBRE9XLTIwMjYtMTAtMDUiLCJmaXJzdF9zZXNzaW9uIjoiMjAyNi0xMC0wNSIsImZpdmVfc2Vzc2lvbl9hdXRob3Jp'
      'dHlfc2hhMjU2IjoiVU5CT1VORF9GSVZFX1NFU1NJT05fQVVUSE9SSVRZX1NIQTI1NiIsImlucHV0X3JlY2VpcHRfc2hhMjU2'
      'cyI6IlVOQk9VTkRfSU5QVVRfUkVDRUlQVF9TSEEyNTZTIiwiaXNzdWVyIjoiRkFCTEUiLCJrOV9pbnRlcmZhY2Vfbm90ZV9z'
      'aGEyNTYiOiJhYjUxNTliZWEzNGIzMjM5Mzc5ZTg3YzI1MDBkMzgzZjA3NzdjYzYxODY2MTg0MzViYTBlYTlmNjFlM2Q1OTZj'
      'IiwibWluX2lucHV0X3JlY2VpcHRzIjowLCJtb2RlIjoiREVMRUdBVEVEX0FDVF9CIiwibm90X2FmdGVyIjoiVU5CT1VORF9O'
      'T1RfQUZURVIiLCJub3RfYmVmb3JlIjoiVU5CT1VORF9OT1RfQkVGT1JFIiwib3BlcmF0aW9uIjoiVU5CT1VORF9PUEVSQVRJ'
      'T04iLCJvcGVyYXRpb25fcGF5bG9hZF9zaGEyNTYiOiJVTkJPVU5EX09QRVJBVElPTl9QQVlMT0FEX1NIQTI1NiIsIm9wZXJh'
      'dGlvbnMiOnsicG9saWN5X3JlYWQiOiJSRUFEIn0sIm93bmVyX3BheWxvYWRfc2lnbmF0dXJlX3NoYTI1NiI6IlVOQk9VTkRf'
      'T1dORVJfUEFZTE9BRF9TSUdOQVRVUkVfU0hBMjU2Iiwib3duZXJfdmV0byI6IldJVEhEUkFXQUxfQkVGT1JFX0RJU1BBVENI'
      'IiwicGFja2FnZV9zaGEyNTYiOiJiNWNlNTI3YTU0NGNhMGViMDhmMDcxOGQ4MzU0NmQ3YjQ2ZjllOTc3NGJlOGU0MzUxYWZj'
      'ZTIxMmU3MmJkYjg0IiwicGhhc2UiOiJwb2xpY3lfcmVhZG9ubHkiLCJwb2xpY3lfc2hhMjU2IjoiZDJmYjNlNzc0YzFkZjdi'
      'NGE4MGY2NzBkMWJkZmRiM2YyM2Y5MGIyMjFkN2JmNDVhN2NlZDk2MTY0YmU3MzhmZSIsInBvbGljeV92YWxpZF9mcm9tIjoi'
      'MjAyNi0xMC0wNVQwMDowMDowMFoiLCJwb2xpY3lfdmFsaWRfdW50aWwiOiIyMDI2LTEwLTA5VDIwOjAwOjAwWiIsInB1Ymxp'
      'Y2F0aW9uX25vdGljZV9zZWNvbmRzX21pbiI6OTAwLCJwdWJsaXNoZWRfYXQiOiJVTkJPVU5EX1BVQkxJU0hFRF9BVCIsInJl'
      'bGVhc2Vfc2hhMjU2IjoiZmMyZjY0ZWEyNTJmOTk5NmJhNjJjZDhiYjEwNDExZWEwY2JjM2EzNTFjMTViODYxMmRlODgzOTBj'
      'Y2JkY2FhMSIsInJ1bnRpbWVfb3JkZXJfc2hhIjoiMWFkOGI5MGNmYWI2NTE4MjNlYjY3N2I4MzBhMDA3OGQxMGMxNzQ0NzU3'
      'NWM4ZDgxM2MzODgzYTcxODU3OWQ4ZSIsInNjaGVtYSI6IlIyRDJfVjJfRVBPQ0gwM19ERUxFR0FURURfUEhBU0VfT1JERVJf'
      'VjIiLCJzY29wZSI6IlBPTElDWV9BTkRfV09SS0VSX1JFQURfT05MWSIsInNpZ25lZF9hY3RfYl9zaGEyNTYiOiJERVJJVkVE'
      'X1NJR05FRF9BQ1RfQl9TSEEyNTYiLCJzaW5nbGVfdXNlIjp0cnVlLCJzaW5nbGVfdXNlX2tleSI6ImF0dGVtcHRfa2V5Iiwi'
      'c2xvdCI6IlVOQk9VTkRfU0xPVCIsInNsb3RzIjpbIlBSSU1BUlkiLCJTUEFSRSJdLCJ0ZW1wbGF0ZV9zaGEyNTYiOiJERVJJ'
      'VkVEX1RFTVBMQVRFX1NIQTI1NiIsIndpbmRvd19jbGFzcyI6IlBPTElDWV9XSU5ET1ciLCJ3aW5kb3dfbWF4X3NlY29uZHMi'
      'OnsiUkVBRCI6MzYwMCwiV1JJVEUiOjkwMH0sIndpbmRvd19zaW5nbGVfdXRjX2RheSI6dHJ1ZX0KYGBgCgojIyA2LiBEZXJp'
      'dmHDp8OjbyBlIGNhbXBvcyBzdWJzdGl0dcOtdmVpcwoKLSBTY3JpcHQgYGRlcml2ZV9kYWlseTAzLnB5YCwgU0hBLTI1NiBg'
      'ODk0ZmZiNWQ5MWQwODY3YjRlYjAxYzc3ZmYyOWYyYzZmYjAzYjQ5YThlN2M0MGJmNzY4NDRjY2I1OTk0YmZjZWAuIERldGVy'
      'bWluw61zdGljbywgc8OzIGJpYmxpb3RlY2EgcGFkcsOjbzsgc2VtIHJlZGUsIHJlbMOzZ2lvIG91IGF1dG9yaWRhZGUuIEzD'
      'qiBvIHRlbXBsYXRlIGRhIGZhc2UgbmVzdGUgYXJxdWl2byAocGVsbyBtYXJjYWRvciksIGNvbmZlcmUgbyBTSEEtMjU2IGRl'
      'c3RlIGFycXVpdm8sIHN1YnN0aXR1aSBvcyBjYW1wb3MgZGEgbGlzdGEgZmVjaGFkYSwgcHJlZW5jaGUgb3MgdHLDqnMgY2Ft'
      'cG9zIGRlcml2YWRvcyBlIGltcHJpbWUgYSBvcmRlbSBkZXJpdmFkYSAoSlNPTiBjYW7DtG5pY28pIGUgbyBzZXUgU0hBLTI1'
      'NiwgY29tIG8gcmVzdWx0YWRvIGBPRkZMSU5FX0RFUklWQVRJT05fTk9UX0FVVEhPUklUWWAuCi0gTGlzdGEgZmVjaGFkYSBk'
      'ZSBjYW1wb3Mgc3Vic3RpdHXDrXZlaXM6IGBkYXlgLCBgb3BlcmF0aW9uYCwgYHNsb3RgLCBgbm90X2JlZm9yZWAsIGBub3Rf'
      'YWZ0ZXJgLCBgcHVibGlzaGVkX2F0YCwgYG9wZXJhdGlvbl9wYXlsb2FkX3NoYTI1NmAsIGBvd25lcl9wYXlsb2FkX3NpZ25h'
      'dHVyZV9zaGEyNTZgLCBgZml2ZV9zZXNzaW9uX2F1dGhvcml0eV9zaGEyNTZgLCBgaW5wdXRfcmVjZWlwdF9zaGEyNTZzYC4g'
      'TmVuaHVtIG91dHJvIGNhbXBvIHZhcmlhLgotIFJlZ3JhcyBkbyBzY3JpcHQ6IGBkYXlgIMOpIHVtYSBkYXMgY2luY28gc2Vz'
      'c8O1ZXM7IGBvcGVyYXRpb25gIMOpIHVtYSBkYXMgb3BlcmHDp8O1ZXMgbGlzdGFkYXMgbm8gdGVtcGxhdGUgZGEgZmFzZSAo'
      'bm90YSBLOSkgZSB1bWEgb3BlcmHDp8OjbyBmb3JhIGRhIGxpc3RhIMOpIHJlY3VzYWRhOyBgc2xvdGAgw6kgYFBSSU1BUllg'
      'IG91IGBTUEFSRWA7IGhvcsOhcmlvcyBlbSBVVEMgY29tIHNlZ3VuZG9zIGludGVpcm9zOyBgbm90X2JlZm9yZWAgYW50ZXMg'
      'ZGUgYG5vdF9hZnRlcmA7IGEgamFuZWxhIGZpY2EgaW50ZWlyYSBudW0gc8OzIGRpYSBVVEMgKG51bmNhIGF0cmF2ZXNzYSAy'
      'MTowMCBkZSBCcmFzw61saWEpIGUgZHVyYSBubyBtw6F4aW1vIDM2MDAgc2VndW5kb3MgbnVtYSBvcGVyYcOnw6NvIGBSRUFE'
      'YCBlIDkwMCBzZWd1bmRvcyBudW1hIG9wZXJhw6fDo28gYFdSSVRFYDsgZSBmaWNhIGRlbnRybyBkYSBjbGFzc2UgZGUgamFu'
      'ZWxhIGRvIGRpYTogYW50ZXMgZGEgYWJlcnR1cmEsIGRvIGZlY2hvIGRhIHNlc3PDo28gYW50ZXJpb3IgYXTDqSBhIGFiZXJ0'
      'dXJhOyBuYSBzZXNzw6NvLCBkYSBhYmVydHVyYSBhbyBmZWNobzsgcmV2YWxpZGHDp8OjbyBkYSBwb2xpY3ksIGRvIGZlY2hv'
      'IGRhIHNlc3PDo28gYW50ZXJpb3IgYW8gZmVjaG8gZG8gZGlhLCBzZW0gc2FpciBkYSB2YWxpZGFkZSBkYSBwb2xpY3kuIGBw'
      'dWJsaXNoZWRfYXRgIHBlbG8gbWVub3MgMTUgbWludXRvcyBlIG5vIG3DoXhpbW8gNCBkaWFzIGFudGVzIGRlIGBub3RfYmVm'
      'b3JlYDsgaGFzaGVzIGNvbSBjYXJhIGRlIHJlYWlzLCBkaXN0aW50b3MgZW50cmUgc2kgZSBkb3MgaGFzaGVzIGZpeG9zOyBy'
      'ZWNpYm9zIGRlIGVudHJhZGEgZW0gbGlzdGEgb3JkZW5hZGEsIHNlbSByZXBldGnDp8OjbywgZG8gbcOtbmltbyBkYSBmYXNl'
      'ICh1bSBwYXJhIGZvbnRlcywgY29tcG9uZW50ZXMgZSByaXNjbzsgemVybyBwYXJhIGFzIGRlbWFpcykgYXTDqSBvaXRvLgot'
      'IFVzbyDDum5pY286IHVtYSBvcmRlbSBkZXJpdmFkYSBwb3IgZGlhLCBmYXNlLCBvcGVyYcOnw6NvIGUgdmFnYS4gQSB2YWdh'
      'IGBTUEFSRWAgc8OzIMOpIHVzYWRhIHNlIGEgYFBSSU1BUllgIGRhIG1lc21hIG9wZXJhw6fDo28gY29tcHJvdmFkYW1lbnRl'
      'IG51bmNhIGZvaSBkZXNwYWNoYWRhLCBwZWxhIGRlZmluacOnw6NvIGRlICJkZXNwYWNoYWRvIiBkYSBhdXRvcmlkYWRlIGRl'
      'IHByZXBhcmHDp8OjbyAoQTEsIGxpbmhhIDIzKSwgcmVwZXRpZGEgbmEgYXV0b3JpZGFkZSBkYXMgY2luY28gc2Vzc8O1ZXM7'
      'IGRlc3BhY2hvLCByZWN1c2Egb3UgaW5jZXJ0ZXphIGNvbnNvbWVtIGEgdGVudGF0aXZhIChPUkQ6MzMpLiBgYXR0ZW1wdF9r'
      'ZXlgID0gU0hBLTI1NiBkYSBsaXN0YSBjYW7DtG5pY2EgYFvDqXBvY2EsIGRpYSwgZmFzZSwgb3BlcmHDp8Ojb11gLCBzZW0g'
      'YSB2YWdhOiBhIGBQUklNQVJZYCBlIGEgYFNQQVJFYCB0w6ptIGEgbWVzbWEgY2hhdmUuIE51bWEgb3BlcmHDp8OjbyBgV1JJ'
      'VEVgLCBvIHByb2dyYW1hIHJlaXZpbmRpY2EgbyB1c28gw7puaWNvIG5vIHNlcnZpZG9yIHBvciBlc3NhIGNoYXZlLCBkZSBt'
      'b2RvIHF1ZSBubyBtw6F4aW1vIHVtYSBkYXMgZHVhcyByb2RhOyBwcm9ncmFtYSBkZSBlc2NyaXRhIHF1ZSBuw6NvIHJlaXZp'
      'bmRpcXVlIHBlbGEgYGF0dGVtcHRfa2V5YCBuw6NvIMOpIHVzYWRvIGNvbSBvcmRlbSBkZXJpdmFkYSBkZXN0ZSBhdG8uIE51'
      'bWEgb3BlcmHDp8OjbyBgUkVBRGAsIHF1ZSBuw6NvIGVzY3JldmUgbm8gc2Vydmlkb3IsIG8gdXNvIMO6bmljbyBmaWNhIGNv'
      'bSBvIHRyYW5zcG9ydGUgZGUgdXNvIMO6bmljbyAob25jZSk6IG8gY2xhaW0gbG9jYWwgZG8gR08gZSBvIGBzcGF3bi5jbGFp'
      'bWAgcXVlIG8gZGlzcGF0Y2hlciBncmF2YSwgdW0gZGVzcGFjaG8gcG9yIHBlZGlkbyBhc3NpbmFkbzsgYSBgU1BBUkVgIGRl'
      'IHVtYSBsZWl0dXJhIHPDsyDDqSB1c2FkYSBzZSBhIHN1YSBgUFJJTUFSWWAgbnVuY2EgZm9pIGRlc3BhY2hhZGEsIHBlbGEg'
      'bWVzbWEgZGVmaW5pw6fDo28gZGUgImRlc3BhY2hhZG8iLgotIE9yZGVtIG51bWEgdsOpc3BlcmE6IG5lbmh1bWEgb3BlcmHD'
      'p8OjbyBkZSBmb250ZXMsIGNvbXBvbmVudGVzIG91IHJpc2NvIGNvbWXDp2EgYW50ZXMgZG8gcmVjaWJvIGRhIGNvbmZpcm1h'
      'w6fDo28gZGEgbGlzdGEgY2F1c2FsIGRvIGRpYTsgYSBvcmRlbSBlbnRyZSBlbGFzIMOpIGEgZGEgbm90YSBLOSBlIGEgZGEg'
      'YXV0b3JpZGFkZSBkYXMgY2luY28gc2Vzc8O1ZXMuCi0gQW50ZXMgZGUgdXNhciB1bWEgb3JkZW0gZGVyaXZhZGEsIGEgRmFi'
      'bGUgY29uZmVyZTogYSBjYWRlaWEgY29tcGxldGEgZGVzdGUgYXRvIChzZXRlIGRvY3VtZW50b3MpOyBvcyBieXRlcyBkbyB0'
      'ZW1wbGF0ZTsgYSBvcmlnZW0gcHVibGljYWRhIGRvcyB2YWxvcmVzIHN1YnN0aXR1w61kb3M7IGEgYXV0b3JpZGFkZSBkYXMg'
      'Y2luY28gc2Vzc8O1ZXMgcXVlIGVudW1lcmEgYSBvcGVyYcOnw6NvLCBvIGRpYSBlIGEgamFuZWxhOyBhIGFzc2luYXR1cmEg'
      'ZG8gZG9ubyBxdWUgYSBkZWNpc8OjbyBlbSB2aWdvciBleGlnZSAoc2XDp8OjbyAzKTsgZSBwdWJsaWNhIG5vIGNhbmFsIG8g'
      'U0hBLTI1NiBkYSBvcmRlbSBkZXJpdmFkYSBubyBpbnN0YW50ZSBgcHVibGlzaGVkX2F0YC4gTyBkb25vIHBvZGUgdmV0YXIg'
      'YXTDqSBvIGRlc3BhY2hvLiBSZWN1c2Egb3UgaW5jZXJ0ZXphIGVuY2VycmEgYXF1ZWxhIG9wZXJhw6fDo28gbmFxdWVsZSBk'
      'aWEgKE9SRDozMykuCgojIyA3LiBGb3JtYXRvIGUgY2FkZWlhCgotIE8gU0hBLTI1NiBkZXN0ZSBhdG8gw6kgbyBkb3MgYnl0'
      'ZXMgY29tcGxldG9zIGRlc3RlIGFycXVpdm8sIHByb3NhIGluY2x1w61kYS4gSMOhIHVtIMO6bmljbyBibG9jbyBjYW7DtG5p'
      'Y28gYWJhaXhvIGUgbmFkYSBkZXBvaXMgZG8gZmltIGRlbGUgKGByMmQyX3YyX2RvY3VtZW50X2Zvcm1hdC5weToyMS00MWAp'
      'OyBvIGNvcnBvIHRlbSBleGF0YW1lbnRlIG9zIGNhbXBvcyBxdWUgbyBjw7NkaWdvIGRhIHJlbGVhc2UgbMOqIChgOjgyLTk2'
      'YCkuCi0gQ2FkZWlhIEI6IEJfQ09ERVgg4oaSIEJfRkFCTEUg4oaSIEJfRFVEVSwgY2FkYSB1bWEgY29tIGBib2R5X3NoYWAg'
      'PSBTSEEtMjU2IGRlc3RlIGFycXVpdm8gZSBgYWN0X2FfaGVhZGAgPSBgMmVlNmRlMjE3MzE2ZGY2NTc3Zjc1MWUyMDhiZTUy'
      'MzljMzQ4MzlmNjA2YWIxMmJiMzkyMzVlNjVjMjk0OGY1Y2A7IEJfQ09ERVggZSBCX0ZBQkxFIHNlbSByZWzDs2dpbyBuZW0g'
      'Y2FtcG8gbGl2cmU7IEJfRFVEVSBjb20gYSByZXNwb3N0YSBsaXRlcmFsIGRvIGRvbm8sIG8gY2FuYWwgZSBhIGhvcmEgKGBy'
      'MmQyX3YyX2RvY3VtZW50X2Zvcm1hdC5weToyMTktMjI1YCkuIEEgcmVzcG9zdGEgdGVtIGRlIG5vbWVhciBlc3RlIGF0byDi'
      'gJQgIkFzc2lubyBvIGF0byBCIiBvdSAiQXNzaW5vIG8gYWRlbmRvIiDigJQgZSBzZXIgZGFkYSBkZXBvaXMgZGUgYSBwZXJn'
      'dW50YSBkZXN0ZSBhdG8gc2VyIG1vc3RyYWRhOiB1bSAiQXNzaW5vIiBzb3ppbmhvIG7Do28gdmFsZSwgcG9ycXVlIGEgbWVz'
      'bWEgc2VudGFkYSB0ZW0gb3V0cmFzIHBlcmd1bnRhcyByZXNwb25kaWRhcyBhc3NpbS4KLSBTZW0gYSBjYWRlaWEgY29tcGxl'
      'dGEgbmVuaHVtYSBmYXNlIGRpw6FyaWEgZXhlY3V0YSAoT1JEOjM3KS4KCjwhLS0gUjJEMi1FVklERU5DRS1WMTpCRUdJTiAt'
      'LT4KYGBganNvbgp7ImJvZHkiOnsiYWN0X2Ffc2NvcGVfbWFwIjp7IkNPREVYIjp7ImF1dGhvcml6ZWRfc2Vzc2lvbnMiOlsi'
      'MjAyNi0xMC0wNSIsIjIwMjYtMTAtMDYiLCIyMDI2LTEwLTA3IiwiMjAyNi0xMC0wOCIsIjIwMjYtMTAtMDkiXSwiZG9jdW1l'
      'bnRfc2hhMjU2IjoiMWE1MjUzYmYyM2Y1MDA2MjI0Yjc5NTI3ZGEwNjY5NzY0NmMzNGM2ZjVhM2E0ZjgyMGFmNWRhMmIxM2Q3'
      'YTExOCIsImVwb2NoIjoiUjJEMi1WMi1TSEFET1ctMjAyNi0xMC0wNSIsImZpcnN0X3Nlc3Npb24iOiIyMDI2LTEwLTA1Iiwi'
      'c2lnbmF0dXJlX3NoYSI6ImM3YjhiZmUxM2ZmZjAyMzFiNWJjMTI3MzY4ODY4MThiNDIwOGY4NDkyOTk4ZjQ1MjgzMTk2MDZm'
      'NWY1NTZhMWMifSwiRFVEVSI6eyJhdXRob3JpemVkX3Nlc3Npb25zIjpbIjIwMjYtMTAtMDUiLCIyMDI2LTEwLTA2IiwiMjAy'
      'Ni0xMC0wNyIsIjIwMjYtMTAtMDgiLCIyMDI2LTEwLTA5Il0sImRvY3VtZW50X3NoYTI1NiI6IjFhNTI1M2JmMjNmNTAwNjIy'
      'NGI3OTUyN2RhMDY2OTc2NDZjMzRjNmY1YTNhNGY4MjBhZjVkYTJiMTNkN2ExMTgiLCJlcG9jaCI6IlIyRDItVjItU0hBRE9X'
      'LTIwMjYtMTAtMDUiLCJmaXJzdF9zZXNzaW9uIjoiMjAyNi0xMC0wNSIsInNpZ25hdHVyZV9zaGEiOiIyZWU2ZGUyMTczMTZk'
      'ZjY1NzdmNzUxZTIwOGJlNTIzOWMzNDgzOWY2MDZhYjEyYmIzOTIzNWU2NWMyOTQ4ZjVjIn0sIkZBQkxFIjp7ImF1dGhvcml6'
      'ZWRfc2Vzc2lvbnMiOlsiMjAyNi0xMC0wNSIsIjIwMjYtMTAtMDYiLCIyMDI2LTEwLTA3IiwiMjAyNi0xMC0wOCIsIjIwMjYt'
      'MTAtMDkiXSwiZG9jdW1lbnRfc2hhMjU2IjoiMWE1MjUzYmYyM2Y1MDA2MjI0Yjc5NTI3ZGEwNjY5NzY0NmMzNGM2ZjVhM2E0'
      'ZjgyMGFmNWRhMmIxM2Q3YTExOCIsImVwb2NoIjoiUjJEMi1WMi1TSEFET1ctMjAyNi0xMC0wNSIsImZpcnN0X3Nlc3Npb24i'
      'OiIyMDI2LTEwLTA1Iiwic2lnbmF0dXJlX3NoYSI6IjY5Y2U2ZjE4MTUxYzM1MTFkODk2MzI1MmExMTNjMWM4MDZhZWJlMTI4'
      'Yjc4NzZkOTYyYWIzOTFhNTk5NDU1OGMifX0sImF1dGhvcml6ZWRfc2Vzc2lvbnMiOlsiMjAyNi0xMC0wNSIsIjIwMjYtMTAt'
      'MDYiLCIyMDI2LTEwLTA3IiwiMjAyNi0xMC0wOCIsIjIwMjYtMTAtMDkiXSwiYXV0b21hdGljX3JldHJ5IjpmYWxzZSwiY2Fw'
      'YWNpdHkiOjU1MCwiY2F1c2FsX29yZGVyIjp7ImN1dCI6IlRBSUxfTkVXX09OTFkiLCJwcmltYXJ5IjoiQURWX0RFU0MiLCJ0'
      'aWVfYnJlYWsiOiJTWU1CT0xfQVNDIn0sImNoYWluX2hlYWQiOiIyZWU2ZGUyMTczMTZkZjY1NzdmNzUxZTIwOGJlNTIzOWMz'
      'NDgzOWY2MDZhYjEyYmIzOTIzNWU2NWMyOTQ4ZjVjIiwiY3V0X3J1bGUiOiJPUEVOX0ZJUlNUX1RIRU5fRVhJU1RJTkdfQ0FV'
      'U0FMX09SREVSX1YxX1BST1BPU0VEIiwiZG9jdW1lbnRfb3JkZXJfc2hhIjoiMWE1MjUzYmYyM2Y1MDA2MjI0Yjc5NTI3ZGEw'
      'NjY5NzY0NmMzNGM2ZjVhM2E0ZjgyMGFmNWRhMmIxM2Q3YTExOCIsImVwb2NoIjoiUjJEMi1WMi1TSEFET1ctMjAyNi0xMC0w'
      'NSIsImZpcnN0X3Nlc3Npb24iOiIyMDI2LTEwLTA1IiwiaW5kaXZpZHVhbF9nb19pc3N1ZXJzIjpbIkZBQkxFIl0sIm9yZGVy'
      'X3NoYSI6IjUxODYyNzkxOTc1NGY3OTVmZjU1MWM5ZDgzM2EzYjEwMDBmYjkzMGI1NTVkZjY0N2U3ZTAwZTJiMTllNzc1ZmUi'
      'LCJvd25lcl9jb3VudGVyc2lnbl9waGFzZXMiOlsiYmFyX21lcmdlX2RlcGxveV9yZWNlcnRpZnkiLCJpbnN0YWxsX3JlbGVh'
      'c2UiLCJhY3RpdmF0ZSIsIndpbmRfZG93bl8yOCJdLCJwb2xpY3lfZXBvY2hfdmFsaWRpdHkiOnRydWUsInBvbGljeV9zaGEi'
      'OiJkMmZiM2U3NzRjMWRmN2I0YTgwZjY3MGQxYmRmZGIzZjIzZjkwYjIyMWQ3YmY0NWE3Y2VkOTYxNjRiZTczOGZlIiwicm9s'
      'bGJhY2tfZGlzcG9zaXRpb24iOiJSRVZBTElEQVRFX1VOQ09NTUlUVEVEX09OTFkiLCJzdGF0dXMiOiJBQ0NFUFRFRCIsInN1'
      'YnBoYXNlcyI6e30sInRlbXBsYXRlX3NldF9zaGEiOiI2ODcwNWIzYmEzMjY5ZGRkYWIzNzVjYmZmYjllODQ0NTNmNTQyYWZj'
      'YTMyOWEzODU0YmM1Y2I5MjNiZDJkYzVmIiwidGVtcGxhdGVfc2hhcyI6eyIyMDI2LTEwLTA1IjoiZDBjNjgyODY3YjVjZGNh'
      'NmY1MmE0ZTlhODhkYmM3ZGM5M2ViN2ZiODE5MjhjYzUyYjA1OTk4OWFmYzY2MjI1NSIsIjIwMjYtMTAtMDYiOiI4NWVmNDYw'
      'YWFlNjhkZTA0OWFlNzU4MTBhYmJmMmJkMDUzMWMwOGU2NWU4NGYxMjMzZjAzODgwZjIzM2Q1NWQzIiwiMjAyNi0xMC0wNyI6'
      'IjAwMmI0N2Y2ZGFmMjBkNDQ1NTE0Njg0ZDQ1ZjQ1NTk5NTQ4Y2Q1ZjQ5ODQyNGEwNTVjN2Q0NGQ0YTRmZTlmNjAiLCIyMDI2'
      'LTEwLTA4IjoiMDk4MGIyYTAyYmE3YzA3NzQwMjA0MjA1ZTRkZmQ4YjhlOTE4NmFhN2M4Zjg4M2JlNjE3MjE1ZmQxOWY3YTkx'
      'NiIsIjIwMjYtMTAtMDkiOiI4YTg1MmFhYzA2OTM3ZmI2YWUxODM3M2M1MzVhMGViMTgwZTk0OWYzNWQwZjA1NmJiOWZhMmM5'
      'MTMyZmNiZDk0In0sInRlbXBsYXRlcyI6W3siYXV0aG9yaXplZF9zZXNzaW9ucyI6WyIyMDI2LTEwLTA1Il0sImVwb2NoIjoi'
      'UjJEMi1WMi1TSEFET1ctMjAyNi0xMC0wNSIsImZpcnN0X3Nlc3Npb24iOiIyMDI2LTEwLTA1IiwicGhhc2VzIjpbImFkbWlz'
      'c2lvbiIsImJhcl9tYW5pZmVzdCIsInF1b3RlX3JlZnJlc2giLCJxdW90ZV9jYXB0dXJlIl0sInNoYSI6ImQwYzY4Mjg2N2I1'
      'Y2RjYTZmNTJhNGU5YTg4ZGJjN2RjOTNlYjdmYjgxOTI4Y2M1MmIwNTk5ODlhZmM2NjIyNTUifSx7ImF1dGhvcml6ZWRfc2Vz'
      'c2lvbnMiOlsiMjAyNi0xMC0wNiJdLCJlcG9jaCI6IlIyRDItVjItU0hBRE9XLTIwMjYtMTAtMDUiLCJmaXJzdF9zZXNzaW9u'
      'IjoiMjAyNi0xMC0wNSIsInBoYXNlcyI6WyJhZG1pc3Npb24iLCJiYXJfbWFuaWZlc3QiLCJxdW90ZV9yZWZyZXNoIiwicXVv'
      'dGVfY2FwdHVyZSJdLCJzaGEiOiI4NWVmNDYwYWFlNjhkZTA0OWFlNzU4MTBhYmJmMmJkMDUzMWMwOGU2NWU4NGYxMjMzZjAz'
      'ODgwZjIzM2Q1NWQzIn0seyJhdXRob3JpemVkX3Nlc3Npb25zIjpbIjIwMjYtMTAtMDciXSwiZXBvY2giOiJSMkQyLVYyLVNI'
      'QURPVy0yMDI2LTEwLTA1IiwiZmlyc3Rfc2Vzc2lvbiI6IjIwMjYtMTAtMDUiLCJwaGFzZXMiOlsiYWRtaXNzaW9uIiwiYmFy'
      'X21hbmlmZXN0IiwicXVvdGVfcmVmcmVzaCIsInF1b3RlX2NhcHR1cmUiXSwic2hhIjoiMDAyYjQ3ZjZkYWYyMGQ0NDU1MTQ2'
      'ODRkNDVmNDU1OTk1NDhjZDVmNDk4NDI0YTA1NWM3ZDQ0ZDRhNGZlOWY2MCJ9LHsiYXV0aG9yaXplZF9zZXNzaW9ucyI6WyIy'
      'MDI2LTEwLTA4Il0sImVwb2NoIjoiUjJEMi1WMi1TSEFET1ctMjAyNi0xMC0wNSIsImZpcnN0X3Nlc3Npb24iOiIyMDI2LTEw'
      'LTA1IiwicGhhc2VzIjpbImFkbWlzc2lvbiIsImJhcl9tYW5pZmVzdCIsInF1b3RlX3JlZnJlc2giLCJxdW90ZV9jYXB0dXJl'
      'Il0sInNoYSI6IjA5ODBiMmEwMmJhN2MwNzc0MDIwNDIwNWU0ZGZkOGI4ZTkxODZhYTdjOGY4ODNiZTYxNzIxNWZkMTlmN2E5'
      'MTYifSx7ImF1dGhvcml6ZWRfc2Vzc2lvbnMiOlsiMjAyNi0xMC0wOSJdLCJlcG9jaCI6IlIyRDItVjItU0hBRE9XLTIwMjYt'
      'MTAtMDUiLCJmaXJzdF9zZXNzaW9uIjoiMjAyNi0xMC0wNSIsInBoYXNlcyI6WyJhZG1pc3Npb24iLCJiYXJfbWFuaWZlc3Qi'
      'LCJxdW90ZV9yZWZyZXNoIiwicXVvdGVfY2FwdHVyZSJdLCJzaGEiOiI4YTg1MmFhYzA2OTM3ZmI2YWUxODM3M2M1MzVhMGVi'
      'MTgwZTk0OWYzNWQwZjA1NmJiOWZhMmM5MTMyZmNiZDk0In1dfSwia2luZCI6IkFDVF9CIiwic2NoZW1hIjoiUjJEMl9ET0NV'
      'TUVOVEFSWV9FVklERU5DRV9WMSIsInN0YXRlIjoiSVNTVUVEIn0KYGBgCjwhLS0gUjJEMi1FVklERU5DRS1WMTpFTkQgLS0+'
      'Cg==')),
    ('B_CODEX','B_CODEX_ADENDO_EPOCA_03.md','41c528a6a1fc21a85a1ea813d5ce502ff84826296edc74e3e499b0ce6a9594b2',837,
     ('IyBCX0NPREVYIOKAlCBhcHJvdmHDp8OjbyBDT0RFWCBkbyBhdG8gKGIpIEFERU5ET19FUE9DQV8wMwoKUHJpbWVpcmEgYXBy'
      'b3Zhw6fDo28gZGEgY2FkZWlhIEIgKENPREVYIOKGkiBGQUJMRSDihpIgRFVEVSkuIEFwcm92YSBvcyBieXRlcyBkbyBhdG8g'
      'KGIpIGN1am8gU0hBLTI1NiBlc3TDoSBlbSBgYm9keV9zaGFgLCBsaWdhZG8gYW8gZmltIGRhIGNhZGVpYSBkbyBhdG8gKGEp'
      'IGVtIGBhY3RfYV9oZWFkYC4gQnl0ZXMgZGV0ZXJtaW5hZG9zIHBlbG8gaGFzaCBkbyBhdG8gKGIpOiBzZW0gcmVsw7NnaW8g'
      'ZSBzZW0gY2FtcG8gbGl2cmUuCgo8IS0tIFIyRDItRVZJREVOQ0UtVjE6QkVHSU4gLS0+CmBgYGpzb24KeyJib2R5Ijp7ImFj'
      'dF9hX2hlYWQiOiIyZWU2ZGUyMTczMTZkZjY1NzdmNzUxZTIwOGJlNTIzOWMzNDgzOWY2MDZhYjEyYmIzOTIzNWU2NWMyOTQ4'
      'ZjVjIiwiYXV0aG9yaXplZF9zZXNzaW9ucyI6WyIyMDI2LTEwLTA1IiwiMjAyNi0xMC0wNiIsIjIwMjYtMTAtMDciLCIyMDI2'
      'LTEwLTA4IiwiMjAyNi0xMC0wOSJdLCJib2R5X3NoYSI6ImFiMjQxOTkzZGE5NTliMjJhOTFlODQwNTQ3YzZhYjExMzM0OTFk'
      'NTU4MDQzNzU2ZTNhZjUzMmJkOGQ0NmFhYWYiLCJkZWNpc2lvbiI6IkFQUFJPVkVEIiwiZXBvY2giOiJSMkQyLVYyLVNIQURP'
      'Vy0yMDI2LTEwLTA1IiwiZmlyc3Rfc2Vzc2lvbiI6IjIwMjYtMTAtMDUiLCJwcmV2aW91c19zaGEiOm51bGwsInJvbGUiOiJD'
      'T0RFWCJ9LCJraW5kIjoiQVBQUk9WQUwiLCJzY2hlbWEiOiJSMkQyX0RPQ1VNRU5UQVJZX0VWSURFTkNFX1YxIiwic3RhdGUi'
      'OiJJU1NVRUQifQpgYGAKPCEtLSBSMkQyLUVWSURFTkNFLVYxOkVORCAtLT4K')),
    ('B_FABLE','B_FABLE_ADENDO_EPOCA_03.md','254bcd757f24466f009c2b3ad50c3576da6fc87bd1a3186989f82e321fcd2e64',822,
     ('IyBCX0ZBQkxFIOKAlCBhcHJvdmHDp8OjbyBGQUJMRSBkbyBhdG8gKGIpIEFERU5ET19FUE9DQV8wMwoKU2VndW5kYSBhcHJv'
      'dmHDp8OjbyBkYSBjYWRlaWEgQi4gYHByZXZpb3VzX3NoYWAgw6kgbyBTSEEtMjU2IGRvIGFycXVpdm8gQl9DT0RFWC4gQnl0'
      'ZXMgZGV0ZXJtaW5hZG9zIHBlbG9zIGhhc2hlcyBkbyBhdG8gKGIpIGUgZG8gQl9DT0RFWDogc2VtIHJlbMOzZ2lvIGUgc2Vt'
      'IGNhbXBvIGxpdnJlLgoKPCEtLSBSMkQyLUVWSURFTkNFLVYxOkJFR0lOIC0tPgpgYGBqc29uCnsiYm9keSI6eyJhY3RfYV9o'
      'ZWFkIjoiMmVlNmRlMjE3MzE2ZGY2NTc3Zjc1MWUyMDhiZTUyMzljMzQ4MzlmNjA2YWIxMmJiMzkyMzVlNjVjMjk0OGY1YyIs'
      'ImF1dGhvcml6ZWRfc2Vzc2lvbnMiOlsiMjAyNi0xMC0wNSIsIjIwMjYtMTAtMDYiLCIyMDI2LTEwLTA3IiwiMjAyNi0xMC0w'
      'OCIsIjIwMjYtMTAtMDkiXSwiYm9keV9zaGEiOiJhYjI0MTk5M2RhOTU5YjIyYTkxZTg0MDU0N2M2YWIxMTMzNDkxZDU1ODA0'
      'Mzc1NmUzYWY1MzJiZDhkNDZhYWFmIiwiZGVjaXNpb24iOiJBUFBST1ZFRCIsImVwb2NoIjoiUjJEMi1WMi1TSEFET1ctMjAy'
      'Ni0xMC0wNSIsImZpcnN0X3Nlc3Npb24iOiIyMDI2LTEwLTA1IiwicHJldmlvdXNfc2hhIjoiNDFjNTI4YTZhMWZjMjFhODVh'
      'MWVhODEzZDVjZTUwMmZmODQ4MjYyOTZlZGM3NGUzZTQ5OWIwY2U2YTk1OTRiMiIsInJvbGUiOiJGQUJMRSJ9LCJraW5kIjoi'
      'QVBQUk9WQUwiLCJzY2hlbWEiOiJSMkQyX0RPQ1VNRU5UQVJZX0VWSURFTkNFX1YxIiwic3RhdGUiOiJJU1NVRUQifQpgYGAK'
      'PCEtLSBSMkQyLUVWSURFTkNFLVYxOkVORCAtLT4K')),
    ('B_DUDU','B_DUDU_ADENDO_EPOCA_03.md','c5938d35c106836adf3c93ec79b652852c156664354b05d0f95e82f77c162229',964,
     ('IyBCX0RVRFUg4oCUIGFwcm92YcOnw6NvIGRvIGRvbm8gZG8gYXRvIChiKSBBREVORE9fRVBPQ0FfMDMKClRlcmNlaXJhIGUg'
      'w7psdGltYSBhcHJvdmHDp8OjbyBkYSBjYWRlaWEgQi4gYHByZXZpb3VzX3NoYWAgw6kgbyBTSEEtMjU2IGRvIGFycXVpdm8g'
      'Ql9GQUJMRS4gYG93bmVyX2V2aWRlbmNlYCBndWFyZGEgYSByZXNwb3N0YSBsaXRlcmFsIGRvIGRvbm8sIG8gY2FuYWwgZSBh'
      'IGhvcmEgKFVUQykgZW0gcXVlIGVsYSBmb2kgZGFkYS4KCjwhLS0gUjJEMi1FVklERU5DRS1WMTpCRUdJTiAtLT4KYGBganNv'
      'bgp7ImJvZHkiOnsiYWN0X2FfaGVhZCI6IjJlZTZkZTIxNzMxNmRmNjU3N2Y3NTFlMjA4YmU1MjM5YzM0ODM5ZjYwNmFiMTJi'
      'YjM5MjM1ZTY1YzI5NDhmNWMiLCJhdXRob3JpemVkX3Nlc3Npb25zIjpbIjIwMjYtMTAtMDUiLCIyMDI2LTEwLTA2IiwiMjAy'
      'Ni0xMC0wNyIsIjIwMjYtMTAtMDgiLCIyMDI2LTEwLTA5Il0sImJvZHlfc2hhIjoiYWIyNDE5OTNkYTk1OWIyMmE5MWU4NDA1'
      'NDdjNmFiMTEzMzQ5MWQ1NTgwNDM3NTZlM2FmNTMyYmQ4ZDQ2YWFhZiIsImRlY2lzaW9uIjoiQVBQUk9WRUQiLCJlcG9jaCI6'
      'IlIyRDItVjItU0hBRE9XLTIwMjYtMTAtMDUiLCJmaXJzdF9zZXNzaW9uIjoiMjAyNi0xMC0wNSIsIm93bmVyX2V2aWRlbmNl'
      'Ijp7ImNoYW5uZWwiOiJBc2tVc2VyUXVlc3Rpb24gdmlhIEZhYmxlIiwic2lnbmVkX2F0X3V0YyI6IjIwMjYtMTAtMDRUMTc6'
      'MTc6MjVaIiwidmVyYmF0aW0iOiJBc3Npbm8gbyBhdG8gQiJ9LCJwcmV2aW91c19zaGEiOiIyNTRiY2Q3NTdmMjQ0NjZmMDA5'
      'YzJiM2FkNTBjMzU3NmRhNmZjODdiZDFhMzE4Njk4OWY4MmUzMjFmY2QyZTY0Iiwicm9sZSI6IkRVRFUifSwia2luZCI6IkFQ'
      'UFJPVkFMIiwic2NoZW1hIjoiUjJEMl9ET0NVTUVOVEFSWV9FVklERU5DRV9WMSIsInN0YXRlIjoiSVNTVUVEIn0KYGBgCjwh'
      'LS0gUjJEMi1FVklERU5DRS1WMTpFTkQgLS0+Cg==')),
)
# ---- CHAIN BLOCK END ----
# ---- WRITER BLOCK BEGIN (written by chain_block.py from the reviewed manifest_writer.py; never edited by hand) ----
K4_WRITER=('aeda5b12d34a406b0d61e1e4696e3c535e89fa3dc680ce0d3b14bb4d60b1d387',46977,
    ('IiIiQ2FwYWNpdHktZGF5IG1hbmlmZXN0IHdyaXRlcjogYWRtaXNzaW9uIGNvbW1pdCBhbmQgdGhlIGRhdGVkIGJhciBtYW5p'
     'ZmVzdCwgaW4gb25lIHByb2Nlc3MuCgpEZXBsb3ltZW50IHNjcmlwdC4gSXQgaXMgTk9UIHBhcnQgb2YgdGhlIHBpbm5lZCBp'
     'bXBsZW1lbnRhdGlvbiBwYWNrYWdlOiBpdCBsaXZlcyBpbgpjM3BvL2RlcGxveW1lbnQsIGlzIHBpbm5lZCBieSBTSEEtMjU2'
     'IGluIGVhY2ggYXV0aG9yaXNhdGlvbiwgYW5kIG9ubHkgaW1wb3J0cyBhbmQgY2FsbHMKdGhlIHBhY2thZ2VkIGNvZGUgb2Yg'
     'dGhlIGRlcGxveWVkIGltYWdlLiBSdW4gaXQgZnJvbSBhIHJlYWQtb25seSBiaW5kIG1vdW50IG9yIG9uCnN0YW5kYXJkIGlu'
     'cHV0OgoKICAgIHB5dGhvbiAtSSAtQiAtIDxhcmd1bWVudHM+IDwgbWFuaWZlc3Rfd3JpdGVyLnB5CgpPZmZsaW5lIGNhbmRp'
     'ZGF0ZTogbm90aGluZyBoZXJlIHdhcyBpbnN0YWxsZWQgb3IgcnVuIG9uIGEgaG9zdCBvciBpbiBhIGNvbnRhaW5lci4KCk9u'
     'ZSBpbnZvY2F0aW9uLCBmb3Igb25lIHNlc3Npb24gZGF0ZToKCiAgcHVibGlzaCAoZGVmYXVsdCkgIHByZS1mbGlnaHQsIHRo'
     'ZW4gKHdpdGggLS1wcmVwYXJlLWZpcnN0LCB3aGVuIHRoZSBkYXkncyBiaW5kaW5nIGlzIG5vdAogICAgICAgICAgICAgICAg'
     'ICAgICBjb21taXR0ZWQgeWV0KSBwcmVwYXJlLWNhcGFjaXR5LWRheSB0aHJvdWdoIHRoZSBwYWNrYWdlZCBjb2RlLCB0aGVu'
     'IHRoZQogICAgICAgICAgICAgICAgICAgICBleGNsdXNpdmUgcHVibGljYXRpb24gb2YgPG1hbmlmZXN0LWRpcmVjdG9yeT4v'
     'PGRheT4uanNvbjogdGhlIGNhbm9uaWNhbAogICAgICAgICAgICAgICAgICAgICBKU09OIG9mIERhaWx5Q2FwYWNpdHlCaW5k'
     'aW5nLmJhcl9tYW5pZmVzdCgpIG9mIHRoZSBjb21taXR0ZWQgYmluZGluZy4KICAtLXZlcmlmeS1vbmx5ICAgICAgY29tcGFy'
     'ZXMgdGhlIGV4aXN0aW5nIGZpbGUgd2l0aCB0aGUgY29tbWl0dGVkIGJpbmRpbmcuIE5ldmVyIHdyaXRlcywKICAgICAgICAg'
     'ICAgICAgICAgICAgbmV2ZXIgcmVwYWlycy4KICAtLXByZWZsaWdodCAgICAgICAgYnVpbGRzIHRoZSBzYW1lIGNvbnRleHQg'
     'YW5kIHZhbGlkYXRlcyBldmVyeXRoaW5nIHRoYXQgbmVlZHMgbmVpdGhlciB0aGUKICAgICAgICAgICAgICAgICAgICAgY2xv'
     'Y2sgbm9yIHRoZSB2ZXRvIHZpZXcuIE5ldmVyIHdhaXRzLCBwcmVwYXJlcywgd3JpdGVzIG9yIHJlYWRzIHRoZSB2aWV3LgoK'
     'VGhlIGZpbGUgaXMgY3JlYXRlZCBieSBwcml2YXRlIHRlbXBvcmFyeSArIGZzeW5jICsgbGluaygpICsgdW5saW5rLCBtb2Rl'
     'IDA2MDAsIGFuZCBpcyBuZXZlcgpvdmVyd3JpdHRlbiwgdHJ1bmNhdGVkIG9yIGRlbGV0ZWQuIFRoZSB0ZW1wb3JhcnkgaXMg'
     'Y3JlYXRlZCAoZW1wdHkpIGJlZm9yZSBhbnl0aGluZyBpcwpjb21taXR0ZWQsIHNvIGEgZGlyZWN0b3J5IHRoYXQgY2Fubm90'
     'IHRha2UgYSBuZXcgZmlsZSByZWZ1c2VzIHdpdGggbm90aGluZyBjb21taXR0ZWQuIFRoZQpvbmUgd3JpdGUgdGhhdCBuZWVk'
     'cyBubyBiYXJfbWFuaWZlc3QgR08gaXMgdGhlIHJlbW92YWwgb2YgdGhlIHNlY29uZCBuYW1lIGxlZnQgYnkgYQpwdWJsaWNh'
     'dGlvbiBpbnRlcnJ1cHRlZCBiZXR3ZWVuIGxpbmsoKSBhbmQgdW5saW5rKCksIGFuZCBvbmx5IGFmdGVyIHRoZSBieXRlcyB1'
     'bmRlciB0aGUKZmluYWwgbmFtZSB3ZXJlIGZvdW5kIGVxdWFsIHRvIHRoZSBtYW5pZmVzdCBvZiB0aGUgY29tbWl0dGVkIGJp'
     'bmRpbmcuCgpUaGUgbGlzdCBvZiBzeW1ib2xzIGlzIHdyaXR0ZW4gb25seSB0byB0aGF0IGZpbGUuIFN0YW5kYXJkIG91dHB1'
     'dCBjYXJyaWVzIGV4YWN0bHkgb25lIEpTT04KbGluZSB3aXRoIGNvdW50cywgaGFzaGVzLCBjbG9ja3MgYW5kIGNvbnN0YW50'
     'IGNvZGVzLiBBIHJlZnVzYWwgY29kZSBhbHdheXMgaG9sZHMgYW4KdW5kZXJzY29yZSwgd2hpY2ggbm8gc3ltYm9sIGNhbi4g'
     'VGhlIGRhdGFiYXNlIFVSTCBpcyByZWFkIGJ5IHRoZSBwYWNrYWdlZCBzZXR0aW5ncyBhbmQgaXMKbmV2ZXIgcHJpbnRlZCwg'
     'bmV2ZXIgYW4gYXJndW1lbnQsIGFuZCBuZXZlciBwYXJ0IG9mIGFuIGVycm9yIHRleHQgdGhhdCByZWFjaGVzIG91dHB1dC4K'
     'CkF1dGhvcml0eS4gVGhpcyBzY3JpcHQgaXNzdWVzIG5vIEdPLiBUaGUgZGF5J3MgYmFyX21hbmlmZXN0IEdPIGlzIGNoZWNr'
     'ZWQgYnkgdGhlIHBhY2thZ2VkCmRvY3VtZW50YXJ5IGF1dGhvcml0eSAoQWN0IEIgY2hhaW4sIHRoZSBkYXkncyB0ZW1wbGF0'
     'ZSwgR08gYW5kIHB1YmxpY2F0aW9uIHJlY29yZHMsIHRoZQpwaW5uZWQgdmV0byB2aWV3KTogYmVmb3JlIHRoZSBjb21taXQg'
     'YWdhaW5zdCB0aGUgcGxhbiBpbiB0aGUgZGF5J3MgcGF5bG9hZCBmaWxlLCBhbmQgYWdhaW4KaW1tZWRpYXRlbHkgYmVmb3Jl'
     'IGxpbmsoKSBhZ2FpbnN0IHRoZSBwbGFuIGZyb3plbiBpbiB0aGUgY29tbWl0dGVkIGJpbmRpbmcuCiIiIgpmcm9tIF9fZnV0'
     'dXJlX18gaW1wb3J0IGFubm90YXRpb25zCgppbXBvcnQgYXJncGFyc2UKZnJvbSBjb250ZXh0bGliIGltcG9ydCBjb250ZXh0'
     'bWFuYWdlcgppbXBvcnQgY29weQpmcm9tIGRhdGFjbGFzc2VzIGltcG9ydCBkYXRhY2xhc3MsIGZpZWxkCmZyb20gZGF0ZXRp'
     'bWUgaW1wb3J0IGRhdGUsIGRhdGV0aW1lLCB0aW1lZGVsdGEsIHRpbWV6b25lCmltcG9ydCBoYXNobGliCmltcG9ydCBpbXBv'
     'cnRsaWIKaW1wb3J0IGpzb24KaW1wb3J0IGxvZ2dpbmcKaW1wb3J0IG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBv'
     'cnQgcmUKaW1wb3J0IHNlY3JldHMKaW1wb3J0IHN0YXQKaW1wb3J0IHN5cwppbXBvcnQgdGltZQpmcm9tIHR5cGVzIGltcG9y'
     'dCBTaW1wbGVOYW1lc3BhY2UKZnJvbSB0eXBpbmcgaW1wb3J0IEFueSwgQ2FsbGFibGUsIEl0ZXJhdG9yCmltcG9ydCB3YXJu'
     'aW5ncwoKIyBXaGVyZSB0aGUgaW1hZ2Uga2VlcHMgdGhlIGFwcGxpY2F0aW9uLiBUaGUgb25seSBwYXRoIHRoaXMgc2NyaXB0'
     'IGFkZHMgdG8gc3lzLnBhdGgKIyAocHl0aG9uIC1JIGxlYXZlcyB0aGUgc2NyaXB0IGRpcmVjdG9yeSBhbmQgdGhlIGVudmly'
     'b25tZW50IG91dCBvZiBpdCkuCkFQUExJQ0FUSU9OX1JPT1QgPSAnL2FwcCcKClJFQ0VJUFRfU0NIRU1BID0gJ1IyRDJfVjJf'
     'QkFSX01BTklGRVNUX1dSSVRFUl9SRUNFSVBUX1YxJwpQSEFTRSwgQURNSVNTSU9OID0gJ2Jhcl9tYW5pZmVzdCcsICdhZG1p'
     'c3Npb24nCk1BWF9NQU5JRkVTVF9CWVRFUyA9IDY1NTM2ICAgICAgICAgICAgICAgICAgICMgdGhlIHN1cGVydmlzb3IncyBv'
     'd24gYm91bmQKTUFYX1NZTUJPTFMgPSA1NTAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIyB0aGUgcHJvZHVjZXIncyBv'
     'd24gYm91bmQKQ1VUT0ZGX0JFRk9SRV9PUEVOID0gdGltZWRlbHRhKG1pbnV0ZXM9MTApICAgIyAwOToyMCBOZXcgWW9yayBv'
     'biBhIHJlZ3VsYXIgZGF5Ck1BWF9XQUlUX1NFQ09ORFMgPSA5MDAgICAgICAgICAgICAgICAgICAgICAgICMgbG9uZ2VzdCBw'
     'YXJraW5nIGJlZm9yZSAtLXZpZXctb3BlbnMtYXQKVklFV19HUkFDRV9TRUNPTkRTID0gNS4wICAgICAgICAgICAgICAgICAg'
     'ICAgIyBhIHZpZXcgZW1pdHRlZCBpbi13aW5kb3cgbWF5IGxhZyB0aGlzIG11Y2gKIyBTdGF0ZXMgb2YgYSB2aWV3IGZpbGUg'
     'dGhhdCBpcyBzdGlsbCBiZWluZyBkZWxpdmVyZWQ7IHJldHJpZWQgb25seSBpbnNpZGUgdGhlIGdyYWNlLgpWSUVXX05PVF9Z'
     'RVQgPSBmcm96ZW5zZXQoeydWRVRPX0hBU0hfTUlTTUFUQ0gnLCAnUk9PVF9GSUxFX1BPTElDWScsICdST09UX0ZJTEVfQ0hB'
     'TkdFRCd9KQpFWElUX09LLCBFWElUX1VOVkVSSUZJRUQsIEVYSVRfUkVGVVNFRCA9IDAsIDEsIDMKR09fTU9ERVMgPSAoJ0lO'
     'RElWSURVQUwnLCAnREVMRUdBVEVEX0FDVF9CJykgICMgLS1yZXF1aXJlLWdvLW1vZGUKR09fRklFTERTID0gZnJvemVuc2V0'
     'KHsnZGVjaXNpb24nLCAnZXBvY2gnLCAnZmlyc3Rfc2Vzc2lvbicsICdkYXknLCAncGhhc2UnLCAncHJvcG9zYWxfc2hhJywg'
     'J3NpZ25lZF9vcmRlcl9zaGEnLAogICAgICAgICAgICAgICAgICAgICAgICd0ZW1wbGF0ZV9zaGEnLCAnbW9kZScsICdub3Rf'
     'YmVmb3JlJywgJ25vdF9hZnRlcicsICdhdXRvbWF0aWNfcmV0cnknLCAnYXV0aG9yaXR5X3JlY2VpcHRzJ30pCiMgQSBjb2Rl'
     'IGFsd2F5cyBob2xkcyBhbiB1bmRlcnNjb3JlOyB0aGUgc3ltYm9sIGdyYW1tYXIgKFtBLVowLTldW0EtWjAtOS4tXXswLDE5'
     'fSkgaGFzIG5vbmUuCl9DT0RFID0gcmUuY29tcGlsZShyJ1tBLVpdW0EtWjAtOV0qKD86X1tBLVowLTldKykrXFonKQpfU0hB'
     'ID0gcmUuY29tcGlsZShyJ1swLTlhLWZdezY0fVxaJykKX0VQT0NIID0gcmUuY29tcGlsZShyJ1tBLVphLXowLTldW0EtWmEt'
     'ejAtOV8uOi1dezAsOTV9XFonKSAgICMgdGhlIHByb2R1Y2VyJ3MgZXBvY2ggZ3JhbW1hcgpfVEVNUE9SQVJZID0gcidcLiVz'
     'XC5bMC05YS1mXXsxNn1cLnRtcFxaJwpfQVBQOiBTaW1wbGVOYW1lc3BhY2UgfCBOb25lID0gTm9uZQoKCmNsYXNzIFJlZnVz'
     'ZWQoVmFsdWVFcnJvcik6CiAgICAiIiJPbmUgY29uc3RhbnQgY29kZTsgbmV2ZXIgaW5wdXQsIGEgcGF0aCBvciBhIHN5bWJv'
     'bC4iIiIKCgpkZWYgbmVlZChjb25kaXRpb246IEFueSwgY29kZTogc3RyKSAtPiBOb25lOgogICAgaWYgbm90IGNvbmRpdGlv'
     'bjoKICAgICAgICByYWlzZSBSZWZ1c2VkKGNvZGUpCgoKZGVmIHBhY2thZ2VkKCkgLT4gU2ltcGxlTmFtZXNwYWNlOgogICAg'
     'IiIiVGhlIGRlcGxveWVkIGltYWdlJ3Mgb3duIGNvZGUsIGltcG9ydGVkIG9uY2UgZnJvbSBBUFBMSUNBVElPTl9ST09UIGFu'
     'ZCBub3doZXJlIGVsc2UuIiIiCiAgICBnbG9iYWwgX0FQUAogICAgaWYgX0FQUCBpcyBOb25lOgogICAgICAgIGlmIEFQUExJ'
     'Q0FUSU9OX1JPT1Qgbm90IGluIHN5cy5wYXRoOgogICAgICAgICAgICBzeXMucGF0aC5pbnNlcnQoMCwgQVBQTElDQVRJT05f'
     'Uk9PVCkKICAgICAgICBzdG9yZSA9IGltcG9ydGxpYi5pbXBvcnRfbW9kdWxlKCdhcHAucjJkMl92Ml9zdG9yZScpCiAgICAg'
     'ICAgb3JpZ2luID0gb3MucGF0aC5kaXJuYW1lKG9zLnBhdGguZGlybmFtZShvcy5wYXRoLnJlYWxwYXRoKHN0cihzdG9yZS5f'
     'X2ZpbGVfXykpKSkKICAgICAgICBuZWVkKG9yaWdpbiA9PSBvcy5wYXRoLnJlYWxwYXRoKEFQUExJQ0FUSU9OX1JPT1QpLCAn'
     'TUFOSUZFU1RfQVBQTElDQVRJT05fUk9PVCcpCiAgICAgICAgZnJvbSBhcHAucjJkMl92Ml9jYWxlbmRhciBpbXBvcnQgTkVX'
     'X1lPUksKICAgICAgICBmcm9tIGFwcC5yMmQyX3YyX2NhcGFjaXR5X2F1dGhvcml0eSBpbXBvcnQgdmFsaWRhdGVfY29udHJh'
     'Y3QKICAgICAgICBmcm9tIGFwcC5yMmQyX3YyX2NhcGFjaXR5X2JvdW5kIGltcG9ydCBEYWlseUNhcGFjaXR5QmluZGluZwog'
     'ICAgICAgIGZyb20gYXBwLnIyZDJfdjJfZXBvY2hfYXNzZW1ibGVyIGltcG9ydCBkaWdlc3QgYXMgZ29fZGlnZXN0LCBpc19z'
     'aGEsIHN0YW1wLCB2YWxpZGF0ZV9nbwogICAgICAgIGZyb20gYXBwLnIyZDJfdjJfbWFzc2l2ZV9zdXBlcnZpc29yIGltcG9y'
     'dCBwcml2YXRlX2J5dGVzCiAgICAgICAgZnJvbSBhcHAucjJkMl92Ml9taW51dGVfYmFycyBpbXBvcnQgX1NZTUJPTAogICAg'
     'ICAgIGZyb20gYXBwLnIyZDJfdjJfc291cmNlcyBpbXBvcnQgX2xvYWRfanNvbiwgX29wZW5fZGlyZWN0b3J5CiAgICAgICAg'
     'X0FQUCA9IFNpbXBsZU5hbWVzcGFjZSgKICAgICAgICAgICAgTkVXX1lPUks9TkVXX1lPUkssIHZhbGlkYXRlX2NvbnRyYWN0'
     'PXZhbGlkYXRlX2NvbnRyYWN0LCBEYWlseUNhcGFjaXR5QmluZGluZz1EYWlseUNhcGFjaXR5QmluZGluZywKICAgICAgICAg'
     'ICAgZ29fZGlnZXN0PWdvX2RpZ2VzdCwgaXNfc2hhPWlzX3NoYSwgc3RhbXA9c3RhbXAsIHZhbGlkYXRlX2dvPXZhbGlkYXRl'
     'X2dvLCBwcml2YXRlX2J5dGVzPXByaXZhdGVfYnl0ZXMsCiAgICAgICAgICAgIHN5bWJvbD1fU1lNQk9MLCBsb2FkX2pzb249'
     'X2xvYWRfanNvbiwgb3Blbl9kaXJlY3Rvcnk9X29wZW5fZGlyZWN0b3J5LCBjYW5vbmljYWw9c3RvcmUuY2Fub25pY2FsLAog'
     'ICAgICAgICAgICB1dGM9c3RvcmUudXRjKQogICAgcmV0dXJuIF9BUFAKCgpAZGF0YWNsYXNzCmNsYXNzIENvbnRleHQ6CiAg'
     'ICAiIiJFdmVyeXRoaW5nIHRoZSB3cml0ZXIgY29uc3VtZXMsIGFscmVhZHkgYm91bmQgdG8gdGhlIHZlcmlmaWVkIHJlbGVh'
     'c2UuIiIiCiAgICByZWxlYXNlOiBBbnkgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAjIHZlcmlmaWVkIFJl'
     'bGVhc2UKICAgIGNhbGVuZGFyOiBBbnkgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICMgU2hhZG93Q2FsZW5k'
     'YXIKICAgIHJlYWRfc3RhdGU6IENhbGxhYmxlW1tdLCBkaWN0IHwgTm9uZV0gICAgICAgICAgICMgc3RvcmUucmVhZChlcG9j'
     'aCk7IHZlcmlmaWVzIHRoZSBzdGF0ZSBoYXNoCiAgICB2ZXJpZnlfYmluZGluZzogQ2FsbGFibGVbW2RpY3RdLCBib29sXSAg'
     'ICAgICAgICAjIEFjdCBCIGNoYWluIGZvciBhIGJpbmRpbmcgZG9jdW1lbnQKICAgIHZlcmlmeV9nbzogQ2FsbGFibGVbW2Rp'
     'Y3QsIGRpY3RdLCBib29sXSAgICAgICAgICMgZG9jdW1lbnRhcnkgR08gKyBwdWJsaWNhdGlvbiArIHZldG8gdmlldwogICAg'
     'dmVyaWZ5X2NoYWluOiBDYWxsYWJsZVtbc3RyXSwgTm9uZV0gICAgICAgICAgICAgIyBBY3QgQS9CIGNoYWluIGZvciB0aGUg'
     'ZGF5OyByYWlzZXMgYSBjb2RlCiAgICBjaGVja19nbzogQ2FsbGFibGVbW2RpY3QsIGRpY3RdLCBOb25lXSAgICAgICAgICAj'
     'IChHTywgcGxhbik6IGV2ZXJ5IGRvY3VtZW50IGJlaGluZCBhIEdPLCB3aXRob3V0IHRoZSB2aWV3CiAgICByZWFkX2dvOiBD'
     'YWxsYWJsZVtbc3RyLCBzdHJdLCBkaWN0XSAgICAgICAgICAgICAjIChkYXksIHBoYXNlKSAtPiB0aGUgMTMtZmllbGQgR08K'
     'ICAgIHJlYWRfcGF5bG9hZDogQ2FsbGFibGVbW3N0cl0sIGRpY3RdICAgICAgICAgICAgICMgZGF5IC0+IHsnY29udHJhY3Qn'
     'LCAnY2F1c2FsJ30KICAgIHZpZXdfcGlubmVkOiBDYWxsYWJsZVtbc3RyXSwgYm9vbF0gICAgICAgICAgICAgICMgdGhlIGNh'
     'cGFjaXR5IGNvbmZpZyBwaW5zIGEgdmlldyBmb3IgdGhlIGRheQogICAgdmV0b19ib3VuZHM6IENhbGxhYmxlW1tzdHJdLCB0'
     'dXBsZVtkYXRldGltZSwgZGF0ZXRpbWVdXSAgICMgcGlubmVkIHZpZXc6IG9ic2VydmVkX2F0LCB2YWxpZF91bnRpbAogICAg'
     'cHJlcGFyZTogQ2FsbGFibGVbW3N0cl0sIGRpY3RdIHwgTm9uZSA9IE5vbmUgICAgIyBvbmx5IHdpdGggLS1wcmVwYXJlLWZp'
     'cnN0CiAgICBwaW5zOiBkaWN0ID0gZmllbGQoZGVmYXVsdF9mYWN0b3J5PWRpY3QpICAgICAgICAjIG5vbi1zZWNyZXQgaWRl'
     'bnRpZmllcnMgZWNob2VkIGluIHRoZSByZWNlaXB0CiAgICBwcm90ZWN0ZWQ6IHR1cGxlID0gKCkgICAgICAgICAgICAgICAg'
     'ICAgICAgICAgICAjIGNvbmZpZ3VyZWQgcm9vdHMgdGhlIG1hbmlmZXN0IGRpcmVjdG9yeSBtdXN0IG5vdCB0b3VjaAoKCmRl'
     'ZiBfY29kZShlcnJvcjogQmFzZUV4Y2VwdGlvbikgLT4gc3RyIHwgTm9uZToKICAgIGlmIChpc2luc3RhbmNlKGVycm9yLCBW'
     'YWx1ZUVycm9yKSBhbmQgbGVuKGVycm9yLmFyZ3MpID09IDEgYW5kIHR5cGUoZXJyb3IuYXJnc1swXSkgaXMgc3RyCiAgICAg'
     'ICAgICAgIGFuZCBfQ09ERS5tYXRjaChlcnJvci5hcmdzWzBdKSk6CiAgICAgICAgcmV0dXJuIGVycm9yLmFyZ3NbMF0KICAg'
     'IHJldHVybiBOb25lCgoKZGVmIHJlZnVzYWwoZXJyb3I6IEJhc2VFeGNlcHRpb24pIC0+IHR1cGxlW3N0ciwgaW50XToKICAg'
     'ICIiIkNvbnN0YW50IGNvZGVzIG9ubHkuIEFueXRoaW5nIHRoYXQgaXMgbm90IGEgcmV2aWV3ZWQgY29kZSBpcyBVTlZFUklG'
     'SUVELiIiIgogICAgY29kZSA9IF9jb2RlKGVycm9yKQogICAgaWYgY29kZSBpcyBub3QgTm9uZToKICAgICAgICByZXR1cm4g'
     'Y29kZSwgRVhJVF9SRUZVU0VECiAgICBpZiBpc2luc3RhbmNlKGVycm9yLCBJbXBvcnRFcnJvcik6CiAgICAgICAgcmV0dXJu'
     'ICdNQU5JRkVTVF9BUFBMSUNBVElPTl9VTkFWQUlMQUJMRScsIEVYSVRfVU5WRVJJRklFRAogICAgaWYgdHlwZShlcnJvciku'
     'X19tb2R1bGVfXy5zcGxpdCgnLicpWzBdID09ICdwc3ljb3BnJzoKICAgICAgICByZXR1cm4gJ01BTklGRVNUX0RBVEFCQVNF'
     'X1VOQVZBSUxBQkxFJywgRVhJVF9VTlZFUklGSUVECiAgICBpZiBpc2luc3RhbmNlKGVycm9yLCBPU0Vycm9yKToKICAgICAg'
     'ICByZXR1cm4gJ01BTklGRVNUX0ZJTEVfVU5BVkFJTEFCTEUnLCBFWElUX1VOVkVSSUZJRUQKICAgIHJldHVybiAnTUFOSUZF'
     'U1RfVU5WRVJJRklFRCcsIEVYSVRfVU5WRVJJRklFRAoKCmRlZiBfY29kZWQoZnVuY3Rpb246IENhbGxhYmxlW1tdLCBBbnld'
     'LCBjb2RlOiBzdHIsIG1pc3Npbmc6IHN0ciB8IE5vbmUgPSBOb25lKSAtPiBBbnk6CiAgICAiIiJSdW4gYSByZWFkIG9yIGEg'
     'c3RydWN0dXJhbCBjaGVjazsgYW55dGhpbmcgdGhhdCBpcyBub3QgYWxyZWFkeSBhIGNvZGUgYmVjb21lcyBgY29kZWAuIiIi'
     'CiAgICB0cnk6CiAgICAgICAgcmV0dXJuIGZ1bmN0aW9uKCkKICAgIGV4Y2VwdCBGaWxlTm90Rm91bmRFcnJvcjoKICAgICAg'
     'ICByYWlzZSBSZWZ1c2VkKG1pc3Npbmcgb3IgY29kZSkgZnJvbSBOb25lCiAgICBleGNlcHQgT1NFcnJvcjoKICAgICAgICBy'
     'YWlzZQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlcnJvcjoKICAgICAgICBpZiBfY29kZShlcnJvcikgaXMgbm90IE5vbmU6'
     'CiAgICAgICAgICAgIHJhaXNlCiAgICAgICAgcmFpc2UgUmVmdXNlZChjb2RlKSBmcm9tIE5vbmUKCgpkZWYgX3N0cnVjdHVy'
     'ZV9vbmx5KF9nbzogZGljdCwgX3BsYW46IGRpY3QpIC0+IGJvb2w6CiAgICAiIiJTdGFuZC1pbiBmb3IgdGhlIGF1dGhvcml0'
     'eSBpbiBzdGF0aWNfZ28gT05MWS4gTm8gZ2F0ZSB1c2VzIGl0LiIiIgogICAgcmV0dXJuIFRydWUKCgpkZWYgc3RhdGljX2dv'
     'KGdvOiBBbnksIHBsYW46IEFueSwgKiwgZGF5OiBzdHIsIHBoYXNlOiBzdHIpIC0+IHR1cGxlW2RhdGV0aW1lLCBkYXRldGlt'
     'ZV06CiAgICAiIiJJcyB0aGlzIEdPIHdlbGwgZm9ybWVkIGZvciB0aGUgZGF5J3MgcGxhbj8gVGhlIHBhY2thZ2VkIHZhbGlk'
     'YXRvciwgd2l0aG91dCBjbG9jayBvciBhdXRob3JpdHkuCgogICAgVGhlIGNsb2NrIGlzIHBsYWNlZCBhdCB0aGUgR08ncyBv'
     'd24gbm90X2JlZm9yZSBhbmQgdGhlIGF1dGhvcml0eSBpcyByZXBsYWNlZCBieSBhCiAgICBzdGFuZC1pbiwgc28gdGhlIGFu'
     'c3dlciBjb3ZlcnMgdGhlIDEzIGZpZWxkcywgZGF5LCBwaGFzZSwgcGxhbiBoYXNoLCBvcmRlciBhbmQgdGVtcGxhdGUKICAg'
     'IGhhc2hlcywgdGhlIHBoYXNlIHdpbmRvdyBhbmQgdGhlIG5vdGljZS4gVGhlIHJlc3VsdCBpcyBkaXNjYXJkZWQ6IG5vdGhp'
     'bmcgaXMgcHJlcGFyZWQsCiAgICB3cml0dGVuIG9yIHB1Ymxpc2hlZCBvbiBpdCAoc2VlIF9nYXRlKS4gUmV0dXJucyB0aGUg'
     'R08gd2luZG93LgogICAgIiIiCiAgICBhcHAgPSBwYWNrYWdlZCgpCiAgICBuZWVkKHR5cGUoZ28pIGlzIGRpY3QgYW5kIHNl'
     'dChnbykgPT0gR09fRklFTERTLCAnTUFOSUZFU1RfR09fRklFTERTJykKCiAgICBkZWYgY2hlY2soKSAtPiB0dXBsZVtkYXRl'
     'dGltZSwgZGF0ZXRpbWVdOgogICAgICAgIHByb3Bvc2FsID0gcGxhblsncHJvcG9zYWwnXQogICAgICAgIG5lZWQocHJvcG9z'
     'YWxbJ3BoYXNlJ10gPT0gcGhhc2UgYW5kIHByb3Bvc2FsWydkYWlseSddWydkYXknXSA9PSBkYXksICdNQU5JRkVTVF9QTEFO'
     'X0RBWV9QSEFTRScpCiAgICAgICAgYXBwLnZhbGlkYXRlX2dvKGdvLCBwbGFuLCBub3c9YXBwLnN0YW1wKGdvWydub3RfYmVm'
     'b3JlJ10pLCBhdXRob3JpdHlfdmVyaWZpZXI9X3N0cnVjdHVyZV9vbmx5KQogICAgICAgIHJldHVybiBhcHAudXRjKGdvWydu'
     'b3RfYmVmb3JlJ10pLCBhcHAudXRjKGdvWydub3RfYWZ0ZXInXSkKCiAgICByZXR1cm4gX2NvZGVkKGNoZWNrLCAnTUFOSUZF'
     'U1RfR09fSU5WQUxJRCcpCgoKZGVmIGdvX3JlY29yZHMoYXV0aG9yaXR5OiBBbnksIGdvOiBkaWN0KSAtPiBOb25lOgogICAg'
     'IiIiUGlubmVkIGRvY3VtZW50YXJ5IHJlY29yZHMgYmVoaW5kIG9uZSBHTywgd2l0aG91dCB0aGUgdmV0byB2aWV3LgoKICAg'
     'IEVhY2ggY29uZGl0aW9uIGlzIGEgbmVjZXNzYXJ5IG9uZSBvZiB0aGUgcGFja2FnZWQgdmVyaWZ5X2dvLCBzbyB0aGlzIGNh'
     'biByZWZ1c2UgZWFybHkKICAgIHdpdGggYSBwcmVjaXNlIGNvZGUgYnV0IGNhbiBuZXZlciBhY2NlcHQgd2hhdCB2ZXJpZnlf'
     'Z28gd291bGQgcmVmdXNlLgogICAgIiIiCiAgICBhcHAgPSBwYWNrYWdlZCgpCgogICAgZGVmIGNoZWNrKCkgLT4gTm9uZToK'
     'ICAgICAgICBwaGFzZSwgcmVjZWlwdHMgPSBnb1sncGhhc2UnXSwgZ29bJ2F1dGhvcml0eV9yZWNlaXB0cyddCiAgICAgICAg'
     'dGVtcGxhdGUsIHJlY29yZCA9IGF1dGhvcml0eS5yZWNvcmQoJ1RFTVBMQVRFJyksIGF1dGhvcml0eS5yZWNvcmQoJ0dPOicg'
     'KyBwaGFzZSkKICAgICAgICBuZWVkKHJlY29yZFsnZ29fc2hhJ10gPT0gYXBwLmdvX2RpZ2VzdChnbykgYW5kIHJlY29yZFsn'
     'ZGVjaXNpb24nXSA9PSAnR08nCiAgICAgICAgICAgICBhbmQgcmVjb3JkWyd0ZW1wbGF0ZV9zaGEnXSA9PSBnb1sndGVtcGxh'
     'dGVfc2hhJ10gPT0gdGVtcGxhdGVbJ3NoYSddLCAnTUFOSUZFU1RfR09fUkVDT1JEJykKICAgICAgICBpZiBnb1snbW9kZSdd'
     'ID09ICdERUxFR0FURURfQUNUX0InOgogICAgICAgICAgICBwdWJsaWNhdGlvbiA9IGF1dGhvcml0eS5yZWNvcmQoJ1BVQkxJ'
     'Q0FUSU9OOicgKyBwaGFzZSkKICAgICAgICAgICAgbmVlZChyZWNlaXB0c1sncHVibGljYXRpb25fcmVjZWlwdF9zaGEnXSA9'
     'PSBhdXRob3JpdHkucGluc1snUFVCTElDQVRJT046JyArIHBoYXNlXVsnc2hhMjU2J10KICAgICAgICAgICAgICAgICBhbmQg'
     'cHVibGljYXRpb25bJ3B1Ymxpc2hlZF9hdCddID09IHJlY29yZFsncHVibGlzaGVkX2F0J10gPT0gcmVjZWlwdHNbJ3B1Ymxp'
     'c2hlZF9hdCddLAogICAgICAgICAgICAgICAgICdNQU5JRkVTVF9HT19SRUNPUkQnKQoKICAgIF9jb2RlZChjaGVjaywgJ01B'
     'TklGRVNUX0dPX1JFQ09SRCcsIG1pc3Npbmc9J01BTklGRVNUX0dPX1JFQ09SRF9NSVNTSU5HJykKCgpkZWYgX25vX3ZpZXco'
     'bm93OiBkYXRldGltZSkgLT4gZGljdDoKICAgICIiIlN0YW5kLWluIGZvciB0aGUgdmV0byB2aWV3IGluIHN0YXRpY19kb2N1'
     'bWVudHMgT05MWS4gTm8gZ2F0ZSB1c2VzIGl0LiIiIgogICAgcmV0dXJuIHsnc3RhdHVzJzogJ1ZFUklGSUVEJywgJ29ic2Vy'
     'dmVkX2F0Jzogbm93Lmlzb2Zvcm1hdCgpLAogICAgICAgICAgICAndmFsaWRfdW50aWwnOiAobm93ICsgdGltZWRlbHRhKHNl'
     'Y29uZHM9MTApKS5pc29mb3JtYXQoKSwgJ293bmVyX3ZldG8nOiBGYWxzZSwgJ3Jldm9rZWRfc2hhcyc6IFtdfQoKCmRlZiBz'
     'dGF0aWNfZG9jdW1lbnRzKGF1dGhvcml0eTogQW55LCBnbzogZGljdCwgcGxhbjogZGljdCkgLT4gTm9uZToKICAgICIiIldv'
     'dWxkIHRoZSBkb2N1bWVudHMgYmVoaW5kIHRoaXMgR08gcGFzcyB0aGUgcGFja2FnZWQgdmVyaWZ5X2dvPyBXaXRob3V0IGNs'
     'b2NrIG9yIHZpZXcuCgogICAgVGhlIHBhY2thZ2VkIHZlcmlmeV9nbyBpdHNlbGYsIG9uIGEgY29weSBvZiB0aGUgYXV0aG9y'
     'aXR5IHdob3NlIHZldG8gdmlldyBpcyBhIHN0YW5kLWluCiAgICBvcGVuIGF0IHRoZSBHTydzIG93biBub3RfYmVmb3JlLiBJ'
     'dCBjb3ZlcnMgd2hhdCBuZWVkcyBuZWl0aGVyIHRoZSBjbG9jayBub3IgdGhlIHJlYWwKICAgIHZpZXc6IHRoZSBBY3QgQSBh'
     'bmQgQWN0IEIgY2hhaW5zLCB0aGUgb3JkZXIgaGFzaCwgdGhlIHRlbXBsYXRlJ3MgbWVtYmVyc2hpcCBhbmQgc2NvcGUsCiAg'
     'ICB0aGUgR08gcmVjb3JkJ3Mgc2NvcGUsIHJvbGUgYW5kIGJpbmRpbmcsIHRoZSBwdWJsaWNhdGlvbiByZWNvcmQgYW5kIHRo'
     'ZSBub3RpY2UuIFRoZQogICAgcmVzdWx0IGlzIGRpc2NhcmRlZDogbm90aGluZyBpcyBwcmVwYXJlZCwgd3JpdHRlbiBvciBw'
     'dWJsaXNoZWQgb24gaXQgKHNlZSBfZ2F0ZSwgd2hpY2gKICAgIGFza3MgdGhlIHJlYWwgYXV0aG9yaXR5IHdpdGggdGhlIHJl'
     'YWwgdmlldykuCiAgICAiIiIKICAgIGJsaW5kID0gY29weS5jb3B5KGF1dGhvcml0eSkKICAgIGJsaW5kLnJldm9jYXRpb25f'
     'cmVhZGVyID0gX25vX3ZpZXcKICAgIG5lZWQoYmxpbmQudmVyaWZ5X2dvKGdvLCBwbGFuLCBwYWNrYWdlZCgpLnN0YW1wKGdv'
     'Wydub3RfYmVmb3JlJ10pKSBpcyBUcnVlLCAnTUFOSUZFU1RfR09fRE9DVU1FTlRTJykKCgpkZWYgbWFuaWZlc3RfYnl0ZXMo'
     'bWFuaWZlc3Q6IEFueSwgKiwgZGF5OiBzdHIsIGVwb2NoOiBzdHIpIC0+IGJ5dGVzOgogICAgIiIiRXZlcnkgY2hlY2sgdGhl'
     'IHByb2R1Y2VyIGFwcGxpZXMgYWZ0ZXIgdGhlIGNsYWltLCBhcHBsaWVkIGJlZm9yZSBwdWJsaXNoaW5nLgoKICAgIEEgbWFu'
     'aWZlc3QgdGhhdCBwYXNzZXMgdGhlIHN1cGVydmlzb3IgYnV0IGZhaWxzIHRoZSBwcm9kdWNlciBjb3N0cyBhbGwgZml2ZSBj'
     'bGFpbXMgb2YKICAgIHRoZSBkYXksIHNvIHRoZSBwcm9kdWNlcidzIGdyYW1tYXIgaXMgZW5mb3JjZWQgaGVyZSBpbiBmdWxs'
     'LgogICAgIiIiCiAgICBhcHAgPSBwYWNrYWdlZCgpCiAgICBuZWVkKHR5cGUobWFuaWZlc3QpIGlzIGRpY3QgYW5kIHNldCht'
     'YW5pZmVzdCkgPT0geydlcG9jaCcsICdzZXNzaW9uJywgJ3N5bWJvbHMnLCAnb3duZXJfdWlkJ30sICdNQU5JRkVTVF9GSUVM'
     'RFMnKQogICAgbmVlZCh0eXBlKG1hbmlmZXN0Wydvd25lcl91aWQnXSkgaXMgaW50IGFuZCBtYW5pZmVzdFsnb3duZXJfdWlk'
     'J10gPT0gb3MuZ2V0ZXVpZCgpLCAnTUFOSUZFU1RfT1dORVInKQogICAgbmVlZCh0eXBlKG1hbmlmZXN0WydlcG9jaCddKSBp'
     'cyBzdHIgYW5kIF9FUE9DSC5tYXRjaChtYW5pZmVzdFsnZXBvY2gnXSkgYW5kIG1hbmlmZXN0WydlcG9jaCddID09IGVwb2No'
     'LAogICAgICAgICAnTUFOSUZFU1RfRVBPQ0gnKQogICAgbmVlZChtYW5pZmVzdFsnc2Vzc2lvbiddID09IGRheSwgJ01BTklG'
     'RVNUX1NFU1NJT04nKQogICAgc3ltYm9scyA9IG1hbmlmZXN0WydzeW1ib2xzJ10KICAgIG5lZWQodHlwZShzeW1ib2xzKSBp'
     'cyBsaXN0LCAnTUFOSUZFU1RfU1lNQk9MUycpCiAgICBuZWVkKGxlbihzeW1ib2xzKSA+IDAsICdNQU5JRkVTVF9TWU1CT0xT'
     'X0VNUFRZJykKICAgIG5lZWQobGVuKHN5bWJvbHMpIDw9IE1BWF9TWU1CT0xTIGFuZCBhbGwodHlwZShzKSBpcyBzdHIgYW5k'
     'IGFwcC5zeW1ib2wuZnVsbG1hdGNoKHMpIGZvciBzIGluIHN5bWJvbHMpCiAgICAgICAgIGFuZCBsZW4oc2V0KHN5bWJvbHMp'
     'KSA9PSBsZW4oc3ltYm9scyksICdNQU5JRkVTVF9TWU1CT0xTJykKICAgIGRhdGEgPSBhcHAuY2Fub25pY2FsKG1hbmlmZXN0'
     'KSAgICAgICAgICAgICAgICMgc29ydGVkIGtleXMsIGNvbXBhY3QsIEFTQ0lJLCBubyB0cmFpbGluZyBuZXdsaW5lCiAgICBu'
     'ZWVkKDAgPCBsZW4oZGF0YSkgPD0gTUFYX01BTklGRVNUX0JZVEVTIGFuZCBhcHAubG9hZF9qc29uKGRhdGEpID09IG1hbmlm'
     'ZXN0LCAnTUFOSUZFU1RfRU5DT0RJTkcnKQogICAgcmV0dXJuIGRhdGEKCgpkZWYgX3BlcnNpc3RlZChyb3c6IGRpY3QgfCBO'
     'b25lLCBkYXk6IHN0cikgLT4gZGljdCB8IE5vbmU6CiAgICAiIiJUaGUgYmluZGluZyBjb21taXR0ZWQgYnkgcHJlcGFyZS1j'
     'YXBhY2l0eS1kYXksIG9yIE5vbmUgd2hlbiBpdCBpcyBtaXNzaW5nLiIiIgogICAgaWYgcm93IGlzIE5vbmU6CiAgICAgICAg'
     'cmV0dXJuIE5vbmUKICAgIHN0YXRlID0gcm93WydzdGF0ZSddCiAgICBwcmVwYXJlZCA9IHN0YXRlLmdldCgnZGFpbHlfY2Fw'
     'YWNpdHknLCB7fSkuZ2V0KGRheSkKICAgIG9wZW5lZCA9IHN0YXRlLmdldCgnc2Vzc2lvbnMnLCB7fSkuZ2V0KGRheSwge30p'
     'LmdldCgnY2FwYWNpdHlfYmluZGluZycpCiAgICBuZWVkKG9wZW5lZCBpcyBOb25lIG9yIG9wZW5lZCA9PSBwcmVwYXJlZCwg'
     'J01BTklGRVNUX0JJTkRJTkdfRElWRVJHRUQnKQogICAgcmV0dXJuIHByZXBhcmVkCgoKZGVmIF9yZXN0b3JlKGN0eDogQ29u'
     'dGV4dCwgcGVyc2lzdGVkOiBkaWN0KSAtPiBBbnk6CiAgICByZXR1cm4gcGFja2FnZWQoKS5EYWlseUNhcGFjaXR5QmluZGlu'
     'Zy5yZXN0b3JlKHBlcnNpc3RlZCwgcmVsZWFzZT1jdHgucmVsZWFzZSwgY2FsZW5kYXI9Y3R4LmNhbGVuZGFyLAogICAgICAg'
     'ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBhdXRob3JpdHlfdmVyaWZpZXI9Y3R4LnZlcmlm'
     'eV9iaW5kaW5nKQoKCmRlZiBfbWFuaWZlc3QoY3R4OiBDb250ZXh0LCBiaW5kaW5nOiBBbnksIHJvdzogZGljdCwgZGF5OiBz'
     'dHIsIGNsb2NrOiBDYWxsYWJsZVtbXSwgZGF0ZXRpbWVdKSAtPiB0dXBsZVtieXRlcywgaW50XToKICAgIG1hbmlmZXN0ID0g'
     'YmluZGluZy5iYXJfbWFuaWZlc3Qob3duZXJfdWlkPW9zLmdldGV1aWQoKSwgc3RhdGU9cm93WydzdGF0ZSddLCBjdXJyZW50'
     'X2RheT1kYXksIG5vdz1jbG9jaygpLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBjYWxlbmRhcj1jdHgu'
     'Y2FsZW5kYXIpCiAgICByZXR1cm4gbWFuaWZlc3RfYnl0ZXMobWFuaWZlc3QsIGRheT1kYXksIGVwb2NoPWN0eC5yZWxlYXNl'
     'LmVwb2NoKSwgbGVuKG1hbmlmZXN0WydzeW1ib2xzJ10pCgoKZGVmIF9wYXlsb2FkX2NvbnRyYWN0KGN0eDogQ29udGV4dCwg'
     'ZGF5OiBzdHIpIC0+IGRpY3Q6CiAgICAiIiJUaGUgY29udHJhY3Qgb2YgdGhlIGRheSdzIHBheWxvYWQgZmlsZSwgdmFsaWRh'
     'dGVkIGJ5IHRoZSBwYWNrYWdlZCBjb250cmFjdCBjaGVjay4iIiIKICAgIHBheWxvYWQgPSBjdHgucmVhZF9wYXlsb2FkKGRh'
     'eSkKICAgIG5lZWQodHlwZShwYXlsb2FkKSBpcyBkaWN0IGFuZCBzZXQocGF5bG9hZCkgPT0geydjb250cmFjdCcsICdjYXVz'
     'YWwnfSwgJ0NBUEFDSVRZX0lOUFVUX0ZJRUxEUycpCiAgICByZXR1cm4gcGFja2FnZWQoKS52YWxpZGF0ZV9jb250cmFjdChw'
     'YXlsb2FkWydjb250cmFjdCddLCByZWxlYXNlPWN0eC5yZWxlYXNlLCBkYXk9ZGF5LCBjYXVzYWw9cGF5bG9hZFsnY2F1c2Fs'
     'J10sCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBjYWxlbmRhcj1jdHguY2FsZW5kYXIpCgoKZGVm'
     'IF9wYXJrKG9wZW5zX2F0OiBkYXRldGltZSB8IE5vbmUsICosIGNsb2NrLCBzbGVlcCwgbW9ub3RvbmljLCBtYXhpbXVtOiBp'
     'bnQpIC0+IGZsb2F0OgogICAgIiIiU2xlZXAgdW50aWwgdGhlIGRlY2xhcmVkIGluc3RhbnQuIFRoZSB2aWV3IGZpbGUgaXMg'
     'bm90IHJlYWQgaGVyZS4iIiIKICAgIGJlZ2FuID0gY2xvY2soKQogICAgaWYgb3BlbnNfYXQgaXMgTm9uZSBvciBiZWdhbiA+'
     'PSBvcGVuc19hdDoKICAgICAgICByZXR1cm4gMC4wCiAgICBuZWVkKChvcGVuc19hdCAtIGJlZ2FuKS50b3RhbF9zZWNvbmRz'
     'KCkgPD0gbWF4aW11bSwgJ01BTklGRVNUX1ZFVE9fV0lORE9XX05PVF9PUEVOJykKICAgIHN0YXJ0ZWQgPSBtb25vdG9uaWMo'
     'KQogICAgd2hpbGUgVHJ1ZToKICAgICAgICByZW1haW5pbmcgPSAob3BlbnNfYXQgLSBjbG9jaygpKS50b3RhbF9zZWNvbmRz'
     'KCkKICAgICAgICBpZiByZW1haW5pbmcgPD0gMDoKICAgICAgICAgICAgcmV0dXJuIChjbG9jaygpIC0gYmVnYW4pLnRvdGFs'
     'X3NlY29uZHMoKQogICAgICAgIG5lZWQobW9ub3RvbmljKCkgLSBzdGFydGVkIDw9IG1heGltdW0gKyAxLjAsICdNQU5JRkVT'
     'VF9XQUlUX0NMT0NLJykKICAgICAgICBzbGVlcChtaW4oMC4yNSwgbWF4KDAuMDAxLCByZW1haW5pbmcpKSkKCgpkZWYgX3Zp'
     'ZXcoY3R4OiBDb250ZXh0LCBkYXk6IHN0ciwgb3BlbnNfYXQ6IGRhdGV0aW1lIHwgTm9uZSwgKiwgY2xvY2ssIHNsZWVwLCBt'
     'b25vdG9uaWMpIC0+IHR1cGxlW2RhdGV0aW1lLCBkYXRldGltZV06CiAgICAiIiJSZWFkIHRoZSBwaW5uZWQgdmlldywgb25s'
     'eSBub3cuIEEgdmlldyBlbWl0dGVkIGluLXdpbmRvdyBtYXkgYXJyaXZlIGEgZmV3IHNlY29uZHMgbGF0ZS4iIiIKICAgIHN0'
     'YXJ0ZWQgPSBtb25vdG9uaWMoKQogICAgd2hpbGUgVHJ1ZToKICAgICAgICB0cnk6CiAgICAgICAgICAgIG9ic2VydmVkLCB1'
     'bnRpbCA9IGN0eC52ZXRvX2JvdW5kcyhkYXkpCiAgICAgICAgICAgIGJyZWFrCiAgICAgICAgZXhjZXB0IEZpbGVOb3RGb3Vu'
     'ZEVycm9yOgogICAgICAgICAgICBjb2RlID0gJ01BTklGRVNUX1ZFVE9fVklFV19BQlNFTlQnCiAgICAgICAgZXhjZXB0IFZh'
     'bHVlRXJyb3IgYXMgZXJyb3I6CiAgICAgICAgICAgIGNvZGUgPSBfY29kZShlcnJvcikKICAgICAgICAgICAgaWYgY29kZSBu'
     'b3QgaW4gVklFV19OT1RfWUVUOgogICAgICAgICAgICAgICAgcmFpc2UKICAgICAgICBuZWVkKG9wZW5zX2F0IGlzIG5vdCBO'
     'b25lIGFuZCAoY2xvY2soKSAtIG9wZW5zX2F0KS50b3RhbF9zZWNvbmRzKCkgPCBWSUVXX0dSQUNFX1NFQ09ORFMKICAgICAg'
     'ICAgICAgIGFuZCBtb25vdG9uaWMoKSAtIHN0YXJ0ZWQgPD0gVklFV19HUkFDRV9TRUNPTkRTICsgMS4wLCBjb2RlKQogICAg'
     'ICAgIHNsZWVwKDAuMDUpCiAgICBuZWVkKG9wZW5zX2F0IGlzIE5vbmUgb3Igb2JzZXJ2ZWQgPT0gb3BlbnNfYXQsICdNQU5J'
     'RkVTVF9WSUVXX0FSR1VNRU5UX01JU01BVENIJykKICAgIG5vdyA9IGNsb2NrKCkKICAgIG5lZWQob2JzZXJ2ZWQgPD0gbm93'
     'LCAnTUFOSUZFU1RfVkVUT19XSU5ET1dfTk9UX09QRU4nKQogICAgbmVlZChub3cgPCB1bnRpbCwgJ01BTklGRVNUX1ZFVE9f'
     'V0lORE9XX01JU1NFRCcpCiAgICByZXR1cm4gb2JzZXJ2ZWQsIHVudGlsCgoKZGVmIF9nYXRlKGN0eDogQ29udGV4dCwgZ286'
     'IGRpY3QsIHBsYW46IGRpY3QsICosIGNsb2NrLCBjdXRvZmY6IGRhdGV0aW1lKSAtPiBkaWN0OgogICAgIiIiVGhlIGNvZGUt'
     'bGV2ZWwgR086IHBhY2thZ2VkIHZhbGlkYXRvciB3aXRoIHRoZSByZWFsIGF1dGhvcml0eSwgaW5zaWRlIHdpbmRvdyBhbmQg'
     'Y3V0b2ZmLiIiIgogICAgYXBwID0gcGFja2FnZWQoKQogICAgbm93ID0gY2xvY2soKQogICAgbmVlZChub3cgPCBjdXRvZmYs'
     'ICdNQU5JRkVTVF9DVVRPRkZfUEFTU0VEJykKICAgIHJlc3VsdCA9IGFwcC52YWxpZGF0ZV9nbyhnbywgcGxhbiwgbm93PW5v'
     'dywgYXV0aG9yaXR5X3ZlcmlmaWVyPWN0eC52ZXJpZnlfZ28pCiAgICBhZnRlciA9IGNsb2NrKCkKICAgIG5lZWQobm93IDw9'
     'IGFmdGVyIGFuZCBhcHAudXRjKGdvWydub3RfYmVmb3JlJ10pIDw9IGFmdGVyIDwgYXBwLnV0Yyhnb1snbm90X2FmdGVyJ10p'
     'LCAnR09fV0lORE9XX0FGVEVSX0FVVEhPUklUWScpCiAgICBuZWVkKGFmdGVyIDwgY3V0b2ZmLCAnTUFOSUZFU1RfQ1VUT0ZG'
     'X1BBU1NFRCcpCiAgICByZXR1cm4gcmVzdWx0CgoKZGVmIF9vdXRzaWRlKHRhcmdldDogUGF0aCwgcHJvdGVjdGVkOiB0dXBs'
     'ZSkgLT4gTm9uZToKICAgICIiIlRoZSBtYW5pZmVzdCBkaXJlY3RvcnkgaXMgbm8gY29uZmlndXJlZCByb290LCBob2xkcyBu'
     'b25lIGFuZCBsaWVzIGluc2lkZSBub25lLiIiIgogICAgaGVyZSA9IG9zLnBhdGgubm9ybXBhdGgoc3RyKHRhcmdldCkpCiAg'
     'ICBmb3Igcm9vdCBpbiBwcm90ZWN0ZWQ6CiAgICAgICAgaWYgcm9vdCBhbmQgb3MucGF0aC5pc2FicyhzdHIocm9vdCkpOgog'
     'ICAgICAgICAgICB0aGVyZSA9IG9zLnBhdGgubm9ybXBhdGgoc3RyKHJvb3QpKQogICAgICAgICAgICBuZWVkKG9zLnBhdGgu'
     'Y29tbW9ucGF0aChbaGVyZSwgdGhlcmVdKSBub3QgaW4gKGhlcmUsIHRoZXJlKSwgJ01BTklGRVNUX0RJUkVDVE9SWV9PVkVS'
     'TEFQJykKCgpkZWYgX3dyaXRhYmxlKGRpcmVjdG9yeTogaW50KSAtPiBOb25lOgogICAgIiIiQ291bGQgdGhpcyBwcm9jZXNz'
     'IGNyZWF0ZSBhIGZpbGUgaGVyZT8gQXNrZWQgd2l0aG91dCB3cml0aW5nLCBiZWZvcmUgYW55dGhpbmcgaXMgY29tbWl0dGVk'
     'LiIiIgogICAgbmVlZChvcy5hY2Nlc3MoJy4nLCBvcy5XX09LIHwgb3MuWF9PSywgZGlyX2ZkPWRpcmVjdG9yeSksICdNQU5J'
     'RkVTVF9ESVJFQ1RPUllfTk9UX1dSSVRBQkxFJykKICAgIHZvbHVtZSA9IG9zLmZzdGF0dmZzKGRpcmVjdG9yeSkKICAgIGJs'
     'b2NrcyA9IHZvbHVtZS5mX2JmcmVlIGlmIG9zLmdldGV1aWQoKSA9PSAwIGVsc2Ugdm9sdW1lLmZfYmF2YWlsCiAgICBuZWVk'
     'KG5vdCB2b2x1bWUuZl9mbGFnICYgb3MuU1RfUkRPTkxZIGFuZCAodm9sdW1lLmZfYmxvY2tzID09IDAgb3IgYmxvY2tzID4g'
     'MCkKICAgICAgICAgYW5kICh2b2x1bWUuZl9maWxlcyA9PSAwIG9yIHZvbHVtZS5mX2ZmcmVlID4gMCksICdNQU5JRkVTVF9E'
     'SVJFQ1RPUllfTk9UX1dSSVRBQkxFJykKCgpkZWYgX3RlbXBvcmFyaWVzKGRpcmVjdG9yeTogaW50LCBuYW1lOiBzdHIpIC0+'
     'IHR1cGxlW2ludCwgbGlzdFtzdHJdXToKICAgICIiIkxlZnRvdmVyIHRlbXBvcmFyaWVzLCByZWFkIG9ubHk6IChmb3JlaWdu'
     'IG9uZXMsIHNlY29uZCBuYW1lcyBvZiB0aGUgcHVibGlzaGVkIGlub2RlKS4iIiIKICAgIHRyeToKICAgICAgICBmaW5hbCA9'
     'IG9zLnN0YXQobmFtZSwgZGlyX2ZkPWRpcmVjdG9yeSwgZm9sbG93X3N5bWxpbmtzPUZhbHNlKQogICAgZXhjZXB0IEZpbGVO'
     'b3RGb3VuZEVycm9yOgogICAgICAgIGZpbmFsID0gTm9uZQogICAgc3RhbGUsIHNlY29uZCA9IDAsIFtdCiAgICBmb3IgZW50'
     'cnkgaW4gc29ydGVkKG9zLmxpc3RkaXIoZGlyZWN0b3J5KSk6CiAgICAgICAgaWYgcmUubWF0Y2goX1RFTVBPUkFSWSAlIHJl'
     'LmVzY2FwZShuYW1lKSwgZW50cnkpIGlzIE5vbmU6CiAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgaW5mbyA9IG9zLnN0'
     'YXQoZW50cnksIGRpcl9mZD1kaXJlY3RvcnksIGZvbGxvd19zeW1saW5rcz1GYWxzZSkKICAgICAgICBpZiAoZmluYWwgaXMg'
     'bm90IE5vbmUgYW5kIHN0YXQuU19JU1JFRyhpbmZvLnN0X21vZGUpCiAgICAgICAgICAgICAgICBhbmQgKGluZm8uc3RfZGV2'
     'LCBpbmZvLnN0X2lubykgPT0gKGZpbmFsLnN0X2RldiwgZmluYWwuc3RfaW5vKSk6CiAgICAgICAgICAgIHNlY29uZC5hcHBl'
     'bmQoZW50cnkpCiAgICAgICAgZWxzZToKICAgICAgICAgICAgc3RhbGUgKz0gMQogICAgcmV0dXJuIHN0YWxlLCBzZWNvbmQK'
     'CgpkZWYgX3JlcGFpcihkaXJlY3Rvcnk6IGludCwgbmFtZTogc3RyLCBzZWNvbmQ6IGxpc3Rbc3RyXSwgZGF0YTogYnl0ZXMp'
     'IC0+IGludDoKICAgICIiIkNvbXBsZXRlIGFuIGludGVycnVwdGVkIHB1YmxpY2F0aW9uLCBhbmQgbm90aGluZyBlbHNlLgoK'
     'ICAgIFRoZSBleHRyYSBuYW1lIGlzIHJlbW92ZWQgb25seSB3aGVuIHRoZSBmaWxlIHVuZGVyIHRoZSBmaW5hbCBuYW1lIGlz'
     'IGEgcHJpdmF0ZSByZWd1bGFyCiAgICBmaWxlIG9mIHRoaXMgdWlkIHdpdGggZXhhY3RseSB0d28gbGlua3MsIHRoZSBvdGhl'
     'ciBvbmUgYmVpbmcgdGhhdCB0ZW1wb3JhcnksIGFuZCBpdHMKICAgIGJ5dGVzIEFSRSB0aGUgbWFuaWZlc3Qgb2YgdGhlIGNv'
     'bW1pdHRlZCBiaW5kaW5nLiBBbnkgb3RoZXIgdHdvLWxpbmsgZmlsZSBpcyBsZWZ0IGV4YWN0bHkKICAgIGFzIGl0IGlzIGFu'
     'ZCByZWZ1c2VkOiByZW1vdmluZyBhIG5hbWUgd291bGQgdHVybiBhIGZpbGUgdGhlIHN1cGVydmlzb3IgcmVmdXNlcyBpbnRv'
     'IG9uZQogICAgaXQgYWNjZXB0cy4KICAgICIiIgogICAgZmQgPSBvcy5vcGVuKG5hbWUsIG9zLk9fUkRPTkxZIHwgb3MuT19O'
     'T0ZPTExPVyB8IG9zLk9fTk9OQkxPQ0ssIGRpcl9mZD1kaXJlY3RvcnkpCiAgICB0cnk6CiAgICAgICAgaW5mbyA9IG9zLmZz'
     'dGF0KGZkKQogICAgICAgIG5lZWQobGVuKHNlY29uZCkgPT0gMSBhbmQgc3RhdC5TX0lTUkVHKGluZm8uc3RfbW9kZSkgYW5k'
     'IGluZm8uc3RfbmxpbmsgPT0gMgogICAgICAgICAgICAgYW5kIGluZm8uc3RfdWlkID09IG9zLmdldGV1aWQoKSBhbmQgc3Rh'
     'dC5TX0lNT0RFKGluZm8uc3RfbW9kZSkgPT0gMG82MDAsCiAgICAgICAgICAgICAnTUFOSUZFU1RfUFVCTElDQVRJT05fSU5U'
     'RVJSVVBURUQnKQogICAgICAgIG90aGVyID0gb3Muc3RhdChzZWNvbmRbMF0sIGRpcl9mZD1kaXJlY3RvcnksIGZvbGxvd19z'
     'eW1saW5rcz1GYWxzZSkKICAgICAgICBuZWVkKChvdGhlci5zdF9kZXYsIG90aGVyLnN0X2lubykgPT0gKGluZm8uc3RfZGV2'
     'LCBpbmZvLnN0X2lubyksICdNQU5JRkVTVF9QVUJMSUNBVElPTl9JTlRFUlJVUFRFRCcpCiAgICAgICAgcmF3ID0gYicnCiAg'
     'ICAgICAgd2hpbGUgbGVuKHJhdykgPD0gbGVuKGRhdGEpOgogICAgICAgICAgICBjaHVuayA9IG9zLnJlYWQoZmQsIGxlbihk'
     'YXRhKSArIDEgLSBsZW4ocmF3KSkKICAgICAgICAgICAgaWYgbm90IGNodW5rOgogICAgICAgICAgICAgICAgYnJlYWsKICAg'
     'ICAgICAgICAgcmF3ICs9IGNodW5rCiAgICAgICAgbmVlZChyYXcgPT0gZGF0YSwgJ01BTklGRVNUX0NPTkZMSUNUJykKICAg'
     'IGZpbmFsbHk6CiAgICAgICAgb3MuY2xvc2UoZmQpCiAgICBvcy51bmxpbmsoc2Vjb25kWzBdLCBkaXJfZmQ9ZGlyZWN0b3J5'
     'KSAgICAgICAgICAjIGNoYW5nZXMgbm8gY29udGVudDogdGhlIGxpbmsgY291bnQgZ29lcyBmcm9tIDIgdG8gMQogICAgb3Mu'
     'ZnN5bmMoZGlyZWN0b3J5KQogICAgcmV0dXJuIDEKCgpkZWYgX2V4aXN0aW5nKHRhcmdldDogUGF0aCwgZGlyZWN0b3J5OiBp'
     'bnQsIG5hbWU6IHN0cikgLT4gYnl0ZXMgfCBOb25lOgogICAgdHJ5OgogICAgICAgIG9zLnN0YXQobmFtZSwgZGlyX2ZkPWRp'
     'cmVjdG9yeSwgZm9sbG93X3N5bWxpbmtzPUZhbHNlKQogICAgZXhjZXB0IEZpbGVOb3RGb3VuZEVycm9yOgogICAgICAgIHJl'
     'dHVybiBOb25lCiAgICB0cnk6CiAgICAgICAgcmV0dXJuIHBhY2thZ2VkKCkucHJpdmF0ZV9ieXRlcyh0YXJnZXQgLyBuYW1l'
     'LCBNQVhfTUFOSUZFU1RfQllURVMpICAgIyB0aGUgc3VwZXJ2aXNvcidzIG93biByZWFkZXIKICAgIGV4Y2VwdCBFeGNlcHRp'
     'b246CiAgICAgICAgcmFpc2UgUmVmdXNlZCgnTUFOSUZFU1RfRVhJU1RJTkdfVU5WRVJJRklFRCcpIGZyb20gTm9uZQoKCkBj'
     'b250ZXh0bWFuYWdlcgpkZWYgX3Jlc2VydmVkKGRpcmVjdG9yeTogaW50LCBuYW1lOiBzdHIpIC0+IEl0ZXJhdG9yW3R1cGxl'
     'W3N0ciwgaW50XV06CiAgICAiIiJUaGUgcHJpdmF0ZSB0ZW1wb3JhcnksIGNyZWF0ZWQgZXhjbHVzaXZlbHkgYW5kIGVtcHR5'
     'IEJFRk9SRSBhbnl0aGluZyBpcyBjb21taXR0ZWQuCgogICAgQSBkaXJlY3RvcnkgdGhhdCBjYW5ub3QgdGFrZSBhIG5ldyBm'
     'aWxlIGZhaWxzIGhlcmUsIHdpdGggbm8gYmluZGluZyBjb21taXR0ZWQgYnkgdGhpcwogICAgcnVuLiBXaGF0ZXZlciBoYXBw'
     'ZW5zIG5leHQsIHRoZSB0ZW1wb3JhcnkgbmFtZSBpcyByZW1vdmVkIG9uIHRoZSB3YXkgb3V0LgogICAgIiIiCiAgICB0ZW1w'
     'b3JhcnkgPSAnLicgKyBuYW1lICsgJy4nICsgc2VjcmV0cy50b2tlbl9oZXgoOCkgKyAnLnRtcCcKICAgIGZkID0gb3Mub3Bl'
     'bih0ZW1wb3JhcnksIG9zLk9fV1JPTkxZIHwgb3MuT19DUkVBVCB8IG9zLk9fRVhDTCB8IG9zLk9fTk9GT0xMT1csIDBvNjAw'
     'LCBkaXJfZmQ9ZGlyZWN0b3J5KQogICAgdHJ5OgogICAgICAgIHRyeToKICAgICAgICAgICAgb3MuZmNobW9kKGZkLCAwbzYw'
     'MCkKICAgICAgICAgICAgeWllbGQgdGVtcG9yYXJ5LCBmZAogICAgICAgIGZpbmFsbHk6CiAgICAgICAgICAgIG9zLmNsb3Nl'
     'KGZkKQogICAgZmluYWxseToKICAgICAgICBvcy51bmxpbmsodGVtcG9yYXJ5LCBkaXJfZmQ9ZGlyZWN0b3J5KQogICAgICAg'
     'IG9zLmZzeW5jKGRpcmVjdG9yeSkKCgpkZWYgX3B1Ymxpc2goZGlyZWN0b3J5OiBpbnQsIG5hbWU6IHN0ciwgdGVtcG9yYXJ5'
     'OiBzdHIsIGZkOiBpbnQsIGRhdGE6IGJ5dGVzLCAqLAogICAgICAgICAgICAgYmVmb3JlX2xpbms6IENhbGxhYmxlW1tdLCBB'
     'bnldLCBsaW5rZWQ6IENhbGxhYmxlW1tdLCBOb25lXSkgLT4gYm9vbDoKICAgICIiIkV4Y2x1c2l2ZSwgYWxsLW9yLW5vdGhp'
     'bmcgcHVibGljYXRpb24gZnJvbSB0aGUgcmVzZXJ2ZWQgdGVtcG9yYXJ5LiBGYWxzZTogYW5vdGhlciB3cml0ZXIgd29uIHRo'
     'ZSBuYW1lLiIiIgogICAgdmlldyA9IG1lbW9yeXZpZXcoZGF0YSkKICAgIHdoaWxlIHZpZXc6CiAgICAgICAgY291bnQgPSBv'
     'cy53cml0ZShmZCwgdmlldykKICAgICAgICBuZWVkKGNvdW50ID4gMCwgJ01BTklGRVNUX1dSSVRFX0ZBSUxFRCcpCiAgICAg'
     'ICAgdmlldyA9IHZpZXdbY291bnQ6XQogICAgb3MuZnN5bmMoZmQpCiAgICBpbmZvID0gb3MuZnN0YXQoZmQpCiAgICBuZWVk'
     'KHN0YXQuU19JU1JFRyhpbmZvLnN0X21vZGUpIGFuZCBpbmZvLnN0X25saW5rID09IDEgYW5kIGluZm8uc3RfdWlkID09IG9z'
     'LmdldGV1aWQoKQogICAgICAgICBhbmQgc3RhdC5TX0lNT0RFKGluZm8uc3RfbW9kZSkgPT0gMG82MDAgYW5kIGluZm8uc3Rf'
     'c2l6ZSA9PSBsZW4oZGF0YSksICdNQU5JRkVTVF9XUklURV9GQUlMRUQnKQogICAgYmVmb3JlX2xpbmsoKSAgICAgICAgICAg'
     'ICAgICAgICAgICAgICAgICAgICAgICAgIyBhdXRob3JpdHkgaXMgcmVjaGVja2VkIGFmdGVyIHRoZSBsYXN0IHNsb3cgc3Rl'
     'cAogICAgdHJ5OgogICAgICAgIG9zLmxpbmsodGVtcG9yYXJ5LCBuYW1lLCBzcmNfZGlyX2ZkPWRpcmVjdG9yeSwgZHN0X2Rp'
     'cl9mZD1kaXJlY3RvcnkpCiAgICBleGNlcHQgRmlsZUV4aXN0c0Vycm9yOgogICAgICAgIHJldHVybiBGYWxzZQogICAgbGlu'
     'a2VkKCkKICAgIHJldHVybiBUcnVlCgoKZGVmIF92ZXJpZmllZChyZWNlaXB0OiBkaWN0LCBkaXJlY3Rvcnk6IGludCwgbmFt'
     'ZTogc3RyLCAqLCBkYXk6IHN0ciwgZXhpc3Rpbmc6IGJ5dGVzLCBkYXRhOiBieXRlcywgYmluZGluZzogQW55LAogICAgICAg'
     'ICAgICAgIGNvdW50OiBpbnQsIHN0YXR1czogc3RyKSAtPiBpbnQ6CiAgICAiIiJUaGUgcHJpdmF0ZSBmaWxlIGVxdWFscyB0'
     'aGUgbWFuaWZlc3Qgb2YgdGhlIGNvbW1pdHRlZCBiaW5kaW5nOiByZWNvcmQgaXQuIiIiCiAgICBuZWVkKGV4aXN0aW5nID09'
     'IGRhdGEsICdNQU5JRkVTVF9DT05GTElDVCcpCiAgICByZWFkYmFjayA9IHBhY2thZ2VkKCkubG9hZF9qc29uKGV4aXN0aW5n'
     'KSAgICAgICAjIHRoZSBzdXBlcnZpc29yJ3MgcGFyc2UgYW5kIGl0cyB0d28gY2hlY2tzCiAgICBuZWVkKHJlYWRiYWNrLmdl'
     'dCgnc2Vzc2lvbicpID09IGRheSBhbmQgcmVhZGJhY2suZ2V0KCdvd25lcl91aWQnKSA9PSBvcy5nZXRldWlkKCksICdNQU5J'
     'RkVTVF9SRUFEQkFDS19GQUlMRUQnKQogICAgaW5mbyA9IG9zLnN0YXQobmFtZSwgZGlyX2ZkPWRpcmVjdG9yeSwgZm9sbG93'
     'X3N5bWxpbmtzPUZhbHNlKQogICAgbmVlZChpbmZvLnN0X25saW5rID09IDEgYW5kIHN0YXQuU19JTU9ERShpbmZvLnN0X21v'
     'ZGUpID09IDBvNjAwIGFuZCBpbmZvLnN0X3VpZCA9PSBvcy5nZXRldWlkKCksCiAgICAgICAgICdNQU5JRkVTVF9SRUFEQkFD'
     'S19GQUlMRUQnKQogICAgaWYgc3RhdHVzID09ICdBTFJFQURZX1BVQkxJU0hFRF9WRVJJRklFRCc6CiAgICAgICAgIyBBIHB1'
     'Ymxpc2ggcnVuIHRoYXQgZGlkIG5vdCBjcmVhdGUgdGhlIG5hbWUgaXRzZWxmOiB0aGUgcnVuIHRoYXQgZGlkIG1heSBoYXZl'
     'IGRpZWQKICAgICAgICAjIGJlZm9yZSBpdHMgZGlyZWN0b3J5IGZzeW5jLiBDaGFuZ2VzIG5vdGhpbmc7IC0tdmVyaWZ5LW9u'
     'bHkgbmV2ZXIgY29tZXMgaGVyZS4KICAgICAgICBvcy5mc3luYyhkaXJlY3RvcnkpCiAgICByZWNlaXB0LnVwZGF0ZShiaW5k'
     'aW5nX3NoYTI1Nj1iaW5kaW5nLnNoYSwgc3ltYm9sX2NvdW50PWNvdW50LCBtYW5pZmVzdF9zaGEyNTY9aGFzaGxpYi5zaGEy'
     'NTYoZGF0YSkuaGV4ZGlnZXN0KCkpCiAgICByZWNlaXB0WydmaWxlJ10gPSB7J3VpZCc6IGluZm8uc3RfdWlkLCAnZ2lkJzog'
     'aW5mby5zdF9naWQsICdtb2RlJzogJyUwNG8nICUgc3RhdC5TX0lNT0RFKGluZm8uc3RfbW9kZSksCiAgICAgICAgICAgICAg'
     'ICAgICAgICAgJ25saW5rJzogaW5mby5zdF9ubGluaywgJ2RldmljZSc6IGluZm8uc3RfZGV2LCAnaW5vZGUnOiBpbmZvLnN0'
     'X2lubywKICAgICAgICAgICAgICAgICAgICAgICAnc2l6ZV93aXRoaW5fbGltaXQnOiAwIDwgaW5mby5zdF9zaXplIDw9IE1B'
     'WF9NQU5JRkVTVF9CWVRFU30KICAgIHJlY2VpcHRbJ3N0YXR1cyddID0gc3RhdHVzCiAgICByZXR1cm4gRVhJVF9PSwoKCmRl'
     'ZiBfd2luZG93KGdvOiBkaWN0KSAtPiBkaWN0OgogICAgcmV0dXJuIHsnbm90X2JlZm9yZSc6IGdvWydub3RfYmVmb3JlJ10s'
     'ICdub3RfYWZ0ZXInOiBnb1snbm90X2FmdGVyJ119CgoKZGVmIF9wcmVmbGlnaHQoY3R4OiBDb250ZXh0LCByZWNlaXB0OiBk'
     'aWN0LCAqLCBkYXk6IHN0ciwgZGlyZWN0b3J5OiBQYXRoIHwgTm9uZSwgZXhwZWN0X3NoYTogc3RyIHwgTm9uZSwKICAgICAg'
     'ICAgICAgICAgdmlld19vcGVuc19hdDogZGF0ZXRpbWUgfCBOb25lLCB0b2RheTogYm9vbCwgbm93OiBkYXRldGltZSwgY3V0'
     'b2ZmOiBkYXRldGltZSwKICAgICAgICAgICAgICAgcmVxdWlyZV9nb19tb2RlOiBzdHIgfCBOb25lKSAtPiBpbnQ6CiAgICAi'
     'IiJDb250ZXh0IG9ubHk6IG5vIHdhaXQsIG5vIHByZXBhcmUsIG5vIHdyaXRlLCBubyB2ZXRvIHZpZXcuIiIiCiAgICByb3cg'
     'PSBjdHgucmVhZF9zdGF0ZSgpCiAgICBwZXJzaXN0ZWQgPSBfcGVyc2lzdGVkKHJvdywgZGF5KQogICAgbmVlZChleHBlY3Rf'
     'c2hhIGlzIE5vbmUgb3IgcGVyc2lzdGVkIGlzIE5vbmUgb3IgcGVyc2lzdGVkLmdldCgnc2hhJykgPT0gZXhwZWN0X3NoYSwK'
     'ICAgICAgICAgJ01BTklGRVNUX0JJTkRJTkdfU0hBX01JU01BVENIJykKICAgIGN0eC52ZXJpZnlfY2hhaW4oZGF5KQogICAg'
     'bmVlZChjdHgudmlld19waW5uZWQoZGF5KSwgJ0NBUEFDSVRZX1ZFVE9fREFZX1VOQk9VTkQnKQogICAgY2hlY2tzID0geydz'
     'dGF0ZV9yb3dfcHJlc2VudCc6IHJvdyBpcyBub3QgTm9uZSwgJ2JpbmRpbmdfY29tbWl0dGVkJzogcGVyc2lzdGVkIGlzIG5v'
     'dCBOb25lLAogICAgICAgICAgICAgICdhY3RfYl9jaGFpbl92ZXJpZmllZCc6IFRydWUsICd2ZXRvX3ZpZXdfcGlubmVkJzog'
     'VHJ1ZSwgJ2RheV9pc190b2RheSc6IHRvZGF5LAogICAgICAgICAgICAgICdiZWZvcmVfY3V0b2ZmJzogbm93IDwgY3V0b2Zm'
     'LCAnZGlyZWN0b3J5X2NoZWNrZWQnOiBGYWxzZX0KICAgIHBsYW5zID0ge30KICAgIGlmIHBlcnNpc3RlZCBpcyBOb25lOgog'
     'ICAgICAgIG5lZWQoY3R4LnByZXBhcmUgaXMgbm90IE5vbmUsICdNQU5JRkVTVF9QUkVQQVJFX01JU1NJTkcnKQogICAgICAg'
     'IGNvbnRyYWN0ID0gX3BheWxvYWRfY29udHJhY3QoY3R4LCBkYXkpCiAgICAgICAgY2hlY2tzWydwYXlsb2FkX2NvbnRyYWN0'
     'X3ZhbGlkJ10gPSBUcnVlCiAgICAgICAgcGxhbnNbQURNSVNTSU9OXSA9IGNvbnRyYWN0Wydhc3NlbWJsZXJfcGxhbiddCiAg'
     'ICBlbHNlOgogICAgICAgIGNvbnRyYWN0ID0gX3Jlc3RvcmUoY3R4LCBwZXJzaXN0ZWQpLmRvY3VtZW50Wydjb250cmFjdCdd'
     'CiAgICAgICAgY2hlY2tzWydiaW5kaW5nX3Jlc3RvcmVkJ10gPSBUcnVlCiAgICBwbGFuc1tQSEFTRV0gPSBjb250cmFjdFsn'
     'Y29uc3VtZXJfcGxhbnMnXVtQSEFTRV0KICAgIHdpbmRvd3MsIGZpbGVzID0ge30sIHt9CiAgICBmb3IgcGhhc2UsIHBsYW4g'
     'aW4gc29ydGVkKHBsYW5zLml0ZW1zKCkpOgogICAgICAgIGZpbGVzW3BoYXNlXSA9IGN0eC5yZWFkX2dvKGRheSwgcGhhc2Up'
     'CiAgICAgICAgYmVmb3JlLCBhZnRlciA9IHN0YXRpY19nbyhmaWxlc1twaGFzZV0sIHBsYW4sIGRheT1kYXksIHBoYXNlPXBo'
     'YXNlKQogICAgICAgIG5lZWQodmlld19vcGVuc19hdCBpcyBOb25lIG9yIGJlZm9yZSA8PSB2aWV3X29wZW5zX2F0IDwgYWZ0'
     'ZXIsICdNQU5JRkVTVF9HT19XSU5ET1dfVklFVycpCiAgICAgICAgd2luZG93c1twaGFzZV0gPSBfd2luZG93KGZpbGVzW3Bo'
     'YXNlXSkKICAgIG5lZWQocmVxdWlyZV9nb19tb2RlIGlzIE5vbmUgb3IgZmlsZXNbUEhBU0VdWydtb2RlJ10gPT0gcmVxdWly'
     'ZV9nb19tb2RlLCAnTUFOSUZFU1RfR09fTU9ERScpCiAgICBmb3IgcGhhc2UsIGZpbGUgaW4gZmlsZXMuaXRlbXMoKToKICAg'
     'ICAgICBjdHguY2hlY2tfZ28oZmlsZSwgcGxhbnNbcGhhc2VdKQogICAgbmVlZCh2aWV3X29wZW5zX2F0IGlzIE5vbmUgb3Ig'
     'dmlld19vcGVuc19hdCA8IGN1dG9mZiwgJ01BTklGRVNUX0NVVE9GRl9QQVNTRUQnKQogICAgY2hlY2tzWydnb19maWxlc192'
     'YWxpZCddID0gc29ydGVkKHdpbmRvd3MpCiAgICBpZiBkaXJlY3RvcnkgaXMgbm90IE5vbmU6CiAgICAgICAgdGFyZ2V0ID0g'
     'UGF0aChkaXJlY3RvcnkpCiAgICAgICAgbmVlZCh0YXJnZXQuaXNfYWJzb2x1dGUoKSwgJ01BTklGRVNUX0RJUkVDVE9SWV9J'
     'TlZBTElEJykKICAgICAgICBfb3V0c2lkZSh0YXJnZXQsIGN0eC5wcm90ZWN0ZWQpCiAgICAgICAgaGFuZGxlID0gcGFja2Fn'
     'ZWQoKS5vcGVuX2RpcmVjdG9yeSh0YXJnZXQpICAgIyBwcml2YXRlIGxlYWYsIG5vIHN5bWJvbGljIGxpbmsgaW4gYW55IGNv'
     'bXBvbmVudAogICAgICAgIHRyeToKICAgICAgICAgICAgbmVlZChvcy5mc3RhdChoYW5kbGUpLnN0X3VpZCA9PSBvcy5nZXRl'
     'dWlkKCksICdNQU5JRkVTVF9ESVJFQ1RPUllfT1dORVInKQogICAgICAgICAgICBfd3JpdGFibGUoaGFuZGxlKSAgICAgICAg'
     'ICAgICAgICAgICAgICAgICMgYXNrZWQsIG5vdCB0cmllZDogdGhpcyBtb2RlIHdyaXRlcyBub3RoaW5nCiAgICAgICAgICAg'
     'IHN0YWxlLCBzZWNvbmQgPSBfdGVtcG9yYXJpZXMoaGFuZGxlLCBkYXkgKyAnLmpzb24nKQogICAgICAgICAgICBwcmVzZW50'
     'ID0gYm9vbChzZWNvbmQpIG9yIF9leGlzdGluZyh0YXJnZXQsIGhhbmRsZSwgZGF5ICsgJy5qc29uJykgaXMgbm90IE5vbmUK'
     'ICAgICAgICAgICAgY2hlY2tzLnVwZGF0ZShkaXJlY3RvcnlfY2hlY2tlZD1UcnVlLCBkaXJlY3Rvcnlfd3JpdGFibGU9VHJ1'
     'ZSwgc3RhbGVfdGVtcG9yYXJpZXM9c3RhbGUsCiAgICAgICAgICAgICAgICAgICAgICAgICAgcHVibGljYXRpb25faW50ZXJy'
     'dXB0ZWQ9Ym9vbChzZWNvbmQpLCBtYW5pZmVzdF9wcmVzZW50PXByZXNlbnQpCiAgICAgICAgZmluYWxseToKICAgICAgICAg'
     'ICAgb3MuY2xvc2UoaGFuZGxlKQogICAgcmVjZWlwdC51cGRhdGUoY2hlY2tzPWNoZWNrcywgd2luZG93cz13aW5kb3dzLCBz'
     'dGF0dXM9J1BSRUZMSUdIVF9PSycpCiAgICByZXR1cm4gRVhJVF9PSwoKCmRlZiBydW4oY3R4OiBDb250ZXh0LCByZWNlaXB0'
     'OiBkaWN0LCAqLCBkYXk6IHN0ciwgZGlyZWN0b3J5OiBQYXRoIHwgTm9uZSA9IE5vbmUsIHZlcmlmeV9vbmx5OiBib29sID0g'
     'RmFsc2UsCiAgICAgICAgcHJlZmxpZ2h0OiBib29sID0gRmFsc2UsIGV4cGVjdF9zaGE6IHN0ciB8IE5vbmUgPSBOb25lLCB2'
     'aWV3X29wZW5zX2F0OiBkYXRldGltZSB8IE5vbmUgPSBOb25lLAogICAgICAgIG1heF93YWl0OiBpbnQgPSAwLCByZXF1aXJl'
     'X2dvX21vZGU6IHN0ciB8IE5vbmUgPSBOb25lLCBjbG9jazogQ2FsbGFibGVbW10sIGRhdGV0aW1lXSwKICAgICAgICBzbGVl'
     'cDogQ2FsbGFibGVbW2Zsb2F0XSwgTm9uZV0gPSB0aW1lLnNsZWVwLCBtb25vdG9uaWM6IENhbGxhYmxlW1tdLCBmbG9hdF0g'
     'PSB0aW1lLm1vbm90b25pYykgLT4gaW50OgogICAgYXBwID0gcGFja2FnZWQoKQogICAgcmVjZWlwdC51cGRhdGUoZXBvY2g9'
     'Y3R4LnJlbGVhc2UuZXBvY2gsIG93bmVyX3VpZD1vcy5nZXRldWlkKCksICoqY3R4LnBpbnMpCiAgICBwYXJzZWQgPSBkYXRl'
     'LmZyb21pc29mb3JtYXQoZGF5KQogICAgbmVlZChjdHguY2FsZW5kYXIuaXNfc2Vzc2lvbihwYXJzZWQpLCAnTUFOSUZFU1Rf'
     'REFZX05PVF9TRVNTSU9OJykKICAgIGN1dG9mZiA9IGN0eC5jYWxlbmRhci5kZXRhaWxzKHBhcnNlZClbJ29wZW4nXSAtIENV'
     'VE9GRl9CRUZPUkVfT1BFTgogICAgcmVjZWlwdFsnY3V0b2ZmX2F0J10gPSBjdXRvZmYuaXNvZm9ybWF0KCkKICAgIG5vdyA9'
     'IGNsb2NrKCkKICAgIHRvZGF5ID0gbm93LmFzdGltZXpvbmUoYXBwLk5FV19ZT1JLKS5kYXRlKCkgPT0gcGFyc2VkCiAgICBp'
     'ZiBwcmVmbGlnaHQ6CiAgICAgICAgcmV0dXJuIF9wcmVmbGlnaHQoY3R4LCByZWNlaXB0LCBkYXk9ZGF5LCBkaXJlY3Rvcnk9'
     'ZGlyZWN0b3J5LCBleHBlY3Rfc2hhPWV4cGVjdF9zaGEsCiAgICAgICAgICAgICAgICAgICAgICAgICAgdmlld19vcGVuc19h'
     'dD12aWV3X29wZW5zX2F0LCB0b2RheT10b2RheSwgbm93PW5vdywgY3V0b2ZmPWN1dG9mZiwKICAgICAgICAgICAgICAgICAg'
     'ICAgICAgICByZXF1aXJlX2dvX21vZGU9cmVxdWlyZV9nb19tb2RlKQoKICAgICMgLS0tLSBwcmUtZmxpZ2h0OiBldmVyeXRo'
     'aW5nIGJlbG93IHJ1bnMgYmVmb3JlIHByZXBhcmUsIGFuZCBtb3N0IG9mIGl0IGJlZm9yZSB0aGUgd2FpdCAtLS0tCiAgICBu'
     'ZWVkKGRpcmVjdG9yeSBpcyBub3QgTm9uZSBhbmQgUGF0aChkaXJlY3RvcnkpLmlzX2Fic29sdXRlKCksICdNQU5JRkVTVF9E'
     'SVJFQ1RPUllfSU5WQUxJRCcpCiAgICB0YXJnZXQsIG5hbWUgPSBQYXRoKGRpcmVjdG9yeSksIGRheSArICcuanNvbicKICAg'
     'IF9vdXRzaWRlKHRhcmdldCwgY3R4LnByb3RlY3RlZCkKICAgIGlmIG5vdCB2ZXJpZnlfb25seToKICAgICAgICBuZWVkKHRv'
     'ZGF5LCAnTUFOSUZFU1RfREFZX05PVF9UT0RBWScpCiAgICAgICAgIyBGcm9tIHRoZSBjdXRvZmYgb24sIGEgcHVibGlzaGlu'
     'ZyBydW4gZG9lcyBub3RoaW5nIGF0IGFsbDogbm8gcmVwYWlyLCBubyBwdWJsaWNhdGlvbi4KICAgICAgICBuZWVkKG5vdyA8'
     'IGN1dG9mZiBhbmQgKHZpZXdfb3BlbnNfYXQgaXMgTm9uZSBvciB2aWV3X29wZW5zX2F0IDwgY3V0b2ZmKSwgJ01BTklGRVNU'
     'X0NVVE9GRl9QQVNTRUQnKQogICAgcm93ID0gY3R4LnJlYWRfc3RhdGUoKQogICAgcGVyc2lzdGVkID0gX3BlcnNpc3RlZChy'
     'b3csIGRheSkKICAgIG5lZWQoZXhwZWN0X3NoYSBpcyBOb25lIG9yIHBlcnNpc3RlZCBpcyBOb25lIG9yIHBlcnNpc3RlZC5n'
     'ZXQoJ3NoYScpID09IGV4cGVjdF9zaGEsCiAgICAgICAgICdNQU5JRkVTVF9CSU5ESU5HX1NIQV9NSVNNQVRDSCcpCiAgICBo'
     'YW5kbGUgPSBhcHAub3Blbl9kaXJlY3RvcnkodGFyZ2V0KSAgICAgICAgICAgICAjIHByaXZhdGUgbGVhZiwgbm8gc3ltYm9s'
     'aWMgbGluayBpbiBhbnkgY29tcG9uZW50CiAgICB0cnk6CiAgICAgICAgbmVlZChvcy5mc3RhdChoYW5kbGUpLnN0X3VpZCA9'
     'PSBvcy5nZXRldWlkKCksICdNQU5JRkVTVF9ESVJFQ1RPUllfT1dORVInKQogICAgICAgIGlmIG5vdCB2ZXJpZnlfb25seToK'
     'ICAgICAgICAgICAgX3dyaXRhYmxlKGhhbmRsZSkgICAgICAgICAgICAgICAgICAgICAgICMgYmVmb3JlIHRoZSB3YWl0LCBh'
     'bmQgbG9uZyBiZWZvcmUgdGhlIGNvbW1pdAogICAgICAgIHN0YWxlLCBzZWNvbmQgPSBfdGVtcG9yYXJpZXMoaGFuZGxlLCBu'
     'YW1lKSAgIyByZWFkIG9ubHkKICAgICAgICByZWNlaXB0LnVwZGF0ZShzdGFsZV90ZW1wb3Jhcmllcz1zdGFsZSwgcmVwYWly'
     'ZWRfdGVtcG9yYXJpZXM9MCkKICAgICAgICAjIE9ubHkgdGhlIHB1YmxpY2F0aW9uIG9mIGEgY29tbWl0dGVkIGJpbmRpbmcg'
     'aXMgY29tcGxldGVkIChiZWxvdywgb25jZSBpdHMgYnl0ZXMgYXJlCiAgICAgICAgIyBrbm93biksIGFuZCBuZXZlciBieSBh'
     'IHJlYWRiYWNrLgogICAgICAgIG5lZWQobm90IHNlY29uZCBvciAocGVyc2lzdGVkIGlzIG5vdCBOb25lIGFuZCBub3QgdmVy'
     'aWZ5X29ubHkpLAogICAgICAgICAgICAgJ01BTklGRVNUX1BVQkxJQ0FUSU9OX0lOVEVSUlVQVEVEJyBpZiBwZXJzaXN0ZWQg'
     'aXMgbm90IE5vbmUgb3IgdmVyaWZ5X29ubHkKICAgICAgICAgICAgIGVsc2UgJ01BTklGRVNUX0VYSVNUSU5HX1dJVEhPVVRf'
     'QklORElORycpCiAgICAgICAgZXhpc3RpbmcgPSBOb25lIGlmIHNlY29uZCBlbHNlIF9leGlzdGluZyh0YXJnZXQsIGhhbmRs'
     'ZSwgbmFtZSkKCiAgICAgICAgaWYgdmVyaWZ5X29ubHk6CiAgICAgICAgICAgIG5lZWQocGVyc2lzdGVkIGlzIG5vdCBOb25l'
     'LCAnTUFOSUZFU1RfUFJFUEFSRV9NSVNTSU5HJykKICAgICAgICAgICAgYmluZGluZyA9IF9yZXN0b3JlKGN0eCwgcGVyc2lz'
     'dGVkKQogICAgICAgICAgICBkYXRhLCBjb3VudCA9IF9tYW5pZmVzdChjdHgsIGJpbmRpbmcsIHJvdywgZGF5LCBjbG9jaykK'
     'ICAgICAgICAgICAgaWYgZXhpc3RpbmcgaXMgTm9uZToKICAgICAgICAgICAgICAgIHJlY2VpcHQudXBkYXRlKHN0YXR1cz0n'
     'QUJTRU5UJywgY29kZT0nTUFOSUZFU1RfQUJTRU5UJykKICAgICAgICAgICAgICAgIHJldHVybiBFWElUX1JFRlVTRUQKICAg'
     'ICAgICAgICAgcmV0dXJuIF92ZXJpZmllZChyZWNlaXB0LCBoYW5kbGUsIG5hbWUsIGRheT1kYXksIGV4aXN0aW5nPWV4aXN0'
     'aW5nLCBkYXRhPWRhdGEsIGJpbmRpbmc9YmluZGluZywKICAgICAgICAgICAgICAgICAgICAgICAgICAgICBjb3VudD1jb3Vu'
     'dCwgc3RhdHVzPSdNQVRDSF9WRVJJRklFRCcpCgogICAgICAgIHdpbmRvd3MsIGZpbGVzID0gW10sIFtdCiAgICAgICAgaWYg'
     'cGVyc2lzdGVkIGlzIE5vbmU6CiAgICAgICAgICAgIG5lZWQoY3R4LnByZXBhcmUgaXMgbm90IE5vbmUsICdNQU5JRkVTVF9Q'
     'UkVQQVJFX01JU1NJTkcnKQogICAgICAgICAgICAjIEEgbWFuaWZlc3QgY2FuIG9ubHkgY29tZSBmcm9tIGEgY29tbWl0dGVk'
     'IGJpbmRpbmc6IGEgZmlsZSB3aXRob3V0IG9uZSBpcyBmb3JlaWduLgogICAgICAgICAgICBuZWVkKGV4aXN0aW5nIGlzIE5v'
     'bmUsICdNQU5JRkVTVF9FWElTVElOR19XSVRIT1VUX0JJTkRJTkcnKQogICAgICAgICAgICBjb250cmFjdCA9IF9wYXlsb2Fk'
     'X2NvbnRyYWN0KGN0eCwgZGF5KQogICAgICAgICAgICBmaWxlcy5hcHBlbmQoKGN0eC5yZWFkX2dvKGRheSwgQURNSVNTSU9O'
     'KSwgY29udHJhY3RbJ2Fzc2VtYmxlcl9wbGFuJ10pKQogICAgICAgICAgICB3aW5kb3dzLmFwcGVuZChzdGF0aWNfZ28oZmls'
     'ZXNbMF1bMF0sIGZpbGVzWzBdWzFdLCBkYXk9ZGF5LCBwaGFzZT1BRE1JU1NJT04pKQogICAgICAgIGVsc2U6CiAgICAgICAg'
     'ICAgIHJlY2VpcHRbJ3ByZXBhcmVfc3RhdHVzJ10gPSAnUFJFQ09NTUlUVEVEJwogICAgICAgICAgICBiaW5kaW5nID0gX3Jl'
     'c3RvcmUoY3R4LCBwZXJzaXN0ZWQpCiAgICAgICAgICAgIGRhdGEsIGNvdW50ID0gX21hbmlmZXN0KGN0eCwgYmluZGluZywg'
     'cm93LCBkYXksIGNsb2NrKQogICAgICAgICAgICBpZiBzZWNvbmQ6CiAgICAgICAgICAgICAgICAjIFRoZSBvbmUgd3JpdGUg'
     'dGhhdCBuZWVkcyBubyBiYXJfbWFuaWZlc3QgR08sIGFuZCBvbmx5IG5vdzogdGhlIGJpbmRpbmcgaXMKICAgICAgICAgICAg'
     'ICAgICMgcmVzdG9yZWQgYW5kIF9yZXBhaXIgY29tcGFyZXMgdGhlIGZpbGUncyBieXRlcyB3aXRoIGl0cyBtYW5pZmVzdCBm'
     'aXJzdC4KICAgICAgICAgICAgICAgIHJlY2VpcHRbJ3JlcGFpcmVkX3RlbXBvcmFyaWVzJ10gPSBfcmVwYWlyKGhhbmRsZSwg'
     'bmFtZSwgc2Vjb25kLCBkYXRhKQogICAgICAgICAgICAgICAgZXhpc3RpbmcgPSBfZXhpc3RpbmcodGFyZ2V0LCBoYW5kbGUs'
     'IG5hbWUpCiAgICAgICAgICAgIGlmIGV4aXN0aW5nIGlzIG5vdCBOb25lOiAgICAgICAgICAgICAgICAjIG5vdGhpbmcgdG8g'
     'cHVibGlzaDogbm8gR08sIG5vIHZpZXcsIG5vIHdhaXQKICAgICAgICAgICAgICAgIHJldHVybiBfdmVyaWZpZWQocmVjZWlw'
     'dCwgaGFuZGxlLCBuYW1lLCBkYXk9ZGF5LCBleGlzdGluZz1leGlzdGluZywgZGF0YT1kYXRhLCBiaW5kaW5nPWJpbmRpbmcs'
     'CiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNvdW50PWNvdW50LCBzdGF0dXM9J0FMUkVBRFlfUFVCTElTSEVE'
     'X1ZFUklGSUVEJykKICAgICAgICAgICAgY29udHJhY3QgPSBiaW5kaW5nLmRvY3VtZW50Wydjb250cmFjdCddCiAgICAgICAg'
     'cGxhbiA9IGNvbnRyYWN0Wydjb25zdW1lcl9wbGFucyddW1BIQVNFXQogICAgICAgIGdvID0gY3R4LnJlYWRfZ28oZGF5LCBQ'
     'SEFTRSkKICAgICAgICB3aW5kb3dzLmFwcGVuZChzdGF0aWNfZ28oZ28sIHBsYW4sIGRheT1kYXksIHBoYXNlPVBIQVNFKSkK'
     'ICAgICAgICBuZWVkKHJlcXVpcmVfZ29fbW9kZSBpcyBOb25lIG9yIGdvWydtb2RlJ10gPT0gcmVxdWlyZV9nb19tb2RlLCAn'
     'TUFOSUZFU1RfR09fTU9ERScpCiAgICAgICAgY3R4LnZlcmlmeV9jaGFpbihkYXkpCiAgICAgICAgbmVlZChjdHgudmlld19w'
     'aW5uZWQoZGF5KSwgJ0NBUEFDSVRZX1ZFVE9fREFZX1VOQk9VTkQnKQogICAgICAgIGZvciBmaWxlLCBwcm9wb3NhbCBpbiBm'
     'aWxlcyArIFsoZ28sIHBsYW4pXToKICAgICAgICAgICAgY3R4LmNoZWNrX2dvKGZpbGUsIHByb3Bvc2FsKQogICAgICAgIG5l'
     'ZWQodmlld19vcGVuc19hdCBpcyBOb25lIG9yIGFsbChiZWZvcmUgPD0gdmlld19vcGVuc19hdCA8IGFmdGVyIGZvciBiZWZv'
     'cmUsIGFmdGVyIGluIHdpbmRvd3MpLAogICAgICAgICAgICAgJ01BTklGRVNUX0dPX1dJTkRPV19WSUVXJykKCiAgICAgICAg'
     'IyAtLS0tIHRoZSB2ZXRvIHZpZXc6IHBhcmsgb24gdGhlIGRlY2xhcmVkIGluc3RhbnQsIHRoZW4gcmVhZCB0aGUgcGlubmVk'
     'IGZpbGUgLS0tLQogICAgICAgIHJlY2VpcHRbJ3dhaXRlZF9zZWNvbmRzJ10gPSByb3VuZChfcGFyayh2aWV3X29wZW5zX2F0'
     'LCBjbG9jaz1jbG9jaywgc2xlZXA9c2xlZXAsIG1vbm90b25pYz1tb25vdG9uaWMsCiAgICAgICAgICAgICAgICAgICAgICAg'
     'ICAgICAgICAgICAgICAgICAgICAgICAgIG1heGltdW09bWF4X3dhaXQpLCAzKQogICAgICAgIG9ic2VydmVkLCB1bnRpbCA9'
     'IF92aWV3KGN0eCwgZGF5LCB2aWV3X29wZW5zX2F0LCBjbG9jaz1jbG9jaywgc2xlZXA9c2xlZXAsIG1vbm90b25pYz1tb25v'
     'dG9uaWMpCiAgICAgICAgcmVjZWlwdFsndmlldyddID0geydvYnNlcnZlZF9hdCc6IG9ic2VydmVkLmlzb2Zvcm1hdCgpLCAn'
     'dmFsaWRfdW50aWwnOiB1bnRpbC5pc29mb3JtYXQoKX0KICAgICAgICBuZWVkKGFsbChiZWZvcmUgPD0gb2JzZXJ2ZWQgYW5k'
     'IHVudGlsIDw9IGFmdGVyIGZvciBiZWZvcmUsIGFmdGVyIGluIHdpbmRvd3MpLCAnTUFOSUZFU1RfR09fV0lORE9XX1ZJRVcn'
     'KQoKICAgICAgICAjIC0tLS0gZmlyc3QgZ2F0ZTogdGhlIGJhcl9tYW5pZmVzdCBHTywgaW4gZnVsbCwgYmVmb3JlIGFueXRo'
     'aW5nIGlzIGNvbW1pdHRlZCAtLS0tCiAgICAgICAgY2hlY2tlZCA9IF9nYXRlKGN0eCwgZ28sIHBsYW4sIGNsb2NrPWNsb2Nr'
     'LCBjdXRvZmY9Y3V0b2ZmKQogICAgICAgIHJlY2VpcHQudXBkYXRlKGdvX3NoYTI1Nj1jaGVja2VkWydnb19zaGEnXSwgZ29f'
     'bW9kZT1nb1snbW9kZSddLCB0ZW1wbGF0ZV9zaGEyNTY9Z29bJ3RlbXBsYXRlX3NoYSddLAogICAgICAgICAgICAgICAgICAg'
     'ICAgIHdpbmRvdz1fd2luZG93KGdvKSkKCiAgICAgICAgZGVmIGxpbmtlZCgpIC0+IE5vbmU6CiAgICAgICAgICAgICMgVGhl'
     'IG5hbWUgZXhpc3RzIGZyb20gaGVyZSBvbi4gVW50aWwgdGhlIHJlYWRiYWNrIGl0IGlzIG5vdCByZXBvcnRlZCBhcyB2ZXJp'
     'ZmllZC4KICAgICAgICAgICAgcmVjZWlwdC51cGRhdGUoc3RhdHVzPSdQVUJMSVNIRURfVU5WRVJJRklFRCcsIHB1Ymxpc2hl'
     'ZF9hdD1jbG9jaygpLmlzb2Zvcm1hdCgpKQoKICAgICAgICAjIFRoZSB0ZW1wb3JhcnkgZXhpc3RzIGJlZm9yZSBwcmVwYXJl'
     'OiBhIGRpcmVjdG9yeSB0aGF0IHJlZnVzZXMgYSBuZXcgZmlsZSBzdG9wcyB0aGUKICAgICAgICAjIHJ1biBoZXJlLCB3aXRo'
     'IG5vdGhpbmcgY29tbWl0dGVkLgogICAgICAgIHdpdGggX3Jlc2VydmVkKGhhbmRsZSwgbmFtZSkgYXMgKHRlbXBvcmFyeSwg'
     'ZmQpOgogICAgICAgICAgICBpZiBwZXJzaXN0ZWQgaXMgTm9uZToKICAgICAgICAgICAgICAgICMgRnJvbSB0aGlzIGxpbmUg'
     'b24gdGhlIGJpbmRpbmcgbWF5IGJlIGNvbW1pdHRlZCwgd2hhdGV2ZXIgcHJlcGFyZSByZXR1cm5zIG9yIHJhaXNlcy4KICAg'
     'ICAgICAgICAgICAgIHJlY2VpcHRbJ3ByZXBhcmVfc3RhdHVzJ10gPSAnQVRURU1QVEVEJwogICAgICAgICAgICAgICAgcHJl'
     'cGFyZWQgPSBjdHgucHJlcGFyZShkYXkpICAgICAgICAgIyBwcmVwYXJlLWNhcGFjaXR5LWRheSwgdGhyb3VnaCB0aGUgcGFj'
     'a2FnZWQgY29kZQogICAgICAgICAgICAgICAgbmVlZCh0eXBlKHByZXBhcmVkKSBpcyBkaWN0IGFuZCBwcmVwYXJlZC5nZXQo'
     'J3N0YXR1cycpIGluICgnQ09NTUlUVEVEJywgJ0FMUkVBRFlfQ09NTUlUVEVEJykKICAgICAgICAgICAgICAgICAgICAgYW5k'
     'IGFwcC5pc19zaGEocHJlcGFyZWQuZ2V0KCdzaGEnKSksICdNQU5JRkVTVF9QUkVQQVJFX0ZBSUxFRCcpCiAgICAgICAgICAg'
     'ICAgICByZWNlaXB0WydwcmVwYXJlX3N0YXR1cyddID0gcHJlcGFyZWRbJ3N0YXR1cyddCiAgICAgICAgICAgICAgICByb3cg'
     'PSBjdHgucmVhZF9zdGF0ZSgpCiAgICAgICAgICAgICAgICBwZXJzaXN0ZWQgPSBfcGVyc2lzdGVkKHJvdywgZGF5KQogICAg'
     'ICAgICAgICAgICAgbmVlZChwZXJzaXN0ZWQgaXMgbm90IE5vbmUgYW5kIHBlcnNpc3RlZC5nZXQoJ3NoYScpID09IHByZXBh'
     'cmVkWydzaGEnXSwKICAgICAgICAgICAgICAgICAgICAgJ01BTklGRVNUX1BSRVBBUkVfVU5DT05GSVJNRUQnKQogICAgICAg'
     'ICAgICAgICAgYmluZGluZyA9IF9yZXN0b3JlKGN0eCwgcGVyc2lzdGVkKQogICAgICAgICAgICAgICAgcmVjZWlwdFsnYmlu'
     'ZGluZ19zaGEyNTYnXSA9IGJpbmRpbmcuc2hhCiAgICAgICAgICAgICAgICBuZWVkKGV4cGVjdF9zaGEgaXMgTm9uZSBvciBi'
     'aW5kaW5nLnNoYSA9PSBleHBlY3Rfc2hhLCAnTUFOSUZFU1RfQklORElOR19TSEFfTUlTTUFUQ0gnKQogICAgICAgICAgICAg'
     'ICAgbmVlZChiaW5kaW5nLmRvY3VtZW50Wydjb250cmFjdCddID09IGNvbnRyYWN0LCAnTUFOSUZFU1RfQ09OVFJBQ1RfRElW'
     'RVJHRUQnKQogICAgICAgICAgICAgICAgcGxhbiA9IGJpbmRpbmcuZG9jdW1lbnRbJ2NvbnRyYWN0J11bJ2NvbnN1bWVyX3Bs'
     'YW5zJ11bUEhBU0VdCiAgICAgICAgICAgICAgICBkYXRhLCBjb3VudCA9IF9tYW5pZmVzdChjdHgsIGJpbmRpbmcsIHJvdywg'
     'ZGF5LCBjbG9jaykKICAgICAgICAgICAgcmVjZWlwdC51cGRhdGUoYmluZGluZ19zaGEyNTY9YmluZGluZy5zaGEsIHN5bWJv'
     'bF9jb3VudD1jb3VudCwKICAgICAgICAgICAgICAgICAgICAgICAgICAgbWFuaWZlc3Rfc2hhMjU2PWhhc2hsaWIuc2hhMjU2'
     'KGRhdGEpLmhleGRpZ2VzdCgpKQogICAgICAgICAgICB3b24gPSBfcHVibGlzaChoYW5kbGUsIG5hbWUsIHRlbXBvcmFyeSwg'
     'ZmQsIGRhdGEsIGxpbmtlZD1saW5rZWQsCiAgICAgICAgICAgICAgICAgICAgICAgICAgIGJlZm9yZV9saW5rPWxhbWJkYTog'
     'X2dhdGUoY3R4LCBnbywgcGxhbiwgY2xvY2s9Y2xvY2ssIGN1dG9mZj1jdXRvZmYpKQogICAgICAgIGV4aXN0aW5nID0gX2V4'
     'aXN0aW5nKHRhcmdldCwgaGFuZGxlLCBuYW1lKQogICAgICAgIG5lZWQoZXhpc3RpbmcgaXMgbm90IE5vbmUsICdNQU5JRkVT'
     'VF9SRUFEQkFDS19GQUlMRUQnKQogICAgICAgIHJldHVybiBfdmVyaWZpZWQocmVjZWlwdCwgaGFuZGxlLCBuYW1lLCBkYXk9'
     'ZGF5LCBleGlzdGluZz1leGlzdGluZywgZGF0YT1kYXRhLCBiaW5kaW5nPWJpbmRpbmcsIGNvdW50PWNvdW50LAogICAgICAg'
     'ICAgICAgICAgICAgICAgICAgc3RhdHVzPSdQVUJMSVNIRURfVkVSSUZJRUQnIGlmIHdvbiBlbHNlICdBTFJFQURZX1BVQkxJ'
     'U0hFRF9WRVJJRklFRCcpCiAgICBmaW5hbGx5OgogICAgICAgIG9zLmNsb3NlKGhhbmRsZSkKCgpkZWYgX2luc3RhbnQodmFs'
     'dWU6IEFueSkgLT4gZGF0ZXRpbWUgfCBOb25lOgogICAgaWYgdmFsdWUgaXMgTm9uZSBvciBpc2luc3RhbmNlKHZhbHVlLCBk'
     'YXRldGltZSk6CiAgICAgICAgcGFyc2VkID0gdmFsdWUKICAgIGVsc2U6CiAgICAgICAgdHJ5OgogICAgICAgICAgICBwYXJz'
     'ZWQgPSBkYXRldGltZS5mcm9taXNvZm9ybWF0KHZhbHVlLnJlcGxhY2UoJ1onLCAnKzAwOjAwJykpCiAgICAgICAgZXhjZXB0'
     'IChWYWx1ZUVycm9yLCBBdHRyaWJ1dGVFcnJvcik6CiAgICAgICAgICAgIHJhaXNlIFJlZnVzZWQoJ01BTklGRVNUX0FSR1VN'
     'RU5UU19JTlZBTElEJykgZnJvbSBOb25lCiAgICBuZWVkKHBhcnNlZCBpcyBOb25lIG9yIHBhcnNlZC51dGNvZmZzZXQoKSBp'
     'cyBub3QgTm9uZSwgJ01BTklGRVNUX0FSR1VNRU5UU19JTlZBTElEJykKICAgIHJldHVybiBOb25lIGlmIHBhcnNlZCBpcyBO'
     'b25lIGVsc2UgcGFyc2VkLmFzdGltZXpvbmUodGltZXpvbmUudXRjKQoKCmRlZiBfc2Vzc2lvbl9kYXkoZGF5OiBBbnkpIC0+'
     'IHN0ciB8IE5vbmU6CiAgICB0cnk6CiAgICAgICAgcmV0dXJuIGRheSBpZiB0eXBlKGRheSkgaXMgc3RyIGFuZCBkYXRlLmZy'
     'b21pc29mb3JtYXQoZGF5KS5pc29mb3JtYXQoKSA9PSBkYXkgZWxzZSBOb25lCiAgICBleGNlcHQgVmFsdWVFcnJvcjoKICAg'
     'ICAgICByZXR1cm4gTm9uZQoKCmRlZiBleGVjdXRlKGJ1aWxkOiBDYWxsYWJsZVtbXSwgQ29udGV4dF0sICosIGRheTogQW55'
     'LCBkaXJlY3Rvcnk6IEFueSA9IE5vbmUsIHByZXBhcmVfZmlyc3Q6IGJvb2wgPSBGYWxzZSwKICAgICAgICAgICAgdmVyaWZ5'
     'X29ubHk6IGJvb2wgPSBGYWxzZSwgcHJlZmxpZ2h0OiBib29sID0gRmFsc2UsIGV4cGVjdF9zaGE6IEFueSA9IE5vbmUsIHZp'
     'ZXdfb3BlbnNfYXQ6IEFueSA9IE5vbmUsCiAgICAgICAgICAgIG1heF93YWl0OiBBbnkgPSAwLCByZXF1aXJlX2dvX21vZGU6'
     'IEFueSA9IE5vbmUsIGNsb2NrOiBDYWxsYWJsZVtbXSwgZGF0ZXRpbWVdLAogICAgICAgICAgICBzbGVlcDogQ2FsbGFibGVb'
     'W2Zsb2F0XSwgTm9uZV0gPSB0aW1lLnNsZWVwLAogICAgICAgICAgICBtb25vdG9uaWM6IENhbGxhYmxlW1tdLCBmbG9hdF0g'
     'PSB0aW1lLm1vbm90b25pYykgLT4gdHVwbGVbZGljdCwgaW50XToKICAgICIiIk9uZSByZWNlaXB0IGFuZCBvbmUgZXhpdCBj'
     'b2RlLiBUaGUgYXJndW1lbnRzIGFyZSBjaGVja2VkIGJlZm9yZSBhbnl0aGluZyBpcyBidWlsdC4iIiIKICAgIG1vZGUgPSAn'
     'UFJFRkxJR0hUJyBpZiBwcmVmbGlnaHQgZWxzZSAnVkVSSUZZX09OTFknIGlmIHZlcmlmeV9vbmx5IGVsc2UgJ1BVQkxJU0gn'
     'CiAgICByZWNlaXB0OiBkaWN0ID0geydzY2hlbWEnOiBSRUNFSVBUX1NDSEVNQSwgJ3N0YXR1cyc6ICdSRUZVU0VEJywgJ2Nv'
     'ZGUnOiBOb25lLCAnc2Vzc2lvbic6IF9zZXNzaW9uX2RheShkYXkpLAogICAgICAgICAgICAgICAgICAgICAnbW9kZSc6IG1v'
     'ZGV9CiAgICB0cnk6CiAgICAgICAgbmVlZChyZWNlaXB0WydzZXNzaW9uJ10gaXMgbm90IE5vbmUsICdNQU5JRkVTVF9EQVlf'
     'SU5WQUxJRCcpCiAgICAgICAgbmVlZChub3QgKHByZWZsaWdodCBhbmQgdmVyaWZ5X29ubHkpLCAnTUFOSUZFU1RfQVJHVU1F'
     'TlRTX0lOVkFMSUQnKQogICAgICAgIG5lZWQodHlwZShtYXhfd2FpdCkgaXMgaW50IGFuZCAwIDw9IG1heF93YWl0IDw9IE1B'
     'WF9XQUlUX1NFQ09ORFMsICdNQU5JRkVTVF9BUkdVTUVOVFNfSU5WQUxJRCcpCiAgICAgICAgbmVlZChleHBlY3Rfc2hhIGlz'
     'IE5vbmUgb3IgKHR5cGUoZXhwZWN0X3NoYSkgaXMgc3RyIGFuZCBfU0hBLm1hdGNoKGV4cGVjdF9zaGEpKSwgJ01BTklGRVNU'
     'X0FSR1VNRU5UU19JTlZBTElEJykKICAgICAgICBuZWVkKHJlcXVpcmVfZ29fbW9kZSBpcyBOb25lIG9yIHJlcXVpcmVfZ29f'
     'bW9kZSBpbiBHT19NT0RFUywgJ01BTklGRVNUX0FSR1VNRU5UU19JTlZBTElEJykKICAgICAgICBvcGVucyA9IF9pbnN0YW50'
     'KHZpZXdfb3BlbnNfYXQpCiAgICAgICAgIyAtLXZlcmlmeS1vbmx5IGlzIGEgcmVhZGJhY2s6IGl0IG5ldmVyIHByZXBhcmVz'
     'LCBuZXZlciB3YWl0cyBhbmQgcmVhZHMgbm8gR08uCiAgICAgICAgbmVlZChub3QgdmVyaWZ5X29ubHkgb3IgKG5vdCBwcmVw'
     'YXJlX2ZpcnN0IGFuZCBvcGVucyBpcyBOb25lIGFuZCBtYXhfd2FpdCA9PSAwIGFuZCByZXF1aXJlX2dvX21vZGUgaXMgTm9u'
     'ZSksCiAgICAgICAgICAgICAnTUFOSUZFU1RfQVJHVU1FTlRTX0lOVkFMSUQnKQogICAgICAgIG5lZWQocHJlZmxpZ2h0IG9y'
     'IGRpcmVjdG9yeSBpcyBub3QgTm9uZSwgJ01BTklGRVNUX0FSR1VNRU5UU19JTlZBTElEJykKICAgICAgICBjb2RlID0gcnVu'
     'KGJ1aWxkKCksIHJlY2VpcHQsIGRheT1kYXksIGRpcmVjdG9yeT1kaXJlY3RvcnksIHZlcmlmeV9vbmx5PXZlcmlmeV9vbmx5'
     'LCBwcmVmbGlnaHQ9cHJlZmxpZ2h0LAogICAgICAgICAgICAgICAgICAgZXhwZWN0X3NoYT1leHBlY3Rfc2hhLCB2aWV3X29w'
     'ZW5zX2F0PW9wZW5zLCBtYXhfd2FpdD1tYXhfd2FpdCwgcmVxdWlyZV9nb19tb2RlPXJlcXVpcmVfZ29fbW9kZSwKICAgICAg'
     'ICAgICAgICAgICAgIGNsb2NrPWNsb2NrLCBzbGVlcD1zbGVlcCwgbW9ub3RvbmljPW1vbm90b25pYykKICAgIGV4Y2VwdCBF'
     'eGNlcHRpb24gYXMgZXJyb3I6CiAgICAgICAgcmVjZWlwdFsnY29kZSddLCBjb2RlID0gcmVmdXNhbChlcnJvcikKICAgICAg'
     'ICBpZiByZWNlaXB0LmdldCgnc3RhdHVzJykgIT0gJ1BVQkxJU0hFRF9VTlZFUklGSUVEJzoKICAgICAgICAgICAgIyBBZnRl'
     'ciBsaW5rKCkgdGhlIG5hbWUgZXhpc3RzOiBuZXZlciByZXBvcnQgc3VjY2VzcywgbmV2ZXIgdW5kbywgbmV2ZXIgY2FsbCBp'
     'dCBhIHJlZnVzYWwuCiAgICAgICAgICAgIHJlY2VpcHRbJ3N0YXR1cyddID0gJ1JFRlVTRUQnIGlmIGNvZGUgPT0gRVhJVF9S'
     'RUZVU0VEIGVsc2UgJ1VOVkVSSUZJRUQnCiAgICByZXR1cm4gcmVjZWlwdCwgY29kZQoKCmRlZiBjb250ZXh0KHNldHRpbmdz'
     'OiBBbnksICosIG5vdzogZGF0ZXRpbWUsIHByZXBhcmVfZmlyc3Q6IGJvb2wsIGNsb2NrOiBDYWxsYWJsZVtbXSwgZGF0ZXRp'
     'bWVdKSAtPiBDb250ZXh0OgogICAgIiIiV2lyZSB0aGUgZGVwbG95ZWQgc2V0dGluZ3MuIE5vdGhpbmcgaXMgb3BlbmVkLCBy'
     'ZWFkIG9yIGNvbm5lY3RlZCB3aGlsZSBPRkYuIiIiCiAgICBuZWVkKGdldGF0dHIoc2V0dGluZ3MsICdyMmQyX3YyX3NoYWRv'
     'd19lbmFibGVkJywgRmFsc2UpLCAnTUFOSUZFU1RfU0hBRE9XX09GRicpCiAgICBuZWVkKGdldGF0dHIoc2V0dGluZ3MsICdy'
     'MmQyX3YyX2NhcGFjaXR5X3JlcXVpcmVkJywgRmFsc2UpLCAnTUFOSUZFU1RfQ0FQQUNJVFlfUkVRVUlSRUQnKQogICAgbmVl'
     'ZChib29sKGdldGF0dHIoc2V0dGluZ3MsICdkYXRhYmFzZV91cmwnLCAnJykpLCAnUEVSU0lTVEVOVF9EQVRBQkFTRV9SRVFV'
     'SVJFRCcpCiAgICBhcHAgPSBwYWNrYWdlZCgpCiAgICBmcm9tIGFwcC5yMmQyX3YyX2RvY3VtZW50X2Zvcm1hdCBpbXBvcnQg'
     'cGFyc2VfZG9jdW1lbnQKICAgIGlmIHByZXBhcmVfZmlyc3Q6CiAgICAgICAgIyBUaGUgY29sbGVjdG9yIHRoZSB3b3JrZXIg'
     'YnVpbGRzIGZvciAtLXByZXBhcmUtY2FwYWNpdHktZGF5OiByZWxlYXNlLCBjYXBhY2l0eSBjb25maWcsCiAgICAgICAgIyBz'
     'b3VyY2VzIGFuZCB0aGUgam91cm5hbCBjYXRhbG9nLiBJdCBuZWVkcyB0aGUgcmVhZGVyJ3MgbW91bnRzIGFuZCBlbnZpcm9u'
     'bWVudC4KICAgICAgICBmcm9tIGFwcC5yMmQyX3YyX2NhcGFjaXR5X2JvdW5kIGltcG9ydCBDYXBhY2l0eUJvdW5kQ29sbGVj'
     'dG9yCiAgICAgICAgZnJvbSBhcHAucjJkMl92Ml9jYXBhY2l0eV93aXJpbmcgaW1wb3J0IHByZXBhcmVfY2FwYWNpdHlfZGF5'
     'CiAgICAgICAgZnJvbSBhcHAucjJkMl92Ml9zaGFkb3dfd29ya2VyIGltcG9ydCBidWlsZF9jb2xsZWN0b3IKICAgICAgICBj'
     'b2xsZWN0b3IgPSBidWlsZF9jb2xsZWN0b3Ioc2V0dGluZ3MsIG5vdz1ub3cpCiAgICAgICAgbmVlZChpc2luc3RhbmNlKGNv'
     'bGxlY3RvciwgQ2FwYWNpdHlCb3VuZENvbGxlY3RvciksICdDQVBBQ0lUWV9DT05GSUdfUkVRVUlSRUQnKQogICAgICAgIGF1'
     'dGhvcml0eSA9IGNvbGxlY3Rvci5jYXBhY2l0eV9sb2FkZXIuYXV0aG9yaXR5CiAgICAgICAgY29uZmlnLCByZWxlYXNlLCBj'
     'YWxlbmRhciwgc3RvcmUgPSBhdXRob3JpdHkuY29uZmlnLCBjb2xsZWN0b3IucmVsZWFzZSwgY29sbGVjdG9yLmNhbGVuZGFy'
     'LCBjb2xsZWN0b3Iuc3RvcmUKICAgICAgICBwcmVwYXJlID0gbGFtYmRhIGRheTogcHJlcGFyZV9jYXBhY2l0eV9kYXkoc3Rv'
     'cmUsIGNvbGxlY3RvciwgZGF5KQogICAgZWxzZToKICAgICAgICBmcm9tIGFwcC5kYXRhYmFzZSBpbXBvcnQgRGF0YWJhc2UK'
     'ICAgICAgICBmcm9tIGFwcC5yMmQyX3YyX2NhbGVuZGFyIGltcG9ydCBTaGFkb3dDYWxlbmRhcgogICAgICAgIGZyb20gYXBw'
     'LnIyZDJfdjJfY2FwYWNpdHlfYm9vdHN0cmFwIGltcG9ydCBDYXBhY2l0eUNvbmZpZwogICAgICAgIGZyb20gYXBwLnIyZDJf'
     'djJfc2hhZG93IGltcG9ydCBSZWxlYXNlCiAgICAgICAgZnJvbSBhcHAucjJkMl92Ml9zaGFkb3dfd29ya2VyIGltcG9ydCBf'
     'cmVsZWFzZV9ieXRlcwogICAgICAgIGZyb20gYXBwLnIyZDJfdjJfc3RvcmUgaW1wb3J0IFBvc3RncmVzU2hhZG93U3RvcmUK'
     'ICAgICAgICBjYWxlbmRhciA9IFNoYWRvd0NhbGVuZGFyKCkKICAgICAgICByZWxlYXNlID0gUmVsZWFzZS52ZXJpZnkoX3Jl'
     'bGVhc2VfYnl0ZXMoc3RyKHNldHRpbmdzLnIyZDJfdjJfc2hhZG93X3JlbGVhc2VfZmlsZSkpLAogICAgICAgICAgICAgICAg'
     'ICAgICAgICAgICAgICAgICBzZXR0aW5ncy5yMmQyX3YyX3NoYWRvd19yZWxlYXNlX3NoYSwgbm93PW5vdywgYnVpbGRfc2hh'
     'PXNldHRpbmdzLmJ1aWxkX3NoYSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY2FsZW5kYXI9Y2FsZW5kYXIp'
     'CiAgICAgICAgY29uZmlnID0gQ2FwYWNpdHlDb25maWcoc2V0dGluZ3MpCiAgICAgICAgY29uZmlnLnJlbGVhc2UocmVsZWFz'
     'ZSkKICAgICAgICBhdXRob3JpdHksIHN0b3JlLCBwcmVwYXJlID0gY29uZmlnLmF1dGhvcml0eSwgUG9zdGdyZXNTaGFkb3dT'
     'dG9yZShEYXRhYmFzZShzZXR0aW5ncykuY29ubmVjdGlvbiksIE5vbmUKCiAgICBkZWYgdmVyaWZ5X2NoYWluKGRheTogc3Ry'
     'KSAtPiBOb25lOgogICAgICAgIF9jb2RlZChsYW1iZGE6IGF1dGhvcml0eS5hY3RfYihjbG9jaygpLCBlcG9jaD1yZWxlYXNl'
     'LmVwb2NoLCBmaXJzdD1yZWxlYXNlLmZpcnN0X3Nlc3Npb24uaXNvZm9ybWF0KCksCiAgICAgICAgICAgICAgICAgICAgICAg'
     'ICAgICAgICAgICAgICAgIGRheT1kYXkpLCAnTUFOSUZFU1RfQ0hBSU5fVU5WRVJJRklFRCcpCgogICAgZGVmIGNoZWNrX2dv'
     'KGdvOiBkaWN0LCBwbGFuOiBkaWN0KSAtPiBOb25lOgogICAgICAgIGdvX3JlY29yZHMoYXV0aG9yaXR5LCBnbykgICAgICAg'
     'ICAgICAgICAgICAgIyBwcmVjaXNlIGNvZGVzIGZpcnN0CiAgICAgICAgc3RhdGljX2RvY3VtZW50cyhhdXRob3JpdHksIGdv'
     'LCBwbGFuKSAgICAgICAjIHRoZW4gZXZlcnl0aGluZyB2ZXJpZnlfZ28gYXNrcywgbWludXMgdGhlIHZpZXcKCiAgICAjIEV2'
     'ZXJ5IGRpcmVjdG9yeSB0aGUgc2V0dGluZ3MgYW5kIHRoZSBjYXBhY2l0eSBjb25maWcgbmFtZS4gVGhlIG1hbmlmZXN0IGRp'
     'cmVjdG9yeSBtdXN0CiAgICAjIGJlIG5vbmUgb2YgdGhlbSwgaG9sZCBub25lIG9mIHRoZW0gYW5kIGxpZSBpbnNpZGUgbm9u'
     'ZSBvZiB0aGVtLgogICAgcmVzdG9yZSA9IGNvbmZpZy5ib2R5LmdldCgncmVzdG9yZV9yZXZvY2F0aW9uJykKICAgIHByb3Rl'
     'Y3RlZCA9IFtvcy5wYXRoLmRpcm5hbWUoc3RyKGdldGF0dHIoc2V0dGluZ3MsICdyMmQyX3YyX2NhcGFjaXR5X2NvbmZpZ19m'
     'aWxlJywgJycpIG9yICcnKSksCiAgICAgICAgICAgICAgICAgb3MucGF0aC5kaXJuYW1lKHN0cihnZXRhdHRyKHNldHRpbmdz'
     'LCAncjJkMl92Ml9zaGFkb3dfcmVsZWFzZV9maWxlJywgJycpIG9yICcnKSksCiAgICAgICAgICAgICAgICAgKihzdHIoZ2V0'
     'YXR0cihzZXR0aW5ncywgbmFtZSwgJycpIG9yICcnKSBmb3IgbmFtZSBpbiAoCiAgICAgICAgICAgICAgICAgICAgICdyMmQy'
     'X3YyX21hc3NpdmVfam91cm5hbF9kaXInLCAncjJkMl92Ml9zaGFkb3dfc291cmNlX2RpcicsICdyMmQyX21pY3Jvc3RydWN0'
     'dXJlX3Jhd19kaXInKSksCiAgICAgICAgICAgICAgICAgKihwaW5bJ3BhdGgnXSBmb3IgcGluIGluIGNvbmZpZy5ib2R5Wydy'
     'b290cyddLnZhbHVlcygpKSwKICAgICAgICAgICAgICAgICAqKFtyZXN0b3JlWydyb290J11bJ3BhdGgnXV0gaWYgdHlwZShy'
     'ZXN0b3JlKSBpcyBkaWN0IGVsc2UgW10pXQoKICAgIGRlZiByZWFkX2dvKGRheTogc3RyLCBwaGFzZTogc3RyKSAtPiBkaWN0'
     'OgogICAgICAgIGRlZiBsb2FkKCkgLT4gZGljdDoKICAgICAgICAgICAgYm9keSA9IGNvbmZpZy5yb290c1snZ28nXS5qc29u'
     'KCdzZXNzaW9uPScgKyBkYXkgKyAnLicgKyBwaGFzZSArICcuanNvbicpCiAgICAgICAgICAgIG5lZWQodHlwZShib2R5KSBp'
     'cyBkaWN0IGFuZCBzZXQoYm9keSkgPT0geydnbyd9LCAnTUFOSUZFU1RfR09fRklFTERTJykKICAgICAgICAgICAgcmV0dXJu'
     'IGJvZHlbJ2dvJ10KICAgICAgICByZXR1cm4gX2NvZGVkKGxvYWQsICdNQU5JRkVTVF9HT19JTlZBTElEJywgbWlzc2luZz0n'
     'TUFOSUZFU1RfR09fTUlTU0lORycpCgogICAgZGVmIHJlYWRfcGF5bG9hZChkYXk6IHN0cikgLT4gZGljdDoKICAgICAgICBy'
     'ZXR1cm4gX2NvZGVkKGxhbWJkYTogY29uZmlnLnJvb3RzWydwYXlsb2FkJ10uanNvbignc2Vzc2lvbj0nICsgZGF5ICsgJy5q'
     'c29uJyksCiAgICAgICAgICAgICAgICAgICAgICAnTUFOSUZFU1RfUEFZTE9BRF9JTlZBTElEJywgbWlzc2luZz0nTUFOSUZF'
     'U1RfUEFZTE9BRF9NSVNTSU5HJykKCiAgICBkZWYgdmlld19waW5uZWQoZGF5OiBzdHIpIC0+IGJvb2w6CiAgICAgICAgY29u'
     'ZmlnLnZlcmlmeSgpCiAgICAgICAgcmV0dXJuIHR5cGUoY29uZmlnLmJvZHlbJ3ZldG9fdmlld3MnXS5nZXQoZGF5KSkgaXMg'
     'ZGljdAoKICAgIGRlZiB2ZXRvX2JvdW5kcyhkYXk6IHN0cikgLT4gdHVwbGVbZGF0ZXRpbWUsIGRhdGV0aW1lXToKICAgICAg'
     'ICBjb25maWcudmVyaWZ5KCkKICAgICAgICBwaW4gPSBjb25maWcuYm9keVsndmV0b192aWV3cyddLmdldChkYXkpCiAgICAg'
     'ICAgbmVlZCh0eXBlKHBpbikgaXMgZGljdCwgJ0NBUEFDSVRZX1ZFVE9fREFZX1VOQk9VTkQnKQogICAgICAgIHJhdyA9IGNv'
     'bmZpZy5yb290c1snZG9jdW1lbnRzJ10ucmVhZChwaW5bJ2ZpbGUnXSkKICAgICAgICBuZWVkKGhhc2hsaWIuc2hhMjU2KHJh'
     'dykuaGV4ZGlnZXN0KCkgPT0gcGluWydzaGEyNTYnXSwgJ1ZFVE9fSEFTSF9NSVNNQVRDSCcpCiAgICAgICAgYm9keSA9IHBh'
     'cnNlX2RvY3VtZW50KHJhdylbJ2JvZHknXQogICAgICAgIHJldHVybiBhcHAudXRjKGJvZHlbJ29ic2VydmVkX2F0J10pLCBh'
     'cHAudXRjKGJvZHlbJ3ZhbGlkX3VudGlsJ10pCgogICAgcmV0dXJuIENvbnRleHQocmVsZWFzZT1yZWxlYXNlLCBjYWxlbmRh'
     'cj1jYWxlbmRhciwgcmVhZF9zdGF0ZT1sYW1iZGE6IHN0b3JlLnJlYWQocmVsZWFzZS5lcG9jaCksCiAgICAgICAgICAgICAg'
     'ICAgICB2ZXJpZnlfYmluZGluZz1sYW1iZGEgZG9jdW1lbnQ6IGF1dGhvcml0eS52ZXJpZnlfYmluZGluZyhkb2N1bWVudCwg'
     'Y2xvY2soKSksCiAgICAgICAgICAgICAgICAgICB2ZXJpZnlfZ289bGFtYmRhIGdvLCBwbGFuOiBhdXRob3JpdHkudmVyaWZ5'
     'X2dvKGdvLCBwbGFuLCBjbG9jaygpKSwKICAgICAgICAgICAgICAgICAgIHZlcmlmeV9jaGFpbj12ZXJpZnlfY2hhaW4sIGNo'
     'ZWNrX2dvPWNoZWNrX2dvLCByZWFkX2dvPXJlYWRfZ28sIHJlYWRfcGF5bG9hZD1yZWFkX3BheWxvYWQsCiAgICAgICAgICAg'
     'ICAgICAgICB2aWV3X3Bpbm5lZD12aWV3X3Bpbm5lZCwgdmV0b19ib3VuZHM9dmV0b19ib3VuZHMsIHByZXBhcmU9cHJlcGFy'
     'ZSwgcHJvdGVjdGVkPXR1cGxlKHByb3RlY3RlZCksCiAgICAgICAgICAgICAgICAgICBwaW5zPXsncmVsZWFzZV9zaGEyNTYn'
     'OiByZWxlYXNlLnJlY2VpcHRfc2hhLCAnY2FwYWNpdHlfY29uZmlnX3NoYTI1Nic6IGNvbmZpZy5zaGEsCiAgICAgICAgICAg'
     'ICAgICAgICAgICAgICAncGFja2FnZV9zaGEyNTYnOiByZWxlYXNlLmltcGxlbWVudGF0aW9uX3BhY2thZ2Vfc2hhLCAnYnVp'
     'bGRfc2hhJzogc2V0dGluZ3MuYnVpbGRfc2hhLAogICAgICAgICAgICAgICAgICAgICAgICAgJ2NhcGFjaXR5X3ZldG9fbW9k'
     'ZSc6IGNvbmZpZy52ZXRvX21vZGUsCiAgICAgICAgICAgICAgICAgICAgICAgICAnbWFzc2l2ZV9iYXJzX2VuYWJsZWQnOiBi'
     'b29sKGdldGF0dHIoc2V0dGluZ3MsICdyMmQyX3YyX21hc3NpdmVfYmFyc19lbmFibGVkJywgRmFsc2UpKX0pCgoKY2xhc3Mg'
     'X1BhcnNlcihhcmdwYXJzZS5Bcmd1bWVudFBhcnNlcik6CiAgICBkZWYgZXJyb3Ioc2VsZiwgbWVzc2FnZTogc3RyKTogICAg'
     'ICAgICAgICAgICAgICAjIG9uZSBKU09OIGxpbmUsIG5ldmVyIGFyZ3BhcnNlJ3Mgb3duIHRleHQKICAgICAgICByYWlzZSBS'
     'ZWZ1c2VkKCdNQU5JRkVTVF9BUkdVTUVOVFNfSU5WQUxJRCcpCgoKZGVmIF91dGNub3coKSAtPiBkYXRldGltZToKICAgIHJl'
     'dHVybiBkYXRldGltZS5ub3codGltZXpvbmUudXRjKQoKCmRlZiBtYWluKGFyZ3Y6IGxpc3Rbc3RyXSB8IE5vbmUgPSBOb25l'
     'LCAqLCBjbG9jazogQ2FsbGFibGVbW10sIGRhdGV0aW1lXSA9IF91dGNub3csCiAgICAgICAgIHNsZWVwOiBDYWxsYWJsZVtb'
     'ZmxvYXRdLCBOb25lXSA9IHRpbWUuc2xlZXAsIG1vbm90b25pYzogQ2FsbGFibGVbW10sIGZsb2F0XSA9IHRpbWUubW9ub3Rv'
     'bmljKSAtPiBpbnQ6CiAgICByZWNlaXB0OiBkaWN0ID0geydzY2hlbWEnOiBSRUNFSVBUX1NDSEVNQSwgJ3N0YXR1cyc6ICdS'
     'RUZVU0VEJywgJ2NvZGUnOiAnTUFOSUZFU1RfQVJHVU1FTlRTX0lOVkFMSUQnLAogICAgICAgICAgICAgICAgICAgICAnc2Vz'
     'c2lvbic6IE5vbmUsICdtb2RlJzogTm9uZX0KICAgIGNvZGUgPSBFWElUX1JFRlVTRUQKICAgIHRyeToKICAgICAgICAjIE5v'
     'IGhlbHAgYWN0aW9uOiAtaCBpcyBhIHdyb25nIGFyZ3VtZW50IGxpa2UgYW55IG90aGVyLCBvbmUgSlNPTiBsaW5lIGFuZCBl'
     'eGl0IDMuCiAgICAgICAgcGFyc2VyID0gX1BhcnNlcihwcm9nPSdtYW5pZmVzdF93cml0ZXInLCBhbGxvd19hYmJyZXY9RmFs'
     'c2UsIGFkZF9oZWxwPUZhbHNlKQogICAgICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy0tZGF5JywgcmVxdWlyZWQ9VHJ1ZSwg'
     'aGVscD0nU2Vzc2lvbiBkYXRlLCBZWVlZLU1NLUREIChOZXcgWW9yayknKQogICAgICAgIHBhcnNlci5hZGRfYXJndW1lbnQo'
     'Jy0tbWFuaWZlc3QtZGlyZWN0b3J5JywgdHlwZT1QYXRoLCBoZWxwPSdSZXF1aXJlZCB1bmxlc3MgLS1wcmVmbGlnaHQnKQog'
     'ICAgICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy0tcHJlcGFyZS1maXJzdCcsIGFjdGlvbj0nc3RvcmVfdHJ1ZScsCiAgICAg'
     'ICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSdDb21taXQgdGhlIGNhcGFjaXR5IGJpbmRpbmcgaW4gdGhpcyBwcm9jZXNz'
     'IHdoZW4gaXQgaXMgbm90IGNvbW1pdHRlZCB5ZXQnKQogICAgICAgIHBhcnNlci5hZGRfYXJndW1lbnQoJy0tdmVyaWZ5LW9u'
     'bHknLCBhY3Rpb249J3N0b3JlX3RydWUnLCBoZWxwPSdDb21wYXJlIHRoZSBmaWxlIHdpdGggdGhlIGJpbmRpbmc7IG5ldmVy'
     'IHdyaXRlJykKICAgICAgICBwYXJzZXIuYWRkX2FyZ3VtZW50KCctLXByZWZsaWdodCcsIGFjdGlvbj0nc3RvcmVfdHJ1ZScs'
     'CiAgICAgICAgICAgICAgICAgICAgICAgICAgICBoZWxwPSdDb250ZXh0IGFuZCBzdGF0aWMgdmFsaWRhdGlvbiBvbmx5OyBu'
     'ZXZlciB3YWl0cywgcHJlcGFyZXMsIHdyaXRlcyBvciByZWFkcyB0aGUgdmlldycpCiAgICAgICAgcGFyc2VyLmFkZF9hcmd1'
     'bWVudCgnLS1leHBlY3QtYmluZGluZy1zaGEnLCBoZWxwPSdTSEEgb2YgYW4gYWxyZWFkeSBhY2NlcHRlZCBwcmVwYXJlLWNh'
     'cGFjaXR5LWRheScpCiAgICAgICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLS12aWV3LW9wZW5zLWF0JywgaGVscD0nb2JzZXJ2'
     'ZWRfYXQgb2YgdGhlIHBpbm5lZCB2ZXRvIHZpZXcsIElTTyA4NjAxIHdpdGggb2Zmc2V0JykKICAgICAgICBwYXJzZXIuYWRk'
     'X2FyZ3VtZW50KCctLW1heC13YWl0LXNlY29uZHMnLCB0eXBlPWludCwgZGVmYXVsdD0wLAogICAgICAgICAgICAgICAgICAg'
     'ICAgICAgICAgaGVscD0nTG9uZ2VzdCBwYXJraW5nIGJlZm9yZSAtLXZpZXctb3BlbnMtYXQgKDAtJWQpJyAlIE1BWF9XQUlU'
     'X1NFQ09ORFMpCiAgICAgICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnLS1yZXF1aXJlLWdvLW1vZGUnLCBjaG9pY2VzPUdPX01P'
     'REVTLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgaGVscD0nUmVmdXNlIGEgYmFyX21hbmlmZXN0IEdPIG9mIGFub3Ro'
     'ZXIgbW9kZSwgYmVmb3JlIHRoZSB3YWl0JykKICAgICAgICBhcmdzID0gcGFyc2VyLnBhcnNlX2FyZ3MoYXJndikKCiAgICAg'
     'ICAgZGVmIGJ1aWxkKCkgLT4gQ29udGV4dDoKICAgICAgICAgICAgcGFja2FnZWQoKQogICAgICAgICAgICBmcm9tIGFwcC5j'
     'b25maWcgaW1wb3J0IGdldF9zZXR0aW5ncwogICAgICAgICAgICByZXR1cm4gY29udGV4dChnZXRfc2V0dGluZ3MoKSwgbm93'
     'PWNsb2NrKCksIHByZXBhcmVfZmlyc3Q9YXJncy5wcmVwYXJlX2ZpcnN0LCBjbG9jaz1jbG9jaykKCiAgICAgICAgcmVjZWlw'
     'dCwgY29kZSA9IGV4ZWN1dGUoYnVpbGQsIGRheT1hcmdzLmRheSwgZGlyZWN0b3J5PWFyZ3MubWFuaWZlc3RfZGlyZWN0b3J5'
     'LAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHByZXBhcmVfZmlyc3Q9YXJncy5wcmVwYXJlX2ZpcnN0LCB2ZXJp'
     'Znlfb25seT1hcmdzLnZlcmlmeV9vbmx5LAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHByZWZsaWdodD1hcmdz'
     'LnByZWZsaWdodCwgZXhwZWN0X3NoYT1hcmdzLmV4cGVjdF9iaW5kaW5nX3NoYSwKICAgICAgICAgICAgICAgICAgICAgICAg'
     'ICAgICAgICB2aWV3X29wZW5zX2F0PWFyZ3Mudmlld19vcGVuc19hdCwgbWF4X3dhaXQ9YXJncy5tYXhfd2FpdF9zZWNvbmRz'
     'LAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHJlcXVpcmVfZ29fbW9kZT1hcmdzLnJlcXVpcmVfZ29fbW9kZSwg'
     'Y2xvY2s9Y2xvY2ssIHNsZWVwPXNsZWVwLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIG1vbm90b25pYz1tb25v'
     'dG9uaWMpCiAgICBleGNlcHQgUmVmdXNlZDoKICAgICAgICBwYXNzICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg'
     'ICAgICAgICMgdGhlIGFyZ3VtZW50IHJlZnVzYWwgcHJlcGFyZWQgYWJvdmUKICAgIHN5cy5zdGRvdXQud3JpdGUoanNvbi5k'
     'dW1wcyhyZWNlaXB0LCBzb3J0X2tleXM9VHJ1ZSwgc2VwYXJhdG9ycz0oJywnLCAnOicpLCBhbGxvd19uYW49RmFsc2UpICsg'
     'J1xuJykKICAgIHN5cy5zdGRvdXQuZmx1c2goKQogICAgcmV0dXJuIGNvZGUKCgppZiBfX25hbWVfXyA9PSAnX19tYWluX18n'
     'OgogICAgIyBOb3RoaW5nIGJ1dCB0aGUgcmVjZWlwdCBsaW5lIG1heSByZWFjaCB0aGUgb3V0cHV0OiBsaWJyYXJ5IGxvZyBy'
     'ZWNvcmRzIGFuZCB3YXJuaW5ncwogICAgIyBjb3VsZCBjYXJyeSBhIGNvbm5lY3Rpb24gc3RyaW5nIG9yIGEgZmlsZSBuYW1l'
     'LgogICAgbG9nZ2luZy5kaXNhYmxlKGxvZ2dpbmcuQ1JJVElDQUwpCiAgICB3YXJuaW5ncy5zaW1wbGVmaWx0ZXIoJ2lnbm9y'
     'ZScpCiAgICByYWlzZSBTeXN0ZW1FeGl0KG1haW4oKSkK'))
# ---- WRITER BLOCK END ----
CHAIN_LABELS=tuple(row[0] for row in K4_CHAIN_DOCUMENTS)

# pins.env: the twelve names in their order (reader README, "Environment files" item 2; L1 is the twelfth line).
PINS_NAMES=('C3PO_BUILD_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA','C3PO_R2D2_V2_SHADOW_SOURCE_DIR',
            'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR','C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR','C3PO_R2D2_V2_CAPACITY_REQUIRED',
            'C3PO_R2D2_V2_CAPACITY_VETO_MODE','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA',
            'C3PO_R2D2_V2_SHADOW_POLL_SECONDS','C3PO_READER_LAUNCHER_SHA256')
PINS_CONSTANTS={'C3PO_BUILD_SHA':K4_CODE_REVISION,'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':K4_RELEASE_SHA,
                'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR':CONTAINER_DATA_ROOT+'/provider=eodhd/microstructure/raw',
                'C3PO_R2D2_V2_CAPACITY_REQUIRED':'true','C3PO_R2D2_V2_CAPACITY_VETO_MODE':K4_VETO_MODE,
                'C3PO_R2D2_V2_SHADOW_POLL_SECONDS':'1.0'}
JOURNAL_TARGET_PATTERN='/c3po-[a-z0-9][a-z0-9-]*'
JOURNAL_TARGETS_TAKEN=(CONTAINER_CAPACITY_ROOT,CONTAINER_LAUNCHER_ROOT)
UNIT_FILE_MODE=0o644
MAX_UNIT_BYTES=65536

K4_DELIVERY_KEYS={'CHAIN_STATIC':frozenset(('documents_parent','config_parent','static_config')),
                  'PINS':frozenset(('reader_parent','config_parent','unit_parent','source_chain','journal_chain','values','sha256','bytes','producer_unit_sha256',
                                    'reader_unit_sha256')),
                  'LAUNCHER':frozenset(('reader_parent','launcher')),
                  'WRITER':frozenset(('config_parent','writer_sha256'))}

SCOPE_STATEMENT=('Delivers, for epoch '+K4_EPOCH+', exactly one of four signed modes. CHAIN_STATIC: the seven chain documents '
                 'compiled into this source into '+DOCUMENTS_DIRECTORY+' and the static capacity config '+STATIC_CONFIG_NAME+' whose bytes '
                 'the request signs into '+CAPACITY_CONFIG_DIRECTORY+'. PINS: '+READER_CONFIG_DIRECTORY+'/'+PINS_NAME+', twelve lines rendered '
                 'from the signed values, only after the static config, the launcher and the two installed units it names are read on '
                 'the host and found to be the signed bytes, and the host sources of the source-root and journal binds are walked as '
                 'root-controlled chains. LAUNCHER: the directory '+LAUNCHER_DIRECTORY+' and in it '+LAUNCHER_NAME+' '
                 'holding the bytes the request signs. WRITER: in '+CAPACITY_CONFIG_DIRECTORY+' the capacity-day manifest writer compiled '
                 'into this source, under the content-addressed name '+WRITER_STEM+'<sha256>'+WRITER_EXTENSION+'. Every file root:root 0600 and every directory root:root 0700, by exclusive '
                 'creation relative to a held descriptor of a parent walked from "/" against signed rows, fsync, and a readback of '
                 'the bytes and of the directories through descriptors inside the run. Nothing that exists is overwritten, renamed, '
                 'chmodded, chowned or removed, except the temporary of this run once its identity is proved. No process is '
                 'started, no secret is read or written, no container is touched and nothing is activated.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':K4_EPOCH,'modes':list(K4_MODES),
       'placement':{'reader_config_directory':READER_CONFIG_DIRECTORY,'capacity_root':CAPACITY_ROOT,'documents':DOCUMENTS_DIRECTORY,
                    'capacity_config':CAPACITY_CONFIG_DIRECTORY,'launcher_directory':LAUNCHER_DIRECTORY,'unit_directory':UNIT_DIRECTORY,
                    'open_roots':None},
       'chain_documents':[{'label':label,'file':name,'sha256':digest,'bytes':size} for label,name,digest,size,_ in K4_CHAIN_DOCUMENTS],
       'static_config':{'directory':CAPACITY_CONFIG_DIRECTORY,'name':STATIC_CONFIG_NAME,'schema':STATIC_CONFIG_SCHEMA,'max_bytes':MAX_STATIC_CONFIG_BYTES,
                        'release_sha':K4_RELEASE_SHA,'package_sha':K4_PACKAGE_SHA,'veto_mode':K4_VETO_MODE},
       'pins_env':{'path':READER_CONFIG_DIRECTORY+'/'+PINS_NAME,'names':list(PINS_NAMES),'constants':PINS_CONSTANTS,
                   'path_rule':'the core clean_path: /[A-Za-z0-9._=/_-]{0,199}, no //, no . or .. component, no trailing slash, at most 16 '
                               'components (stricter than the README grammar)','journal_target_pattern':JOURNAL_TARGET_PATTERN,'journal_targets_taken':list(JOURNAL_TARGETS_TAKEN),
                   'read_before':{'static_config':CAPACITY_CONFIG_DIRECTORY+'/'+STATIC_CONFIG_NAME+' (judged again as in CHAIN_STATIC)',
                                  'launcher':LAUNCHER_DIRECTORY+'/'+LAUNCHER_NAME,
                                  'units':[UNIT_DIRECTORY+'/'+PRODUCER_UNIT_NAME,UNIT_DIRECTORY+'/'+READER_UNIT_NAME]}},
       'launcher':{'directory':LAUNCHER_DIRECTORY,'name':LAUNCHER_NAME,'max_bytes':MAX_LAUNCHER_BYTES},
       'writer':{'directory':CAPACITY_CONFIG_DIRECTORY,'name':WRITER_STEM+'<sha256>'+WRITER_EXTENSION,'sha256':K4_WRITER[0] if K4_WRITER else None,
                 'bytes':K4_WRITER[1] if K4_WRITER else None,'bytes_compiled_into_this_source':True},
       'bind_sources_root_controlled':{'decision':'Codex decision 6 (#429 5985748037)','source_root':K4_SOURCE_ROOT,'journal':K4_JOURNAL_HOST,
                                       'capacity':CAPACITY_ROOT,'launcher':LAUNCHER_DIRECTORY},
       'files':FILES_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the files this run delivered (readback inside the run)',
                             'PINS only: the static config, the launcher and the two unit files it names (hashed and compared, never copied)'],
       'processes_started':0,
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the temporary this run created','a process','docker','systemctl',
                'a shell','a network connection','a secret','activation','a container','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'static_config_bytes':MAX_STATIC_CONFIG_BYTES,'launcher_bytes':MAX_LAUNCHER_BYTES,'free_bytes_floor':FREE_BYTES_FLOOR,
                 'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the seven creating calls. No process."""


# ---------------------------------------------------------------- pure: the plan
def chain_document_bytes(index):
    """The bytes of one compiled chain document, proved against its compiled hash and size."""
    label,name,digest,size,encoded=K4_CHAIN_DOCUMENTS[index]
    raw=base64.b64decode(encoded.encode('ascii'),validate=True)
    need(len(raw)==size and sha(raw)==digest,'CHAIN_DOCUMENT_NOT_THE_COMPILED_HASH')
    return raw

def writer_bytes():
    """The compiled manifest writer, proved against its compiled hash and size."""
    digest,size,encoded=K4_WRITER
    raw=base64.b64decode(encoded.encode('ascii'),validate=True)
    need(len(raw)==size and sha(raw)==digest,'WRITER_NOT_THE_COMPILED_HASH')
    return raw

def signed_bytes(item,limit,code):
    """Bytes the request carries: strict base64, their SHA-256 and size signed beside them."""
    need(type(item) is dict and set(item)==set(K4_BYTES_KEYS) and hexpin(item['sha256']) and integer(item['bytes'],1,limit)
         and type(item['content_b64']) is str,code)
    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused(code) from None
    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],code)
    return raw

def private_chain(rows,path):
    """A chain controlled by root alone that receives a new entry: no open root (uid 0, nothing writable by group or
    other on any component), group 0 and no setgid anywhere, and the parent itself exactly root:root 0700."""
    validate_chain(rows,path,open_root=None,receives_entry=True)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_NOT_ROOT_CONTROLLED')
    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,PRIVATE_DIRECTORY_MODE),'PARENT_NOT_ROOT_0700')
    return rows

def static_config_of(raw):
    """The static capacity config, judged from its bytes: canonical JSON of exactly the documents tool's keys, this
    epoch's identity, the approved release and package, the seven chain pins equal to the compiled documents, one
    TEMPLATE pin and one view pin of a session of the epoch, the three container roots under /c3po-capacity."""
    try:config=strict(raw,MAX_STATIC_CONFIG_BYTES)
    except Exception:raise Refused('STATIC_CONFIG_INVALID') from None
    need(type(config) is dict and canonical(config)==raw and set(config)==set(STATIC_CONFIG_KEYS),'STATIC_CONFIG_INVALID')
    need(config['schema']==STATIC_CONFIG_SCHEMA and config['r2d2_v2_capacity_veto_mode']==K4_VETO_MODE and config['restore_revocation'] is None
         and hexpin(config['calendar_pin_sha']),'STATIC_CONFIG_INVALID')
    identity=config['identity']
    need(type(identity) is dict and set(identity)==set(STATIC_IDENTITY_KEYS) and identity['epoch']==K4_EPOCH and identity['namespace']==K4_EPOCH
         and identity['first_session']==K4_SESSIONS[0] and identity['authorized_sessions']==list(K4_SESSIONS)
         and hexpin(identity['document_order_sha']) and hexpin(identity['runtime_order_sha']),'STATIC_CONFIG_IDENTITY')
    need(config['release_sha']==K4_RELEASE_SHA and config['package_sha']==K4_PACKAGE_SHA,'STATIC_CONFIG_RELEASE')
    pins=config['document_pins']
    need(type(pins) is dict and set(pins)==set(CHAIN_LABELS)|{'TEMPLATE'},'STATIC_CONFIG_CHAIN_PINS')
    for label,name,digest,_,_ in K4_CHAIN_DOCUMENTS:need(pins[label]=={'file':name,'sha256':digest},'STATIC_CONFIG_CHAIN_PINS')
    template=pins['TEMPLATE'];views=config['veto_views']
    need(type(template) is dict and set(template)=={'file','sha256'} and hexpin(template['sha256'])
         and template['file'] in ['session='+day+'.template.md' for day in K4_SESSIONS],'STATIC_CONFIG_ANCHOR')
    need(type(views) is dict and len(views)==1 and template['file']=='session='+list(views)[0]+'.template.md','STATIC_CONFIG_ANCHOR')
    view=list(views.values())[0]
    need(type(view) is dict and set(view)=={'file','sha256'} and hexpin(view['sha256']) and text(view['file'],K4_DOCUMENT_FILE)
         and view['file'].startswith('session='+list(views)[0]+'.view-'),'STATIC_CONFIG_ANCHOR')
    roots=config['roots']
    need(type(roots) is dict and set(roots)==set(CAPACITY_ROOT_NAMES)
         and all(type(roots[name]) is dict and set(roots[name])=={'path','identity'} and roots[name]['path']==CONTAINER_CAPACITY_ROOT+'/'+name and hexpin(roots[name]['identity'])
                 for name in CAPACITY_ROOT_NAMES),'STATIC_CONFIG_ROOTS')
    return config

def pins_lines(values):
    """The twelve values judged one by one, then the bytes of pins.env: NAME=value and one newline each, in order."""
    need(type(values) is dict and set(values)==set(PINS_NAMES) and all(type(value) is str for value in values.values()),'PINS_VALUES_INVALID')
    for name,value in PINS_CONSTANTS.items():need(values[name]==value,'PINS_CONSTANT_MISMATCH')
    def container_path(value,depth):
        parts=value.split('/')
        return clean_path(value) and value.startswith(CONTAINER_DATA_ROOT+'/') and len(parts)==len(CONTAINER_DATA_ROOT.split('/'))+depth
    need(container_path(values['C3PO_R2D2_V2_SHADOW_RELEASE_FILE'],2),'PINS_RELEASE_FILE')
    source=values['C3PO_R2D2_V2_SHADOW_SOURCE_DIR']        # a dedicated read-only bind of K4_SOURCE_ROOT (decision 6)
    need(text(source,JOURNAL_TARGET_PATTERN) and source not in JOURNAL_TARGETS_TAKEN and source!=values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR'],'PINS_SOURCE_DIR')
    journal=values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR']
    need(text(journal,JOURNAL_TARGET_PATTERN) and journal not in JOURNAL_TARGETS_TAKEN,'PINS_JOURNAL_DIR')
    need(values['C3PO_R2D2_V2_CAPACITY_CONFIG_FILE']==CONTAINER_CAPACITY_ROOT+'/config/'+STATIC_CONFIG_NAME,'PINS_CONFIG_FILE')
    digests=(values['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'],values['C3PO_READER_LAUNCHER_SHA256'])
    need(all(hexpin(value) for value in digests),'PINS_HASH_INVALID')
    need(len(set(digests+(K4_RELEASE_SHA,)))==3,'PINS_HASH_REUSED')
    return ''.join(name+'='+values[name]+'\n' for name in PINS_NAMES).encode('ascii')

def delivery_of(plan):
    """The mode and its delivery member, judged from the bytes. Returns (mode, delivery, files) where files lists, in
    creation order, (key, path, bytes) of every file the run will create."""
    mode=plan['mode'];need(type(mode) is str and mode in K4_MODES,'MODE_INVALID')
    item=plan['delivery'];need(type(item) is dict and set(item)==set(K4_DELIVERY_KEYS[mode]),'DELIVERY_INVALID')
    if mode=='CHAIN_STATIC':
        documents=private_chain(item['documents_parent'],DOCUMENTS_DIRECTORY);config=private_chain(item['config_parent'],CAPACITY_CONFIG_DIRECTORY)
        need(documents[:-1]==config[:-1],'CAPACITY_CHAIN_DIVERGES')
        raw=signed_bytes(item['static_config'],MAX_STATIC_CONFIG_BYTES,'STATIC_CONFIG_BYTES_NOT_THE_SIGNED_HASH');static_config_of(raw)
        files=[('CHAIN_'+label,DOCUMENTS_DIRECTORY+'/'+name,chain_document_bytes(index)) for index,(label,name,_,_,_) in enumerate(K4_CHAIN_DOCUMENTS)]
        return mode,item,files+[('STATIC_CONFIG',CAPACITY_CONFIG_DIRECTORY+'/'+STATIC_CONFIG_NAME,raw)]
    if mode=='PINS':
        private_chain(item['reader_parent'],READER_CONFIG_DIRECTORY);private_chain(item['config_parent'],CAPACITY_CONFIG_DIRECTORY)
        private_chain(item['source_chain'],K4_SOURCE_ROOT);private_chain(item['journal_chain'],K4_JOURNAL_HOST)
        validate_chain(item['unit_parent'],UNIT_DIRECTORY,open_root=None)
        need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in item['unit_parent']),'CHAIN_NOT_ROOT_CONTROLLED')
        raw=pins_lines(item['values'])
        need(hexpin(item['sha256']) and integer(item['bytes'],1,4096) and item['sha256']==sha(raw) and item['bytes']==len(raw),'PINS_BYTES_NOT_THE_SIGNED_HASH')
        need(hexpin(item['producer_unit_sha256']) and hexpin(item['reader_unit_sha256'])
             and item['producer_unit_sha256']!=item['reader_unit_sha256'],'UNIT_HASH_INVALID')
        return mode,item,[('PINS_ENV',READER_CONFIG_DIRECTORY+'/'+PINS_NAME,raw)]
    if mode=='WRITER':
        private_chain(item['config_parent'],CAPACITY_CONFIG_DIRECTORY)
        need(item['writer_sha256']==K4_WRITER[0],'WRITER_NOT_THE_COMPILED_HASH')
        return mode,item,[('WRITER',CAPACITY_CONFIG_DIRECTORY+'/'+WRITER_STEM+K4_WRITER[0]+WRITER_EXTENSION,writer_bytes())]
    private_chain(item['reader_parent'],READER_CONFIG_DIRECTORY)
    raw=signed_bytes(item['launcher'],MAX_LAUNCHER_BYTES,'LAUNCHER_BYTES_NOT_THE_SIGNED_HASH')
    return mode,item,[('LAUNCHER',LAUNCHER_DIRECTORY+'/'+LAUNCHER_NAME,raw)]

def validate_plan(plan):
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    delivery_of(plan)

def file_effect(path,raw):
    return {'path':path,'sha256':sha(raw),'bytes':len(raw),'mode_octal':'%04o'%PRIVATE_FILE_MODE,'uid':0,'gid':0,'links':1,'expect':'ABSENT'}

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    mode,item,files=delivery_of(plan)
    out={'operation':OPERATION,'epoch':K4_EPOCH,'mode':mode,'files':[dict(file_effect(path,raw),key=key) for key,path,raw in files],
         'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'pre_existing_objects_modified':False,'secret_written':False,
         'activation':False,'container_touched':False,'process_started':False}
    if mode=='CHAIN_STATIC':
        out.update(documents_parent=chain_effects(item['documents_parent']),config_parent=chain_effects(item['config_parent']),directories=[],
                   static_config={'release_sha':K4_RELEASE_SHA,'package_sha':K4_PACKAGE_SHA,'chain_pins':'EQUAL_TO_THE_SEVEN_DELIVERED_DOCUMENTS'})
    elif mode=='PINS':
        values=item['values']
        out.update(reader_parent=chain_effects(item['reader_parent']),config_parent=chain_effects(item['config_parent']),
                   unit_parent=chain_effects(item['unit_parent']),directories=[],values=dict(values),
                   required_on_the_host={'static_config':{'path':CAPACITY_CONFIG_DIRECTORY+'/'+STATIC_CONFIG_NAME,
                                                          'sha256':values['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA']},
                                         'launcher':{'path':LAUNCHER_DIRECTORY+'/'+LAUNCHER_NAME,'sha256':values['C3PO_READER_LAUNCHER_SHA256']},
                                         'producer_unit':{'path':UNIT_DIRECTORY+'/'+PRODUCER_UNIT_NAME,'sha256':item['producer_unit_sha256']},
                                         'reader_unit':{'path':UNIT_DIRECTORY+'/'+READER_UNIT_NAME,'sha256':item['reader_unit_sha256']},
                                         'journal_bind':'SAME_SOURCE_IN_BOTH_UNITS_TARGET_'+values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR'],
                                         'bind_sources':{'source_root':chain_effects(item['source_chain']),'journal':chain_effects(item['journal_chain']),
                                                         'reader_binds_source_root_at':values['C3PO_R2D2_V2_SHADOW_SOURCE_DIR']}})
    elif mode=='WRITER':
        out.update(config_parent=chain_effects(item['config_parent']),directories=[],
                   writer={'path_in_containers':CONTAINER_CAPACITY_ROOT+'/config/'+WRITER_STEM+K4_WRITER[0]+WRITER_EXTENSION,'compiled':True})
    else:
        out.update(reader_parent=chain_effects(item['reader_parent']),
                   directories=[{'path':LAUNCHER_DIRECTORY,'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'uid':0,'gid':0,'expect':'ABSENT','entries_after':1}])
    return out
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- on the host
def entry_named(host,name,parent,gate):
    """One lstat of a plain name in the held, pinned parent; no link is followed. None when the name does not exist."""
    gate()
    try:info=host.lstat(name,parent.fd)
    except FileNotFoundError:return None
    return {'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink,
            'device':info.st_dev,'inode':info.st_ino}

def private_child(host,name,parent,gate,code):
    """An existing private directory (root:root 0700, not a link) opened by the held parent and held: the descriptor
    must be the object the lstat saw. Returns the Pinned child."""
    found=entry_named(host,name,parent,gate)
    need(found is not None,code+'_ABSENT')
    need(found['type']=='dir' and (found['uid'],found['gid'],found['mode_octal'])==(0,0,'%04o'%PRIVATE_DIRECTORY_MODE),code+'_INVALID')
    gate()
    try:fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
    except OSError:raise Refused(code+'_CHANGED_DURING_PRECHECK') from None
    try:held=Pinned(host,fd,parent=parent,name=name)
    except BaseException:
        host.close(fd);raise
    if held.identity[:2]!=(found['device'],found['inode']) or held.identity[2:]!=(0,0,PRIVATE_DIRECTORY_MODE):
        held.close();raise Refused(code+'_CHANGED_DURING_PRECHECK')
    return held

def signed_file_on_host(host,name,parent,gate,digest,mode,limit,code):
    """An existing file read through the held parent without following a link: regular, root:root, the mode, one
    link, its bytes hashing to the signed value. Returns (bytes, fstat); the bytes stay in memory, the receipt gets
    booleans; the fstat is kept to prove after the effects that the file did not change (stat_signature)."""
    try:raw,info=read_regular(host,name,parent.fd,gate,limit)
    except FileNotFoundError:raise Refused(code+'_ABSENT') from None
    except Refused as error:
        raise Refused(str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED') else code+'_METADATA') from None
    need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,mode,1),code+'_METADATA')
    need(sha(raw)==digest,code+'_NOT_THE_SIGNED_BYTES')
    return raw,info

def found_equal(host,key,path,raw,parent,gate,code):
    """A target name, looked at through the held parent: None when it is absent; a ledger row PRESENT_EQUAL when it is
    a regular file, root:root 0600, one link, holding exactly the bytes this run would write (an earlier run of the same
    signed bytes delivered it); anything else is the refusal `code`. Nothing that exists is ever replaced."""
    name=PurePosixPath(path).name
    if entry_named(host,name,parent,gate) is None:return None
    try:found,info=read_regular(host,name,parent.fd,gate,MAX_FILE_BYTES)
    except Refused as error:
        raise Refused(str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED') else code) from None
    except OSError:raise Refused(code) from None
    need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,PRIVATE_FILE_MODE,1)
         and found==raw,code)
    return {'key':key,'path':path,'state':'PRESENT_EQUAL','code':None,'errno':None,'bytes':len(found),'sha256_signed':sha(raw),'sha256_observed':None,
            'mode_octal':'%04o'%PRIVATE_FILE_MODE,'uid':0,'gid':0,'links':1,'device':info.st_dev,'inode':info.st_ino}

def bind_source(unit,target,suffix):
    """The source of the one --mount line of a unit text whose target is `target` followed by `suffix`, or None."""
    found=re.findall(r'(?m)^  --mount type=bind,source=(/[A-Za-z0-9._/-]+),target='+re.escape(target)+re.escape(suffix)+r' \\$',unit)
    return found[0] if len(found)==1 else None

def journal_and_mounts(producer,reader,values,capacity_root):
    """The README's PINS guards on the two installed unit texts: the journal target of pins.env is the producer's
    container journal root (its --journal-root and the target of its journal bind) and the target of the reader's
    read-only journal bind, both binds having the same host source; the reader binds the capacity tree and the
    launcher directory read-only where this source delivered them."""
    journal=values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR']
    produced=bind_source(producer,journal,'');read=bind_source(reader,journal,',readonly')
    need(produced is not None and read is not None and produced==read and producer.count('--journal-root ')==1
         and ('--journal-root '+journal+' ') in producer,'JOURNAL_BIND_MISMATCH')
    need(produced==K4_JOURNAL_HOST,'JOURNAL_BIND_MISMATCH')
    need(bind_source(reader,values['C3PO_R2D2_V2_SHADOW_SOURCE_DIR'],',readonly')==K4_SOURCE_ROOT
         and bind_source(reader,CONTAINER_CAPACITY_ROOT,',readonly')==capacity_root
         and bind_source(reader,CONTAINER_LAUNCHER_ROOT,',readonly')==LAUNCHER_DIRECTORY,'READER_UNIT_MOUNTS_MISMATCH')
    return produced

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_parent(receipt):receipt['parent']={key:len(value) if type(value) is list else value for key,value in (receipt.get('parent') or {}).items()}
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('PARENT_REDUCED_TO_COUNT',_reduce_parent)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    mode,item,files=delivery_of(plan)                         # pure: the bytes that will be written, and no others
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'parent':{},'precheck':{}};directories=[];ledger=[];handles={};pinned=[];held=[];entries={};present={};inputs=[]
    go16=bound['go_sha256'][:16]
    def finish(status,outcome,code,extra):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),mode=mode,
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),parent=detail['parent'],precheck=detail['precheck'],
            directories=directories,ledger=ledger,objects_left_by_this_run=objects_left(directories,ledger),
            pre_existing_objects_modified=False,**extra)))
    def walk(key,rows):
        detail['parent'][key]=[];parent=Pinned(host,walk_pinned(host,rows,gate,detail['parent'][key]),rows=rows);pinned.append(parent);return parent
    def look(index,parent,code):
        key,path,raw=files[index];row=found_equal(host,key,path,raw,parent,gate,code)
        detail['precheck'].setdefault('found',{})[PurePosixPath(path).name]='ABSENT' if row is None else 'PRESENT_EQUAL'
        if row is not None:present[index]=row
    def input_file(name,parent,digest,mode_,limit,code):
        raw,info=signed_file_on_host(host,name,parent,gate,digest,mode_,limit,code);inputs.append((name,parent,stat_signature(info)));return raw
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            if mode=='CHAIN_STATIC':
                handles['DOCUMENTS']=walk('documents',item['documents_parent']);handles['CONFIG']=walk('config',item['config_parent'])
                targets=[handles['DOCUMENTS']]*(len(files)-1)+[handles['CONFIG']]
                for index in range(len(files)-1):look(index,handles['DOCUMENTS'],'CHAIN_DOCUMENT_PRESENT')
                look(len(files)-1,handles['CONFIG'],'STATIC_CONFIG_PRESENT')
                for key in ('DOCUMENTS','CONFIG'):entries[key]=count_entries(host,handles[key].fd,gate,MAX_DIRECTORY_ENTRIES)
                detail['precheck']['entries_before']=dict(entries)
                after={'DOCUMENTS':len([index for index in range(len(files)-1) if index not in present]),'CONFIG':0 if len(files)-1 in present else 1}
            elif mode=='PINS':
                values=item['values'];reader=handles['READER']=walk('reader',item['reader_parent'])
                look(0,reader,'PINS_ENV_PRESENT')
                launcher=private_child(host,LAUNCHER_DIRECTORY_NAME,reader,gate,'LAUNCHER_DIRECTORY');held.append(launcher)
                input_file(LAUNCHER_NAME,launcher,values['C3PO_READER_LAUNCHER_SHA256'],PRIVATE_FILE_MODE,MAX_LAUNCHER_BYTES,'LAUNCHER_FILE')
                config=walk('config',item['config_parent'])
                static_config_of(input_file(STATIC_CONFIG_NAME,config,values['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'],PRIVATE_FILE_MODE,MAX_STATIC_CONFIG_BYTES,
                                            'STATIC_CONFIG_FILE'))
                walk('source_root',item['source_chain']);walk('journal',item['journal_chain'])     # decision 6: bind sources root-only, held to the end
                units=walk('units',item['unit_parent'])
                producer=input_file(PRODUCER_UNIT_NAME,units,item['producer_unit_sha256'],UNIT_FILE_MODE,MAX_UNIT_BYTES,'PRODUCER_UNIT')
                reader_unit=input_file(READER_UNIT_NAME,units,item['reader_unit_sha256'],UNIT_FILE_MODE,MAX_UNIT_BYTES,'READER_UNIT')
                try:producer,reader_unit=producer.decode('ascii'),reader_unit.decode('ascii')
                except UnicodeDecodeError:raise Refused('JOURNAL_BIND_MISMATCH') from None
                source=journal_and_mounts(producer,reader_unit,values,item['config_parent'][-2]['path'])
                detail['precheck']['read_and_equal_to_the_signed_bytes']=['LAUNCHER_FILE','STATIC_CONFIG_FILE','PRODUCER_UNIT','READER_UNIT']
                detail['precheck']['journal_bind']={'host_source':source,'container_target':values['C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR'],'same_in_both_units':True}
                targets=[reader]
            elif mode=='WRITER':
                config=handles['CONFIG']=walk('config',item['config_parent']);targets=[config]
                look(0,config,'WRITER_PRESENT')
                entries['CONFIG']=count_entries(host,config.fd,gate,MAX_DIRECTORY_ENTRIES);detail['precheck']['entries_before']=dict(entries)
                after={'CONFIG':0 if 0 in present else 1}
            else:
                reader=handles['READER']=walk('reader',item['reader_parent'])
                if entry_named(host,LAUNCHER_DIRECTORY_NAME,reader,gate) is None:detail['precheck']['launcher_directory']='ABSENT'
                else:
                    # an earlier run of these bytes made it: root:root 0700, and empty or holding exactly the signed file
                    handles['LAUNCHER_DIRECTORY']=private_child(host,LAUNCHER_DIRECTORY_NAME,reader,gate,'LAUNCHER_DIRECTORY_PRESENT')
                    look(0,handles['LAUNCHER_DIRECTORY'],'LAUNCHER_DIRECTORY_PRESENT')
                    need(count_entries(host,handles['LAUNCHER_DIRECTORY'].fd,gate,MAX_DIRECTORY_ENTRIES)==len(present),'LAUNCHER_DIRECTORY_PRESENT')
                    detail['precheck']['launcher_directory']='PRESENT_PRIVATE'
                targets=[handles.get('LAUNCHER_DIRECTORY')]
            # every filesystem that receives a file of this run (the receiving parents are pinned first)
            detail['precheck']['free_bytes']=[]
            for handle in pinned[:2 if mode=='CHAIN_STATIC' else 1]:
                free=free_bytes(host,handle.fd);detail['precheck']['free_bytes'].append(free)
                need(free>=FREE_BYTES_FLOOR,'FREE_SPACE_BELOW_FLOOR')
            # The last refusal that costs nothing on the host: the time the creations and the readback may take.
            left=gate();detail['precheck']['seconds_left_before_first_effect']=int(left)
            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','delivered':None})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None
        if mode=='LAUNCHER' and targets[0] is None:
            entry=create_directory('LAUNCHER_DIRECTORY',LAUNCHER_DIRECTORY,PRIVATE_DIRECTORY_MODE,handles['READER'],host,gate,state,handles)
            directories.append(entry)
            if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'
            targets=[handles.get('LAUNCHER_DIRECTORY')]
        for index,((key,path,raw),directory) in enumerate(zip(files,targets)):
            if index in present:
                ledger.append(present[index]);continue
            if stop is not None:
                ledger.append({'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None});continue
            row=create_file(index,key,path,raw,PRIVATE_FILE_MODE,directory,host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        # ---- the readback inside the run: every file through a descriptor (also those found equal), the directories
        # ---- that received them, the inputs of PINS unchanged since they were read, the parents walked again from "/"
        for row,(key,path,raw),directory in zip(ledger,files,targets):
            if stop is None:stop=readback_file(row,raw,PRIVATE_FILE_MODE,directory,host,gate)
        if stop is None and mode=='LAUNCHER':
            stop=readback_directory(LAUNCHER_DIRECTORY,PRIVATE_DIRECTORY_MODE,handles['LAUNCHER_DIRECTORY'],host,gate,1)
        if stop is None and mode in ('CHAIN_STATIC','WRITER'):
            for key,path in (('DOCUMENTS',DOCUMENTS_DIRECTORY),('CONFIG',CAPACITY_CONFIG_DIRECTORY)):
                if key not in entries:continue
                if stop is None:stop=readback_directory(path,PRIVATE_DIRECTORY_MODE,handles[key],host,gate,entries[key]+after[key])
        for name,parent,signature in inputs:
            if stop is None:
                try:
                    gate();need(stat_signature(host.lstat(name,parent.fd))==signature,'PINS_INPUT_CHANGED')
                except Exception as error:stop=code_of(error,'PINS_INPUT_CHANGED')
        for handle in held+pinned:
            if stop is None:
                try:handle.verify(gate)
                except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        delivered=None
        if stop is None:
            delivered={'mode':mode,'epoch':K4_EPOCH,
                       'files':[{'key':row['key'],'path':row['path'],'sha256':row['sha256_observed'],'bytes':row['bytes'],'mode_octal':row['mode_octal'],
                                 'uid':row['uid'],'gid':row['gid'],'links':row['links'],'bytes_equal_the_signed_bytes':True,
                                 'created_by_this_run':row['state']!='PRESENT_EQUAL'} for row in ledger],
                       'directories':[{'path':entry['path'],'mode_octal':entry['observed']['mode_octal'],'uid':entry['observed']['uid'],
                                       'gid':entry['observed']['gid'],'entries':1} for entry in directories]}
            if mode in ('CHAIN_STATIC','WRITER'):delivered['entries_after']={key:entries[key]+after[key] for key in entries}
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None,'delivered':delivered}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for key,handle in list(handles.items()):
            if key not in ('DOCUMENTS','CONFIG','READER'):
                try:handle.close()
                except Exception:pass
        for handle in held+pinned:
            try:handle.close()
            except Exception:pass
# ==== END OP_K4_FILES ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
