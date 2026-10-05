"""OP_K9_PHASE_STEP (K9W): the write program of the delegated daily phases of epoch R2D2-V2-SHADOW-2026-10-05.

One signed step of the closed step table per run. Everything is looked at first, read-only: the executor, the window of
D, the boot of the evidence, the signed chains of the K9 tree and of the source root from "/", the absence of this
attempt's claim, the day directory, the K9 containers the engine lists, the exited container of the previous step named
by its launch record (inspected by ID: name, image, labels, state), every input of the step by fixed path (the
predecessors' receipts, the destinations, the environment files by lstat only, the runner file, the space floor), the
signed image, and the time left. Then: the claim file by exclusive creation; the removal of the previous step's exited
container (docker rm of its ID, no -f, no -v); for collect_launch the day directories; the step plan; and one container
of the signed image ID: LAUNCH creates it (no --rm, its own timeout -s KILL limit) and starts it after every mounted
directory has been proved again, then writes the launch record; ATTACHED runs it with --rm and reads its receipt back;
CLEANUP only removes. When an input is not complete the run removes the previous exited container and refuses
(removal-only). It never reads a secret (the docker CLI reads the environment files), never stops, kills or execs into
a container, never pulls, never overwrites, renames or removes a file. The caller authenticates exact
request/authority/GO/source bytes first.
No action on import.
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

# ==== BEGIN OP_K9_PHASE_STEP (this operation only) ====
OPERATION='GO_WRITE_HOSTOPS02_K9_PHASE_STEP_01'
PHASE='WRITE_K9_PHASE_STEP'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K9_PHASE_STEP_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K9_PHASE_STEP_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K9_PHASE_STEP_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K9_PHASE_STEP_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K9_PHASE_STEP_PLAN_V1'
SOURCE_NAME='k9_phase_step.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The rows and the boot every request signs come from a TREE receipt of the read program (K9R) of the same boot.
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_K9_PHASE_READ_01',)
MAX_GATE_SPAN_SECONDS=900
# Exit 0 exists for one outcome per mode of the signed operation (the mode follows the operation, section 2 of DESIGN.md).
COMPLETE_OUTCOME='K9_STEP_LAUNCHED_DETACHED_READ_BACK'
K9W_ATTACHED_OUTCOME='K9_STEP_RAN_ATTACHED_RECEIPT_COMPLETE'
K9W_CLEANUP_OUTCOME='K9_CONTAINER_REMOVED_READ_BACK'
K9W_REMOVAL_ONLY_OUTCOME='K9_REMOVAL_ONLY_PREDECESSOR_NOT_COMPLETE'
K9W_NOT_COMPLETE_OUTCOME='K9_STEP_RAN_NOT_COMPLETE'
PARTIAL_OUTCOME='K9_STEP_PARTIAL_REQUIRES_REVIEW'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='K9_STEP_PARTIAL_REQUIRES_REVIEW'
ESCAPED_OUTCOME='K9_STEP_ESCAPED_STATE_UNKNOWN'
K9W_MODES=('LAUNCH','ATTACHED','CLEANUP')
K9W_SUCCESS={'LAUNCH':COMPLETE_OUTCOME,'ATTACHED':K9W_ATTACHED_OUTCOME,'CLEANUP':K9W_CLEANUP_OUTCOME}
PLAN_KEYS=frozenset(('mode','epoch','day','k9_phase','k9_operation','slot','attempt_key','run_not_after','constants','parent_rows',
                     'evidence_boot_id_sha256','bind'))

# ---------------------------------------------------------------- the epoch and the frozen interface (the same values as K9R)
K9W_EPOCH='R2D2-V2-SHADOW-2026-10-05'
K9W_DAYS=('2026-10-06','2026-10-07','2026-10-08','2026-10-09')        # Monday 05/10 has no K9 list (K9_INTERFACE_NOTE.md 5.5)
K9W_NOTE_SHA256='ab5159bea34b3239379e87c2500d383f0777cc6186618435ba0ea9f61e3d596c'        # K9_INTERFACE_NOTE.md rev 2
K9W_OPERATIONS_SHA256='bc796cb7d6d8ab29e314ad29c726f33f16f3b83dfcede7771ec2b2cdae0e7d08'  # K9_OPERATIONS.json beside it
K9W_PACKAGE_SHA256='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
K9W_CODE_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
K9W_SLOTS=('PRIMARY','SPARE')
# The reviewed runner (W/fable-k9runner-20261004/k9_runner.py rev 2, 40,618 bytes): the ONE place its hash is written.
# A new runner is a new value here, a new payload hash and a new review. TREE hashes the delivered file's bytes.
K9W_RUNNER_SHA256='563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690'
K9W_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
# Revision 2, Codex's decision 6 (#429 comment 5985748037): the source root moves off the data volume (whose root is
# uid 1000's) to /var/lib/c3po, under the same root-only chain as the K9 tree and on the filesystem of days/; no open
# root anywhere. Every bind source and every one of its ancestors is root-controlled, so no other account can swap a
# directory a container binds. The rest is Codex's N-8 decision of 2026-10-04 (W/codex-n8-placement-20261004.txt).
K9W_SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
K9W_PLACEMENT={'k9_root':K9W_ROOT,'source_root':K9W_SOURCE_ROOT,'days':K9W_ROOT+'/days','tools':K9W_ROOT+'/tools','claims':K9W_ROOT+'/claims',
               'secrets':K9W_ROOT+'/secrets','emitter':K9W_ROOT+'/secrets/emitter','provider_env_file':K9W_ROOT+'/secrets/provider.env',
               'risk_db_env_file':K9W_ROOT+'/secrets/risk-db.env','emitter_password':K9W_ROOT+'/secrets/emitter/password',
               'source_open_root':None,'k9_open_root':None,'decision':'d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53',
               'decision_6':'#429 comment 5985748037','september_open_root':'/mnt/day-d-data'}
# (K9R rev 4's object, byte for byte. september_open_root names the data volume only for K3-K9's read of the September
# secret files; no chain of this source has an open root.)
K9W_PARENT_CHAINS=('days','source_root','secrets','tools','claims')
K9W_RECEIVES_ENTRY=('days','source_root','claims')
# Codex (#429): 200 GiB available, f_bavail * f_frsize of fstatvfs on the open descriptor of days/; below it: HOLD (a refusal here).
K9W_DISK_FLOOR_BYTES=214748364800
K9W_RISK_LIMITS={'max_symbols':550,'max_total_requests':2200,'max_body_bytes':16777216,'max_total_bytes':1073741824,'max_elapsed_seconds':3600}
K9W_PROVIDER_NETWORK='bridge'
K9W_NETWORK_CLASSES=('PROVIDER','DATABASE','DATABASE_AND_PROVIDER')
K9W_CONSTANT_KEYS=frozenset(('k9_interface_note_sha256','act_b_sha256','package_sha256','code_revision','release_sha256','policy_sha256','image_id',
                             'runner_sha256','probe_snippet_sha256','networks','step_table_sha256','risk_source_pins_sha256','risk_limits',
                             'readiness_rule','disk_floor_bytes','placement'))
K9W_PRIVATE_DIRECTORY_MODE=0o700
K9W_PRIVATE_FILE_MODE=0o600

# ---------------------------------------------------------------- limits and grammar
K9W_MAX_SMALL_FILE=262144                # launch records, start markers, step receipts, step plans
K9W_MAX_PLAN_FILE=16777216               # HOST_PLAN.json and GO.json of the packaged risk plan, the packaged receipts
K9W_MAX_SYMBOLS_FILE=1048576             # control/symbols.txt
K9W_MAX_OUTPUTS=64
K9W_MAX_AGGREGATES=8
K9W_MAX_AGGREGATE_ENTRIES=4096
K9W_MAX_COUNT=10000000
K9W_MAX_LIMIT=1<<40
K9W_ENTRY='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
K9W_OUTPUT_KEY=r'(day|source)(/[A-Za-z0-9][A-Za-z0-9._=-]{0,127}){1,8}'
K9W_NETWORK_NAME='[A-Za-z0-9][A-Za-z0-9_.-]{0,63}'
K9W_COUNT_KEY='[a-z][a-z0-9]{0,30}(_[a-z0-9]{1,30}){1,4}'      # a runner's counts: constant snake names with an underscore, never a ticker (K9R rev 3)
K9W_MAX_COUNTS=64
K9W_ORDER_SCHEMA='R2D2_V2_RISK_HOST_ORDER_V1'
K9W_ORDER_ACTIONS=['READ_PROVIDERS','READ_DATABASE','WRITE_PRIVATE_RISK_ARTIFACTS']
K9W_RISK_PHASES=['preflight','acquire','execute']
K9W_RISK_NAMESPACE='R2D2-V2-DIAG-R4-'        # + D (Codex's answer to N-1: the label is private to the risk spool)
K9W_MIN_TIMEOUT_SECONDS=90             # > the runner's own stop, 60 s before run_not_after (runner MARGIN)
K9W_LAUNCH_MARGIN_SECONDS=5              # a LAUNCH container's own limit ends 5 s before run_not_after
K9W_CEILING_SLACK_SECONDS=900            # and never more than its ceiling + the longest write window after its creation
K9W_FILES_ALLOWANCE_SECONDS=4            # the files written between the first and the last effect (claim, plan, directories)
K9W_EXPIRED=('GO_EXPIRED','CLOCK_REVERSED')
# Needs that are a state of the host, not of the chain: a refusal (HOLD), never removal-only, so that the attempt key is
# not spent and the same request can run once the condition is gone (Codex: HOLD below the floor).
K9W_HOLD_CODES=('DISK_FREE_BELOW_FLOOR','ENV_FILE_NOT_PRIVATE','EMITTER_SECRET_NOT_PRIVATE','RUNNER_FILE_NOT_AS_REQUIRED')

# ---------------------------------------------------------------- the files the read program (K9R) and the runner share with this one
K9W_RECORD_SCHEMA='K9_LAUNCH_RECORD_V1'
K9W_RECORD_KEYS=frozenset(('schema','epoch','day','operation','slot','attempt_key','request_sha256','step_plan_sha256','container_id',
                           'container_name','created_at','started_at','timeout_seconds'))
K9W_STARTED_SCHEMA='K9_STEP_STARTED_V1'
K9W_STARTED_KEYS=frozenset(('schema','epoch','day','phase','operation','attempt_key','step_plan_sha256','started_at'))
K9W_STEP_SCHEMA='K9_STEP_RECEIPT_V1'
K9W_STEP_KEYS=frozenset(('schema','status','code','epoch','day','phase','operation','attempt_key','step_plan_sha256','started_at','completed_at',
                         'package_sha256','build_sha','outputs','aggregates','counts'))
K9W_STEP_FAILED_STATUSES=('REFUSED','FAILED','DEADLINE')
K9W_PACKAGED_RECEIPT_SCHEMA='R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1'
K9W_PACKAGED_RECEIPT_KEYS=frozenset(('schema','phase','status','manifest_sha256','go_sha256','namespace','session_date','started_at','completed_at',
                                     'previous_receipt_sha256','outputs','operation_activation','certification_granted'))
K9W_PACKAGED_STARTED_KEYS=frozenset(('phase','manifest_sha256','go_sha256','started_at'))
K9W_PACKAGED_FAILED_SCHEMA='R2D2_V2_RISK_HOST_FAILED_V1'
K9W_PLAN_STEP_SCHEMA='K9_STEP_PLAN_V1'
K9W_CLAIM_KEYS=('epoch','day','phase','operation','slot','request_sha256')
K9W_CONTAINER_PREFIX='c3po-k9-'
K9W_LABEL_ATTEMPT='c3po.k9.attempt_key'
K9W_LABEL_REQUEST='c3po.k9.request_sha256'

# ---------------------------------------------------------------- the closed step table (K9_INTERFACE_NOTE.md 3.1-3.3), compiled
# Inside every K9 container: the tools directory, the day directory, the source root and the emitter secret directory
# at fixed targets. Hosts paths are derived from the placement and from D, never from a request.
K9W_TARGETS={'TOOLS':'/c3po-k9-tools','DAY':'/c3po-k9-day','SOURCE':'/c3po-source','EMITTER':'/c3po-k9-emitter'}
K9W_MOUNTS={'TOOLS':{'host':'tools','target':K9W_TARGETS['TOOLS'],'read_only':True},
            'DAY':{'host':'day','target':K9W_TARGETS['DAY'],'read_only':False},
            'DAY_READ_ONLY':{'host':'day','target':K9W_TARGETS['DAY'],'read_only':True},
            'DAY_RECEIPTS':{'host':'day_receipts','target':K9W_TARGETS['DAY']+'/receipts','read_only':False},
            'SOURCE':{'host':'source_root','target':K9W_TARGETS['SOURCE'],'read_only':False},
            'EMITTER':{'host':'emitter','target':K9W_TARGETS['EMITTER'],'read_only':True}}
K9W_ENV_FILES={'PROVIDER':'provider_env_file','RISK_DATABASE':'risk_db_env_file'}
K9W_FIXED_ENV=['C3PO_R2D2_V2_PRODUCERS_ENABLED=true','C3PO_BUILD_SHA='+K9W_CODE_REVISION]
K9W_DAY_DIRECTORIES=('plans','launches','receipts')
K9W_HOST_PLAN=['risk','plan','HOST_PLAN.json']
K9W_HOST_GO=['risk','plan','GO.json']
def k9w_row(phase,mode,row,network,mounts,env_files,command,ceiling,timeout,needs,removes,absent=(),present=(),symbols=False,emitter=False,
            creates_day=False,packaged_phase=None,latest=None,window_class='BEFORE_OPEN'):
    return {'phase':phase,'mode':mode,'row':row,'network':network,'mounts':list(mounts),'env_files':list(env_files),'command':command,
            'ceiling_seconds':ceiling,'timeout_seconds':timeout,'needs':[list(item) for item in needs],'removes':removes,
            'destinations_absent':[list(item) for item in absent],'destinations_present':[list(item) for item in present],
            'symbols_equal_publish_receipt':symbols,'emitter_password':emitter,'creates_day_directory':creates_day,
            'packaged_phase':packaged_phase,'latest_run_not_after_utc_of_d':latest,'window_class':window_class}
K9W_STEPS={
    'collect_launch':k9w_row('causal_list','LAUNCH','create','PROVIDER',['TOOLS','DAY'],['PROVIDER'],'RUNNER',900,None,[],None,
                             absent=[('days','<D>')],creates_day=True),
    'commit_launch':k9w_row('causal_list','LAUNCH','create','DATABASE',['TOOLS','DAY','EMITTER'],[],'RUNNER',600,None,
                            [('RUNNER','collect_launch')],'collect_launch',absent=[('day','causal')],emitter=True,latest='03:50:00'),
    'publish_launch':k9w_row('causal_list','LAUNCH','create','DATABASE',['TOOLS','DAY','SOURCE','EMITTER'],[],'RUNNER',600,None,
                             [('RUNNER','commit_launch')],'commit_launch',absent=[('day','relay'),('day','control')],emitter=True),
    'components_launch':k9w_row('components','LAUNCH','create','PROVIDER',['TOOLS','DAY','SOURCE'],['PROVIDER'],'RUNNER',2400,None,
                                [('RUNNER','publish_launch')],'publish_launch',absent=[('source','components','<D>')],symbols=True),
    'sources_launch':k9w_row('sources','LAUNCH','create','DATABASE_AND_PROVIDER',['TOOLS','DAY'],['PROVIDER','RISK_DATABASE'],'RUNNER',4500,None,
                             [('RUNNER','publish_launch')],'components_launch',absent=[('day','risk')],symbols=True),
    'bind':k9w_row('risk','ATTACHED','attached','NONE',['TOOLS','DAY'],[],'RUNNER',None,35,[('RUNNER','sources_launch'),('RUNNER','publish_launch')],None,
                   absent=[('day','risk','plan','OWNER_ORDER.json'),('day','risk','plan','SOURCE_PINS.json'),('day','risk','plan','list.private.json'),
                           ('day','risk','plan','HOST_PLAN.json'),('day','risk','plan','GO.json'),('day','risk','spool')],present=[('day','risk','plan')]),
    'preflight':k9w_row('risk','ATTACHED','attached','NONE',['DAY'],[],'PACKAGED',None,35,[('RUNNER','bind')],None,
                        present=[('day','risk','spool')],packaged_phase='preflight'),
    'acquire_launch':k9w_row('risk','LAUNCH','create','DATABASE_AND_PROVIDER',['DAY'],['PROVIDER','RISK_DATABASE'],'PACKAGED',3600,None,
                             [('PACKAGED','preflight')],'sources_launch',packaged_phase='acquire'),
    'execute_launch':k9w_row('risk','LAUNCH','create','NONE',['DAY'],[],'PACKAGED',1200,None,[('PACKAGED','acquire')],'acquire_launch',
                             packaged_phase='execute'),
    'stage':k9w_row('risk','ATTACHED','attached_short','NONE',['TOOLS','DAY_READ_ONLY','DAY_RECEIPTS','SOURCE'],[],'RUNNER',None,18,
                    [('PACKAGED','execute')],'execute_launch',absent=[('source','components','<D>','risk.json')],present=[('source','components','<D>')]),
    'capture_launch':k9w_row('capture','LAUNCH','create','PROVIDER',['TOOLS','DAY','SOURCE'],['PROVIDER'],'RUNNER',780,None,
                             [('RUNNER','publish_launch')],None,window_class='IN_SESSION'),
    'capture_cleanup':k9w_row('capture','CLEANUP',None,None,[],[],None,None,None,[],'capture_launch',window_class='IN_SESSION')}
# run_not_after of the capture launch: 11:03:00 BRT of D (K9_INTERFACE_NOTE.md 4.2, 5.5)
K9W_CAPTURE_RUN_NOT_AFTER='14:03:00'
K9W_STEP_TABLE={'steps':K9W_STEPS,'mounts':K9W_MOUNTS,'env_files':K9W_ENV_FILES,'fixed_env':K9W_FIXED_ENV,'day_directories':list(K9W_DAY_DIRECTORIES),
                'capture_run_not_after_utc_of_d':K9W_CAPTURE_RUN_NOT_AFTER,'risk_namespace_prefix':K9W_RISK_NAMESPACE,
                'launch_timeout':{'margin_seconds':K9W_LAUNCH_MARGIN_SECONDS,'ceiling_slack_seconds':K9W_CEILING_SLACK_SECONDS,
                                  'minimum_seconds':K9W_MIN_TIMEOUT_SECONDS}}
K9W_STEP_TABLE_SHA256=sha(canonical(K9W_STEP_TABLE))
K9W_PHASE_OF={name:row['phase'] for name,row in K9W_STEPS.items()}
K9W_PACKAGED_LAUNCH={'acquire':'acquire_launch','execute':'execute_launch','preflight':'preflight'}

# ---------------------------------------------------------------- the commands
# The format of the read of one K9 container by ID: K9R's K9_LAUNCHED_FORMAT byte for byte. Never the environment.
K9W_LAUNCHED_FORMAT=('{"name":{{json .Name}},"id":{{json .Id}},"image_id":{{json .Image}},"state":{{json .State.Status}},'
                     '"running":{{json .State.Running}},"exit_code":{{json .State.ExitCode}},"oom_killed":{{json .State.OOMKilled}},'
                     '"started_at":{{json .State.StartedAt}},"finished_at":{{json .State.FinishedAt}},'
                     '"attempt_key":{{json (index .Config.Labels "c3po.k9.attempt_key")}},'
                     '"request_sha256":{{json (index .Config.Labels "c3po.k9.request_sha256")}}}')
K9W_LAUNCHED_KEYS=frozenset(('name','id','image_id','state','running','exit_code','oom_killed','started_at','finished_at','attempt_key','request_sha256'))
# A detached K9 container (K9_INTERFACE_NOTE.md 3.1): never pulled, an init, uid 0, a read-only root, no capability, no new
# privilege, never restarted, and NO --rm: the engine keeps it, exited, until a RESULT read has seen its state and exit code.
K9W_CREATE_PREFIX=['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no']
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'launched':command_row('docker',['container','inspect','--format',K9W_LAUNCHED_FORMAT],'one 64-hex container ID (a launch record\'s, or the one create printed)','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'create':command_row('docker',K9W_CREATE_PREFIX,'--name, two --label, --network, up to two --env-file, two --env, up to four --mount, the signed image ID, '
                               'then the command of the step (built by k9w_container_arguments from the compiled step table)','QUICK','EFFECT'),
          'start':command_row('docker',['start'],'exactly the 64-hex ID create printed','RUN_SHORT','EFFECT'),
          'remove':command_row('docker',['rm'],'exactly one 64-hex ID: an exited K9 container named by a launch record, labels and image checked; or the '
                               'container this run created and never started, when a mounted directory changed before start','QUICK','EFFECT'),
          'attached':command_row('docker',RUN_PREFIX,'--name, two --label, up to two --env, up to four --mount, the signed image ID, '
                                 'then the command of the step (bind, preflight)','RUN','EFFECT'),
          'attached_short':command_row('docker',RUN_PREFIX,'--name, two --label, two --env, up to four --mount, the signed image ID, '
                                       'then the command of the step (stage)','RUN_SHORT','EFFECT')}

SCOPE_STATEMENT=('Writes one delegated daily step of epoch R2D2-V2-SHADOW-2026-10-05 and nothing else. Every run first proves the K9 tree, '
                 'the source root and every input by fixed path against the signed rows, then creates its claim file by exclusive creation '
                 '(an existing claim is a refusal). LAUNCH: removes the exited K9 container of the previous step named by its launch record '
                 '(docker rm of that ID, no -f, no -v, only when it is exited and carries that step\'s labels), writes the step plan, creates '
                 'and starts one detached container of the signed image ID with its own time limit and no --rm, and writes the launch record. '
                 'ATTACHED: the same with one attached docker run --rm whose receipt is read back. CLEANUP: the removal alone. When the '
                 'inputs of a step are not complete it removes the previous exited K9 container and refuses (removal-only). It reads no '
                 'secret: the docker CLI reads the environment files. Only the outcome named as success criterion counts.')
SIDE_EFFECTS=['a claim file <k9_root>/claims/<attempt_key>.claim, root:root 0600, by exclusive creation (single use per attempt key: at most one of PRIMARY and SPARE)',
              'collect_launch only: the directories days/<D>, days/<D>/plans, days/<D>/launches, days/<D>/receipts, root:root 0700',
              'the step plan days/<D>/plans/<operation>.json and, after start, the launch record days/<D>/launches/<operation>.json, root:root 0600',
              'LAUNCH: one docker create and one docker start of a container named c3po-k9-<yyyymmdd of D>-<operation> with the labels '
              'c3po.k9.attempt_key and c3po.k9.request_sha256, which then runs on its own up to its timeout -s KILL limit and is kept, exited, by the engine',
              'ATTACHED: one docker run --rm of a container of the same name and labels, ended by its own timeout -s KILL limit',
              'one docker rm of the exited container of the previous step when the table names one and its launch record, labels and image are as written',
              'LAUNCH only: one docker rm of the container this run created, before it is ever started, when a mounted directory is no longer the one held (it never runs)',
              'the docker CLI reads the environment files of the K9 tree as root and gives their values to the container it creates; nothing of them reaches this process',
              'the containers write in days/<D> and, where the table says, in the source root: their bytes are the reviewed runner\'s and the packaged executor\'s, not this source\'s']
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'modes':dict(K9W_SUCCESS),'epoch':K9W_EPOCH,'days':list(K9W_DAYS),'interface_note_sha256':K9W_NOTE_SHA256,
       'operations_sha256':K9W_OPERATIONS_SHA256,'placement':K9W_PLACEMENT,'parent_chains':list(K9W_PARENT_CHAINS),
       'step_table':K9W_STEP_TABLE,'step_table_sha256':K9W_STEP_TABLE_SHA256,'disk_floor_bytes':K9W_DISK_FLOOR_BYTES,
       'contracts':{'launch_record':[K9W_RECORD_SCHEMA,sorted(K9W_RECORD_KEYS)],'start_marker':[K9W_STARTED_SCHEMA,sorted(K9W_STARTED_KEYS)],
                    'step_receipt':[K9W_STEP_SCHEMA,sorted(K9W_STEP_KEYS)],'packaged_receipt':[K9W_PACKAGED_RECEIPT_SCHEMA,sorted(K9W_PACKAGED_RECEIPT_KEYS)],
                    'step_plan':K9W_PLAN_STEP_SCHEMA,'claim':list(K9W_CLAIM_KEYS),'labels':[K9W_LABEL_ATTEMPT,K9W_LABEL_REQUEST]},
       'files':FILES_SCOPE,'side_effects':SIDE_EFFECTS,
       'never':['docker rm -f','docker rm -v','a removal of a container that is not exited, not named by a launch record of this day, or whose labels or image differ '
                '(except the container this run created and never started, withdrawn when a mount source moved)',
                'docker exec','docker kill','docker stop','a pull','a privileged container','a socket or device in a container','a bind other than the four of the table',
                'a shell','a systemctl verb','an overwrite, chmod, chown, rename or removal of a file','a read of a secret file',
                'a value of an environment, a byte or digest of a secret, a symbol of an instrument in the receipt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'small_file_bytes':K9W_MAX_SMALL_FILE,'plan_file_bytes':K9W_MAX_PLAN_FILE,'symbols_file_bytes':K9W_MAX_SYMBOLS_FILE,
                 'max_arguments':MAX_ARGUMENTS,'files_allowance_seconds':K9W_FILES_ALLOWANCE_SECONDS,
                 'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the signed commands and the creating calls of files."""


# ---------------------------------------------------------------- the signed plan (pure)
def k9w_attempt_key(epoch,day,phase,operation):
    """The Act B single-use key: sha256 of the canonical list [epoch, day, phase, operation] (actb03_lib.attempt_key)."""
    return sha(canonical([epoch,day,phase,operation]))

def k9w_day_shift(day,count):
    return datetime.fromordinal(datetime.fromisoformat(day).toordinal()+count).date().isoformat()

def k9w_at(day,clock_text):
    return instant(day+'T'+clock_text+'+00:00')

def k9w_after(point,seconds):
    """point + seconds as a UTC instant (the core imports no timedelta)."""
    return datetime.fromtimestamp(point.timestamp()+seconds,timezone.utc)

def k9w_container_name(day,operation):
    return K9W_CONTAINER_PREFIX+day.replace('-','')+'-'+operation

def k9w_chain(item,path,open_root,receives_entry,code):
    """One signed chain: the core's rule with no open root (every component uid 0, not writable by group or other), and
    (as K4-E0) gid 0 and no setgid bit on every component, and a leaf that is root's private directory (0:0 0700), as E0
    creates every K9 directory and the source root. open_root is always None (decision 6); it stays a member of the
    signed chain object so that the object is K9R's."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and item['path']==path and item['open_root']==open_root and item['rows'] is not None,code)
    rows=validate_chain(item['rows'],path,open_root,receives_entry)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_ROW_GROUP_OR_SETGID')
    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,K9W_PRIVATE_DIRECTORY_MODE),'CHAIN_LEAF_NOT_ROOT_PRIVATE')
    return item

def k9w_instant_text(value,code):
    """An instant written exactly as datetime.isoformat() writes it in UTC."""
    try:point=instant(value)
    except Refused:raise Refused(code) from None
    need(point.isoformat()==value,code)
    return point

def k9w_constants(plan):
    """The week's constants: the same object K9R signs. Compared with the compiled values where this source has them."""
    values=plan['constants']
    need(type(values) is dict and set(values)==K9W_CONSTANT_KEYS,'CONSTANTS_INVALID')
    need(values['k9_interface_note_sha256']==K9W_NOTE_SHA256 and values['package_sha256']==K9W_PACKAGE_SHA256
         and values['code_revision']==K9W_CODE_REVISION,'CONSTANTS_NOT_THE_COMPILED_ONES')
    need(values['placement']==K9W_PLACEMENT,'PLACEMENT_NOT_THE_COMPILED_ONE')
    need(all(hexpin(values[key]) for key in ('act_b_sha256','release_sha256','policy_sha256','runner_sha256','probe_snippet_sha256','step_table_sha256',
                                             'risk_source_pins_sha256')) and text(values['image_id'],IMAGE_ID),'CONSTANTS_INVALID')
    need(values['step_table_sha256']==K9W_STEP_TABLE_SHA256,'STEP_TABLE_NOT_THE_COMPILED_ONE')
    need(values['runner_sha256']==K9W_RUNNER_SHA256,'RUNNER_NOT_THE_COMPILED_ONE')
    networks=values['networks']
    need(type(networks) is dict and set(networks)==set(K9W_NETWORK_CLASSES) and all(text(value,K9W_NETWORK_NAME) for value in networks.values()),'CONSTANTS_INVALID')
    need(networks['PROVIDER']==K9W_PROVIDER_NETWORK and 'none' not in networks.values() and 'host' not in networks.values(),'NETWORKS_NOT_THE_COMPILED_ONES')
    need(canonical(values['risk_limits'])==canonical(K9W_RISK_LIMITS),'RISK_LIMITS_NOT_THE_COMPILED_ONES')
    # K9R's to judge (it compiles the rule and the snippet); here the grammar only, so that one object serves both programs
    rule=values['readiness_rule']
    need(type(rule) is dict and 0<len(rule)<=8 and all(text(key,'[a-z][a-z0-9_]{0,63}') and integer(value,0,K9W_MAX_COUNT) for key,value in rule.items()),'CONSTANTS_INVALID')
    need(integer(values['disk_floor_bytes'],0,K9W_MAX_LIMIT) and values['disk_floor_bytes']==K9W_DISK_FLOOR_BYTES,'DISK_FLOOR_NOT_THE_COMPILED_ONE')
    return values

def k9w_owner_order(day,cutoff_at):
    """The packaged executor's owner order for D (risk_host_executor.py:163-166): its exact canonical bytes."""
    return canonical({'schema':K9W_ORDER_SCHEMA,'actions':list(K9W_ORDER_ACTIONS),
                      'scope':{'namespace':K9W_RISK_NAMESPACE+day,'session_date':day,'cutoff_at':cutoff_at,'phases':list(K9W_RISK_PHASES)}})

def k9w_bind(plan):
    """bind only: the risk documents' signed values. The cutoff and the phase windows are grid instants of D; the owner
    order is the canonical bytes those values determine, carried as ASCII text with their hash for the signer's sheet
    (the runner's RISK_KEYS: namespace, cutoff_at, phase_windows, owner_order_text, owner_order_sha256)."""
    value=plan['bind'];day=plan['day']
    need(type(value) is dict and set(value)=={'namespace','cutoff_at','phase_windows','owner_order_text','owner_order_sha256'},'BIND_INVALID')
    need(value['namespace']==K9W_RISK_NAMESPACE+day,'BIND_NAMESPACE_NOT_THE_COMPILED_ONE')
    cutoff=k9w_instant_text(value['cutoff_at'],'BIND_INVALID')
    windows=value['phase_windows']
    need(type(windows) is dict and set(windows)==set(K9W_RISK_PHASES),'BIND_INVALID')
    bounds={}
    for name in K9W_RISK_PHASES:
        item=windows[name];need(type(item) is dict and set(item)=={'not_before','not_after'},'BIND_INVALID')
        bounds[name]=(k9w_instant_text(item['not_before'],'BIND_INVALID'),k9w_instant_text(item['not_after'],'BIND_INVALID'))
        need(bounds[name][0]<bounds[name][1],'BIND_WINDOWS_INVALID')
    low,high=k9w_at(k9w_day_shift(day,-1),'20:00:00'),k9w_at(day,'13:30:00')
    need(low<=cutoff and all(low<=start and end<=high for start,end in bounds.values()),'BIND_WINDOWS_INVALID')
    need(bounds['preflight'][0]<=bounds['acquire'][0]<=bounds['execute'][0] and cutoff<=bounds['acquire'][0]
         and bounds['acquire'][1]<=bounds['execute'][1],'BIND_WINDOWS_INVALID')
    need(type(value['owner_order_text']) is str and 0<len(value['owner_order_text'])<=4096 and text(value['owner_order_text'],'[ -~]+'),'BIND_ORDER_NOT_ASCII')
    raw=value['owner_order_text'].encode('ascii')
    need(raw==k9w_owner_order(day,value['cutoff_at']),'BIND_ORDER_NOT_THE_DETERMINED_BYTES')
    need(value['owner_order_sha256']==sha(raw),'BIND_ORDER_SHA256_MISMATCH')
    return value

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in K9W_MODES,'MODE_INVALID')
    need(plan['epoch']==K9W_EPOCH,'EPOCH_INVALID')
    k9w_constants(plan)
    day=plan['day'];need(type(day) is str and day in K9W_DAYS,'DAY_INVALID')
    operation=plan['k9_operation'];need(type(operation) is str and operation in K9W_STEPS,'OPERATION_INVALID')
    step=K9W_STEPS[operation]
    need(step['mode']==mode and plan['k9_phase']==step['phase'],'OPERATION_NOT_OF_THIS_MODE')
    need(type(plan['slot']) is str and plan['slot'] in K9W_SLOTS,'SLOT_INVALID')
    need(plan['attempt_key']==k9w_attempt_key(K9W_EPOCH,day,step['phase'],operation),'ATTEMPT_KEY_MISMATCH')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    rows=plan['parent_rows']
    need(type(rows) is dict and set(rows)==set(K9W_PARENT_CHAINS),'PARENT_ROWS_INVALID')
    for name in K9W_PARENT_CHAINS:
        k9w_chain(rows[name],K9W_PLACEMENT[name],None,name in K9W_RECEIVES_ENTRY,'PARENT_ROWS_INVALID')
    # the source root lies on the filesystem of days/ (decision 6): the device of both signed leaves is one
    need(rows['source_root']['rows'][-1]['device']==rows['days']['rows'][-1]['device'],'SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS')
    if mode=='LAUNCH':
        point=k9w_instant_text(plan['run_not_after'],'RUN_NOT_AFTER_INVALID')
        if operation=='capture_launch':need(point==k9w_at(day,K9W_CAPTURE_RUN_NOT_AFTER),'RUN_NOT_AFTER_INVALID')
    else:need(plan['run_not_after'] is None,'RUN_NOT_AFTER_INVALID')
    if operation=='bind':k9w_bind(plan)
    else:need(plan['bind'] is None,'BIND_INVALID')
    # every argv this request can start, built once from the bytes with placeholders of the right grammar
    if step['row'] is not None:
        k9w_container_arguments(plan,'1'*64,'2'*64,K9W_MIN_TIMEOUT_SECONDS,{'manifest':'3'*64,'go':'4'*64,'previous':'5'*64})

def k9w_window_of(plan,now):
    """Pure, from the signed bytes and the clock, checked by perform before anything is observed (not by validate_plan:
    the core's conformance suite moves one plan's window across every day of the date class). The window lies in the eve
    or the morning of D (20:00Z of D-1 to 15:00Z of D); a before-open step ends by 13:30Z of D, an in-session step starts
    at 13:30Z of D or later; a LAUNCH's run_not_after is its window end plus its ceiling (capture: 14:03:00Z of D), on the
    UTC day of its window, and before the step's own limit (commit 03:50Z, publish 14:00Z of D); a cleanup starts after
    the capture's run_not_after; the time left to run_not_after leaves the container its minimum timeout."""
    day=plan['day'];step=K9W_STEPS[plan['k9_operation']]
    start,end=instant(plan['window']['not_before']),instant(plan['window']['expires_at'])
    low,high=k9w_at(k9w_day_shift(day,-1),'20:00:00'),k9w_at(day,'15:00:00')
    need(low<=start and end<=high,'WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    opening=k9w_at(day,'13:30:00')
    if step['window_class']=='BEFORE_OPEN':need(end<=opening,'WINDOW_NOT_OF_THE_STEP_CLASS')
    else:need(start>=opening,'WINDOW_NOT_OF_THE_STEP_CLASS')
    if plan['k9_operation']=='capture_cleanup':need(start>=k9w_at(day,K9W_CAPTURE_RUN_NOT_AFTER),'CLEANUP_BEFORE_CAPTURE_RUN_NOT_AFTER')
    if step['mode']!='LAUNCH':return None
    limit=instant(plan['run_not_after'])
    if plan['k9_operation']!='capture_launch':
        need(limit==k9w_after(end,step['ceiling_seconds']),'RUN_NOT_AFTER_NOT_WINDOW_END_PLUS_CEILING')
    need(limit.date()==start.date() and limit<=high,'RUN_NOT_AFTER_OUTSIDE_THE_UTC_DAY')
    if step['latest_run_not_after_utc_of_d'] is not None:need(limit<=k9w_at(day,step['latest_run_not_after_utc_of_d']),'RUN_NOT_AFTER_AFTER_THE_STEP_LIMIT')
    need((limit-now).total_seconds()>=K9W_MIN_TIMEOUT_SECONDS+K9W_LAUNCH_MARGIN_SECONDS+MAX_SECONDS,'RUN_NOT_AFTER_TOO_CLOSE')
    return limit

def k9w_host_paths(day):
    return {'tools':K9W_PLACEMENT['tools'],'day':K9W_PLACEMENT['days']+'/'+day,'day_receipts':K9W_PLACEMENT['days']+'/'+day+'/receipts',
            'source_root':K9W_SOURCE_ROOT,'emitter':K9W_PLACEMENT['emitter']}

def k9w_mounts(day,names):
    paths=k9w_host_paths(day)
    return [{'source':paths[K9W_MOUNTS[name]['host']],'target':K9W_MOUNTS[name]['target'],'read_only':K9W_MOUNTS[name]['read_only']} for name in names]

def k9w_step_plan_path(operation):return K9W_TARGETS['DAY']+'/plans/'+operation+'.json'

def k9w_command(plan,timeout,plan_sha256,packaged):
    """The command of the step: the content-addressed runner with its step plan, or the packaged risk CLI."""
    step=K9W_STEPS[plan['k9_operation']];values=plan['constants']
    head=['timeout','-s','KILL',str(timeout),'python']
    if step['command']=='RUNNER':
        return head+['-I',K9W_TARGETS['TOOLS']+'/k9_runner-'+values['runner_sha256']+'.py','--plan',k9w_step_plan_path(plan['k9_operation']),'--plan-sha256',plan_sha256]
    day_root=K9W_TARGETS['DAY']
    words=head+['-m','app.r2d2_v2_risk_host_executor',step['packaged_phase'],'--manifest',day_root+'/'+'/'.join(K9W_HOST_PLAN),'--manifest-sha256',packaged['manifest'],
                '--go',day_root+'/'+'/'.join(K9W_HOST_GO),'--go-sha256',packaged['go'],'--source-root','/app','--spool-root',day_root+'/risk/spool']
    if step['packaged_phase']!='preflight':words+=['--previous-receipt-sha256',packaged['previous']]
    return words

def k9w_container_arguments(plan,request_sha256,plan_sha256,timeout,packaged):
    """K9W's own argv builder (K9_INTERFACE_NOTE.md F5): what follows the fixed prefix of the create, attached or
    attached_short row. --name, the two labels, the network (create rows: the attached prefix fixes --network none), the
    env files of the step, the two fixed --env words, the mounts of the step (the core's mount_argument), the signed image
    ID, then the command. Every word in the core's run grammar; at most MAX_ARGUMENTS words."""
    step=K9W_STEPS[plan['k9_operation']];values=plan['constants'];day=plan['day']
    need(step['row'] in ('create','attached','attached_short'),'COMMAND_KIND')
    need(hexpin(request_sha256) and hexpin(plan_sha256) and integer(timeout,K9W_MIN_TIMEOUT_SECONDS if step['mode']=='LAUNCH' else 1,7200),'RUN_COMMAND_INVALID')
    need(text(values['image_id'],IMAGE_ID),'IMAGE_ID')
    name=k9w_container_name(day,plan['k9_operation']);need(text(name,'[a-z0-9][a-z0-9_.-]{0,62}'),'CONTAINER_TARGET')
    words=['--name',name,'--label',K9W_LABEL_ATTEMPT+'='+plan['attempt_key'],'--label',K9W_LABEL_REQUEST+'='+request_sha256]
    if step['row']=='create':
        network='none' if step['network']=='NONE' else values['networks'][step['network']]
        need(text(network,K9W_NETWORK_NAME),'NETWORK_INVALID');words+=['--network',network]
    else:need(step['network']=='NONE' and not step['env_files'],'NETWORK_INVALID')
    for name_of in step['env_files']:words+=['--env-file',K9W_PLACEMENT[K9W_ENV_FILES[name_of]]]
    for word in K9W_FIXED_ENV:words+=['--env',word]
    mounts=k9w_mounts(day,step['mounts'])
    need(len(mounts)<=MAX_MOUNTS and len({mount['target'] for mount in mounts})==len(mounts),'MOUNT_INVALID')
    for mount in mounts:words+=['--mount',mount_argument(mount)]
    command=k9w_command(plan,timeout,plan_sha256,packaged)
    need(0<len(command)<=2*MAX_RUN_WORDS and all(text(word,RUN_WORD) for word in command) and not command[0].startswith('-'),'RUN_COMMAND_INVALID')
    words+=[values['image_id']]+command
    need(len(words)<=MAX_ARGUMENTS and all(type(word) is str and word and len(word)<=8192 for word in words),'COMMAND_ARGUMENTS')
    return words

def k9w_chain_effects(item):return dict(chain_effects(item['rows']),open_root=item['open_root'])

def k9w_step_of(plan):
    """What the signers see of the step: the compiled row with its host paths, the argv with placeholders, the files."""
    operation=plan['k9_operation'];step=K9W_STEPS[operation];day=plan['day'];days=K9W_PLACEMENT['days']+'/'+day
    seen={'row':step,'container_name':k9w_container_name(day,operation) if step['row'] else None,
          'labels':{K9W_LABEL_ATTEMPT:plan['attempt_key'],K9W_LABEL_REQUEST:'<this request sha256>'} if step['row'] else None,
          'claim_file':K9W_PLACEMENT['claims']+'/'+plan['attempt_key']+'.claim',
          'step_plan_file':days+'/plans/'+operation+'.json' if step['row'] else None,
          'launch_record_file':days+'/launches/'+operation+'.json' if step['mode']=='LAUNCH' else None,
          'directories_created':[days]+[days+'/'+name for name in K9W_DAY_DIRECTORIES] if step['creates_day_directory'] else [],
          'removes_the_container_of':step['removes'],
          'removal_record_file':days+'/launches/'+step['removes']+'.json' if step['removes'] else None,
          'removal_container_name':k9w_container_name(day,step['removes']) if step['removes'] else None,
          'removal_argv':['rm','<the 64-hex ID of that record, exited, labels and image as written>'] if step['removes'] else None,
          'withdrawal_argv':['rm','<the 64-hex ID this run created, never started, when a mounted directory is no longer the one held>'] if step['row']=='create' else None,
          'mounts':k9w_mounts(day,step['mounts']),
          'env_files':[K9W_PLACEMENT[K9W_ENV_FILES[name]] for name in step['env_files']]}
    if step['row'] is not None:
        prefix=K9W_CREATE_PREFIX if step['row']=='create' else RUN_PREFIX
        timeout=K9W_MIN_TIMEOUT_SECONDS if step['mode']=='LAUNCH' else step['timeout_seconds']          # a LAUNCH's is computed at create
        seen['argv']=prefix+k9w_container_arguments(plan,'1'*64,'2'*64,timeout,{'manifest':'3'*64,'go':'4'*64,'previous':'5'*64})
        seen['argv_placeholders']={'1'*64:'<this request sha256>','2'*64:'<sha256 of the step plan>','3'*64:'<sha256 of risk/plan/HOST_PLAN.json>',
                                   '4'*64:'<sha256 of risk/plan/GO.json>','5'*64:'<sha256 of the previous packaged receipt>',
                                   str(timeout):('<min(run_not_after - now at create - %d s, ceiling + %d s)>'%(K9W_LAUNCH_MARGIN_SECONDS,K9W_CEILING_SLACK_SECONDS)
                                                 if step['mode']=='LAUNCH' else 'the fixed limit of the attached step')}
    return seen

def effects_of(plan):
    rows=plan['parent_rows'];step=K9W_STEPS.get(plan['k9_operation']) if type(plan['k9_operation']) is str else None
    launch=step is not None and step['mode']=='LAUNCH'
    return {'operation':OPERATION,'mode':plan['mode'],'epoch':plan['epoch'],'day':plan['day'],'k9_phase':plan['k9_phase'],
            'k9_operation':plan['k9_operation'],'slot':plan['slot'],'attempt_key':plan['attempt_key'],'run_not_after':plan['run_not_after'],
            'constants':plan['constants'],'parent_rows':None if rows is None else {name:k9w_chain_effects(rows[name]) for name in K9W_PARENT_CHAINS},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'bind':plan['bind'],
            'step':None if step is None else k9w_step_of(plan),
            'removal_only':'when an input of the step is not complete: the claim, the removal of the previous exited K9 container if the table names one, '
                           'then REFUSED_PREDECESSOR_NOT_COMPLETE (a subset of these effects)',
            'claims':1,'containers_created':0 if step is None or step['row'] is None else 1,'containers_removed_at_most':0 if step is None else (0 if step['removes'] is None else 1)+(1 if step['row']=='create' else 0),
            'files_created_at_most':0 if step is None else 1+(1 if step['row'] else 0)+(1 if launch else 0),
            'directories_created_at_most':0 if step is None or not step['creates_day_directory'] else 1+len(K9W_DAY_DIRECTORIES),'activation':False}

def success_of(plan):
    return K9W_SUCCESS.get(plan.get('mode'),COMPLETE_OUTCOME) if type(plan.get('mode')) is str else COMPLETE_OUTCOME


# ---------------------------------------------------------------- reads (the read program's helpers, written again here)
def k9w_child(host,parent_fd,name,gate):
    """A directory entry of a held directory, classified by lstat and opened without following a link: (fd, fstat)."""
    gate();named=host.lstat(name,parent_fd)
    need(not stat.S_ISLNK(named.st_mode),'SYMLINK_COMPONENT');need(stat.S_ISDIR(named.st_mode),'COMPONENT_NOT_DIRECTORY')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent_fd)
    try:
        info=host.fstat(fd);need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'PATH_CHANGED');return fd,info
    except BaseException:
        host.close(fd);raise

def k9w_descend(host,base_fd,parts,gate):
    fd=None
    try:
        for part in parts:
            child,_=k9w_child(host,base_fd if fd is None else fd,part,gate)
            if fd is not None:host.close(fd)
            fd=child
        return fd
    except BaseException:
        if fd is not None:host.close(fd)
        raise

def k9w_read(host,base_fd,parts,gate,limit):
    """(bytes, fstat) of a regular file below a held directory; FileNotFoundError when a component or the file is absent."""
    fd=k9w_descend(host,base_fd,parts[:-1],gate)
    try:
        gate();named=host.lstat(parts[-1],base_fd if fd is None else fd)
        need(stat.S_ISREG(named.st_mode),'FILE_NOT_REGULAR')
        raw,info=read_regular(host,parts[-1],base_fd if fd is None else fd,gate,limit)
        need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'FILE_CHANGED_DURING_READ');return raw,info
    finally:
        if fd is not None:host.close(fd)

def k9w_maybe(host,base_fd,parts,gate,limit=K9W_MAX_SMALL_FILE):
    try:return k9w_read(host,base_fd,parts,gate,limit)
    except FileNotFoundError:return None

def k9w_lexists(host,base_fd,parts,gate):
    """True when the last name exists (any type) below a held directory whose components are directories; False when
    any component or the name is absent. A component that is a link or not a directory is a refusal (never followed)."""
    try:fd=k9w_descend(host,base_fd,parts[:-1],gate)
    except FileNotFoundError:return False
    try:
        gate()
        try:host.lstat(parts[-1],base_fd if fd is None else fd)
        except FileNotFoundError:return False
        return True
    finally:
        if fd is not None:host.close(fd)

def k9w_private(info,mode):
    return (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink==1)

def k9w_document(raw,code):
    try:value=strict(raw,K9W_MAX_PLAN_FILE)
    except Refused:raise Refused(code) from None
    need(type(value) is dict,code);return value

def k9w_secret_private(host,parent,name,gate):
    """lstat only: a regular file of root, 0600, one link. Never opened, never its size or a digest."""
    parent.verify(gate);gate()
    try:found=host.lstat(name,parent.fd)
    except FileNotFoundError:return False
    return stat.S_ISREG(found.st_mode) and k9w_private(found,K9W_PRIVATE_FILE_MODE)

def k9w_outputs_ok(outputs,aggregates):
    def keys_ok(value,limit):return type(value) is dict and len(value)<=limit and all(text(key,K9W_OUTPUT_KEY) for key in value)
    return (keys_ok(outputs,K9W_MAX_OUTPUTS) and all(text(value,HEX64) for value in outputs.values()) and keys_ok(aggregates,K9W_MAX_AGGREGATES)
            and all(type(value) is dict and set(value)=={'files','sha256'} and integer(value['files'],0,K9W_MAX_AGGREGATE_ENTRIES) and text(value['sha256'],HEX64)
                    for value in aggregates.values()))

def k9w_counts_ok(value,depth=0):
    return (type(value) is dict and len(value)<=K9W_MAX_COUNTS
            and all(text(key,K9W_COUNT_KEY) and (integer(item,0,K9W_MAX_COUNT) or (depth==0 and k9w_counts_ok(item,1))) for key,item in value.items()))

def k9w_times_ok(first,second,now):
    try:return instant(first)<=instant(second)<=now
    except Refused:return False

def k9w_launched_facts(commands,target):
    """One container by its 64-hex ID with the launched format; CommandFailed when the engine does not know it."""
    need(text(target,CONTAINER_ID),'CONTAINER_TARGET')
    row=decode(commands.output('launched',target))
    need(set(row)==K9W_LAUNCHED_KEYS and row['id']==target and text(row['name'],'/'+CONTAINER_NAME) and text(row['image_id'],IMAGE_ID)
         and type(row['state']) is str and row['state'] in CONTAINER_STATES and type(row['running']) is bool and type(row['oom_killed']) is bool
         and integer(row['exit_code'],-1,255) and all(type(row[key]) is str and len(row[key])<=64 for key in ('started_at','finished_at'))
         and all(row[key] in ('',None) or text(row[key],HEX64) for key in ('attempt_key','request_sha256')),'LAUNCHED_METADATA_INVALID')
    return row


class K9Step:
    """The checks of one run, all before the first effect. Each method returns facts for the receipt and raises Refused
    only for what makes the run a refusal."""
    def __init__(self,plan,host,gate,commands,bound,clock):
        self.plan,self.host,self.gate,self.commands,self.clock=plan,host,gate,commands,clock
        self.day=plan['day'];self.operation=plan['k9_operation'];self.step=K9W_STEPS[self.operation];self.values=plan['constants']
        self.request_sha256=bound['request_sha256'];self.held={};self.unmet=[];self.predecessors={};self.packaged={}
        self.removable=None;self.listing=None;self.day_exists=None

    def hold(self,key,fd,**options):
        try:self.held[key]=Pinned(self.host,fd,**options)
        except BaseException:
            self.host.close(fd);raise
        return self.held[key]

    def chains(self):
        rows=self.plan['parent_rows']
        for key,name in (('DAYS','days'),('CLAIMS','claims'),('TOOLS','tools'),('SECRETS','secrets'),('SOURCE_ROOT','source_root')):
            self.hold(key,walk_pinned(self.host,rows[name]['rows'],self.gate,[]),rows=rows[name]['rows'])
        need(self.held['SOURCE_ROOT'].identity[0]==self.held['DAYS'].identity[0],'SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS')
        return {'held':sorted(self.held),'source_root_on_the_filesystem_of_days':True}

    def claim_absent(self):
        claims=self.held['CLAIMS'];claims.verify(self.gate);self.gate()
        try:self.host.lstat(self.plan['attempt_key']+'.claim',claims.fd)
        except FileNotFoundError:return {'claim_absent':True}
        raise Refused('CLAIM_EXISTS')

    def day_directory(self):
        """days/<D>: held when it exists, root's and private; the three directories K9W writes in, likewise."""
        days=self.held['DAYS'];days.verify(self.gate)
        try:fd,info=k9w_child(self.host,days.fd,self.day,self.gate)
        except FileNotFoundError:
            self.day_exists=False;return {'day_directory':'ABSENT'}
        day=self.hold('DAY',fd,parent=days,name=self.day);self.day_exists=True
        need(k9w_private(info,K9W_PRIVATE_DIRECTORY_MODE) and info.st_dev==days.identity[0],'DAY_DIRECTORY_NOT_PRIVATE')
        for name in K9W_DAY_DIRECTORIES:
            try:child,found=k9w_child(self.host,day.fd,name,self.gate)
            except FileNotFoundError:raise Refused('DAY_LAYOUT_INVALID') from None
            self.hold('DAY_'+name.upper(),child,parent=day,name=name)
            need(k9w_private(found,K9W_PRIVATE_DIRECTORY_MODE),'DAY_LAYOUT_INVALID')
        return {'day_directory':'PRESENT_PRIVATE'}

    def containers(self):
        """docker ps -a: the K9 containers the engine knows (names and states only in the receipt)."""
        self.listing=container_list(self.commands)
        mine=[row for row in self.listing if row['name'].startswith(K9W_CONTAINER_PREFIX)]
        return {'containers':len(self.listing),'k9_containers':sorted([row['name'],row['state']] for row in mine)}

    def previous(self):
        """The container this step removes (section 3.2 of the note): named by its launch record, inspected by ID."""
        removes=self.step['removes']
        if removes is None:return {'removes':None}
        name=k9w_container_name(self.day,removes);listed=[row for row in self.listing if row['name']==name]
        facts={'removes':removes,'name_listed':bool(listed)}
        if not self.day_exists:return dict(facts,record=False)
        day=self.held['DAY'];day.verify(self.gate)
        found=k9w_maybe(self.host,day.fd,['launches',removes+'.json'],self.gate)
        if found is None:return dict(facts,record=False)
        raw,info=found;record=k9w_document(raw,'PREVIOUS_LAUNCH_RECORD_INVALID')
        key=k9w_attempt_key(K9W_EPOCH,self.day,K9W_PHASE_OF[removes],removes)
        need(set(record)==K9W_RECORD_KEYS and record['schema']==K9W_RECORD_SCHEMA and record['epoch']==K9W_EPOCH and record['day']==self.day
             and record['operation']==removes and record['attempt_key']==key and record['container_name']==name and text(record['container_id'],CONTAINER_ID)
             and hexpin(record['request_sha256']) and hexpin(record['step_plan_sha256']) and k9w_private(info,K9W_PRIVATE_FILE_MODE),'PREVIOUS_LAUNCH_RECORD_INVALID')
        facts.update(record=True,record_sha256=sha(raw))
        ids=[row for row in self.listing if row['id']==record['container_id']]
        if not ids:return dict(facts,present=False)
        row=k9w_launched_facts(self.commands,record['container_id'])
        need(row['name']=='/'+name and row['image_id']==self.values['image_id'] and row['attempt_key']==key
             and row['request_sha256']==record['request_sha256'],'PREVIOUS_CONTAINER_NOT_AS_RECORDED')
        need(row['state']=='exited' and row['running'] is False,'UNCERTAIN_PREVIOUS_RUNNING')
        self.removable={'id':record['container_id'],'operation':removes,'exit_code':row['exit_code'],'oom_killed':row['oom_killed']}
        return dict(facts,present=True,state=row['state'],exit_code=row['exit_code'],oom_killed=row['oom_killed'],finished_at=row['finished_at'])

    def unmet_need(self,code):
        if code not in self.unmet:self.unmet.append(code)

    def runner_need(self,launch):
        """A runner step's files: its plan (hashed), its start marker, its one receipt COMPLETE, no FAILED; for a
        launch, its launch record with the same step plan hash; for the container this step removes, exit 0, not OOM."""
        day=self.held.get('DAY');facts={'kind':'RUNNER','complete':False}
        if day is None:return dict(facts,reason='DAY_DIRECTORY_ABSENT')
        day.verify(self.gate)
        phase=K9W_PHASE_OF[launch];key=k9w_attempt_key(K9W_EPOCH,self.day,phase,launch);now=self.clock()
        plan_file=k9w_maybe(self.host,day.fd,['plans',launch+'.json'],self.gate)
        if plan_file is None:return dict(facts,reason='STEP_PLAN_ABSENT')
        plan_sha=sha(plan_file[0])
        if K9W_STEPS[launch]['mode']=='LAUNCH':
            record=k9w_maybe(self.host,day.fd,['launches',launch+'.json'],self.gate)
            if record is None:return dict(facts,reason='LAUNCH_RECORD_ABSENT')
            body=k9w_document(record[0],'LAUNCH_RECORD_INVALID')
            if not (set(body)==K9W_RECORD_KEYS and body.get('attempt_key')==key and body.get('step_plan_sha256')==plan_sha and body.get('day')==self.day):
                return dict(facts,reason='LAUNCH_RECORD_NOT_OF_THIS_STEP')
        files={}
        for suffix in ('STARTED','RECEIPT','FAILED'):files[suffix]=k9w_maybe(self.host,day.fd,['receipts',launch+'.'+suffix+'.json'],self.gate)
        if files['FAILED'] is not None:return dict(facts,reason='STEP_FAILED')
        if files['STARTED'] is None or files['RECEIPT'] is None:return dict(facts,reason='STEP_RECEIPT_ABSENT')
        identity={'epoch':K9W_EPOCH,'day':self.day,'phase':phase,'operation':launch,'attempt_key':key,'step_plan_sha256':plan_sha}
        marker=k9w_document(files['STARTED'][0],'STEP_RECEIPT_INVALID');receipt=k9w_document(files['RECEIPT'][0],'STEP_RECEIPT_INVALID')
        marker_ok=(set(marker)==K9W_STARTED_KEYS and marker['schema']==K9W_STARTED_SCHEMA and all(marker[name]==value for name,value in identity.items())
                   and k9w_times_ok(marker['started_at'],marker['started_at'],now))
        receipt_ok=(set(receipt)==K9W_STEP_KEYS and receipt['schema']==K9W_STEP_SCHEMA and all(receipt[name]==value for name,value in identity.items())
                    and receipt['status']=='COMPLETE' and receipt['code'] is None and receipt['package_sha256']==K9W_PACKAGE_SHA256
                    and receipt['build_sha']==K9W_CODE_REVISION and k9w_times_ok(receipt['started_at'],receipt['completed_at'],now)
                    and k9w_outputs_ok(receipt['outputs'],receipt['aggregates']) and k9w_counts_ok(receipt['counts']))
        private=all(k9w_private(found[1],K9W_PRIVATE_FILE_MODE) for found in (files['STARTED'],files['RECEIPT']))
        if not (marker_ok and receipt_ok and private):return dict(facts,reason='STEP_RECEIPT_NOT_OF_THIS_STEP')
        removable=self.removable
        if removable is not None and removable['operation']==launch and (removable['exit_code']!=0 or removable['oom_killed']):
            return dict(facts,reason='EXIT_CODE_CONTRADICTS_THE_RECEIPT')
        return dict(facts,complete=True,reason=None,receipt_sha256=sha(files['RECEIPT'][0]),step_plan_sha256=plan_sha,outputs=receipt['outputs'])

    def packaged_plan(self):
        """The hashes of the packaged risk plan and GO, computed on the host."""
        if 'manifest' in self.packaged:return self.packaged
        day=self.held['DAY'];day.verify(self.gate)
        plan_raw=k9w_maybe(self.host,day.fd,list(K9W_HOST_PLAN),self.gate,K9W_MAX_PLAN_FILE);go_raw=k9w_maybe(self.host,day.fd,list(K9W_HOST_GO),self.gate,K9W_MAX_PLAN_FILE)
        if plan_raw is None or go_raw is None:return self.packaged
        self.packaged.update(manifest=sha(plan_raw[0]),go=sha(go_raw[0]),plan_document=k9w_document(plan_raw[0],'HOST_PLAN_INVALID'))
        return self.packaged

    def packaged_need(self,phase):
        """The packaged executor's receipt of a phase in spool/<HOST_PLAN sha256>: COMPLETE, bound to this plan and GO, D's namespace."""
        facts={'kind':'PACKAGED','complete':False}
        if self.held.get('DAY') is None:return dict(facts,reason='DAY_DIRECTORY_ABSENT')
        packaged=self.packaged_plan()
        if 'manifest' not in packaged:return dict(facts,reason='HOST_PLAN_ABSENT')
        day=self.held['DAY'];base=['risk','spool',packaged['manifest']];now=self.clock()
        files={suffix:k9w_maybe(self.host,day.fd,base+[phase+'.'+suffix+'.json'],self.gate,K9W_MAX_PLAN_FILE) for suffix in ('STARTED','RECEIPT','FAILED')}
        if files['FAILED'] is not None:return dict(facts,reason='STEP_FAILED')
        if files['STARTED'] is None or files['RECEIPT'] is None:return dict(facts,reason='STEP_RECEIPT_ABSENT')
        marker=k9w_document(files['STARTED'][0],'STEP_RECEIPT_INVALID');receipt=k9w_document(files['RECEIPT'][0],'STEP_RECEIPT_INVALID')
        bound={'phase':phase,'manifest_sha256':packaged['manifest'],'go_sha256':packaged['go']}
        marker_ok=set(marker)==K9W_PACKAGED_STARTED_KEYS and all(marker[name]==value for name,value in bound.items())
        receipt_ok=(set(receipt)==K9W_PACKAGED_RECEIPT_KEYS and receipt['schema']==K9W_PACKAGED_RECEIPT_SCHEMA and all(receipt[name]==value for name,value in bound.items())
                    and receipt['status']=='COMPLETE' and receipt['session_date']==self.day and receipt['namespace']==K9W_RISK_NAMESPACE+self.day
                    and receipt['operation_activation'] is False and receipt['certification_granted'] is False and type(receipt['outputs']) is dict
                    and k9w_times_ok(receipt['started_at'],receipt['completed_at'],now))
        if not (marker_ok and receipt_ok):return dict(facts,reason='STEP_RECEIPT_NOT_OF_THIS_STEP')
        removable=self.removable
        if removable is not None and removable['operation']==K9W_PACKAGED_LAUNCH[phase] and (removable['exit_code']!=0 or removable['oom_killed']):
            return dict(facts,reason='EXIT_CODE_CONTRADICTS_THE_RECEIPT')
        return dict(facts,complete=True,reason=None,receipt_sha256=sha(files['RECEIPT'][0]),manifest_sha256=packaged['manifest'],go_sha256=packaged['go'],
                    outputs=receipt['outputs'])

    def needs(self):
        """Everything the step needs on the host by fixed path. A need not met is collected, never raised: the run then
        does removal-only (or refuses when there is nothing to remove)."""
        step=self.step;facts={}
        if step['creates_day_directory']:
            if self.day_exists:self.unmet_need('DAY_DIRECTORY_EXISTS')
        elif not self.day_exists:self.unmet_need('DAY_DIRECTORY_ABSENT')
        for kind_of,name in step['needs']:
            found=self.runner_need(name) if kind_of=='RUNNER' else self.packaged_need(name)
            self.predecessors[name]=found
            facts[name]={key:found.get(key) for key in ('kind','complete','reason','receipt_sha256')}
            if not found['complete']:self.unmet_need('REFUSED_PREDECESSOR_NOT_COMPLETE')
        if self.unmet or self.step['mode']=='CLEANUP':return dict(facts,needs_not_met=list(self.unmet))
        day=self.held.get('DAY');source=self.held['SOURCE_ROOT']
        for item in step['destinations_absent']+step['destinations_present']:
            root,parts=item[0],[self.day if part=='<D>' else part for part in item[1:]]
            if root=='days':continue                                   # days/<D> itself: decided above
            base=day if root=='day' else source;base.verify(self.gate)
            exists=k9w_lexists(self.host,base.fd,parts,self.gate)
            if item in step['destinations_absent'] and exists:self.unmet_need('DESTINATION_EXISTS')
            if item in step['destinations_present'] and not exists:self.unmet_need('INPUT_DIRECTORY_ABSENT')
        if step['symbols_equal_publish_receipt']:
            outputs=self.predecessors['publish_launch'].get('outputs') or {}
            found=k9w_maybe(self.host,day.fd,['control','symbols.txt'],self.gate,K9W_MAX_SYMBOLS_FILE)
            if found is None or outputs.get('day/control/symbols.txt')!=sha(found[0]):self.unmet_need('SYMBOLS_NOT_AS_PUBLISHED')
        if self.operation=='preflight':
            outputs=self.predecessors['bind'].get('outputs') or {};packaged=self.packaged_plan()
            if ('manifest' not in packaged or outputs.get('day/risk/plan/HOST_PLAN.json')!=packaged['manifest']
                    or outputs.get('day/risk/plan/GO.json')!=packaged['go']):self.unmet_need('RISK_PLAN_NOT_AS_BOUND')
        if step['packaged_phase'] is not None:
            packaged=self.packaged_plan();now=self.clock()
            try:
                bounds=packaged['plan_document']['phase_windows'][step['packaged_phase']]
                inside_window=instant(bounds['not_before'])<=now<=instant(bounds['not_after'])
            except (KeyError,TypeError,Refused):inside_window=False
            if not inside_window:self.unmet_need('RISK_PHASE_WINDOW_NOT_OPEN')
            spool=['risk','spool',packaged.get('manifest','0'*64)]
            if step['packaged_phase']!='preflight' and any(k9w_lexists(self.host,day.fd,spool+[step['packaged_phase']+'.'+suffix+'.json'],self.gate)
                                                           for suffix in ('STARTED','RECEIPT','FAILED')):self.unmet_need('DESTINATION_EXISTS')
            if step['packaged_phase']=='preflight' and k9w_lexists(self.host,day.fd,spool,self.gate):self.unmet_need('DESTINATION_EXISTS')
        secrets=self.held['SECRETS']
        for name in step['env_files']:
            if not k9w_secret_private(self.host,secrets,K9W_PLACEMENT[K9W_ENV_FILES[name]].rsplit('/',1)[1],self.gate):self.unmet_need('ENV_FILE_NOT_PRIVATE')
        if step['emitter_password']:
            secrets.verify(self.gate)
            try:
                fd,info=k9w_child(self.host,secrets.fd,'emitter',self.gate);emitter=self.hold('EMITTER',fd,parent=secrets,name='emitter')
                if not (k9w_private(info,K9W_PRIVATE_DIRECTORY_MODE) and k9w_secret_private(self.host,emitter,'password',self.gate)):self.unmet_need('EMITTER_SECRET_NOT_PRIVATE')
            except FileNotFoundError:self.unmet_need('EMITTER_SECRET_NOT_PRIVATE')
        if step['command']=='RUNNER':
            tools=self.held['TOOLS'];tools.verify(self.gate);self.gate()
            try:found=self.host.lstat('k9_runner-'+self.values['runner_sha256']+'.py',tools.fd);ok=stat.S_ISREG(found.st_mode) and k9w_private(found,K9W_PRIVATE_FILE_MODE)
            except FileNotFoundError:ok=False
            if not ok:self.unmet_need('RUNNER_FILE_NOT_AS_REQUIRED')
        if 'DAY_RECEIPTS' in step['mounts'] and self.held.get('DAY_RECEIPTS') is None:self.unmet_need('DAY_LAYOUT_INVALID')
        days=self.held['DAYS'];days.verify(self.gate);available=free_bytes(self.host,days.fd)
        if available<K9W_DISK_FLOOR_BYTES:self.unmet_need('DISK_FREE_BELOW_FLOOR')
        return dict(facts,needs_not_met=list(self.unmet),days_bytes_available=available,floor_bytes=K9W_DISK_FLOOR_BYTES,hold=available<K9W_DISK_FLOOR_BYTES)

    def engine(self):
        """FULL mode only: the signed image is present with the revision label; no K9 container is active; the name of
        this step's container is free."""
        found=image_facts(self.commands,self.values['image_id'])
        need(found['id']==self.values['image_id'] and found['revision_label']==K9W_CODE_REVISION,'IMAGE_NOT_THE_SIGNED_ONE')
        need(not [row for row in self.listing if row['name'].startswith(K9W_CONTAINER_PREFIX) and row['state'] in ('running','restarting','paused','removing')],
             'ANOTHER_K9_CONTAINER_ACTIVE')
        need(not [row for row in self.listing if row['name']==k9w_container_name(self.day,self.operation)],'CONTAINER_NAME_IN_USE')
        # every bind source: held (its ancestors are the signed root-only chains, walked and held) and itself root's,
        # gid 0, not writable by group or other, not setgid; its device the one of days/ (no mount inside the tree)
        for name in self.step['mounts']:
            if self.step['creates_day_directory'] and K9W_MOUNT_HELD[name] in ('DAY','DAY_RECEIPTS'):continue     # created by this run: proved 0:0 0700 there
            held=self.held.get(K9W_MOUNT_HELD[name]);need(held is not None,'MOUNT_SOURCE_NOT_ROOT_CONTROLLED')
            device,_,uid,gid,mode=held.identity
            need(uid==0 and gid==0 and not mode&0o022 and not mode&stat.S_ISGID and device==self.held['DAYS'].identity[0],'MOUNT_SOURCE_NOT_ROOT_CONTROLLED')
        return {'mount_sources_root_controlled':True,'image_equal_signed':True,'revision_equal_signed':True,'no_active_k9_container':True,'own_name_free':True}

    def close(self):
        for key in sorted(self.held,reverse=True):
            try:self.held[key].close()
            except Exception:pass


K9W_STEP_PLAN_KEYS=frozenset(('schema','epoch','day','k9_phase','k9_operation','slot','attempt_key','request_sha256','go_sha256',
                              'run_not_after','constants','network_class','database','risk','step_row'))
K9W_STEP_PLAN_CONSTANTS=('package_sha256','code_revision','act_b_sha256','release_sha256','policy_sha256','runner_sha256','risk_source_pins_sha256',
                         'risk_limits','disk_floor_bytes')
# The emitter's non-secret connection names (K9_INTERFACE_NOTE.md 4.3; the runner's DB); the password is the file of the EMITTER mount.
K9W_EMITTER_DATABASE={'host':'db','port':5432,'dbname':'c3po','role':'c3po_v2_causal_emitter'}

def k9w_step_plan(plan,bound,checks,run_not_after):
    """The step plan K9_STEP_PLAN_V1 the runner reads by --plan and --plan-sha256: canonical bytes, exactly the keys of
    the runner's PLAN_KEYS (fable-k9runner-20261004, read 2026-10-04 21:2xZ; DESIGN.md section 5). The runner reads its
    predecessors' receipts itself by fixed path; this file carries the identity, the deadline, the signed constants, the
    network class, the emitter's connection names (commit, publish), the bind's signed risk values, and the compiled row."""
    step=checks.step;values=plan['constants'];operation=plan['k9_operation']
    row=dict(step,operation=operation,container_name=k9w_container_name(plan['day'],operation),step_table_sha256=K9W_STEP_TABLE_SHA256)
    body={'schema':K9W_PLAN_STEP_SCHEMA,'epoch':K9W_EPOCH,'day':plan['day'],'k9_phase':step['phase'],'k9_operation':operation,'slot':plan['slot'],
          'attempt_key':plan['attempt_key'],'request_sha256':bound['request_sha256'],'go_sha256':bound['go_sha256'],'run_not_after':run_not_after,
          'constants':{key:values[key] for key in K9W_STEP_PLAN_CONSTANTS},'network_class':step['network'],
          'database':dict(K9W_EMITTER_DATABASE) if step['emitter_password'] else None,
          'risk':dict(plan['bind']) if operation=='bind' else None,'step_row':row}
    return canonical(body)


def k9w_settle(state,result,settled):
    """Exactly one of done / fail / unknown for an effect() that returned (effect() settled the others itself)."""
    if not (result['started'] and result['returned']):return
    {'DONE':state.done,'FAIL':state.fail}.get(settled,state.unknown)()

def k9w_command_facts(result):
    return {'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'code':result['code']}


def _never_complete(receipt):
    receipt['expectations_met']=False
    if receipt.get('code') is None:receipt['code']='RECEIPT_REDUCED_FOR_SIZE'
def _drop_checks(receipt):
    _never_complete(receipt)
    for name in ('checks',):
        if type(receipt.get(name)) is dict:receipt[name]={key:'REDUCED' for key in receipt[name]}
def _drop_effects(receipt):
    _never_complete(receipt);receipt['effects']='REDUCED'
REDUCTIONS=[('CHECKS_REDUCED',_drop_checks),('EFFECTS_REDUCED',_drop_effects)]


def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    commands=Commands(host,gate);checks=K9Step(plan,host,gate,commands,bound,clock)            # pure: nothing is touched
    step=checks.step;operation=plan['k9_operation'];go16=bound['go_sha256'][:16]
    gate()                                                                                      # first gate call: before anything is observed
    state.started=True
    facts={};ledger={'directories':[],'files':[],'commands':{}};out={'container_id':None,'launch_record_sha256':None,'step_plan_sha256':None,
                                                                    'timeout_seconds':None,'removed':None,'removal_read_back':False,'receipt':None}
    def finish(status,outcome,code,reached,extra=None):
        if status==COMPLETE_STATUS and state.uncertain()!=0:
            status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,'EFFECT_NOT_SETTLED'                 # never a success with an uncertain effect
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),k9_operation=operation,day=plan['day'],slot=plan['slot'],
            mode=plan['mode'],effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),
            mutating_calls=state.counts(),phase_reached=reached,checks=facts,ledger=ledger,objects_left_by_this_run=objects_left(ledger['directories'],ledger['files']),
            expectations_met=status==COMPLETE_STATUS,**dict(out,**(extra or {})))))
    def observe(label,action):
        gate();facts[label]=action()
    removal_only=False
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')                     # first, before anything is looked at
            k9w_window_of(plan,clock())                                                 # pure: the window belongs to D
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            observe('chains',checks.chains)
            observe('claim',checks.claim_absent)
            observe('day',checks.day_directory)
            observe('containers',checks.containers)
            observe('previous',checks.previous)
            observe('needs',checks.needs)
            held=[code for code in checks.unmet if code in K9W_HOLD_CODES]
            if held:raise Refused(held[0])
            if checks.unmet or step['mode']=='CLEANUP':
                if checks.removable is None:
                    raise Refused('CLEANUP_NOTHING_TO_REMOVE' if step['mode']=='CLEANUP' and not checks.unmet else checks.unmet[0])
                removal_only=step['mode']!='CLEANUP'
                rows=('remove',)
            else:
                observe('engine',checks.engine)
                rows=(('remove',) if checks.removable is not None else ())+(('create','start') if step['row']=='create' else (step['row'],))
            budget=effects_budget(*rows)+K9W_FILES_ALLOWANCE_SECONDS
            facts['budget']={'rows':list(rows),'seconds_needed':budget}
            need(gate()>=budget,'BUDGET_INSUFFICIENT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,'PRECHECK')

        # ---------------------------------------------------------------- effects: from here on nothing refuses
        claim=canonical({'epoch':K9W_EPOCH,'day':plan['day'],'phase':step['phase'],'operation':operation,'slot':plan['slot'],'request_sha256':bound['request_sha256']})
        claims=checks.held['CLAIMS']
        row=create_file(0,'CLAIM',K9W_PLACEMENT['claims']+'/'+plan['attempt_key']+'.claim',claim,K9W_PRIVATE_FILE_MODE,claims,host,gate,state,go16)
        ledger['files'].append(row)
        if row['state']!='INSTALLED_DURABLE':
            if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,'CLAIM_EXISTS' if row['code']=='DESTINATION_APPEARED_AFTER_PRECHECK' else row['code'] or 'CLAIM_NOT_CREATED','CLAIM')
            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,row['code'] or 'CLAIM_NOT_CREATED','CLAIM')
        stop=readback_file(row,claim,K9W_PRIVATE_FILE_MODE,claims,host,gate)
        if stop is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,'CLAIM')

        removal=None
        if checks.removable is not None:
            removal=effect(state,commands,'remove',checks.removable['id'],capture=True);ledger['commands']['remove']=k9w_command_facts(removal)
            if not removal['started']:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,removal['code'] or 'REMOVE_NOT_STARTED','REMOVE')
            if not removal['returned']:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,removal['code'] or 'REMOVE_UNCERTAIN','REMOVE')
            if removal['returncode']!=0 or removal_only or step['mode']=='CLEANUP':
                # read back now: a failed removal stops the step; for removal-only and cleanup it is the last effect
                gone=k9w_removal_readback(state,removal,commands,checks,out)
                if gone is not True:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREVIOUS_CONTAINER_NOT_REMOVED' if gone is False else 'REMOVAL_READBACK_UNAVAILABLE','REMOVE')
                if step['mode']=='CLEANUP':return finish(COMPLETE_STATUS,K9W_CLEANUP_OUTCOME,None,'REMOVED')
                if removal['returncode']!=0:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'PREVIOUS_CONTAINER_REMOVAL_STATUS_NONZERO','REMOVE')
                if removal_only:return finish(PARTIAL_STATUS,K9W_REMOVAL_ONLY_OUTCOME,checks.unmet[0],'REMOVAL_ONLY',{'needs_not_met':list(checks.unmet)})

        # FULL mode: the day's directories (collect_launch), the step plan, the container
        day=checks.held.get('DAY')
        if step['creates_day_directory']:
            handles={}
            try:
                entry=create_directory('DAY',K9W_PLACEMENT['days']+'/'+plan['day'],K9W_PRIVATE_DIRECTORY_MODE,checks.held['DAYS'],host,gate,state,handles)
                ledger['directories'].append(entry)
                if 'DAY' in handles:checks.held['DAY']=handles.pop('DAY')
                if entry['state']!='CREATED_DURABLE':return k9w_stopped(finish,state,removal,commands,checks,out,entry['code'] or 'DIRECTORY_NOT_CREATED','DIRECTORIES')
                day=checks.held['DAY']
                for name in K9W_DAY_DIRECTORIES:
                    key='DAY_'+name.upper()
                    entry=create_directory(key,K9W_PLACEMENT['days']+'/'+plan['day']+'/'+name,K9W_PRIVATE_DIRECTORY_MODE,day,host,gate,state,handles)
                    ledger['directories'].append(entry)
                    if key in handles:checks.held[key]=handles.pop(key)
                    if entry['state']!='CREATED_DURABLE':return k9w_stopped(finish,state,removal,commands,checks,out,entry['code'] or 'DIRECTORY_NOT_CREATED','DIRECTORIES')
            finally:
                for handle in handles.values():
                    try:handle.close()
                    except Exception:pass
        run_not_after=plan['run_not_after'] if step['mode']=='LAUNCH' else k9w_after(instant(plan['window']['expires_at']),MAX_SECONDS).isoformat()
        content=k9w_step_plan(plan,bound,checks,run_not_after);plans=checks.held['DAY_PLANS']
        row=create_file(1,'STEP_PLAN',K9W_PLACEMENT['days']+'/'+plan['day']+'/plans/'+operation+'.json',content,K9W_PRIVATE_FILE_MODE,plans,host,gate,state,go16)
        ledger['files'].append(row)
        stop=row['code'] if row['state']!='INSTALLED_DURABLE' else readback_file(row,content,K9W_PRIVATE_FILE_MODE,plans,host,gate)
        if stop is None and step['creates_day_directory']:
            for entry in ledger['directories']:
                held=checks.held[entry['key']];stop=readback_directory(entry['path'],K9W_PRIVATE_DIRECTORY_MODE,held,host,gate,
                                                                       len(K9W_DAY_DIRECTORIES) if entry['key']=='DAY' else 1 if entry['key']=='DAY_PLANS' else 0)
                if stop is not None:break
        if stop is not None:return k9w_stopped(finish,state,removal,commands,checks,out,stop,'STEP_PLAN')
        plan_sha256=sha(content);out['step_plan_sha256']=plan_sha256
        packaged={'manifest':checks.packaged.get('manifest'),'go':checks.packaged.get('go'),
                  'previous':(checks.predecessors.get(step['needs'][0][1]) or {}).get('receipt_sha256') if step['needs'] else None}

        if step['mode']=='ATTACHED':
            middle=k9w_container_arguments(plan,bound['request_sha256'],plan_sha256,step['timeout_seconds'],packaged)
            moved=k9w_mounts_moved(checks)
            if moved:
                out['mount_sources_replaced']=moved
                return k9w_stopped(finish,state,removal,commands,checks,out,'MOUNT_SOURCE_REPLACED_BEFORE_START','ATTACHED')
            result=effect(state,commands,step['row'],*middle,capture=True);ledger['commands'][step['row']]=k9w_command_facts(result)
            if not result['started']:return k9w_stopped(finish,state,removal,commands,checks,out,result['code'] or 'ATTACHED_NOT_STARTED','ATTACHED')
            if not result['returned']:return k9w_stopped(finish,state,removal,commands,checks,out,result['code'] or 'ATTACHED_DID_NOT_RETURN','ATTACHED')
            verdict=k9w_attached_result(plan,checks,result['returncode'],plan_sha256,result['output'])
            moved=k9w_mounts_moved(checks)
            if moved:out['mount_sources_replaced_after_run']=moved;verdict['complete']=False;verdict['code']='MOUNT_SOURCE_REPLACED_AROUND_THE_RUN'

            out['receipt']=verdict
            k9w_settle(state,result,'FAIL' if verdict['engine_refused'] else 'DONE')
            k9w_removal_readback(state,removal,commands,checks,out);gone=k9w_removal_code(removal,out)
            if gone is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,gone,'ATTACHED')
            if verdict['complete']:return finish(COMPLETE_STATUS,K9W_ATTACHED_OUTCOME,None,'ATTACHED')
            return finish(PARTIAL_STATUS,K9W_NOT_COMPLETE_OUTCOME,verdict['code'],'ATTACHED')

        # LAUNCH: create, start, the launch record, then the readbacks
        now=clock();timeout=int((instant(plan['run_not_after'])-now).total_seconds())-K9W_LAUNCH_MARGIN_SECONDS
        if operation!='capture_launch':timeout=min(timeout,step['ceiling_seconds']+K9W_CEILING_SLACK_SECONDS)      # capture: its fixed 14:03Z bounds it
        if timeout<K9W_MIN_TIMEOUT_SECONDS:return k9w_stopped(finish,state,removal,commands,checks,out,'RUN_NOT_AFTER_TOO_CLOSE','CREATE')
        out['timeout_seconds']=timeout
        middle=k9w_container_arguments(plan,bound['request_sha256'],plan_sha256,timeout,packaged)
        created_at=now.isoformat()
        created=effect(state,commands,'create',*middle,capture=True);ledger['commands']['create']=k9w_command_facts(created)
        identifier=None
        if created['started'] and created['returned'] and created['returncode']==0:
            raw=created['output']
            if type(raw) is bytes and raw.endswith(b'\n') and raw.count(b'\n')==1 and text(raw[:-1].decode('ascii','replace'),CONTAINER_ID):identifier=raw[:-1].decode('ascii')
        if identifier is None:
            if created['started'] and created['returned']:
                exists=k9w_name_listed(commands,k9w_container_name(plan['day'],operation))
                k9w_settle(state,created,'FAIL' if exists is False else 'UNKNOWN')
            return k9w_stopped(finish,state,removal,commands,checks,out,created['code'] or 'CREATE_FAILED','CREATE')
        out['container_id']=identifier
        # The engine resolves a bind source by path when the container starts, following links. Every bind source and
        # its ancestors are root's (decision 6), so only root can move one; as defence in depth every mounted directory
        # is still proved again from "/" right before start; a divergence removes the created (never started) container.
        moved=k9w_mounts_moved(checks)
        if moved:
            out['mount_sources_replaced']=moved
            withdrawn=effect(state,commands,'remove',identifier,capture=True);ledger['commands']['remove_created']=k9w_command_facts(withdrawn)
            gone=k9w_listed_absent(commands,identifier) if withdrawn['started'] and withdrawn['returned'] else None
            k9w_settle(state,created,'DONE');k9w_settle(state,withdrawn,'DONE' if gone is True else 'FAIL' if gone is False and withdrawn['returncode']!=0 else 'UNKNOWN')
            out['created_container_removed']=gone
            return k9w_stopped(finish,state,removal,commands,checks,out,'MOUNT_SOURCE_REPLACED_BEFORE_START','START')
        started_at=clock().isoformat()
        started=effect(state,commands,'start',identifier,capture=True);ledger['commands']['start']=k9w_command_facts(started)
        if not (started['started'] and started['returned'] and started['returncode']==0):
            seen=attempt(lambda:k9w_launched_facts(commands,identifier))
            k9w_settle(state,created,'DONE' if seen.get('id')==identifier else 'UNKNOWN')
            k9w_settle(state,started,'FAIL' if seen.get('state')=='created' else 'UNKNOWN')
            return k9w_stopped(finish,state,None,commands,checks,out,started['code'] or 'START_FAILED','START',removal)
        record=canonical({'schema':K9W_RECORD_SCHEMA,'epoch':K9W_EPOCH,'day':plan['day'],'operation':operation,'slot':plan['slot'],'attempt_key':plan['attempt_key'],
                          'request_sha256':bound['request_sha256'],'step_plan_sha256':plan_sha256,'container_id':identifier,
                          'container_name':k9w_container_name(plan['day'],operation),'created_at':created_at,'started_at':started_at,'timeout_seconds':timeout})
        launches=checks.held['DAY_LAUNCHES']
        row=create_file(2,'LAUNCH_RECORD',K9W_PLACEMENT['days']+'/'+plan['day']+'/launches/'+operation+'.json',record,K9W_PRIVATE_FILE_MODE,launches,host,gate,state,go16)
        ledger['files'].append(row)
        stop=row['code'] if row['state']!='INSTALLED_DURABLE' else readback_file(row,record,K9W_PRIVATE_FILE_MODE,launches,host,gate)
        if row['state']=='INSTALLED_DURABLE':out['launch_record_sha256']=sha(record)
        # readback of the container this run created and started: by ID, its name, image, labels and a started state
        seen=attempt(lambda:k9w_launched_facts(commands,identifier))
        expected=seen.get('id')==identifier and seen.get('name')=='/'+k9w_container_name(plan['day'],operation) and seen.get('image_id')==plan['constants']['image_id']
        labelled=expected and seen.get('attempt_key')==plan['attempt_key'] and seen.get('request_sha256')==bound['request_sha256']
        k9w_settle(state,created,'DONE' if labelled else 'UNKNOWN')
        k9w_settle(state,started,'DONE' if labelled and seen.get('state') in ('running','exited') else 'UNKNOWN')
        out['container_readback']={key:seen.get(key) for key in ('status','code','state','running','exit_code')} if 'status' in seen else {
            'as_built':labelled,'state':seen.get('state'),'running':seen.get('running'),'exit_code':seen.get('exit_code')}
        k9w_removal_readback(state,removal,commands,checks,out)
        moved=k9w_mounts_moved(checks)
        if moved:
            out['mount_sources_replaced_after_start']=moved
            return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'MOUNT_SOURCE_REPLACED_AROUND_START','READBACK')
        if stop is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,'LAUNCH_RECORD')
        if not (labelled and seen.get('state') in ('running','exited')):return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,'LAUNCHED_CONTAINER_NOT_AS_BUILT','READBACK')
        gone=k9w_removal_code(removal,out)
        if gone is not None:return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,gone,'READBACK')
        return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,'LAUNCHED')
    finally:checks.close()


K9W_MOUNT_HELD={'TOOLS':'TOOLS','DAY':'DAY','DAY_READ_ONLY':'DAY','DAY_RECEIPTS':'DAY_RECEIPTS','SOURCE':'SOURCE_ROOT','EMITTER':'EMITTER'}
def k9w_mounts_moved(checks):
    """The mount names of the step whose directory is no longer the one held (walked again from "/" without following
    a link, identity compared): [] when every one is still in place."""
    moved=[]
    for name in checks.step['mounts']:
        held=checks.held.get(K9W_MOUNT_HELD[name])
        try:
            need(held is not None,'DIRECTORY_NOT_HELD');held.verify(checks.gate)
        except Exception:moved.append(name)
    return moved

def k9w_listed_absent(commands,identifier):
    """True when a complete listing no longer shows the ID, False when it does, None when the listing is unavailable."""
    try:rows=container_list(commands)
    except Exception:return None
    return not [row for row in rows if row['id']==identifier]

def k9w_name_listed(commands,name):
    try:rows=container_list(commands)
    except Exception:return None
    return bool([row for row in rows if row['name']==name])

def k9w_removal_readback(state,removal,commands,checks,out):
    """The readback of a removal that returned (once per run): a complete listing without the ID settles it as done; a
    listing that still shows it after a non-zero status proves nothing changed; anything else is uncertain. None when
    no removal returned."""
    if removal is None or not (removal['started'] and removal['returned']):return None
    if out['removal_read_back']:return out['removed']
    gone=k9w_listed_absent(commands,checks.removable['id']);out['removed']=gone;out['removal_read_back']=True
    k9w_settle(state,removal,'DONE' if gone is True else 'FAIL' if gone is False and removal['returncode']!=0 else 'UNKNOWN')
    return gone

def k9w_removal_code(removal,out):
    """None when no removal was made or it was read back as done; otherwise the code that stops the step."""
    if removal is None:return None
    if out['removed'] is True:return None
    return 'PREVIOUS_CONTAINER_NOT_REMOVED' if out['removed'] is False else 'REMOVAL_READBACK_UNAVAILABLE'

def k9w_stopped(finish,state,removal,commands,checks,out,code,reached,deferred=None):
    """A FULL-mode run that stops after its claim: settle a pending removal by reading it back, then PARTIAL."""
    k9w_removal_readback(state,removal if removal is not None else deferred,commands,checks,out)
    return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,reached)

def k9w_attached_result(plan,checks,returncode,plan_sha256,output=b''):
    """After an attached run returned: its receipt read back (the runner's in days/<D>/receipts, or the packaged one in
    the spool). engine_refused: docker's own status with no start marker (nothing ran in the container). The runner prints
    its terminal receipt's bytes as its one result line (its DESIGN.md section 6 item 3): for bind and stage the line
    must be the receipt file's bytes, or the step is not complete."""
    operation=plan['k9_operation'];step=checks.step;day=checks.held['DAY'];gate=checks.gate;host=checks.host;now=checks.clock()
    verdict={'returncode':returncode,'complete':False,'engine_refused':False,'code':None,'receipt_sha256':None}
    try:
        day.verify(gate)
        if step['command']=='PACKAGED':
            base=['risk','spool',checks.packaged['manifest']];phase=step['packaged_phase']
            files={suffix:k9w_maybe(host,day.fd,base+[phase+'.'+suffix+'.json'],gate,K9W_MAX_PLAN_FILE) for suffix in ('STARTED','RECEIPT','FAILED')}
            bound={'phase':phase,'manifest_sha256':checks.packaged['manifest'],'go_sha256':checks.packaged['go']}
            ok=False
            if files['RECEIPT'] is not None and files['FAILED'] is None and files['STARTED'] is not None:
                receipt=k9w_document(files['RECEIPT'][0],'STEP_RECEIPT_INVALID');marker=k9w_document(files['STARTED'][0],'STEP_RECEIPT_INVALID')
                ok=(set(marker)==K9W_PACKAGED_STARTED_KEYS and all(marker[key]==value for key,value in bound.items())
                    and set(receipt)==K9W_PACKAGED_RECEIPT_KEYS and receipt['schema']==K9W_PACKAGED_RECEIPT_SCHEMA and all(receipt[key]==value for key,value in bound.items())
                    and receipt['status']=='COMPLETE' and receipt['session_date']==plan['day'] and receipt['namespace']==K9W_RISK_NAMESPACE+plan['day']
                    and receipt['operation_activation'] is False and receipt['certification_granted'] is False
                    and k9w_times_ok(receipt['started_at'],receipt['completed_at'],now))
                verdict['receipt_sha256']=sha(files['RECEIPT'][0])
            elif files['FAILED'] is not None:
                failed=k9w_document(files['FAILED'][0],'STEP_RECEIPT_INVALID')
                verdict['code']=failed.get('code') if text(failed.get('code'),CODE) else 'PACKAGED_PHASE_FAILED'
        else:
            key=plan['attempt_key'];files={suffix:k9w_maybe(host,day.fd,['receipts',operation+'.'+suffix+'.json'],gate) for suffix in ('STARTED','RECEIPT','FAILED')}
            identity={'epoch':K9W_EPOCH,'day':plan['day'],'phase':step['phase'],'operation':operation,'attempt_key':key,'step_plan_sha256':plan_sha256}
            ok=False
            if files['RECEIPT'] is not None and files['FAILED'] is None and files['STARTED'] is not None:
                receipt=k9w_document(files['RECEIPT'][0],'STEP_RECEIPT_INVALID');marker=k9w_document(files['STARTED'][0],'STEP_RECEIPT_INVALID')
                ok=(set(receipt)==K9W_STEP_KEYS and receipt['schema']==K9W_STEP_SCHEMA and all(receipt[name]==value for name,value in identity.items())
                    and receipt['status']=='COMPLETE' and receipt['code'] is None and receipt['package_sha256']==K9W_PACKAGE_SHA256
                    and receipt['build_sha']==K9W_CODE_REVISION and k9w_times_ok(receipt['started_at'],receipt['completed_at'],now)
                    and k9w_outputs_ok(receipt['outputs'],receipt['aggregates']) and k9w_counts_ok(receipt['counts'])
                    and set(marker)==K9W_STARTED_KEYS and marker['schema']==K9W_STARTED_SCHEMA and all(marker[name]==value for name,value in identity.items())
                    and all(k9w_private(found[1],K9W_PRIVATE_FILE_MODE) for found in (files['STARTED'],files['RECEIPT'])))
                verdict['receipt_sha256']=sha(files['RECEIPT'][0])
                verdict['result_line_is_the_receipt']=type(output) is bytes and output==files['RECEIPT'][0]+b'\n'
                if ok and not verdict['result_line_is_the_receipt']:ok=False;verdict['code']='ATTACHED_RESULT_LINE_NOT_THE_RECEIPT'
                if ok and operation=='bind':ok=k9w_bind_outputs(plan,checks,receipt['outputs'])
                if ok and operation=='stage':ok=k9w_stage_outputs(plan,checks,receipt['outputs'])
            elif files['FAILED'] is not None:
                failed=k9w_document(files['FAILED'][0],'STEP_RECEIPT_INVALID')
                verdict['code']=failed.get('code') if text(failed.get('code'),CODE) else 'STEP_FAILED'
        verdict['engine_refused']=files['STARTED'] is None and files['RECEIPT'] is None and files['FAILED'] is None and returncode in RUN_ENGINE_STATUSES
        verdict['complete']=bool(ok) and returncode==0
        if not verdict['complete'] and verdict['code'] is None:
            verdict['code']=('ATTACHED_ENGINE_REFUSED' if verdict['engine_refused'] else 'EXIT_CODE_CONTRADICTS_THE_RECEIPT' if ok
                             else 'ATTACHED_RECEIPT_NOT_COMPLETE')
    except Exception as error:
        verdict['code']=code_of(error,'ATTACHED_RECEIPT_UNAVAILABLE')
    return verdict

def k9w_bind_outputs(plan,checks,outputs):
    """bind: the documents it wrote are where the executor reads them, the owner order is the signed bytes and the
    source pins are the signed constant (both hashed again on the host)."""
    day=checks.held['DAY'];names=('OWNER_ORDER.json','SOURCE_PINS.json','list.private.json','HOST_PLAN.json','GO.json')
    if not all(text(outputs.get('day/risk/plan/'+name),HEX64) for name in names):return False
    if outputs['day/risk/plan/OWNER_ORDER.json']!=plan['bind']['owner_order_sha256']:return False
    if outputs['day/risk/plan/SOURCE_PINS.json']!=plan['constants']['risk_source_pins_sha256']:return False
    for name in ('OWNER_ORDER.json','HOST_PLAN.json','GO.json'):
        found=k9w_maybe(checks.host,day.fd,['risk','plan',name],checks.gate,K9W_MAX_PLAN_FILE)
        if found is None or sha(found[0])!=outputs['day/risk/plan/'+name]:return False
    return k9w_lexists(checks.host,day.fd,['risk','spool'],checks.gate)

def k9w_stage_outputs(plan,checks,outputs):
    """stage: components/<D>/risk.json in the source root is the execute receipt's risk.json, hashed again."""
    key='source/components/'+plan['day']+'/risk.json';expected=(checks.predecessors.get('execute') or {}).get('outputs') or {}
    if outputs.get(key) is None or outputs.get(key)!=expected.get('risk_sha256'):return False
    source=checks.held['SOURCE_ROOT'];source.verify(checks.gate)
    found=k9w_maybe(checks.host,source.fd,['components',plan['day'],'risk.json'],checks.gate,K9W_MAX_PLAN_FILE)
    return found is not None and sha(found[0])==outputs[key]
# ==== END OP_K9_PHASE_STEP ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
