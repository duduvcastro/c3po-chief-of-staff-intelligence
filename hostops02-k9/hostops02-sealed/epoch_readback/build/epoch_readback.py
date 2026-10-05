"""OP_EPOCH_READBACK (K11): the readback of epoch R2D2-V2-SHADOW-2026-10-05, modes PRE (dry run) and POST.

Observations only. This source has no call that creates, changes or removes anything on the host's filesystem; it
does not carry the files part and its command table has no EFFECT row. PRE takes the release bytes from the signed
request and requires that nothing stands yet where install_release will create its directory; POST reads the
installed release file. In both modes the release is verified by the deployed code itself (Release.verify) in one
attached container of the signed image ID that has no network, a read-only root filesystem and at most one read-only
bind (POST: the installed release directory; PRE: none, or an existing private directory signed as a probe of the
bind of the bind itself); the pinned snippet travels on standard input and prints booleans and codes (the release's own
refusal code or the name of an exception's class, never a message). The live policy candidate is put to the deployed
controller's and assembler's own validators in that same container. What install_release and activate refuse on
before any effect is looked at beforehand and is a finding here: the place of each directory they create, the pin,
the free space, the live names of the running worker, the bind of the data volume in the render, and the signed
milliseconds of the docker reads. Around it: pinned directories walked from "/", the compose render with the intended override on
standard input (never written to the host), image and worker metadata, the signed environment names of the worker
as booleans, unit states, free space of the journal filesystem, and a probe of the deployment lock. Each item is
observed on its own: a failed observation is UNAVAILABLE with a constant code, never an absence; a mismatch is a
finding that leaves every other item in the receipt; what the signed plan omits is not observed and the receipt
says so. No value of an environment, no byte of the release, of the policy or of the render, and no name of an
instrument leaves the run. The caller authenticates exact request/authority/GO/source bytes first.
No action on import.
"""

# ==== BEGIN SEAL (generated: the frozen core this source is assembled from) ====
CORE_SHA256='4c24c5cfe4d6c70ce8aa57c61b070255dd67850be6697b8a0f58f95f6663d0d6'
CORE_PARTS={'core': 'ecf72edaf2bae478186e642bc93804bd567384c5d13dfab2bb4c4d55d00eef7a', 'runner': '2a1cc5bc73a0d456eb596aea65caaffcf7dd3834cbbd844a02a69486bbdacaa7', 'docker': '4602f6f07a4502a3decec99cd415737efb429e3b1a188b368939a090bc3b3aa5', 'parents': '3f5eafa763339068424304d23efdbffeb19a0910d5600eef7e534c13a81cd38b', 'lock': '17099e318c9f7df61b570563fba45868ff6e0b884120265a01572bcb7d2ef554'}
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

# ==== BEGIN OP_EPOCH_READBACK (this operation only) ====
import base64

OPERATION='GO_READONLY_HOSTOPS02_EPOCH_READBACK_01'
PHASE='READONLY_EPOCH_READBACK'
REQUEST_SCHEMA='READONLY_HOSTOPS02_EPOCH_READBACK_REQUEST_V1'
AUTHORITY_SCHEMA='READONLY_HOSTOPS02_EPOCH_READBACK_AUTHORITY_V1'
GO_SCHEMA='READONLY_HOSTOPS02_EPOCH_READBACK_GO_V1'
RECEIPT_SCHEMA='READONLY_HOSTOPS02_EPOCH_READBACK_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_EPOCH_READBACK_PLAN_V1'
SOURCE_NAME='epoch_readback.py'
WRITES_ALLOWED=False
ACTIVATION_ALLOWED=False
DATE_CLASS='READ'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
EVIDENCE_OPERATIONS=()
MAX_GATE_SPAN_SECONDS=3600
# Exit 0 exists for one outcome per signed mode. Only the POST outcome is the readback of the first session.
COMPLETE_OUTCOME='EPOCH_READBACK_POST_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
PRE_OUTCOME='EPOCH_DRY_RUN_PRE_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
# A dry run that leaves out any part of the full profile succeeds under another name: it is never the rehearsal of Monday.
PRE_REDUCED_OUTCOME='EPOCH_DRY_RUN_PRE_REDUCED_PROFILE_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
MISMATCH_OUTCOME='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
PARTIAL_OUTCOME='PARTIAL_OBSERVED'
REFUSED_OUTCOME='REFUSED_NOTHING_OBSERVED'
REDUCED_OUTCOME='PARTIAL_OBSERVED'
ESCAPED_OUTCOME='PARTIAL_OBSERVED'
MODES=('PRE','POST')
DRY_RUNS=('FULL','REDUCED')
PLAN_KEYS=frozenset(('mode','evidence_boot_id_sha256','revision','package_sha256','image','worker','release','policy','render','deploy',
                     'units','journal','docker_config','rows_in_receipt','bind_probe','dry_run','live','limits'))
RELEASE_KEYS=frozenset(('sha256','bytes','content_b64','parent','directory_name','file_name','container_target','directory_entries'))
# The epoch of this family (r2d2_v2_epoch_assembler.py lines 9, 10, 13 at the release; the controller's ORDER_SHA).
EPOCH_NAME='R2D2-V2-SHADOW-2026-10-05'
FIRST_SESSION_DAY='2026-10-05'
RUNTIME_ORDER_SHA256='1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e'
RELEASE_SCHEMA_NAME='R2D2_V2_RELEASE_V3'
POLICY_SCHEMA_NAME='R2D2_V2_LIVE_POLICY_V1'
WORKER_SERVICE='r2d2-worker'
BUILD_KEY='C3PO_BUILD_SHA'
# The four names of the activation override of 2026-09-28, in its order: policy file, policy hash, release file, release hash.
LIVE_KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')
REVISION='[0-9a-f]{40}'
ENTRY_NAME='[A-Za-z0-9][A-Za-z0-9._-]{0,127}'
DOTTED_NAME='[A-Za-z0-9._-]{1,128}'
CONTAINER_TARGET='/c3po-[a-z0-9][a-z0-9-]{0,40}'
UNIT_NAME=r'[A-Za-z0-9][A-Za-z0-9@_.:-]{0,120}\.(service|timer)'
UNIT_STATE='[A-Za-z0-9-]{0,32}'
SNIPPET_CODE='[A-Za-z_][A-Za-z0-9_]{0,79}'
MAX_RELEASE_BYTES=24576          # carried base64 in the request (PRE); the request is a document of at most 65536 bytes
MAX_INSTALLED_BYTES=65536        # the worker's own limit for the installed file (r2d2_v2_shadow_worker.py line 33)
MAX_POLICY_BYTES=8192
MAX_OVERRIDE_BYTES=4096
MAX_DIRECTORY_ENTRIES=8
MAX_UNITS=8
MAX_VALID_AT=4
MAX_FLOOR_BYTES=1<<50
MAX_COUNT=100000
MAX_REVISION_FILE_BYTES=128         # what activate reads of the deployed revision file
MAX_LIMIT_MILLISECONDS=60000
MAX_RENDERED_VOLUMES=64
# What install_release and activate take from the host by constant or by derivation (their own sources): a full dry
# run signs exactly these, so that it looks at the places and renders the files Monday's two writes will use.
MONDAY_DATA_VOLUME='/mnt/day-d-data'
MONDAY_DATA_TARGET='/app/day-d-data'
MONDAY_RELEASE_DIRECTORY='r2d2-v2-release-20261005'
MONDAY_RELEASE_FILE='release.CERTIFIED.json'
MONDAY_ENV_FILE='.env'
MONDAY_COMPOSE_FILE='compose.yml'
MONDAY_VERSION_NAME='.deploy-version'
MONDAY_LOCK_DIRECTORY='runtime/security'
MONDAY_LOCK_NAME='deployment.lock'
RELEASE_DIRECTORY_MODE=0o700
RELEASE_FILE_MODE=0o600
DOCKER_CONFIG_MODE=0o700
PIN_NAME='.r2d2-v2-pinned'
REBOOT_PENDING='/run/c3po-security/reboot.pending'
REBOOT_REQUIRED='/run/reboot-required'
CATALOG_NAMES=('epoch.json','maintenance.lock')
EXPIRED_CODES=('GO_EXPIRED','CLOCK_REVERSED')
# What a walk says about a directory that is not as signed: a finding. Anything else a walk refuses is an observation that failed.
WALK_FINDINGS=('PARENT_MISSING','PARENT_SYMLINK_COMPONENT','PARENT_NOT_DIRECTORY','PARENT_IDENTITY_MISMATCH','SYMLINK_COMPONENT','COMPONENT_NOT_DIRECTORY')
ROW_FIELDS=('device','inode','uid','gid','mode')
UNIT_PROPERTIES=('Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','WantedBy','RequiredBy','TriggeredBy')
GATED_PROPERTIES=('LoadState','ActiveState','SubState','UnitFileState')
CONTAINER_PREFIX='hostops02-k11-'
VERIFY_COMMAND=['python','-I','-B','-']
VERIFY_ALARM_SECONDS=30
# The pinned snippet. It runs in the container as `python -I -B -` after one line that this source writes in front of
# it (SIGNED_CONTEXT=<a literal of signed values>). Its first statement arms an alarm: the interpreter is killed by
# the kernel after VERIFY_ALARM_SECONDS, so the container ends by itself before the docker CLI's time limit. It reads
# the release (from the context, or with the worker's own reader from the read-only bind), calls the deployed
# Release.verify, read_policy and validate_policy, and prints ONE line of booleans and codes. A code is the single
# upper-case argument of an exception of the release's own two refusal classes, and otherwise the name of the
# exception's class: never a message. The reader of the worker and the controller are imported in every run, signed
# policy or not, so that no module the first session needs is imported for the first time on Monday.
VERIFY_SNIPPET=r'''import signal
signal.alarm(30)
import base64, hashlib, json, os, re, sys, types
from datetime import datetime, timezone
sys.path.insert(0, '/app')
C = SIGNED_CONTEXT
OWN = ()
def code_of(error):
    value = error.args[0] if isinstance(error, OWN) and len(error.args) == 1 and type(error.args[0]) is str else ''
    return value if re.fullmatch('[A-Z][A-Z0-9_]{0,79}', value) else type(error).__name__[:80]
def attempt(action):
    try:
        action()
        return {'valid': True, 'code': None}
    except Exception as error:
        return {'valid': False, 'code': code_of(error)}
try:
    from app.r2d2_v2_shadow import EBAR_AMENDMENT_SHA, Release, ShadowCalendar
    from app.r2d2_v2_earnings_package import implementation_package_sha
    from app import r2d2_v2_epoch_assembler as assembler
    from app.r2d2_v2_store import ShadowIntegrityError
    from app.r2d2_v2_shadow_worker import _release_bytes
    from app import r2d2_v2_live_controller as controller
    OWN = (ShadowIntegrityError, assembler.Refused)
    now = datetime.now(timezone.utc)
    calendar = ShadowCalendar()
    package = implementation_package_sha()
    release = {'source': 'STDIN' if C['release_b64'] is not None else 'FILE', 'read': False, 'bytes_equal_signed': False,
               'verified': False, 'code': None, 'mode_certified': False, 'epoch_equal': False, 'first_session_equal': False,
               'ebar_bound': False}
    try:
        if C['release_b64'] is not None:
            data = base64.b64decode(C['release_b64'], validate=True)
        else:
            data = _release_bytes(C['release_path'])
        release['read'] = True
        release['bytes_equal_signed'] = hashlib.sha256(data).hexdigest() == C['release_sha256'] and len(data) == C['release_bytes']
        found = Release.verify(data, C['release_sha256'], now=now, build_sha=C['revision'], calendar=calendar)
        release.update(verified=True, mode_certified=found.mode == 'CERTIFIED',
                       epoch_equal=found.epoch == C['epoch'] == assembler.EPOCH,
                       first_session_equal=found.first_session.isoformat() == C['first_session'] == assembler.FIRST_SESSION,
                       ebar_bound=found.ebar_amendment_sha == EBAR_AMENDMENT_SHA)
    except Exception as error:
        release['code'] = code_of(error)
    probe = None
    if C['probe_path'] is not None:
        probe = attempt(lambda: _release_bytes(C['probe_path']))
    policy = None
    if C['policy_b64'] is not None:
        raw = base64.b64decode(C['policy_b64'], validate=True)
        controller._release_bytes = lambda path: raw
        settings = types.SimpleNamespace(r2d2_v2_live_policy_file='/signed-bytes-on-standard-input',
                                         r2d2_v2_live_policy_sha=C['policy_sha256'], build_sha=C['revision'])
        identity = {'epoch': assembler.EPOCH, 'runtime_order_sha': assembler.RUNTIME_ORDER_SHA}
        bindings = {'release_sha': C['release_sha256'], 'package_sha': package, 'policy_sha': C['policy_sha256']}
        policy = {'hash_equal_signed': hashlib.sha256(raw).hexdigest() == C['policy_sha256'],
                  'controller_now': attempt(lambda: controller.read_policy(settings, now)),
                  'controller_at': [attempt(lambda item=item: controller.read_policy(settings, datetime.fromisoformat(item)))
                                    for item in C['policy_valid_at']],
                  'assembler': attempt(lambda: assembler.validate_policy(json.loads(raw), identity, bindings, calendar))}
    out = {'status': 'DONE', 'release': release, 'policy': policy, 'probe': probe, 'package_equal_signed': package == C['package_sha256'],
           'facts': {'python': '%d.%d.%d' % sys.version_info[:3], 'calendar_version': str(calendar.version)[:32]},
           'context_request_sha256': C['request_sha256']}
except BaseException as error:
    out = {'status': 'FAILED', 'code': code_of(error)}
os.write(1, json.dumps(out, sort_keys=True, separators=(',', ':')).encode('ascii') + b'\n')
raise SystemExit(0 if out['status'] == 'DONE' else 1)
'''
VERIFY_SNIPPET_SHA256=sha(VERIFY_SNIPPET.encode('ascii'))
VERIFY_LINE_KEYS=frozenset(('status','release','policy','probe','package_equal_signed','facts','context_request_sha256'))
VERIFY_RELEASE_KEYS=frozenset(('source','read','bytes_equal_signed','verified','code','mode_certified','epoch_equal','first_session_equal','ebar_bound'))
VERIFY_POLICY_KEYS=frozenset(('hash_equal_signed','controller_now','controller_at','assembler'))
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl','/bin/systemctl']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image reference','QUICK','READ'),
          'container':command_row('docker',['container','inspect','--format',CONTAINER_FORMAT],'the signed name of the worker container','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          'container_environment':command_row('docker',['container','inspect','--format'],'the presence and equality template, then the worker container ID','QUICK','READ'),
          'verify':command_row('docker',RUN_PREFIX,'--name hostops02-k11-<16 hex of the GO>, at most one read-only bind (POST: the installed release directory; PRE: the signed bind probe), the signed image ID, python -I -B -','RUN','CONTAINER',stdin=True),
          'render_base':command_row('docker',['compose'],'--project-name, --env-file and the signed -f list','RENDER','READ',tail=COMPOSE_CONFIG_TAIL),
          'render_override':command_row('docker',['compose'],'--project-name, --env-file, the signed -f list, then -f - : the signed override on standard input as the last file','RENDER','READ',tail=COMPOSE_CONFIG_TAIL,stdin=True),
          'unit':command_row('systemctl',['show'],'one signed unit name','QUICK','READ',tail=[part for key in UNIT_PROPERTIES for part in ('-p',key)])}
SCOPE_STATEMENT=('Reads and changes nothing on the filesystem of the host. PRE (dry run): the release bytes of the signed request, verified by '
                 'the deployed code in one attached container of the signed image ID with no network, a read-only root filesystem and no bind '
                 '(or the one read-only bind of an existing private directory that the request signs as a probe of the bind itself); '
                 'the place where install_release will create its directory must still be empty. POST: the installed release file, read on the '
                 'host and verified the same way through one read-only bind of its directory. In both: the live policy candidate put to the '
                 'deployed validators in that container, signed directories walked from "/", the compose render with the intended override on '
                 'standard input (never written to the host), image and worker metadata, the signed environment names of the worker as '
                 'booleans, unit states, free space of the journal filesystem, the maintenance pin and the reboot markers by lstat, and a '
                 'shared probe of the deployment lock. It creates and removes one container. Only the outcome named as success criterion '
                 'counts: the PRE outcome is a dry run and is never the readback of the first session, and a dry run signed as REDUCED '
                 'succeeds under a name of its own and is never the rehearsal of install_release and activate. This operation authorises no '
                 'installation, no activation and no change of any kind.')
SIDE_EFFECTS=['one attached docker run --rm: the engine creates a container named hostops02-k11-<16 hex of the GO> and removes it when its process ends; '
              'the snippet arms a %d s alarm as its first statement, so the process ends by itself before the %d s limit of the docker CLI; '
              'a run whose CLI is killed first may leave the container to the engine until its process ends, and the receipt says whether one of that name is listed; '
              'a container that was created and never started has no process and no alarm: it stays in the state created until someone removes it by its name, '
              'and no source of this family removes a container'
              %(VERIFY_ALARM_SECONDS,COMMAND_CLASSES['RUN']['seconds']),
              'a shared, non-blocking flock on the deployment lock, released at once: for that instant a non-blocking exclusive request of another process fails',
              'docker compose config reads the environment file; its values stay in the memory of this process and never reach the receipt, an argv or a log',
              'the values compared with the environment of the worker (the revision, two container paths, two hashes) travel in the argv of the docker CLI; none is a secret',
              'systemctl show of a unit the manager has not loaded makes the manager load it from disk; no daemon-reload is run',
              'with a signed docker_config (a reduced dry run only: activate never sets it) every docker command runs with DOCKER_CONFIG set to that directory, '
              'only after it was seen root:root 0700 and empty; it is counted before and after and a change is a finding of its own',
              'the Docker CLI executes its installed plugin binaries to answer compose; nothing is installed or changed']
FACTS_NOT_GATED=['the state of the deployment lock (FREE or BUSY)','the marker '+REBOOT_REQUIRED,'the state of a unit without a signed expectation',
                 'a journal root that does not exist, and its free space, without a signed floor','the restart count and the health of the worker',
                 'whether the policy is inside its window at the instant of the run','the versions of Python and of the calendar library in the image',
                 'the names of the catalog files in the journal root','the owner of the maintenance pin in POST','the milliseconds of every command without signed limits',
                 'whether the rows of a directory that receives no entry after this run would be accepted by a write']
# Items that carry no signed expectation at all. When one of them cannot be observed the receipt lists it under
# fact_items_not_observed and the outcome is decided by the other items.
FACT_ITEMS=['reboot_required','unit:<name> without a signed expectation','journal without a signed floor']
# What install_release and activate refuse on before any effect, and this source therefore finds beforehand.
PRECONDITIONS={'install_release':['the release directory absent in its parent','the parent rows as that write accepts them, the data volume a mount point',
                                  'the maintenance pin a regular file of root:root (PRE)','free bytes and, where counted, free inodes of the filesystem of its parent at or above the signed floors'],
               'activate':['its directory absent in the signed live parent, the rows of that parent as the write accepts them',
                           'free bytes and, where counted, free inodes of the filesystem of the live parent at or above the signed floors',
                           'no container left under a temporary name of the worker (an interrupted recreate)',
                           'the running worker without any of the four live names, with or without a value',
                           'the render with the override: build revision, the four values, the image reference, and the policy and release files reached through '
                           'exactly one bind of the signed source at the signed target that is not read-only',
                           'the two renders and each quick docker read within the signed milliseconds','the lock file present','no security reboot pending']}
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,'lock':LOCK_SCOPE,
       'modes':{'PRE':PRE_OUTCOME+' (a dry run; never the readback of the first session)','POST':COMPLETE_OUTCOME},
       'dry_run':{'FULL':PRE_OUTCOME+': policy, bind_probe, live, limits and the environment of the worker are signed, no docker_config, the places '
                         'of install_release, the layout and the override bytes of activate',
                  'REDUCED':PRE_REDUCED_OUTCOME+': anything less; never the rehearsal of install_release and activate'},
       'monday':{'data_volume':MONDAY_DATA_VOLUME,'data_target':MONDAY_DATA_TARGET,'release_directory':MONDAY_RELEASE_DIRECTORY,'release_file':MONDAY_RELEASE_FILE,
                 'env_file':'<deploy tree>/'+MONDAY_ENV_FILE,'compose_file':'<deploy tree>/<project>/'+MONDAY_COMPOSE_FILE,'version_file':MONDAY_VERSION_NAME,
                 'lock':MONDAY_LOCK_DIRECTORY+'/'+MONDAY_LOCK_NAME,'worker_container':'<project>-'+WORKER_SERVICE+'-1',
                 'override':'json.dumps of {"services":{"'+WORKER_SERVICE+'":{"environment":{the four names}}}} with sorted keys, ASCII'},
       'preconditions_of_the_writes_found_here':PRECONDITIONS,'fact_items':FACT_ITEMS,
       'epoch':{'name':EPOCH_NAME,'first_session':FIRST_SESSION_DAY,'runtime_order_sha256':RUNTIME_ORDER_SHA256,
                'release_schema':RELEASE_SCHEMA_NAME,'policy_schema':POLICY_SCHEMA_NAME},
       'verify':{'snippet_sha256':VERIFY_SNIPPET_SHA256,'command':VERIFY_COMMAND,'alarm_seconds':VERIFY_ALARM_SECONDS,
                 'container_name':CONTAINER_PREFIX+'<first 16 hex of the GO hash>','network':'none','root_filesystem':'read-only',
                 'binds':'read-only only. POST: the installed release directory. PRE: none, or the one existing private directory the request signs as bind_probe '
                         '(the snippet reads one named file of it with the reader of the worker and prints a boolean). Every bind source is held and proved again before and after the run',
                 'standard_input':'one line that assigns a literal of signed values to the name the snippet reads, then the snippet',
                 'imports':'the release verifier, the package hash, the assembler, the reader of the worker and the live controller, in every run',
                 'prints':'one JSON line of booleans, codes and two version strings; a code is the single upper-case argument of an exception of the '
                          "release's own refusal classes (ShadowIntegrityError, the assembler's Refused), otherwise the name of the exception's class"},
       'render':{'service':WORKER_SERVICE,'live_keys':list(LIVE_KEYS),'build_key':BUILD_KEY,
                 'compared':'the render of the signed files alone with the render that adds the signed override on standard input',
                 'data_volume':'the volumes of the worker in the render with the override, judged by the rule of activate; at most %d entries'%MAX_RENDERED_VOLUMES},
       'installed_release':{'directory':{'type':'dir','uid':0,'gid':0,'mode_octal':'%04o'%RELEASE_DIRECTORY_MODE},
                            'file':{'type':'file','uid':0,'gid':0,'mode_octal':'%04o'%RELEASE_FILE_MODE,'links':1}},
       'unit_properties':list(UNIT_PROPERTIES),'unit_properties_that_can_be_signed':list(GATED_PROPERTIES),
       'lstat_only':{'maintenance_pin':'<data volume>/'+PIN_NAME,'reboot_pending':REBOOT_PENDING,'reboot_required':REBOOT_REQUIRED,
                     'catalog_names':list(CATALOG_NAMES),'compose_inputs':'the environment file and every compose file: type, owner, mode and links, never content or size'},
       'file_contents_read':[BOOT_ID_PATH,'the deployed revision file of the deploy tree','POST: the installed release file, compared with the signed hash and size'],
       'reported_not_gated':FACTS_NOT_GATED,
       'side_effects':SIDE_EFFECTS,
       'never':['a file opened for writing','mkdir','chmod','chown','rename','removal','docker exec','compose up','a container with a bind it can write through',
                'a container with a network','a shell','a pull','a systemctl verb other than show','daemon-reload','a network connection opened by this process',
                'a value of an environment, a byte of the release, of the policy or of the render in the receipt','the content, size or digest of the environment file',
                'a device or inode number observed by this run in the receipt unless the request signs rows_in_receipt true (the effects repeat the signed leaf rows)'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'release_bytes_in_request':MAX_RELEASE_BYTES,'installed_release_bytes':MAX_INSTALLED_BYTES,'policy_bytes':MAX_POLICY_BYTES,
                 'override_bytes':MAX_OVERRIDE_BYTES,'standard_input_bytes':MAX_STDIN_BYTES,'units':MAX_UNITS,'policy_instants':MAX_VALID_AT,
                 'release_directory_entries':MAX_DIRECTORY_ENTRIES,'timeouts_before_a_tool_is_skipped':MAX_TOOL_TIMEOUTS,
                 'signed_milliseconds':MAX_LIMIT_MILLISECONDS,'rendered_volumes':MAX_RENDERED_VOLUMES}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeLock):
    """Everything this source can do to the host: the read primitives, the signed commands, the lock probe."""


# ---------------------------------------------------------------- the signed plan (pure)
def unpacked(value,digest,size,limit,code):
    """Bytes that travel base64 in the signed plan: exactly the signed hash and size, and no larger than the limit."""
    need(type(value) is str and len(value)<=4*limit and hexpin(digest) and integer(size,1,limit),code)
    try:raw=base64.b64decode(value.encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused(code) from None
    need(sha(raw)==digest and len(raw)==size,code);return raw

def json_object(raw,code):
    try:value=strict(raw)
    except Refused:raise Refused(code) from None
    need(type(value) is dict,code);return value

def chain_spec(item,code,receives_entry=False):
    """One directory of the plan: its path, the rows a receipt of the same boot gave for it (or null: observed, compared
    with nothing) and the root below which an operational account owns the tree (or null). receives_entry: a later
    write creates an entry in it, so its signed rows must be rows that write accepts (no setgid directory)."""
    need(type(item) is dict and set(item)=={'path','rows','open_root'} and type(item['path']) is str and clean_path(item['path']) and item['path']!='/',code)
    root=item['open_root']
    need(root is None or (type(root) is str and clean_path(root) and root!='/' and inside(item['path'],root)),code)
    if item['rows'] is not None:validate_chain(item['rows'],item['path'],root,receives_entry)
    return item

def release_path_of(plan):
    release=plan['release'];return release['parent']['path']+'/'+release['directory_name']+'/'+release['file_name']
def container_path_of(plan):
    """The installed release file as the worker sees it: the data volume is bound at worker.data_target."""
    worker=plan['worker'];return worker['data_target']+release_path_of(plan)[len(worker['data_source']):]
def live_path_of(plan):
    """Where activate will create its directory: the signed name in the signed parent."""
    live=plan['live'];return live['parent']['path']+'/'+live['directory_name']
def host_path_of(plan,path):
    """The host path of a path the worker sees through its bind of the data volume."""
    worker=plan['worker'];return worker['data_source']+path[len(worker['data_target']):]
def mounts_of(plan):
    """The binds of the container, all read-only: in POST the installed release directory; in PRE none, or the one
    existing private directory the request signs as a probe of the bind itself."""
    release,probe=plan['release'],plan['bind_probe']
    if plan['mode']=='PRE':return [] if probe is None else [{'source':probe['directory']['path'],'target':probe['container_target'],'read_only':True}]
    return [{'source':release['parent']['path']+'/'+release['directory_name'],'target':release['container_target'],'read_only':True}]
def context_of(plan,request_sha256):
    release,policy,probe=plan['release'],plan['policy'],plan['bind_probe']
    return {'request_sha256':request_sha256,'revision':plan['revision'],'package_sha256':plan['package_sha256'],'epoch':EPOCH_NAME,
            'first_session':FIRST_SESSION_DAY,'release_sha256':release['sha256'],'release_bytes':release['bytes'],'release_b64':release['content_b64'],
            'release_path':None if plan['mode']=='PRE' else release['container_target']+'/'+release['file_name'],
            'policy_b64':None if policy is None else policy['content_b64'],'policy_sha256':None if policy is None else policy['sha256'],
            'policy_valid_at':[] if policy is None else list(policy['valid_at']),
            'probe_path':None if probe is None else probe['container_target']+'/'+probe['file_name']}
def frame_of(plan,request_sha256):
    """Standard input of the container: one assignment of signed values, then the pinned snippet."""
    return b'SIGNED_CONTEXT='+repr(context_of(plan,request_sha256)).encode('ascii')+b'\n'+VERIFY_SNIPPET.encode('ascii')

def policy_of(plan):
    """The policy candidate of the plan: its bytes are the signed ones, it names this epoch, this release, this
    revision, this package and the compiled order, and every signed instant lies inside its window."""
    policy=plan['policy']
    need(type(policy) is dict and set(policy)=={'sha256','bytes','content_b64','valid_at'},'POLICY_PLAN_INVALID')
    raw=unpacked(policy['content_b64'],policy['sha256'],policy['bytes'],MAX_POLICY_BYTES,'POLICY_NOT_THE_SIGNED_BYTES')
    body=json_object(raw,'POLICY_INVALID')
    # The controller compares the hash of the file; the assembler compares the hash of the canonical form of its
    # content (r2d2_v2_epoch_assembler.py: canonical, digest, POLICY_HASH). One signed hash meets both only when the
    # file is that canonical form, byte for byte.
    need(raw==json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8'),'POLICY_NOT_CANONICAL')
    need(body.get('schema')==POLICY_SCHEMA_NAME and body.get('mode')=='LIVE' and body.get('epoch')==EPOCH_NAME
         and body.get('release_sha')==plan['release']['sha256'] and body.get('code_revision')==plan['revision']
         and body.get('package_sha')==plan['package_sha256'] and body.get('order_sha')==RUNTIME_ORDER_SHA256,'POLICY_SCOPE')
    moments=policy['valid_at']
    need(type(moments) is list and 0<len(moments)<=MAX_VALID_AT and all(type(item) is str for item in moments) and len(set(moments))==len(moments),'POLICY_PLAN_INVALID')
    try:
        start,end=instant(body.get('valid_from')),instant(body.get('valid_until'));points=[instant(item) for item in moments]
    except Refused:raise Refused('POLICY_WINDOW') from None
    # An instant is spelled as isoformat() writes it: the container may run another interpreter than the dispatcher.
    need(all(point.isoformat()==item for point,item in zip(points,moments)),'POLICY_PLAN_INVALID')
    need(start<end and all(start<=point<end for point in points),'POLICY_WINDOW')
    return raw

def override_of(plan):
    """(bytes, environment) of the intended activation override: exactly the four live names of the worker service."""
    render=plan['render']
    need(type(render) is dict and set(render)=={'project','env_file','files','override_b64','override_sha256','override_bytes'},'RENDER_PLAN_INVALID')
    raw=unpacked(render['override_b64'],render['override_sha256'],render['override_bytes'],MAX_OVERRIDE_BYTES,'OVERRIDE_NOT_THE_SIGNED_BYTES')
    body=json_object(raw,'OVERRIDE_INVALID')
    need(set(body)=={'services'} and type(body['services']) is dict and set(body['services'])=={WORKER_SERVICE}
         and type(body['services'][WORKER_SERVICE]) is dict and set(body['services'][WORKER_SERVICE])=={'environment'},'OVERRIDE_INVALID')
    environment=body['services'][WORKER_SERVICE]['environment']
    need(type(environment) is dict and set(environment)==set(LIVE_KEYS) and all(text(value,ENVIRONMENT_VALUE) and value for value in environment.values()),'OVERRIDE_INVALID')
    return raw,environment

def activate_override(environment):
    """The bytes activate writes as its override file for these four values (activate: override_of)."""
    return json.dumps({'services':{WORKER_SERVICE:{'environment':environment}}},sort_keys=True).encode('ascii')

def full_profile(plan,environment):
    """The full dry run: every member Monday's runs will meet is signed, and the places and files are the ones
    install_release and activate use. Anything less is signed as REDUCED and succeeds under another name."""
    worker,release,deploy,render=plan['worker'],plan['release'],plan['deploy'],plan['render']
    need(plan['policy'] is not None and plan['bind_probe'] is not None and plan['live'] is not None and plan['limits'] is not None
         and worker['environment'] is True,'DRY_RUN_NOT_THE_FULL_PROFILE')
    tree=deploy['tree']['path']
    need(worker['data_source']==MONDAY_DATA_VOLUME and worker['data_target']==MONDAY_DATA_TARGET and release['parent']['path']==MONDAY_DATA_VOLUME
         and release['directory_name']==MONDAY_RELEASE_DIRECTORY and release['file_name']==MONDAY_RELEASE_FILE,'DRY_RUN_NOT_THE_PLACES_OF_INSTALL_RELEASE')
    need(render['env_file']==tree+'/'+MONDAY_ENV_FILE and render['files']==[tree+'/'+render['project']+'/'+MONDAY_COMPOSE_FILE]
         and deploy['version_name']==MONDAY_VERSION_NAME and deploy['lock_directory']['path']==tree+'/'+MONDAY_LOCK_DIRECTORY
         and deploy['lock_name']==MONDAY_LOCK_NAME and worker['container']=='%s-%s-1'%(render['project'],WORKER_SERVICE),'DRY_RUN_NOT_THE_LAYOUT_OF_ACTIVATE')
    need(override_of(plan)[0]==activate_override(environment),'OVERRIDE_NOT_AS_ACTIVATE_WRITES_IT')
    rows=release['parent']['rows']                                   # install_release: the signed rows show the data volume as a mount point
    need(rows is None or mount_point_of(rows)==MONDAY_DATA_VOLUME,'DATA_VOLUME_NOT_A_MOUNT_POINT')

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in MODES,'MODE_INVALID');pre=mode=='PRE'
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(text(plan['revision'],REVISION) and hexpin(plan['package_sha256']),'REVISION_OR_PACKAGE_UNBOUND')
    need(type(plan['rows_in_receipt']) is bool,'ROWS_FLAG_INVALID')
    profile=plan['dry_run']
    need((type(profile) is str and profile in DRY_RUNS) if pre else profile is None,'DRY_RUN_PROFILE_INVALID')
    image=plan['image']
    need(type(image) is dict and set(image)=={'reference','image_id'} and text(image['reference'],REFERENCE) and text(image['image_id'],IMAGE_ID),'IMAGE_PLAN_INVALID')
    need(not image['reference'].startswith('-'),'IMAGE_PLAN_INVALID')                 # activate refuses a rendered image that begins like an option
    worker=plan['worker']
    need(type(worker) is dict and set(worker)=={'container','environment','data_source','data_target'} and text(worker['container'],CONTAINER_NAME)
         and not text(worker['container'],CONTAINER_ID) and type(worker['environment']) is bool
         and all(type(worker[key]) is str and clean_path(worker[key]) and worker[key]!='/' for key in ('data_source','data_target')),'WORKER_PLAN_INVALID')
    release=plan['release']
    need(type(release) is dict and set(release)==set(RELEASE_KEYS) and hexpin(release['sha256']) and integer(release['bytes'],1,MAX_INSTALLED_BYTES)
         and text(release['directory_name'],ENTRY_NAME) and text(release['file_name'],ENTRY_NAME),'RELEASE_PLAN_INVALID')
    chain_spec(release['parent'],'RELEASE_PLAN_INVALID',True)
    need(inside(release['parent']['path'],worker['data_source']),'RELEASE_OUTSIDE_THE_DATA_VOLUME')
    need(clean_path(release_path_of(plan)) and clean_path(container_path_of(plan)),'RELEASE_PLAN_INVALID')
    if pre:
        need(release['container_target'] is None and release['directory_entries'] is None,'RELEASE_PLAN_INVALID')
        body=json_object(unpacked(release['content_b64'],release['sha256'],release['bytes'],MAX_RELEASE_BYTES,'RELEASE_NOT_THE_SIGNED_BYTES'),'RELEASE_INVALID')
        need(body.get('schema')==RELEASE_SCHEMA_NAME and body.get('mode')=='CERTIFIED' and body.get('epoch')==EPOCH_NAME
             and body.get('first_session')==FIRST_SESSION_DAY and body.get('code_revision')==plan['revision']
             and body.get('implementation_package_sha')==plan['package_sha256'],'RELEASE_SCOPE')
    else:
        need(release['content_b64'] is None and text(release['container_target'],CONTAINER_TARGET)
             and integer(release['directory_entries'],1,MAX_DIRECTORY_ENTRIES),'RELEASE_PLAN_INVALID')
    live=plan['live']
    need(live is None or (type(live) is dict and set(live)=={'parent','directory_name'} and text(live['directory_name'],ENTRY_NAME)),'LIVE_PLAN_INVALID')
    if live is not None:
        chain_spec(live['parent'],'LIVE_PLAN_INVALID',True)
        need(inside(live['parent']['path'],worker['data_source']) and clean_path(live_path_of(plan)),'LIVE_OUTSIDE_THE_DATA_VOLUME')
        place=release['parent']['path']+'/'+release['directory_name']
        need(not inside(live_path_of(plan),place) and not inside(place,live_path_of(plan)),'LIVE_AND_RELEASE_OVERLAP')
    limits=plan['limits']
    need(limits is None or (type(limits) is dict and set(limits)=={'render_ms','quick_ms','data_volume_free_bytes','data_volume_free_inodes'}
                            and integer(limits['render_ms'],1,MAX_LIMIT_MILLISECONDS) and integer(limits['quick_ms'],1,MAX_LIMIT_MILLISECONDS)
                            and integer(limits['data_volume_free_bytes'],0,MAX_FLOOR_BYTES) and integer(limits['data_volume_free_inodes'],0,MAX_FLOOR_BYTES)),'LIMITS_PLAN_INVALID')
    policy=plan['policy']
    need(policy is not None or pre,'POLICY_REQUIRED')
    if policy is not None:policy_of(plan)
    deploy=plan['deploy']
    need(type(deploy) is dict and set(deploy)=={'tree','lock_directory','lock_name','version_name'} and text(deploy['version_name'],DOTTED_NAME)
         and deploy['version_name'] not in ('.','..') and (deploy['lock_name'] is None or (text(deploy['lock_name'],DOTTED_NAME) and deploy['lock_name'] not in ('.','..'))),
         'DEPLOY_PLAN_INVALID')
    chain_spec(deploy['tree'],'DEPLOY_PLAN_INVALID');chain_spec(deploy['lock_directory'],'DEPLOY_PLAN_INVALID')
    need(inside(deploy['lock_directory']['path'],deploy['tree']['path']),'DEPLOY_PLAN_INVALID')
    render=plan['render']
    need(render is not None or not pre,'RENDER_REQUIRED')
    if render is not None:
        _,environment=override_of(plan)
        compose_arguments(render['project'],render['env_file'],render['files'],True)
        need(all(inside(item,deploy['tree']['path']) and item!=deploy['tree']['path'] for item in [render['env_file']]+render['files']),'RENDER_OUTSIDE_THE_DEPLOY_TREE')
        need(environment[LIVE_KEYS[3]]==release['sha256'] and environment[LIVE_KEYS[2]]==container_path_of(plan),'OVERRIDE_RELEASE_BINDING')
        need(clean_path(environment[LIVE_KEYS[0]]) and inside(environment[LIVE_KEYS[0]],worker['data_target']) and environment[LIVE_KEYS[0]]!=worker['data_target']
             and hexpin(environment[LIVE_KEYS[1]]) and (policy is None or environment[LIVE_KEYS[1]]==policy['sha256']),'OVERRIDE_POLICY_BINDING')
        # the policy file of the override is a file directly in the directory activate will create
        need(live is None or str(PurePosixPath(host_path_of(plan,environment[LIVE_KEYS[0]])).parent)==live_path_of(plan),'OVERRIDE_POLICY_NOT_IN_THE_LIVE_DIRECTORY')
        if profile=='FULL':full_profile(plan,environment)
    units=plan['units']
    need(type(units) is list and len(units)<=MAX_UNITS and all(type(item) is dict and set(item)=={'name','expected'} and text(item['name'],UNIT_NAME) for item in units)
         and len({item['name'] for item in units})==len(units),'UNITS_PLAN_INVALID')
    need(all(item['expected'] is None or (type(item['expected']) is dict and item['expected'] and set(item['expected'])<=set(GATED_PROPERTIES)
                                          and all(text(value,UNIT_STATE) for value in item['expected'].values())) for item in units),'UNITS_PLAN_INVALID')
    journal=plan['journal']
    need(journal is None or (type(journal) is dict and set(journal)=={'path','floor_bytes'} and type(journal['path']) is str and clean_path(journal['path'])
                             and journal['path']!='/' and (journal['floor_bytes'] is None or integer(journal['floor_bytes'],0,MAX_FLOOR_BYTES))),'JOURNAL_PLAN_INVALID')
    need(plan['docker_config'] is None or (text(plan['docker_config'],COMMAND_VARIABLES['DOCKER_CONFIG']) and clean_path(plan['docker_config'])),'DOCKER_CONFIG_INVALID')
    need(plan['docker_config'] is None or profile=='REDUCED','DOCKER_CONFIG_ONLY_IN_A_REDUCED_DRY_RUN')
    probe=plan['bind_probe']
    need(probe is None or (pre and type(probe) is dict and set(probe)=={'directory','file_name','container_target'} and text(probe['file_name'],DOTTED_NAME)
                           and probe['file_name'] not in ('.','..') and text(probe['container_target'],CONTAINER_TARGET)),'BIND_PROBE_INVALID')
    if probe is not None:chain_spec(probe['directory'],'BIND_PROBE_INVALID')
    run_arguments('verify',image['image_id'],mounts_of(plan),VERIFY_COMMAND,CONTAINER_PREFIX+'0'*16)
    need(len(frame_of(plan,'0'*64))<=MAX_STDIN_BYTES,'VERIFY_FRAME_TOO_LARGE')

def expected_environment(plan):
    """What is compared with the environment of the running worker: the revision and, with a render, the four intended
    values; without one, the four names against the empty value, so that only their presence is learnt."""
    intended={key:'' for key in LIVE_KEYS} if plan['render'] is None else override_of(plan)[1]
    return dict(intended,**{BUILD_KEY:plan['revision']})

def chain_effects_of(item):
    if item['rows'] is None:
        return {'path':item['path'],'open_root':item['open_root'],'rows_signed':False,'row':None,'chain_sha256':None,'mount_point_by_device_change':None}
    return dict(chain_effects(item['rows']),open_root=item['open_root'],rows_signed=True)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    release,policy,render,deploy=plan['release'],plan['policy'],plan['render'],plan['deploy'];pre=plan['mode']=='PRE'
    return {'operation':OPERATION,'mode':plan['mode'],'gates_first_session_readback':not pre,
            'epoch':EPOCH_NAME,'first_session':FIRST_SESSION_DAY,'revision':plan['revision'],'package_sha256':plan['package_sha256'],
            'image':plan['image'],'worker':plan['worker'],
            'release':{'sha256':release['sha256'],'bytes':release['bytes'],'path':release_path_of(plan),'path_in_the_worker':container_path_of(plan),
                       'source':'THE_BYTES_OF_THE_REQUEST_ON_STANDARD_INPUT' if pre else 'THE_INSTALLED_FILE_THROUGH_A_READ_ONLY_BIND',
                       'expected_on_the_host':'DIRECTORY_ABSENT' if pre else 'INSTALLED','directory_entries':release['directory_entries'],
                       'parent':chain_effects_of(release['parent'])},
            'verify':{'snippet_sha256':VERIFY_SNIPPET_SHA256,'image_id':plan['image']['image_id'],'binds':mounts_of(plan),'network':'none',
                      'command':VERIFY_COMMAND,'alarm_seconds':VERIFY_ALARM_SECONDS},
            'policy':None if policy is None else {'sha256':policy['sha256'],'bytes':policy['bytes'],'valid_at':policy['valid_at']},
            'render':None if render is None else {'project':render['project'],'env_file':render['env_file'],'files':render['files'],
                                                  'override_sha256':render['override_sha256'],'service':WORKER_SERVICE,'environment':override_of(plan)[1]},
            'deploy':{'tree':chain_effects_of(deploy['tree']),'lock_directory':chain_effects_of(deploy['lock_directory']),
                      'lock':None if deploy['lock_name'] is None else deploy['lock_directory']['path']+'/'+deploy['lock_name'],
                      'version_file':deploy['tree']['path']+'/'+deploy['version_name']},
            'maintenance_pin':plan['worker']['data_source']+'/'+PIN_NAME,
            'dry_run':plan['dry_run'],'rehearses_install_release_and_activate':plan['dry_run']=='FULL','limits':plan['limits'],
            'live':None if plan['live'] is None else {'path':live_path_of(plan),'expected_on_the_host':'DIRECTORY_ABSENT','parent':chain_effects_of(plan['live']['parent'])},
            'bind_probe':None if plan['bind_probe'] is None else {'directory':chain_effects_of(plan['bind_probe']['directory']),
                                                                  'file':plan['bind_probe']['directory']['path']+'/'+plan['bind_probe']['file_name']},
            'units':plan['units'],'journal':plan['journal'],'docker_config':plan['docker_config'],'rows_in_receipt':plan['rows_in_receipt'],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],'writes':0,'containers_run':1,'activation':False}
def success_of(plan):
    if plan['mode']=='PRE':return PRE_OUTCOME if plan['dry_run']=='FULL' else PRE_REDUCED_OUTCOME
    return COMPLETE_OUTCOME


# ---------------------------------------------------------------- the observations
def item_of(status='COMPLETE',findings=(),**fields):
    """One observation: whether it could be made (status) and, separately, whether what was seen is what was signed."""
    codes=sorted(set(findings))
    return dict(fields,status=status,findings=codes,matches=(not codes) if status=='COMPLETE' else None)

def verdict(value):
    return type(value) is dict and set(value)=={'valid','code'} and type(value['valid']) is bool and (value['code'] is None or text(value['code'],SNIPPET_CODE))

def verify_line(raw,returncode,plan,request_sha256):
    """The one line the snippet prints, member by member: booleans, constant codes, two version strings. None when a
    run that failed printed nothing this source can read."""
    try:line=single_line(raw)
    except Refused:
        need(returncode!=0,'VERIFY_OUTPUT_INVALID');return None
    if returncode!=0:
        return line if set(line)=={'status','code'} and line['status']=='FAILED' and text(line['code'],SNIPPET_CODE) else None
    need(set(line)==set(VERIFY_LINE_KEYS) and line['status']=='DONE' and line['context_request_sha256']==request_sha256
         and type(line['package_equal_signed']) is bool,'VERIFY_OUTPUT_INVALID')
    release,policy,facts=line['release'],line['policy'],line['facts']
    need(type(release) is dict and set(release)==set(VERIFY_RELEASE_KEYS) and release['source']==('STDIN' if plan['mode']=='PRE' else 'FILE')
         and all(type(release[key]) is bool for key in VERIFY_RELEASE_KEYS-{'source','code'})
         and (release['code'] is None or text(release['code'],SNIPPET_CODE)) and (release['code'] is None)==release['verified'],'VERIFY_OUTPUT_INVALID')
    need(type(facts) is dict and set(facts)=={'python','calendar_version'} and text(facts['python'],r'[0-9]{1,2}\.[0-9]{1,3}\.[0-9]{1,3}')
         and text(facts['calendar_version'],'[0-9A-Za-z.+_-]{1,32}'),'VERIFY_OUTPUT_INVALID')
    need((policy is None)==(plan['policy'] is None) and (line['probe'] is None)==(plan['bind_probe'] is None)
         and (line['probe'] is None or verdict(line['probe'])),'VERIFY_OUTPUT_INVALID')
    if policy is not None:
        need(type(policy) is dict and set(policy)==set(VERIFY_POLICY_KEYS) and type(policy['hash_equal_signed']) is bool and verdict(policy['controller_now'])
             and verdict(policy['assembler']) and type(policy['controller_at']) is list and len(policy['controller_at'])==len(plan['policy']['valid_at'])
             and all(verdict(item) for item in policy['controller_at']),'VERIFY_OUTPUT_INVALID')
    return line

def free_inodes(host,fd):
    """Inodes a non-root writer can still take on the filesystem of a held descriptor; None where the filesystem
    counts none (f_files 0: it does not run out of them apart from its bytes). (activate: free_inodes)"""
    numbers=host.fstatvfs(fd);total,free=getattr(numbers,'f_files',0),getattr(numbers,'f_favail',None)
    return free if integer(total,1) and integer(free) else None

def plain(path):
    """An absolute path as compose may print it (a trailing or a doubled slash, a "." component) in the one spelling the
    signed paths have; anything else stays as it is, and so stays unequal to a signed path. (activate: plain)"""
    return str(PurePosixPath(path)) if type(path) is str else path

def data_bind_of(volumes,paths,source,target):
    """activate's own rule for the render it recreates from (activate: service_of): every volume has a target, and each
    of the paths the override names is covered by exactly one of them, which is the bind of the signed source at the
    signed target and is not read-only. None: the volumes are not a list activate accepts. Otherwise True or False."""
    if not (type(volumes) is list and len(volumes)<=MAX_RENDERED_VOLUMES
            and all(type(item) is dict and type(item.get('target')) is str and item['target'] for item in volumes)):return None
    binds=[(plain(item['target']),item) for item in volumes]
    for path in paths:
        covering=[pair for pair in binds if inside(path,pair[0])]
        if not (len(covering)==1 and covering[0][0]==target and covering[0][1].get('type')=='bind'
                and plain(covering[0][1].get('source'))==source and covering[0][1].get('read_only') in (None,False)):return False
    return True

class Readback:
    """The observations of one run. Each method is one item of the receipt and fails on its own."""
    def __init__(self,plan,host,gate,commands,bound,monotonic):
        self.plan,self.host,self.gate,self.commands,self.monotonic=plan,host,gate,commands,monotonic
        self.pre=plan['mode']=='PRE';self.held={};self.same_boot=True;self.config_signed=plan['docker_config'];self.config_usable=False
        self.request_sha256=bound['request_sha256'];self.name=CONTAINER_PREFIX+bound['go_sha256'][:16]
        self.frame=frame_of(plan,self.request_sha256);self.expected=expected_environment(plan)
        self.override=None if plan['render'] is None else override_of(plan)[0]
        self.worker_id=None;self.entries_before=None

    def config(self):
        """DOCKER_CONFIG of every docker command: nothing when the plan signs none; otherwise that directory, and only
        after it was seen private and empty."""
        if self.config_signed is None:return None
        need(self.config_usable,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE');return self.config_signed

    def timed(self,action):
        """(what one command answered, the milliseconds it took)."""
        mark=self.monotonic();result=action();return result,int((self.monotonic()-mark)*1000)
    def slow(self,key,*milliseconds):
        """The finding of a command that took longer than the signed limit of its kind; nothing without signed limits."""
        limits=self.plan['limits']
        if limits is None or all(value<=limits[key] for value in milliseconds):return []
        return ['RENDER_SLOWER_THAN_THE_SIGNED_LIMIT' if key=='render_ms' else 'DOCKER_CALL_SLOWER_THAN_THE_SIGNED_LIMIT']

    def boot(self):
        self.same_boot=boot_id_sha256(self.host,self.gate)==self.plan['evidence_boot_id_sha256']
        # A reboot may renumber devices: one finding here, and the signed rows are then compared without the device.
        return item_of(findings=[] if self.same_boot else ['EVIDENCE_FROM_EARLIER_BOOT'],equal_to_the_evidence=self.same_boot,
                       device_numbers_compared=self.same_boot)

    def directory(self,key,spec,receives_entry=False,write_follows=False,volume=None):
        """One directory walked from "/" without following a link and held for the rest of the run. With signed rows the
        walk compares every component; without, it records what it finds. Identities are reported as booleans and
        counts; the rows themselves only when the request signs rows_in_receipt.
        receives_entry: a write creates an entry here, so the observed rows are judged as that write judges its signed
        rows (the family's rule, no setgid directory; with volume, the filesystem's mount point is that volume).
        write_follows: that write is still to come, so rows it would refuse are a finding and not only a fact."""
        host,signed=self.host,spec['rows'];observed=[];findings=[];fd=None
        try:
            if signed is None:fd=descend(host,spec['path'],self.gate,observed)
            else:fd=walk_pinned(host,signed,self.gate,observed,self.same_boot)
        except FileNotFoundError:findings.append('PARENT_MISSING')
        except Refused as error:
            if str(error) not in WALK_FINDINGS:raise
            findings.append(str(error))
        facts={'path':spec['path'],'components':len(prefixes(spec['path'])),'components_observed':len(observed),'rows_signed':signed is not None,
               'as_signed':None if signed is None else fd is not None,'held':fd is not None}
        if fd is None:
            if signed is not None and findings==['PARENT_IDENTITY_MISMATCH']:
                facts['fields_that_differ']={field:observed[-1][field]!=signed[len(observed)-1][field] for field in ROW_FIELDS}
        else:
            try:
                self.held[key]=Pinned(host,fd,rows=[dict(row) for row in observed] if signed is None else signed,compare_device=signed is None or self.same_boot)
            except BaseException:
                host.close(fd);raise
            leaf=observed[-1]
            try:validate_chain([dict(row) for row in observed],spec['path'],spec['open_root'],receives_entry);acceptable,why=True,None
            except Refused as error:acceptable,why=False,code_of(error,'CHAIN_ROW_INVALID')
            on_volume=None if volume is None else mount_point_of(observed)==volume
            if acceptable and on_volume is False:acceptable,why=False,'DATA_VOLUME_NOT_A_MOUNT_POINT'
            if write_follows and not acceptable:findings.append('DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS')
            # room for what the write creates, on the filesystem of the directory it creates in, as that write asks for it
            available,inodes=free_bytes(host,fd),free_inodes(host,fd);limits=self.plan['limits']
            if receives_entry and limits is not None:
                facts.update(free_bytes_floor=limits['data_volume_free_bytes'],free_inodes_floor=limits['data_volume_free_inodes'])
                if available<limits['data_volume_free_bytes']:findings.append('DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')
                if inodes is not None and inodes<limits['data_volume_free_inodes']:findings.append('DATA_VOLUME_FREE_INODES_BELOW_FLOOR')
            facts.update(owner_uid=leaf['uid'],owner_gid=leaf['gid'],mode_octal='%04o'%leaf['mode'],
                         device_changes=sum(1 for previous,row in zip(observed,observed[1:]) if row['device']!=previous['device']),
                         mount_point_by_device_change=mount_point_of(observed),
                         leaf_is_a_mount_point=len(observed)>1 and observed[-1]['device']!=observed[-2]['device'],
                         world_writable_without_sticky=world_writable_without_sticky(leaf),setgid=bool(leaf['mode']&stat.S_ISGID),
                         rows_acceptable_to_a_write=acceptable,rows_refusal=why,judged_as_receiving_an_entry=receives_entry,
                         mount_point_is_the_data_volume=on_volume,
                         entries=count_entries(host,fd,self.gate,MAX_COUNT),bytes_available=available,inodes_available=inodes)
        if self.plan['rows_in_receipt']:facts['observed_rows']=observed
        return item_of(findings=findings,**facts)

    def release_target(self):
        """PRE: nothing stands where install_release will create its directory. POST: the directory and the file as
        install_release leaves them, the bytes equal to the signed hash; the directory is then held for the bind."""
        parent=self.held.get('RELEASE_PARENT');need(parent is not None,'DIRECTORY_NOT_HELD')
        host,release=self.host,self.plan['release'];name=release['directory_name'];expected='DIRECTORY_ABSENT' if self.pre else 'INSTALLED'
        parent.verify(self.gate);self.gate()
        try:named=host.lstat(name,parent.fd)
        except FileNotFoundError:
            return item_of(findings=[] if self.pre else ['RELEASE_DIRECTORY_ABSENT'],expected=expected,exists=False)
        if self.pre:return item_of(findings=['RELEASE_TARGET_ALREADY_EXISTS'],expected=expected,exists=True,type=kind(named.st_mode))
        if not stat.S_ISDIR(named.st_mode):
            return item_of(findings=['RELEASE_DIRECTORY_NOT_A_DIRECTORY'],expected=expected,exists=True,type=kind(named.st_mode))
        self.gate();fd=host.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime(),dir_fd=parent.fd)
        try:
            info=host.fstat(fd);need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino),'RELEASE_DIRECTORY_CHANGED_DURING_READ')
            self.held['RELEASE_DIRECTORY']=Pinned(host,fd,parent=parent,name=name)
        except BaseException:
            host.close(fd);raise
        findings=[];entries=count_entries(host,fd,self.gate,MAX_COUNT)
        directory={'type':'dir','uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),
                   'on_the_device_of_its_parent':info.st_dev==parent.identity[0],'entries':entries,'entries_signed':release['directory_entries']}
        if (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))!=(0,0,RELEASE_DIRECTORY_MODE):findings.append('RELEASE_DIRECTORY_METADATA')
        if not directory['on_the_device_of_its_parent']:findings.append('RELEASE_DIRECTORY_IS_A_MOUNT_POINT')
        if entries!=release['directory_entries']:findings.append('RELEASE_DIRECTORY_ENTRIES')
        self.gate()
        try:leaf=host.lstat(release['file_name'],fd)
        except FileNotFoundError:
            return item_of(findings=findings+['RELEASE_FILE_ABSENT'],expected=expected,exists=True,directory=directory,file={'exists':False})
        found={'exists':True,'type':kind(leaf.st_mode),'uid':leaf.st_uid,'gid':leaf.st_gid,'mode_octal':'%04o'%stat.S_IMODE(leaf.st_mode),'links':leaf.st_nlink}
        if not stat.S_ISREG(leaf.st_mode):
            return item_of(findings=findings+['RELEASE_FILE_NOT_REGULAR'],expected=expected,exists=True,directory=directory,file=found)
        if (leaf.st_uid,leaf.st_gid,stat.S_IMODE(leaf.st_mode),leaf.st_nlink)!=(0,0,RELEASE_FILE_MODE,1):findings.append('RELEASE_FILE_METADATA')
        try:raw,read=read_regular(host,release['file_name'],fd,self.gate,MAX_INSTALLED_BYTES)
        except Refused as error:
            if str(error)!='FILE_TOO_LARGE':raise
            return item_of(findings=findings+['RELEASE_FILE_TOO_LARGE'],expected=expected,exists=True,directory=directory,file=found)
        need((read.st_dev,read.st_ino)==(leaf.st_dev,leaf.st_ino),'RELEASE_FILE_CHANGED_DURING_READ')
        found['bytes_equal_signed']=sha(raw)==release['sha256'] and len(raw)==release['bytes']
        if not found['bytes_equal_signed']:findings.append('RELEASE_FILE_BYTES_MISMATCH')
        return item_of(findings=findings,expected=expected,exists=True,directory=directory,file=found)

    def live_target(self):
        """Nothing stands yet where activate will create its directory: one lstat of the signed name in the held,
        signed parent (activate refuses DESTINATION_PRESENT before any effect, and its GO is then spent)."""
        parent=self.held.get('LIVE_PARENT');need(parent is not None,'DIRECTORY_NOT_HELD')
        parent.verify(self.gate);self.gate()
        try:named=self.host.lstat(self.plan['live']['directory_name'],parent.fd)
        except FileNotFoundError:return item_of(expected='DIRECTORY_ABSENT',exists=False)
        return item_of(findings=['LIVE_DIRECTORY_ALREADY_EXISTS'],expected='DIRECTORY_ABSENT',exists=True,type=kind(named.st_mode))

    def configuration(self):
        """The signed configuration directory of the docker CLI: root:root 0700 and empty, counted before any command."""
        rows=[];fd=descend(self.host,self.config_signed,self.gate,rows)
        try:
            info=self.host.fstat(fd);self.held['DOCKER_CONFIG']=Pinned(self.host,fd,rows=rows)
        except BaseException:
            self.host.close(fd);raise
        private=(info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,DOCKER_CONFIG_MODE)
        self.entries_before=count_entries(self.host,fd,self.gate,MAX_COUNT);self.config_usable=private and self.entries_before==0
        return item_of(findings=[] if self.config_usable else ['DOCKER_CONFIG_NOT_PRIVATE_AND_EMPTY'],path=self.config_signed,private=private,
                       entries_before=self.entries_before,passed_to_the_docker_commands=self.config_usable)

    def configuration_after(self):
        handle=self.held.get('DOCKER_CONFIG');need(handle is not None and self.entries_before is not None,'DOCKER_CONFIG_DIRECTORY_UNAVAILABLE')
        entries=count_entries(self.host,handle.fd,self.gate,MAX_COUNT)
        return item_of(findings=[] if entries==self.entries_before else ['DOCKER_CONFIG_CHANGED_DURING_RUN'],entries_before=self.entries_before,entries_after=entries)

    def verify(self):
        """The one container of the run. Started before every other command: it needs its whole class time."""
        plan=self.plan;config=self.config();mounts=mounts_of(plan)
        if mounts:
            handle=self.held.get('BIND_PROBE' if self.pre else 'RELEASE_DIRECTORY')
            need(handle is not None,'BIND_PROBE_NOT_HELD' if self.pre else 'RELEASE_DIRECTORY_NOT_HELD');handle.verify(self.gate)
        result=container_run(self.commands,'verify',plan['image']['image_id'],mounts,VERIFY_COMMAND,self.frame,docker_config=config,container_name=self.name)
        facts={'started':result['started'],'returned':result['returned'],'returncode':result['returncode'],'binds':len(mounts),
               'frame_sha256':sha(self.frame),'snippet_sha256':VERIFY_SNIPPET_SHA256}
        if not result['returned']:
            # Not started: nothing ran. Started and not returned: the CLI was killed; "containers" says what is left.
            return dict(facts,status='UNAVAILABLE',code=result['code'] if text(result['code'],CODE) else 'VERIFY_RUN_NOT_COMPLETED',
                        container_may_still_exist=result['started'])
        if mounts:
            try:handle.verify(self.gate);facts['bind_source_stable']=True
            except Refused as error:
                if str(error) in EXPIRED_CODES:raise
                facts['bind_source_stable']=False
        code=result['returncode'];facts['engine_failure']=code in RUN_ENGINE_STATUSES
        try:line=verify_line(result['output'],code,plan,self.request_sha256)
        except Refused as error:return dict(facts,status='UNAVAILABLE',code=code_of(error,'VERIFY_OUTPUT_INVALID'),container_may_still_exist=False)
        if code!=0:
            if facts['engine_failure']:return item_of(findings=['VERIFY_ENGINE_FAILURE'],**facts)
            if line is None:return item_of(findings=['VERIFY_RUN_FAILED'],**facts)
            return item_of(findings=['VERIFY_SNIPPET_FAILED'],snippet_code=line['code'],**facts)
        release,policy=line['release'],line['policy'];findings=[]
        if mounts and not facts['bind_source_stable']:findings.append('BIND_SOURCE_REPLACED_DURING_RUN')
        if line['probe'] is not None and not line['probe']['valid']:findings.append('BIND_PROBE_NOT_READ')
        if not line['package_equal_signed']:findings.append('PACKAGE_NOT_THE_SIGNED_ONE')
        if not release['read']:findings.append('RELEASE_NOT_READ_IN_THE_CONTAINER')
        elif not release['bytes_equal_signed']:findings.append('RELEASE_BYTES_NOT_THE_SIGNED_ONES')
        if not release['verified']:findings.append('RELEASE_NOT_VERIFIED')
        elif not (release['mode_certified'] and release['epoch_equal'] and release['first_session_equal'] and release['ebar_bound']):
            findings.append('RELEASE_SCOPE_NOT_AS_SIGNED')
        if policy is not None:
            if not policy['hash_equal_signed']:findings.append('POLICY_BYTES_NOT_THE_SIGNED_ONES')
            if not all(item['valid'] for item in policy['controller_at']):findings.append('POLICY_REFUSED_BY_THE_CONTROLLER')
            if not policy['assembler']['valid']:findings.append('POLICY_REFUSED_BY_THE_ASSEMBLER')
        return item_of(findings=findings,release=release,policy=policy,probe=line['probe'],package_equal_signed=line['package_equal_signed'],image_facts=line['facts'],**facts)

    def containers(self):
        """Every container the engine knows, as counts; and whether the container of this run is still there."""
        rows,taken=self.timed(lambda:container_list(self.commands,self.config()));present=any(row['name']==self.name for row in rows)
        states={state:len([row for row in rows if row['state']==state]) for state in sorted({row['state'] for row in rows})}
        # a container an interrupted recreate of the worker's service left under its temporary name <hex>_<container>:
        # activate refuses on it before any effect (WORKER_SERVICE_LEFTOVER_CONTAINER; activate: leftovers)
        leftovers=len([row for row in rows if row['name'].endswith('_'+self.plan['worker']['container'])])
        return item_of(findings=(['VERIFY_CONTAINER_LEFT_BEHIND'] if present else [])+(['WORKER_SERVICE_LEFTOVER_CONTAINER'] if leftovers else [])+self.slow('quick_ms',taken),
                       command_ms=taken,listed=len(rows),by_state=states,worker_service_leftovers=leftovers,
                       worker_listed=any(row['name']==self.plan['worker']['container'] for row in rows),verify_container_present=present)

    def image(self):
        signed=self.plan['image'];facts,taken=self.timed(lambda:image_facts(self.commands,signed['reference'],self.config()));findings=self.slow('quick_ms',taken)
        equal=facts['id']==signed['image_id'];revision=facts['revision_label']==self.plan['revision']
        if not equal:findings.append('IMAGE_ID_MISMATCH')
        if not revision:findings.append('IMAGE_REVISION_MISMATCH')
        return item_of(findings=findings,command_ms=taken,reference=signed['reference'],id_equal_signed=equal,revision_equal_signed=revision,
                       repo_tag_count=facts['repo_tag_count'],reference_among_repo_tags=facts['reference_among_repo_tags'])

    def worker(self):
        signed=self.plan['worker'];facts,taken=self.timed(lambda:container_facts(self.commands,signed['container'],docker_config=self.config()));findings=self.slow('quick_ms',taken)
        self.worker_id=facts['id'];equal=facts['image_id']==self.plan['image']['image_id'];running=facts['running'] and facts['state']=='running'
        if not equal:findings.append('WORKER_IMAGE_MISMATCH')
        if not running:findings.append('WORKER_NOT_RUNNING')
        return item_of(findings=findings,command_ms=taken,container=signed['container'],image_id_equal_signed=equal,running=running,state=facts['state'],
                       restarts=facts['restarts'],health=facts['health'],started_at=facts['started_at'],
                       image_reference_equal_signed=facts['image_reference']==self.plan['image']['reference'])

    def worker_environment(self):
        """Booleans only: the revision of the worker, and that it has none of the four live names yet, with or without
        a value: activate refuses a worker that already carries one (WORKER_ALREADY_CARRIES_THE_KEYS), before any effect."""
        need(self.worker_id is not None,'WORKER_NOT_OBSERVED')
        values,taken=self.timed(lambda:container_environment(self.commands,self.worker_id,self.expected,docker_config=self.config()))
        build=values[BUILD_KEY]['equal'];present=[key for key in LIVE_KEYS if values[key]['present']]
        return item_of(findings=([] if build else ['WORKER_BUILD_REVISION_MISMATCH'])+(['WORKER_ALREADY_CARRIES_A_LIVE_NAME'] if present else [])
                                +self.slow('quick_ms',taken),command_ms=taken,build_revision_equal_signed=build,
                       live_names_present=len(present),
                       live_names_equal_to_the_intended_values=None if self.plan['render'] is None else len([key for key in LIVE_KEYS if values[key]['equal']]),
                       names={key:values[key] for key in sorted(values)})

    def render(self):
        """The render of the signed files, and the render with the override on standard input. Both stay in memory:
        what leaves is booleans and counts."""
        plan=self.plan;render=plan['render'];config=self.config();intended=override_of(plan)[1];findings=[]
        mark=self.monotonic()
        base=compose_render(self.commands,'render_base',render['project'],render['env_file'],render['files'],plan['revision'],docker_config=config)
        middle=self.monotonic()
        over=compose_render(self.commands,'render_override',render['project'],render['env_file'],render['files'],plan['revision'],override=self.override,docker_config=config)
        end=self.monotonic()
        before=compose_service(base,WORKER_SERVICE);after=compose_service(over,WORKER_SERVICE)
        equal={key:after['environment'].get(key)==intended[key] for key in LIVE_KEYS}
        build=after['environment'].get(BUILD_KEY)==plan['revision'];reference=after['image']==plan['image']['reference']
        others=set(base['services'])==set(over['services']) and all(base['services'][name]==over['services'][name] for name in base['services'] if name!=WORKER_SERVICE)
        project={key:value for key,value in base.items() if key!='services'}=={key:value for key,value in over.items() if key!='services'}
        def without(service,names):
            return {key:({name:item for name,item in value.items() if name not in names} if key=='environment' and type(value) is dict else value)
                    for key,value in service.items()}
        only=without(base['services'][WORKER_SERVICE],LIVE_KEYS)==without(over['services'][WORKER_SERVICE],LIVE_KEYS)
        if not all(equal.values()):findings.append('RENDER_ENVIRONMENT_NOT_AS_SIGNED')
        if not build:findings.append('RENDER_BUILD_REVISION_MISMATCH')
        if not reference:findings.append('RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE')
        if not (others and project):findings.append('OVERRIDE_CHANGES_MORE_THAN_THE_WORKER')
        if not only:findings.append('OVERRIDE_CHANGES_MORE_THAN_THE_LIVE_NAMES')
        # the policy file and the release file of the override, reached through the one bind of the data volume
        volumes=over['services'][WORKER_SERVICE].get('volumes');worker=plan['worker']
        bound=data_bind_of(volumes,[intended[LIVE_KEYS[0]],intended[LIVE_KEYS[2]]],worker['data_source'],worker['data_target'])
        if bound is None:findings.append('RENDER_VOLUMES_INVALID')
        elif not bound:findings.append('WORKER_MOUNT_NOT_AS_SIGNED')
        bind={'volumes_listed':len(volumes) if type(volumes) is list else None,'policy_and_release_reached_through_the_one_signed_bind':bound}
        base_ms,override_ms=int((middle-mark)*1000),int((end-middle)*1000);findings+=self.slow('render_ms',base_ms,override_ms)
        return item_of(findings=findings,services=len(over['services']),environment_equal=equal,build_revision_equal=build,image_reference_equal_signed=reference,
                       other_services_unchanged=others and project,worker_changes_only_the_live_names=only,
                       live_names_already_in_the_base_render=len([key for key in LIVE_KEYS if key in before['environment']]),
                       data_volume_bind=bind,rendered_canonical_bytes=len(canonical(over)),
                       base_ms=base_ms,override_ms=override_ms)

    def deploy_files(self):
        """The deployed revision (content compared as activate compares it: the revision, surrounding white space
        aside; the pipeline writes the revision and one newline), and the inputs of compose by lstat: never their
        content or size."""
        tree=self.held.get('DEPLOY_TREE');need(tree is not None,'DIRECTORY_NOT_HELD')
        plan=self.plan;deploy,render=plan['deploy'],plan['render'];findings=[]
        try:
            raw,_=read_regular(self.host,deploy['version_name'],tree.fd,self.gate,MAX_REVISION_FILE_BYTES);version={'exists':True,'equal_to_the_signed_revision':raw.strip()==plan['revision'].encode('ascii')}
            if not version['equal_to_the_signed_revision']:findings.append('DEPLOYED_REVISION_MISMATCH')
        except FileNotFoundError:
            version={'exists':False,'equal_to_the_signed_revision':False};findings.append('DEPLOYED_REVISION_FILE_ABSENT')
        inputs=[]
        for path in ([] if render is None else [render['env_file']]+render['files']):
            found=probe(self.host,path,self.gate)
            if found.get('status')!='COMPLETE':raise Refused(found.get('code') if text(found.get('code'),CODE) else 'COMPOSE_INPUT_UNAVAILABLE')
            regular=found['exists'] and found['type']=='file'
            inputs.append({'exists':found['exists'],'regular':regular,'uid':found.get('uid'),'gid':found.get('gid'),'mode_octal':found.get('mode_octal'),'links':found.get('links')})
            if not regular:findings.append('COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR')
        return item_of(findings=findings,deployed_revision=version,compose_inputs=inputs)

    def lstat_of(self,path,finding_when_present=None,finding_when_absent=None):
        found=probe(self.host,path,self.gate)
        if found.get('status')!='COMPLETE':raise Refused(found.get('code') if text(found.get('code'),CODE) else 'PROBE_UNAVAILABLE')
        findings=[finding_when_present] if found['exists'] and finding_when_present else [finding_when_absent] if not found['exists'] and finding_when_absent else []
        return item_of(findings=findings,exists=found['exists'],type=found.get('type'),uid=found.get('uid'),gid=found.get('gid'),mode_octal=found.get('mode_octal'))

    def pin(self):
        """The maintenance pin in the root of the data volume, by lstat: its presence holds the automatic routine."""
        found=self.lstat_of(self.plan['worker']['data_source']+'/'+PIN_NAME,finding_when_absent='MAINTENANCE_PIN_ABSENT')
        if found['exists'] and found['type']!='file':return item_of(findings=['MAINTENANCE_PIN_NOT_REGULAR'],exists=True,type=found['type'])
        if not found['exists']:return found
        owned=(found['uid'],found['gid'])==(0,0)
        # install_release refuses a pin that is not root:root (MAINTENANCE_PIN_NOT_ROOT_OWNED); after it, a fact
        return item_of(findings=['MAINTENANCE_PIN_NOT_ROOT_OWNED'] if self.pre and not owned else [],root_owned=owned,
                       **{key:found[key] for key in ('exists','type','uid','gid','mode_octal')})

    def unit(self,signed):
        name=signed['name'];raw=self.commands.output('unit',name)
        need(re.fullmatch(rb'[ -~\n]*',raw) is not None,'PROPERTY_OUTPUT_INVALID');values={}
        for line in raw.decode('ascii').splitlines():
            if not line:continue
            key,separator,value=line.partition('=');need(separator=='=','PROPERTY_LINE_INVALID')
            if key in UNIT_PROPERTIES:
                need(key not in values and text(value,'[A-Za-z0-9_./:@+ -]{0,512}'),'PROPERTY_VALUE_INVALID');values[key]=value
        need(set(values)==set(UNIT_PROPERTIES),'PROPERTY_MISSING');need(values['Id']==name,'UNIT_ID_MISMATCH')
        expected=signed['expected'] or {}
        return item_of(findings=[] if all(values[key]==value for key,value in expected.items()) else ['UNIT_STATE_NOT_AS_SIGNED'],
                       properties=values,expected=signed['expected'],gated=signed['expected'] is not None)

    def journal(self):
        """Free space of the filesystem of the journal root, on the root itself. A root that does not exist is a fact;
        it is a finding only when the request signs a floor."""
        signed=self.plan['journal'];floor=signed['floor_bytes']
        try:fd=descend(self.host,signed['path'],self.gate)
        except FileNotFoundError:
            return item_of(findings=[] if floor is None else ['JOURNAL_ROOT_ABSENT'],path=signed['path'],exists=False,floor_bytes=floor)
        try:
            info=self.host.fstat(fd);available=free_bytes(self.host,fd);entries=count_entries(self.host,fd,self.gate,MAX_COUNT);names={}
            for name in CATALOG_NAMES:
                self.gate()
                try:self.host.lstat(name,fd);names[name]=True
                except FileNotFoundError:names[name]=False
            above=None if floor is None else available>=floor
            return item_of(findings=['FREE_SPACE_BELOW_FLOOR'] if above is False else [],path=signed['path'],exists=True,owner_uid=info.st_uid,owner_gid=info.st_gid,
                           mode_octal='%04o'%stat.S_IMODE(info.st_mode),bytes_available=available,floor_bytes=floor,at_or_above_the_floor=above,
                           entries=entries,catalog_names_present=names)
        finally:self.host.close(fd)

    def lock(self):
        directory=self.held.get('LOCK_DIRECTORY');need(directory is not None,'DIRECTORY_NOT_HELD');name=self.plan['deploy']['lock_name']
        try:fd=open_lock(self.host,name,directory,self.gate)
        except Refused as error:
            if str(error)!='LOCK_FILE_ABSENT':raise
            return item_of(findings=['LOCK_FILE_ABSENT'],exists=False)
        try:
            state=probe_lock(self.host,fd);return item_of(exists=True,state=state,still_named=lock_still_named(self.host,name,directory,fd))
        finally:self.host.close(fd)

    def stable(self):
        """Every directory held is still the one its way from "/" shows."""
        result={}
        for key in sorted(self.held):
            try:self.held[key].verify(self.gate);result[key]=True
            except Refused as error:
                if str(error) in EXPIRED_CODES:raise
                result[key]=False
        return item_of(findings=[] if all(result.values()) else ['DIRECTORY_REPLACED_DURING_RUN'],directories=result)

    def close(self):
        for handle in self.held.values():
            try:handle.close()
            except Exception:pass


def _never_complete(receipt):
    """A receipt reduced for size says of itself that it is not the success of its mode (the core has already set its
    status and outcome): neither flag stays true, and it carries a constant code."""
    receipt['expectations_met']=False;receipt['gates_first_session_readback']=False
    if receipt.get('code') is None:receipt['code']='RECEIPT_REDUCED_FOR_SIZE'
def _drop_rows(receipt):
    _never_complete(receipt)
    for item in (receipt.get('items') or {}).values():
        if type(item) is dict and 'observed_rows' in item:item['observed_rows']=len(item['observed_rows'])
def _reduce_items(receipt):
    _never_complete(receipt)
    receipt['items']={name:{key:item.get(key) for key in ('status','matches','findings','code')} for name,item in (receipt.get('items') or {}).items()}
REDUCTIONS=[('OBSERVED_ROWS_REDUCED_TO_COUNTS',_drop_rows),('ITEMS_REDUCED_TO_STATUS',_reduce_items)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    commands=Commands(host,gate);reader=Readback(plan,host,gate,commands,bound,monotonic)                 # pure: nothing is touched
    release,deploy=plan['release'],plan['deploy'];items={};omitted=[];facts_only=set();pre=plan['mode']=='PRE'
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    def observe(label,action,gated=True):
        """One item, observed on its own. An expiry stops the run; any other failure is that item's UNAVAILABLE.
        gated False: the item carries no signed expectation (a fact): when it cannot be observed the receipt says so
        and the outcome is decided by the other items."""
        started=monotonic()
        if not gated:facts_only.add(label)
        try:
            gate();found=action()
        except Exception as error:found=safe(error)
        found['elapsed_ms']=int((monotonic()-started)*1000);items[label]=found
        if found.get('status')=='UNAVAILABLE' and found.get('code') in EXPIRED_CODES:raise Refused(found['code'])
    def optional(present,label,action,gated=True):
        if present:observe(label,action,gated)
        else:omitted.append(label)
    def finish(stop=None):
        findings=sorted({code for item in items.values() for code in item.get('findings') or []})
        incomplete=sorted(label for label,item in items.items() if item.get('status')!='COMPLETE')
        deciding=[label for label in incomplete if label not in facts_only]
        if stop is not None:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,stop
        elif deciding:status,outcome,code=PARTIAL_STATUS,PARTIAL_OUTCOME,findings[0] if findings else 'OBSERVATION_INCOMPLETE'
        elif findings:status,outcome,code=PARTIAL_STATUS,MISMATCH_OUTCOME,findings[0]
        else:status,outcome,code=COMPLETE_STATUS,success_of(plan),None
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),mode=plan['mode'],effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),items=items,
            findings=findings,items_not_complete=incomplete,fact_items_not_observed=[label for label in incomplete if label in facts_only],
            items_omitted_by_the_plan=omitted,dry_run=plan['dry_run'],expectations_met=status==COMPLETE_STATUS,
            gates_first_session_readback=status==COMPLETE_STATUS and plan['mode']=='POST',facts_reported_not_gated=FACTS_NOT_GATED,
            writes=0,containers_run=commands.started['CONTAINER'],phase_reached='OBSERVATION')))
    try:
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')                  # first, before anything is looked at
            observe('boot',reader.boot)
            # the release parent receives install_release's directory (still to come in PRE); the live parent receives activate's
            observe('directory:RELEASE_PARENT',lambda:reader.directory('RELEASE_PARENT',release['parent'],True,pre,plan['worker']['data_source']))
            for key,spec in (('DEPLOY_TREE',deploy['tree']),('LOCK_DIRECTORY',deploy['lock_directory'])):
                observe('directory:'+key,lambda key=key,spec=spec:reader.directory(key,spec))
            optional(plan['live'] is not None,'directory:LIVE_PARENT',lambda:reader.directory('LIVE_PARENT',plan['live']['parent'],True,True))
            optional(plan['bind_probe'] is not None,'directory:BIND_PROBE',lambda:reader.directory('BIND_PROBE',plan['bind_probe']['directory']))
            observe('release_target',reader.release_target)
            optional(plan['live'] is not None,'live_target',reader.live_target)
            optional(plan['docker_config'] is not None,'docker_config',reader.configuration)
            observe('verify',reader.verify)                                         # the container, before every other command
            observe('containers',reader.containers)
            observe('image',reader.image)
            observe('worker',reader.worker)
            optional(plan['worker']['environment'],'worker_environment',reader.worker_environment)
            optional(plan['render'] is not None,'render',reader.render)
            observe('deploy_files',reader.deploy_files)
            observe('maintenance_pin',reader.pin)
            for signed in plan['units']:observe('unit:'+signed['name'],lambda signed=signed:reader.unit(signed),signed['expected'] is not None)
            optional(plan['journal'] is not None,'journal',reader.journal,plan['journal'] is not None and plan['journal']['floor_bytes'] is not None)
            optional(deploy['lock_name'] is not None,'lock',reader.lock)
            observe('reboot_pending',lambda:reader.lstat_of(REBOOT_PENDING,finding_when_present='REBOOT_PENDING_MARKER_PRESENT'))
            observe('reboot_required',lambda:reader.lstat_of(REBOOT_REQUIRED),False)
            optional(plan['docker_config'] is not None,'docker_config_after',reader.configuration_after)
            observe('directories_stable',reader.stable)
        except Refused as error:
            code=code_of(error,'OBSERVATION_FAILED')
            if not items:
                return seal(envelope(REFUSED_STATUS,REFUSED_OUTCOME,code,dict(bound,phase_reached='BEFORE_ANY_OBSERVATION',mode=plan['mode'],
                                                                             mutating_calls=state.counts(),writes=0)))
            return finish(code)
        return finish()
    finally:reader.close()
# ==== END OP_EPOCH_READBACK ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
