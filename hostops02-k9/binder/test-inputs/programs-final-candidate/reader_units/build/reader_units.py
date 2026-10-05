"""OP_READER_UNITS: the three systemd units of the V2 shadow reader of epoch R2D2-V2-SHADOW-2026-10-05, installed once.

c3po-reader.service (the reader README's template with the values of this source and the source-root bind of Codex
decision 6), c3po-reader.timer and c3po-reader-alert.service (verbatim) are created in /etc/systemd/system, root:root
0644, by exclusive creation only: a dot-prefixed temporary that systemd does not load, unbuffered writes, fsync,
exact metadata, a link to the final name (a link never replaces anything), fsync of the directory, removal of the
temporary once its identity is proved. The bytes are read back through a descriptor inside the run. Everything is
looked at before the first creation: the executor, the boot of the evidence, the signed rows of the unit directory,
the installed producer unit (its bytes, its journal bind and its image), the signed rows of the journal root (and
its two catalogue files, by lstat) and of the data volume, what exists at each name, the drop-ins, dependency directories and leftovers of the lookup
directories, and the time left. This source starts no process: no systemctl verb, no daemon-reload, no enablement,
no start. It reads no secret and never changes, renames or removes an object that exists. Units signed as present
are verified and never touched. The caller authenticates exact request/authority/GO/source bytes first.
No action on import.
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

# ==== BEGIN OP_READER_UNITS (this operation only) ====
OPERATION='GO_WRITE_HOSTOPS02_READER_UNITS_01'
PHASE='WRITE_READER_UNITS_NO_ACTIVATION'
REQUEST_SCHEMA='WRITE_HOSTOPS02_READER_UNITS_REQUEST_V1'
AUTHORITY_SCHEMA='WRITE_HOSTOPS02_READER_UNITS_AUTHORITY_V1'
GO_SCHEMA='WRITE_HOSTOPS02_READER_UNITS_GO_V1'
RECEIPT_SCHEMA='WRITE_HOSTOPS02_READER_UNITS_RECEIPT_V1'
PLAN_SCHEMA='HOSTOPS02_READER_UNITS_PLAN_V1'
SOURCE_NAME='reader_units.py'
WRITES_ALLOWED=True
ACTIVATION_ALLOWED=False
DATE_CLASS='WRITE_SESSIONS'
DATES=DATE_SETS[DATE_CLASS]
EVIDENCE_REQUIRED=True
# The read-only precheck of the boot (it scanned the three reader names, alias links included, which this source
# cannot: section "Conflict scan" below), the install receipt of the producer unit and its readback.
PRODUCER_INSTALL_OPERATION='GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01'
PRODUCER_READBACK_OPERATION='GO_READONLY_SUPERVISOR_READBACK_01'
# Codex, #429 5985937724 E1-19: B2 only after E3 and the real catalogue. The catalogue initialisation (A9) is cited,
# and its two files are looked at in the journal root before anything is created.
CATALOG_INIT_OPERATION='GO_WRITE_HOSTOPS02_CATALOG_INIT_01'
EVIDENCE_OPERATIONS=(PRECHECK_OPERATION,PRODUCER_INSTALL_OPERATION,PRODUCER_READBACK_OPERATION,CATALOG_INIT_OPERATION)
MAX_GATE_SPAN_SECONDS=900
COMPLETE_OUTCOME='UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED'
PARTIAL_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
REFUSED_OUTCOME='REFUSED_NOTHING_CREATED'
REDUCED_OUTCOME='RECEIPT_REDUCED_STATE_REQUIRES_READBACK'
ESCAPED_OUTCOME='PARTIAL_REQUIRES_RECONCILIATION'
PLAN_KEYS=frozenset(('unit_rows','journal_rows','data_rows','units','acknowledged_leftovers','evidence_boot_id_sha256'))
UNIT_KEYS=frozenset(('key','destination_name','expect','rendered_sha256','rendered_bytes'))
EXPECT_KEYS=frozenset(('device','inode','links'))
LEFTOVER_KEYS=frozenset(('name','device','inode'))

# ---- PLACEMENT of epoch R2D2-V2-SHADOW-2026-10-05. A request cannot move any of these: they are bytes of the signed
# ---- source. Where each value comes from is in DESIGN.md, section 3 (every one copied by command from a receipt, a
# ---- decision or the reader README; none typed from memory).
READER_EPOCH='R2D2-V2-SHADOW-2026-10-05'
UNIT_DIRECTORY='/etc/systemd/system'
UNIT_MODE=0o644
READER_SERVICE_NAME='c3po-reader.service'
READER_TIMER_NAME='c3po-reader.timer'
READER_ALERT_NAME='c3po-reader-alert.service'
UNIT_ORDER=(('READER_SERVICE',READER_SERVICE_NAME),('READER_TIMER',READER_TIMER_NAME),('READER_ALERT',READER_ALERT_NAME))
READER_VALUES={'IMAGE_ID':'sha256:f86bfb198c186657598c2c410fb39ca3dfed781d0db0522b9a796b80275cb621',
               'HOST_DATA_ROOT':'/mnt/day-d-data',
               'HOST_JOURNAL_ROOT':'/var/lib/c3po-bar/journal',
               'CONTAINER_JOURNAL_ROOT':'/c3po-bar-journal',
               'HOST_CAPACITY_ROOT':'/var/lib/c3po-capacity',
               'HOST_SOURCE_ROOT':'/var/lib/c3po/r2d2-v2-source-20261005',
               'CONTAINER_SOURCE_ROOT':'/c3po-source',
               'HOST_CONFIG_DIR':'/etc/c3po-reader',
               'NETWORK':'c3po_c3po_internal'}
# The installed producer unit (e3-20261004-a, KNOWN_COMPLETE; read back by l6-20261004-a): its bytes are the signed
# render of the supervisor template, and the reader's journal bind and image are taken from them.
PRODUCER_SERVICE_NAME='c3po-massive.service'
PRODUCER_SHA256='662c57b939d1a21e67e332434d3fa40368e2d503f3772f1cf3f7bd3631bdbc06'
PRODUCER_BYTES=1674
# Who reloads the manager: nobody here. The reader switch (K13, mode ACTIVATE, plan row M6) runs systemctl enable
# --now, which reloads the manager unless --no-reload (Codex decision 3 of 2026-10-04).
DAEMON_RELOAD_OWNER='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'
# The real catalogue in the journal root (catalog_init, A9 CATALOG_READY_VERIFIED): lstat only, never opened.
CATALOG_FILE_NAMES=('epoch.json','maintenance.lock')
CATALOG_FILE_MODE=0o600
# ---- end of the placement

# ---- TEMPLATES. The reader README directory of the installation candidate (opsart branch
# ---- ops/r2d2-v2-epoch03-artifacts-20261002, commit below; not in the release revision dd4ec4bb). The timer and the
# ---- alert unit are verbatim. The service is the README's c3po-reader.service (D1 default: the launcher) with exactly
# ---- two insertions for Codex decision 6 (#429 5985748037, 5985768668): the epoch's source root, outside the data
# ---- volume under a chain controlled by root alone, as a fifth read-only bind and in RequiresMountsFor.
TEMPLATE_REVISION='4a6f7675b8e418e0e7ee55a446250815f3bd5562'
README_SERVICE_SHA256='8d2ff7a91b94e39b8c7a0e91fae34b16dbc9d55f7af407b8464486a9bd064fab'
READER_SERVICE_TEMPLATE=r"""[Unit]
Description=Day-bounded R2D2 V2 shadow reader
Wants=network-online.target
Requires=docker.service
After=network-online.target docker.service
RequiresMountsFor=@HOST_DATA_ROOT@ @HOST_JOURNAL_ROOT@ @HOST_CAPACITY_ROOT@ @HOST_SOURCE_ROOT@ @HOST_CONFIG_DIR@
StartLimitIntervalSec=8h
StartLimitBurst=40
OnFailure=c3po-reader-alert.service

[Service]
Type=exec
Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/secret.env
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/pins.env
ExecCondition=/usr/bin/test -f @HOST_CONFIG_DIR@/activation.env
ExecStartPre=-/usr/bin/docker rm c3po-reader
ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} @IMAGE_ID@
ExecStart=/usr/bin/docker run --rm --init --restart no --name c3po-reader --pull never \
  --user 0:0 --workdir /app --network @NETWORK@ \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 512 --stop-timeout 25 \
  --env-file @HOST_CONFIG_DIR@/secret.env \
  --env-file @HOST_CONFIG_DIR@/pins.env \
  --env-file @HOST_CONFIG_DIR@/activation.env \
  --mount type=bind,source=@HOST_DATA_ROOT@,target=/app/day-d-data,readonly \
  --mount type=bind,source=@HOST_JOURNAL_ROOT@,target=@CONTAINER_JOURNAL_ROOT@,readonly \
  --mount type=bind,source=@HOST_CAPACITY_ROOT@,target=/c3po-capacity,readonly \
  --mount type=bind,source=@HOST_SOURCE_ROOT@,target=@CONTAINER_SOURCE_ROOT@,readonly \
  --mount type=bind,source=@HOST_CONFIG_DIR@/launcher,target=/c3po-reader,readonly \
  @IMAGE_ID@ \
  python -I -B /c3po-reader/reader_launcher.py
ExecStop=-/usr/bin/docker stop -t 25 c3po-reader
ExecStopPost=-/usr/bin/docker stop -t 25 c3po-reader
Restart=on-failure
RestartSec=5s
RestartPreventExitStatus=78
TimeoutStartSec=60s
TimeoutStopSec=30s
KillMode=control-group
UMask=0077
NoNewPrivileges=true
StandardOutput=journal
StandardError=journal
SyslogIdentifier=c3po-reader
""".encode('ascii')
READER_SERVICE_TEMPLATE_SHA256='3dc976807a0ff443307fa12e357d478980441b26d19761b0d7964b5580327770'
READER_TIMER_TEMPLATE=r"""[Unit]
Description=Start the approved V2 shadow reader on session days

[Timer]
OnBootSec=90s
OnCalendar=Mon..Fri *-*-* 04:00:00 America/New_York
OnCalendar=Mon..Fri *-*-* 09:29:20 America/New_York
Persistent=false
AccuracySec=1s
Unit=c3po-reader.service

[Install]
WantedBy=timers.target
""".encode('ascii')
READER_TIMER_TEMPLATE_SHA256='dc81e21bfc2398330dd7eff02cbc8cf8d0e035bce883653cab4b10a1078ed4ba'
READER_ALERT_TEMPLATE=r"""[Unit]
Description=Record that the V2 shadow reader unit entered the failed state

[Service]
Type=oneshot
UMask=0077
ExecStart=/bin/sh -c 'umask 077 && set -C && /usr/bin/systemctl show c3po-reader.service --property=Result,ExecMainCode,ExecMainStatus,NRestarts > /var/lib/c3po-reader/failed.`/usr/bin/date -u +%%Y%%m%%dT%%H%%M%%SZ`'
StandardOutput=journal
StandardError=journal
SyslogIdentifier=c3po-reader-alert
""".encode('ascii')
READER_ALERT_TEMPLATE_SHA256='0653bf416e77c5b69d66e4952468380e89b2a79d1cc38c40509332ae015cce2f'
# Placeholders of the service and how often each occurs (the README's table, plus the two of decision 6).
SERVICE_OCCURRENCES={'IMAGE_ID':2,'HOST_DATA_ROOT':2,'HOST_JOURNAL_ROOT':2,'CONTAINER_JOURNAL_ROOT':1,'HOST_CAPACITY_ROOT':2,
                     'HOST_SOURCE_ROOT':2,'CONTAINER_SOURCE_ROOT':1,'HOST_CONFIG_DIR':9,'NETWORK':1}
HOST_PATH_NAMES=('HOST_DATA_ROOT','HOST_JOURNAL_ROOT','HOST_CAPACITY_ROOT','HOST_SOURCE_ROOT','HOST_CONFIG_DIR')
CONTAINER_TARGET_NAMES=('CONTAINER_JOURNAL_ROOT','CONTAINER_SOURCE_ROOT')
# The README's substitution grammar: four (here five) host paths, a positive grammar for a container path at a child
# of "/", the image by ID, and the network by name.
HOST_PATH_GRAMMAR='/[A-Za-z0-9._/-]+'
CONTAINER_TARGET_GRAMMAR='/c3po-[a-z0-9][a-z0-9-]*'
CONTAINER_TARGETS_TAKEN=('/c3po-capacity','/c3po-reader')
NETWORK_GRAMMAR='[A-Za-z0-9][A-Za-z0-9_.-]*'
FORBIDDEN_NETWORKS=('host','none','bridge')
TEMPLATE_FORBIDDEN_CHARACTERS=('%','$','"',"'",';')
MAX_UNIT_BYTES=16384
WRITE_ALLOWANCE_SECONDS=15                # what must be left of the budget before the first creation (the writes take milliseconds)

# ---- CONFLICT SCAN: the reviewed scan of HOSTOPS01 (scan.py) without alias links. A link's text cannot be read here:
# ---- the frozen core has no readlink and an operation part makes no system call of its own (CORE.md rule 4). The
# ---- precheck receipt of the same boot, which this request must cite, scanned the three names alias links included.
SCAN_DIRECTORIES=('/etc/systemd/system.control','/run/systemd/system.control','/run/systemd/transient',
                  '/run/systemd/generator.early','/etc/systemd/system','/etc/systemd/system.attached',
                  '/run/systemd/system','/run/systemd/system.attached','/run/systemd/generator',
                  '/usr/local/lib/systemd/system','/usr/lib/systemd/system','/run/systemd/generator.late')
DEPENDENCY_SUFFIXES=('.wants','.requires','.upholds')
SCAN_ENTRY_NAME='[A-Za-z0-9@._:-]{1,128}'
MAX_SCAN_ENTRIES=4096
MAX_FINDINGS=64
MAX_LEFTOVERS=16
SCAN_SCOPE={'lookup_directories':list(SCAN_DIRECTORIES),'dependency_suffixes':list(DEPENDENCY_SUFFIXES),
            'drop_in_forms':['<name>.d','<type>.d','<dash-truncated prefix>-.<type>.d'],
            'own_dependency_directories':['<name>.wants','<name>.requires','<name>.upholds'],
            'leftovers':'temporaries of the family in the unit directory, by name and identity',
            'not_scanned':['alias links (a symbolic link of a unit type whose text ends in a signed name): the frozen core reads no link text; '
                           'the cited precheck scanned them','/lib/systemd/system when /lib is a symbolic link (same directory as /usr/lib/systemd/system)',
                           'a link inside a dependency directory whose own name is not a signed name but whose text ends in one',
                           'user-manager directories']}

SCOPE_STATEMENT=('Creates only the three units of the V2 shadow reader in '+UNIT_DIRECTORY+' (c3po-reader.service rendered with the '
                 'values of this source, c3po-reader.timer and c3po-reader-alert.service verbatim), root:root, mode 0644, each written '
                 'under a dot-prefixed temporary name that systemd does not load, fsynced, then linked to its final name (a link never '
                 'replaces anything), after which the temporary of this run is removed once its identity is proved; nothing else is ever '
                 'removed. The installed producer unit, the journal root and the data volume are only read. No process is started: no '
                 'systemctl verb, no daemon-reload, no enablement, no start, no drop-in, no overwrite, no chmod, chown or rename. The '
                 'manager is reloaded by the reader switch under its own GO, never by this operation. A spent GO is never retried; after '
                 'anything other than the success criterion the host state is established by a read-only operation under its own GO.')


def overlap(first,second):return inside(first,second) or inside(second,first)

def placement_findings(values,producer_sources=()):
    """The README's isolation rules on the values, and the same relation between the host journal root and the other
    bind sources of the installed producer unit. Returns the codes of every rule broken, in a fixed order. Pure."""
    data,journal,capacity=values['HOST_DATA_ROOT'],values['HOST_JOURNAL_ROOT'],values['HOST_CAPACITY_ROOT']
    source,config=values['HOST_SOURCE_ROOT'],values['HOST_CONFIG_DIR']
    found=[]
    if any(overlap(config,other) for other in (data,capacity,journal,source)):found.append('CONFIG_DIRECTORY_OVERLAPS_A_BIND_SOURCE')
    if any(overlap(journal,other) for other in (data,capacity,source)):found.append('HOST_JOURNAL_OVERLAPS_A_BIND_SOURCE')
    if any(overlap(source,other) for other in (data,capacity)):found.append('SOURCE_ROOT_OVERLAPS_A_BIND_SOURCE')
    if overlap(capacity,data):found.append('CAPACITY_ROOT_OVERLAPS_THE_DATA_VOLUME')
    if any(overlap(journal,other) for other in producer_sources if other!=journal):found.append('HOST_JOURNAL_OVERLAPS_A_PRODUCER_PRIVATE_ROOT')
    targets=[values[name] for name in CONTAINER_TARGET_NAMES]
    if len(set(targets))!=len(targets) or any(target in CONTAINER_TARGETS_TAKEN for target in targets):found.append('CONTAINER_TARGETS_NOT_DISTINCT')
    return found

def render_service(template,values):
    """Plain textual substitution after the README's grammar: every value checked before rendering, each placeholder
    occurring exactly as counted, nothing of the form @NAME@ left. Returns the bytes. Pure."""
    need(type(template) is bytes and re.fullmatch(rb'[\x20-\x7e\n]*',template) is not None
         and not any(character.encode('ascii') in template for character in TEMPLATE_FORBIDDEN_CHARACTERS),'TEMPLATE_CHARACTERS')
    found=re.findall(rb'@([A-Z_]+)@',template)
    need({name.decode('ascii'):found.count(name) for name in set(found)}==SERVICE_OCCURRENCES,'PLACEHOLDER_COUNTS')
    need(type(values) is dict and set(values)==set(SERVICE_OCCURRENCES) and all(type(value) is str for value in values.values()),'SUBSTITUTION_KEYS')
    for name in HOST_PATH_NAMES:need(text(values[name],HOST_PATH_GRAMMAR) and clean_path(values[name]),'PATH_INVALID')
    for name in CONTAINER_TARGET_NAMES:need(text(values[name],CONTAINER_TARGET_GRAMMAR),'CONTAINER_TARGET_INVALID')
    need(text(values['IMAGE_ID'],IMAGE_ID),'IMAGE_ID_INVALID')
    network=values['NETWORK']
    need(text(network,NETWORK_GRAMMAR) and network not in FORBIDDEN_NETWORKS,'NETWORK_FORBIDDEN')        # container:* fails the grammar
    findings=placement_findings(values)
    need(not findings,findings[0] if findings else 'PLACEMENT_INVALID')
    rendered=template
    for name in sorted(values):rendered=rendered.replace(('@'+name+'@').encode('ascii'),values[name].encode('ascii'))
    need(b'@' not in rendered,'UNRESOLVED_PLACEHOLDER')         # the README: the render fails if any '@' survives
    need(len(rendered)<=MAX_UNIT_BYTES,'RENDER_TOO_LARGE')
    return rendered

def verbatim(template):
    """A unit installed as it stands: ASCII, no placeholder sign at all."""
    need(type(template) is bytes and re.fullmatch(rb'[\x20-\x7e\n]*',template) is not None and b'@' not in template
         and 0<len(template)<=MAX_UNIT_BYTES,'VERBATIM_TEMPLATE_INVALID')
    return template

def rendered_units():
    """The three files this source installs, by key, from its own templates and values. Pure."""
    need(sha(READER_SERVICE_TEMPLATE)==READER_SERVICE_TEMPLATE_SHA256 and sha(READER_TIMER_TEMPLATE)==READER_TIMER_TEMPLATE_SHA256
         and sha(READER_ALERT_TEMPLATE)==READER_ALERT_TEMPLATE_SHA256,'TEMPLATE_HASH_MISMATCH')
    return {'READER_SERVICE':render_service(READER_SERVICE_TEMPLATE,READER_VALUES),'READER_TIMER':verbatim(READER_TIMER_TEMPLATE),
            'READER_ALERT':verbatim(READER_ALERT_TEMPLATE)}

def producer_facts(raw):
    """What the installed producer unit says of the journal and of the image, read from its own text: the source and the
    target of the one bind whose target is its --journal-root argument, the image it names (twice, one ID), and the
    sources of its other binds. Pure; raises PRODUCER_UNIT_NOT_AS_SIGNED for any other shape."""
    need(type(raw) is bytes and re.fullmatch(rb'[\x20-\x7e\n]*',raw) is not None,'PRODUCER_UNIT_NOT_AS_SIGNED')
    body=raw.decode('ascii')
    binds=re.findall(r'(?m)^  --mount type=bind,source=(/[A-Za-z0-9._/-]+),target=(/[A-Za-z0-9._/-]+)(,readonly)? \\$',body)
    roots=re.findall(r' --journal-root (/[A-Za-z0-9._/-]+) ',body);images=re.findall(r'sha256:[0-9a-f]{64}',body)
    need(len(roots)==1 and body.count('--journal-root')==1 and len(images)==2 and len(set(images))==1 and body.count('--mount ')==len(binds),'PRODUCER_UNIT_NOT_AS_SIGNED')
    journal=[(source,target,readonly) for source,target,readonly in binds if target==roots[0]]
    need(len(journal)==1 and journal[0][2]=='','PRODUCER_UNIT_NOT_AS_SIGNED')
    return {'journal_source':journal[0][0],'journal_target':journal[0][1],'image_id':images[0],
            'other_sources':sorted(source for source,target,_ in binds if target!=roots[0])}

def root_only_chain(rows,path,code):
    """Signed rows of an existing directory under a chain controlled by root alone: no open root, every component uid 0
    and gid 0, not writable by group or other, not setgid (Codex decision 6 for bind sources; the unit directory too)."""
    rows=validate_chain(rows,path,open_root=None,receives_entry=True)
    need(all(row['gid']==0 and not row['mode']&stat.S_ISGID for row in rows),code)
    return rows

def units_of(plan):
    """The three signed unit rows, in the fixed order, each compared with this source's own render. Pure.
    Returns [(unit, bytes)]."""
    units=plan['units'];renders=rendered_units()
    need(type(units) is list and len(units)==len(UNIT_ORDER),'UNITS_INVALID')
    out=[]
    for unit,(key,name) in zip(units,UNIT_ORDER):
        need(type(unit) is dict and set(unit)==set(UNIT_KEYS),'UNITS_INVALID')
        need(unit['key']==key and unit['destination_name']==name,'UNIT_NAME_INVALID')
        expect=unit['expect']
        need(expect=='ABSENT' or (type(expect) is dict and set(expect)==set(EXPECT_KEYS) and integer(expect['device'])
                                  and integer(expect['inode'],1) and integer(expect['links'],1,2)),'EXPECT_INVALID')
        content=renders[key]
        need(unit['rendered_sha256']==sha(content) and unit['rendered_bytes']==len(content),'RENDERED_HASH_MISMATCH')
        out.append((unit,content))
    need(any(unit['expect']=='ABSENT' for unit,_ in out),'NOTHING_TO_CREATE')
    return out

def leftovers_of(plan):
    items=plan['acknowledged_leftovers']
    need(type(items) is list and len(items)<=MAX_LEFTOVERS,'LEFTOVERS_INVALID')
    for item in items:
        need(type(item) is dict and set(item)==set(LEFTOVER_KEYS) and text(item['name'],LEFTOVER)
             and integer(item['device']) and integer(item['inode'],1),'LEFTOVERS_INVALID')
    need(len({item['name'] for item in items})==len(items),'LEFTOVERS_INVALID')
    return items

def validate_plan(plan):
    root_only_chain(plan['unit_rows'],UNIT_DIRECTORY,'UNIT_CHAIN_NOT_ROOT_CONTROLLED')
    journal=root_only_chain(plan['journal_rows'],READER_VALUES['HOST_JOURNAL_ROOT'],'JOURNAL_CHAIN_NOT_ROOT_CONTROLLED')
    need((journal[-1]['uid'],journal[-1]['gid'],journal[-1]['mode'])==(0,0,0o700),'JOURNAL_ROOT_NOT_PRIVATE')
    data=validate_chain(plan['data_rows'],READER_VALUES['HOST_DATA_ROOT'],open_root=READER_VALUES['HOST_DATA_ROOT'])
    need(mount_point_of(data)==READER_VALUES['HOST_DATA_ROOT'],'DATA_VOLUME_NOT_A_MOUNT_POINT')
    need(journal[-1]['device']!=data[-1]['device'],'JOURNAL_ON_THE_DATA_VOLUME')
    need(hexpin(plan['evidence_boot_id_sha256']),'EVIDENCE_BOOT_UNBOUND')
    units_of(plan);leftovers_of(plan)

def effects_of(plan):
    """What the signers see in the authority and in the GO without opening the request; recomputed and compared."""
    renders=rendered_units()
    return {'operation':OPERATION,'epoch':READER_EPOCH,'directory':chain_effects(plan['unit_rows']),
            'units':[{'destination_name':unit['destination_name'],'mode_octal':'%04o'%UNIT_MODE,'uid':0,'gid':0,
                      'rendered_sha256':sha(renders[unit['key']]),'rendered_bytes':len(renders[unit['key']]),
                      'expect':'ABSENT' if unit['expect']=='ABSENT' else 'PRESENT'} for unit in plan['units']],
            'files_to_create':sum(1 for unit in plan['units'] if unit['expect']=='ABSENT'),
            'values':dict(READER_VALUES),'template_revision':TEMPLATE_REVISION,
            'journal':chain_effects(plan['journal_rows']),'data_volume':chain_effects(plan['data_rows']),
            'producer_unit':{'path':UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,'sha256':PRODUCER_SHA256,'bytes':PRODUCER_BYTES,'read_only':True},
            'acknowledged_leftovers':[item['name'] for item in plan['acknowledged_leftovers']],
            'evidence_boot_id_sha256':plan['evidence_boot_id_sha256'],
            'daemon_reload':{'performed_by_this_operation':False,'owner':DAEMON_RELOAD_OWNER},
            'external_processes':0,'pre_existing_objects_modified':False,'activation':False}
def success_of(plan):return COMPLETE_OUTCOME

_RENDERED=rendered_units()
SCOPE={'operation':OPERATION,'dates':list(DATES),'statement':SCOPE_STATEMENT,'core_sha256':CORE_SHA256,
       'writes_allowed':WRITES_ALLOWED,'activation_allowed':ACTIVATION_ALLOWED,'epoch':READER_EPOCH,'unit_directory':UNIT_DIRECTORY,
       'units':[{'key':key,'destination_name':name,'rendered_sha256':sha(_RENDERED[key]),'rendered_bytes':len(_RENDERED[key]),
                 'template_sha256':{'READER_SERVICE':READER_SERVICE_TEMPLATE_SHA256,'READER_TIMER':READER_TIMER_TEMPLATE_SHA256,
                                    'READER_ALERT':READER_ALERT_TEMPLATE_SHA256}[key],
                 'how':'rendered' if key=='READER_SERVICE' else 'verbatim'} for key,name in UNIT_ORDER],
       'every_file':{'type':'regular file','uid':0,'gid':0,'mode_octal':'%04o'%UNIT_MODE,'umask_octal':'0022','links':1},
       'values':dict(READER_VALUES),'service_occurrences':dict(SERVICE_OCCURRENCES),'template_revision':TEMPLATE_REVISION,
       'template_deviation':{'readme_service_sha256':README_SERVICE_SHA256,
                             'inserted':['@HOST_SOURCE_ROOT@ in RequiresMountsFor, after @HOST_CAPACITY_ROOT@',
                                         '  --mount type=bind,source=@HOST_SOURCE_ROOT@,target=@CONTAINER_SOURCE_ROOT@,readonly \\ after the capacity bind'],
                             'why':'Codex decision 6 (#429 5985748037) and the placement 5985768668: the source root leaves the data volume'},
       'grammar':{'host_path':HOST_PATH_GRAMMAR,'container_target':CONTAINER_TARGET_GRAMMAR,'container_targets_taken':list(CONTAINER_TARGETS_TAKEN),
                  'image_id':IMAGE_ID,'network':NETWORK_GRAMMAR,'forbidden_networks':list(FORBIDDEN_NETWORKS)+['container:*'],
                  'template_forbidden_characters':list(TEMPLATE_FORBIDDEN_CHARACTERS)},
       'producer_unit':{'path':UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,'sha256':PRODUCER_SHA256,'bytes':PRODUCER_BYTES,
                        'required':'regular, root:root 0644, one link, these bytes; its journal bind and image equal the reader values; '
                                   'its other bind sources do not overlap the host journal root'},
       'catalog':{'files':list(CATALOG_FILE_NAMES),'required':'regular, root:root 0600, one link, by lstat only (Codex E1-19: B2 only after E3 and the real catalogue)'},
       'journal':{'path':READER_VALUES['HOST_JOURNAL_ROOT'],'chain':'controlled by root alone (uid 0, gid 0, no group or other write, no setgid, no open root)',
                  'leaf':'root:root 0700','device':'differs from the data volume'},
       'data_volume':{'path':READER_VALUES['HOST_DATA_ROOT'],'open_root':READER_VALUES['HOST_DATA_ROOT'],'mount_point':True,
                      'decision_6':'NOT root-controlled (uid 1000): the one bind source of the unit outside decision 6; an open question, see DESIGN.md'},
       'bind_sources_not_opened_here':{'capacity':READER_VALUES['HOST_CAPACITY_ROOT'],'source_root':READER_VALUES['HOST_SOURCE_ROOT'],
                                       'launcher':READER_VALUES['HOST_CONFIG_DIR']+'/launcher'},
       'expect':['ABSENT: created exclusively','PRESENT with signed device, inode and link count: verified against the render, never touched'],
       'temporary_name':TEMPORARY%('<first 16 hex of the GO hash>',0),'leftover_pattern':LEFTOVER,
       'conflict_scan':SCAN_SCOPE,'files':FILES_SCOPE,'evidence_operations_required':list(EVIDENCE_OPERATIONS),
       'daemon_reload':{'performed_by_this_operation':False,'owner':DAEMON_RELOAD_OWNER},
       'file_contents_read':[BOOT_ID_PATH,UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,
                             'a regular file found at a destination name, only to say whether its bytes equal the render: of a file that is not '
                             'the render no digest and no size is reported','the unit files this run installed (readback inside the run)'],
       'external_processes':0,
       'never':['a process','systemctl','daemon-reload','enablement link','start','drop-in','overwrite','chmod','chown','rename','truncate',
                'removal of anything but the temporary this run created and proved by identity','repair of an existing object',
                'docker','container environment','a secret','shell','network connection','a second attempt'],
       'limits':{'max_seconds':MAX_SECONDS,'max_gate_span_seconds':MAX_GATE_SPAN_SECONDS,'unit_bytes':MAX_UNIT_BYTES,'scan_entries':MAX_SCAN_ENTRIES,
                 'findings':MAX_FINDINGS,'leftovers':MAX_LEFTOVERS,'write_allowance_seconds':WRITE_ALLOWANCE_SECONDS,'receipt_bytes':RECEIPT_LIMIT}}
SCOPE_SHA256=sha(canonical(SCOPE))


class Native(NativeRead,NativeFiles):
    """Everything this source can do to the host: the read primitives and the creating calls. No process."""


# ---------------------------------------------------------------- the conflict scan (lstat and names only)
def drop_in_names(name):
    """<name>.d, the type-level <type>.d, and each dash-truncated prefix form the manager also reads."""
    stem,_,suffix=name.rpartition('.');parts=stem.split('-')
    return [name+'.d',suffix+'.d']+['-'.join(parts[:index])+'-.'+suffix+'.d' for index in range(1,len(parts))]

def conflict_scan(host,names,check):
    """lstat only, no content, no link text. In every lookup directory: a unit of the same name anywhere but the
    install directory, every drop-in directory form, the unit's own dependency directories, and the name inside every
    dependency directory. In the install directory also the leftover temporaries of this family. A directory that
    cannot be read is UNAVAILABLE, never an absence."""
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|host.noatime()
    findings=[];leftovers=[];directories={}
    def present(name,fd):
        check()
        try:return host.lstat(name,fd)
        except FileNotFoundError:return None
    def add(code,directory,name,within=None):
        findings.append({'code':code,'directory':directory,'name':name,'within':within})
    def one(directory):
        try:fd=descend(host,directory,check)
        except FileNotFoundError:return {'status':'COMPLETE','exists':False}
        try:
            listed=[];issues=[]
            for name in host.names(fd):
                listed.append(name);need(len(listed)<=MAX_SCAN_ENTRIES,'SCAN_LIMIT')
                if len(listed)%256==0:check()
            for name in names:
                if directory!=UNIT_DIRECTORY and present(name,fd) is not None:add('UNIT_SHADOWED_IN_OTHER_PATH',directory,name)
                for candidate in drop_in_names(name):
                    if present(candidate,fd) is not None:add('DROP_IN_PRESENT',directory,candidate)
                for suffix in DEPENDENCY_SUFFIXES:
                    if present(name+suffix,fd) is not None:add('OWN_DEPENDENCY_DIRECTORY_PRESENT',directory,name+suffix)
            for entry in sorted(listed):
                if directory==UNIT_DIRECTORY and text(entry,LEFTOVER):
                    info=present(entry,fd)
                    if info is not None:
                        leftovers.append({'name':entry,'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,
                                          'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink,'device':info.st_dev,'inode':info.st_ino})
                if not entry.endswith(DEPENDENCY_SUFFIXES):continue
                info=present(entry,fd)
                if info is None:continue
                label=entry if text(entry,SCAN_ENTRY_NAME) else None
                if not stat.S_ISDIR(info.st_mode):
                    issues.append('DEPENDENCY_DIRECTORY_NOT_A_DIRECTORY');continue
                check();child=host.open(entry,flags,dir_fd=fd)
                try:
                    held=host.fstat(child);need((held.st_dev,held.st_ino)==(info.st_dev,info.st_ino),'PATH_CHANGED')
                    for name in names:
                        if present(name,child) is not None:add('ENABLEMENT_LINK_PRESENT',directory,name,label)
                finally:host.close(child)
            return {'status':'COMPLETE' if not issues else 'UNAVAILABLE','exists':True,'entries':len(listed),
                    **({'code':issues[0]} if issues else {})}
        finally:host.close(fd)
    for directory in SCAN_DIRECTORIES:directories[directory]=attempt(lambda directory=directory:one(directory))
    status=combined(directories.values())
    return {'status':'COMPLETE' if status=='COMPLETE' else 'UNAVAILABLE','directories':directories,
            'findings':findings[:MAX_FINDINGS],'findings_truncated':len(findings)>MAX_FINDINGS,
            'finding_codes':sorted({item['code'] for item in findings}),'leftovers':leftovers[:MAX_FINDINGS],
            'leftover_count':len(leftovers)}


# ---------------------------------------------------------------- the precheck
def producer_unit(host,directory,gate):
    """The installed producer unit, read by descriptor without following a link: regular, root:root 0644, one link,
    exactly the signed bytes; then its journal bind and image, which must be the reader's."""
    gate()
    try:named=host.lstat(PRODUCER_SERVICE_NAME,directory.fd)
    except FileNotFoundError:raise Refused('PRODUCER_UNIT_ABSENT') from None
    need(stat.S_ISREG(named.st_mode) and (named.st_uid,named.st_gid,stat.S_IMODE(named.st_mode),named.st_nlink)==(0,0,UNIT_MODE,1),
         'PRODUCER_UNIT_NOT_AS_SIGNED')
    raw,info=read_regular(host,PRODUCER_SERVICE_NAME,directory.fd,gate,MAX_UNIT_BYTES)
    need((info.st_dev,info.st_ino)==(named.st_dev,named.st_ino) and len(raw)==PRODUCER_BYTES and sha(raw)==PRODUCER_SHA256,'PRODUCER_UNIT_NOT_AS_SIGNED')
    facts=producer_facts(raw)
    need((facts['journal_source'],facts['journal_target'],facts['image_id'])
         ==(READER_VALUES['HOST_JOURNAL_ROOT'],READER_VALUES['CONTAINER_JOURNAL_ROOT'],READER_VALUES['IMAGE_ID']),'PRODUCER_VALUES_NOT_THE_READER_VALUES')
    findings=placement_findings(READER_VALUES,facts['other_sources'])
    need(not findings,findings[0] if findings else 'PLACEMENT_INVALID')
    return {'path':UNIT_DIRECTORY+'/'+PRODUCER_SERVICE_NAME,'sha256':PRODUCER_SHA256,'bytes':len(raw),'device':info.st_dev,'inode':info.st_ino,
            'journal_source':facts['journal_source'],'journal_target':facts['journal_target'],'image_id':facts['image_id'],
            'other_sources':facts['other_sources']}

def catalog_files(host,journal,gate):
    """The real catalogue is there (E1-19): epoch.json and maintenance.lock in the held journal root, each a regular
    file, root:root 0600, one link. lstat only: nothing of the catalogue is opened, read or locked here."""
    found={}
    for name in CATALOG_FILE_NAMES:
        gate()
        try:info=host.lstat(name,journal.fd)
        except FileNotFoundError:raise Refused('CATALOG_NOT_INITIALISED') from None
        found[name]={'type':kind(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),'links':info.st_nlink}
        need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,CATALOG_FILE_MODE,1),
             'CATALOG_FILE_NOT_PRIVATE')
    return found

def unit_table(units,host,directory,gate):
    """Per name: what exists there, by lstat; a regular file found there is read only to say whether it is the signed
    render. Its digest and size are reported ONLY when it is (a foreign unit may carry an inline secret)."""
    rows=[]
    for unit,content in units:
        name=unit['destination_name'];expect=unit['expect']
        row={'key':unit['key'],'destination_name':name,'expected':'ABSENT' if expect=='ABSENT' else 'PRESENT'}
        rows.append(row);gate()
        try:named=host.lstat(name,directory.fd)
        except FileNotFoundError:named=None
        if named is None:
            row['observed']='ABSENT';row['state']='OK_ABSENT' if expect=='ABSENT' else 'EXPECTED_PRESENT_ABSENT';continue
        row.update(observed='PRESENT',type=kind(named.st_mode),uid=named.st_uid,gid=named.st_gid,mode_octal='%04o'%stat.S_IMODE(named.st_mode),
                   links=named.st_nlink,device=named.st_dev,inode=named.st_ino);equal=None
        if stat.S_ISREG(named.st_mode):
            try:
                raw,info=read_regular(host,name,directory.fd,gate,MAX_UNIT_BYTES)
                equal=raw==content and (info.st_dev,info.st_ino)==(named.st_dev,named.st_ino)
            except Refused as error:row['read_code']=code_of(error,'FILE_UNREADABLE')
            row['bytes_equal_signed_render']=equal
            if equal:row.update(sha256=sha(raw),size=len(raw))
        conforms=bool(equal and named.st_uid==0 and named.st_gid==0 and stat.S_IMODE(named.st_mode)==UNIT_MODE)
        if not stat.S_ISREG(named.st_mode):row['state']='OCCUPIED_NOT_REGULAR'
        elif expect=='ABSENT':row['state']='PRESENT_EQUAL_NOT_SIGNED' if conforms and named.st_nlink in (1,2) else 'PRESENT_FOREIGN'
        elif conforms and (named.st_dev,named.st_ino,named.st_nlink)==(expect['device'],expect['inode'],expect['links']):row['state']='OK_PRESENT'
        else:row['state']='PRESENT_IDENTITY_MISMATCH'
    return rows

def precedence(rows,scan,signed,own):
    """The refusal of the unit table and of the scan, in a fixed order, or None. None of these says that an installation
    happened: they say what exists."""
    states={row['state'] for row in rows};seen={item['name']:(item['device'],item['inode']) for item in scan['leftovers']}
    if 'OCCUPIED_NOT_REGULAR' in states:return 'UNIT_NAME_OCCUPIED'
    if 'PRESENT_FOREIGN' in states:return 'UNIT_PRESENT_FOREIGN_CONTENT'
    if states&{'EXPECTED_PRESENT_ABSENT','PRESENT_IDENTITY_MISMATCH'} or set(signed)-set(seen):return 'EXPECTATION_MISMATCH'
    if 'PRESENT_EQUAL_NOT_SIGNED' in states:
        # "All present" is said only of one-link files with no unacknowledged temporary beside them; a name that still
        # shares its inode with a temporary is the state an interrupted run leaves.
        settled=all(row['observed']=='PRESENT' for row in rows) and all(row['links']==1 for row in rows) and not scan['leftovers_not_acknowledged'] \
            and scan['leftover_count']<=MAX_FINDINGS
        return 'ALL_UNITS_PRESENT' if settled else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
    if scan['leftover_count']>MAX_FINDINGS or scan['leftovers_not_acknowledged']:
        return 'TEMPORARY_NAME_OCCUPIED' if own&set(scan['leftovers_not_acknowledged']) else 'PRIOR_PARTIAL_REQUIRES_RECONCILIATION'
    for code in ('DROP_IN_PRESENT','OWN_DEPENDENCY_DIRECTORY_PRESENT','ENABLEMENT_LINK_PRESENT','UNIT_SHADOWED_IN_OTHER_PATH'):
        if code in scan['finding_codes']:return code
    if scan['status']!='COMPLETE':return 'CONFLICT_SCAN_UNAVAILABLE'
    return None


def _reduce_scan(receipt):
    scan=((receipt.get('precheck') or {}).get('conflicts'))
    if type(scan) is dict:scan['directories']={name:item.get('status') for name,item in scan.get('directories',{}).items()}
def _reduce_precheck(receipt):
    table=receipt.get('precheck') or {}
    receipt['precheck']={'units':[{'key':row.get('key'),'state':row.get('state')} for row in table.get('units',[])],
                         'finding_codes':(table.get('conflicts') or {}).get('finding_codes')}
REDUCTIONS=[('SCAN_DIRECTORIES_REDUCED_TO_STATUS',_reduce_scan),('PRECHECK_REDUCED_TO_STATES',_reduce_precheck)]

def perform(plan,gate,host,bound,clock,monotonic,state):
    begun,mark=clock(),monotonic()
    units=units_of(plan)                                      # pure: the bytes that will be written, and no others
    gate()                                                    # first gate call: before anything is observed
    state.started=True
    detail={'unit_directory':[],'journal':[],'data_volume':[],'producer':None,'catalog':None,'precheck':None};ledger=[];held=[];directory=None
    go16=bound['go_sha256'][:16]
    def finish(status,outcome,code,extra):
        return seal(envelope(status,outcome,code,dict(bound,observed_at=begun.isoformat(),effects=effects_of(plan),
            clock=timing(begun,mark,clock,monotonic),mutating_calls=state.counts(),unit_directory=detail['unit_directory'],
            journal=detail['journal'],data_volume=detail['data_volume'],producer=detail['producer'],catalog=detail['catalog'],precheck=detail['precheck'],
            ledger=ledger,objects_left_by_this_run=objects_left([],ledger),external_processes=0,daemon_reload_owner=DAEMON_RELOAD_OWNER,
            pre_existing_objects_modified=False,**extra)))
    try:
        # ---- everything is looked at before the first creation
        try:
            need(tuple(host.identity())==(0,0),'EXECUTOR_IDENTITY')
            host.umask(0o022)
            need(boot_id_sha256(host,gate)==plan['evidence_boot_id_sha256'],'EVIDENCE_FROM_EARLIER_BOOT')
            directory=Pinned(host,walk_pinned(host,plan['unit_rows'],gate,detail['unit_directory']),rows=plan['unit_rows']);held.append(directory)
            detail['producer']=producer_unit(host,directory,gate)
            journal=Pinned(host,walk_pinned(host,plan['journal_rows'],gate,detail['journal']),rows=plan['journal_rows']);held.append(journal)
            detail['catalog']=catalog_files(host,journal,gate)
            # Each walk compares the device of every component with its signed row, and validate_plan refused rows that
            # put the journal on the data volume's device: what is held here is two filesystems.
            held.append(Pinned(host,walk_pinned(host,plan['data_rows'],gate,detail['data_volume']),rows=plan['data_rows']))
            rows=unit_table(units,host,directory,gate)
            scan=conflict_scan(host,[name for _,name in UNIT_ORDER],gate)
            signed={item['name']:(item['device'],item['inode']) for item in plan['acknowledged_leftovers']}
            seen={item['name']:(item['device'],item['inode']) for item in scan['leftovers']}
            scan['leftovers_acknowledged']=sorted(name for name in seen if signed.get(name)==seen[name])
            scan['leftovers_not_acknowledged']=sorted(name for name in seen if signed.get(name)!=seen[name])
            own={TEMPORARY%(go16,index) for index,(unit,_) in enumerate(units) if unit['expect']=='ABSENT'}
            detail['precheck']={'units':rows,'conflicts':scan}
            code=precedence(rows,scan,signed,own)
            if code is None:
                # The last refusal that costs nothing on the host: the time the creations and the readback may take.
                left=gate();detail['precheck']['seconds_left_before_first_effect']=int(left)
                need(left>=WRITE_ALLOWANCE_SECONDS,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')
        except Exception as error:
            code=code_of(error,'PRECHECK_OS_ERROR' if isinstance(error,OSError) else 'PRECHECK_FAILED')
        if code is not None:return finish(REFUSED_STATUS,REFUSED_OUTCOME,code,{'phase_reached':'PRECHECK','readback':None})
        # ---- from here on nothing refuses unless nothing has changed
        stop=None
        for index,(unit,content) in enumerate(units):
            path=UNIT_DIRECTORY+'/'+unit['destination_name']
            if unit['expect']!='ABSENT' or stop is not None:
                ledger.append({'key':unit['key'],'path':path,'code':None,'sha256_signed':sha(content),'sha256_observed':None,
                               'state':'NOT_ATTEMPTED' if unit['expect']=='ABSENT' else 'PRESENT_VERIFIED_NOT_TOUCHED'});continue
            row=create_file(index,unit['key'],path,content,UNIT_MODE,directory,host,gate,state,go16);ledger.append(row)
            if row['state']!='INSTALLED_DURABLE':stop=row['code'] or 'INSTALL_FAILED'
        # ---- the readback inside the run: every name through the held directory, then the directory from "/"
        if stop is None:
            for (unit,content),row in zip(units,ledger):
                if stop is not None:break
                if row['state']=='INSTALLED_DURABLE':
                    stop=readback_file(row,content,UNIT_MODE,directory,host,gate);continue
                try:
                    raw,info=read_regular(host,unit['destination_name'],directory.fd,gate,MAX_UNIT_BYTES)
                    row['sha256_observed']=sha(raw);expect=unit['expect']
                    need(raw==content and (info.st_dev,info.st_ino,info.st_nlink)==(expect['device'],expect['inode'],expect['links'])
                         and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,UNIT_MODE),'READBACK_HASH_MISMATCH')
                except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        if stop is None:
            try:directory.verify(gate)
            except Exception as error:stop=code_of(error,'READBACK_UNAVAILABLE')
        extra={'phase_reached':'CREATION','readback':'COMPLETE' if stop is None else None}
        if stop is None:return finish(COMPLETE_STATUS,COMPLETE_OUTCOME,None,extra)
        # REFUSED only while no mutating call succeeded and none is uncertain; otherwise the run is a partial.
        if state.clean():return finish(REFUSED_STATUS,REFUSED_OUTCOME,stop,extra)
        return finish(PARTIAL_STATUS,PARTIAL_OUTCOME,stop,extra)
    finally:
        for handle in held:
            try:handle.close()
            except Exception:pass
# ==== END OP_READER_UNITS ====

if __name__=='__main__':
    raise SystemExit('REFUSED: independently authenticated request/authority/GO and pinned once transport required')
