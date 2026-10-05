"""Fixtures of the capacity probe: the emulated host as the epoch leaves it before each step (the capacity tree that
once-e2-20261003-b provisioned under /var/lib, the static config of B5 in its config directory, the worker with the
read-only bind of B4), the plan a binder copies from read-only receipts, and a model of the three containers.

The model containers are written here, independently of the source: they read the bound tree through the emulated
binds (call.stat, call.read), compute the AnchoredRoot identities with the release's digest algorithm (sha256 of the
compact sorted JSON of [[part, device, inode], ...]), and print the line each pinned script prints.
tests/test_scripts.py runs the real scripts and compares their lines with these models."""
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
ROOT='/var/lib/c3po-capacity'
CHILDREN=('config','documents','go','payload')
CONFIG_NAME='week.static.capacity.json'
CONFIG_PATH='/c3po-capacity/config/'+CONFIG_NAME
CONFIG=b'{"schema":"R2D2_CAPACITY_BOOTSTRAP_V3","synthetic":"a static config of the tests, never authoritative"}\n'
CONFIG_SHA=hashlib.sha256(CONFIG).hexdigest()
RELEASE_SHA=hashlib.sha256(b'synthetic release file of the tests').hexdigest()
MOUNT_RECEIPT=hashlib.sha256(b'synthetic receipt of the mount (K6b) of the tests').hexdigest()
EPOCH='R2D2-V2-SHADOW-2026-10-05'
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
ORDER='1a5253bf23f5006224b79527da06697646c34c6f5a3a4f820af5da2b13d7a118'
PIN=hashlib.sha256(b'synthetic calendar pin of the tests').hexdigest()
NOW={'CALENDAR':datetime(2026,10,4,17,0,tzinfo=timezone.utc),'IDENT':datetime(2026,10,4,17,0,tzinfo=timezone.utc),
     'LOAD':datetime(2026,10,5,21,0,tzinfo=timezone.utc)}

def K():return f.load(DIRECTORY)
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()

def provision(host,root=ROOT):
    """The tree of once-e2-20261003-b: the root and its four children root:root 0700, and B5's static config 0600."""
    host.tree.add(root,mode=0o700)
    for name in CHILDREN:host.tree.add(root+'/'+name,mode=0o700)
    host.tree.add(root+'/config/'+CONFIG_NAME,kind='file',mode=0o600,content=CONFIG)
    return host
def worker(host):return host.docker.container(hostemu.WORKER)
def mount(source=ROOT,destination='/c3po-capacity',kind='bind',rw=False):
    return {'Type':kind,'Name':'','Source':source,'Destination':destination,'Driver':'','Mode':'' if rw else 'ro','RW':rw,'Propagation':'rprivate'}
def bind_worker(host,mounts=None):
    """B4: the worker recreated with the bind; the data volume's bind stays beside it."""
    worker(host)['Mounts']=[mount(hostemu.DATA,'/app/day-d-data',rw=True),mount()] if mounts is None else mounts
    return host
WORKER_SETTINGS=['C3PO_R2D2_V2_SHADOW_RELEASE_SHA='+RELEASE_SHA,'C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE='+ROOT]
def world(step='LOAD'):
    """The host before a step: the tree, B5's config, the worker recreated by B4 with the bind and the mount source of
    K6b's block, the release pin of K6a's activation (no capacity setting yet: the flag is a later step)."""
    k=K();host=f.world(k);provision(host);bind_worker(host);worker(host)['Config']['Env'].extend(WORKER_SETTINGS)
    host.docker.on_run=container;return k,host
def fields(step,host=None,**changes):
    if host is None:_,host=world(step)
    out={'step':step,'image_id':hostemu.BACKEND,'image_revision':hostemu.REVISION,'evidence_boot_id_sha256':f.BOOT_SHA,
         'capacity':None if step=='CALENDAR' else {'root_path':ROOT,'parent_rows':hostemu.rows(host,str(Path(ROOT).parent))},
         'load':None if step!='LOAD' else {'config_file':CONFIG_PATH,'config_sha256':CONFIG_SHA,'release_sha':RELEASE_SHA,'mount_receipt_sha256':MOUNT_RECEIPT}}
    out.update(changes);return out
def case(step,now=None,**changes):
    """(docs, host): a bound fixture of one step that completes on a fresh emulated host."""
    k,host=world(step);return f.Docs(k,fields(step,host,**changes),now=now or NOW[step]),host


# ---------------------------------------------------------------- the model containers
def compact(row):return (json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode()
def calendar_line(**changes):
    row={'status':'CALENDAR_PIN','epoch':EPOCH,'calendar_version':'4.13.2','calendar_pin_sha':PIN,'package_sha':PACKAGE,'document_order_sha':ORDER}
    row.update(changes);return row
def calendar_bytes(row):return (json.dumps(row,sort_keys=True)+'\n').encode()          # the script prints with the default separators
def identity_in(call,name):
    """What AnchoredRoot computes inside the container for /c3po-capacity/<name>, through the emulated bind."""
    top,child=call.stat('/c3po-capacity'),call.stat('/c3po-capacity/'+name)
    return digest([['c3po-capacity',top.st_dev,top.st_ino],[name,child.st_dev,child.st_ino]])
def host_identity(host,name,root=ROOT):
    top,child=host.tree.get(root),host.tree.get(root+'/'+name)
    return digest([['c3po-capacity',top.dev,top.ino],[name,child.dev,child.ino]])
def ident_line(call):
    for name in CHILDREN:
        node=call.stat('/c3po-capacity/'+name)
        if (node.st_uid,node.st_mode&0o077)!=(0,0):return {'status':'ROOT_IDENTITIES_REFUSED','code':'ROOT_NOT_PRIVATE'}
    return {'status':'ROOT_IDENTITIES','identities':{name:identity_in(call,name) for name in CHILDREN}}
LOAD_TAIL=re.compile(rb"run\(json\.loads\('([^'\\]*)'\)\)\n\Z")
def load_values(stdin):
    match=LOAD_TAIL.search(stdin);assert match,'the LOAD script ends with one line of the signed values';return json.loads(match.group(1))
def load_line(call):
    values=load_values(call.stdin)
    try:raw=call.read(values['config_file'])
    except FileNotFoundError:return {'status':'CAPACITY_STARTUP_REFUSED','code':'FileNotFoundError'}
    if hashlib.sha256(raw).hexdigest()!=values['config_sha256']:return {'status':'CAPACITY_STARTUP_REFUSED','code':'CAPACITY_CONFIG_HASH'}
    if values['release_sha']!=RELEASE_SHA:return {'status':'CAPACITY_STARTUP_REFUSED','code':'CAPACITY_CONFIG_RELEASE'}
    roots=['documents','go','payload']
    return {'status':'CAPACITY_STARTUP_OK','roots':roots,'veto_mode':'DISPATCH_AND_DERIVATION_ONLY',
            'identities':{name:identity_in(call,name) for name in roots},'config_sha256':hashlib.sha256(raw).hexdigest()}
def step_of(call):
    m=K().m;scripts=m.scripts()
    if call.stdin==scripts['CALENDAR']:return 'CALENDAR'
    if call.stdin==scripts['IDENT']:return 'IDENT'
    assert call.stdin.startswith(scripts['LOAD']) and call.stdin.count(b'\n')==scripts['LOAD'].count(b'\n')+1,'only the three pinned scripts'
    return 'LOAD'

def assert_run(call,image=hostemu.BACKEND):
    """What the engine was asked for is a run of the core's argv: the image by ID, python -I -B -, no variable, a name
    of this family, and for IDENT and LOAD exactly one read-only bind of the root at /c3po-capacity."""
    step=step_of(call)
    assert call.flags==['--rm','-i','--init','--read-only'] and call.network=='none' and call.read_only_root
    assert call.options=={'--pull':['never'],'--user':['0:0'],'--network':['none'],'--cap-drop':['ALL'],'--security-opt':['no-new-privileges'],
                          '--name':[call.name]}
    assert call.environment=={} and call.image==image and call.command==['python','-I','-B','-']
    assert call.name.startswith('hostops02-probe-'+step.lower()+'-')
    if step=='CALENDAR':assert call.mounts==[]
    else:assert call.mounts==[{'source':ROOT,'target':'/c3po-capacity','read_only':True}]
    return step

def container(call):
    """The emulated container of a correct run of any step."""
    step=assert_run(call)
    if step=='CALENDAR':return 0,calendar_bytes(calendar_line())
    row=ident_line(call) if step=='IDENT' else load_line(call)
    return (0 if row['status'] in ('ROOT_IDENTITIES','CAPACITY_STARTUP_OK') else 1),compact(row)
def answers(returncode=None,output=None,before=None,lines=None):
    """An on_run that checks the run and answers: the model (default), the given bytes, or the n-th of `lines`."""
    seen=[]
    def on_run(call):
        assert_run(call);seen.append(call)
        if before is not None:before(call)
        code,out=container(call)
        if lines is not None:out=lines[len(seen)-1]
        if output is not None:out=output
        return (code if returncode is None else returncode),out
    return on_run


def app_python():
    """An interpreter that has the release's requirements (pydantic_settings, exchange_calendars): HOSTOPS02_TEST_APP_PYTHON,
    or the test environment night23-test-venv found in a directory above this one; None otherwise."""
    if os.environ.get('HOSTOPS02_TEST_APP_PYTHON'):return Path(os.environ['HOSTOPS02_TEST_APP_PYTHON'])
    for parent in HERE.parents:
        candidate=parent/'night23-test-venv'/'bin'/'python'
        if candidate.is_file():return candidate
    return None


# ---------------------------------------------------------------- the release, when a tree of it is at hand
RELEASE='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
RELEASE_FILES={'c3po/backend/app/r2d2_v2_capacity_anchored.py':None,'c3po/backend/app/r2d2_v2_store.py':None,
               'c3po/backend/app/r2d2_v2_capacity_bootstrap.py':None,'c3po/backend/app/config.py':None,
               'c3po/backend/app/r2d2_v2_epoch_assembler.py':None}
def release_tree():
    """A directory that holds c3po/backend/app of the release (dd4ec4bb), or None. Looked for in
    HOSTOPS02_TEST_RELEASE_TREE, then in the scratch export the author used. The files are pinned by hash in
    tests/test_static_pins.py."""
    candidates=[Path(os.environ['HOSTOPS02_TEST_RELEASE_TREE'])] if os.environ.get('HOSTOPS02_TEST_RELEASE_TREE') else []
    candidates.append(DIRECTORY/'work'/'release')
    for candidate in candidates:
        if all((candidate/name).is_file() for name in RELEASE_FILES):return candidate.resolve()
    return None
