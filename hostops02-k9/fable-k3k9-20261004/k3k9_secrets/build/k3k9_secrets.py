"""OP_K3K9_SECRETS: the secrets of the K9 daily phases, placed once under <K9 root>/secrets (root:root 0700, created
empty by K4 mode E0): provider.env (C3PO_EODHD_API_TOKEN, C3PO_FINNHUB_API_TOKEN, C3PO_FMP_API_TOKEN), risk-db.env
(C3PO_R2D2_RISK_DATABASE_URL) and emitter/password, every file root:root 0600, the directory emitter root:root 0700.

First of all, before anything of the host is looked at, it makes its own process non-dumpable (prctl PR_SET_DUMPABLE
0, read back 0 with PR_GET_DUMPABLE, through the core's dumps_disabled): no core dump of it, to a file or through a
pipe to a crash collector, can carry a value out. If that cannot be done and proved, it refuses with nothing changed.

The three provider tokens are copied in memory from the environment of the running container c3po-r2d2-worker-1,
whose ID the request signs, each from its prefixed or its unprefixed name (the two the settings accept; every one
present byte-equal): the root-private config.v2.json of the signed ID is read twice inside protected Python,
with root-only descriptor traversal, bounded strict JSON and comparison; no worker inspect subprocess. The database URL of the restricted reader and
the emitter password are copied in memory from the two files of September on the data volume
(/mnt/day-d-data/.r2d2-v2-risk-secrets/risk-database-url and
/mnt/day-d-data/.c3po-role-executor-20260908-r2/secret/password): "/", "/mnt" and the data volume (a mount point) equal
to their signed rows, then every directory below it and the file equal to signed identity rows (device, inode, owner,
mode, both change instants; never the size) before each is opened, never following a link; each file regular, with one
link, unchanged while read, and its content within a fixed grammar (the URL that of the restricted reader, with no
query or fragment). Both docker ps checks finish before the first file of September is opened; neither acquires
secret values. Everything is looked at before the
first creation; the secrets directory must be the signed one and empty.

Then one mkdir of emitter and three exclusive creates (O_CREAT|O_EXCL|O_NOFOLLOW, 0600 under umask 0077) relative to
held descriptors, each file written from a bytearray that is zeroed afterwards, fsynced, its metadata proved through
the descriptor, the directory fsynced, and the name opened again and proved by descriptor: the same inode, regular,
uid 0, gid 0, mode 0600, one link. The content is never read back, and no size, digest or length of any value, line or
file is computed for a receipt or reaches one. If a step after a creation fails, the file this run created is removed
again, and only while its name still shows the inode this run holds (an exception to rule 4 of the core, declared in
the signed scope). It never overwrites, renames, chmods, chowns or truncates anything, never reads a file of the deploy
tree, never runs anything but docker ps, and never activates anything. The receipt
carries listed codes, booleans and identity rows only. The caller authenticates exact request/authority/GO/source
bytes first.
No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='2db09adfefb4e19c4c4f860735283d6078e91017b24025b1f4a072b52d84d8e8'
CORE_PARTS={'core': '60e29427f42b500642fdf57568843d63f2437714c899d61d88bcee05e63ecd6b', 'runner': '5035383365ee928aa254c8db9157420564301eb2a9921ed4feae37ce29c71c71', 'docker': '4633cc6f20d268c7de91eddc1681a5cfc622aa2c8d559dbe1f39bc3fb6e4310d', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'files': '6b96ad64fe8ce5a9a2293b109964e069c2ad32169e7d421449da3f88516b60ba'}
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
# The one row that prints values of a container's environment (the secrets family's revision, CORE.md section 15): its
# template is fixed and signed, and it is started only through the helper of the same name, which parses what it
# prints into buffers it can zero. assemble.py admits it only in a writing source and only in its one exact shape.
SECRET_ENVIRONMENT_ROW='container_secret_environment'
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
            need(through==(SECRET_ENVIRONMENT_ROW if name==SECRET_ENVIRONMENT_ROW else TEMPLATE_AT_CALL_TIME if row['argv'][-1:]==['--format']
                           else STARTED_THROUGH[row['kind']])
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


# ---------------------------------------------------------------- the values of named entries of one container's environment
# The secrets family's revision (CORE.md section 15). One fixed template, which the row of COMMANDS carries as its own
# words and every scope therefore signs: for each entry of .Config.Env whose name (the text before the first "=") is one
# of the names, the entry as a JSON string and a newline. Nothing else of the environment is printed, and no fallback
# prints more. Only constructs that ran on the host: range over .Config.Env, split, index, eq, a variable declared inside
# the range, json, and literal text. JSON quoting means an entry whose value holds a newline or a quote cannot be read as
# another entry: such a value is refused, never split.
SECRET_ENVIRONMENT_MIDDLE='one container ID'
MAX_SECRET_NAMES=8
MAX_SECRET_VALUE_BYTES=4096
def secret_environment_format(names):
    """The template of the row container_secret_environment for these names (a tuple, sorted, no repeat)."""
    need(type(names) is tuple and 0<len(names)<=MAX_SECRET_NAMES and all(text(name,ENVIRONMENT_NAME) for name in names)
         and list(names)==sorted(set(names)),'SECRET_ENVIRONMENT_NAMES')
    return ('{{range .Config.Env}}{{$p := split . "="}}'+''.join('{{if eq (index $p 0) "%s"}}{{json .}}\n{{end}}'%name for name in names)
            +'{{end}}')

def zero_secret_values(values):
    """Best effort: every bytearray of a {name: bytearray} overwritten in place. Immutable copies (the bytes the docker CLI
    printed, the buffer the runner read them into) cannot be overwritten; they are only dropped."""
    for value in list((values or {}).values()):
        if type(value) is bytearray:
            for index in range(len(value)):value[index]=0

def secret_entries(raw,names):
    """{name: bytearray(value) or None} of the names present, from what the template printed: one line per entry,
    '"NAME=VALUE"', then the inspector's own newline (so every entry line ends with a newline before the last byte). A
    name absent from the environment is absent from the result; a name present at most once (SECRET_ENVIRONMENT_REPEATED,
    decided by the names alone). A value of 1 to MAX_SECRET_VALUE_BYTES bytes of printable ASCII without a quote or a
    backslash (so the JSON string holds the value's own bytes) is copied from a view of raw into a new bytearray; any
    other value is None. The parse never refuses for a value: what a refusal says depends on the names and the shape of
    the output only, never on a length or a character of a value; the caller judges the values and decides. On any
    refusal every bytearray made so far is zeroed. Constant codes only; no exception carries a byte of raw."""
    found={};view=memoryview(raw) if type(raw) is bytes else None
    try:
        need(view is not None and raw.endswith(b'\n'),'SECRET_ENVIRONMENT_SHAPE')
        prefixes={name:b'"'+name.encode('ascii')+b'=' for name in names};position=0;size=len(raw)-1
        while position<size:
            end=raw.find(b'\n',position,size);need(end>=0,'SECRET_ENVIRONMENT_SHAPE')
            line=view[position:end];matched=[name for name,prefix in prefixes.items() if line[:len(prefix)]==prefix]
            need(len(matched)==1 and line[-1:]==b'"','SECRET_ENVIRONMENT_SHAPE')
            name=matched[0];need(name not in found,'SECRET_ENVIRONMENT_REPEATED')
            value=line[len(prefixes[name]):-1]
            valid=0<len(value)<=MAX_SECRET_VALUE_BYTES and all(0x20<=byte<=0x7e and byte not in (0x22,0x5c) for byte in value)
            found[name]=bytearray(value) if valid else None;position=end+1
        return found
    except BaseException:
        zero_secret_values(found);raise
    finally:
        if view is not None:view.release()

def container_secret_environment(commands,target,names,docker_config=None):
    """The values of the named entries of one container's environment (by 64-hex ID), through the one fixed row
    container_secret_environment, whose template must be the one these names give. Returns {name: bytearray or None}
    of the names present (none, some or all of them; None for a value outside the bound or the characters); the
    caller zeroes them (zero_secret_values) in a finally. The values travel only on the docker CLI's standard output,
    never in an argv or an environment."""
    need(text(target,CONTAINER_ID),'CONTAINER_TARGET')
    row=COMMANDS[SECRET_ENVIRONMENT_ROW]
    need(row['tool']=='docker' and row['argv']==['container','inspect','--format',secret_environment_format(names)] and not row['tail']
         and row['kind']=='READ' and row['class']=='QUICK' and row['stdin'] is False,'COMMAND_KIND')
    return secret_entries(commands.output(SECRET_ENVIRONMENT_ROW,target,docker_config=docker_config,through=SECRET_ENVIRONMENT_ROW),names)


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

# ==== BEGIN OP_K3K9_SECRETS (this operation only) ====
OPERATION='GO_WRITE_HOSTOPS02_K3K9_SECRETS_01'
PHASE='WRITE_K9_SECRETS_ENVIRONMENT_FILES_AND_EMITTER_PASSWORD'
REQUEST_SCHEMA='WRITE_HOSTOPS02_K3K9_SECRETS_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_K3K9_SECRETS_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_K3K9_SECRETS_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_K3K9_SECRETS_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_K3K9_SECRETS_PLAN_V1'
SOURCE_NAME='k3k9_secrets.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The rows of the secrets directory come from the receipt of K4 mode E0, which creates it empty (PROPOSED name: the
# operation name the family's grammar gives to E0's stem HOSTOPS02_K4_E0); the ID of the running worker from the epoch
# readback (K11 POST, M3r) of the same boot.
# The identity rows of the files of September and of the directories that hold them come from the K9R TREE read, mode
# TREE, of the same boot (an lstat of exactly the five paths of SOURCE_PATHS: no content).
K4_E0_OPERATION='GO_WRITE_HOSTOPS02_K4_E0_01'
EPOCH_READBACK_OPERATION='GO_READONLY_HOSTOPS02_EPOCH_READBACK_01'
K9_TREE_OPERATION='GO_READONLY_HOSTOPS02_K9_PHASE_READ_01'
EVIDENCE_OPERATIONS=(K4_E0_OPERATION,EPOCH_READBACK_OPERATION,K9_TREE_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='K9_SECRETS_PLACED_METADATA_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_SEE_SECRET_FILE_STATES'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_SECRET_FILES_MAY_EXIST'
PLAN_KEYS=frozenset(('secrets_chain','data_volume_chain','source_rows','worker_container_id','evidence_boot_id_sha256'))

# ---- the constants of this operation. A request cannot move any of them: they are bytes of the signed source.
# PLACEMENT: decision N-8 of the co-auditor (W/codex-n8-placement-20261004.txt, sha256 d30f7f90...c2c53, by command):
# the K9 root under /var/lib/c3po, a chain controlled by root alone (no open root, no ancestor owned by uid 1000, none
# writable by group or other, no link), every new directory root:root 0700; /var/lib/c3po is created by K4 mode E0 with
# its own signed effect and is not presumed here: the request signs the rows of the whole chain. The one place where the
# K9 root is named; a change of placement is a change of this line, a new seal and a new review.
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'                                     # N-8 (Codex), not under the data volume
# The open root of the two walks of the files of September ONLY (a read of a source, never the K9 tree): the data
# volume, owned by uid 1000. Its chain from "/" is signed (data_volume_chain: "/", "/mnt", "/mnt/day-d-data", from the
# receipt of K4 mode E0, which signs the same rows as the parent of the source root) and each walk must find those rows;
# the owner a September file may have besides root is the signed owner of the data volume. What crosses uid 1000 is
# DESIGN.md section 5.
SOURCE_OPEN_ROOT='/mnt/day-d-data'
K9_SECRETS_DIRECTORY=K9_ROOT+'/secrets'
K9_SECRETS_DIRECTORY_MODE=0o700
K9_SECRET_FILE_MODE=0o600
K9_EMITTER_NAME='emitter'
K9_EMITTER_DIRECTORY=K9_SECRETS_DIRECTORY+'/'+K9_EMITTER_NAME
PROVIDER_ENV_NAME='provider.env'
RISK_DB_ENV_NAME='risk-db.env'
EMITTER_PASSWORD_NAME='password'
TARGET_PATHS=(K9_SECRETS_DIRECTORY+'/'+PROVIDER_ENV_NAME,K9_SECRETS_DIRECTORY+'/'+RISK_DB_ENV_NAME,K9_EMITTER_DIRECTORY+'/'+EMITTER_PASSWORD_NAME)
SECRET_CREATE_FLAGS=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
READBACK_FLAGS=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
# The provider tokens, read from the environment of the running worker of the compose project (service r2d2-worker),
# whose ID the request signs. The settings of the release accept two names for each token (c3po/backend/app/config.py
# lines 107, 111 and 113 at dd4ec4bb: AliasChoices("C3PO_<X>", "<X>"), the first present winning), and the release's
# .env.example defines the unprefixed ones; the worker receives them from ../.env (compose.yml, env_file). Both names
# are read; every one present must hold the same bytes (the token placement's rule D11: no choosing which one wins), and
# provider.env holds the prefixed name, which the K9 containers' settings take first.
WORKER_CONTAINER_NAME='c3po-r2d2-worker-1'
PROVIDER_TOKEN_NAMES=(('C3PO_EODHD_API_TOKEN','EODHD_API_TOKEN'),('C3PO_FINNHUB_API_TOKEN','FINNHUB_API_TOKEN'),('C3PO_FMP_API_TOKEN','FMP_API_TOKEN'))
SECRET_ENVIRONMENT_NAMES=tuple(sorted(name for pair in PROVIDER_TOKEN_NAMES for name in pair))
# A token every reader takes as the same bytes (no quote, space, "#", "$" or backslash), one line, ASCII, 16 to 512
# characters (the grammar of the token placement, reviewed): the docker CLI reads an --env-file line literally.
PROVIDER_TOKEN_GRAMMAR=rb'[A-Za-z0-9._~+/=-]{16,512}'
# The database URL of the restricted reader role (E28: bound-package-rev3/operations/sources.py, role c3po_v2_risk_reader)
# and the password of the causal emitter role (E28: tonight_native.py, AUTHORITY_DIRECT_CHECK._read_private_password:
# exactly 64 bytes of [A-Za-z0-9_-], no newline). Both are copied from the files of September, by these fixed paths.
RISK_URL_DIRECTORY=SOURCE_OPEN_ROOT+'/.r2d2-v2-risk-secrets'
RISK_URL_NAME='risk-database-url'
RISK_URL_KEY='C3PO_R2D2_RISK_DATABASE_URL'
RISK_URL_MAX_FILE_BYTES=4096
RISK_URL_GRAMMAR=rb'postgresql://[\x21-\x7e]{1,4082}'     # with the scheme and one newline, at most RISK_URL_MAX_FILE_BYTES
RISK_URL_READER_PREFIX=b'postgresql://c3po_v2_risk_reader:'
EMITTER_SOURCE_DIRECTORY=SOURCE_OPEN_ROOT+'/.c3po-role-executor-20260908-r2/secret'
EMITTER_SOURCE_NAME='password'
EMITTER_PASSWORD_GRAMMAR=rb'[A-Za-z0-9_-]{64}'
# Everything the two walks cross below the data volume, in this order, each signed in source_rows with its identity,
# owner, mode and both change instants (never its size), and judged from the bytes: on the device of the data volume,
# owned by root or by the signed owner of the data volume, not writable by group or other (sticky or not).
SOURCE_PATHS=(RISK_URL_DIRECTORY,RISK_URL_DIRECTORY+'/'+RISK_URL_NAME,SOURCE_OPEN_ROOT+'/.c3po-role-executor-20260908-r2',EMITTER_SOURCE_DIRECTORY,
              EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME)
SOURCE_ROW_KEYS=('path','device','inode','uid','gid','mode','mtime_ns','ctime_ns')
EMITTER_PASSWORD_MAX_FILE_BYTES=64
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the first creation (the writes take milliseconds)
SECRET_FILE_STATES=('NOT_ATTEMPTED','NOT_CREATED','CREATE_UNCERTAIN','WITHDRAWN','WITHDRAWN_NOT_DURABLE','LEFT_UNVERIFIED','PLACED_VERIFIED')
# Every code a receipt of this source's run may carry (code, and code and withdrawal_code of each file row). The core's
# code_of() lets any text of the shape of a code through; here a code is a member of this list, and any other text is
# replaced by UNLISTED_CODE before the receipt is sealed.
SOURCE_PREFIXES=('RISK_URL','EMITTER_PASSWORD')
SOURCE_SUFFIXES=('COMPONENT_ABSENT','COMPONENT_DIVERGES','FILE_ABSENT','FILE_NOT_REGULAR','FILE_LINKED','FILE_DIVERGES','FILE_CHANGED_DURING_READ','FORMAT')
RECEIPT_CODES=frozenset((
    # the precheck: the process, the executor, the boot, the secrets directory (the core's walk)
    'WORKER_CONFIG_CHAIN_UNSAFE','WORKER_CONFIG_METADATA_UNSAFE','WORKER_CONFIG_CHANGED','WORKER_CONFIG_IDENTITY','WORKER_CONFIG_FORMAT','WORKER_CONFIG_UNREADABLE','PROCESS_DUMPABLE_NOT_DISABLED','EXECUTOR_IDENTITY','NOATIME_UNAVAILABLE','BOOT_ID_INVALID','EVIDENCE_FROM_EARLIER_BOOT','PARENT_MISSING',
    'PARENT_UNREADABLE','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_CHANGED_DURING_WALK','PARENT_IDENTITY_MISMATCH','PARENT_REPLACED',
    'SECRETS_DIRECTORY_NOT_EMPTY','ENTRY_LIMIT',
    # the worker and its environment (the core's docker helpers and runner)
    'WORKER_CONTAINER_MISMATCH','WORKER_NOT_RUNNING','WORKER_ENVIRONMENT_CHANGED_DURING_READ','PROVIDER_TOKEN_GRAMMAR','PROVIDER_TOKEN_ABSENT',
    'PROVIDER_TOKEN_DEFINITIONS_DISAGREE','SECRET_ENVIRONMENT_SHAPE','SECRET_ENVIRONMENT_REPEATED','SECRET_ENVIRONMENT_NAMES',
    'CONTAINER_TARGET','CONTAINER_METADATA_INVALID','CONTAINER_LIST_INVALID','COMMAND_FAILED','COMMAND_KIND','COMMAND_ARGUMENTS','COMMAND_STDIN',
    'COMMAND_VARIABLES','COMMAND_NOT_STARTED','COMMAND_NOT_STARTED_BUDGET','COMMAND_SKIPPED_AFTER_TIMEOUT','COMMAND_TIMEOUT','COMMAND_OUTPUT_LIMIT',
    'BINARY_UNAVAILABLE_OR_UNSAFE','DOCUMENT_SIZE','DOCUMENT_TYPE','DUPLICATE_KEY','JSON_INVALID','NONFINITE_JSON',
    # the database URL of the reader and the emitter password, as found in the files of September
    'RISK_DATABASE_URL_NOT_THE_RESTRICTED_READER','RISK_DATABASE_URL_WITH_PARAMETERS')+tuple(prefix+'_'+suffix for prefix in SOURCE_PREFIXES for suffix in SOURCE_SUFFIXES)+(
    # the last refusals before the first creation, and the clock at any point
    'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT','GO_EXPIRED','CLOCK_REVERSED','PRECHECK_OS_ERROR','PRECHECK_FAILED',
    # the directory emitter (the core's create_directory)
    'DIRECTORY_REQUEST_INVALID','DESTINATION_APPEARED_AFTER_PRECHECK','CREATED_OPEN_FAILED','CREATED_NAME_REPLACED','CREATED_METADATA_MISMATCH',
    'CREATED_STAT_FAILED','CREATED_LIST_FAILED','CREATED_NOT_EMPTY','FSYNC_FAILED','EMITTER_DIRECTORY_NOT_CREATED',
    # the creations, their readbacks and withdrawals
    'SECRET_FILE_APPEARED_AFTER_PRECHECK','FILESYSTEM_READ_ONLY','FILESYSTEM_FULL','FILESYSTEM_ACCESS_DENIED','FILESYSTEM_ERROR',
    'SECRET_FILE_CREATE_UNCERTAIN','SECRET_FILE_WRITE_INCOMPLETE','SECRET_FILE_METADATA_MISMATCH','SECRET_FILE_STAT_FAILED','READBACK_MISMATCH',
    'READBACK_UNAVAILABLE','SECRET_FILE_PLACEMENT_FAILED','SECRET_FILE_NOT_PLACED','SECRET_FILE_NAME_NOT_THIS_RUNS_FILE','SECRET_FILE_WITHDRAWAL_FAILED',
    'SECRET_FILE_WITHDRAWAL_UNCERTAIN','DIRECTORY_READBACK_MISMATCH'))
UNLISTED_CODE='UNLISTED_CODE'
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ')}
DOCKER_CONTAINER_ROOT='/var/lib/docker/containers'
WORKER_CONFIG_NAME='config.v2.json'
WORKER_CONFIG_MAX_BYTES=1048576
# The process itself, first of all (the token placement's D9, closed by its revision 3): before anything of the host is
# looked at, the core's NativeRead.not_dumpable() sets the dumpable attribute of this process to 0 and reads it back 0.
PROCESS_SCOPE={'dumpable':0,'how':'prctl(PR_SET_DUMPABLE, 0), then prctl(PR_GET_DUMPABLE) must answer 0 (the core\'s dumps_disabled)',
               'when':'first, before the executor, the boot, any directory, any container or any file is looked at',
               'core_dump':'none of this process, to a file or through a pipe to a crash collector: the kernel dumps no process that is not dumpable',
               'commands':'only docker ps; no worker inspect, no Env in a subprocess; config read and parsed in protected Python',
               'otherwise':'refused, nothing changed: PROCESS_DUMPABLE_NOT_DISABLED'}
FILE_ROWS=('provider_env','risk_db_env','emitter_password')
SCOPE_STATEMENT=('First of all, before anything of the host is looked at, makes its own process non-dumpable (prctl PR_SET_DUMPABLE 0, read back '
                 '0 with PR_GET_DUMPABLE); otherwise it refuses with nothing changed. Copies in memory the three provider tokens '
                 'C3PO_EODHD_API_TOKEN, C3PO_FINNHUB_API_TOKEN and C3PO_FMP_API_TOKEN from the environment of the running container '
                 +WORKER_CONTAINER_NAME+' whose ID the request signs, each from its prefixed or its unprefixed name (every one present '
                 'byte-equal; config.v2.json read twice inside protected Python through a root-only chain and compared; no docker inspect), '
                 'the database URL of the restricted reader role from '+RISK_URL_DIRECTORY+'/'
                 +RISK_URL_NAME+' and the emitter password from '+EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME+' (every component '
                 'below the data volume and both files equal to signed identity rows before each is opened, read once, unchanged while '
                 'read, within a fixed grammar; the URL with no query or fragment), and places them in the signed, empty '
                 'directory '+K9_SECRETS_DIRECTORY+' (root:root 0700, the K9 root root:root 0700, every component from "/" root-owned and '
                 'not writable by group or other, no open root): provider.env with the three tokens, risk-db.env with '+RISK_URL_KEY+
                 ', and the directory emitter (root:root 0700) with password, the same 64 bytes. One mkdir and three exclusive creates '
                 'relative to held descriptors, every file root:root 0600 with one link, fsync of each file and directory, and a readback '
                 'by descriptor of identity, owner, mode and links; the content is never read back. If a step after a creation fails, the '
                 'file this run created is removed while its name still shows the inode this run holds, and only then. On 2026-10-05 to '
                 '2026-10-10 UTC. Nothing that exists is overwritten, renamed, chmodded, chowned or truncated, nothing is activated, and '
                 'the receipt never carries a value, a digest, a length or a size of a value, of a line or of a file.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,
       'placement':{'k9_root':K9_ROOT,'status':'decision N-8 of the co-auditor (codex-n8-placement-20261004.txt, sha256 d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53)',
                    'k9_chain':'signed rows from "/", every row root-owned and not writable by group or other, no open root; the K9 root and secrets root:root 0700',
                    'source_open_root':SOURCE_OPEN_ROOT+' (the two walks of the files of September only)',
                    'secrets_directory':K9_SECRETS_DIRECTORY,'emitter_directory':K9_EMITTER_DIRECTORY,'files':list(TARGET_PATHS)},
       'secrets_directory':{'path':K9_SECRETS_DIRECTORY,'uid':0,'gid':0,'mode_octal':'%04o'%K9_SECRETS_DIRECTORY_MODE,
                            'expect':'present, signed rows from "/" (the K9 root root:root 0700 too, no open root), empty'},
       'emitter_directory':{'path':K9_EMITTER_DIRECTORY,'uid':0,'gid':0,'mode_octal':'0700','expect':'ABSENT','creation':'the core\'s create_directory'},
       'files':{'provider_env':{'path':TARGET_PATHS[0],'content':'one line NAME=VALUE per token, NAME the first of its pair, in this order, each ending in a newline',
                                'names':[list(pair) for pair in PROVIDER_TOKEN_NAMES],'from':'the environment of the running container '+WORKER_CONTAINER_NAME,
                                'rule':'for each token at least one of its two names present, every one present within the grammar and byte-equal',
                                'value_grammar':PROVIDER_TOKEN_GRAMMAR.decode('ascii')},
                'risk_db_env':{'path':TARGET_PATHS[1],'content':RISK_URL_KEY+'=VALUE and a newline','from':RISK_URL_DIRECTORY+'/'+RISK_URL_NAME,
                               'value_grammar':RISK_URL_GRAMMAR.decode('ascii'),'value_begins_with':RISK_URL_READER_PREFIX.decode('ascii'),
                               'file':'the value, then at most one newline'},
                'emitter_password':{'path':TARGET_PATHS[2],'content':'the 64 bytes of the source file, nothing added','from':EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME,
                                    'value_grammar':EMITTER_PASSWORD_GRAMMAR.decode('ascii')},
                'every_file':{'type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%K9_SECRET_FILE_MODE,'links':1,'umask_octal':'0077',
                              'creation':'one open O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC relative to the held descriptor of its directory',
                              'readback':'the name opened again O_RDONLY|O_NOFOLLOW by descriptor: the same inode, regular, uid 0, gid 0, mode 0600, one link; never the content',
                              'withdrawal':'only after its own creation succeeded and a later step failed, only while the name shows the inode this run holds '
                                           'with one link; never after the expiry of the GO or a replaced directory'}},
       'sources':{'paths':list(SOURCE_PATHS),'rows':'signed (source_rows, from the K9R TREE read of the same boot): device, inode, uid, gid, mode, '
                          'mtime_ns, ctime_ns, never the size; on the device of '+SOURCE_OPEN_ROOT+', owned by root or by its signed owner, '
                          'not writable by group or other',
                  'walk':'"/", "/mnt", '+SOURCE_OPEN_ROOT+' equal to data_volume_chain (a mount point), then each component below it '
                         'compared by lstat with its signed row before it is opened, without following a link, and again by descriptor',
                  'file':'regular, one link, its lstat equal to its signed row before it is opened, unchanged while read; whether group or '
                         'other may read it is reported, never refused'},
       'exceptions_to_the_core':['rule 4 (nothing is removed but the temporary of this run once its identity is proved): this source may remove '
                                 'the final name of one of its three files, and only the file this run created, after a later step of this run '
                                 'failed, while the name shows the inode this run holds with one link; never after the expiry of the GO, never '
                                 'after its directory was found replaced',
                                 'rule 5 and 6: the fixed config.v2.json of the signed worker ID is read only in protected Python, root-only descriptor chain, root:root 0600, twice, bounded strict JSON; no CLI worker inspect or secret row is available'],
       'process':PROCESS_SCOPE,
       'receipt_never':['a value','a digest of a value, of a line or of a file','a length of a value or of a line','the size of a file','any byte of a source file'],
       'receipt_codes':sorted(RECEIPT_CODES),'receipt_code_otherwise':UNLISTED_CODE,
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[DOCKER_CONTAINER_ROOT+'/<signed worker ID>/'+WORKER_CONFIG_NAME+' (protected Python only; in memory)',BOOT_ID_PATH,RISK_URL_DIRECTORY+'/'+RISK_URL_NAME+' (in memory)',EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME+' (in memory)'],
       'never':['overwrite','chmod','chown','rename','truncate','removal of anything but a file this run created','a read of the deploy tree or of its .env',
                'docker exec','docker run','compose','systemctl','a shell','a network connection opened by this process','activation','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS,'risk_url_file_bytes':RISK_URL_MAX_FILE_BYTES,
                 'emitter_password_file_bytes':EMITTER_PASSWORD_MAX_FILE_BYTES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the signed docker reads, the creating calls."""


def listed(code):return code if code is None or code in RECEIPT_CODES else UNLISTED_CODE

def zero(buffer):
    """Best effort: a bytearray that held a value is overwritten in place (DESIGN.md, section 8)."""
    if type(buffer) is bytearray:
        for index in range(len(buffer)):buffer[index]=0


def validate_plan(plan):
    rows=validate_chain(plan['secrets_chain'],K9_SECRETS_DIRECTORY,receives_entry=True)      # no open root: every row root-owned, not group- or other-writable
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),'CHAIN_ROW_NOT_ROOT_GROUP')
    need((rows[-2]['uid'],rows[-2]['gid'],rows[-2]['mode'])==(0,0,K9_SECRETS_DIRECTORY_MODE),'K9_ROOT_NOT_ROOT_0700')
    need((rows[-1]['uid'],rows[-1]['gid'],rows[-1]['mode'])==(0,0,K9_SECRETS_DIRECTORY_MODE),'SECRETS_DIRECTORY_NOT_ROOT_0700')
    volume=validate_chain(plan['data_volume_chain'],SOURCE_OPEN_ROOT,open_root=SOURCE_OPEN_ROOT)     # "/" and "/mnt" root-owned and closed
    need(mount_point_of(volume)==SOURCE_OPEN_ROOT,'DATA_VOLUME_NOT_A_MOUNT_POINT')
    sources=plan['source_rows']
    need(type(sources) is list and len(sources)==len(SOURCE_PATHS)
         and all(type(row) is dict and set(row)==set(SOURCE_ROW_KEYS) and row['path']==path and integer(row['device']) and integer(row['inode'],1)
                 and integer(row['uid']) and integer(row['gid']) and integer(row['mode'],0,0o7777) and integer(row['mtime_ns']) and integer(row['ctime_ns'])
                 for row,path in zip(sources,SOURCE_PATHS)),'SOURCE_ROWS_INVALID')
    need(all(row['device']==volume[-1]['device'] for row in sources),'SOURCE_ROWS_OFF_THE_DATA_VOLUME')
    need(all(not row['mode']&0o022 for row in sources),'SOURCE_ROWS_WRITABLE_BY_GROUP_OR_OTHER')
    need(all(row['uid'] in (0,volume[-1]['uid']) for row in sources),'SOURCE_ROWS_OWNER_UNEXPECTED')
    need(text(plan['worker_container_id'],CONTAINER_ID),'WORKER_CONTAINER_UNBOUND')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    return {'operation':OPERATION,'k9_root':K9_ROOT,'placement':'N-8',
            'secrets_directory':dict(chain_effects(plan['secrets_chain']),required={'uid':0,'gid':0,'mode_octal':'0700','entries':0,'k9_root':'root:root 0700','open_root':None}),
            'creates':{'directory':{'path':K9_EMITTER_DIRECTORY,'uid':0,'gid':0,'mode_octal':'0700'},
                       'files':[{'path':path,'uid':0,'gid':0,'mode_octal':'0600','links':1} for path in TARGET_PATHS]},
            'values':{'worker_config':{'root':DOCKER_CONTAINER_ROOT,'leaf':WORKER_CONFIG_NAME,'max_bytes':WORKER_CONFIG_MAX_BYTES,'root_only':True,'private_mode':'0600','no_cli_inspect':True},'provider_env':{'names':[list(pair) for pair in PROVIDER_TOKEN_NAMES],'from_container':WORKER_CONTAINER_NAME,
                                      'container_id':plan['worker_container_id']},
                      'data_volume':dict(chain_effects(plan['data_volume_chain']),open_root_of='the two walks of the files of September only'),
                      'source_rows_sha256':sha(canonical(plan['source_rows'])),
                      'risk_db_env':{'name':RISK_URL_KEY,'from_file':RISK_URL_DIRECTORY+'/'+RISK_URL_NAME},
                      'emitter_password':{'from_file':EMITTER_SOURCE_DIRECTORY+'/'+EMITTER_SOURCE_NAME}},
            'process':{'dumpable':0,'when':'first, before anything of the host is looked at'},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':False,'activation':False,'value_in_receipt':False,'size_or_digest_in_receipt':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the worker: the three tokens, in memory
def worker_facts():
    return {'one_container_with_the_name':None,'id_equal_signed':None,'running':None,'names_present':None,'grammar_met':None,'read_twice_equal':None}

def token_values(host,gate,worker):
    """Read only this signed ID's root-private engine config in the protected Python process. No inspect subprocess.
    The config is implementation-specific: absence or a different data-root is a refusal, never a CLI fallback."""
    need(text(worker,CONTAINER_ID),'CONTAINER_TARGET')
    need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED')
    held=None;raw=None;body=None;failed=None
    try:
        observed=[];path=DOCKER_CONTAINER_ROOT+'/'+worker
        fd=descend(host,path,gate,observed)
        held=Pinned(host,fd,rows=observed)
        need(all(row['uid']==0 and row['gid']==0 and not row['mode']&0o022 for row in observed),'WORKER_CONFIG_CHAIN_UNSAFE')
        need(observed[-1]['mode']==0o700,'WORKER_CONFIG_CHAIN_UNSAFE')
        gate();named=host.lstat(WORKER_CONFIG_NAME,held.fd)
        need(stat.S_ISREG(named.st_mode) and named.st_uid==0 and named.st_gid==0 and named.st_nlink==1
             and stat.S_IMODE(named.st_mode)==0o600,'WORKER_CONFIG_METADATA_UNSAFE')
        raw,info=read_regular(host,WORKER_CONFIG_NAME,held.fd,gate,WORKER_CONFIG_MAX_BYTES)
        need((info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink,info.st_mtime_ns,info.st_ctime_ns)==
             (named.st_dev,named.st_ino,named.st_uid,named.st_gid,named.st_mode,named.st_nlink,named.st_mtime_ns,named.st_ctime_ns),'WORKER_CONFIG_CHANGED')
        gate();after=host.lstat(WORKER_CONFIG_NAME,held.fd)
        need((after.st_dev,after.st_ino,after.st_mtime_ns,after.st_ctime_ns)==
             (info.st_dev,info.st_ino,info.st_mtime_ns,info.st_ctime_ns),'WORKER_CONFIG_CHANGED')
        held.verify(gate)
        body=strict(raw,WORKER_CONFIG_MAX_BYTES)
        need(type(body) is dict and body.get('ID')==worker and body.get('Name')=='/'+WORKER_CONTAINER_NAME,'WORKER_CONFIG_IDENTITY')
        config=body.get('Config');need(type(config) is dict and type(config.get('Env')) is list,'WORKER_CONFIG_FORMAT')
        entries=config['Env'];need(len(entries)<=1024 and all(type(x) is str and '=' in x for x in entries),'WORKER_CONFIG_FORMAT')
        selected=[x for x in entries if x.split('=',1)[0] in SECRET_ENVIRONMENT_NAMES]
        rendered=b''.join(json.dumps(x,ensure_ascii=True).encode('ascii')+b'\n' for x in selected)+b'\n'
        need(len(rendered)<=65536,'PROVIDER_TOKEN_GRAMMAR')
        return secret_entries(rendered,SECRET_ENVIRONMENT_NAMES)
    except Exception as error:
        failed=str(error) if isinstance(error,Refused) and str(error) in RECEIPT_CODES else 'WORKER_CONFIG_UNREADABLE'
    finally:
        raw=None;body=None
        if held is not None:held.close()
    # Outside the exception handler: neither exception context nor an exception message retains secret JSON.
    raise Refused(failed) from None

def provider_content(commands,worker,facts,buffers):
    """The content of provider.env in a new bytearray: one line C3PO_<X>=VALUE per token, in the order of
    PROVIDER_TOKEN_NAMES. For each token at least one of its two names is present, every value present meets the grammar
    and all are byte-equal. The six names are read twice through the fixed row and compared (presence and bytes); every
    buffer is registered for zeroing. The facts are said only of an accepted read, so a refusal says nothing of a
    value but its code."""
    listed_rows=[row for row in container_list(commands) if row['name']==WORKER_CONTAINER_NAME]
    facts['one_container_with_the_name']=len(listed_rows)==1
    facts['id_equal_signed']=len(listed_rows)==1 and listed_rows[0]['id']==worker
    need(facts['one_container_with_the_name'] and facts['id_equal_signed'],'WORKER_CONTAINER_MISMATCH')
    facts['running']=listed_rows[0]['state']=='running'
    need(facts['running'],'WORKER_NOT_RUNNING')
    first=token_values(commands.host,commands.gate,worker);buffers.extend(first.values())
    # Each rule over every token before the next rule, so that the code is decided by the presence of names first, then
    # by the grammar, then by the equality: never by which value happens to come first, or by its length.
    need(all(any(name in first for name in pair) for pair in PROVIDER_TOKEN_NAMES),'PROVIDER_TOKEN_ABSENT')
    need(all(value is not None and re.fullmatch(PROVIDER_TOKEN_GRAMMAR,value) is not None for value in first.values()),'PROVIDER_TOKEN_GRAMMAR')
    chosen=[]
    for pair in PROVIDER_TOKEN_NAMES:
        present=[first[name] for name in pair if name in first]
        need(all(value==present[0] for value in present),'PROVIDER_TOKEN_DEFINITIONS_DISAGREE')
        chosen.append(present[0])
    second=token_values(commands.host,commands.gate,worker);buffers.extend(second.values())
    after=[row for row in container_list(commands) if row['name']==WORKER_CONTAINER_NAME]
    need(len(after)==1 and after[0]['id']==worker,'WORKER_CONTAINER_MISMATCH')
    need(after[0]['state']=='running','WORKER_NOT_RUNNING')
    facts.update(names_present={name:name in first for name in SECRET_ENVIRONMENT_NAMES},grammar_met=True,
                 read_twice_equal=sorted(first)==sorted(second) and all(first[name]==second[name] for name in first))
    need(facts['read_twice_equal'],'WORKER_ENVIRONMENT_CHANGED_DURING_READ')
    content=bytearray();buffers.append(content)
    for (name,_),value in zip(PROVIDER_TOKEN_NAMES,chosen):
        content.extend(name.encode('ascii'));content.extend(b'=');content.extend(value);content.extend(b'\n')
    return content


# ---------------------------------------------------------------- the files of September: read once, in memory
def source_facts():
    """Booleans of one file of September. unchanged_during_read and grammar_met are said together, and only of a content
    that is accepted: a file over the bound and a file outside the grammar leave the same facts and the same code, so
    the receipt does not say which (that would be a bound on its size)."""
    return {'components_as_signed':None,'present':None,'regular':None,'single_link':None,'file_as_signed':None,
            'not_readable_by_group_or_other':None,'unchanged_during_read':None,'grammar_met':None}

def as_signed(info,row):
    """An lstat or fstat equal to a signed row on every member the row has (the data volume's rows have no instants).
    Compared in memory; never the size."""
    seen={'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode),
          'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}
    return all(seen[key]==row[key] for key in seen if key in row)

def source_walk(host,prefix,rows,gate,facts):
    """"/" opened, then each component looked at with lstat and compared with its signed row BEFORE it is opened, then
    opened by the held descriptor without following a link and compared again through the new descriptor. Returns the
    descriptor of the last directory."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    gate();fd=host.open('/',flags)
    try:
        need(as_signed(host.fstat(fd),rows[0]),prefix+'_COMPONENT_DIVERGES')
        for row in rows[1:]:
            name=PurePosixPath(row['path']).name;gate()
            try:named=host.lstat(name,fd)
            except FileNotFoundError:raise Refused(prefix+'_COMPONENT_ABSENT') from None
            need(stat.S_ISDIR(named.st_mode) and as_signed(named,row),prefix+'_COMPONENT_DIVERGES')
            gate();child=host.open(name,flags,dir_fd=fd);host.close(fd);fd=child
            held=host.fstat(fd)
            need((held.st_dev,held.st_ino)==(named.st_dev,named.st_ino) and as_signed(held,row),prefix+'_COMPONENT_DIVERGES')
        facts['components_as_signed']=True
        return fd
    except BaseException:
        host.close(fd);raise

READ_CODES={'FILE_NOT_REGULAR':'FILE_DIVERGES','FILE_TOO_LARGE':'FORMAT','FILE_CHANGED_DURING_READ':'FILE_CHANGED_DURING_READ'}
def source_bytes(host,prefix,rows,limit,gate,facts):
    """The bytes of one file of September: the signed walk to its directory (the data volume's rows, then the rows of
    source_rows above it), the file's lstat equal to its signed row before it is opened, one read through the held
    descriptor, unchanged while read."""
    fd=source_walk(host,prefix,rows[:-1],gate,facts)
    try:
        name=PurePosixPath(rows[-1]['path']).name;gate()
        try:named=host.lstat(name,fd)
        except FileNotFoundError:raise Refused(prefix+'_FILE_ABSENT') from None
        facts['present']=True
        need(stat.S_ISREG(named.st_mode),prefix+'_FILE_NOT_REGULAR');facts['regular']=True
        need(named.st_nlink==1,prefix+'_FILE_LINKED');facts['single_link']=True
        need(as_signed(named,rows[-1]),prefix+'_FILE_DIVERGES');facts['file_as_signed']=True
        facts['not_readable_by_group_or_other']=not named.st_mode&0o044          # the exposure as found: said, never a refusal
        try:raw,info=read_regular(host,name,fd,gate,limit)
        except FileNotFoundError:raise Refused(prefix+'_FILE_CHANGED_DURING_READ') from None
        except Refused as error:
            code=str(error);raise Refused(prefix+'_'+READ_CODES[code] if code in READ_CODES else code) from None
        gate()
        try:after=host.lstat(name,fd)
        except FileNotFoundError:raise Refused(prefix+'_FILE_CHANGED_DURING_READ') from None
        need(stat_signature(info)==stat_signature(named)==stat_signature(after),prefix+'_FILE_CHANGED_DURING_READ')
        return raw
    finally:host.close(fd)

def risk_url_content(raw,facts,buffers):
    """C3PO_R2D2_RISK_DATABASE_URL=<the value>\\n in a new bytearray. The file holds the value and at most one newline."""
    view=memoryview(raw)
    try:
        value=view[:-1] if raw[-1:]==b'\n' else view
        need(re.fullmatch(RISK_URL_GRAMMAR,value) is not None,'RISK_URL_FORMAT')
        facts.update(unchanged_during_read=True,grammar_met=True)
        facts['userinfo_names_the_restricted_reader']=value[:len(RISK_URL_READER_PREFIX)]==RISK_URL_READER_PREFIX
        need(facts['userinfo_names_the_restricted_reader'],'RISK_DATABASE_URL_NOT_THE_RESTRICTED_READER')
        # libpq takes parameters from a query string (user=, service=, host=, options=, ...) over the userinfo: none at all
        facts['no_query_or_fragment']=re.search(rb'[?#]',value) is None                 # searched in the view: no copy
        need(facts['no_query_or_fragment'],'RISK_DATABASE_URL_WITH_PARAMETERS')
        content=bytearray();buffers.append(content)
        content.extend(RISK_URL_KEY.encode('ascii'));content.extend(b'=');content.extend(value);content.extend(b'\n')
        return content
    finally:view.release()

def emitter_password_content(raw,facts,buffers):
    """The 64 bytes of the source file in a new bytearray, nothing added."""
    need(re.fullmatch(EMITTER_PASSWORD_GRAMMAR,raw) is not None,'EMITTER_PASSWORD_FORMAT')
    facts.update(unchanged_during_read=True,grammar_met=True)
    content=bytearray(raw);buffers.append(content);return content


# ---------------------------------------------------------------- the creations, their readbacks and their withdrawals
def file_row(path):
    return {'path':path,'state':'NOT_ATTEMPTED','code':None,'errno':None,'created':False,'fsync_file':False,'fsync_directory':False,
            'device':None,'inode':None,'regular':None,'uid_0':None,'gid_0':None,'mode_0600':None,'single_link':None,
            'on_the_device_of_the_directory':None,'readback_same_inode':None,'readback_metadata_as_created':None,
            'withdrawn':False,'withdrawal_code':None,'withdrawal_errno':None,'fsync_directory_after_withdrawal':False}

def metadata_facts(info,row,directory):
    """Owner, mode, type and links of a created file through a descriptor; never its size."""
    row.update(regular=stat.S_ISREG(info.st_mode),uid_0=info.st_uid==0,gid_0=info.st_gid==0,mode_0600=stat.S_IMODE(info.st_mode)==K9_SECRET_FILE_MODE,
               single_link=info.st_nlink==1,on_the_device_of_the_directory=info.st_dev==directory.identity[0])
    return all(row[key] for key in ('regular','uid_0','gid_0','mode_0600','single_link','on_the_device_of_the_directory'))

def withdraw(name,fd,row,directory,host,gate,state,code,error=None):
    """The one removal of this source: the file it created, after a later step failed, while the name still shows the
    inode of the descriptor held and that inode has one link. Anything else at the name is left in place."""
    row['code']=code
    if error is not None:row['errno']=number(error)
    row['state']='LEFT_UNVERIFIED'
    try:
        named=host.lstat(name,directory.fd);held=host.fstat(fd)
        if (named.st_dev,named.st_ino)!=(held.st_dev,held.st_ino) or named.st_nlink!=1:
            row['withdrawal_code']='SECRET_FILE_NAME_NOT_THIS_RUNS_FILE';return row
        mutate(state,gate,lambda:host.unlink(name,directory.fd))
    except Refused as error:
        row['withdrawal_code']=code_of(error,'GO_EXPIRED');return row
    except OSError as error:
        row.update(withdrawal_code='SECRET_FILE_WITHDRAWAL_FAILED',withdrawal_errno=number(error));return row
    except Exception:
        if state.pending:state.unknown()
        row['withdrawal_code']='SECRET_FILE_WITHDRAWAL_UNCERTAIN';return row
    row.update(withdrawn=True,state='WITHDRAWN_NOT_DURABLE')
    try:host.fsync(directory.fd)
    except OSError as error:
        row.update(withdrawal_code='FSYNC_FAILED',withdrawal_errno=number(error));return row
    row.update(state='WITHDRAWN',fsync_directory_after_withdrawal=True);return row

def readback(name,info,row,directory,host,gate):
    """The directory proved again from "/", the name opened again without following a link, and the new descriptor
    proved: the same inode, regular, root:root, 0600, one link. The content is not read."""
    directory.verify(gate);gate()
    fd=host.open(name,READBACK_FLAGS|host.noatime(),dir_fd=directory.fd)
    try:seen=host.fstat(fd)
    finally:host.close(fd)
    row['readback_same_inode']=(seen.st_dev,seen.st_ino)==(info.st_dev,info.st_ino)
    probe_row=file_row(row['path']);row['readback_metadata_as_created']=metadata_facts(seen,probe_row,directory)
    return row['readback_same_inode'] and row['readback_metadata_as_created']

def place_file(name,content,directory,host,gate,state,row):
    """One exclusive create, the writes from a view of the bytearray, fsync of the file, its metadata, fsync of the
    directory, the readback by descriptor. Fills and returns the row; never raises for a failure of the host (an
    interrupt or the death of the process is not caught)."""
    fd=None;view=memoryview(content)
    try:
        try:fd=mutate(state,gate,lambda:host.create(name,SECRET_CREATE_FLAGS,K9_SECRET_FILE_MODE,directory.fd))
        except Refused as error:
            row['code']=code_of(error,'GO_EXPIRED');return row
        except OSError as error:
            row.update(state='NOT_CREATED',errno=number(error),
                       code='SECRET_FILE_APPEARED_AFTER_PRECHECK' if error.errno==errno.EEXIST else filesystem_code(error))
            return row
        except Exception:
            if state.pending:state.unknown()
            row.update(state='CREATE_UNCERTAIN',code='SECRET_FILE_CREATE_UNCERTAIN');return row
        row['created']=True;row['state']='LEFT_UNVERIFIED'
        try:
            written=0
            try:
                while written<len(content):
                    size=mutate(state,gate,lambda:host.write(fd,view[written:]))
                    if type(size) is not int or size<=0:return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_WRITE_INCOMPLETE')
                    written+=size
            except Refused as error:
                row['code']=code_of(error,'GO_EXPIRED');return row
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,filesystem_code(error),error)
            try:host.fsync(fd);row['fsync_file']=True
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'FSYNC_FAILED',error)
            try:
                info=host.fstat(fd);row.update(device=info.st_dev,inode=info.st_ino)
                if not metadata_facts(info,row,directory):return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_METADATA_MISMATCH')
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_STAT_FAILED',error)
            try:host.fsync(directory.fd);row['fsync_directory']=True
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'FSYNC_FAILED',error)
            try:
                if not readback(name,info,row,directory,host,gate):return withdraw(name,fd,row,directory,host,gate,state,'READBACK_MISMATCH')
            except Refused as error:
                if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','PARENT_REPLACED'):
                    row['code']=str(error);return row
                return withdraw(name,fd,row,directory,host,gate,state,'READBACK_MISMATCH')
            except OSError as error:return withdraw(name,fd,row,directory,host,gate,state,'READBACK_UNAVAILABLE',error)
            row.update(state='PLACED_VERIFIED',code=None);return row
        except Exception:
            # neither an OS error nor a refusal (the call it interrupted is uncertain): the file of this run is withdrawn
            # by identity, as after any other failure
            if state.pending:state.unknown()
            return withdraw(name,fd,row,directory,host,gate,state,'SECRET_FILE_PLACEMENT_FAILED')
    finally:
        view.release()
        if fd is not None:
            try:host.close(fd)
            except Exception:pass

def left_by_this_run(directory_row,rows):
    """Objects this run created and left on the host: the directory emitter and the files placed or left; None when a
    creation itself was uncertain."""
    if directory_row['state']=='NOT_ATTEMPTED' and all(row['state']=='NOT_ATTEMPTED' for row in rows):return 0
    if any(row['state']=='CREATE_UNCERTAIN' for row in rows):return None
    created=0 if directory_row['state'] in ('NOT_ATTEMPTED','NOT_CREATED') else 1
    return created+sum(1 for row in rows if row['state'] in ('PLACED_VERIFIED','LEFT_UNVERIFIED'))


def _reduce_rows(receipt):receipt['secrets_directory']={'rows_reduced_for_size':len((receipt.get('secrets_directory') or {}).get('rows') or [])}
REDUCTIONS=[('SECRETS_ROWS_REDUCED_TO_COUNT',_reduce_rows)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    worker=plan['worker_container_id']                        # pure: everything below reads the host
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate)
    process={'dumpable_disabled':None}
    secrets_rows=[];secrets={'rows':secrets_rows,'pinned':False,'empty':None}
    workers=worker_facts();url=dict(source_facts(),userinfo_names_the_restricted_reader=None,no_query_or_fragment=None);password=source_facts()
    precheck={'seconds_left_before_the_first_effect':None}
    pinned=[];handles={};buffers=[]
    directory=[{'key':'EMITTER','path':K9_EMITTER_DIRECTORY,'state':'NOT_ATTEMPTED','code':None,'errno':None,'observed':None,
                'fsync_directory':False,'fsync_parent':False}]
    rows=[file_row(path) for path in TARGET_PATHS];readbacks={'secrets_directory':None,'emitter_directory':None}
    def finish(status,outcome,code,extra):
        for row in rows:row.update(code=listed(row['code']),withdrawal_code=listed(row['withdrawal_code']))
        directory[0]['code']=listed(directory[0]['code'])
        return seal(envelope(status,outcome,listed(code),dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),process=process,
            secrets_directory=secrets,worker=workers,risk_url_source=url,emitter_password_source=password,precheck=precheck,
            emitter_directory=directory[0],files=dict(zip(FILE_ROWS,rows)),directory_readbacks={key:listed(value) for key,value in readbacks.items()},
            objects_left_by_this_run=left_by_this_run(directory[0],rows),pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the first creation
        try:
            # first, before anything of the host is looked at: this process made non-dumpable and proved so (PROCESS_SCOPE)
            process['dumpable_disabled']=False
            need(host.not_dumpable() is True,'PROCESS_DUMPABLE_NOT_DISABLED');process['dumpable_disabled']=True
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            target=Pinned(host,walk_pinned(host,plan['secrets_chain'],gate,secrets_rows),rows=plan['secrets_chain']);pinned.append(target)
            secrets['pinned']=True
            secrets['empty']=count_entries(host,target.fd,gate)==0
            need(secrets['empty'],'SECRETS_DIRECTORY_NOT_EMPTY')
            # the provider tokens first: the docker commands start before any file of September is in this process
            provider=provider_content(commands,worker,workers,buffers)
            volume,sources=plan['data_volume_chain'],plan['source_rows']
            risk=risk_url_content(source_bytes(host,'RISK_URL',volume+sources[0:2],RISK_URL_MAX_FILE_BYTES,gate,url),url,buffers)
            emitter=emitter_password_content(source_bytes(host,'EMITTER_PASSWORD',volume+sources[2:5],EMITTER_PASSWORD_MAX_FILE_BYTES,gate,password),password,buffers)
            # The last refusals that cost nothing on the host: the time the creations and readbacks may take, and the
            # secrets directory proved again from "/" just before the first creation.
            left=gate();precheck['seconds_left_before_the_first_effect']=int(left)
            need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            target.verify(gate)
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        directory[0]=create_directory('EMITTER',K9_EMITTER_DIRECTORY,0o700,target,host,gate,state,handles)
        stop=None if directory[0]['state']=='CREATED_DURABLE' else (directory[0]['code'] or 'EMITTER_DIRECTORY_NOT_CREATED')
        if stop is None:
            for row,name,content,where in ((rows[0],PROVIDER_ENV_NAME,provider,target),(rows[1],RISK_DB_ENV_NAME,risk,target),
                                           (rows[2],EMITTER_PASSWORD_NAME,emitter,handles['EMITTER'])):
                place_file(name,content,where,host,gate,state,row)
                if row['state']!='PLACED_VERIFIED':
                    stop=row['code'] or 'SECRET_FILE_NOT_PLACED';break
        if stop is None:
            # both directories read back from "/": identity, owner, mode, and exactly the entries this run put in them
            readbacks['secrets_directory']=readback_directory(K9_SECRETS_DIRECTORY,K9_SECRETS_DIRECTORY_MODE,target,host,gate,3)
            readbacks['emitter_directory']=readback_directory(K9_EMITTER_DIRECTORY,0o700,handles['EMITTER'],host,gate,1)
            if readbacks['secrets_directory'] or readbacks['emitter_directory']:stop='DIRECTORY_READBACK_MISMATCH'
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for buffer in buffers:zero(buffer)
        for handle in list(handles.values())+pinned:
            try:handle.close()
            except Exception:pass
# ==== END OP_K3K9_SECRETS ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
