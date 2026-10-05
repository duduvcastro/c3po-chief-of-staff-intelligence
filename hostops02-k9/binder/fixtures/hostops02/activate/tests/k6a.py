"""Fixtures of K6a (activate): the emulated host as it must be on the first session day (the release installed by an
earlier operation, the parent of the live directory present, the worker's bind of the data root in the render), and a
request plan built from it exactly as a binder would copy it from a read-only receipt of the same boot. Every byte,
number, ID and value is synthetic: the policy and the release here are never the real ones."""
import base64
import copy
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
EPOCH='R2D2-V2-SHADOW-2026-10-05'
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
ORDER='1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e'
LIVE_PARENT=hostemu.DATA+'/r2d2-v2-live'
LEAF='2026-10-05'
LIVE=LIVE_PARENT+'/'+LEAF
RELEASE_LEAF='r2d2-v2-release-20261005'
RELEASE_DIRECTORY=hostemu.DATA+'/'+RELEASE_LEAF
RELEASE_NAME='release.CERTIFIED.json'
RELEASE=b'{"note":"synthetic bytes, never a release","schema":"SYNTHETIC_RELEASE"}'
TARGET='/app/day-d-data'
POLICY_NAME='policy.json'
OVERRIDE_NAME='compose.override.json'
LOCK=hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME
PENDING='/run/c3po-security/reboot.pending'
KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')
VOLUMES=[{'type':'bind','source':hostemu.DEPLOY+'/runtime/security/maintenance','target':'/run/c3po-maintenance','read_only':True,'bind':{'create_host_path':True}},
         {'type':'bind','source':hostemu.DATA,'target':TARGET,'bind':{'create_host_path':True}},
         {'type':'volume','source':'c3po_capacity_unprovisioned','target':'/c3po-capacity','read_only':True,'volume':{}}]

def b64(raw):return base64.b64encode(raw).decode('ascii')
def policy_object(**changes):
    value={'schema':'R2D2_V2_LIVE_POLICY_V1','mode':'LIVE','epoch':EPOCH,'release_sha':f.sha(RELEASE),'order_sha':ORDER,'package_sha':PACKAGE,
           'code_revision':hostemu.REVISION,'capacity':550,'c8_receipt_sha':'c'*64,'head_go_sha':'d'*64,
           'valid_from':'2026-10-05T00:00:00+00:00','valid_until':'2026-10-10T00:00:00+00:00','automatic_retry':False,'first_session':'2026-10-05'}
    value.update(changes);return {key:item for key,item in value.items() if item is not ...}
def policy_bytes(**changes):return f.canonical(policy_object(**changes))
POLICY=policy_bytes()
def policy_member(raw=POLICY,name=POLICY_NAME):return {'name':name,'content_b64':b64(raw),'sha256':f.sha(raw),'bytes':len(raw)}

def environment(live=LIVE,policy=POLICY,release=RELEASE):
    """The four values, computed here independently of the source."""
    return {KEYS[0]:TARGET+live[len(hostemu.DATA):]+'/'+POLICY_NAME,KEYS[1]:f.sha(policy),
            KEYS[2]:TARGET+'/'+RELEASE_LEAF+'/'+RELEASE_NAME,KEYS[3]:f.sha(release)}
def override(values=None):
    """The bytes of the override, computed here independently of the source: json.dumps with its default separators, keys sorted."""
    import json
    return json.dumps({'services':{'r2d2-worker':{'environment':environment() if values is None else values}}},sort_keys=True).encode()

def prepare(host):
    """What the weekend and the install of the release leave, added to the baseline of hostemu.world()."""
    host.tree.add(LIVE_PARENT,dev=hostemu.DATA_DEVICE,mode=0o755)
    host.tree.add(RELEASE_DIRECTORY,dev=hostemu.DATA_DEVICE,mode=0o700)
    host.tree.add(RELEASE_DIRECTORY+'/'+RELEASE_NAME,kind='file',dev=hostemu.DATA_DEVICE,mode=0o600,content=RELEASE)
    host.docker.compose.base['services']['r2d2-worker']['volumes']=copy.deepcopy(VOLUMES)
    return host
def world(k):return prepare(f.world(k))

def fields(host,policy=POLICY):
    return {'data_root':hostemu.DATA,'live_parent':hostemu.rows(host,LIVE_PARENT),'directory_name':LEAF,'policy':policy_member(policy),
            'override_name':OVERRIDE_NAME,
            'release':{'parent':hostemu.rows(host,hostemu.DATA),'directory_name':RELEASE_LEAF,'file_name':RELEASE_NAME,'sha256':f.sha(RELEASE),'bytes':len(RELEASE)},
            'worker':{'image_id':hostemu.BACKEND,'mount_target':TARGET},
            'compose':{'project':hostemu.PROJECT,'env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE]},
            'deploy_directory':hostemu.rows(host,hostemu.DEPLOY),
            'lock':{'directory':hostemu.rows(host,hostemu.LOCK_DIRECTORY),'wait_seconds':20},
            'evidence_boot_id_sha256':f.BOOT_SHA}

def load():return f.load(DIRECTORY)
def case(now=None,minutes=5):
    """(docs, host): a bound fixture of K6a that completes on a fresh emulated host."""
    k=load();host=world(k);return f.Docs(k,fields(host),now=now,minutes=minutes),host
def fresh(now=None,minutes=5):
    docs,host=case(now,minutes);return docs.k.m,docs,host
def timed(seconds=0.0,now=None,minutes=5):
    """A fixture whose clock moves: every command costs `seconds`, a pause costs itself (family.Budget)."""
    m,docs,host=fresh(now,minutes);budget=f.Budget(docs.now,seconds).attach(host);return m,docs,host,budget
OVERRIDE_FILE=LIVE+'/'+OVERRIDE_NAME
def state_of(host):
    import json
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)
def worker(host):return host.docker.container(hostemu.WORKER)

# ---------------------------------------------------------------- hostile hosts
def replace(host,path,kind,**attributes):
    """Put another object where one is (or was): a symbolic link, a fifo, a file, a directory."""
    if host.tree.get(path) is not None:host.tree.remove(path)
    parent=host.tree.get(path.rsplit('/',1)[0] or '/')
    if parent is not None:attributes.setdefault('dev',parent.dev)
    return host.tree.add(path,kind=kind,**attributes)
def answer(host,match,reply,nth=None):
    """A hostile or changed answer of the docker CLI: for the calls whose arguments match (all of them, or only the
    nth, counted from 1), reply(real) is returned instead, real() being what the emulated engine would have said."""
    original=host.docker.run;count=[0]
    def run(args,stdin=None,environment=None):
        real=lambda:original(args,stdin,environment)
        if match(args):
            count[0]+=1
            if nth is None or count[0]==nth:return reply(real)
        return real()
    host.docker.run=run
def during(host,match,action,nth=1):
    """Something else happens on the host right before the nth docker call whose arguments match."""
    original=host.docker.run;count=[0]
    def run(args,stdin=None,environment=None):
        if match(args):
            count[0]+=1
            if count[0]==nth:action(host)
        return original(args,stdin,environment)
    host.docker.run=run
is_inspect=lambda args:args[:2]==['container','inspect'] and 'RestartCount' in args[3]
is_environment=lambda args:args[:2]==['container','inspect'] and 'RestartCount' not in args[3]
is_image=lambda args:args[:2]==['image','inspect']
is_list=lambda args:args[:1]==['ps']
is_render=lambda args:args[:1]==['compose'] and 'config' in args
is_up=lambda args:args[:1]==['compose'] and 'up' in args

# ---------------------------------------------------------------- what an interrupted recreate leaves on an engine
# `docker compose up --force-recreate` of one service is five calls to the engine, and compose has made them in two
# orders. Either way one container carries, for a while, the name <first 12 hex of the OLD ID>_<name of the service's
# container>. Neither order was ever interrupted on an engine by this family (DESIGN.md section 6; the Linux job
# records which one the runner's compose uses): the states below are what each order leaves when it stops part-way.
#   NEW FIRST (compose v2 as its source reads today): create the new container under the temporary name, stop the
#             old one, remove it, rename the new one, start it.
#   OLD FIRST (compose v1, early v2): stop the old one, rename it to the temporary name, create the new one under the
#             service's name, start it, remove the old one.
def temporary_name(old):return old[:12]+'_'+hostemu.WORKER
def service_container(name,state='created',keys=True):
    """A container of the worker service as a recreate with the override creates it: the signed four names in its
    environment, a new ID, and the state given (`created`: never started)."""
    values=dict(hostemu.service_environment('r2d2-worker'),**(environment() if keys else {}))
    item=hostemu.container(name,hostemu.BACKEND,'c3po/backend:production',['PATH=/usr/local/bin:/usr/bin']+['%s=%s'%pair for pair in sorted(values.items())],
                           project=hostemu.PROJECT,service='r2d2-worker',running=state=='running')
    item['State'].update(Status=state,Running=state=='running');return item
def _stopped(host):worker(host)['State'].update(Status='exited',Running=False)
def _new_first_created(host,old):host.docker.containers.append(service_container(temporary_name(old)))
def _new_first_old_stopped(host,old):_new_first_created(host,old);_stopped(host)
def _new_first_old_removed(host,old):
    _new_first_created(host,old);host.docker.containers=[item for item in host.docker.containers if item['Name']!='/'+hostemu.WORKER]
def _new_first_renamed(host,old):
    _new_first_old_removed(host,old);host.docker.container(temporary_name(old))['Name']='/'+hostemu.WORKER
def _old_first_stopped(host,old):_stopped(host)
def _old_first_renamed(host,old):_stopped(host);worker(host)['Name']='/'+temporary_name(old)
def _old_first_created(host,old):_old_first_renamed(host,old);host.docker.containers.append(service_container(hostemu.WORKER))
def _old_first_started(host,old):_old_first_created(host,old);worker(host)['State'].update(Status='running',Running=True)
INTERRUPTED={'NEW_FIRST_1_NEW_CREATED_UNDER_THE_TEMPORARY_NAME_OLD_RUNNING':_new_first_created,
             'NEW_FIRST_2_OLD_STOPPED':_new_first_old_stopped,
             'NEW_FIRST_3_OLD_REMOVED_NEW_STILL_UNDER_THE_TEMPORARY_NAME':_new_first_old_removed,
             'NEW_FIRST_4_NEW_RENAMED_NOT_STARTED':_new_first_renamed,
             'OLD_FIRST_1_OLD_STOPPED':_old_first_stopped,
             'OLD_FIRST_2_OLD_RENAMED_TO_THE_TEMPORARY_NAME':_old_first_renamed,
             'OLD_FIRST_3_NEW_CREATED_NOT_STARTED':_old_first_created,
             'OLD_FIRST_4_NEW_STARTED_OLD_NOT_REMOVED':_old_first_started}
def interrupt(host,stage,how):
    """The recreate command leaves the engine in that in-between state and ends by a timeout (the process group is
    killed), by a non-zero return, or with the death of the run itself. Returns the ID of the worker before."""
    old=worker(host)['Id'];original=host.docker.run
    def run(args,stdin=None,environment=None):
        if is_up(args):
            INTERRUPTED[stage](host,old)
            if how=='timeout':raise host.refused('COMMAND_TIMEOUT')
            if how=='death':raise hostemu.Death('dead')
            assert how=='nonzero';return 1,b''
        return original(args,stdin,environment)
    host.docker.run=run;return old

# ---------------------------------------------------------------- a directory swapped by name
PROJECT_DIRECTORY=hostemu.DEPLOY+'/'+hostemu.PROJECT
def swap_directory(host,path,content=None):
    """What an account that owns the parent can do to a directory this run holds open: rename it away and put another
    directory, with the same owner and mode and copies of its files, under the name. With content, every file of the
    new directory holds those bytes instead. The descriptor held still shows the old one; the path shows the new one."""
    parent=host.tree.get(path.rsplit('/',1)[0]);leaf=path.rsplit('/',1)[1];old=parent.children.pop(leaf);parent.children[leaf+'.moved-away']=old
    host.tree.add(path,dev=old.dev,uid=old.uid,gid=old.gid,mode=old.mode)
    for name,node in old.children.items():
        if node.kind=='file':host.tree.add(path+'/'+name,kind='file',dev=node.dev,uid=node.uid,gid=node.gid,mode=node.mode,content=bytes(node.content) if content is None else content)
        else:host.tree.add(path+'/'+name,kind=node.kind,dev=node.dev,uid=node.uid,gid=node.gid,mode=node.mode)
    return host.tree.get(path)
def data_volume(host,**members):
    """Other figures of the filesystem of the data volume (what fstatvfs of the live parent answers)."""
    import types
    host.vfs[hostemu.DATA_DEVICE]=types.SimpleNamespace(**dict(vars(host.vfs[hostemu.DATA_DEVICE]),**members))
