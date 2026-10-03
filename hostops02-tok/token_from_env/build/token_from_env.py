"""OP_TOKEN_FROM_ENV: the provider token of the Massive supervisor, placed once as /etc/c3po-bar/token from the
value the deploy environment file of the host already holds (MASSIVE_API_TOKEN, or C3PO_MASSIVE_API_TOKEN, the two
names the backend accepts). One source, one signed run, on 2026-10-03 or 2026-10-04 UTC only.

First of all, before the deploy directory, the environment file or anything else is opened, it makes its own process
non-dumpable (prctl PR_SET_DUMPABLE 0, read back 0 with PR_GET_DUMPABLE, through the core's dumps_disabled): the kernel
then produces no core dump of it, to a file or through a pipe to a crash collector, so a crash cannot carry any byte of
the environment file out. If that cannot be done and proved, it refuses with nothing changed.

It reads ONE file: <signed deploy directory>/.env, by a descriptor walk from "/" that never follows a link, after
proving every component a directory, every component above the deploy directory root-owned and not writable by group
or other, none writable by any user without the sticky bit, and the file regular, with one link, not world-writable,
owned by root or by the owner of the deploy directory and at most 65536 bytes. The file is parsed in memory under a
strict subset of the dotenv grammar of docker compose; every definition of either name must be the plain form
NAME=VALUE, all of them byte-equal, no other line may hold the name in any case, and the value must match a fixed
grammar; anything else is a refusal with a constant code. It never reads an environment of a process, never runs
docker or any other program, and starts no process.

Then, relative to the held descriptor of /etc/c3po-bar (identity signed from the receipt of supervisor operation 2,
root:root 0700), ONE exclusive create of the name "token" (O_CREAT|O_EXCL|O_NOFOLLOW, 0600 under umask 0077), the
value and one newline written, the file and the directory fsynced, and the file read back by descriptor: uid 0, gid
0, mode 0600, one link, size within 1-4096, bytes equal to what was written (compared in memory only). Everything is
looked at before the creation; a token file that exists is never touched (refusal). If a step after the creation
fails, the file this run created is removed again, and only while its name still shows the inode this run holds (an
exception to rule 4 of the core, declared in the signed scope). The receipt carries listed codes, booleans and
identity rows only: never the value, a digest of it, its length or a line count. The caller authenticates exact
request/authority/GO/source bytes first.
No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='32c44cf80e6d53e860745e52792cc917c15ccaae448aee7ba68b6aca76d3c644'
CORE_PARTS={'core': '60e29427f42b500642fdf57568843d63f2437714c899d61d88bcee05e63ecd6b', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'files': '6b96ad64fe8ce5a9a2293b109964e069c2ad32169e7d421449da3f88516b60ba'}
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

# ==== BEGIN OP_TOKEN_FROM_ENV (this operation only) ====
OPERATION='GO_WRITE_HOSTOPS02_TOKEN_FROM_ENV_01'
PHASE='WRITE_SUPERVISOR_TOKEN_FROM_THE_DEPLOY_ENVIRONMENT_FILE'
REQUEST_SCHEMA='WRITE_HOSTOPS02_TOKEN_FROM_ENV_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_TOKEN_FROM_ENV_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_TOKEN_FROM_ENV_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_TOKEN_FROM_ENV_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_TOKEN_FROM_ENV_PLAN_V1'
SOURCE_NAME='token_from_env.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_WEEKEND'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
PROVISION_OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='TOKEN_PLACED_METADATA_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_SEE_TOKEN_FILE_STATE'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_TOKEN_FILE_MAY_EXIST'
PLAN_KEYS=frozenset(('config_chain','deploy_directory','evidence_boot_id_sha256'))

# ---- the constants of this operation. A request cannot move any of them: they are bytes of the signed source.
# The days: the token must exist before the first session. The Sunday read L5 of the A1 (window from 2026-10-04 11:15
# UTC, 08:15 BRT) reads its metadata, so the binding puts this run before that instant, on Saturday when it can
# (CONTRACT section 4). That instant is not a refusal of the source (CONTRACT D10). The date class of the core
# (WRITE_WEEKEND) also holds 2026-10-02; this source narrows it to the two days below.
TOKEN_DAYS=('2026-10-03','2026-10-04')
# Where the supervisor reads the token (README of c3po/deployment/massive-supervisor at dd4ec4bb, "Token procedure"),
# and what it accepts there (r2d2_v2_massive_supervisor.py:38-55, private_bytes, and :114-115, the read): a regular
# file, one link, owned by the effective uid of the supervisor (uid 0), mode 0600, 1 to 4096 bytes, decoded as UTF-8,
# stripped, not empty and without a line break.
CONFIG_DIRECTORY='/etc/c3po-bar'
CONFIG_DIRECTORY_MODE=0o700
TOKEN_NAME='token'
TOKEN_PATH=CONFIG_DIRECTORY+'/'+TOKEN_NAME
TOKEN_FILE_MODE=0o600
TOKEN_MAX_FILE_BYTES=4096
TOKEN_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
# Where the value comes from: the environment file of the deploy tree, which docker compose reads for every backend
# service (c3po/compose.yml: env_file ../.env) and which holds MASSIVE_API_TOKEN (README line 207). The backend accepts
# C3PO_MASSIVE_API_TOKEN or MASSIVE_API_TOKEN, the first one present winning (c3po/backend/app/config.py:116-118,
# pydantic AliasChoices; names matched without regard to case). Both names are looked for, in any case.
ENV_FILE_NAME='.env'
MAX_ENV_FILE_BYTES=65536
TOKEN_KEYS=('C3PO_MASSIVE_API_TOKEN','MASSIVE_API_TOKEN')
# The value: what every reader of the file takes as the same bytes (no quote, space, "#", "$" or backslash), one line,
# ASCII, 16 to 512 characters. The supervisor needs a non-empty single line after strip(); this grammar implies it.
TOKEN_VALUE_GRAMMAR='[A-Za-z0-9._~+/=-]{16,512}'
TOKEN_VALUE=TOKEN_VALUE_GRAMMAR.encode('ascii')
# The lines of the environment file, as docker compose's dotenv parser delimits its statements. A file in which any
# line is none of these is refused whole: a statement boundary that differs from compose's could hide a definition.
# A statement must have "=" or ":": compose v2 takes a bare name from its own environment, and an older parser took
# the next line as its value, so a bare name is a boundary on which parsers differ.
ENV_LINE_BLANK=rb'[ \t]*'
ENV_LINE_COMMENT=rb'[ \t]*#.*'
ENV_LINE_STATEMENT=rb'([ \t]*)(export[ \t]+)?([A-Za-z0-9_.\[\]-]+)([ \t]*)([=:])([ \t]*)(.*)'
ENV_QUOTED_TAIL=rb'[ \t]*(?:#.*)?'
# Both names as a reader that compares names without regard to case sees them (pydantic-settings: str.lower()). No line
# but a plain definition and comments may hold this, in any case: a parser that split a line where compose does not
# would otherwise find a definition there. U+212A (the Kelvin sign) is the one character outside ASCII that
# str.lower() turns into an ASCII letter ("k"), so it is read as "k".
TOKEN_NAME_FOLDED=b'massive_api_token'
KELVIN_SIGN=b'\xe2\x84\xaa'
ENV_RULES=['the file holds no carriage return and no NUL byte',
           'every line is blank (spaces and tabs), a comment (# after spaces and tabs), or a statement: optional spaces and tabs, '
           'optional "export" and spaces or tabs, a name of the characters A-Z a-z 0-9 _ . - [ ], optional spaces or tabs, "=" or ":", '
           'optional spaces or tabs and a value; a name without "=" or ":" (compose would take it from its own environment) is refused',
           'a value of another name that begins with a quote ends on the same line at the next quote of the same kind, holds no two '
           'consecutive backslashes and no backslash just before that quote, and is followed by nothing but spaces, tabs and an optional '
           'comment; a value of another name that does not begin with a quote ends at the end of its line and does not begin with a '
           'vertical tab, a form feed or a byte above 127',
           'a statement whose name equals MASSIVE_API_TOKEN or C3PO_MASSIVE_API_TOKEN without regard to case is a definition; every '
           'definition is exactly NAME=VALUE: the name in capitals, at the start of the line, no "export", "=" with no space on either side',
           'no line but a definition and the comments holds massive_api_token in any case (the Kelvin sign read as k): not inside or '
           'around another name, not in a value of another name',
           'at least one definition; every definition of both names byte-equal (compose keeps the last of a name, the backend the '
           'first of the two names present)',
           'the value matches '+TOKEN_VALUE_GRAMMAR+' to the end of its line (no quote, space, comment, "$" or backslash)']
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the creation (the writes take milliseconds)
TOKEN_STATES=('NOT_ATTEMPTED','NOT_CREATED','CREATE_UNCERTAIN','WITHDRAWN','WITHDRAWN_NOT_DURABLE','LEFT_UNVERIFIED','PLACED_VERIFIED')
# Every code a receipt of this source's run may carry (code, token_file.code, token_file.withdrawal_code). The core's
# code_of() lets any text of the shape of a code through; here a code is a member of this list, and any other text is
# replaced by UNLISTED_CODE before the receipt is sealed, so no text the run did not write itself can reach a receipt.
RECEIPT_CODES=frozenset((
    # the precheck: the process (not dumpable), the executor, the boot, the configuration directory (the core's walk), the token name
    'PROCESS_DUMPABLE_NOT_DISABLED','EXECUTOR_IDENTITY','NOATIME_UNAVAILABLE','BOOT_ID_INVALID','EVIDENCE_FROM_EARLIER_BOOT','PARENT_MISSING','PARENT_UNREADABLE',
    'PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_CHANGED_DURING_WALK','PARENT_IDENTITY_MISMATCH','PARENT_REPLACED',
    'TOKEN_FILE_PRESENT',
    # the deploy chain and the environment file
    'DEPLOY_DIRECTORY_ABSENT','DEPLOY_CHAIN_SYMLINK','DEPLOY_CHAIN_NOT_A_DIRECTORY','DEPLOY_CHAIN_CHANGED_DURING_WALK',
    'DEPLOY_CHAIN_UNSAFE_ABOVE_THE_DEPLOY_DIRECTORY','DEPLOY_CHAIN_WORLD_WRITABLE','CHAIN_ROW_INVALID','PATH_INVALID',
    'ENV_FILE_ABSENT','ENV_FILE_NOT_REGULAR','ENV_FILE_WORLD_WRITABLE','ENV_FILE_LINKED','ENV_FILE_OWNER_UNEXPECTED','ENV_FILE_TOO_LARGE',
    'ENV_FILE_CHANGED_DURING_READ','ENV_FILE_SYNTAX_UNSUPPORTED','ENV_TOKEN_DEFINITION_NOT_PLAIN','ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION',
    'ENV_TOKEN_ABSENT','ENV_TOKEN_DEFINITIONS_DISAGREE','ENV_TOKEN_VALUE_GRAMMAR',
    # the last refusals before the creation, and the clock at any point
    'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT','GO_EXPIRED','CLOCK_REVERSED','PRECHECK_OS_ERROR','PRECHECK_FAILED',
    # the creation, the readback, the withdrawal
    'TOKEN_FILE_APPEARED_AFTER_PRECHECK','FILESYSTEM_READ_ONLY','FILESYSTEM_FULL','FILESYSTEM_ACCESS_DENIED','FILESYSTEM_ERROR',
    'TOKEN_CREATE_UNCERTAIN','TOKEN_WRITE_INCOMPLETE','FSYNC_FAILED','TOKEN_METADATA_MISMATCH','TOKEN_STAT_FAILED','READBACK_MISMATCH',
    'READBACK_UNAVAILABLE','TOKEN_PLACEMENT_FAILED','TOKEN_NOT_PLACED','TOKEN_NAME_NOT_THIS_RUNS_FILE','TOKEN_WITHDRAWAL_FAILED',
    'TOKEN_WITHDRAWAL_UNCERTAIN'))
UNLISTED_CODE='UNLISTED_CODE'
# The process itself, first of all (revision 3, CONTRACT D9): before the deploy directory, the environment file or anything
# else is opened, the core's NativeRead.not_dumpable() sets the dumpable attribute of this process to 0 and reads it back
# 0 (prctl(2)). A process that is not dumpable produces no core dump: the kernel returns from do_coredump() before it
# reads kernel.core_pattern, so neither a pipe to a crash collector nor a file receives its memory, and no byte of .env
# can leave through a crash. Otherwise the run refuses, nothing changed (PROCESS_DUMPABLE_NOT_DISABLED).
PROCESS_SCOPE={'dumpable':0,'how':'prctl(PR_SET_DUMPABLE, 0), then prctl(PR_GET_DUMPABLE) must answer 0 (the core\'s dumps_disabled)',
               'when':'first, before the deploy directory, the environment file or anything else is opened',
               'core_dump':'none, to a file or through a pipe to a crash collector: the kernel dumps no process that is not dumpable',
               'otherwise':'refused, nothing changed: PROCESS_DUMPABLE_NOT_DISABLED'}

SCOPE_STATEMENT=('First of all, before the deploy directory or the environment file is opened, makes its own process non-dumpable (prctl '
                 'PR_SET_DUMPABLE 0, read back 0 with PR_GET_DUMPABLE), so that no core dump of it, to a file or through a pipe to a crash '
                 'collector, can hold any byte of the environment file; otherwise it refuses with nothing changed. '
                 'Reads the environment file .env of the signed deploy directory once, in memory, and places the value it holds for '
                 'MASSIVE_API_TOKEN (or C3PO_MASSIVE_API_TOKEN; every definition byte-equal) as the provider token of the supervisor: '
                 'one exclusive create of '+TOKEN_PATH+' (root:root 0600, one link, the value and one newline) relative to the held '
                 'descriptor of the configuration directory whose identity the request signs from the receipt of supervisor operation 2, '
                 'fsync of the file and of the directory, and a readback by descriptor of owner, mode, links, size within 1-4096 and the '
                 'bytes, compared in memory. A file that exists at that name is never touched. If a step after the creation fails, the '
                 'file this run created is removed while its name still shows the inode this run holds, and only then. On 2026-10-03 or '
                 '2026-10-04 UTC only. No process is started, no environment of a process and no container is read, nothing is activated, '
                 'and the receipt never carries the value, a digest of it, its length or a line count.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'token_days':list(TOKEN_DAYS),
       'paths':{'config_directory':CONFIG_DIRECTORY,'token_file':TOKEN_PATH,'environment_file':'<the signed deploy directory>/'+ENV_FILE_NAME},
       'token_file':{'type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%TOKEN_FILE_MODE,'links':1,'content':'the value, then one newline',
                     'bytes':'1 to %d, never reported'%TOKEN_MAX_FILE_BYTES,'umask_octal':'0077',
                     'creation':'one open O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC relative to the held descriptor of the configuration directory',
                     'withdrawal':'only after its own creation succeeded and a later step failed, only while the name shows the inode this run holds '
                                  'with one link; never after the expiry of the GO or a replaced directory'},
       'config_directory':{'path':CONFIG_DIRECTORY,'uid':0,'gid':0,'mode_octal':'%04o'%CONFIG_DIRECTORY_MODE,'rows':'signed, from "/"'},
       'environment_file':{'name':ENV_FILE_NAME,'max_bytes':MAX_ENV_FILE_BYTES,'keys':list(TOKEN_KEYS),'value_grammar':TOKEN_VALUE_GRAMMAR,'rules':ENV_RULES,
                           'chain':'walked from "/" without following a link and not signed: every component a directory, every component above '
                                   'the deploy directory root-owned and not writable by group or other, no component writable by any user '
                                   'without the sticky bit',
                           'file':'regular, one link, not world-writable, owned by root or by the owner of the deploy directory, unchanged while read'},
       'exceptions_to_the_core':['rule 4 (nothing is removed but the temporary of this run once its identity is proved): this source may '
                                 'remove the final name '+TOKEN_PATH+', and only the file this run created, after a later step of this run '
                                 'failed, while the name shows the inode this run holds with one link; never after the expiry of the GO, '
                                 'never after the configuration directory was found replaced'],
       'process':PROCESS_SCOPE,
       'receipt_never':['the value','a digest of the value','the length of the value','a line count','any byte of the environment file'],
       'receipt_codes':sorted(RECEIPT_CODES),'receipt_code_otherwise':UNLISTED_CODE,
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'<the signed deploy directory>/'+ENV_FILE_NAME+' (in memory)',TOKEN_PATH+' (the readback, in memory)'],
       'processes_started':0,
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but the token file this run created','a process','docker','systemctl',
                'a shell','a network connection','the environment of a process or of a container','activation','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'environment_file_bytes':MAX_ENV_FILE_BYTES,'token_file_bytes':TOKEN_MAX_FILE_BYTES,'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the creating calls of the files part. No process."""


# ---------------------------------------------------------------- the environment file, in memory
def value_boundary(value):
    """A value of another name ends where every compose parser ends it: a quoted one at its closing quote, an unquoted
    one at the end of its line. Only the forms whose end is the same in all of them are accepted. In a quoted value a
    backslash before any other character is harmless (the closing quote is the first quote of its kind either way); two
    backslashes, or one just before that quote, are where the escape rules of the old and the new parser differ."""
    if value[:1] in (b'"',b"'"):
        closing=value.find(value[:1],1)            # -1 when the quote is not closed on this line: the tail is then the
        body=value[1:closing]                      # whole value, which the tail rule refuses
        need(b'\\\\' not in body and body[-1:]!=b'\\' and re.fullmatch(ENV_QUOTED_TAIL,value[closing+1:]) is not None,'ENV_FILE_SYNTAX_UNSUPPORTED')
    else:
        need(value[:1] not in (b'\x0b',b'\x0c') and (not value or value[0]<0x80),'ENV_FILE_SYNTAX_UNSUPPORTED')

def folded(line):
    """A line of another name as a reader that compares names without regard to case sees it."""
    return line.replace(KELVIN_SIGN,b'k').lower()

def token_definitions(raw):
    """[(name, start, end)] of every definition of the two names, as offsets of the value in raw. Raises Refused with a
    constant code for a file outside the accepted subset, a definition that is not the plain form, or the name anywhere
    else. The lines are looked at through a view of raw: the line of a definition is never copied, its value is judged
    only by token_content(), and nothing of the bytes leaves this function but offsets."""
    need(b'\r' not in raw and b'\x00' not in raw,'ENV_FILE_SYNTAX_UNSUPPORTED')
    names={key.encode('ascii'):key for key in TOKEN_KEYS}
    found=[];position=0;size=len(raw);view=memoryview(raw)
    try:
        while position<=size:
            end=raw.find(b'\n',position)
            if end<0:end=size
            line=view[position:end]
            if re.fullmatch(ENV_LINE_BLANK,line) is None and re.fullmatch(ENV_LINE_COMMENT,line) is None:
                match=re.fullmatch(ENV_LINE_STATEMENT,line)
                need(match is not None,'ENV_FILE_SYNTAX_UNSUPPORTED')
                lead,export,key,space,separator,gap=match.group(1,2,3,4,5,6)     # the value (group 7) is not copied out
                if key.upper() in names:
                    need(not lead and export is None and key in names and not space and separator==b'=' and not gap,'ENV_TOKEN_DEFINITION_NOT_PLAIN')
                    found.append((names[key],position+match.start(7),end))
                else:
                    other=bytes(line)                  # a line of another name: it may hold another secret, and stays here
                    value_boundary(other[match.start(7):])
                    need(TOKEN_NAME_FOLDED not in folded(other),'ENV_TOKEN_NAME_OUTSIDE_A_PLAIN_DEFINITION')
            position=end+1
        return found
    finally:view.release()

def token_content(raw,found):
    """The value every definition holds, and one newline, in a new bytearray (zeroed by the caller after use)."""
    need(found,'ENV_TOKEN_ABSENT')
    view=memoryview(raw)
    try:
        first=view[found[0][1]:found[0][2]]
        need(all(view[start:end]==first for _,start,end in found),'ENV_TOKEN_DEFINITIONS_DISAGREE')
        need(re.fullmatch(TOKEN_VALUE,first) is not None,'ENV_TOKEN_VALUE_GRAMMAR')
        content=bytearray(len(first)+1);content[:len(first)]=first;content[len(first)]=0x0a
        return content
    finally:view.release()

def zero(buffer):
    """Best effort: the bytearray that held the value is overwritten in place. Immutable copies made by the interpreter
    (the bytes read from the file and from the readback, the blocks read_regular() joined) cannot be overwritten; they
    are only dropped, and the memory they leave is not cleared by the interpreter (DESIGN.md section 8)."""
    if type(buffer) is bytearray:
        for index in range(len(buffer)):buffer[index]=0


def validate_plan(plan):
    rows=validate_chain(plan['config_chain'],CONFIG_DIRECTORY,receives_entry=True)         # every row root-owned, not writable by group or other
    need((rows[-1]['gid'],rows[-1]['mode'])==(0,CONFIG_DIRECTORY_MODE),'CONFIG_DIRECTORY_NOT_ROOT_0700')
    deploy=plan['deploy_directory']
    need(clean_path(deploy),'DEPLOY_DIRECTORY_INVALID')
    need(not inside(deploy,CONFIG_DIRECTORY) and not inside(CONFIG_DIRECTORY,deploy),'DEPLOY_DIRECTORY_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(instant(plan['window']['not_before']).date().isoformat() in TOKEN_DAYS,'WINDOW_NOT_ON_A_TOKEN_DAY')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    deploy=plan['deploy_directory']
    return {'operation':OPERATION,
            'config_directory':dict(chain_effects(plan['config_chain']),required={'uid':0,'gid':0,'mode_octal':'%04o'%CONFIG_DIRECTORY_MODE}),
            'token_file':{'path':TOKEN_PATH,'expect':'ABSENT','uid':0,'gid':0,'mode_octal':'%04o'%TOKEN_FILE_MODE,'links':1,
                          'content':'the value of the environment file, then one newline','size':'within 1-%d (a boolean, never the size)'%TOKEN_MAX_FILE_BYTES},
            'environment_file':{'path':deploy+'/'+ENV_FILE_NAME,'deploy_directory':deploy,'keys':list(TOKEN_KEYS),'value_grammar':TOKEN_VALUE_GRAMMAR,
                                'chain':'walked by this run, not signed'},
            'process':{'dumpable':0,'when':'first, before the deploy directory or the environment file is opened','core_dump':'none, to a file or through a pipe'},
            'token_days':list(TOKEN_DAYS),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'process_started':False,'activation':False,'value_in_receipt':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the reads before the creation
DEPLOY_CODES={'SYMLINK_COMPONENT':'DEPLOY_CHAIN_SYMLINK','COMPONENT_NOT_DIRECTORY':'DEPLOY_CHAIN_NOT_A_DIRECTORY','PATH_CHANGED':'DEPLOY_CHAIN_CHANGED_DURING_WALK',
              'CHAIN_ROW_UNSAFE':'DEPLOY_CHAIN_UNSAFE_ABOVE_THE_DEPLOY_DIRECTORY','CHAIN_ROW_WORLD_WRITABLE':'DEPLOY_CHAIN_WORLD_WRITABLE'}
ENV_CODES={'FILE_NOT_REGULAR':'ENV_FILE_NOT_REGULAR','FILE_TOO_LARGE':'ENV_FILE_TOO_LARGE','FILE_CHANGED_DURING_READ':'ENV_FILE_CHANGED_DURING_READ'}
def renamed(error,table):return Refused(table.get(str(error),str(error)))
def listed(code):return code if code is None or code in RECEIPT_CODES else UNLISTED_CODE

def chain_facts():
    return {'walked_without_following_a_link':None,'root_owned_and_not_group_or_other_writable_above_the_deploy_directory':None,
            'no_component_world_writable_without_sticky':None}
def environment_facts():
    return {'present':None,'regular':None,'not_readable_by_group_or_other':None,'not_world_writable':None,'single_link':None,
            'owner_root_or_the_deploy_directory_owner':None,'within_the_size_bound':None,'unchanged_during_read':None,
            'syntax_within_the_accepted_subset':None,'every_definition_plain':None,'names_defined':{key:None for key in TOKEN_KEYS},
            'definitions_agree':None,'value_grammar_met':None}

def deploy_chain(host,deploy,gate,facts):
    """The deploy directory, walked from "/" without following a link, and the rows as read judged by the family's rule
    with the deploy directory as the open root. Returns the held descriptor and the observed rows (which stay here)."""
    observed=[]
    try:fd=descend(host,deploy,gate,observed)
    except FileNotFoundError:raise Refused('DEPLOY_DIRECTORY_ABSENT') from None
    except Refused as error:raise renamed(error,DEPLOY_CODES) from None
    try:
        facts['walked_without_following_a_link']=True
        facts['root_owned_and_not_group_or_other_writable_above_the_deploy_directory']=all(row_root_safe(row) for row in observed[:-1])
        facts['no_component_world_writable_without_sticky']=not any(world_writable_without_sticky(row) for row in observed)
        try:validate_chain(observed,deploy,open_root=deploy)
        except Refused as error:raise renamed(error,DEPLOY_CODES) from None
        return fd,observed
    except BaseException:
        host.close(fd);raise

def environment_bytes(host,fd,owner,gate,facts):
    """The bytes of the environment file of the held deploy directory, read once, unchanged while read."""
    gate()
    try:named=host.lstat(ENV_FILE_NAME,fd)
    except FileNotFoundError:raise Refused('ENV_FILE_ABSENT') from None
    facts['present']=True
    need(stat.S_ISREG(named.st_mode),'ENV_FILE_NOT_REGULAR');facts['regular']=True
    facts['not_readable_by_group_or_other']=not named.st_mode&0o044          # the exposure as found: said, never a refusal
    need(not named.st_mode&0o002,'ENV_FILE_WORLD_WRITABLE');facts['not_world_writable']=True
    need(named.st_nlink==1,'ENV_FILE_LINKED');facts['single_link']=True      # no second name (a hard link) for these bytes
    need(named.st_uid in (0,owner),'ENV_FILE_OWNER_UNEXPECTED');facts['owner_root_or_the_deploy_directory_owner']=True
    try:raw,info=read_regular(host,ENV_FILE_NAME,fd,gate,MAX_ENV_FILE_BYTES)
    except FileNotFoundError:raise Refused('ENV_FILE_CHANGED_DURING_READ') from None
    except Refused as error:raise renamed(error,ENV_CODES) from None
    facts['within_the_size_bound']=True
    gate()
    try:after=host.lstat(ENV_FILE_NAME,fd)
    except FileNotFoundError:raise Refused('ENV_FILE_CHANGED_DURING_READ') from None
    need(stat_signature(info)==stat_signature(named)==stat_signature(after),'ENV_FILE_CHANGED_DURING_READ')
    facts['unchanged_during_read']=True
    return raw

def environment_token(raw,facts):
    """The parse, with its facts: which names were found and that the rules held (booleans only)."""
    found=token_definitions(raw);facts['syntax_within_the_accepted_subset']=True;facts['every_definition_plain']=True
    facts['names_defined']={key:any(name==key for name,_,_ in found) for key in TOKEN_KEYS}
    content=token_content(raw,found)
    facts['definitions_agree']=True;facts['value_grammar_met']=True
    return content


# ---------------------------------------------------------------- the creation, its readback and its withdrawal
def token_row():
    return {'path':TOKEN_PATH,'state':'NOT_ATTEMPTED','code':None,'errno':None,'created':False,'fsync_file':False,'fsync_directory':False,
            'device':None,'inode':None,'regular':None,'uid_0':None,'gid_0':None,'mode_0600':None,'single_link':None,'size_within_1_4096':None,
            'on_the_device_of_the_directory':None,'readback_same_inode':None,'readback_bytes_equal_what_was_written':None,
            'meets_the_supervisor_file_rules':None,'withdrawn':False,'withdrawal_code':None,'withdrawal_errno':None,'fsync_directory_after_withdrawal':False}

def metadata_facts(info,row,config):
    row.update(regular=stat.S_ISREG(info.st_mode),uid_0=info.st_uid==0,gid_0=info.st_gid==0,mode_0600=stat.S_IMODE(info.st_mode)==TOKEN_FILE_MODE,
               single_link=info.st_nlink==1,size_within_1_4096=1<=info.st_size<=TOKEN_MAX_FILE_BYTES,
               on_the_device_of_the_directory=info.st_dev==config.identity[0])
    row['meets_the_supervisor_file_rules']=all(row[key] for key in ('regular','uid_0','mode_0600','single_link','size_within_1_4096'))
    return row['meets_the_supervisor_file_rules'] and row['gid_0'] and row['on_the_device_of_the_directory']

def withdraw(fd,row,config,host,gate,state,code,error=None):
    """The one removal of this source: the file it created, after a later step failed, while the name still shows the
    inode of the descriptor held and that inode has one link. Anything else at the name is left in place."""
    row['code']=code
    if error is not None:row['errno']=number(error)
    row['state']='LEFT_UNVERIFIED'
    try:
        named=host.lstat(TOKEN_NAME,config.fd);held=host.fstat(fd)
        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:
            row['withdrawal_code']='TOKEN_NAME_NOT_THIS_RUNS_FILE';return row
        mutate(state,gate,lambda:host.unlink(TOKEN_NAME,config.fd))
    except Refused as error:
        row['withdrawal_code']=code_of(error,'GO_EXPIRED');return row
    except OSError as error:
        row.update(withdrawal_code='TOKEN_WITHDRAWAL_FAILED',withdrawal_errno=number(error));return row
    except Exception:
        if state.pending:state.unknown()
        row['withdrawal_code']='TOKEN_WITHDRAWAL_UNCERTAIN';return row
    row.update(withdrawn=True,state='WITHDRAWN_NOT_DURABLE')
    try:host.fsync(config.fd)
    except OSError as error:
        row.update(withdrawal_code='FSYNC_FAILED',withdrawal_errno=number(error));return row
    row.update(state='WITHDRAWN',fsync_directory_after_withdrawal=True);return row

def place_token(content,config,host,gate,state):
    """One exclusive create, the writes, fsync of the file, its metadata, fsync of the directory, the readback by
    descriptor. Returns the ledger row; never raises for a failure of the host (an interrupt or the death of the process
    is not caught)."""
    row=token_row();fd=None;view=memoryview(content)
    try:
        try:fd=mutate(state,gate,lambda:host.create(TOKEN_NAME,TOKEN_CREATE_FLAGS,TOKEN_FILE_MODE,config.fd))
        except Refused as error:
            row['code']=code_of(error,'GO_EXPIRED');return row
        except OSError as error:
            row.update(state='NOT_CREATED',errno=number(error),
                       code='TOKEN_FILE_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))
            return row
        except Exception:
            if state.pending:state.unknown()
            row.update(state='CREATE_UNCERTAIN',code='TOKEN_CREATE_UNCERTAIN');return row
        row['created']=True;row['state']='LEFT_UNVERIFIED'
        try:
            written=0
            try:
                while written<len(content):
                    size=mutate(state,gate,lambda:host.write(fd,view[written:]))
                    if type(size) is not int or size<=0:return withdraw(fd,row,config,host,gate,state,'TOKEN_WRITE_INCOMPLETE')
                    written+=size
            except Refused as error:
                row['code']=code_of(error,'GO_EXPIRED');return row
            except OSError as error:return withdraw(fd,row,config,host,gate,state,filesystem_code(error),error)
            try:host.fsync(fd);row['fsync_file']=True
            except OSError as error:return withdraw(fd,row,config,host,gate,state,'FSYNC_FAILED',error)
            try:
                info=host.fstat(fd);row.update(device=info.st_dev,inode=info.st_ino)
                if not (metadata_facts(info,row,config) and info.st_size==len(content)):
                    return withdraw(fd,row,config,host,gate,state,'TOKEN_METADATA_MISMATCH')
            except OSError as error:return withdraw(fd,row,config,host,gate,state,'TOKEN_STAT_FAILED',error)
            try:host.fsync(config.fd);row['fsync_directory']=True
            except OSError as error:return withdraw(fd,row,config,host,gate,state,'FSYNC_FAILED',error)
            # the readback: the directory proved again from "/", the name opened again without following a link
            try:config.verify(gate)
            except Refused as error:
                row['code']=code_of(error,'PARENT_REPLACED');return row
            try:
                raw,seen=read_regular(host,TOKEN_NAME,config.fd,gate,TOKEN_MAX_FILE_BYTES)
                row['readback_same_inode']=(seen.st_dev,seen.st_ino)==(info.st_dev,info.st_ino)
                row['readback_bytes_equal_what_was_written']=raw==content
                raw=None
                if not (row['readback_same_inode'] and row['readback_bytes_equal_what_was_written'] and metadata_facts(seen,row,config)):
                    return withdraw(fd,row,config,host,gate,state,'READBACK_MISMATCH')
            except Refused as error:
                if str(error) in ('GO_EXPIRED','CLOCK_REVERSED'):
                    row['code']=str(error);return row
                return withdraw(fd,row,config,host,gate,state,'READBACK_MISMATCH')
            except OSError as error:return withdraw(fd,row,config,host,gate,state,'READBACK_UNAVAILABLE',error)
            row.update(state='PLACED_VERIFIED',code=None);return row
        except Exception:
            # a failure that is neither an OS error nor a refusal (the call it interrupted is uncertain): the file of this
            # run is withdrawn by identity, as after any other failure
            if state.pending:state.unknown()
            return withdraw(fd,row,config,host,gate,state,'TOKEN_PLACEMENT_FAILED')
    finally:
        view.release()
        if fd is not None:
            try:host.close(fd)
            except Exception:pass

def left_by_this_run(row):
    if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED'):return 1
    return None if row['state']=='CREATE_UNCERTAIN' else 0


def _reduce_config(receipt):receipt['config_directory']={'rows_reduced_for_size':len((receipt.get('config_directory') or {}).get('rows') or [])}
REDUCTIONS=[('CONFIG_ROWS_REDUCED_TO_COUNT',_reduce_config)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    deploy=plan['deploy_directory']                           # pure: everything below reads the host
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    process={'dumpable_disabled':None}
    config_rows=[];chain=chain_facts();environment=environment_facts();precheck={'token_file_absent':None,'seconds_left_before_the_creation':None}
    pinned=[];held=[];buffers=[];token=[token_row()]
    def finish(status,outcome,code,extra):
        token[0].update(code=listed(token[0]['code']),withdrawal_code=listed(token[0]['withdrawal_code']))
        return seal(envelope(status,outcome,listed(code),dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),process=process,
            config_directory={'rows':config_rows,'pinned':bool(pinned)},deploy_chain=chain,environment_file=environment,precheck=precheck,
            token_file=token[0],objects_left_by_this_run=left_by_this_run(token[0]),pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the creation
        try:
            # first, before anything is opened: this process made non-dumpable and proved so (PROCESS_SCOPE)
            process['dumpable_disabled']=False
            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            config=Pinned(host,walk_pinned(host,plan['config_chain'],gate,config_rows),rows=plan['config_chain']);pinned.append(config)
            gate()
            try:host.lstat(TOKEN_NAME,config.fd)
            except FileNotFoundError:precheck['token_file_absent']=True
            else:
                precheck['token_file_absent']=False;raise Refused('TOKEN_FILE_PRESENT')
            fd,observed=deploy_chain(host,deploy,gate,chain);held.append(fd)
            raw=environment_bytes(host,fd,observed[-1]['uid'],gate,environment)
            content=environment_token(raw,environment);buffers.append(content);raw=None
            # The last refusals that cost nothing on the host: the time the creation and the readback may take, and the
            # configuration directory proved again from "/" just before the creation.
            left=gate();precheck['seconds_left_before_the_creation']=int(left)
            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            config.verify(gate)
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        token[0]=row=place_token(content,config,host,gate,state)
        stop=None if row['state']=='PLACED_VERIFIED' else (row['code'] or 'TOKEN_NOT_PLACED')
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for buffer in buffers:zero(buffer)
        for fd in held:
            try:host.close(fd)
            except Exception:pass
        for handle in pinned:
            try:handle.close()
            except Exception:pass
# ==== END OP_TOKEN_FROM_ENV ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
