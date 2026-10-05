"""OP_CAPACITY_SWITCH: the capacity mount, enable and disable of the compose worker r2d2-worker for epoch
R2D2-V2-SHADOW-2026-10-05, one signed mode per request (MOUNT, ENABLE, DISABLE_FAST, DISABLE_FULL), on a session day.

What c3po/deployment/capacity-mount/README.md at the release does by hand (step 1, step 3, fast and full disable),
in the HOSTOPS02 family and with the compose file list of the activation (K6a): the compose file of the deploy plus
the override the activation delivered, so that a recreate keeps the release and live-policy pins. Under the
deployment lock it edits the environment file of the project in place through one attached container of the signed
backend image, run as the account that owns that file, with no network, a read-only root and that one file bound
read-write: the trailing block of capacity settings is appended to or cut, every other byte stays as it was. It then
renders the project from the edited file and recreates that one service. Everything is looked at before the first
effect: the executor, the boot of the evidence, the deploy tree, the deployed revision, the environment file (in
memory only) and the block it holds, the compose file, the override (compared with the four signed values), the
capacity tree and its static config (MOUNT and ENABLE), the worker, its image, its environment (booleans), its mounts,
the render, the lock (waited for at most the signed seconds and never past the point where both effects would no
longer fit), and under it: no security reboot pending, every held directory still reached by its name, nothing
changed since the first look, no container left by an interrupted recreate of the service. Every effect is read back
inside the run. When the render after the edit is not as signed, the edit is withdrawn by the same editor and the
worker is not recreated. It never runs docker exec, a shell, a systemctl verb or a pull, never writes the capacity
tree, and prints no value it read from an environment, from the render or from the environment file. A run that
changed anything and did not finish is PARTIAL, never a refusal, and says which of its effects exist. The caller
authenticates exact request/authority/GO/source bytes first. No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='4bb3b3babd292096893fceb335cb4fb8f85fd4c38117e30d779da8669d26c10e'
CORE_PARTS={'core': '60e29427f42b500642fdf57568843d63f2437714c899d61d88bcee05e63ecd6b', 'runner': '2a1cc5bc73a0d456eb596aea65caaffcf7dd3834cbbd844a02a69486bbdacaa7', 'docker': '4602f6f07a4502a3decec99cd415737efb429e3b1a188b368939a090bc3b3aa5', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'files': '6b96ad64fe8ce5a9a2293b109964e069c2ad32169e7d421449da3f88516b60ba', 'lock': '17099e318c9f7df61b570563fba45868ff6e0b884120265a01572bcb7d2ef554'}
# ==== END SEAL ====

# ==== BEGIN CORE (shared part, byte-identical in every source that carries it) ====
import ctypes
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


# ---------------------------------------------------------------- the process: no core dump of it
# prctl(2) options (<linux/prctl.h>). A process whose dumpable attribute is 0 produces no core dump on a signal whose
# default action is to dump core: the kernel's do_coredump() returns before it formats kernel.core_pattern when the
# memory of the process is not dumpable, so neither a file nor a pipe to a crash collector receives any of it.
# RLIMIT_CORE is not relied on (a pipe ignores it). The token family's revision of the core (CORE.md section 14).
PR_GET_DUMPABLE=3
PR_SET_DUMPABLE=4
def dumps_disabled(library=None):
    """Makes the calling process non-dumpable and proves it: prctl(PR_SET_DUMPABLE, 0) must return 0, and then
    prctl(PR_GET_DUMPABLE) must answer 0 (the second call is made only when the first returned 0). Returns True, or
    raises Refused('PROCESS_DUMPABLE_NOT_DISABLED') whatever failed: the C library cannot be loaded or has no prctl, a
    call returned anything else, a call raised. library: None for the C library of this interpreter, loaded here as
    ctypes.CDLL(None, use_errno=True) and never handed out; a stand-in with the same prctl in the tests. The attribute
    stays 0 for the rest of the process: only an exec or a change of credentials sets it again, and a source does neither
    (a command of the runner is a process of its own)."""
    try:
        if library is None:library=ctypes.CDLL(None,use_errno=True)
        disabled=library.prctl(PR_SET_DUMPABLE,0,0,0,0)==0 and library.prctl(PR_GET_DUMPABLE,0,0,0,0)==0
    except Exception:disabled=False
    need(disabled,'PROCESS_DUMPABLE_NOT_DISABLED');return True


class NativeRead:
    """Read-only host primitives shared by every source. A source's own Native adds only what its operation needs."""
    def identity(self):return os.geteuid(),os.getegid()
    def not_dumpable(self):return dumps_disabled()          # the process itself, not the host: no core dump of it from here on
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

# ==== BEGIN LOCK (shared part, byte-identical in every source that carries it) ====
import fcntl

# The deployment lock of this host is an advisory flock on one file of the deploy tree; the pipeline's deploy job and
# the security controller take it exclusively before they touch the compose project. A run that recreates a
# container holds it for the time of the effect; a read-only run may only ask whether it is free.
LOCK_POLL_SECONDS=.25
MAX_LOCK_WAIT_SECONDS=20
LOCK_SCOPE={'kind':'flock on a descriptor opened read-only and without following a link; the file is never created, written or removed',
            'max_wait_seconds':MAX_LOCK_WAIT_SECONDS,'poll_seconds':LOCK_POLL_SECONDS,
            'released':'explicitly, and in any case when the process ends',
            'probe':'a shared, non-blocking request released at once: it fails only while another process holds the lock exclusively; '
                    'for that instant a non-blocking exclusive request of another process fails as well'}

class NativeLock:
    """The two calls of the lock: a non-blocking flock on a held descriptor, and the pause between two attempts."""
    def flock(self,fd,operation):fcntl.flock(fd,operation)
    def pause(self,seconds):time.sleep(seconds)

def open_lock(host,name,directory,check):
    """The lock file, opened read-only by dir_fd without following a link: a regular file with one link that the name
    still shows. Returns the descriptor. The file is never created here: an absent lock file is a refusal."""
    check()
    try:named=host.lstat(name,directory.fd)
    except FileNotFoundError:raise Refused('LOCK_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode) and named.st_nlink==1,'LOCK_FILE_NOT_REGULAR')
    check();fd=host.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory.fd)
    try:
        held=host.fstat(fd)
        need(stat.S_ISREG(held.st_mode) and (held.st_dev,held.st_ino)==(named.st_dev,named.st_ino),'LOCK_FILE_REPLACED')
        return fd
    except BaseException:
        host.close(fd);raise

def lock_still_named(host,name,directory,fd):
    """True while the name still shows the file whose descriptor holds the lock (a lock on a replaced file excludes nobody)."""
    try:
        named=host.lstat(name,directory.fd);held=host.fstat(fd)
        return bool(stat.S_ISREG(named.st_mode) and (named.st_dev,named.st_ino)==(held.st_dev,held.st_ino))
    except OSError:return False

def acquire_lock(host,fd,gate,wait_seconds,keep_seconds):
    """Exclusive lock, asked for without blocking and again every LOCK_POLL_SECONDS. It gives up, with nothing
    changed, after wait_seconds or as soon as less than keep_seconds of the budget would be left for what the lock
    is taken for. Returns the number of attempts. Taking the lock changes nothing on disk; the caller releases it."""
    need(integer(wait_seconds,0,MAX_LOCK_WAIT_SECONDS) and integer(keep_seconds,0,MAX_SECONDS),'LOCK_WAIT_INVALID')
    budget=gate();need(budget>keep_seconds,'LOCK_NOT_TAKEN_BUDGET')
    limit=budget-min(wait_seconds,budget-keep_seconds);attempts=0;most=int(wait_seconds/LOCK_POLL_SECONDS)+1
    while True:
        attempts+=1
        try:host.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return attempts
        except OSError as error:
            need(error.errno in (errno.EWOULDBLOCK,errno.EAGAIN,errno.EACCES),'LOCK_UNAVAILABLE')
        # The budget only falls: once another pause would take it to the limit, the wait is over. The number of
        # attempts is bounded as well, so a clock that stands still cannot make the wait endless.
        need(attempts<most and gate()-LOCK_POLL_SECONDS>limit,'DEPLOY_LOCK_BUSY')
        host.pause(LOCK_POLL_SECONDS)

def release_lock(host,fd):
    """Unlock and close. Never raises: the lock ends with the descriptor in any case."""
    try:host.flock(fd,fcntl.LOCK_UN)
    except Exception:pass
    try:host.close(fd)
    except Exception:pass

def probe_lock(host,fd):
    """'FREE' or 'BUSY': a shared, non-blocking request, released at once. For a source that changes nothing."""
    try:host.flock(fd,fcntl.LOCK_SH|fcntl.LOCK_NB)
    except OSError as error:
        need(error.errno in (errno.EWOULDBLOCK,errno.EAGAIN,errno.EACCES),'LOCK_UNAVAILABLE')
        return 'BUSY'
    host.flock(fd,fcntl.LOCK_UN);return 'FREE'
# ==== END LOCK ====

# ==== BEGIN OP_CAPACITY_SWITCH (this operation only) ====
OPERATION='GO_WRITE_HOSTOPS02_CAPACITY_SWITCH_01'
PHASE='WRITE_CAPACITY_SWITCH_ENV_FILE_AND_RECREATE_WORKER'
REQUEST_SCHEMA='WRITE_HOSTOPS02_CAPACITY_SWITCH_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_CAPACITY_SWITCH_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_CAPACITY_SWITCH_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_CAPACITY_SWITCH_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_CAPACITY_SWITCH_PLAN_V1'
SOURCE_NAME='capacity_switch.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False                  # no systemd unit is switched: an edit of the environment file and the recreate of a compose service
DATE_CLASS='WRITE_SESSIONS'               # 10-05 .. 10-10 UTC: mount/enable Mon-Thu after the close, fast disable Mon-Fri, full disable Fri
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_WRITE_HOSTOPS02_ACTIVATE_01',)                 # M3's receipt: the override file this run renders and recreates with (decision C-13)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='CAPACITY_SWITCH_APPLIED_WORKER_RECREATED_AND_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
# the partial outcomes of a run that returned its own receipt (PARTIAL_OUTCOME itself is what an escaped run says)
# a stop BEFORE the recreate was started, and a stop AFTER it was started, are separate states (Codex decision 1)
ENV_ONLY_OUTCOME='PARTIAL_ENV_FILE_EDITED_RECREATE_NOT_STARTED'
WITHDRAWN_OUTCOME='PARTIAL_ENV_EDIT_WITHDRAWN_RECREATE_NOT_STARTED'
RECREATE_FAILED_OUTCOME='PARTIAL_ENV_FILE_EDITED_RECREATE_FAILED_WORKER_UNCHANGED'
NOT_VERIFIED_OUTCOME='PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED'
UNCERTAIN_OUTCOME='PARTIAL_UNCERTAIN_REQUIRES_READBACK'

# ---------------------------------------------------------------- the epoch and the deploy layout, as K6a signs them
EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'                                                        # r2d2_v2_epoch_assembler.py:9
EPOCH_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'                                     # .deploy-version and C3PO_BUILD_SHA
WORKER_SERVICE='r2d2-worker'
BUILD_KEY='C3PO_BUILD_SHA'
ACTIVATION_KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')
ENV_FILE_NAME='.env'
COMPOSE_FILE_NAME='compose.yml'
DEPLOY_VERSION_NAME='.deploy-version'
LOCK_RELATIVE_DIRECTORY='runtime/security'
LOCK_FILE_NAME='deployment.lock'
REBOOT_PENDING_PATH='/run/c3po-security/reboot.pending'
MAX_ENV_FILE_BYTES=1048576
MAX_COMPOSE_FILE_BYTES=1048576
MAX_OVERRIDE_BYTES=4096
MAX_CONFIG_BYTES=1048576
# ---------------------------------------------------------------- the capacity settings (c3po/deployment/capacity-mount/README.md at the release)
KEY_MOUNT_SOURCE='C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE'                                         # read by compose only: compose.yml:169
KEY_CONFIG_FILE='C3PO_R2D2_V2_CAPACITY_CONFIG_FILE'                                           # config.py:201
KEY_CONFIG_SHA='C3PO_R2D2_V2_CAPACITY_CONFIG_SHA'                                             # config.py:202
KEY_VETO_MODE='C3PO_R2D2_V2_CAPACITY_VETO_MODE'                                               # config.py:200
KEY_REQUIRED='C3PO_R2D2_V2_CAPACITY_REQUIRED'                                                 # config.py:199
CAPACITY_KEYS=(KEY_MOUNT_SOURCE,KEY_CONFIG_FILE,KEY_CONFIG_SHA,KEY_VETO_MODE,KEY_REQUIRED)    # the order of the trailing block this source keeps in .env
VETO_MODE_VALUE='DISPATCH_AND_DERIVATION_ONLY'
REQUIRED_VALUE='true'
CAPACITY_TARGET='/c3po-capacity'
CAPACITY_SUBDIRECTORIES=('config','documents','go','payload')
PLACEHOLDER_VOLUME='c3po_capacity_unprovisioned'
DATA_TARGET='/app/day-d-data'
WORKER_TARGETS=('/app/day-d-data','/c3po-capacity','/run/c3po-maintenance')                  # check_compose_render.py:26
CAPACITY_LINE=re.compile(b'[ \t]*(?:export[ \t]+)?C3PO_R2D2_V2_CAPACITY_')                    # any line compose's dotenv parser could read as a capacity setting
# ---------------------------------------------------------------- the four modes: how many lines of the block exist before and after
MODES={'MOUNT':{'before':(0,),'after':1},'ENABLE':{'before':(1,),'after':5},
       'DISABLE_FAST':{'before':(5,),'after':4},'DISABLE_FULL':{'before':(1,4,5),'after':0}}
# ---------------------------------------------------------------- the editor of the environment file: one attached container
ENV_OWNER=(1000,1000)                     # the operational account that owns .env (the deploy writes it); the editor runs as that account, never as root
ENV_MODE=0o600
ENV_EDITOR_TARGET='/c3po-env/.env'
ENV_EDITOR_COMMAND=['python','-I','-B','-']
ENV_EDITOR_PREFIX=['run','--rm','-i','--pull','never','--init','--user','%d:%d'%ENV_OWNER,'--network','none','--read-only','--cap-drop','ALL',
                   '--security-opt','no-new-privileges']
ENV_EDIT_SCRIPT='''import ctypes,json,os,re,stat,sys
TARGET='/c3po-env/.env'
CAPACITY=re.compile(b'[ \\t]*(?:export[ \\t]+)?C3PO_R2D2_V2_CAPACITY_')
LIMIT=1048576
class Stop(Exception):pass
def not_dumpable():
    try:
        library=ctypes.CDLL(None,use_errno=True)
        return library.prctl(4,0,0,0,0)==0 and library.prctl(3,0,0,0,0)==0
    except Exception:return False
def say(status,code=None):
    sys.stdout.write(json.dumps({'code':code,'status':status},sort_keys=True)+'\\n');sys.stdout.flush()
def read_all(fd,size):
    chunks=[];offset=0
    while offset<=size:
        block=os.pread(fd,65536,offset)
        if not block:break
        chunks.append(block);offset+=len(block)
    return b''.join(chunks)
def edited(raw,spec):
    if raw!=b'' and not raw.endswith(b'\\n'):raise Stop('ENV_FILE_NOT_NEWLINE_TERMINATED')
    lines=raw[:-1].split(b'\\n') if raw else []
    marks=[index for index,line in enumerate(lines) if CAPACITY.match(line)]
    count=len(marks);head=lines[:len(lines)-count]
    if marks!=list(range(len(lines)-count,len(lines))):raise Stop('ENV_CAPACITY_LINES_NOT_TRAILING')
    if [line.decode('latin-1') for line in lines[len(lines)-count:]] not in spec['before']:raise Stop('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED')
    return b''.join(line+b'\\n' for line in head)+b''.join(line.encode('ascii')+b'\\n' for line in spec['after'])
def main(spec):
    wrote=False
    try:
        if not not_dumpable():raise Stop('EDITOR_DUMPABLE_NOT_DISABLED')
        try:fd=os.open(TARGET,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
        except OSError:raise Stop('ENV_FILE_OPEN')
        try:
            info=os.fstat(fd)
            if not (stat.S_ISREG(info.st_mode) and info.st_nlink==1 and [info.st_uid,info.st_gid]==spec['owner']
                    and stat.S_IMODE(info.st_mode)==spec['mode'] and info.st_size<=LIMIT):raise Stop('ENV_FILE_NOT_AS_EXPECTED')
            raw=read_all(fd,info.st_size)
            if len(raw)!=info.st_size:raise Stop('ENV_FILE_CHANGED_DURING_READ')
            new=edited(raw,spec)
            again=os.fstat(fd)
            if (again.st_size,again.st_mtime_ns,again.st_ino)!=(info.st_size,info.st_mtime_ns,info.st_ino) or read_all(fd,info.st_size)!=raw:
                raise Stop('ENV_FILE_CHANGED_DURING_THE_EDIT')
            if len(new)>len(raw) and new[:len(raw)]==raw:
                data=new[len(raw):];wrote=True;written=os.pwrite(fd,data,len(raw))
                if written!=len(data):
                    os.ftruncate(fd,len(raw));os.fsync(fd);say('ENV_EDIT_FAILED','ENV_SHORT_WRITE_WITHDRAWN');return 3
            elif len(new)<len(raw) and raw[:len(new)]==new:
                wrote=True;os.ftruncate(fd,len(new))
            else:raise Stop('ENV_EDIT_NOT_AN_APPEND_OR_A_CUT')
            os.fsync(fd)
            say('ENV_EDIT_DONE');return 0
        finally:os.close(fd)
    except Stop as error:
        say('ENV_EDIT_REFUSED',str(error));return 1
    except Exception:
        if wrote:say('ENV_EDIT_FAILED','ENV_EDIT_OS_ERROR');return 3
        say('ENV_EDIT_REFUSED','ENV_EDIT_OS_ERROR');return 1
'''
ENV_EDIT_SCRIPT_SHA256=sha(ENV_EDIT_SCRIPT.encode('ascii'))
ENV_EDIT_STATUSES=('ENV_EDIT_DONE','ENV_EDIT_REFUSED','ENV_EDIT_FAILED')
# The source's own process, first of all (as the token program, core section 14): the core's NativeRead.not_dumpable()
# sets the dumpable attribute to 0 and reads it back 0 (prctl(2)) before the deploy tree or .env is opened; the editor's
# process does the same before it opens the file. A process that is not dumpable produces no core dump, to a file or
# through a pipe to a crash collector. Otherwise: refused, nothing changed.
PROCESS_SCOPE={'dumpable':0,'how':'prctl(PR_SET_DUMPABLE, 0), then prctl(PR_GET_DUMPABLE) must answer 0 (the core\'s dumps_disabled)',
               'when':'first, before the deploy directory, the environment file or anything else is opened',
               'editor':'the editor container\'s process makes itself non-dumpable the same way before it opens the file; otherwise EDITOR_DUMPABLE_NOT_DISABLED, nothing written',
               'bytes_of_the_file':'held only in the memory of those two processes; no byte outside the trailing capacity block is written back; no copy, log, argv or output',
               'otherwise':'refused, nothing changed: PROCESS_DUMPABLE_NOT_DISABLED'}
MOUNTS_FORMAT='{{json .Mounts}}'
MAX_MOUNTS_LISTED=32
# ---------------------------------------------------------------- the budget (seconds of the 60 a run has)
SETTLE_SECONDS=3                          # the one fixed pause, between the two readings of the new worker (as K6a)
SECOND_CHECK_RESERVE_SECONDS=2
FILES_ALLOWANCE_SECONDS=1                 # the readbacks of the environment file between the effects
UNDER_LOCK_ALLOWANCE_SECONDS=2
RENDER_ALLOWANCE_FLOOR_SECONDS=3

PLAN_KEYS=frozenset(('mode','data_root','capacity','override','worker','compose','deploy_directory','lock','probe_load_receipt_sha256','withdrawal_authorized',
                     'evidence_boot_id_sha256'))
CAPACITY_KEYS_OF_PLAN=frozenset(('root','config_name','config_sha256'))
OVERRIDE_KEYS=frozenset(('directory','name','environment'))
WORKER_KEYS=frozenset(('image_id',))
COMPOSE_KEYS=frozenset(('project','env_file','files'))
LOCK_KEYS=frozenset(('directory','wait_seconds'))
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then one container ID','QUICK','READ'),
          'container_mounts':command_row('docker',['container','inspect','--format',MOUNTS_FORMAT],'one container ID','QUICK','READ'),
          'render_files':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL),
          'edit_env':command_row('docker',ENV_EDITOR_PREFIX,'one read-write bind of the environment file at '+ENV_EDITOR_TARGET+', the image ID, python -I -B -','QUICK','EFFECT',stdin=True),
          'recreate':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RECREATE','EFFECT',tail=compose_up_tail(WORKER_SERVICE))}
SUCCESS_CRITERIA=['the environment file is the same object (device, inode, owner, mode, one link) holding exactly the signed edit of its bytes: the trailing capacity block replaced by the signed one, every other byte as it was',
                  'the render from the edited file gives the worker the capacity mount and the capacity names of the mode, the four names of the activation and the build revision',
                  'the recreate command returned 0',
                  'exactly one container carries the name of the service and it is not the container that was there before; that one no longer exists under any name',
                  'the new container is running with restart count 0 on the signed image, read twice with a fixed pause between; the second reading shows the same container and the same start instant',
                  'its environment carries the names of the mode with the signed values and lacks the others, compared inside a docker template that prints booleans',
                  'its mount at /c3po-capacity is the one of the mode (the read-only bind of the signed tree, or the placeholder volume) and the data root is still bound',
                  'every other container is listed with the ID and the name it had under the lock before the recreate, and no other container appeared',
                  'the compose file and the override file are the same objects with the same bytes as at the first look; the lock file is still the one held']
SCOPE_STATEMENT=('Epoch R2D2-V2-SHADOW-2026-10-05, session days 2026-10-05 to 2026-10-10 UTC. One signed mode per request: MOUNT, ENABLE, '
                 'DISABLE_FAST or DISABLE_FULL of the capacity of the compose service r2d2-worker. Under the deployment lock: edits the '
                 'environment file of the compose project in place, through one attached container of the signed backend image run as the '
                 'account that owns that file, with no network, a read-only root and that one file bound read-write, which appends or cuts '
                 'the trailing block of capacity settings and nothing else; then renders the project with the compose file of the deploy '
                 'plus the override file of the activation, and recreates that one service with the same file list: one docker compose up '
                 '-d --no-deps --no-build --pull never --force-recreate. The running worker container is stopped and replaced. Rule 4 of '
                 'the core (nothing that exists is overwritten) is NOT preserved: the environment file is edited in place under the one '
                 'exception of this core generation (IN_PLACE_EDIT_EXCEPTION). Only when the request authorizes it, and only when the run '
                 'stops BEFORE the recreate was started, after an edit that was confirmed and read back, with the lock still held, the edit '
                 'is withdrawn by a second run of the same editor; never after the recreate was started. No other file, container, image or unit is changed; the '
                 'capacity tree is read, never written. No docker exec, no shell, no systemctl, no pull. No value of an environment, of the '
                 'render or of the environment file is printed, stored or put in an argv, with three exceptions that are not values of '
                 'the environment: the image reference the render names and the container IDs the engine prints are passed to docker '
                 'inspect, and the receipt says which of the signed capacity blocks the environment file held. The signed capacity values '
                 'travel on the standard input of the editor and, with the four values of the activation and the build revision, in the '
                 'argv of the docker template that compares them.')

def capacity_root_path(plan):return plan['capacity']['root'][-1]['path']
def config_container_path(plan):return CAPACITY_TARGET+'/config/'+plan['capacity']['config_name']
def capacity_values(plan):
    """The five values of the block, in its order; nothing is free: each follows from a signed member or is a constant."""
    return {KEY_MOUNT_SOURCE:capacity_root_path(plan),KEY_CONFIG_FILE:config_container_path(plan),KEY_CONFIG_SHA:plan['capacity']['config_sha256'],
            KEY_VETO_MODE:VETO_MODE_VALUE,KEY_REQUIRED:REQUIRED_VALUE}
def block_lines(plan,count):
    values=capacity_values(plan);return ['%s=%s'%(key,values[key]) for key in CAPACITY_KEYS[:count]]
def edit_spec(plan,before_counts=None,after_count=None):
    mode=MODES[plan['mode']]
    before=mode['before'] if before_counts is None else before_counts;after=mode['after'] if after_count is None else after_count
    return {'before':[block_lines(plan,count) for count in before],'after':block_lines(plan,after),'owner':list(ENV_OWNER),'mode':ENV_MODE}
def editor_stdin(spec):
    """The bytes the editor runs: the pinned script, then one line that calls it with the spec as a JSON text. The spec
    holds signed values only (paths, a hash, constants): nothing of the environment file is in it."""
    return (ENV_EDIT_SCRIPT+'raise SystemExit(main(json.loads(%s)))\n'%json.dumps(json.dumps(spec,sort_keys=True,separators=(',',':')))).encode('ascii')
def editor_name(bound):return 'hostops02-k6b-'+bound['go_sha256'][:16]
def editor_mounts(plan):return [{'source':plan['compose']['env_file'],'target':ENV_EDITOR_TARGET,'read_only':False}]
def override_path(plan):return plan['override']['directory'][-1]['path']+'/'+plan['override']['name']
def override_bytes(plan):
    """The override of the activation exactly as K6a writes it (activate/op.py override_of): the four signed values."""
    return json.dumps({'services':{WORKER_SERVICE:{'environment':dict(plan['override']['environment'])}}},sort_keys=True).encode('ascii')
def deploy_path(plan):return plan['deploy_directory'][-1]['path']
def lock_path(plan):return plan['lock']['directory'][-1]['path']+'/'+LOCK_FILE_NAME
def worker_name(plan):return '%s-%s-1'%(plan['compose']['project'],WORKER_SERVICE)
def file_list(plan):return plan['compose']['files']+[override_path(plan)]
def expected_environment(plan,count):
    """{name: value} compared in the worker; the names of the block beyond count must be absent."""
    values=dict(plan['override']['environment']);values[BUILD_KEY]=EPOCH_REVISION;values.update(capacity_values(plan))
    return values
def present_names(plan,count):return set(ACTIVATION_KEYS)|{BUILD_KEY}|set(CAPACITY_KEYS[:count])
def placeholder_name(plan):return plan['compose']['project']+'_'+PLACEHOLDER_VOLUME

def chain_path(rows):
    need(type(rows) is list and rows and type(rows[-1]) is dict,'CHAIN_ROW_INVALID');return rows[-1].get('path')     # its spelling: validate_chain
def signed_chain(rows,open_root,receives_entry=False):return validate_chain(rows,chain_path(rows),open_root,receives_entry)

def validate_plan(plan):
    need(plan['mode'] in MODES,'MODE_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    root=plan['data_root']                                    # its spelling is judged by validate_chain as an open root (PATH_INVALID)
    capacity=plan['capacity']
    need(type(capacity) is dict and set(capacity)==set(CAPACITY_KEYS_OF_PLAN) and text(capacity['config_name'],FILE_NAME)
         and hexpin(capacity['config_sha256']),'CAPACITY_REQUEST_INVALID')
    tree=chain_path(capacity['root']);signed_chain(capacity['root'],None)          # root-owned from '/', not writable by group or other
    need(text(tree,MOUNT_PATH),'CAPACITY_REQUEST_INVALID')
    override=plan['override']
    need(type(override) is dict and set(override)==set(OVERRIDE_KEYS) and text(override['name'],FILE_NAME) and type(override['environment']) is dict
         and set(override['environment'])==set(ACTIVATION_KEYS),'OVERRIDE_REQUEST_INVALID')
    signed_chain(override['directory'],root)
    need(inside(chain_path(override['directory']),root) and chain_path(override['directory'])!=root,'OVERRIDE_OUTSIDE_DATA_ROOT')
    worker=plan['worker']
    need(type(worker) is dict and set(worker)==set(WORKER_KEYS) and text(worker['image_id'],IMAGE_ID),'WORKER_REQUEST_INVALID')
    compose=plan['compose']
    need(type(compose) is dict and set(compose)==set(COMPOSE_KEYS),'COMPOSE_REQUEST_INVALID')
    compose_arguments(compose['project'],compose['env_file'],file_list(plan))
    deploy=chain_path(plan['deploy_directory']);signed_chain(plan['deploy_directory'],deploy)
    need(compose['env_file']==deploy+'/'+ENV_FILE_NAME and compose['files']==[deploy+'/'+compose['project']+'/'+COMPOSE_FILE_NAME],'COMPOSE_NOT_THE_DEPLOY_LAYOUT')
    need(not inside(root,deploy) and not inside(deploy,root),'PATHS_OVERLAP')
    # the tree must lie neither in the data volume (three services reach it read-write there) nor in the deploy tree (the next rsync removes it)
    need(not inside(tree,root) and not inside(root,tree) and not inside(tree,deploy) and not inside(deploy,tree),'CAPACITY_TREE_PLACEMENT')
    lock=plan['lock']
    need(type(lock) is dict and set(lock)==set(LOCK_KEYS) and integer(lock['wait_seconds'],0,MAX_LOCK_WAIT_SECONDS),'LOCK_REQUEST_INVALID')
    signed_chain(lock['directory'],deploy)
    need(lock['directory'][-1]['path']==deploy+'/'+LOCK_RELATIVE_DIRECTORY,'LOCK_NOT_THE_DEPLOYMENT_LOCK')
    need(hexpin(plan['probe_load_receipt_sha256']) if plan['mode']=='ENABLE' else plan['probe_load_receipt_sha256'] is None,'LOAD_EVIDENCE_INVALID')
    need(type(plan['withdrawal_authorized']) is bool,'WITHDRAWAL_REQUEST_INVALID')
    environment_format(expected_environment(plan,5))                         # every value fits the grammar of the template
    run_arguments('edit_env',worker['image_id'],editor_mounts(plan),ENV_EDITOR_COMMAND)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    mode=MODES[plan['mode']];compose=plan['compose'];stdin=editor_stdin(edit_spec(plan));overrides=override_bytes(plan)
    after=mode['after'];values=capacity_values(plan)
    return {'operation':OPERATION,'mode':plan['mode'],'epoch':EPOCH_NAME,'revision':EPOCH_REVISION,
            'environment_file':{'path':compose['env_file'],'owner':list(ENV_OWNER),'mode_octal':'%04o'%ENV_MODE,
                                'trailing_capacity_block_before_one_of':[block_lines(plan,count) for count in mode['before']],
                                'trailing_capacity_block_after':block_lines(plan,after),
                                'rule':'no capacity line outside the trailing block; every other byte unchanged; same object'},
            'editor':{'row':'edit_env','argv_prefix':ENV_EDITOR_PREFIX,'image_id':plan['worker']['image_id'],'mounts':editor_mounts(plan),
                      'command':ENV_EDITOR_COMMAND,'script_sha256':ENV_EDIT_SCRIPT_SHA256,'stdin_sha256':sha(stdin),'stdin_bytes':len(stdin),
                      'container_name':'hostops02-k6b-<first 16 hex of the GO hash>[-withdraw]'},
            'withdrawal':{'authorized':plan['withdrawal_authorized'],'row':'edit_env','container_name':'hostops02-k6b-<first 16 hex of the GO hash>-withdraw',
                          'stdin_sha256_by_block_found':({str(count):sha(editor_stdin(edit_spec(plan,(after,),count))) for count in mode['before']}
                                                         if plan['withdrawal_authorized'] else {}),
                          'when':'only if authorized here; only BEFORE the recreate is started, after an edit the editor confirmed and the host read back, '
                                 'while the lock file is still the one held; never after the recreate was started, whatever it did',
                          'effect':'the inverse edit of E1, by the same row: the trailing block found before is put back; every other byte unchanged'},
            'process':{'dumpable':0,'when':'first, before the deploy directory or the environment file is opened; the editor before it opens the file',
                       'core_dump':'none, to a file or through a pipe'},
            'core_exception':{'rule_4_preserved':False,'core_sha256':CORE_SHA256,'exception':'IN_PLACE_EDIT_EXCEPTION of this core generation: row edit_env of '
                              'source capacity_switch edits <deploy>/.env in place (append to, or cut the end of, the trailing capacity block)'},
            'bind_source_chain':{'rows':[{key:row[key] for key in ('path','uid','gid','mode')} for row in plan['deploy_directory']]+
                                        [{'path':compose['env_file'],'uid':ENV_OWNER[0],'gid':ENV_OWNER[1],'mode':ENV_MODE}],
                                 'all_root_controlled':all(row['uid']==0 for row in plan['deploy_directory']) and ENV_OWNER[0]==0,
                                 'note':'decision 6 asks every bind source and its ancestors to be root-controlled; this one is not (open item)'},
            'override':{'path':override_path(plan),'sha256':sha(overrides),'bytes':len(overrides),'directory':chain_effects(plan['override']['directory']),
                        'environment':dict(plan['override']['environment']),'expect':'DELIVERED_BY_THE_ACTIVATION_READ_AND_COMPARED_NEVER_WRITTEN'},
            'capacity_tree':{'host_path':capacity_root_path(plan),'root':chain_effects(plan['capacity']['root']),'container_target':CAPACITY_TARGET,
                             'config_file':config_container_path(plan),'config_sha256':plan['capacity']['config_sha256'],
                             'read':plan['mode'] in ('MOUNT','ENABLE'),'expect':'READ_NEVER_WRITTEN'},
            'recreate':{'project':compose['project'],'env_file':compose['env_file'],'files':file_list(plan),'service':WORKER_SERVICE,
                        'container':worker_name(plan),'image_id':plan['worker']['image_id'],'build_sha':EPOCH_REVISION,
                        'lock':lock_path(plan),'lock_wait_seconds':plan['lock']['wait_seconds'],'lock_chain_sha256':sha(canonical(plan['lock']['directory'])),
                        'deploy_directory':chain_effects(plan['deploy_directory'])},
            'worker_after':{'environment_present':{key:values[key] for key in CAPACITY_KEYS[:after]},'environment_absent':list(CAPACITY_KEYS[after:]),
                            'activation_environment':dict(plan['override']['environment']),
                            'capacity_mount':({'type':'bind','source':capacity_root_path(plan),'target':CAPACITY_TARGET,'read_only':True} if after
                                              else {'type':'volume','name':placeholder_name(plan),'target':CAPACITY_TARGET,'read_only':True}),
                            'data_mount':{'type':'bind','source':plan['data_root'],'target':DATA_TARGET}},
            'required':{'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':EPOCH_REVISION,
                        'probe_load_receipt_sha256':plan['probe_load_receipt_sha256'],
                        'worker_running_before':plan['mode'] in ('MOUNT','ENABLE')},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':'THE_ENVIRONMENT_FILE_IS_EDITED_IN_PLACE_AND_THE_WORKER_CONTAINER_IS_REPLACED','activation':False}
def success_of(plan):return COMPLETE_OUTCOME

SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'modes':MODES,'capacity_keys_in_block_order':list(CAPACITY_KEYS),'veto_mode':VETO_MODE_VALUE,'required_value':REQUIRED_VALUE,
       'capacity_target':CAPACITY_TARGET,'capacity_subdirectories':list(CAPACITY_SUBDIRECTORIES),'placeholder_volume':PLACEHOLDER_VOLUME,
       'worker_targets':list(WORKER_TARGETS),'data_target':DATA_TARGET,
       'editor':{'owner':list(ENV_OWNER),'mode':ENV_MODE,'target':ENV_EDITOR_TARGET,'command':ENV_EDITOR_COMMAND,'script_sha256':ENV_EDIT_SCRIPT_SHA256,
                 'statuses':list(ENV_EDIT_STATUSES)},
       'mounts_format':MOUNTS_FORMAT,'process':PROCESS_SCOPE,
       'budget':{'settle_seconds':SETTLE_SECONDS,'second_check_reserve_seconds':SECOND_CHECK_RESERVE_SECONDS,'files_allowance_seconds':FILES_ALLOWANCE_SECONDS,
                 'under_lock_allowance_seconds':UNDER_LOCK_ALLOWANCE_SECONDS,'render_allowance_floor_seconds':RENDER_ALLOWANCE_FLOOR_SECONDS,
                 'rule':'before the lock is asked for and again before the first effect: edit class + recreate class + reserve + render allowance + files + settle must be left'},
       'files':FILES_SCOPE,'lock':LOCK_SCOPE,'service':WORKER_SERVICE,'activation_names':list(ACTIVATION_KEYS),'build_name':BUILD_KEY,
       'epoch':{'name':EPOCH_NAME,'revision':EPOCH_REVISION},
       'deploy_layout':{'environment_file':ENV_FILE_NAME,'compose_file':'<project>/'+COMPOSE_FILE_NAME,'deploy_version':DEPLOY_VERSION_NAME,
                        'lock':LOCK_RELATIVE_DIRECTORY+'/'+LOCK_FILE_NAME},
       'success_criteria':SUCCESS_CRITERIA,
       'partial_outcomes':[ENV_ONLY_OUTCOME,WITHDRAWN_OUTCOME,RECREATE_FAILED_OUTCOME,NOT_VERIFIED_OUTCOME,UNCERTAIN_OUTCOME,PARTIAL_OUTCOME],
       'failure_phases':['BEFORE_THE_EDIT','BEFORE_THE_RECREATE','AFTER_THE_RECREATE_STARTED'],
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,DEPLOY_VERSION_NAME+' of the deploy tree',
                             'the environment file of the compose project: read into memory, edited only by the editor container, compared with the signed edit; no value, digest or size of it leaves the run',
                             'the compose file of the deploy: compared with itself, never judged as text (the render is)',
                             'the override file of the activation: compared with the four signed values',
                             'the static capacity config in the config directory of the tree (MOUNT, ENABLE): compared with the signed hash'],
       'side_effects':['the environment file of the compose project gains or loses the trailing capacity lines of the mode: every service that is created later from it (all six backend services) gets them',
                       'the worker container is stopped and replaced by a new one (new ID); what it held in memory is lost',
                       'the deployment lock is held from before the first effect until the last readback'],
       'never':['overwrite of any byte of the environment file that is not in the trailing capacity block','chmod','chown','rename','removal of any file',
                'docker exec','a shell','systemctl','a pull','a build','a second recreate','a change of the compose file, of the override or of the capacity tree',
                'a network connection opened by this process or by the editor'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'environment_file_bytes':MAX_ENV_FILE_BYTES,'compose_file_bytes':MAX_COMPOSE_FILE_BYTES,'override_bytes':MAX_OVERRIDE_BYTES,
                 'config_bytes':MAX_CONFIG_BYTES,'lock_wait_seconds':MAX_LOCK_WAIT_SECONDS,'mounts_listed':MAX_MOUNTS_LISTED}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles,NativeLock):
    """Everything this source can do to the host: the read primitives, the signed commands, the lock. Of the files
    part it uses the umask only: this source creates no file and no directory of its own."""


# ---------------------------------------------------------------- the environment file, in memory (pure)
def env_lines(raw):
    need(raw==b'' or raw.endswith(b'\n'),'ENV_FILE_NOT_NEWLINE_TERMINATED')
    return raw[:-1].split(b'\n') if raw else []
def edited_env(raw,spec):
    """(new bytes, the block found): the same rule the editor applies, computed here first and compared after. The
    capacity lines must be the trailing lines of the file and be exactly one of the signed blocks."""
    lines=env_lines(raw);marks=[index for index,line in enumerate(lines) if CAPACITY_LINE.match(line)]
    count=len(marks);head=lines[:len(lines)-count]
    need(marks==list(range(len(lines)-count,len(lines))),'ENV_CAPACITY_LINES_NOT_TRAILING')
    block=[line.decode('latin-1') for line in lines[len(lines)-count:]]
    need(block in spec['before'],'ENV_CAPACITY_BLOCK_NOT_AS_SIGNED')
    # the signed blocks are prefixes of one another: the result is always an append to the end or a cut of the end
    return b''.join(line+b'\n' for line in head)+b''.join(line.encode('ascii')+b'\n' for line in spec['after']),block


# ---------------------------------------------------------------- what is read on the host
def hold(host,fd,pinned,**how):
    try:holder=Pinned(host,fd,**how)
    except BaseException:
        host.close(fd);raise
    pinned.append(holder);return holder

def deploy_version(host,directory,gate):
    gate()
    try:named=host.lstat(DEPLOY_VERSION_NAME,directory.fd)
    except FileNotFoundError:raise Refused('DEPLOY_VERSION_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'DEPLOY_VERSION_NOT_REGULAR')
    raw,_=read_regular(host,DEPLOY_VERSION_NAME,directory.fd,gate,128)
    need(raw.strip()==EPOCH_REVISION.encode('ascii'),'DEPLOY_VERSION_MISMATCH')

def identity_of(info):
    """The object, without its content: what an in-place edit keeps (device, inode, owner, group, mode, links)."""
    return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)

def env_file_read(host,directory,gate):
    """(bytes, fstat) of the environment file: a regular file of the editor's account, mode 0600, one link. The bytes
    stay in memory: no value, digest or size of that file leaves the run."""
    gate()
    try:named=host.lstat(ENV_FILE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('ENV_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'ENV_FILE_NOT_REGULAR')
    return read_regular(host,ENV_FILE_NAME,directory.fd,gate,MAX_ENV_FILE_BYTES)

def project_directory(host,plan,deploy,gate,pinned):
    name=plan['compose']['project'];gate()
    try:named=host.lstat(name,deploy.fd)
    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None
    need(stat.S_ISDIR(named.st_mode),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=deploy.fd)
    return hold(host,fd,pinned,parent=deploy,name=name)      # proved again by name under the lock (DEPLOY_TREE_REPLACED)

def compose_file_state(host,directory,gate):
    gate()
    try:named=host.lstat(COMPOSE_FILE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'COMPOSE_FILE_NOT_REGULAR')
    raw,info=read_regular(host,COMPOSE_FILE_NAME,directory.fd,gate,MAX_COMPOSE_FILE_BYTES)
    return stat_signature(info),sha(raw)

def override_state(host,plan,directory,gate):
    """The override the activation delivered: root:root 0600, one link, exactly the bytes of the four signed values."""
    name=plan['override']['name'];gate()
    try:named=host.lstat(name,directory.fd)
    except FileNotFoundError:raise Refused('OVERRIDE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'OVERRIDE_NOT_AS_DELIVERED')            # never opened when it is not a regular file (a fifo would block)
    raw,info=read_regular(host,name,directory.fd,gate,MAX_OVERRIDE_BYTES)     # what was read is what is judged: its own fstat
    need(info.st_nlink==1 and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o600) and raw==override_bytes(plan),'OVERRIDE_NOT_AS_DELIVERED')
    return stat_signature(info)

def capacity_tree(host,plan,root,gate,pinned):
    """The tree the mount names: four root:root 0700 directories under the held root, on its device, never through a
    link; in config, the static config a regular root:root 0600 file of one link with the signed hash."""
    for name in CAPACITY_SUBDIRECTORIES:
        gate()
        try:named=host.lstat(name,root.fd)
        except FileNotFoundError:raise Refused('CAPACITY_TREE_INCOMPLETE') from None
        need(stat.S_ISDIR(named.st_mode) and (named.st_uid,named.st_gid,stat.S_IMODE(named.st_mode))==(0,0,0o700) and named.st_dev==root.identity[0],
             'CAPACITY_TREE_NOT_PRIVATE')
    gate();fd=host.open('config',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=root.fd)
    config=hold(host,fd,pinned,parent=root,name='config')
    name=plan['capacity']['config_name'];gate()
    try:named=host.lstat(name,config.fd)
    except FileNotFoundError:raise Refused('CAPACITY_CONFIG_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'CAPACITY_CONFIG_NOT_PRIVATE')
    raw,info=read_regular(host,name,config.fd,gate,MAX_CONFIG_BYTES)
    need(info.st_nlink==1 and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o600),'CAPACITY_CONFIG_NOT_PRIVATE')
    need(sha(raw)==plan['capacity']['config_sha256'],'CAPACITY_CONFIG_HASH_MISMATCH')
    return config

def reached_by_name(holder,gate):
    try:holder.verify(gate);return True
    except Refused as error:
        if str(error)!='PARENT_REPLACED':raise
        return False

def leftovers(rows,container):return [row for row in rows if row['name'].endswith('_'+container)]
def alive(row):return row['running'] is True and row['state']=='running'
def plain(path):return str(PurePosixPath(path)) if type(path) is str else path

def stopwatch(monotonic):
    try:start=monotonic()
    except Exception:start=None
    def read():
        try:return int(round((monotonic()-start)*1000))
        except Exception:return None
    return read

def mounts_of(commands,container_id):
    """docker inspect of the mounts of one container (by ID): Type, Name, Source, Destination, RW of each. A mount
    names host paths and volume names, never a value of the environment."""
    try:rows=strict(commands.output('container_mounts',container_id))
    except Refused as error:
        if isinstance(error,CommandFailed) or str(error) in ('COMMAND_TIMEOUT','COMMAND_OUTPUT_LIMIT','GO_EXPIRED'):raise
        raise Refused('MOUNTS_METADATA_INVALID') from None
    need(type(rows) is list and len(rows)<=MAX_MOUNTS_LISTED and all(type(row) is dict and type(row.get('Destination')) is str
         and type(row.get('Type')) is str and type(row.get('RW')) is bool for row in rows),'MOUNTS_METADATA_INVALID')
    return rows

def mounts_as(plan,rows,count):
    """The mount at /c3po-capacity is the one of a block of `count` lines (the read-only bind of the signed tree from
    the first line on, the placeholder volume without it), and the data root is still bound read-write."""
    capacity=[row for row in rows if plain(row['Destination'])==CAPACITY_TARGET];data=[row for row in rows if plain(row['Destination'])==DATA_TARGET]
    if len(capacity)!=1 or len(data)!=1:return False
    mount=capacity[0]
    if count:right=mount['Type']=='bind' and plain(mount.get('Source'))==capacity_root_path(plan) and mount['RW'] is False
    else:right=mount['Type']=='volume' and mount.get('Name')==placeholder_name(plan) and mount['RW'] is False
    return right and data[0]['Type']=='bind' and plain(data[0].get('Source'))==plan['data_root'] and data[0]['RW'] is True

def environment_as(values,plan,count):
    present=present_names(plan,count)
    return all(item=={'present':True,'equal':True} if name in present else item['present'] is False for name,item in values.items())

def render_errors(rendered,plan,count):
    """check_compose_render.py of the release (check(), placeholder or bind=<tree>), ported: r2d2-worker and no other
    service mounts /c3po-capacity, once, read-only; its three targets unchanged; the project name; the placeholder
    declared with its project name when it is used."""
    errors=[];services=rendered.get('services');found=[]
    for name,service in services.items():
        if type(service) is not dict:errors.append('SERVICE');continue
        for volume in service.get('volumes') or []:
            if type(volume) is not dict:errors.append('LONG_FORM')
            elif volume.get('target')==CAPACITY_TARGET:found.append((name,volume))
    if [name for name,_ in found]!=[WORKER_SERVICE]:return errors+['ONCE_ON_THE_WORKER_ONLY']
    mount=found[0][1]
    if mount.get('read_only') is not True:errors.append('READ_ONLY')
    targets=[volume.get('target') for volume in services[WORKER_SERVICE]['volumes'] if type(volume) is dict]
    if sorted(map(str,targets))!=sorted(WORKER_TARGETS):errors.append('WORKER_TARGETS')
    if rendered.get('name')!=plan['compose']['project']:errors.append('PROJECT')
    declared=rendered.get('volumes')
    if declared is None:declared={}
    if type(declared) is not dict:errors.append('VOLUMES');declared={}
    placeholder=declared.get(PLACEHOLDER_VOLUME)
    named=type(placeholder) is dict and placeholder.get('name')==placeholder_name(plan)
    if count:
        if (mount.get('type'),mount.get('source'))!=('bind',capacity_root_path(plan)):errors.append('BIND')
        if PLACEHOLDER_VOLUME in declared and not named:errors.append('PLACEHOLDER_NAME')
    else:
        if (mount.get('type'),mount.get('source'))!=('volume',PLACEHOLDER_VOLUME):errors.append('PLACEHOLDER')
        if not named:errors.append('PLACEHOLDER_NAME')
    return errors

def service_of(rendered,plan,count,findings=None):
    """What a render must say of the worker: the build revision, the four values of the activation, the capacity names
    of a block of `count` lines with the signed values and none of the others, the data root bound at its target, and
    the capacity mount of that block. Never prints a value."""
    service=compose_service(rendered,WORKER_SERVICE);environment=service['environment'];values=expected_environment(plan,count)
    for ok,code in ((environment.get(BUILD_KEY)==EPOCH_REVISION,'RENDER_BUILD_REVISION'),
                    (all(environment.get(key)==values[key] for key in ACTIVATION_KEYS),'RENDER_ACTIVATION_ENVIRONMENT_MISMATCH')):
        if findings is None:need(ok,code)
        elif not ok:findings.append(code)
    need(all(environment.get(key)==values[key] for key in CAPACITY_KEYS[:count]) and not [key for key in CAPACITY_KEYS[count:] if key in environment],
         'RENDER_CAPACITY_ENVIRONMENT_MISMATCH')
    need(text(service['image'],REFERENCE) and not service['image'].startswith('-'),'RENDER_IMAGE_INVALID')
    volumes=rendered['services'][WORKER_SERVICE].get('volumes')
    need(type(volumes) is list and len(volumes)<=64 and all(type(item) is dict and type(item.get('target')) is str and item['target'] for item in volumes),
         'RENDER_VOLUMES_INVALID')
    data=[item for item in volumes if plain(item['target'])==DATA_TARGET]
    need(len(data)==1 and data[0].get('type')=='bind' and plain(data[0].get('source'))==plan['data_root'] and data[0].get('read_only') in (None,False),
         'WORKER_DATA_MOUNT_NOT_AS_SIGNED')
    need(not render_errors(rendered,plan,count),'RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED')
    return service

def editor_line(result):
    """The status and the constant code of the one line the editor printed; (None, None) when it printed something else."""
    try:
        line=single_line(result['output'])
        if set(line)=={'status','code'} and line['status'] in ENV_EDIT_STATUSES and (line['code'] is None or text(line['code'],CODE)):
            return line['status'],line['code']
    except Exception:pass
    return None,None

def settle_edit(host,state,result,deploy,gate,before,expected,identity):
    """Settle one call of the editor from what the environment file holds afterwards, read on the host: the expected
    bytes on the same object is done; the bytes before on the same object (and a command that returned) is a failure
    that changed nothing; anything else, or a file that cannot be read, is unknown. Returns the row for the receipt."""
    status,code=editor_line(result)
    row={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'status':status,'code':code or result['code'],'state':None}
    if not result['started']:row['state']='NOT_STARTED';return row
    try:
        if not reached_by_name(deploy,gate):raise Refused('DEPLOY_TREE_REPLACED')
        raw,info=env_file_read(host,deploy,gate);same=identity_of(info)==identity
        if same and raw==expected:found='EDITED'
        elif same and raw==before:found='UNCHANGED'
        else:found='OTHER'
    except Exception:found='UNREADABLE'
    if not result['returned']:row['state']=found;return row                     # effect() settled it as unknown already
    if found=='EDITED' and result['returncode']==0 and status=='ENV_EDIT_DONE':state.done()
    elif found=='UNCHANGED' and status=='ENV_EDIT_REFUSED':state.fail()
    else:state.unknown()
    row['state']=found;return row

NOT_STARTED={'started':False,'returned':False,'returncode':None,'status':None,'code':None,'state':'NOT_STARTED'}
def env_file_after(edit,withdraw):
    """What the environment file holds at the end, as far as this run read it: UNCHANGED, EDITED (the signed edit),
    RESTORED (edited, then the edit withdrawn), or UNKNOWN (a call whose result could not be read back)."""
    if withdraw['started'] and not withdraw['returned']:return 'UNKNOWN'          # the editor may still be running
    if withdraw['state']=='EDITED':return 'RESTORED'
    if withdraw['state'] in ('OTHER','UNREADABLE'):return 'UNKNOWN'
    if edit['started'] and not edit['returned']:return 'UNKNOWN'
    if edit['state']=='EDITED':return 'EDITED'
    if edit['state']=='NOT_STARTED' or (edit['state']=='UNCHANGED' and edit['status']=='ENV_EDIT_REFUSED'):return 'UNCHANGED'
    return 'UNKNOWN'
def edit_stop(row):
    """The code a call of the editor that did not end as signed stops the run with."""
    if row['state']=='NOT_STARTED':return row['code'] or 'COMMAND_NOT_STARTED'
    if not row['returned']:return row['code'] or 'ENV_EDIT_DID_NOT_RETURN'
    if row['state']=='UNCHANGED':return row['code'] if row['status']=='ENV_EDIT_REFUSED' and row['code'] else 'ENV_EDIT_FILE_UNCHANGED'
    if row['state']=='EDITED':return 'ENV_EDIT_STATUS_NOT_DONE'
    if row['state']=='UNREADABLE':return 'ENV_FILE_UNREADABLE_AFTER_THE_EDIT'
    return 'ENV_FILE_NOT_AS_EDITED'

def still_listed(commands,name):
    """Whether a container of that name is still listed (an editor whose CLI was killed: CORE U10); None if unreadable."""
    try:return name in [row['name'] for row in container_list(commands)]
    except Exception:return None

AFTER_FACTS=('worker_listed_once','worker_is_new','old_container_gone','running','restarts','image_is_the_signed_one','environment_as_signed',
             'mounts_as_signed','others_unchanged','others_states_unchanged','others_appeared','others_gone','others_same_name_new_id','service_leftovers',
             'env_file_as_edited','compose_file_unchanged','override_unchanged','lock_still_named','settle_pause_taken','second_check_passed',
             'milliseconds_between_checks')
def read_after(c):
    """Everything read after the recreate command was started, each fact on its own (K6a's rule)."""
    host,gate,commands,plan,before,container,count=c['host'],c['gate'],c['commands'],c['plan'],c['before'],c['container'],c['count']
    facts={name:None for name in AFTER_FACTS};failed={};seen={}
    def step(label,action):
        try:action()
        except Exception as error:failed[label]=code_of(error,'OS_ERROR' if isinstance(error,OSError) else 'READBACK_FAILED')
    def worker():
        row=container_facts(commands,container);seen['first']=row;seen['at']=c['monotonic']()
        facts.update(worker_is_new=row['id']!=before['id'],running=alive(row),restarts=row['restarts'],
                     image_is_the_signed_one=row['image_id']==plan['worker']['image_id'])
    def environment():
        if 'first' in seen:
            facts['environment_as_signed']=environment_as(container_environment(commands,seen['first']['id'],c['signed']),plan,count)
    def mounts():
        if 'first' in seen:facts['mounts_as_signed']=mounts_as(plan,mounts_of(commands,seen['first']['id']),count)
    def containers():
        rows=container_list(commands);named=[row['id'] for row in rows if row['name']==container]
        def others(source,states):return sorted((row['id'],row['name'])+((row['state'],) if states else ()) for row in source if row['name']!=container)
        facts.update(worker_listed_once=len(named)==1 and ('first' not in seen or named==[seen['first']['id']]),
                     old_container_gone=before['id'] not in [row['id'] for row in rows],
                     others_unchanged=others(rows,False)==others(c['listing'],False),others_states_unchanged=others(rows,True)==others(c['listing'],True))
        if 'first' not in seen and len(named)==1:facts['worker_is_new']=named[0]!=before['id']
        seen['listing_unchanged']=sorted((row['id'],row['name']) for row in rows)==sorted((row['id'],row['name']) for row in c['listing'])
        was={row['name']:row['id'] for row in c['listing'] if row['name']!=container};now={row['name']:row['id'] for row in rows if row['name']!=container}
        facts.update(others_appeared=len([name for name in now if name not in was]),others_gone=len([name for name in was if name not in now]),
                     others_same_name_new_id=len([name for name in now if name in was and now[name]!=was[name]]),service_leftovers=len(leftovers(rows,container)))
    def environment_file():
        if reached_by_name(c['deploy'],gate):
            raw,info=env_file_read(host,c['deploy'],gate);facts['env_file_as_edited']=raw==c['expected'] and identity_of(info)==c['identity']
        else:facts['env_file_as_edited']=False
    def compose_file():facts['compose_file_unchanged']=reached_by_name(c['project'],gate) and compose_file_state(host,c['project'],gate)==c['compose_before']
    def override():
        def now():
            try:return override_state(host,plan,c['override_directory'],gate)
            except Refused as error:
                if c['override_before'] is not None or str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):raise
                return None                                   # a disable that went on with an override not as delivered: compared as it was
        facts['override_unchanged']=reached_by_name(c['override_directory'],gate) and now()==c['override_before']
    def locked():facts['lock_still_named']=reached_by_name(c['lock_directory'],gate) and lock_still_named(host,LOCK_FILE_NAME,c['lock_directory'],c['lock'])
    def settle():
        facts['settle_pause_taken']=False
        if 'first' in seen and gate()>=SETTLE_SECONDS+SECOND_CHECK_RESERVE_SECONDS:
            host.pause(SETTLE_SECONDS);facts['settle_pause_taken']=True
    def second():
        if 'first' in seen:
            first=seen['first'];row=container_facts(commands,first['id'],expected_name=container)
            facts['second_check_passed']=row['started_at']==first['started_at'] and alive(row) and row['restarts']==0
            facts['milliseconds_between_checks']=int((c['monotonic']()-seen['at'])*1000)
    for label,action in (('WORKER',worker),('ENVIRONMENT',environment),('MOUNTS',mounts),('CONTAINERS',containers),('ENV_FILE',environment_file),
                         ('COMPOSE_FILE',compose_file),('OVERRIDE',override),('LOCK',locked),('SETTLE',settle),('SECOND_CHECK',second)):step(label,action)
    first=seen.get('first')
    unchanged=bool(first is not None and seen.get('listing_unchanged') is True and alive(first)
                   and all(first[key]==before[key] for key in ('started_at','restarts')))
    return facts,failed,unchanged

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_chains(receipt):receipt['chains']={key:len(rows) for key,rows in (receipt.get('chains') or {}).items()}
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('CHAINS_REDUCED_TO_COUNTS',_reduce_chains)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    mode=plan['mode'];spec=edit_spec(plan);stdin=editor_stdin(spec);after=MODES[mode]['after']                    # pure
    signed=expected_environment(plan,5);compose=plan['compose'];container=worker_name(plan);listed=file_list(plan)
    active=mode in ('MOUNT','ENABLE')                       # the worker must run before; the tree is read
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'chains':{},'precheck':{},'budget':{},'process':{'dumpable_disabled':None}};pinned=[];lock=[None]
    commands=Commands(host,gate)
    edit=dict(NOT_STARTED);withdraw=dict(NOT_STARTED);findings=[];detail['precheck']['findings']=findings
    def judge(ok,code):
        """MOUNT and ENABLE refuse; a disable reports and goes on: it must work on a worker that loops because the
        epoch's pins no longer hold (MNT, "While the flag is on")."""
        if active:need(ok,code)
        elif not ok:findings.append(code)
    def looked(action):
        try:return action()
        except Refused as error:
            if active or str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):raise
            findings.append(code_of(error,'FINDING'));return None
    run={'state':'NOT_STARTED','code':None,'returncode':None,'started':False,'returned':False,'milliseconds':None,'replaced':False,'facts':None,'unavailable':None}
    def finish(status,outcome,code,extra):
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),mode=mode,chains=detail['chains'],precheck=detail['precheck'],
            budget=detail['budget'],process=detail['process'],env_edit=edit,env_withdraw=withdraw,recreate=run,worker_container_replaced=run['replaced'],
            env_file_after=env_file_after(edit,withdraw),pre_existing_objects_modified=not state.clean(),
            failure_phase=None if code is None else ('AFTER_THE_RECREATE_STARTED' if run['started'] else
                                                     'BEFORE_THE_RECREATE' if edit['started'] else 'BEFORE_THE_EDIT'),**extra))
        return seal(receipt)
    def chain(key,rows):
        seen=[];detail['chains'][key]=seen
        return hold(host,walk_pinned(host,rows,gate,seen),pinned,rows=rows)
    try:
        # ---- everything is looked at before the first effect
        try:
            # first, before anything is opened: this process made non-dumpable and proved so (PROCESS_SCOPE)
            detail['process']['dumpable_disabled']=False
            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');detail['process']['dumpable_disabled']=True
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            deploy=chain('DEPLOY_DIRECTORY',plan['deploy_directory'])
            looked(lambda:deploy_version(host,deploy,gate))
            env_before,env_info=env_file_read(host,deploy,gate)
            identity=identity_of(env_info)
            need(identity[2:]==ENV_OWNER+(ENV_MODE,1),'ENV_FILE_NOT_EDITABLE_BY_THE_EDITOR')
            # decision 6 (every bind source and its ancestors root-controlled): reported as read, not judged (open item)
            detail['precheck']['bind_source_root_controlled']=bool(all(row.get('uid')==0 for row in detail['chains']['DEPLOY_DIRECTORY']) and identity[2]==0)
            expected,block=edited_env(env_before,spec)
            withdrawn_spec=edit_spec(plan,(after,),len(block))                         # the inverse edit, used only if the render after the edit is not as signed
            detail['precheck']['capacity_lines_found']=len(block)
            project=project_directory(host,plan,deploy,gate,pinned)
            compose_before=compose_file_state(host,project,gate)
            override_directory=chain('OVERRIDE_DIRECTORY',plan['override']['directory'])
            override_before=looked(lambda:override_state(host,plan,override_directory,gate))
            tree=None
            if active:
                tree=chain('CAPACITY_ROOT',plan['capacity']['root'])
                capacity_tree(host,plan,tree,gate,pinned)
            lock_directory=chain('LOCK_DIRECTORY',plan['lock']['directory'])
            lock[0]=open_lock(host,LOCK_FILE_NAME,lock_directory,gate)
            detail['precheck'].update(deploy_version_is_the_revision='DEPLOY_VERSION_MISMATCH' not in findings and 'DEPLOY_VERSION_ABSENT' not in findings,
                                      override_as_delivered=override_before is not None,capacity_tree_as_signed=True if active else None)
            # the worker as it is: by name; for MOUNT and ENABLE running and in the state of the block found
            before=container_facts(commands,container)
            detail['precheck']['worker']={'id':before['id'],'started_at':before['started_at'],'restarts':before['restarts'],'state':before['state']}
            judge(before['image_id']==plan['worker']['image_id'],'WORKER_IMAGE_NOT_THE_SIGNED_ONE')
            try:image=image_facts(commands,plan['worker']['image_id'])
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            judge(image['revision_label']==EPOCH_REVISION,'IMAGE_REVISION_MISMATCH')
            values=container_environment(commands,before['id'],signed);mounts=mounts_of(commands,before['id'])
            detail['precheck'].update(worker_running=alive(before),worker_environment_as_found=environment_as(values,plan,len(block)),
                                      worker_mounts_as_found=mounts_as(plan,mounts,len(block)))
            if active:
                need(alive(before),'WORKER_NOT_RUNNING')
                need(detail['precheck']['worker_environment_as_found'],'WORKER_ENVIRONMENT_NOT_AS_FOUND_IN_THE_FILE')
                need(detail['precheck']['worker_mounts_as_found'],'WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE')
            # the render from the files as they are, timed: the same render runs again between the edit and the recreate
            began=monotonic()
            service=service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan,len(block),
                               None if active else findings)
            measured=monotonic()-began
            try:resolved=image_facts(commands,service['image'])
            except CommandFailed:raise Refused('RENDER_IMAGE_UNRESOLVED') from None
            judge(resolved['id']==plan['worker']['image_id'],'RENDER_IMAGE_CHANGED')
            detail['precheck']['render']={'as_the_file_says':True,'image_is_the_signed_one':resolved['id']==plan['worker']['image_id']}
            allowance=min(COMMAND_CLASSES['RENDER']['seconds'],max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1))
            needed=effects_budget('edit_env','recreate')+allowance+FILES_ALLOWANCE_SECONDS+SETTLE_SECONDS
            detail['budget']={'first_render_milliseconds':int(measured*1000),'render_allowance_seconds':allowance,'needed_before_first_effect_seconds':needed,
                              'kept_while_waiting_for_the_lock_seconds':needed+UNDER_LOCK_ALLOWANCE_SECONDS,'left_when_the_lock_was_asked_for_milliseconds':int(gate()*1000)}
            need(needed+UNDER_LOCK_ALLOWANCE_SECONDS<MAX_SECONDS,'BUDGET_CANNOT_HOLD_BOTH_EFFECTS')
            detail['precheck']['lock_attempts']=acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed+UNDER_LOCK_ALLOWANCE_SECONDS)
            need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
            pending=probe(host,REBOOT_PENDING_PATH,gate)
            need(pending.get('status')=='COMPLETE','REBOOT_STATE_UNAVAILABLE');need(pending.get('exists') is False,'SECURITY_REBOOT_PENDING')
            need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')
            need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
            if tree is not None:
                need(reached_by_name(tree,gate),'CAPACITY_ROOT_REPLACED')
                capacity_tree(host,plan,tree,gate,pinned)                 # the static config again, under the lock
            looked(lambda:deploy_version(host,deploy,gate))
            again_raw,again_info=env_file_read(host,deploy,gate)
            need(again_raw==env_before and stat_signature(again_info)==stat_signature(env_info),'ENV_FILE_CHANGED_BEFORE_THE_LOCK')
            need(compose_file_state(host,project,gate)==compose_before,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK')
            need(looked(lambda:override_state(host,plan,override_directory,gate))==override_before,'OVERRIDE_CHANGED_BEFORE_THE_LOCK')
            try:again_image=image_facts(commands,service['image'])
            except CommandFailed:raise Refused('RENDER_IMAGE_UNRESOLVED') from None
            need(again_image['id']==resolved['id'],'RENDER_IMAGE_CHANGED_BEFORE_THE_LOCK')        # a tag moved while the lock was waited for
            again=container_facts(commands,container)
            keys=('id','started_at','restarts') if active else ('id',)
            need(all(again[key]==before[key] for key in keys) and (alive(again) or not active),'WORKER_CHANGED_BEFORE_THE_LOCK')
            listing=container_list(commands)
            need([row['id'] for row in listing if row['name']==container]==[before['id']],'CONTAINER_LIST_INCONSISTENT')
            need(not leftovers(listing,container),'WORKER_SERVICE_LEFTOVER_CONTAINER')
            need(not [row for row in listing if row['name'] in (editor_name(bound),editor_name(bound)+'-withdraw')],'EDITOR_NAME_TAKEN')
            need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')         # last, right before the editor binds .env by its path
            detail['precheck'].update(reboot_pending=False,containers_listed=len(listing))
            left=gate();detail['budget']['left_before_first_effect_milliseconds']=int(left*1000)
            need(left>=needed,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None
        mount=editor_mounts(plan)
        result=container_effect(state,commands,'edit_env',plan['worker']['image_id'],mount,ENV_EDITOR_COMMAND,stdin,container_name=editor_name(bound))
        edit=settle_edit(host,state,result,deploy,gate,env_before,expected,identity)
        if result['started'] and not result['returned']:edit['container_left']=still_listed(commands,editor_name(bound))
        if edit['state']!='EDITED' or not result['returned'] or result['returncode']!=0 or edit['status']!='ENV_EDIT_DONE':
            stop=edit_stop(edit)
        if stop is None:
            taken=stopwatch(monotonic)
            try:
                need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
                need(service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan,after,
                                None if active else [])['image']==service['image'],'RENDER_IMAGE_CHANGED')
            except Exception as error:stop=code_of(error,'RENDER_AFTER_EDIT_OS_ERROR' if isinstance(error,OSError) else 'RENDER_AFTER_EDIT_FAILED')
            detail['budget']['render_after_the_edit_milliseconds']=taken()
            # the allowance the budget kept for this render (core rule 4.2): a slower render is a failure, not a late recreate
            if stop is None and (detail['budget']['render_after_the_edit_milliseconds'] is None or detail['budget']['render_after_the_edit_milliseconds']>allowance*1000):
                stop='RENDER_AFTER_EDIT_OVER_ITS_ALLOWANCE'
        if stop is None:
            try:
                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')
                need(reached_by_name(override_directory,gate),'OVERRIDE_DIRECTORY_REPLACED')
                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
            except Exception as error:stop=code_of(error,'RECREATE_PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'RECREATE_PRECHECK_FAILED')
        if stop is None:
            taken=stopwatch(monotonic)
            result=compose_up(state,commands,'recreate',compose['project'],compose['env_file'],listed,EPOCH_REVISION)
            run.update(started=result['started'],returned=result['returned'],returncode=result['returncode'],code=result['code'],milliseconds=taken())
            if not result['started']:stop=result['code'] or 'COMMAND_NOT_STARTED'
            else:
                facts,failed,unchanged=read_after({'host':host,'gate':gate,'commands':commands,'plan':plan,'before':before,'container':container,'count':after,
                    'listing':listing,'signed':signed,'deploy':deploy,'expected':expected,'identity':identity,'project':project,'compose_before':compose_before,
                    'override_directory':override_directory,'override_before':override_before,'lock_directory':lock_directory,'lock':lock[0],'monotonic':monotonic})
                run.update(facts=facts,unavailable=failed)
                criteria=[(result['code'] or 'RECREATE_RETURNED_NONZERO',bool(result['returned'] and result['returncode']==0)),
                          ('WORKER_NOT_FOUND_AFTER_RECREATE',facts['worker_listed_once']),('WORKER_NOT_RECREATED',facts['worker_is_new']),
                          ('OLD_CONTAINER_STILL_PRESENT',facts['old_container_gone']),('WORKER_NOT_RUNNING_AFTER_RECREATE',facts['running']),
                          ('WORKER_RESTARTED_AFTER_RECREATE',None if facts['restarts'] is None else facts['restarts']==0),
                          ('WORKER_IMAGE_CHANGED',facts['image_is_the_signed_one']),('ENVIRONMENT_NOT_AS_SIGNED',facts['environment_as_signed']),
                          ('MOUNTS_NOT_AS_SIGNED',facts['mounts_as_signed']),('OTHER_CONTAINERS_CHANGED',facts['others_unchanged']),
                          ('ENV_FILE_NOT_AS_EDITED',facts['env_file_as_edited']),('COMPOSE_FILE_CHANGED',facts['compose_file_unchanged']),
                          ('OVERRIDE_CHANGED',facts['override_unchanged']),('LOCK_FILE_REPLACED',facts['lock_still_named']),
                          ('SECOND_CHECK_NOT_APART',facts['settle_pause_taken']),('WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS',facts['second_check_passed'])]
                missing=[name if value is False else 'READBACK_UNAVAILABLE' for name,value in criteria if value is not True]
                if not missing:
                    state.done();run.update(state='RECREATED_VERIFIED',replaced=True)
                elif result['returned'] and unchanged:
                    state.fail();run.update(state='NOT_RECREATED',replaced=False)
                    stop='RECREATE_FAILED_CONTAINER_UNCHANGED' if result['returncode'] else 'RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED'
                else:
                    if result['returned']:state.unknown()
                    if facts['worker_is_new'] is True:
                        once=not [name for name,value in criteria[:-2] if value is not True] and facts['second_check_passed'] is not False
                        run.update(state='RECREATED_VERIFIED_ONCE' if once else 'RECREATED_NOT_VERIFIED',replaced=True)
                    else:run.update(state='UNCERTAIN',replaced=None)
                    stop=missing[0]
        if (stop is not None and plan['withdrawal_authorized'] and edit['state']=='EDITED' and edit['returncode']==0 and edit['status']=='ENV_EDIT_DONE'      # exit 0: it returned
                and not run['started']):
            # MNT, step 1: "If config or the check fails, nothing was recreated. Delete the line appended above." The signed
            # effect E1' (effects.withdrawal): only when authorized, only BEFORE the recreate was started (no rollback is
            # inferred from a recreate that ran), only after an edit the editor confirmed and the host read back, and only
            # while the lock is still the one held. The inverse edit, by the same editor; never a second recreate.
            try:held=lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0])
            except Exception:held=False
            if held:
                back=container_effect(state,commands,'edit_env',plan['worker']['image_id'],mount,ENV_EDITOR_COMMAND,editor_stdin(withdrawn_spec),
                                      container_name=editor_name(bound)+'-withdraw')
                withdraw=settle_edit(host,state,back,deploy,gate,expected,env_before,identity)
                if back['started'] and not back['returned']:withdraw['container_left']=still_listed(commands,editor_name(bound)+'-withdraw')
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        if run['state'] in ('RECREATED_VERIFIED_ONCE','RECREATED_NOT_VERIFIED'):outcome=NOT_VERIFIED_OUTCOME
        elif run['state']=='UNCERTAIN' or env_file_after(edit,withdraw)=='UNKNOWN':outcome=UNCERTAIN_OUTCOME
        elif run['state']=='NOT_RECREATED':outcome=RECREATE_FAILED_OUTCOME
        elif withdraw['state']=='EDITED':outcome=WITHDRAWN_OUTCOME
        else:outcome=ENV_ONLY_OUTCOME
        return finish(PARTIAL_STATUS,outcome,stop,extra)
    finally:
        if lock[0] is not None:release_lock(host,lock[0])
        for handle in pinned:
            try:handle.close()
            except Exception:pass
# ==== END OP_CAPACITY_SWITCH ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
