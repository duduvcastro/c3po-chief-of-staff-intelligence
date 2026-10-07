"""OP_ACTIVATE: the activation of the compose worker for epoch R2D2-V2-SHADOW-2026-10-05, once, on the first session day.

What the activation of 2026-09-28 did, in the HOSTOPS02 family: under the deployment lock it creates one private
directory in a signed parent of the data volume, delivers into it the signed live policy and a compose override that
sets four names of the environment of the service r2d2-worker (live policy file and hash, release file and hash),
and recreates that one service with the file list of the deploy plus the override. Everything is looked at before
the first creation: the executor, the boot of the evidence, the four pinned directories, the release an earlier
operation installed (read and compared by hash), the deployed revision, the maintenance pin, the worker and its
image, the environment file and the compose file of the project, the render of the project with the override on
standard input, the lock (waited for at most the signed seconds and never past the point where the recreate would no
longer fit), and under it: no security reboot pending, every held directory still reached by its name, nothing changed
since the first look, no container left by an interrupted recreate of the service, room on the data volume. Every
effect is read back inside the run: the files by descriptor, the worker twice with a fixed pause between, its
environment inside a docker template that prints booleans only, every other container by ID, the environment file and
the compose file by signature and by a hash that stays in memory, the release by its name. It never runs docker exec,
a shell, a systemctl verb or a pull, never overwrites, renames, chmods, chowns or removes anything but its own
temporary, and prints no value it read from an environment (the four signed values of the override are shown in the
effects). A run that changed anything and did not finish is PARTIAL, never a refusal, and says which of its effects
exist. The caller authenticates exact request/authority/GO/source bytes first. No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
CORE_PARTS={'core': 'ecf72edaf2bae478186e642bc93804bd567384c5d13dfab2bb4c4d55d00eef7a', 'runner': '2a1cc5bc73a0d456eb596aea65caaffcf7dd3834cbbd844a02a69486bbdacaa7', 'docker': '4602f6f07a4502a3decec99cd415737efb429e3b1a188b368939a090bc3b3aa5', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'files': '6b96ad64fe8ce5a9a2293b109964e069c2ad32169e7d421449da3f88516b60ba', 'lock': '17099e318c9f7df61b570563fba45868ff6e0b884120265a01572bcb7d2ef554'}
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

# ==== BEGIN OP_ACTIVATE (this operation only) ====
import base64

OPERATION='GO_WRITE_HOSTOPS02_ACTIVATE_01'
PHASE='WRITE_ACTIVATE_WORKER_RELEASE_AND_LIVE_POLICY'
REQUEST_SCHEMA='WRITE_HOSTOPS02_ACTIVATE_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_ACTIVATE_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_ACTIVATE_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_ACTIVATE_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_ACTIVATE_PLAN_V1'
SOURCE_NAME='activate.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False                  # no systemd unit is switched: the recreate of a compose service is not an activation in the family's sense
DATE_CLASS='WRITE_FIRST_SESSION'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=('GO_READONLY_HOSTOPS02_EPOCH_READBACK_01',)        # the epoch readback (K11): its dry run of the same boot gives the rows this request signs
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='ACTIVATE_WORKER_RECREATED_AND_VERIFIED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
# The three partial outcomes of a run that returned its receipt (PARTIAL_OUTCOME itself is what an escaped run says).
OBJECTS_ONLY_OUTCOME='PARTIAL_OBJECTS_LEFT_WORKER_NOT_RECREATED'
NOT_VERIFIED_OUTCOME='PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED'
UNCERTAIN_OUTCOME='PARTIAL_RECREATE_UNCERTAIN_REQUIRES_READBACK'

# ---------------------------------------------------------------- the epoch, as the release code compiles it
EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'                                                        # r2d2_v2_epoch_assembler.py:9
EPOCH_REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'                                     # main at the release; .deploy-version and C3PO_BUILD_SHA
EPOCH_PACKAGE_SHA256='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'       # implementation package of that revision
RUNTIME_ORDER_SHA256='1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e'       # r2d2_v2_live_controller.py:30
EPOCH_FIRST_OPEN='2026-10-05T13:30:00+00:00'                                                  # open of the first session
EPOCH_LAST_CLOSE='2026-10-09T20:00:00+00:00'                                                  # close of the fifth
LIVE_POLICY_SCHEMA='R2D2_V2_LIVE_POLICY_V1'
MAX_POLICY_WINDOW_SECONDS=90*86400
MAX_POLICY_BYTES=16384
MAX_RELEASE_BYTES=65536                                                                       # what the worker accepts (r2d2_v2_shadow_worker.py:33)
MAX_ENV_FILE_BYTES=1048576
MAX_COMPOSE_FILE_BYTES=1048576
FREE_BYTES_FLOOR=1048576                  # bytes a non-root writer must still have on the filesystem of the live parent before the first creation (as install_release)
FREE_INODES_FLOOR=8                       # inodes, where the filesystem counts them: this run takes three
WORKER_SERVICE='r2d2-worker'
BUILD_KEY='C3PO_BUILD_SHA'
KEY_POLICY_FILE='C3PO_R2D2_V2_LIVE_POLICY_FILE'                                               # config.py:197 (env_prefix C3PO_, config.py:20)
KEY_POLICY_SHA='C3PO_R2D2_V2_LIVE_POLICY_SHA'                                                 # config.py:198
KEY_RELEASE_FILE='C3PO_R2D2_V2_SHADOW_RELEASE_FILE'                                           # config.py:207
KEY_RELEASE_SHA='C3PO_R2D2_V2_SHADOW_RELEASE_SHA'                                             # config.py:208
ACTIVATION_KEYS=(KEY_POLICY_FILE,KEY_POLICY_SHA,KEY_RELEASE_FILE,KEY_RELEASE_SHA)
# The layout of the deploy tree, as the pipeline's deploy job uses it (c3po-pipeline.yml:631-658, 743-746).
ENV_FILE_NAME='.env'
COMPOSE_FILE_NAME='compose.yml'
DEPLOY_VERSION_NAME='.deploy-version'
LOCK_RELATIVE_DIRECTORY='runtime/security'
LOCK_FILE_NAME='deployment.lock'
REBOOT_PENDING_PATH='/run/c3po-security/reboot.pending'
PIN_NAME='.r2d2-v2-pinned'                                                                    # scripts/c3po_security_guard.py: its existence is the whole test
STATUS_SUFFIX='.status.json'                                                                  # r2d2_v2_live_controller.py:274
# ---------------------------------------------------------------- the budget (seconds of the 60 a run has)
SETTLE_SECONDS=3                          # the one fixed pause, between the two readings of the new worker
SECOND_CHECK_RESERVE_SECONDS=2            # what must be left after the pause for the second reading
FILES_ALLOWANCE_SECONDS=1                 # the directory, the two files and their readback
UNDER_LOCK_ALLOWANCE_SECONDS=2            # the reads made again once the lock is held, before the first creation
RENDER_ALLOWANCE_FLOOR_SECONDS=3          # the render from the files is given twice what the first render took, at least this much

PLAN_KEYS=frozenset(('data_root','live_parent','directory_name','policy','override_name','release','worker','compose','deploy_directory','lock',
                     'evidence_boot_id_sha256'))
POLICY_KEYS=frozenset(('name','content_b64','sha256','bytes'))
RELEASE_KEYS=frozenset(('parent','directory_name','file_name','sha256','bytes'))
WORKER_KEYS=frozenset(('image_id','mount_target'))
COMPOSE_KEYS=frozenset(('project','env_file','files'))
LOCK_KEYS=frozenset(('directory','wait_seconds'))
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'one container name or ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then one container ID','QUICK','READ'),
          'render':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy, then the override on standard input as the last file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL,stdin=True),
          'render_files':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL),
          'recreate':command_row('docker',['compose'],'--project-name, --env-file, the compose file of the deploy and the delivered override file','RECREATE','EFFECT',tail=compose_up_tail(WORKER_SERVICE))}
SUCCESS_CRITERIA=['the recreate command returned 0',
                  'exactly one container carries the name of the service and it is not the container that was there before',
                  'the container that was there before no longer exists under any name',
                  'the new container is running with restart count 0 on the signed image, read twice with a fixed pause between; the second reading shows the same container and the same start instant',
                  'its environment carries the four signed names and the build revision with the signed values, compared inside a docker template that prints booleans',
                  'every other container is listed with the ID and the name it had under the lock before the recreate, and no other container appeared',
                  'the environment file and the compose file of the project are the same objects with the same bytes as at the first look (signature and a hash kept in memory)',
                  'the installed release is still reached by its name and is the same object with the signed bytes',
                  'the two delivered files and their directory are as delivered, and the lock file is still the one held in the directory still named']
SCOPE_STATEMENT=('Single shot, first session day of epoch R2D2-V2-SHADOW-2026-10-05 only. Under the deployment lock: creates one private directory in '
                 'the signed parent of the data volume, delivers into it the signed live policy and one compose override that sets four environment '
                 'names of the service r2d2-worker (live policy file and hash, release file and hash), and recreates that one service with the '
                 'compose file of the deploy plus that override: one docker compose up -d --no-deps --no-build --pull never --force-recreate. '
                 'The running worker container is stopped and replaced; no other container, no image, no unit and no existing file is changed. '
                 'Nothing that exists is overwritten, renamed, chmodded, chowned or removed, except the temporary of this run once its identity '
                 'is proved. No docker exec, no shell, no systemctl, no pull. No value read from a container, from the render or from the environment '
                 'file is printed, stored or put in an argv. The four signed values are written to the override and shown in the effects; with '
                 'the build revision they are compared inside a docker template, in whose argv they travel.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'budget':{'settle_seconds':SETTLE_SECONDS,'second_check_reserve_seconds':SECOND_CHECK_RESERVE_SECONDS,'files_allowance_seconds':FILES_ALLOWANCE_SECONDS,
                 'under_lock_allowance_seconds':UNDER_LOCK_ALLOWANCE_SECONDS,'render_allowance_floor_seconds':RENDER_ALLOWANCE_FLOOR_SECONDS,
                 'rule':'before the lock is asked for and again before the first creation: recreate class + reserve + render allowance + files + settle must be left'},
       'files':FILES_SCOPE,'lock':LOCK_SCOPE,'service':WORKER_SERVICE,'environment_names':list(ACTIVATION_KEYS),'build_name':BUILD_KEY,
       'epoch':{'name':EPOCH_NAME,'revision':EPOCH_REVISION,'package_sha256':EPOCH_PACKAGE_SHA256,'runtime_order_sha256':RUNTIME_ORDER_SHA256,
                'first_open':EPOCH_FIRST_OPEN,'last_close':EPOCH_LAST_CLOSE,'policy_schema':LIVE_POLICY_SCHEMA},
       'deploy_layout':{'environment_file':ENV_FILE_NAME,'compose_file':'<project>/'+COMPOSE_FILE_NAME,'deploy_version':DEPLOY_VERSION_NAME,
                        'lock':LOCK_RELATIVE_DIRECTORY+'/'+LOCK_FILE_NAME},
       'required_before_any_effect':{'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'maintenance_pin_present':'<data root>/'+PIN_NAME,
                                     'release':'installed by an earlier operation: a root:root 0700 directory holding a root:root 0600 regular file with one link whose bytes have the signed hash',
                                     'no_leftover_of_a_recreate':'no container named <anything>_<the worker container>: the temporary name compose gives while it replaces the container of a service',
                                     'free_space':'on the filesystem of the live parent, for a non-root writer: the bytes of limits.free_bytes_floor and, where inodes are counted, limits.free_inodes_floor',
                                     'unchanged_since_the_first_look':'under the lock: the deployed revision, the environment file, the compose file, the release, the worker; the release directory, the deploy tree, the project directory and the lock directory still reached by their names'},
       'success_criteria':SUCCESS_CRITERIA,
       'partial_outcomes':[OBJECTS_ONLY_OUTCOME,NOT_VERIFIED_OUTCOME,UNCERTAIN_OUTCOME,PARTIAL_OUTCOME],
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'the installed release (compared by hash)',DEPLOY_VERSION_NAME+' of the deploy tree',
                             'the environment file of the compose project: read into memory twice or more and compared with itself; no value, digest or size of it leaves the run',
                             'the compose file of the deploy: the same, never judged as text (the render is)',
                             'the files this run delivered (readback inside the run)',
                             'the status file the worker writes next to the policy, if it exists: two constant codes of it, informational'],
       'side_effects':['the worker container is stopped and replaced by a new one (new ID); what it held in memory is lost',
                       'the new worker writes its own status and journal files into the directory this run created',
                       'the deployment lock is held from before the first creation until the last readback'],
       'never':['overwrite','chmod','chown','rename','removal of anything but the temporary this run created','docker exec','a shell','systemctl',
                'a pull','a build','a second recreate','a change of the environment file or of the compose file','a network connection opened by this process'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,'policy_bytes':MAX_POLICY_BYTES,
                 'release_bytes':MAX_RELEASE_BYTES,'environment_file_bytes':MAX_ENV_FILE_BYTES,'compose_file_bytes':MAX_COMPOSE_FILE_BYTES,
                 'free_bytes_floor':FREE_BYTES_FLOOR,'free_inodes_floor':FREE_INODES_FLOOR,'lock_wait_seconds':MAX_LOCK_WAIT_SECONDS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles,NativeLock):
    """Everything this source can do to the host: the read primitives, the signed commands, the seven creating calls, the lock."""


# ---------------------------------------------------------------- what the plan says (pure)
def live_path(plan):return plan['live_parent'][-1]['path'].rstrip('/')+'/'+plan['directory_name']
def policy_path(plan):return live_path(plan)+'/'+plan['policy']['name']
def override_path(plan):return live_path(plan)+'/'+plan['override_name']
def release_directory_path(plan):return plan['release']['parent'][-1]['path'].rstrip('/')+'/'+plan['release']['directory_name']
def release_path(plan):return release_directory_path(plan)+'/'+plan['release']['file_name']
def deploy_path(plan):return plan['deploy_directory'][-1]['path']
def lock_path(plan):return plan['lock']['directory'][-1]['path']+'/'+LOCK_FILE_NAME
def pin_path(plan):return plan['data_root']+'/'+PIN_NAME
def worker_name(plan):return '%s-%s-1'%(plan['compose']['project'],WORKER_SERVICE)      # the name compose gives the one container of a service
def container_path(plan,path):
    """The path the worker sees for a host path of the data root, through its one bind of the data root."""
    return plan['worker']['mount_target']+path[len(plan['data_root']):]
def environment_of(plan):
    """The four names and values of the override: nothing here is free, each follows from another signed member."""
    return {KEY_POLICY_FILE:container_path(plan,policy_path(plan)),KEY_POLICY_SHA:plan['policy']['sha256'],
            KEY_RELEASE_FILE:container_path(plan,release_path(plan)),KEY_RELEASE_SHA:plan['release']['sha256']}
def override_of(plan):
    """The bytes of the compose override: one JSON object with the token shape of the override of 2026-09-28."""
    return json.dumps({'services':{WORKER_SERVICE:{'environment':environment_of(plan)}}},sort_keys=True).encode('ascii')

def chain_path(rows):
    need(type(rows) is list and rows and type(rows[-1]) is dict and type(rows[-1].get('path')) is str,'CHAIN_ROW_INVALID');return rows[-1]['path']
def signed_chain(rows,open_root,receives_entry=False):return validate_chain(rows,chain_path(rows),open_root,receives_entry)

def policy_instant(value):
    try:return instant(value)
    except Refused:raise Refused('POLICY_WINDOW') from None

def policy_of(plan):
    """(bytes, object) of the signed live policy. The bytes must have the signed hash and size; the object must be
    what the controller of the release (read_policy) and its assembler (validate_policy) will require of it."""
    item=plan['policy']
    need(type(item) is dict and set(item)==set(POLICY_KEYS) and file_request(item['name'],item['sha256'],item['bytes'],PRIVATE_FILE_MODE)
         and item['bytes']<=MAX_POLICY_BYTES and type(item['content_b64']) is str,'POLICY_REQUEST_INVALID')
    try:raw=base64.b64decode(item['content_b64'].encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('POLICY_BYTES_NOT_THE_SIGNED_HASH') from None
    need(sha(raw)==item['sha256'] and len(raw)==item['bytes'],'POLICY_BYTES_NOT_THE_SIGNED_HASH')
    try:policy=strict(raw)
    except Refused:raise Refused('POLICY_JSON_INVALID') from None
    need(type(policy) is dict,'POLICY_JSON_INVALID')
    return raw,policy

def policy_digest(policy):
    """The digest of the policy as the assembler of the release computes it: keys sorted, compact separators, text that
    is not ASCII as itself in UTF-8 (r2d2_v2_epoch_assembler.py:24-28). It is the policy_sha of Act B. A text that
    cannot be encoded (a lone surrogate) is refused: effects_of() is computed during the authentication."""
    try:return sha(json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8'))
    except ValueError:raise Refused('POLICY_JSON_INVALID') from None

def validate_policy(policy,plan):
    need(policy.get('schema')==LIVE_POLICY_SCHEMA and policy.get('mode')=='LIVE','POLICY_SCHEMA')
    need(policy.get('epoch')==EPOCH_NAME and policy.get('release_sha')==plan['release']['sha256'],'POLICY_IDENTITY')
    need(policy.get('order_sha')==RUNTIME_ORDER_SHA256,'POLICY_RUNTIME_ORDER')
    need(policy.get('package_sha')==EPOCH_PACKAGE_SHA256,'POLICY_PACKAGE')
    need(policy.get('code_revision')==EPOCH_REVISION,'POLICY_REVISION')
    need(integer(policy.get('capacity'),1,550),'POLICY_CAPACITY')
    need(all(hexpin(policy.get(key)) for key in ('c8_receipt_sha','head_go_sha')),'POLICY_RECERTIFICATION')
    start,end=policy_instant(policy.get('valid_from')),policy_instant(policy.get('valid_until'))
    need(start<end and (end-start).total_seconds()<=MAX_POLICY_WINDOW_SECONDS,'POLICY_WINDOW')
    need(start<=instant(EPOCH_FIRST_OPEN) and end>=instant(EPOCH_LAST_CLOSE),'POLICY_NOT_EPOCH_WIDE')
    # The controller refuses a policy outside its window at every step: the window of this run must lie inside it. Its
    # end does (the run is on the first session day and the policy ends after the last close); its start is compared.
    need(start<=instant(plan['window']['not_before']),'POLICY_WINDOW_DOES_NOT_COVER_THE_GO')

def validate_plan(plan):
    root=plan['data_root']
    need(clean_path(root),'PATH_INVALID')                        # "/" itself is refused as an open root by validate_chain, with the same code
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    signed_chain(plan['live_parent'],root,receives_entry=True)
    need(inside(plan['live_parent'][-1]['path'],root),'LIVE_PARENT_OUTSIDE_DATA_ROOT')
    need(text(plan['directory_name'],FILE_NAME) and clean_path(live_path(plan)),'DIRECTORY_NAME_INVALID')
    release=plan['release']
    need(type(release) is dict and set(release)==set(RELEASE_KEYS) and text(release['directory_name'],FILE_NAME) and text(release['file_name'],FILE_NAME)
         and hexpin(release['sha256']) and integer(release['bytes'],1,MAX_RELEASE_BYTES),'RELEASE_REQUEST_INVALID')
    signed_chain(release['parent'],root)
    need(inside(release['parent'][-1]['path'],root),'RELEASE_OUTSIDE_DATA_ROOT')
    need(not inside(live_path(plan),release_directory_path(plan)) and not inside(release_directory_path(plan),live_path(plan)),'PATHS_OVERLAP')
    raw,policy=policy_of(plan);validate_policy(policy,plan)
    name=plan['override_name']
    # not the policy's name, and not one of the names the worker itself writes next to the policy (policy.json.status.json, ...)
    need(text(name,FILE_NAME) and name!=plan['policy']['name'] and not name.startswith(plan['policy']['name']+'.'),'OVERRIDE_NAME_INVALID')
    need(clean_path(policy_path(plan)) and clean_path(override_path(plan)),'FILE_PATH_INVALID')
    worker=plan['worker']
    need(type(worker) is dict and set(worker)==set(WORKER_KEYS) and text(worker['image_id'],IMAGE_ID)
         and clean_path(worker['mount_target']) and worker['mount_target']!='/','WORKER_REQUEST_INVALID')
    compose=plan['compose']
    need(type(compose) is dict and set(compose)==set(COMPOSE_KEYS),'COMPOSE_REQUEST_INVALID')
    compose_arguments(compose['project'],compose['env_file'],compose['files'])                       # the signed list alone, then with the override
    compose_arguments(compose['project'],compose['env_file'],compose['files']+[override_path(plan)])
    deploy=chain_path(plan['deploy_directory']);signed_chain(plan['deploy_directory'],deploy)     # the deploy tree: owned by the operational account
    # the file list of the deploy and nothing else: <deploy>/.env and <deploy>/<project>/compose.yml (c3po-pipeline.yml:745-746)
    need(compose['env_file']==deploy+'/'+ENV_FILE_NAME and compose['files']==[deploy+'/'+compose['project']+'/'+COMPOSE_FILE_NAME],'COMPOSE_NOT_THE_DEPLOY_LAYOUT')
    need(not inside(root,deploy) and not inside(deploy,root),'PATHS_OVERLAP')
    lock=plan['lock']
    need(type(lock) is dict and set(lock)==set(LOCK_KEYS) and integer(lock['wait_seconds'],0,MAX_LOCK_WAIT_SECONDS),'LOCK_REQUEST_INVALID')
    signed_chain(lock['directory'],deploy)
    need(lock['directory'][-1]['path']==deploy+'/'+LOCK_RELATIVE_DIRECTORY,'LOCK_NOT_THE_DEPLOYMENT_LOCK')
    environment_format(dict(environment_of(plan),**{BUILD_KEY:EPOCH_REVISION}))                      # every value fits the grammar of the template

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    raw,policy=policy_of(plan);override=override_of(plan);compose=plan['compose']
    return {'operation':OPERATION,'epoch':EPOCH_NAME,'revision':EPOCH_REVISION,'data_root':plan['data_root'],
            'live_parent':chain_effects(plan['live_parent']),
            'directory':{'path':live_path(plan),'mode_octal':'%04o'%PRIVATE_DIRECTORY_MODE,'expect':'ABSENT'},
            'files':[{'key':'POLICY','path':policy_path(plan),'sha256':plan['policy']['sha256'],'bytes':plan['policy']['bytes'],'mode_octal':'%04o'%PRIVATE_FILE_MODE},
                     {'key':'OVERRIDE','path':override_path(plan),'sha256':sha(override),'bytes':len(override),'mode_octal':'%04o'%PRIVATE_FILE_MODE}],
            'policy':{'content_digest_sha256':policy_digest(policy),'valid_from':policy.get('valid_from'),'valid_until':policy.get('valid_until'),
                      'capacity':policy.get('capacity'),'release_sha':policy.get('release_sha')},
            'release':{'parent':chain_effects(plan['release']['parent']),'path':release_path(plan),'sha256':plan['release']['sha256'],
                       'bytes':plan['release']['bytes'],'expect':'INSTALLED_BY_AN_EARLIER_OPERATION_READ_AND_COMPARED_NEVER_WRITTEN'},
            'recreate':{'project':compose['project'],'env_file':compose['env_file'],'files':compose['files']+[override_path(plan)],'service':WORKER_SERVICE,
                        'container':worker_name(plan),'image_id':plan['worker']['image_id'],'build_sha':EPOCH_REVISION,'environment':environment_of(plan),
                        'worker_mount':{'source':plan['data_root'],'target':plan['worker']['mount_target']},
                        'lock':lock_path(plan),'lock_wait_seconds':plan['lock']['wait_seconds'],'lock_chain_sha256':sha(canonical(plan['lock']['directory'])),
                        'deploy_directory':chain_effects(plan['deploy_directory'])},
            'required':{'maintenance_pin':pin_path(plan),'reboot_pending_marker_absent':REBOOT_PENDING_PATH,'deploy_version':EPOCH_REVISION},
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'pre_existing_objects_modified':'THE_WORKER_CONTAINER_IS_REPLACED','activation':False}
def success_of(plan):return COMPLETE_OUTCOME


# ---------------------------------------------------------------- what is read on the host
def hold(host,fd,pinned,**how):
    """A Pinned for a descriptor just opened; the descriptor is closed if it cannot be pinned."""
    try:holder=Pinned(host,fd,**how)
    except BaseException:
        host.close(fd);raise
    pinned.append(holder);return holder

def installed_release(host,plan,parent,gate,pinned):
    """The directory an earlier operation installed the release into, by name under its pinned parent, never through
    a link: a directory of root:root, mode 0700, on the device of its parent. Returns it held."""
    name=plan['release']['directory_name']
    gate()
    try:named=host.lstat(name,parent.fd)
    except FileNotFoundError:raise Refused('RELEASE_NOT_INSTALLED') from None
    need(stat.S_ISDIR(named.st_mode),'RELEASE_DIRECTORY_NOT_AS_INSTALLED')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
    directory=hold(host,fd,pinned,parent=parent,name=name)
    need(directory.identity==(named.st_dev,named.st_ino,0,0,PRIVATE_DIRECTORY_MODE) and named.st_dev==parent.identity[0],'RELEASE_DIRECTORY_NOT_AS_INSTALLED')
    return directory

def release_state(host,plan,directory,gate):
    """The installed release: a regular file of root:root, mode 0600, one link, whose bytes have the signed size and
    hash. Returns its signature, for the comparison under the lock."""
    release=plan['release'];gate()
    try:named=host.lstat(release['file_name'],directory.fd)
    except FileNotFoundError:raise Refused('RELEASE_NOT_INSTALLED') from None
    need(stat.S_ISREG(named.st_mode) and named.st_nlink==1 and (named.st_uid,named.st_gid,stat.S_IMODE(named.st_mode))==(0,0,PRIVATE_FILE_MODE),
         'RELEASE_FILE_NOT_AS_INSTALLED')
    raw,info=read_regular(host,release['file_name'],directory.fd,gate,MAX_RELEASE_BYTES)
    need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'RELEASE_FILE_NOT_AS_INSTALLED')
    need(len(raw)==release['bytes'] and sha(raw)==release['sha256'],'RELEASE_HASH_MISMATCH')
    return stat_signature(info)

def deploy_version(host,directory,gate):
    """.deploy-version of the deploy tree says the revision of the epoch (the pipeline writes it after a healthy deploy)."""
    gate()
    try:named=host.lstat(DEPLOY_VERSION_NAME,directory.fd)
    except FileNotFoundError:raise Refused('DEPLOY_VERSION_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'DEPLOY_VERSION_NOT_REGULAR')
    raw,_=read_regular(host,DEPLOY_VERSION_NAME,directory.fd,gate,128)
    need(raw.strip()==EPOCH_REVISION.encode('ascii'),'DEPLOY_VERSION_MISMATCH')

def env_file_state(host,directory,gate):
    """What tells that the environment file is the same object with the same bytes as at another instant of this run:
    its signature and the hash of its bytes. Both stay in memory: no value, digest or size of that file leaves the run."""
    gate()
    try:named=host.lstat(ENV_FILE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('ENV_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'ENV_FILE_NOT_REGULAR')
    raw,info=read_regular(host,ENV_FILE_NAME,directory.fd,gate,MAX_ENV_FILE_BYTES)
    return stat_signature(info),sha(raw)

def project_directory(host,plan,deploy,gate,pinned):
    """The directory of the compose project in the deploy tree, <deploy>/<project>, by name under the pinned deploy
    tree, never through a link (the deploy job fills it by rsync: c3po-pipeline.yml:702-711). Returns it held."""
    name=plan['compose']['project'];gate()
    try:named=host.lstat(name,deploy.fd)
    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None
    need(stat.S_ISDIR(named.st_mode),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY')
    gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=deploy.fd)
    directory=hold(host,fd,pinned,parent=deploy,name=name)
    need(directory.identity[:2]==(named.st_dev,named.st_ino),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY')
    return directory

def compose_file_state(host,directory,gate):
    """The same for the compose file of the deploy. Its text is never judged here (the render is): this only tells
    whether it is the object, with the bytes, that the first render was made from. The render has no other input
    than this file, the environment file and the build revision of the command (c3po/compose.yml at the release)."""
    gate()
    try:named=host.lstat(COMPOSE_FILE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('COMPOSE_FILE_ABSENT') from None
    need(stat.S_ISREG(named.st_mode),'COMPOSE_FILE_NOT_REGULAR')
    raw,info=read_regular(host,COMPOSE_FILE_NAME,directory.fd,gate,MAX_COMPOSE_FILE_BYTES)
    return stat_signature(info),sha(raw)

def reached_by_name(holder,gate):
    """True while the way from '/' still leads to the directory held, by its name (Pinned.verify of the core: the chain
    walked again, or the name looked at again in the parent). What is read through a descriptor is only then what the
    path shows. An expired window is not an answer and is raised."""
    try:holder.verify(gate);return True
    except Refused as error:
        if str(error)!='PARENT_REPLACED':raise
        return False

def free_inodes(host,fd):
    """Inodes a non-root writer can still take on the filesystem of a held descriptor; None where the filesystem
    counts none (f_files 0: it does not run out of them apart from its bytes)."""
    numbers=host.fstatvfs(fd);total,free=getattr(numbers,'f_files',0),getattr(numbers,'f_favail',None)
    return free if integer(total,1) and integer(free) else None

def leftovers(rows,container):
    """Containers a recreate of the service left behind: while compose replaces the container of a service, one of the
    two (the one being replaced, or the one that replaces it, depending on the compose version) carries the name
    <12 hex of an ID>_<name of the service's container>. With one present, a recreate cannot leave the listing as it
    was, and an earlier recreate is known to have been interrupted."""
    return [row for row in rows if row['name'].endswith('_'+container)]

def alive(row):
    """A container that runs: the flag and the state both say so (a paused or restarting container has the flag alone)."""
    return row['running'] is True and row['state']=='running'

def plain(path):
    """An absolute path as compose may print it (a trailing or a doubled slash, a "." component) in the one spelling the
    signed paths have; anything else stays as it is, and so stays unequal to a signed path."""
    return str(PurePosixPath(path)) if type(path) is str else path

def stopwatch(monotonic):
    """read() gives the milliseconds since now, or None when the clock fails: a timing is reported, it never decides
    and never raises."""
    try:start=monotonic()
    except Exception:start=None
    def read():
        try:return int(round((monotonic()-start)*1000))
        except Exception:return None
    return read

def service_of(rendered,plan):
    """What a render must say of the worker service: the build revision of the epoch, the four signed values, and that
    the two files the values name are reached through the one bind of the data root at the signed target."""
    service=compose_service(rendered,WORKER_SERVICE);environment=service['environment'];expected=environment_of(plan)
    need(environment.get(BUILD_KEY)==EPOCH_REVISION,'RENDER_BUILD_REVISION')
    need(all(environment.get(key)==value for key,value in expected.items()),'RENDER_ENVIRONMENT_MISMATCH')
    need(text(service['image'],REFERENCE) and not service['image'].startswith('-'),'RENDER_IMAGE_INVALID')
    volumes=rendered['services'][WORKER_SERVICE].get('volumes')
    need(type(volumes) is list and len(volumes)<=64 and all(type(item) is dict and type(item.get('target')) is str and item['target'] for item in volumes),
         'RENDER_VOLUMES_INVALID')
    binds=[(plain(item['target']),item) for item in volumes]
    for path in (expected[KEY_POLICY_FILE],expected[KEY_RELEASE_FILE]):
        covering=[pair for pair in binds if inside(path,pair[0])]
        need(len(covering)==1 and covering[0][0]==plan['worker']['mount_target'] and covering[0][1].get('type')=='bind'
             and plain(covering[0][1].get('source'))==plan['data_root'] and covering[0][1].get('read_only') in (None,False),'WORKER_MOUNT_NOT_AS_SIGNED')
    return service

def worker_status(host,name,directory,gate):
    """Informational, never decides: the two constant codes of the status file the controller of the new worker writes
    next to the policy, when it already exists. LIVE_EPOCH_NOT_FOUND is what it says while no epoch row exists."""
    def code(value):return value if text(value,'[A-Z0-9_]{1,100}') else None
    try:
        try:named=host.lstat(name,directory.fd)
        except FileNotFoundError:return {'present':False,'status':None,'readiness':None}
        if not stat.S_ISREG(named.st_mode):return {'present':None,'status':None,'readiness':None}
        raw,_=read_regular(host,name,directory.fd,gate,65536);value=strict(raw)
        if type(value) is not dict:return {'present':True,'status':None,'readiness':None}
        return {'present':True,'status':code(value.get('status')),'readiness':code(value.get('readiness'))}
    except Exception:return {'present':None,'status':None,'readiness':None}

AFTER_FACTS=('worker_listed_once','worker_is_new','old_container_gone','running','restarts','image_is_the_signed_one','environment_as_signed',
             'others_unchanged','others_states_unchanged','others_appeared','others_gone','others_same_name_new_id','service_leftovers',
             'env_file_unchanged','compose_file_unchanged','release_unchanged','files_as_delivered','directory_entries','lock_still_named',
             'settle_pause_taken','second_check_passed','milliseconds_between_checks','worker_status')
def read_after(c):
    """Everything read after the recreate command was started, each fact on its own: a read that fails leaves its
    facts None and its constant code under its step, and never hides another. Returns (facts, failed, unchanged);
    unchanged is True only when the worker is proved to be the container it was, as it was, in an unchanged listing."""
    host,gate,commands,plan,before,container=c['host'],c['gate'],c['commands'],c['plan'],c['before'],c['container']
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
            values=container_environment(commands,seen['first']['id'],c['signed'])
            facts['environment_as_signed']=all(item=={'present':True,'equal':True} for item in values.values())
    def containers():
        rows=container_list(commands);named=[row['id'] for row in rows if row['name']==container]
        def others(source,states):return sorted((row['id'],row['name'])+((row['state'],) if states else ()) for row in source if row['name']!=container)
        facts.update(worker_listed_once=len(named)==1 and ('first' not in seen or named==[seen['first']['id']]),
                     old_container_gone=before['id'] not in [row['id'] for row in rows],
                     others_unchanged=others(rows,False)==others(c['listing'],False),others_states_unchanged=others(rows,True)==others(c['listing'],True))
        if 'first' not in seen and len(named)==1:facts['worker_is_new']=named[0]!=before['id']      # the inspect failed: the listing still says which container it is
        seen['listing_unchanged']=sorted((row['id'],row['name']) for row in rows)==sorted((row['id'],row['name']) for row in c['listing'])
        # numbers only, never judged: what of the other containers differs, by name (names are unique in an engine), and
        # how many containers carry a temporary name of the worker's (an interrupted recreate, of either compose order)
        was={row['name']:row['id'] for row in c['listing'] if row['name']!=container};now={row['name']:row['id'] for row in rows if row['name']!=container}
        facts.update(others_appeared=len([name for name in now if name not in was]),others_gone=len([name for name in was if name not in now]),
                     others_same_name_new_id=len([name for name in now if name in was and now[name]!=was[name]]),service_leftovers=len(leftovers(rows,container)))
    def environment_file():facts['env_file_unchanged']=reached_by_name(c['deploy'],gate) and env_file_state(host,c['deploy'],gate)==c['env_before']
    def compose_file():facts['compose_file_unchanged']=reached_by_name(c['project'],gate) and compose_file_state(host,c['project'],gate)==c['compose_before']
    def release():facts['release_unchanged']=reached_by_name(c['release_directory'],gate) and release_state(host,plan,c['release_directory'],gate)==c['release_before']
    def delivered():
        # each readback proves the directory again first (its descriptor, its name in the pinned parent, owner and mode),
        # then the file: the inode this run created, one link, root:root 0600, the signed bytes
        directory=c['handles']['DIRECTORY'];codes=[readback_file(row,raw,PRIVATE_FILE_MODE,directory,host,gate) for row,raw in zip(c['ledger'],c['contents'])]
        facts['directory_entries']=count_entries(host,directory.fd,gate,MAX_DIRECTORY_ENTRIES)
        facts['files_as_delivered']=codes==[None,None]
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
    def status():facts['worker_status']=worker_status(host,plan['policy']['name']+STATUS_SUFFIX,c['handles']['DIRECTORY'],gate)
    for label,action in (('WORKER',worker),('ENVIRONMENT',environment),('CONTAINERS',containers),('ENV_FILE',environment_file),('COMPOSE_FILE',compose_file),
                         ('RELEASE',release),('FILES',delivered),('LOCK',locked),('SETTLE',settle),('SECOND_CHECK',second),('WORKER_STATUS',status)):step(label,action)
    first=seen.get('first')
    unchanged=bool(first is not None and seen.get('listing_unchanged') is True and alive(first)
                   and all(first[key]==before[key] for key in ('started_at','restarts')))
    return facts,failed,unchanged

def _reduce_precheck(receipt):receipt['precheck']={'reduced_for_size':True}
def _reduce_chains(receipt):receipt['chains']={key:len(rows) for key,rows in (receipt.get('chains') or {}).items()}
REDUCTIONS=[('PRECHECK_DROPPED',_reduce_precheck),('CHAINS_REDUCED_TO_COUNTS',_reduce_chains)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    content,_=policy_of(plan);override=override_of(plan);expected=environment_of(plan)                      # pure
    signed=dict(expected);signed[BUILD_KEY]=EPOCH_REVISION
    compose=plan['compose'];container=worker_name(plan);live=live_path(plan);listed=compose['files']+[override_path(plan)]
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'chains':{},'precheck':{},'budget':{}};directories=[];ledger=[];handles={};pinned=[];lock=[None]
    commands=Commands(host,gate);go16=bound['go_sha256'][:16]
    run={'state':'NOT_STARTED','code':None,'returncode':None,'started':False,'returned':False,'milliseconds':None,'replaced':False,'facts':None,'unavailable':None}
    def finish(status,outcome,code,extra):
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),clock=timing(begun,mark,clock,monotonic),
            commands_started=dict(commands.started),mutating_calls=state.counts(),chains=detail['chains'],precheck=detail['precheck'],budget=detail['budget'],
            directories=directories,ledger=ledger,recreate=run,objects_left_by_this_run=objects_left(directories,ledger),
            worker_container_replaced=run['replaced'],pre_existing_objects_modified=run['replaced'] is not False,**extra))
        return seal(receipt)
    def chain(key,rows):
        seen=[];detail['chains'][key]=seen
        return hold(host,walk_pinned(host,rows,gate,seen),pinned,rows=rows)
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            parent=chain('LIVE_PARENT',plan['live_parent'])
            found=probe(host,live,gate);detail['precheck']['directory']={'exists':found.get('exists')}
            need(found.get('exists') is False,'DESTINATION_PRESENT')                 # absent, proved: an unreadable path is not an absence
            need(probe(host,pin_path(plan),gate).get('type')=='file','MAINTENANCE_PIN_ABSENT')
            release_directory=installed_release(host,plan,chain('RELEASE_PARENT',plan['release']['parent']),gate,pinned)
            release_before=release_state(host,plan,release_directory,gate)
            deploy=chain('DEPLOY_DIRECTORY',plan['deploy_directory'])
            deploy_version(host,deploy,gate)
            env_before=env_file_state(host,deploy,gate)
            project=project_directory(host,plan,deploy,gate,pinned)
            compose_before=compose_file_state(host,project,gate)
            lock_directory=chain('LOCK_DIRECTORY',plan['lock']['directory'])
            lock[0]=open_lock(host,LOCK_FILE_NAME,lock_directory,gate)
            detail['precheck'].update(maintenance_pin_present=True,release_installed_as_signed=True,deploy_version_is_the_revision=True)
            # the worker as it is, its image, and that it is not activated yet
            before=container_facts(commands,container)
            detail['precheck']['worker']={'id':before['id'],'started_at':before['started_at'],'restarts':before['restarts'],'state':before['state']}
            need(alive(before),'WORKER_NOT_RUNNING')
            need(before['image_id']==plan['worker']['image_id'],'WORKER_IMAGE_NOT_THE_SIGNED_ONE')
            try:image=image_facts(commands,plan['worker']['image_id'])
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            need(image['id']==plan['worker']['image_id'] and image['revision_label']==EPOCH_REVISION,'IMAGE_REVISION_MISMATCH')
            values=container_environment(commands,before['id'],signed)
            need(values[BUILD_KEY]=={'present':True,'equal':True},'WORKER_BUILD_REVISION')
            need(not any(values[key]['present'] for key in ACTIVATION_KEYS),'WORKER_ALREADY_CARRIES_THE_KEYS')
            # the render the recreate will be made from, with the override still only bytes; timed, because the same
            # render runs again from the files between the first creation and the recreate
            began=monotonic()
            service=service_of(compose_render(commands,'render',compose['project'],compose['env_file'],compose['files'],EPOCH_REVISION,override=override),plan)
            measured=monotonic()-began
            try:resolved=image_facts(commands,service['image'])
            except CommandFailed:raise Refused('RENDER_IMAGE_UNRESOLVED') from None
            need(resolved['id']==plan['worker']['image_id'],'RENDER_IMAGE_CHANGED')
            detail['precheck']['render']={'environment_as_signed':True,'image_is_the_running_one':True,'data_root_bound_at_the_signed_target':True}
            # The last refusals before the first effect: the lock (waited for at most the signed seconds, and never
            # past the point where what follows would no longer fit), what is read again once it is held, the time.
            allowance=min(COMMAND_CLASSES['RENDER']['seconds'],max(RENDER_ALLOWANCE_FLOOR_SECONDS,int(2*measured)+1))
            needed=effects_budget('recreate')+allowance+FILES_ALLOWANCE_SECONDS+SETTLE_SECONDS
            detail['budget']={'first_render_milliseconds':int(measured*1000),'render_allowance_seconds':allowance,'needed_before_first_effect_seconds':needed,
                              'kept_while_waiting_for_the_lock_seconds':needed+UNDER_LOCK_ALLOWANCE_SECONDS,'left_when_the_lock_was_asked_for_milliseconds':int(gate()*1000)}
            detail['precheck']['lock_attempts']=acquire_lock(host,lock[0],gate,plan['lock']['wait_seconds'],needed+UNDER_LOCK_ALLOWANCE_SECONDS)
            need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
            pending=probe(host,REBOOT_PENDING_PATH,gate)
            need(pending.get('status')=='COMPLETE','REBOOT_STATE_UNAVAILABLE');need(pending.get('exists') is False,'SECURITY_REBOOT_PENDING')
            # what was read through a descriptor is what the path shows only while the name still leads to it: the
            # three directories that are held and not re-proved by a creating call (the live parent is, by the core)
            need(reached_by_name(release_directory,gate),'RELEASE_DIRECTORY_REPLACED')
            need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')                # proves the deploy tree first, then the project directory in it
            need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
            deploy_version(host,deploy,gate)
            need(env_file_state(host,deploy,gate)==env_before,'ENV_FILE_CHANGED_BEFORE_THE_LOCK')
            need(compose_file_state(host,project,gate)==compose_before,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK')
            need(release_state(host,plan,release_directory,gate)==release_before,'RELEASE_CHANGED_BEFORE_THE_LOCK')
            again=container_facts(commands,container)
            need(all(again[key]==before[key] for key in ('id','started_at','restarts')) and alive(again),'WORKER_CHANGED_BEFORE_THE_LOCK')
            listing=container_list(commands)
            need([row['id'] for row in listing if row['name']==container]==[before['id']],'CONTAINER_LIST_INCONSISTENT')
            # a container left by an interrupted recreate of the service: compose would remove or replace it during the
            # recreate, so the listing could not stay as it is and the run could not complete
            need(not leftovers(listing,container),'WORKER_SERVICE_LEFTOVER_CONTAINER')
            # room for one directory and two small files, where it is knowable before the first creation
            free,inodes=free_bytes(host,parent.fd),free_inodes(host,parent.fd)
            detail['precheck'].update(reboot_pending=False,containers_listed=len(listing),free_bytes=free,free_inodes=inodes)
            need(free>=FREE_BYTES_FLOOR,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')
            need(inodes is None or inodes>=FREE_INODES_FLOOR,'DATA_VOLUME_FREE_INODES_BELOW_FLOOR')
            left=gate();detail['budget']['left_before_first_effect_milliseconds']=int(left*1000)
            need(left>=needed,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None;contents=(content,override)
        entry=create_directory('DIRECTORY',live,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)
        if entry['state']!='CREATED_DURABLE':stop=entry['code'] or 'CREATION_FAILED'
        for index,(key,path,raw) in enumerate((('POLICY',policy_path(plan),content),('OVERRIDE',override_path(plan),override))):
            if stop is not None:
                ledger.append({'key':key,'path':path,'state':'NOT_ATTEMPTED','code':None});continue
            row=create_file(index,key,path,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        if stop is None:
            for row,raw in zip(ledger,contents):stop=stop or readback_file(row,raw,PRIVATE_FILE_MODE,handles['DIRECTORY'],host,gate)
        if stop is None:stop=readback_directory(live,PRIVATE_DIRECTORY_MODE,handles['DIRECTORY'],host,gate,len(contents))
        if stop is None:
            # under the lock, with the override now a file: the render the recreate will use
            taken=stopwatch(monotonic)
            try:
                need(lock_still_named(host,LOCK_FILE_NAME,lock_directory,lock[0]),'LOCK_FILE_REPLACED')
                need(service_of(compose_render(commands,'render_files',compose['project'],compose['env_file'],listed,EPOCH_REVISION),plan)['image']==service['image'],
                     'RENDER_IMAGE_CHANGED')
                # last, right before the one command that changes the worker: the names still lead to what is held
                need(reached_by_name(release_directory,gate),'RELEASE_DIRECTORY_REPLACED')
                need(reached_by_name(project,gate),'DEPLOY_TREE_REPLACED')
                need(reached_by_name(lock_directory,gate),'LOCK_DIRECTORY_REPLACED')
            except Exception as error:stop=code_of(error,'RECREATE_PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'RECREATE_PRECHECK_FAILED')
            detail['budget']['render_from_the_files_milliseconds']=taken()
        if stop is None:
            taken=stopwatch(monotonic)
            result=compose_up(state,commands,'recreate',compose['project'],compose['env_file'],listed,EPOCH_REVISION)
            run.update(started=result['started'],returned=result['returned'],returncode=result['returncode'],code=result['code'],milliseconds=taken())
            if not result['started']:stop=result['code'] or 'COMMAND_NOT_STARTED'
            else:
                # the command was started: what it left is read on the host, and only then is the call settled
                facts,failed,unchanged=read_after({'host':host,'gate':gate,'commands':commands,'plan':plan,'before':before,'container':container,
                    'listing':listing,'signed':signed,'deploy':deploy,'env_before':env_before,'handles':handles,'ledger':ledger,'contents':contents,
                    'project':project,'compose_before':compose_before,'release_directory':release_directory,'release_before':release_before,
                    'lock_directory':lock_directory,'lock':lock[0],'monotonic':monotonic})
                run.update(facts=facts,unavailable=failed)
                criteria=[(result['code'] or 'RECREATE_RETURNED_NONZERO',bool(result['returned'] and result['returncode']==0)),
                          ('WORKER_NOT_FOUND_AFTER_RECREATE',facts['worker_listed_once']),('WORKER_NOT_RECREATED',facts['worker_is_new']),
                          ('OLD_CONTAINER_STILL_PRESENT',facts['old_container_gone']),('WORKER_NOT_RUNNING_AFTER_RECREATE',facts['running']),
                          ('WORKER_RESTARTED_AFTER_RECREATE',None if facts['restarts'] is None else facts['restarts']==0),
                          ('WORKER_IMAGE_CHANGED',facts['image_is_the_signed_one']),('ENVIRONMENT_NOT_AS_SIGNED',facts['environment_as_signed']),
                          ('OTHER_CONTAINERS_CHANGED',facts['others_unchanged']),('ENV_FILE_CHANGED',facts['env_file_unchanged']),
                          ('COMPOSE_FILE_CHANGED',facts['compose_file_unchanged']),('RELEASE_CHANGED',facts['release_unchanged']),
                          ('FILES_NOT_AS_DELIVERED',facts['files_as_delivered']),('LOCK_FILE_REPLACED',facts['lock_still_named']),
                          ('SECOND_CHECK_NOT_APART',facts['settle_pause_taken']),('WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS',facts['second_check_passed'])]
                # a criterion that is False names itself; one that could not be read (None) is READBACK_UNAVAILABLE
                missing=[name if value is False else 'READBACK_UNAVAILABLE' for name,value in criteria if value is not True]
                if not missing:
                    state.done();run.update(state='RECREATED_VERIFIED',replaced=True)
                elif result['returned'] and unchanged:
                    # a read proved that nothing changed: the same container, as it was, in an unchanged listing
                    state.fail();run.update(state='NOT_RECREATED',replaced=False)
                    stop='RECREATE_FAILED_CONTAINER_UNCHANGED' if result['returncode'] else 'RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED'
                else:
                    if result['returned']:state.unknown()
                    if facts['worker_is_new'] is True:
                        once=not [name for name,value in criteria[:-2] if value is not True] and facts['second_check_passed'] is not False
                        run.update(state='RECREATED_VERIFIED_ONCE' if once else 'RECREATED_NOT_VERIFIED',replaced=True)
                    else:run.update(state='UNCERTAIN',replaced=None)
                    stop=missing[0]
        extra={'phase_reached':'EFFECTS','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        outcome={'RECREATED_VERIFIED_ONCE':NOT_VERIFIED_OUTCOME,'RECREATED_NOT_VERIFIED':NOT_VERIFIED_OUTCOME,'UNCERTAIN':UNCERTAIN_OUTCOME}.get(run['state'],OBJECTS_ONLY_OUTCOME)
        return finish(PARTIAL_STATUS,outcome,stop,extra)
    finally:
        if lock[0] is not None:release_lock(host,lock[0])
        for handle in list(handles.values())+pinned:
            try:handle.close()
            except Exception:pass
# ==== END OP_ACTIVATE ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
