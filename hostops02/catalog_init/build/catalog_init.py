"""OP_CATALOG_INIT: supervisor operation 4b, the catalog initialisation of the bar journal root. One source, two
signed modes that run the same bytes: REAL on the journal root that operation 2 created (a leaf of /var/lib/c3po-bar,
never the state root), with the epoch string that this source carries as a constant and the docker CLI under the
unit's empty configuration directory /etc/c3po-bar/docker-cli; REHEARSAL on a throwaway root and under a throwaway
configuration directory that this run creates in /var/lib, with a diagnostic epoch string. A rehearsal only reads the
real journal root and the configuration directory of the unit: none of its docker commands runs under that directory.

It starts ONE attached container of the signed image ID with the argv of the supervisor README, word for word (no
network, the journal root bound read-write at the signed container path as the only mount, the docker CLI under an
empty configuration directory), and gives it the README's pinned script on standard input. The script bytes travel
inside this source and are compared with the pinned hash before anything is looked at. REAL looks at everything
before the container is started: a refusal up to that point has changed nothing and leaves the root usable. A
REHEARSAL refuses with nothing changed up to the creation of its first directory; what a docker read finds after
that is a PARTIAL that has touched nothing of production. After the container was started nothing refuses: what it
left is read back on the host through the descriptor held since before the run (the two names, their owner, mode and
link count, and the bytes of epoch.json against the epoch and the device and inode of the root), and anything but a
verified CATALOG_READY is a PARTIAL whose root is not to be used again. Nothing is removed and nothing that exists
is overwritten, renamed, chmodded or chowned by this process; no unit is touched; no token, manifest, state root or
network reaches the container. The caller authenticates exact request/authority/GO/source bytes first.
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

# ==== BEGIN OP_CATALOG_INIT (this operation only) ====
import base64

OPERATION='GO_WRITE_HOSTOPS02_CATALOG_INIT_01'
PHASE='WRITE_BAR_JOURNAL_CATALOG_INITIALISATION_4B'
REQUEST_SCHEMA='WRITE_HOSTOPS02_CATALOG_INIT_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_CATALOG_INIT_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_CATALOG_INIT_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_CATALOG_INIT_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_CATALOG_INIT_PLAN_V1'
SOURCE_NAME='catalog_init.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_WEEKEND'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The rows a request signs come from the precheck of the boot of the write (the chains from "/") and from the ledger
# of the provisioning that created the journal root and the docker CLI configuration directory.
PROVISION_OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PROVISION_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='CATALOG_READY_VERIFIED'                        # mode REAL
REHEARSAL_COMPLETE_OUTCOME='REHEARSAL_CATALOG_READY_VERIFIED'    # mode REHEARSAL: never the receipt of operation 4b
PARTIAL_OUTCOME='PARTIAL_SEE_ROOT_VERDICT'
REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED_NO_CONTAINER_STARTED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_STATE_UNKNOWN_ROOT_NOT_TO_BE_USED_AGAIN'
PLAN_KEYS=frozenset(('mode','journal_chain','throwaway_name','reference_chain','container_journal_root','docker_config_chain',
                     'image_id','image_revision','epoch','script_sha256','evidence_boot_id_sha256'))
MODES=('REAL','REHEARSAL')
# The epoch string of mode REAL is this constant and nothing a request can change. It is the compiled constant of the
# release: c3po/backend/app/r2d2_v2_epoch_assembler.py line 9 at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858.
EPOCH_COMPILED='R2D2-V2-SHADOW-2026-10-05'
EPOCH_SOURCE='c3po/backend/app/r2d2_v2_epoch_assembler.py:9 EPOCH at dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
REHEARSAL_EPOCH='R2D2-V2-DIAG-[A-Za-z0-9_-]{1,80}'              # the DIAG half of validate_epoch (r2d2_v2_store.py:39)
THROWAWAY_NAME='c3po-bar-rehearsal-[a-z0-9][a-z0-9-]{0,39}'
# The layout floor of the reviewed family (hostops01 parts/layout.py: SUP_CONFIG, SUP_STATE_PARENT, SUP_STATE and the
# chain VAR_LIB), carried here as constants. Which directory is a journal root, which one is the docker CLI
# configuration directory of the unit and where a rehearsal creates are decided by this code, not by signed rows alone.
UNIT_DOCKER_CONFIG='/etc/c3po-bar/docker-cli'
JOURNAL_PARENT='/var/lib/c3po-bar'               # placement A: a journal root is a leaf of the private parent of operation 2
STATE_ROOT='/var/lib/c3po-bar/supervisor'        # and never the state root of the supervisor
THROWAWAY_PARENT='/var/lib'                      # a throwaway is a sibling of the private parent, never inside it
THROWAWAY_CONFIG_SUFFIX='.docker-cli'            # what a rehearsal gives docker as DOCKER_CONFIG: <throwaway root>.docker-cli
# The script of the supervisor README, "Catalog initialisation": exactly the lines between its two markers
# (README.md lines 353 to 373 at dd4ec4bb), 1040 bytes. Carried here so that the bytes are part of the signed source.
CATALOG_SCRIPT_SHA256='715d7a660e7a2c4dd5c11287063726cc971156dd6fefc2365c431c9aee0f4bb7'
CATALOG_SCRIPT_BYTES=1040
CATALOG_SCRIPT_B64=(
    'aW1wb3J0IGpzb24sIG9zLCBzeXMKc3lzLnBhdGguaW5zZXJ0KDAsICcvYXBwJykKdHJ5OgogICAgZnJvbSBhcHAucjJkMl92Ml9tYXNzaXZlX3Nlc3Npb25z'
    'IGltcG9ydCBTZXNzaW9uSm91cm5hbFJvb3QKICAgIGZyb20gYXBwLnIyZDJfdjJfc3RvcmUgaW1wb3J0IHZhbGlkYXRlX2Vwb2NoCiAgICByb290LCBlcG9j'
    'aCA9IHN5cy5hcmd2WzE6XQogICAgdmFsaWRhdGVfZXBvY2goZXBvY2gpCiAgICBiZWZvcmUgPSBzb3J0ZWQob3MubGlzdGRpcihyb290KSkKICAgIGlmIGJl'
    'Zm9yZSBhbmQgJ2Vwb2NoLmpzb24nIG5vdCBpbiBiZWZvcmU6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignQ0FUQUxPR19JTklUX1JPT1RfTk9UX0VNUFRZ'
    'JykKICAgIFNlc3Npb25Kb3VybmFsUm9vdChyb290LCBlcG9jaCwgY3JlYXRlPVRydWUpCiAgICBTZXNzaW9uSm91cm5hbFJvb3Qocm9vdCwgZXBvY2gpCiAg'
    'ICB3aXRoIG9wZW4ob3MucGF0aC5qb2luKHJvb3QsICdlcG9jaC5qc29uJyksICdyYicpIGFzIHN0cmVhbToKICAgICAgICBjYXRhbG9nID0ganNvbi5sb2Fk'
    'cyhzdHJlYW0ucmVhZCgpKQogICAgcmVjZWlwdCA9IHsnc3RhdHVzJzogJ0NBVEFMT0dfUkVBRFknLCAnY3JlYXRlZCc6IG5vdCBiZWZvcmUsICdlcG9jaCc6'
    'IGNhdGFsb2dbJ2Vwb2NoJ10sCiAgICAgICAgICAgICAgICdkZXZpY2UnOiBjYXRhbG9nWydkZXZpY2UnXSwgJ2lub2RlJzogY2F0YWxvZ1snaW5vZGUnXSwg'
    'J2VudHJpZXMnOiBzb3J0ZWQob3MubGlzdGRpcihyb290KSl9CmV4Y2VwdCBFeGNlcHRpb24gYXMgZXJyb3I6CiAgICBjb2RlID0gZXJyb3IuYXJnc1swXSBp'
    'ZiBsZW4oZXJyb3IuYXJncykgPT0gMSBhbmQgdHlwZShlcnJvci5hcmdzWzBdKSBpcyBzdHIgZWxzZSB0eXBlKGVycm9yKS5fX25hbWVfXwogICAgcHJpbnQo'
    'anNvbi5kdW1wcyh7J3N0YXR1cyc6ICdDQVRBTE9HX1JFRlVTRUQnLCAnY29kZSc6IGNvZGV9LCBzb3J0X2tleXM9VHJ1ZSkpCiAgICByYWlzZSBTeXN0ZW1F'
    'eGl0KDEpCnByaW50KGpzb24uZHVtcHMocmVjZWlwdCwgc29ydF9rZXlzPVRydWUpKQo=')
# What the script leaves in an empty root, as the application defines it: maintenance.lock first
# (r2d2_v2_massive_maintenance.py:26), then epoch.json in place (r2d2_v2_massive_sessions.py:58-75, 204-205), both
# 0600, one link, owned by the uid of the container (0). epoch.json is the canonical JSON of the four members below;
# the producer compares its bytes at every start (_immutable, :64) and the reader its content (_verify, :213-215).
CATALOG_FILES=('epoch.json','maintenance.lock')
CATALOG_SCHEMA='MASSIVE_SESSION_ROOT_V1'
CATALOG_FILE_MODE=0o600
MAX_CATALOG_ENTRIES=64
MAX_EPOCH_JSON_BYTES=4096
MAX_NEW_CONTAINER_ROWS=8
# README "Substitution grammar", placement A: the container journal root is exactly one new top-level directory, and
# never one the image or the runtime provides (the list is the README's floor).
CONTAINER_ROOT_FORBIDDEN=('app','bin','boot','dev','etc','home','lib','lib64','media','mnt','opt','proc','root','run','sbin','srv','sys','tmp','usr','var')
FILES_ALLOWANCE_SECONDS=2                 # mode REHEARSAL: the two directories this run creates before the container
# What the docker commands that ran before the container left in the directory they were given. A run that finds this
# cannot say that nothing changed: it is never a refusal.
CONFIG_CHANGED='DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_THE_READS'
CONFIG_UNKNOWN='DOCKER_CONFIG_DIRECTORY_NOT_READ_AFTER_THE_READS'
RUN_ROW='catalog_init'
BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}
COMMANDS={'image':command_row('docker',['image','inspect','--format',IMAGE_FORMAT],'the signed image ID','QUICK','READ'),
          'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),
          RUN_ROW:command_row('docker',RUN_PREFIX,'one read-write bind of the journal root at the signed container path, the signed image ID, '
                              'python -I -B -, the container path, the epoch string; the pinned script on standard input','RUN','EFFECT',stdin=True)}
SCOPE_STATEMENT=('Supervisor operation 4b, the catalog initialisation of the bar journal, as the supervisor README at dd4ec4bb describes it. '
                 'Starts one attached container of the signed image ID with the argv of that README word for word: removed on exit, never a '
                 'pull, an init process, uid 0, no network, read-only root filesystem, no capability, the journal root bound read-write at '
                 'the signed container path as its only mount, the docker CLI under an empty configuration directory, and the '
                 'script whose SHA-256 is 715d7a660e7a2c4dd5c11287063726cc971156dd6fefc2365c431c9aee0f4bb7 on standard input. The container '
                 'creates maintenance.lock and epoch.json in the journal root. Mode REAL acts on the journal root that operation 2 created, '
                 'a leaf of /var/lib/c3po-bar that is not the state root, with the docker CLI under /etc/c3po-bar/docker-cli, and binds '
                 'that root for good to the epoch R2D2-V2-SHADOW-2026-10-05, the compiled constant of the release; this process itself '
                 'creates nothing there. Mode REHEARSAL creates two private throwaway directories in /var/lib, a journal root and a '
                 'configuration directory for the docker CLI, runs the same command on them with a diagnostic epoch string, and only '
                 'reads the real journal root and the configuration directory of the unit: no docker command of a rehearsal runs under '
                 'the directory of the unit. Nothing is removed: the throwaway directories and the two files stay. Once the container '
                 'was started, anything but a verified CATALOG_READY leaves a root that is not to be used again. Nothing that exists is '
                 'overwritten, renamed, chmodded or chowned by this process; no unit is touched; a timeout stops the docker CLI, not '
                 'the container.')
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,
       'binaries':BINARIES,'commands':COMMANDS,'command_classes':COMMAND_CLASSES,'command_environment':COMMAND_ENVIRONMENT,
       'command_variables':COMMAND_VARIABLES,'after_effect_reserve_seconds':AFTER_EFFECT_RESERVE_SECONDS,
       'files_allowance_seconds':FILES_ALLOWANCE_SECONDS,'files':FILES_SCOPE,
       'modes':list(MODES),'success_outcome':{'REAL':COMPLETE_OUTCOME,'REHEARSAL':REHEARSAL_COMPLETE_OUTCOME},
       'epoch':{'REAL':EPOCH_COMPILED,'REAL_source':EPOCH_SOURCE,'REHEARSAL_grammar':REHEARSAL_EPOCH},
       'script':{'sha256':CATALOG_SCRIPT_SHA256,'bytes':CATALOG_SCRIPT_BYTES,'carried_in_this_source':True,
                 'reference':'c3po/deployment/massive-supervisor/README.md at dd4ec4bb, the lines between the two catalog-init-script markers'},
       'catalog':{'names':list(CATALOG_FILES),'type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%CATALOG_FILE_MODE,'links':1,
                  'epoch_json':'canonical JSON of schema %s, the epoch, and the device and inode of the journal root as this process reads them on the host'%CATALOG_SCHEMA},
       'throwaway_name':THROWAWAY_NAME,'container_journal_root_forbidden':list(CONTAINER_ROOT_FORBIDDEN),
       'layout':{'docker_config_of_the_unit':UNIT_DOCKER_CONFIG,'journal_root':'a leaf of '+JOURNAL_PARENT,'never_a_journal_root':STATE_ROOT,
                 'throwaway_parent':THROWAWAY_PARENT,'throwaway_docker_config':'<throwaway root>'+THROWAWAY_CONFIG_SUFFIX},
       'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'file_contents_read':[BOOT_ID_PATH,'epoch.json of the journal root, after the container (compared with the expected bytes; only its size and hash leave)'],
       'side_effects':['one container of the signed image is created and removed by the engine (docker run --rm)',
                       'mode REAL: the journal root gains maintenance.lock and epoch.json and is bound to the epoch for good',
                       'mode REHEARSAL: two directories stay in '+THROWAWAY_PARENT+', the throwaway root with its two files and the empty configuration directory docker was given',
                       'a container whose docker CLI was stopped by the time limit is left to the engine; the receipt says whether one is listed that was not there before'],
       'never':['overwrite','chmod','chown','rename','any removal','a second run on a root','docker exec','a shell','systemctl','a pull','a network for the container',
                'any other mount','the token, a manifest, the state root or the configuration directory in the container','--name or any option the README does not write',
                'a docker command of a rehearsal under the configuration directory of the unit'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'receipt_bytes':RECEIPT_LIMIT,
                 'catalog_entries':MAX_CATALOG_ENTRIES,'epoch_json_bytes':MAX_EPOCH_JSON_BYTES,'new_container_rows':MAX_NEW_CONTAINER_ROWS}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeRunner,NativeFiles):
    """Everything this source can do to the host: the read primitives, the three signed commands, and the creating
    calls of the files part, of which this operation uses mkdir and fsync only (the throwaway directory of REHEARSAL)."""


def script_bytes():
    """The pinned script, from the constant this source carries. Nothing else is ever given to the container."""
    try:raw=base64.b64decode(CATALOG_SCRIPT_B64.encode('ascii'),validate=True)
    except (ValueError,UnicodeEncodeError):raise Refused('SCRIPT_NOT_THE_PINNED_HASH') from None
    need(len(raw)==CATALOG_SCRIPT_BYTES and sha(raw)==CATALOG_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');return raw

def signed_rows(rows,receives_entry=False):
    """Signed rows of an existing directory that is not "/": every component root-owned and closed to group and other."""
    need(type(rows) is list and len(rows)>=2 and type(rows[-1]) is dict and type(rows[-1].get('path')) is str,'CHAIN_ROW_INVALID')
    return validate_chain(rows,rows[-1]['path'],None,receives_entry)

def private_rows(rows,label):
    """Signed rows of an existing private directory: root:root, mode 0700 exactly, on the device of its parent (the
    journal root is never a mount point on the host, README "Journal placement")."""
    rows=signed_rows(rows);last=rows[-1]
    need(last['gid']==0 and last['mode']==PRIVATE_DIRECTORY_MODE,label+'_NOT_PRIVATE')          # root-owned like every row: signed_rows
    need(last['device']==rows[-2]['device'],label+'_IS_A_MOUNT_POINT')
    return rows

def journal_rows(rows,label):
    """Signed rows of a journal root: a private directory that is a leaf of the private parent operation 2 created,
    and not the state root of the supervisor. No other directory is a journal root, whatever a request signs."""
    rows=private_rows(rows,label)
    need(rows[-2]['path']==JOURNAL_PARENT,label+'_NOT_A_LEAF_OF_THE_PRIVATE_PARENT')
    need(rows[-1]['path']!=STATE_ROOT,label+'_IS_THE_STATE_ROOT')
    return rows

def journal_path(plan):
    """The host path the container gets: the signed journal root (REAL), or the throwaway this run creates (REHEARSAL)."""
    last=plan['journal_chain'][-1]['path']
    return last if plan['mode']=='REAL' else last.rstrip('/')+'/'+plan['throwaway_name']
def docker_config_path(plan):
    """The directory every docker command of the run gets as DOCKER_CONFIG: the unit's own (REAL), or a throwaway this
    run creates beside the throwaway root (REHEARSAL), so that a rehearsal starts no docker command under the unit's."""
    return plan['docker_config_chain'][-1]['path'] if plan['mode']=='REAL' else journal_path(plan)+THROWAWAY_CONFIG_SUFFIX
def run_mounts(plan):return [{'source':journal_path(plan),'target':plan['container_journal_root'],'read_only':False}]
def run_words(plan):return ['python','-I','-B','-',plan['container_journal_root'],plan['epoch']]

def validate_plan(plan):
    mode=plan['mode'];need(type(mode) is str and mode in MODES,'MODE_INVALID')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    need(type(plan['script_sha256']) is str and plan['script_sha256']==CATALOG_SCRIPT_SHA256,'SCRIPT_NOT_THE_PINNED_HASH');script_bytes()
    need(text(plan['image_revision'],'[0-9a-f]{40}'),'IMAGE_REVISION_UNBOUND')
    target=plan['container_journal_root']
    need(text(target,'/[A-Za-z0-9][A-Za-z0-9._-]{0,63}') and target[1:] not in CONTAINER_ROOT_FORBIDDEN,'CONTAINER_JOURNAL_ROOT_INVALID')
    config=private_rows(plan['docker_config_chain'],'DOCKER_CONFIG')
    need(config[-1]['path']==UNIT_DOCKER_CONFIG,'DOCKER_CONFIG_NOT_THE_DIRECTORY_OF_THE_UNIT')
    if mode=='REAL':
        need(plan['throwaway_name'] is None and plan['reference_chain'] is None,'MODE_MEMBERS_INVALID')
        journal_rows(plan['journal_chain'],'JOURNAL_ROOT')
        need(type(plan['epoch']) is str and plan['epoch']==EPOCH_COMPILED,'EPOCH_NOT_THE_COMPILED_CONSTANT')
    else:
        parent=signed_rows(plan['journal_chain'],True)
        need(parent[-1]['path']==THROWAWAY_PARENT,'THROWAWAY_PARENT_NOT_THE_FIXED_ONE')
        need(text(plan['throwaway_name'],THROWAWAY_NAME),'THROWAWAY_NAME_INVALID')
        reference=journal_rows(plan['reference_chain'],'REFERENCE_ROOT')
        need(reference[-1]['device']==parent[-1]['device'],'REHEARSAL_NOT_ON_THE_FILESYSTEM_OF_THE_REAL_ROOT')
        need(text(plan['epoch'],REHEARSAL_EPOCH),'EPOCH_NOT_A_DIAGNOSTIC_ONE')
    run_arguments(RUN_ROW,plan['image_id'],run_mounts(plan),run_words(plan))

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    rehearsal=plan['mode']=='REHEARSAL';path=journal_path(plan);use_path=docker_config_path(plan)
    return {'operation':OPERATION,'mode':plan['mode'],
            'journal_root':{'path':path,'is_the_real_journal_root':not rehearsal,
                            'expect':'ABSENT_THEN_CREATED_0700_BY_THIS_RUN' if rehearsal else 'PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',
                            'signed_chain':chain_effects(plan['journal_chain']),'signed_chain_is_of':'THE_PARENT' if rehearsal else 'THE_ROOT_ITSELF',
                            'stays_after_the_run':True},
            'real_journal_root_read_only':None if not rehearsal else dict(chain_effects(plan['reference_chain']),expect='PRESENT_EMPTY_ROOT_ROOT_0700_AS_SIGNED',
                                                                           same_device_as_the_parent_of_the_throwaway=True),
            'docker_config':dict(chain_effects(plan['docker_config_chain']),given_to_docker=not rehearsal,
                                 expect='PRESENT_EMPTY_ONLY_READ_NEVER_GIVEN_TO_DOCKER' if rehearsal else 'PRESENT_EMPTY_BEFORE_AND_AFTER'),
            'rehearsal_docker_config':None if not rehearsal else {'path':use_path,'expect':'ABSENT_THEN_CREATED_0700_BY_THIS_RUN_EMPTY_AFTER_IT',
                                                                   'given_to_docker':True,'stays_after_the_run':True},
            'container':{'image_id':plan['image_id'],'image_revision':plan['image_revision'],'docker_config_variable':use_path,
                         'docker_arguments':RUN_PREFIX+run_arguments(RUN_ROW,plan['image_id'],run_mounts(plan),run_words(plan)),
                         'bind':run_mounts(plan)[0],'network':'none','standard_input':{'sha256':CATALOG_SCRIPT_SHA256,'bytes':CATALOG_SCRIPT_BYTES},
                         'time_limit_seconds':COMMAND_CLASSES[COMMANDS[RUN_ROW]['class']]['seconds']},
            'epoch':plan['epoch'],'epoch_source':'SIGNED_DIAGNOSTIC_STRING' if rehearsal else EPOCH_SOURCE,
            'creates':{'by_this_process':[use_path,path] if rehearsal else [],'by_the_container':[path+'/'+name for name in CATALOG_FILES],
                       'file_mode_octal':'%04o'%CATALOG_FILE_MODE},
            'success_outcome':success_of(plan),'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'pre_existing_objects_modified':not rehearsal,'removes':[],'activation':False}
def success_of(plan):return COMPLETE_OUTCOME if plan['mode']=='REAL' else REHEARSAL_COMPLETE_OUTCOME


def script_line(result,epoch):
    """What the container printed, reduced to what is compared. as_signed is true for exactly the line of a creating
    run: the six keys, CATALOG_READY, created true, the signed epoch, the two names in order, an integer identity. Of
    a refusal only a constant code is kept: the script prints the text of whatever exception it caught (README,
    "Known wart"), and raw text never leaves this process."""
    output=result['output'] if type(result.get('output')) is bytes else b''
    line={'returncode':result['returncode'],'bytes':len(output),'sha256':sha(output) if output else None,'one_json_line':False,'status':None,
          'refusal_code':None,'as_signed':False,'keys_exact':None,'created':None,'epoch_equal':None,'entries_as_expected':None,'device':None,'inode':None}
    try:row=single_line(output)
    except Refused:return line
    line['one_json_line']=True;status=row.get('status')
    line['status']=status if type(status) is str and status in ('CATALOG_READY','CATALOG_REFUSED') else 'OTHER'
    if line['status']=='CATALOG_REFUSED':
        line['refusal_code']=row['code'] if text(row.get('code'),CODE) else 'NOT_A_CONSTANT_CODE'
    if line['status']=='CATALOG_READY':
        line['keys_exact']=set(row)=={'status','created','epoch','device','inode','entries'}
        if line['keys_exact']:
            line.update(created=row['created'] is True,epoch_equal=row['epoch']==epoch,entries_as_expected=row['entries']==list(CATALOG_FILES),
                        device=row['device'] if integer(row['device']) else None,inode=row['inode'] if integer(row['inode'],1) else None)
            line['as_signed']=(line['created'] and line['epoch_equal'] and line['entries_as_expected'] and line['device'] is not None
                               and line['inode'] is not None)
    return line

def catalog_readback(host,gate,root,epoch):
    """What the run left in the journal root, read on the host through the descriptor held since before the container:
    how many entries, the two catalog names with type, owner, mode, links and size (other names are counted, never
    printed), and epoch.json compared byte for byte with what the application writes for this epoch and for the
    device and inode of this directory. maintenance.lock is never opened. Never raises: what was read stays in the row."""
    out={'status':'UNAVAILABLE','code':None,'entries':None,'other_entries':None,'files':{},'epoch_json':None,'root_unchanged':None}
    try:
        gate();names=[];listed={}
        for name in host.names(root.fd):
            names.append(name);need(len(names)<=MAX_CATALOG_ENTRIES,'ENTRY_LIMIT')
        out['entries']=len(names);out['other_entries']=len([name for name in names if name not in CATALOG_FILES])
        for name in CATALOG_FILES:
            if name not in names:
                out['files'][name]={'exists':False};continue
            gate();info=host.lstat(name,root.fd);listed[name]=(info.st_dev,info.st_ino)
            out['files'][name]={'exists':True,'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),
                                'links':info.st_nlink,'bytes':info.st_size,'on_the_device_of_the_root':info.st_dev==root.identity[0]}
        if out['files'][CATALOG_FILES[0]].get('type')=='file':
            expected=canonical({'schema':CATALOG_SCHEMA,'epoch':epoch,'device':root.identity[0],'inode':root.identity[1]})
            raw,held=read_regular(host,CATALOG_FILES[0],root.fd,gate,MAX_EPOCH_JSON_BYTES)
            need((held.st_dev,held.st_ino)==listed[CATALOG_FILES[0]],'FILE_CHANGED_DURING_READ')          # the file read is the one whose metadata was taken
            out['epoch_json']={'bytes':len(raw),'sha256':sha(raw),'expected_sha256':sha(expected),'equal_to_the_expected_bytes':raw==expected}
        try:root.verify(gate);out['root_unchanged']=True
        except Refused as error:
            if str(error)=='PARENT_REPLACED':out['root_unchanged']=False
            raise
        out['status']='COMPLETE'
    except Exception as error:
        out['code']=code_of(error,'READBACK_OS_ERROR' if isinstance(error,OSError) else 'READBACK_FAILED')
    return out

def file_as_expected(row):
    return row.get('exists') is True and (row['type'],row['uid'],row['gid'],row['mode_octal'],row['links'],row['on_the_device_of_the_root'])==(
        'file',0,0,'%04o'%CATALOG_FILE_MODE,1,True)
def catalog_as_expected(catalog):
    """A complete readback shows exactly the two files of the application, and epoch.json holds the expected bytes."""
    return (catalog['entries']==len(CATALOG_FILES) and all(file_as_expected(catalog['files'][name]) for name in CATALOG_FILES)
            and catalog['epoch_json']['equal_to_the_expected_bytes'] is True)

def run_failure(result,line,catalog,identity):
    """None when the container that returned is the verified creation of the catalog; otherwise the first thing that
    is not as it must be, in the order in which the run produces it. One of docker's own statuses (125, 126, 127)
    does not by itself spend the root: `--rm` can turn a clean exit into 125 when the wait for the removal fails
    (README, "Exit statuses"). With such a status the line and the host readback decide: when both are those of a
    verified creation this returns None and the caller reports the status as a finding beside a verified catalog."""
    engine=result['returncode'] in RUN_ENGINE_STATUSES
    failure=catalog_failure(result['returncode'] if not engine else 0,line,catalog,identity)
    return 'ENGINE_COULD_NOT_RUN_THE_CONTAINER' if engine and failure is not None else failure
def catalog_failure(returncode,line,catalog,identity):
    if not line['one_json_line']:return 'SCRIPT_OUTPUT_NOT_ONE_LINE'
    if line['status']=='CATALOG_REFUSED':return 'SCRIPT_REFUSED'
    if returncode!=0:return 'SCRIPT_FAILED'
    if not line['as_signed']:return 'SCRIPT_LINE_NOT_AS_SIGNED'
    if (line['device'],line['inode'])!=tuple(identity):return 'CATALOG_IDENTITY_NOT_THE_HOSTS'
    if catalog['status']!='COMPLETE':return 'CATALOG_READBACK_UNAVAILABLE'
    if not catalog_as_expected(catalog):return 'CATALOG_READBACK_MISMATCH'
    return None

def _reduce_observed(receipt):receipt['observed_rows']={'reduced_for_size':True}
def _reduce_containers(receipt):
    if type(receipt.get('containers')) is dict:receipt['containers']['rows']=[]
REDUCTIONS=[('OBSERVED_ROWS_DROPPED',_reduce_observed),('NEW_CONTAINER_ROWS_DROPPED',_reduce_containers)]

def pin_chain(host,rows,gate,observed):
    """Walks a signed chain and holds its last directory. A descriptor that does not become a held directory is closed."""
    fd=walk_pinned(host,rows,gate,observed)
    try:return Pinned(host,fd,rows=rows)
    except BaseException:
        try:host.close(fd)
        except Exception:pass
        raise

def directory_stop(entry):
    """None for a directory this run created and proved; otherwise the code its ledger row carries."""
    return None if entry['state']=='CREATED_DURABLE' else (entry['code'] or 'CREATION_FAILED')

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    script=script_bytes();rehearsal=plan['mode']=='REHEARSAL'                                    # pure
    path=journal_path(plan);use_path=docker_config_path(plan);mounts=run_mounts(plan);words=run_words(plan)
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    commands=Commands(host,gate);observed={'docker_config':[],'journal':[],'reference':[]};precheck={}
    directories=[];handles={};pinned=[]
    facts={'run':None,'script_line':None,'catalog':None,'containers':None,'docker_config':None,'root':None,'verdict':'UNTOUCHED_NO_CONTAINER_STARTED'}
    def finish(status,outcome,code,extra):
        catalog=facts['catalog'];left=objects_left(directories,[])
        if catalog is not None:left=None if catalog['entries'] is None else left+catalog['entries']
        # What the docker commands of the run left in the directory they were given counts as left by this run; in mode
        # REAL that directory is the unit's, an object that existed before. A count that could not be taken is unknown.
        given=precheck.get('docker_config_entries_after_the_reads',0) if facts['docker_config'] is None else facts['docker_config']['entries_after']
        if left is not None:left=None if given is None else left+given
        touched=[False] if rehearsal else [None if given is None else given>0,False if catalog is None else (None if catalog['entries'] is None else catalog['entries']>0)]
        receipt=envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),mode=plan['mode'],effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),commands_started=dict(commands.started),mutating_calls=state.counts(),
            observed_rows=observed,precheck=precheck,directories=directories,journal_root=facts['root'],run=facts['run'],script_line=facts['script_line'],
            catalog=catalog,containers=facts['containers'],docker_config=facts['docker_config'],root_verdict=facts['verdict'],
            objects_left_by_this_run=left,
            pre_existing_objects_modified=True if True in touched else (None if None in touched else False),**extra))
        return seal(receipt)
    def reads(use,root):
        """The two docker reads, under the directory docker is given in this mode, and then the last look: every
        directory held is still what was walked or created and the root (REAL) is still empty. Whatever the reads end
        in, once one of them was started the directory docker was given is counted again before anything is concluded:
        the count goes into the precheck, and a directory that is not empty is a finding of its own. Returns the
        containers listed."""
        failure=None
        try:
            try:image=image_facts(commands,plan['image_id'],docker_config=use_path)
            except CommandFailed:raise Refused('IMAGE_ABSENT_OR_UNREADABLE') from None
            need(image['id']==plan['image_id'],'IMAGE_ID_MISMATCH')
            need(image['revision_label']==plan['image_revision'],'IMAGE_REVISION_MISMATCH')
            precheck['image']={'id_as_signed':True,'revision_as_signed':True}
            try:listed=container_list(commands,docker_config=use_path)
            except CommandFailed:raise Refused('CONTAINER_LISTING_FAILED') from None
            precheck['containers']=len(listed)
            for handle in pinned+list(handles.values()):handle.verify(gate)
            if root is not None:need(count_entries(host,root.fd,gate,MAX_DIRECTORY_ENTRIES)==0,'JOURNAL_ROOT_NOT_EMPTY')
        except Exception as error:failure=error
        if commands.started['READ']:
            counted=attempt(lambda:count_entries(host,use.fd,gate,MAX_DIRECTORY_ENTRIES))
            precheck['docker_config_entries_after_the_reads']=counted if type(counted) is int else None
        if failure is not None:raise failure
        need(precheck.get('docker_config_entries_after_the_reads') is not None,CONFIG_UNKNOWN)
        need(precheck['docker_config_entries_after_the_reads']==0,CONFIG_CHANGED)
        return listed
    def after_reads(code):
        """The code of a failed read or of a failed last look, unless the directory docker was given is not known to be
        empty after the reads: then that is the finding, and the first one is kept beside it in the precheck."""
        given=precheck.get('docker_config_entries_after_the_reads',0)
        if given==0 or code in (CONFIG_CHANGED,CONFIG_UNKNOWN):return code
        precheck['first_finding']=code;return CONFIG_UNKNOWN if given is None else CONFIG_CHANGED
    try:
        # ---- everything the file system shows is looked at before anything is created or started
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o077)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            config=pin_chain(host,plan['docker_config_chain'],gate,observed['docker_config']);pinned.append(config)
            precheck['docker_config_entries']=count_entries(host,config.fd,gate,MAX_DIRECTORY_ENTRIES)
            need(precheck['docker_config_entries']==0,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY')
            if rehearsal:
                reference=pin_chain(host,plan['reference_chain'],gate,observed['reference']);pinned.append(reference)
                precheck['real_journal_root_entries']=count_entries(host,reference.fd,gate,MAX_DIRECTORY_ENTRIES)
                need(precheck['real_journal_root_entries']==0,'REFERENCE_ROOT_NOT_EMPTY')
                parent=pin_chain(host,plan['journal_chain'],gate,observed['journal']);pinned.append(parent)
                for label,target in (('throwaway',path),('throwaway_docker_config',use_path)):
                    found=probe(host,target,gate);precheck[label]={'exists':found.get('exists')}
                    need(found.get('status')=='COMPLETE' and found['exists'] is False,'DESTINATION_PRESENT')
                binary(host,BINARIES['docker'],gate)                      # no directory is created for a docker that cannot be started
            else:
                root=pin_chain(host,plan['journal_chain'],gate,observed['journal']);pinned.append(root)
                precheck['journal_root_entries']=count_entries(host,root.fd,gate,MAX_DIRECTORY_ENTRIES)
                need(precheck['journal_root_entries']==0,'JOURNAL_ROOT_NOT_EMPTY')
                # REAL: the reads run under the directory of the unit and are part of the precheck.
                before=reads(config,root)
            # The last refusal that costs nothing: the whole class of the run and its reserve fit in what is left.
            need(gate()>=effects_budget(RUN_ROW)+(FILES_ALLOWANCE_SECONDS if rehearsal else 0),'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
            code=None
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:
            # A refusal says that nothing changed. When a docker read of the precheck ran (REAL: under the directory of
            # the unit) and that directory is not known to be empty afterwards, that cannot be said: the root is
            # untouched and usable, and the run is a partial whose code names the directory.
            code=after_reads(code)
            if code in (CONFIG_CHANGED,CONFIG_UNKNOWN):return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,code,{'phase_reached':'PRECHECK'})
            return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK'})
        # ---- from here on nothing refuses unless nothing has changed and no container was started
        stop=None
        if rehearsal:
            # A rehearsal never gives docker the directory of the unit. It creates a configuration directory of its
            # own, makes the two reads under it, and only then creates the throwaway root. What fails after the first
            # directory exists is a PARTIAL: the throwaway name is spent, production is as it was.
            entry=create_directory('DOCKER_CONFIG',use_path,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)
            stop=directory_stop(entry)
            if stop is None:
                try:before=reads(handles['DOCKER_CONFIG'],None)
                except Exception as error:stop=after_reads(code_of(error,'READS_OS_ERROR' if isinstance(error,OSError) else 'READS_FAILED'))
            if stop is None:
                entry=create_directory('JOURNAL_ROOT',path,PRIVATE_DIRECTORY_MODE,parent,host,gate,state,handles);directories.append(entry)
                stop=directory_stop(entry)
            if stop is None:root=handles['JOURNAL_ROOT']
            elif not state.clean():facts['verdict']='NOT_TO_BE_USED_AGAIN'
        if stop is None:
            use=handles['DOCKER_CONFIG'] if rehearsal else config
            facts['root']={'path':path,'device':root.identity[0],'inode':root.identity[1],'created_by_this_run':rehearsal}
            run={'state':'NOT_STARTED','code':None,'returncode':None,'seconds':None};facts['run']=run
            started=attempt(monotonic)
            result=container_effect(state,commands,RUN_ROW,plan['image_id'],mounts,words,script,docker_config=use_path)
            ended=attempt(monotonic)
            run.update(code=result['code'],returncode=result['returncode'],
                       seconds=round(ended-started,3) if type(started) in (int,float) and type(ended) in (int,float) else None)
            if not result['started']:
                stop=result['code'] or 'COMMAND_NOT_STARTED'
                if rehearsal:facts['verdict']='NOT_TO_BE_USED_AGAIN'
            else:
                # The container was started. What it left is read on the host, whatever the docker CLI said; only then is the call settled.
                run['state']='RETURNED' if result['returned'] else 'DID_NOT_RETURN'
                line=script_line(result,plan['epoch']);facts['script_line']=line
                catalog=catalog_readback(host,gate,root,plan['epoch']);facts['catalog']=catalog
                listing=attempt(lambda:container_list(commands,docker_config=use_path))
                if type(listing) is list:
                    known=set(row['id'] for row in before);new=[row for row in listing if row['id'] not in known]
                    containers={'status':'COMPLETE','before':len(before),'after':len(listing),'not_there_before':len(new),'rows':new[:MAX_NEW_CONTAINER_ROWS]}
                else:containers=dict(listing,before=len(before),after=None,not_there_before=None,rows=[])
                facts['containers']=containers
                def config_entries():
                    use.verify(gate);return count_entries(host,use.fd,gate,MAX_DIRECTORY_ENTRIES)
                entries=attempt(config_entries)
                facts['docker_config']={'path':use_path,'is_the_directory_of_the_unit':not rehearsal,'entries_before':0,
                                        'entries_after':entries if type(entries) is int else None,'code':None if type(entries) is int else entries.get('code')}
                failure=run_failure(result,line,catalog,root.identity[:2]) if result['returned'] else (result['code'] or 'COMMAND_FAILED')
                if result['returned']:
                    if failure is None:state.done()
                    else:state.unknown()
                if failure is not None:stop=failure;facts['verdict']='NOT_TO_BE_USED_AGAIN'
                else:
                    if result['returncode']!=0:stop='ENGINE_STATUS_AFTER_A_VERIFIED_CATALOG'
                    elif containers['status']!='COMPLETE':stop='CONTAINER_LISTING_UNAVAILABLE_AFTER_RUN'
                    elif containers['not_there_before']:stop='CONTAINER_PRESENT_THAT_WAS_NOT_THERE_BEFORE'
                    elif facts['docker_config']['entries_after'] is None:stop='DOCKER_CONFIG_READBACK_UNAVAILABLE'
                    elif facts['docker_config']['entries_after']:stop='DOCKER_CONFIG_DIRECTORY_NOT_EMPTY_AFTER_RUN'
                    facts['verdict']='CATALOG_READY_VERIFIED' if stop is None else 'CATALOG_VERIFIED_WITH_FINDINGS'
        extra={'phase_reached':'EFFECTS'}
        if stop is None:return finish(COMPLETE_STATUS,success_of(plan),None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain: no directory was created and no process of the run existed.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in list(handles.values())+pinned:
            try:handle.close()
            except Exception:pass
# ==== END OP_CATALOG_INIT ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
