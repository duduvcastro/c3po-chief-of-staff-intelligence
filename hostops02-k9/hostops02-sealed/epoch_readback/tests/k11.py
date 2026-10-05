"""Fixtures of the K11 tests: request plans built from the emulated host as a binder would copy them from read-only
receipts, synthetic release, policy and override bytes, and the emulated container.

The emulated container does not stand in for the snippet: it EXECUTES the exact bytes the run put on standard input
(the SIGNED_CONTEXT line and the pinned snippet) with a real interpreter in isolated mode, against a stand-in of the
application package written to a temporary directory (FAKE below) or, where a checkout of the release and the
calendar library are available, against the application modules of the release themselves. Three lines are put in
front of those bytes, for the test only: the stand-in for /app on the import path, the read-only binds of the run
mapped to temporary copies, and (on request) the alarm scaled down so that a hang costs one second instead of thirty.
Everything here is synthetic: no value, identity or byte of the real host, release or policy."""
import atexit
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
EPOCH='R2D2-V2-SHADOW-2026-10-05'
FIRST='2026-10-05'
REVISION=hostemu.REVISION
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
ORDER='1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e'
EBAR='b492766e4c2ef9e924141ca2be3e47dfbb237086b840aa6bf263b0b9bd0806b1'
KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')
RELEASE_DIRECTORY='r2d2-v2-release-20261005'
RELEASE_FILE='release.CERTIFIED.json'
RELEASE_HOST=hostemu.DATA+'/'+RELEASE_DIRECTORY
TARGET='/c3po-epoch-release'
DATA_TARGET='/app/day-d-data'
POLICY_CONTAINER=DATA_TARGET+'/r2d2-v2-live/2026-10-05/policy.json'
JOURNAL='/var/lib/c3po-bar/journal'
DOCKER_CONFIG='/etc/c3po-bar/docker-cli'
LOCK=hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME
VALID_AT=['2026-10-05T08:45:00+00:00','2026-10-05T13:30:00+00:00','2026-10-09T19:59:59+00:00']
UNITS=('c3po-massive.service','c3po-massive.timer','docker.service')
# The directory activate will create, in a parent that exists (root:root 0700, as on 28/09), and an earlier epoch's
# release directory on the data volume: the default probe of the read-only bind (same filesystem as Monday's bind).
LIVE_PARENT=hostemu.DATA+'/r2d2-v2-live'
LIVE_NAME='2026-10-05'
LIVE_HOST=LIVE_PARENT+'/'+LIVE_NAME
PROBE=hostemu.DATA+'/r2d2-v2-release-20260928'
PROBE_TARGET='/c3po-bind-probe'
LIMITS={'render_ms':3000,'quick_ms':1500,'data_volume_free_bytes':1048576,'data_volume_free_inodes':8}
DEFAULT=object()

def b64(raw):return base64.b64encode(raw).decode('ascii')
def release_bytes(**changes):
    body={'schema':'R2D2_V2_RELEASE_V3','mode':'CERTIFIED','epoch':EPOCH,'first_session':FIRST,'code_revision':REVISION,
          'implementation_package_sha':PACKAGE,'ebar_amendment_sha':EBAR,'approved_at':'2026-10-02T14:00:02+00:00','authorization_ref':'SYNTHETIC'}
    body.update(changes);return f.canonical(body)
RELEASE=release_bytes()
def policy_bytes(release=RELEASE,**changes):
    body={'schema':'R2D2_V2_LIVE_POLICY_V1','mode':'LIVE','epoch':EPOCH,'release_sha':f.sha(release),'code_revision':REVISION,'package_sha':PACKAGE,
          'order_sha':ORDER,'capacity':550,'c8_receipt_sha':'c'*64,'head_go_sha':'d'*64,'valid_from':'2026-10-02T00:00:00+00:00','valid_until':'2026-10-10T00:00:00+00:00'}
    body.update(changes);return f.canonical(body)
POLICY=policy_bytes()
def override_bytes(release=RELEASE,policy=POLICY,**changes):
    environment={KEYS[0]:POLICY_CONTAINER,KEYS[1]:f.sha(policy),KEYS[2]:DATA_TARGET+'/'+RELEASE_DIRECTORY+'/'+RELEASE_FILE,KEYS[3]:f.sha(release)}
    environment.update(changes);return json.dumps({'services':{'r2d2-worker':{'environment':environment}}},sort_keys=True).encode('ascii')      # as activate writes it


# ---------------------------------------------------------------- the stand-in for the application package
FAKE={'__init__.py':'',
'_knobs.py':'''import json,os
def knobs():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'knobs.json')) as stream:return json.load(stream)
    except OSError:return {}
''',
'r2d2_v2_store.py':'''from datetime import datetime, timezone
class ShadowIntegrityError(ValueError):pass
def utc(value):
    if isinstance(value,str):value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('naive')
    return value.astimezone(timezone.utc)
''',
'r2d2_v2_earnings_package.py':'''from ._knobs import knobs
def implementation_package_sha():return knobs().get('package','%s')
'''%PACKAGE,
'r2d2_v2_epoch_assembler.py':'''import hashlib,json
from ._knobs import knobs
EPOCH=knobs().get('assembler_epoch','%s')
FIRST_SESSION='%s'
RUNTIME_ORDER_SHA='%s'
class Refused(ValueError):pass
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def validate_policy(policy,identity,bindings,calendar):
    """The checks of the release's validate_policy that the snippet can meet, in its order and with its codes."""
    if knobs().get('assembler_error'):raise Refused(knobs()['assembler_error'])
    if knobs().get('assembler_foreign_error'):raise ValueError(knobs()['assembler_foreign_error'])
    def need(ok,code):
        if not ok:raise Refused(code)
    need(type(policy) is dict,'POLICY_REQUIRED')
    need(policy.get('schema')=='R2D2_V2_LIVE_POLICY_V1' and policy.get('mode')=='LIVE','POLICY_SCHEMA')
    need(policy.get('epoch')==identity['epoch'] and policy.get('release_sha')==bindings['release_sha'],'POLICY_IDENTITY')
    need(policy.get('order_sha')==identity['runtime_order_sha'],'POLICY_RUNTIME_ORDER')
    need(policy.get('package_sha')==bindings['package_sha'],'POLICY_PACKAGE')
    from .r2d2_v2_store import utc
    need(utc(policy['valid_from'])<=calendar.details(None)['open'] and utc(policy['valid_until'])>=calendar.details(None)['close'],'POLICY_NOT_EPOCH_WIDE')
    need(digest(policy)==bindings['policy_sha'],'POLICY_HASH')
'''%(EPOCH,FIRST,ORDER),
'r2d2_v2_shadow_worker.py':'''import os,stat
from ._knobs import knobs
from .r2d2_v2_store import ShadowIntegrityError
if knobs().get('reader_import_error'):raise ImportError('the worker module cannot be imported')
def _release_bytes(path):
    """The worker's reader, line for line (r2d2_v2_shadow_worker.py lines 29-42 at the release)."""
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,"rb") as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)&0o077 or info.st_size>65536:
            raise ShadowIntegrityError("RELEASE_FILE_NOT_PRIVATE_OR_INVALID")
        data=stream.read(65537);after=os.fstat(stream.fileno())
        if (info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise ShadowIntegrityError("RELEASE_CHANGED_DURING_READ")
        if len(data)!=info.st_size:raise ShadowIntegrityError("RELEASE_CHANGED_DURING_READ")
    return data
''',
'r2d2_v2_shadow.py':'''import hashlib,json,time,types
from datetime import date,datetime,timezone
from ._knobs import knobs
from .r2d2_v2_store import ShadowIntegrityError,utc
from .r2d2_v2_earnings_package import implementation_package_sha
if knobs().get('import_error'):raise ImportError('the application cannot be imported')
EBAR_AMENDMENT_SHA='%s'
class ShadowCalendar:
    def __init__(self):
        if knobs().get('hang'):time.sleep(120)
        if knobs().get('calendar_error'):raise RuntimeError('a message that is not a constant code: /some/path')
        if knobs().get('calendar_token_error'):raise RuntimeError(knobs()['calendar_token_error'])
        self.version=knobs().get('calendar_version','4.13.2')
    def details(self,day):
        return {'open':datetime(2026,10,5,13,30,tzinfo=timezone.utc),'close':datetime(2026,10,9,20,0,tzinfo=timezone.utc)}
class Release:
    @classmethod
    def verify(cls,data,expected_sha,*,now,build_sha,calendar):
        if knobs().get('verify_error'):raise ShadowIntegrityError(knobs()['verify_error'])
        if knobs().get('verify_foreign_error'):raise RuntimeError(knobs()['verify_foreign_error'])
        if hashlib.sha256(data).hexdigest()!=expected_sha:raise ShadowIntegrityError('RELEASE_HASH_MISMATCH')
        body=json.loads(data)
        if body.get('schema')!='R2D2_V2_RELEASE_V3':raise ShadowIntegrityError('RELEASE_POLICY_MISMATCH')
        if body.get('implementation_package_sha')!=implementation_package_sha():raise ShadowIntegrityError('RELEASE_IMPLEMENTATION_PACKAGE_MISMATCH')
        if not utc(body['approved_at'])<=utc(now):raise ShadowIntegrityError('RELEASE_MUST_PRECEDE_FIRST_SESSION')
        if body.get('code_revision')!=build_sha:raise ShadowIntegrityError('RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED')
        return types.SimpleNamespace(epoch=body['epoch'],mode=body['mode'],first_session=date.fromisoformat(body['first_session']),
                                     ebar_amendment_sha=body.get('ebar_amendment_sha'))
'''%EBAR,
'r2d2_v2_live_controller.py':'''import hashlib,json,re
from ._knobs import knobs
from .r2d2_v2_earnings_package import implementation_package_sha as current_package_sha
from .r2d2_v2_shadow_worker import _release_bytes
from .r2d2_v2_store import ShadowIntegrityError,utc
if knobs().get('controller_import_error'):raise ImportError('the controller cannot be imported')
ORDER_SHA='%s'
def read_policy(settings,now):
    """The checks of the controller's read_policy, in its order and with its codes (lines 39-89 at the release)."""
    if knobs().get('policy_error'):raise ShadowIntegrityError(knobs()['policy_error'])
    if knobs().get('policy_foreign_error'):raise KeyError(knobs()['policy_foreign_error'])
    data=_release_bytes(str(settings.r2d2_v2_live_policy_file))
    if hashlib.sha256(data).hexdigest()!=settings.r2d2_v2_live_policy_sha:raise ShadowIntegrityError("LIVE_POLICY_HASH_MISMATCH")
    policy=json.loads(data)
    if (policy.get("schema")!="R2D2_V2_LIVE_POLICY_V1" or policy.get("order_sha")!=ORDER_SHA or policy.get("code_revision")!=settings.build_sha
            or policy.get("package_sha")!=current_package_sha() or any(not re.fullmatch(r"[0-9a-f]{64}",str(policy.get(k,""))) for k in ("c8_receipt_sha","head_go_sha"))
            or type(policy.get("capacity")) is not int or not 1<=policy["capacity"]<=550):raise ShadowIntegrityError("LIVE_POLICY_INVALID")
    start,end=utc(policy["valid_from"]),utc(policy["valid_until"])
    if not start<=now<end:raise ShadowIntegrityError("LIVE_POLICY_OUTSIDE_WINDOW")
    if policy.get("mode")!="LIVE" or (end-start).total_seconds()>90*86400:raise ShadowIntegrityError("LIVE_POLICY_MODE_INVALID")
    return policy
'''%ORDER}

_ROOT=Path(tempfile.mkdtemp(prefix='k11-fake-app-'))
atexit.register(lambda:shutil.rmtree(str(_ROOT),ignore_errors=True))
def fake_tree(**knobs):
    """A directory that holds the stand-in package `app` with these knobs (one directory per set of knobs)."""
    raw=json.dumps(knobs,sort_keys=True).encode();root=_ROOT/hashlib.sha256(raw).hexdigest()[:16]
    if not root.is_dir():
        staging=Path(tempfile.mkdtemp(dir=str(_ROOT)));(staging/'app').mkdir()
        for name,text in FAKE.items():(staging/'app'/name).write_text(text)
        (staging/'app'/'knobs.json').write_bytes(raw)
        try:os.rename(str(staging),str(root))
        except OSError:shutil.rmtree(str(staging),ignore_errors=True)
    return str(root)

SHIM='''import os,sys,signal
sys.path.append(%r)
_k11_map=%r
_k11_open=os.open
def _k11_mapped(path,*arguments,**options):
    for target,real in _k11_map.items():
        if type(path) is str and (path==target or path.startswith(target+'/')):path=real+path[len(target):]
    return _k11_open(path,*arguments,**options)
os.open=_k11_mapped
_k11_alarm=signal.alarm;_k11_scale=%r
if _k11_scale:signal.alarm=lambda seconds:(os.write(2,b'ALARM=%%d\\n'%%seconds),_k11_alarm(_k11_scale))[1]
'''
_CACHE={}
class Container:
    """docker.on_run for the emulated host: runs the exact standard input of the attached run with a real interpreter."""
    def __init__(self,tree=None,alarm_scale=0,python=None):
        self.tree=tree if tree is not None else fake_tree();self.alarm_scale=alarm_scale;self.python=python or sys.executable
        self.calls=[];self.stderr=[]
    def __call__(self,call):
        assert call.command==['python','-I','-B','-'] and call.network=='none' and call.read_only_root and all(mount['read_only'] for mount in call.mounts)
        assert call.stdin.startswith(b'SIGNED_CONTEXT=') and not os.path.exists('/app'),'the workstation must have no /app'
        self.calls.append(call);files=[]
        for mount in call.mounts:
            for name in call.listdir(mount['target']):
                node=call.node(mount['target']+'/'+name);files.append((mount['target'],name,node.kind,node.mode,bytes(node.content),node.target))
        key=(self.tree,self.alarm_scale,self.python,call.stdin,tuple(files))
        if key not in _CACHE:
            work=Path(tempfile.mkdtemp(prefix='k11-binds-'));mapping={}
            try:
                for index,mount in enumerate(call.mounts):
                    real=work/str(index);real.mkdir();mapping[mount['target']]=str(real)
                for target,name,kind,mode,content,link in files:
                    path=Path(mapping[target])/name
                    if kind=='file':
                        path.write_bytes(content);os.chmod(str(path),mode)
                    elif kind=='symlink':os.symlink(link or '/nonexistent',str(path))
                    elif kind=='dir':path.mkdir()
                    elif kind=='fifo':os.mkfifo(str(path))
                shim=(SHIM%(self.tree,mapping,self.alarm_scale)).encode()
                done=subprocess.run([self.python,'-I','-B','-'],input=shim+call.stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                    env={'PATH':'/usr/bin:/bin'},timeout=120)
                _CACHE[key]=(done.returncode if done.returncode>=0 else 128-done.returncode,done.stdout,done.stderr)
            finally:shutil.rmtree(str(work),ignore_errors=True)
        code,out,err=_CACHE[key];self.stderr.append(err);return code,out


# ---------------------------------------------------------------- the emulated host and the plan a binder would write
def world(k,mode,*,provisioned=False,release=RELEASE,units=False):
    """The host before install_release (PRE) or after it (POST); with provisioned, also what the supervisor's
    provisioning and unit installation leave."""
    host=f.world(k)
    host.docker.compose.base['services']['r2d2-worker']['volumes']=[{'type':'bind','source':hostemu.DATA,'target':DATA_TARGET,'bind':{'create_host_path':True}}]
    host.tree.add(LIVE_PARENT,mode=0o700,dev=hostemu.DATA_DEVICE)
    host.tree.add(PROBE,mode=0o700,dev=hostemu.DATA_DEVICE)
    host.tree.add(PROBE+'/'+RELEASE_FILE,kind='file',mode=0o600,dev=hostemu.DATA_DEVICE,content=b'{"epoch":"an earlier one"}')
    if mode=='POST':install(host,release)
    if provisioned:
        hostemu.provision_supervisor(host)
        host.units['c3po-massive.service']={'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','UnitFileState':'static','FragmentPath':'/etc/systemd/system/c3po-massive.service','TriggeredBy':'c3po-massive.timer'}
        host.units['c3po-massive.timer']={'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','UnitFileState':'disabled','FragmentPath':'/etc/systemd/system/c3po-massive.timer'}
    host.docker.on_run=Container()
    return host
def install(host,release=RELEASE,mode=0o600):
    """What install_release leaves: a private directory in the root of the data volume and the release file in it."""
    host.tree.add(RELEASE_HOST,mode=0o700,dev=hostemu.DATA_DEVICE)
    host.tree.add(RELEASE_HOST+'/'+RELEASE_FILE,kind='file',mode=mode,dev=hostemu.DATA_DEVICE,content=release)

def chain(host,path,open_root,signed=True):
    return {'path':path,'rows':hostemu.rows(host,path) if signed else None,'open_root':open_root}
def fields(host,mode,*,release=RELEASE,policy=POLICY,render=None,override=None,units=(),journal=None,floor=None,docker_config=None,signed_rows=True,
           rows_in_receipt=False,environment=True,lock=True,valid_at=VALID_AT,probe=DEFAULT,live=True,limits=DEFAULT,dry_run=None):
    """The operation's own plan members. Defaults: PRE is the full dry run (render, policy, the probe of the bind on an
    earlier release directory, the live directory, limits); POST carries the policy and the live directory, no render
    and no limits. A PRE fixture that leaves out a member of the full profile is signed as REDUCED, as a binder would."""
    pre=mode=='PRE';render=pre if render is None else render
    probe=(PROBE if pre else None) if probe is DEFAULT else probe;limits=(dict(LIMITS) if pre else None) if limits is DEFAULT else limits
    if dry_run is None and pre:
        dry_run='FULL' if policy is not None and probe is not None and live and limits is not None and environment and docker_config is None else 'REDUCED'
    plan={'mode':mode,'evidence_boot_id_sha256':f.BOOT_SHA,'revision':REVISION,'package_sha256':PACKAGE,
          'image':{'reference':'c3po/backend:production','image_id':hostemu.BACKEND},
          'worker':{'container':hostemu.WORKER,'environment':environment,'data_source':hostemu.DATA,'data_target':DATA_TARGET},
          'release':{'sha256':f.sha(release),'bytes':len(release),'content_b64':b64(release) if pre else None,
                     'parent':chain(host,hostemu.DATA,hostemu.DATA,signed_rows),'directory_name':RELEASE_DIRECTORY,'file_name':RELEASE_FILE,
                     'container_target':None if pre else TARGET,'directory_entries':None if pre else 1},
          'policy':None if policy is None else {'sha256':f.sha(policy),'bytes':len(policy),'content_b64':b64(policy),'valid_at':list(valid_at)},
          'render':None,
          'deploy':{'tree':chain(host,hostemu.DEPLOY,hostemu.DEPLOY,signed_rows),'lock_directory':chain(host,hostemu.LOCK_DIRECTORY,hostemu.DEPLOY,signed_rows),
                    'lock_name':hostemu.LOCK_NAME if lock else None,'version_name':'.deploy-version'},
          'units':[{'name':name,'expected':None} for name in units],
          'journal':None if journal is None else {'path':journal,'floor_bytes':floor},
          'docker_config':docker_config,'rows_in_receipt':rows_in_receipt,
          'bind_probe':None if probe is None else {'directory':chain(host,probe,hostemu.DATA if probe.startswith(hostemu.DATA+'/') else None,signed_rows),
                                                   'file_name':RELEASE_FILE if probe.startswith(hostemu.DATA+'/') else 'epoch.json','container_target':PROBE_TARGET},
          'dry_run':dry_run,'limits':limits,
          'live':{'parent':chain(host,LIVE_PARENT,hostemu.DATA,signed_rows),'directory_name':LIVE_NAME} if live else None}
    if render:
        raw=override_bytes(release,policy if policy is not None else POLICY) if override is None else override
        plan['render']={'project':hostemu.PROJECT,'env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE],'override_b64':b64(raw),
                        'override_sha256':f.sha(raw),'override_bytes':len(raw)}
    return plan

def case(mode='PRE',now=None,provisioned=False,**options):
    """(docs, host): a bound fixture of one mode that completes on a fresh emulated host."""
    k=f.load(DIRECTORY);host=world(k,mode,provisioned=provisioned,release=options.get('release',RELEASE))
    return f.Docs(k,fields(host,mode,**options),now=now),host
def state_of(host):
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)
