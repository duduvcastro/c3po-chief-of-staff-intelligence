"""K6b, every refusal on the host before the first effect: the filesystem, the environment file and the block it
holds, the compose inputs, the override, the capacity tree, the worker, the render, the lock and what changes before
it is held. Each is REFUSED with nothing changed: no effect command was started, the tree and the engine are as they
were, the lock is released, no descriptor is left."""
import json

import pytest

import family as f
import hostemu
import k6b

def refused(mode,prepare=None,state=None,unchanged=True,**run):
    m,docs,host=k6b.fresh(mode,state=state)
    if prepare is not None:prepare(host)
    before=k6b.state_of(host);receipt=docs.run(host,**run)
    assert receipt['status']=='REFUSED' and receipt['outcome']==m.REFUSED_OUTCOME,(receipt['outcome'],receipt['code'])
    assert receipt['phase_reached']=='PRECHECK' and receipt['mutating_calls']['issued']==0 and receipt['failure_phase']=='BEFORE_THE_EDIT'
    assert (k6b.state_of(host)==before or not unchanged) and host.effect_commands()==[] and host.container_runs()==[] and host.mutating()==[]
    assert host.fds=={} and not host.lock_held(k6b.LOCK)
    assert hostemu.SECRET not in json.dumps(receipt)
    return receipt['code']

def content(path,raw):
    def change(host):host.tree.get(path).content=bytearray(raw)
    return change
def attribute(path,**values):
    def change(host):
        node=host.tree.get(path)
        for key,value in values.items():setattr(node,key,value)
    return change
def remove(path):
    def change(host):host.tree.remove(path)
    return change
def env_text(host):return k6b.env_bytes(host).decode()
def env_lines(*extra,head=True):
    def change(host):
        base=k6b.base_env(host).decode() if head else ''
        host.tree.get(hostemu.ENV_FILE).content=bytearray((base+''.join(line+'\n' for line in extra)).encode())
    return change

CASES=[
    # ---- the boot, the deploy tree
    ('EVIDENCE_FROM_EARLIER_BOOT','MOUNT',content('/proc/sys/kernel/random/boot_id',b'1f8fad5b-d9cb-469f-a165-70867728950e\n')),
    ('DEPLOY_VERSION_MISMATCH','MOUNT',content(hostemu.DEPLOY+'/.deploy-version',b'0'*40+b'\n')),
    ('DEPLOY_VERSION_ABSENT','ENABLE',remove(hostemu.DEPLOY+'/.deploy-version')),
    ('PARENT_IDENTITY_MISMATCH','MOUNT',attribute(hostemu.DEPLOY,ino=9999)),
    # ---- the environment file and its block
    ('ENV_FILE_ABSENT','MOUNT',remove(hostemu.ENV_FILE)),
    ('ENV_FILE_NOT_REGULAR','MOUNT',lambda host:k6b.replace(host,hostemu.ENV_FILE,'symlink',uid=1000,gid=1000)),
    ('ENV_FILE_NOT_REGULAR','DISABLE_FAST',lambda host:k6b.replace(host,hostemu.ENV_FILE,'fifo',uid=1000,gid=1000,mode=0o600)),
    ('ENV_FILE_NOT_EDITABLE_BY_THE_EDITOR','MOUNT',attribute(hostemu.ENV_FILE,uid=0)),
    ('ENV_FILE_NOT_EDITABLE_BY_THE_EDITOR','ENABLE',attribute(hostemu.ENV_FILE,gid=0)),
    ('ENV_FILE_NOT_EDITABLE_BY_THE_EDITOR','DISABLE_FAST',attribute(hostemu.ENV_FILE,mode=0o640)),
    ('ENV_FILE_NOT_EDITABLE_BY_THE_EDITOR','DISABLE_FULL',attribute(hostemu.ENV_FILE,nlink=2)),
    ('ENV_FILE_NOT_NEWLINE_TERMINATED','MOUNT',lambda host:content(hostemu.ENV_FILE,k6b.env_bytes(host)[:-1])(host)),
    ('ENV_CAPACITY_LINES_NOT_TRAILING','ENABLE',lambda host:content(hostemu.ENV_FILE,(k6b.MOUNT_LINE+'\n').encode()+k6b.base_env(host))(host)),
    ('ENV_CAPACITY_LINES_NOT_TRAILING','DISABLE_FULL',env_lines(*k6b.BLOCK,'C3PO_LATER=appended-after')),
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','ENABLE',env_lines()),                                   # no mount line: enable before mount
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','MOUNT',env_lines(k6b.MOUNT_LINE)),                       # mounted already
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','MOUNT',env_lines('  export C3PO_R2D2_V2_CAPACITY_REQUIRED=true')),
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','ENABLE',env_lines('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=/var/lib/other')),
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','ENABLE',env_lines(k6b.MOUNT_LINE,k6b.BLOCK[4])),         # the flag without the settings
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','DISABLE_FAST',env_lines(*k6b.BLOCK[:4])),               # fast disable done already
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','DISABLE_FAST',env_lines(*(k6b.BLOCK[:2]+['C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='+'1'*64]+k6b.BLOCK[3:]))),
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','DISABLE_FULL',env_lines()),                             # nothing to disable
    ('ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','DISABLE_FULL',env_lines(*k6b.BLOCK[:2])),
    # ---- the compose inputs and the override
    ('COMPOSE_FILE_ABSENT','MOUNT',remove(hostemu.COMPOSE_FILE)),
    ('COMPOSE_FILE_NOT_REGULAR','MOUNT',lambda host:k6b.replace(host,hostemu.COMPOSE_FILE,'symlink',uid=1000,gid=1000)),
    ('COMPOSE_DIRECTORY_NOT_A_DIRECTORY','MOUNT',lambda host:(host.tree.remove(hostemu.DEPLOY+'/c3po'),host.tree.add(hostemu.DEPLOY+'/c3po',kind='file',uid=1000,gid=1000))),
    ('OVERRIDE_ABSENT','MOUNT',remove(k6b.OVERRIDE_FILE)),
    ('OVERRIDE_NOT_AS_DELIVERED','MOUNT',content(k6b.OVERRIDE_FILE,k6b.override_bytes(dict(k6b.ACTIVATION,**{k6b.KEYS[1]:'4'*64})))),
    ('OVERRIDE_NOT_AS_DELIVERED','ENABLE',content(k6b.OVERRIDE_FILE,k6b.override_bytes()+b'\n')),
    ('OVERRIDE_NOT_AS_DELIVERED','MOUNT',attribute(k6b.OVERRIDE_FILE,nlink=2)),
    ('OVERRIDE_NOT_AS_DELIVERED','MOUNT',lambda host:k6b.replace(host,k6b.OVERRIDE_FILE,'fifo',mode=0o600)),
    ('PARENT_IDENTITY_MISMATCH','ENABLE',attribute(k6b.LIVE,ino=7777)),
    # ---- the capacity tree (read by MOUNT and ENABLE only)
    ('CAPACITY_TREE_INCOMPLETE','MOUNT',remove(k6b.CAPACITY+'/go')),
    ('CAPACITY_TREE_NOT_PRIVATE','MOUNT',attribute(k6b.CAPACITY+'/documents',mode=0o750)),
    ('CAPACITY_TREE_NOT_PRIVATE','ENABLE',attribute(k6b.CAPACITY+'/payload',uid=1000)),
    ('CAPACITY_TREE_NOT_PRIVATE','MOUNT',attribute(k6b.CAPACITY+'/config',dev=811)),
    ('CAPACITY_TREE_NOT_PRIVATE','MOUNT',lambda host:k6b.replace(host,k6b.CAPACITY+'/documents','symlink')),
    ('CAPACITY_CONFIG_ABSENT','MOUNT',remove(k6b.CAPACITY+'/config/'+k6b.CONFIG_NAME)),
    ('CAPACITY_CONFIG_NOT_PRIVATE','ENABLE',attribute(k6b.CAPACITY+'/config/'+k6b.CONFIG_NAME,mode=0o640)),
    ('CAPACITY_CONFIG_NOT_PRIVATE','ENABLE',attribute(k6b.CAPACITY+'/config/'+k6b.CONFIG_NAME,nlink=2)),
    ('CAPACITY_CONFIG_NOT_PRIVATE','MOUNT',lambda host:k6b.replace(host,k6b.CAPACITY+'/config/'+k6b.CONFIG_NAME,'symlink')),
    ('CAPACITY_CONFIG_HASH_MISMATCH','ENABLE',content(k6b.CAPACITY+'/config/'+k6b.CONFIG_NAME,b'{"other":1}')),
    ('PARENT_IDENTITY_MISMATCH','MOUNT',attribute(k6b.CAPACITY,ino=31337)),
    ('PARENT_MISSING','ENABLE',remove(k6b.CAPACITY)),
    # ---- the lock file
    ('LOCK_FILE_ABSENT','MOUNT',remove(k6b.LOCK)),
    # ---- the security reboot marker
    ('SECURITY_REBOOT_PENDING','MOUNT',lambda host:host.tree.add(k6b.PENDING,kind='file',mode=0o644)),
    ('SECURITY_REBOOT_PENDING','DISABLE_FAST',lambda host:host.tree.add(k6b.PENDING,kind='file',mode=0o644)),
]

@pytest.mark.parametrize('code,mode,prepare',CASES)
def test_refused_on_the_host(code,mode,prepare):
    assert refused(mode,prepare)==code

@pytest.mark.parametrize('mode',('DISABLE_FAST','DISABLE_FULL'))
def test_a_disable_does_not_read_the_tree(mode):
    m,docs,host=k6b.fresh(mode);host.tree.remove(k6b.CAPACITY);receipt=docs.run(host)
    assert receipt['outcome']==m.COMPLETE_OUTCOME and not any(entry[1:2]==(k6b.CAPACITY,) for entry in host.log)

def test_a_commented_capacity_line_is_not_a_setting():
    m,docs,host=k6b.fresh('MOUNT');k6b.env_lines=None
    node=host.tree.get(hostemu.ENV_FILE);node.content=bytearray(k6b.base_env(host)+b'# C3PO_R2D2_V2_CAPACITY_REQUIRED=true\n')
    receipt=docs.run(host);assert receipt['outcome']==m.COMPLETE_OUTCOME
    assert k6b.env_bytes(host).endswith(b'# C3PO_R2D2_V2_CAPACITY_REQUIRED=true\n'+(k6b.MOUNT_LINE+'\n').encode())

# ---------------------------------------------------------------- the worker, its image, its environment, its mounts
def stopped(host):k6b.worker(host)['State'].update(Status='exited',Running=False)
def other_image(host):k6b.worker(host)['Image']='sha256:'+'ab'*32
def label(host):
    for image in host.docker.images:
        if image['Id']==hostemu.BACKEND:image['Config']['Labels']['org.opencontainers.image.revision']='0'*40
def env_add(name,value):
    def change(host):k6b.worker(host)['Config']['Env'].append('%s=%s'%(name,value))
    return change
def env_drop(name):
    def change(host):
        worker=k6b.worker(host);worker['Config']['Env']=[item for item in worker['Config']['Env'] if not item.startswith(name+'=')]
    return change
def mount(**changes):
    def change(host):
        for item in k6b.worker(host)['Mounts']:
            if item['Destination']=='/c3po-capacity':item.update(changes)
    return change
def data_mount(**changes):
    def change(host):
        for item in k6b.worker(host)['Mounts']:
            if item['Destination']=='/app/day-d-data':item.update(changes)
    return change

WORKER=[
    ('WORKER_IMAGE_NOT_THE_SIGNED_ONE','MOUNT',other_image),
    ('IMAGE_REVISION_MISMATCH','MOUNT',label),
    ('WORKER_NOT_RUNNING','MOUNT',stopped),
    ('WORKER_NOT_RUNNING','ENABLE',stopped),
    ('WORKER_ENVIRONMENT_NOT_AS_FOUND_IN_THE_FILE','MOUNT',env_add('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE',k6b.CAPACITY)),
    ('WORKER_ENVIRONMENT_NOT_AS_FOUND_IN_THE_FILE','ENABLE',env_drop('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE')),
    ('WORKER_ENVIRONMENT_NOT_AS_FOUND_IN_THE_FILE','ENABLE',env_drop(k6b.KEYS[2])),
    ('WORKER_ENVIRONMENT_NOT_AS_FOUND_IN_THE_FILE','MOUNT',env_drop('C3PO_BUILD_SHA')),
    ('WORKER_ENVIRONMENT_NOT_AS_FOUND_IN_THE_FILE','ENABLE',env_add('C3PO_R2D2_V2_CAPACITY_REQUIRED','true')),
    ('WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE','MOUNT',mount(Type='bind',Source=k6b.CAPACITY)),
    ('WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE','ENABLE',mount(RW=True)),
    ('WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE','ENABLE',mount(Source='/var/lib/other')),
    ('WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE','MOUNT',mount(Name='other_volume')),
    ('WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE','MOUNT',data_mount(Source='/mnt/other')),
    ('WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE','ENABLE',data_mount(RW=False)),
    ('WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE','MOUNT',lambda host:k6b.worker(host)['Mounts'].append(dict(k6b.worker(host)['Mounts'][-1]))),
    ('WORKER_MOUNTS_NOT_AS_FOUND_IN_THE_FILE','MOUNT',lambda host:k6b.worker(host).update(Mounts=[m for m in k6b.worker(host)['Mounts'] if m['Destination']!='/app/day-d-data'])),
]

@pytest.mark.parametrize('code,mode,prepare',WORKER)
def test_the_worker_as_found(code,mode,prepare):
    assert refused(mode,prepare)==code

@pytest.mark.parametrize('mode',('DISABLE_FAST','DISABLE_FULL'))
def test_a_disable_reports_but_does_not_judge_the_worker_as_found(mode):
    m,docs,host=k6b.fresh(mode);env_drop('C3PO_R2D2_V2_CAPACITY_REQUIRED')(host);mount(RW=True)(host);stopped(host)
    receipt=docs.run(host);assert receipt['outcome']==m.COMPLETE_OUTCOME,receipt['code']
    p=receipt['precheck'];assert (p['worker_running'],p['worker_environment_as_found'],p['worker_mounts_as_found'])==(False,False,False)

def test_the_worker_absent_or_unreadable():
    def gone(host):host.docker.containers=[item for item in host.docker.containers if item['Name']!='/'+hostemu.WORKER]
    assert refused('DISABLE_FAST',gone)=='COMMAND_FAILED'
    assert refused('MOUNT',lambda host:k6b.answer(host,k6b.is_mounts,lambda real:(0,b'{"not":"a list"}\n')))=='MOUNTS_METADATA_INVALID'
    assert refused('MOUNT',lambda host:k6b.answer(host,k6b.is_mounts,lambda real:(0,b'[{"Destination":1}]\n')))=='MOUNTS_METADATA_INVALID'
    assert refused('MOUNT',lambda host:k6b.answer(host,k6b.is_mounts,lambda real:(0,b'not json\n')))=='MOUNTS_METADATA_INVALID'
    assert refused('MOUNT',lambda host:k6b.answer(host,k6b.is_mounts,lambda real:(0,('['+','.join(['{"Destination":"/x","Type":"bind","RW":true}']*33)+']\n').encode())))=='MOUNTS_METADATA_INVALID'
    assert refused('MOUNT',lambda host:k6b.answer(host,k6b.is_mounts,lambda real:(1,b'')))=='COMMAND_FAILED'
    assert refused('MOUNT',lambda host:k6b.answer(host,k6b.is_environment,lambda real:(0,b'{}\n')))=='ENVIRONMENT_METADATA_INVALID'
    assert refused('MOUNT',lambda host:k6b.answer(host,k6b.is_image,lambda real:(1,b''),nth=1))=='IMAGE_ABSENT_OR_UNREADABLE'

# ---------------------------------------------------------------- the render
def rendered(change):
    """A render that compose answers otherwise than the files say: change(object) applied to the real answer."""
    def prepare(host):
        def reply(real):
            code,out=real();value=json.loads(out);change(value);return code,json.dumps(value).encode()+b'\n'
        k6b.answer(host,k6b.is_render,reply,nth=1)
    return prepare
def worker_service(value):return value['services']['r2d2-worker']
def capacity_volume(value):return [item for item in worker_service(value)['volumes'] if item['target']=='/c3po-capacity'][0]

RENDER=[
    ('RENDER_BUILD_REVISION','MOUNT',lambda value:worker_service(value)['environment'].update(C3PO_BUILD_SHA='development')),
    ('RENDER_ACTIVATION_ENVIRONMENT_MISMATCH','MOUNT',lambda value:worker_service(value)['environment'].pop(k6b.KEYS[0])),
    ('RENDER_ACTIVATION_ENVIRONMENT_MISMATCH','ENABLE',lambda value:worker_service(value)['environment'].update({k6b.KEYS[3]:'0'*64})),
    ('RENDER_CAPACITY_ENVIRONMENT_MISMATCH','MOUNT',lambda value:worker_service(value)['environment'].update(C3PO_R2D2_V2_CAPACITY_VETO_MODE='CONTINUOUS')),
    ('RENDER_CAPACITY_ENVIRONMENT_MISMATCH','ENABLE',lambda value:worker_service(value)['environment'].pop('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE')),
    ('RENDER_CAPACITY_ENVIRONMENT_MISMATCH','DISABLE_FAST',lambda value:worker_service(value)['environment'].update(C3PO_R2D2_V2_CAPACITY_REQUIRED='false')),
    ('RENDER_IMAGE_INVALID','MOUNT',lambda value:worker_service(value).update(image='-x')),
    ('RENDER_VOLUMES_INVALID','MOUNT',lambda value:worker_service(value).update(volumes='x')),
    ('RENDER_VOLUMES_INVALID','MOUNT',lambda value:worker_service(value)['volumes'].append({'target':''})),
    ('WORKER_DATA_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:[item.update(source='/mnt/other') for item in worker_service(value)['volumes'] if item['target']=='/app/day-d-data']),
    ('WORKER_DATA_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:[item.update(read_only=True) for item in worker_service(value)['volumes'] if item['target']=='/app/day-d-data']),
    ('WORKER_DATA_MOUNT_NOT_AS_SIGNED','ENABLE',lambda value:[item.update(type='volume') for item in worker_service(value)['volumes'] if item['target']=='/app/day-d-data']),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:capacity_volume(value).update(read_only=False)),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:capacity_volume(value).update(type='bind',source=k6b.CAPACITY)),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','ENABLE',lambda value:capacity_volume(value).update(source='/var/lib/other')),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:value['volumes'].pop('c3po_capacity_unprovisioned')),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:value['volumes'].update(c3po_capacity_unprovisioned={'name':'other'})),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','ENABLE',lambda value:value.update(volumes={'c3po_capacity_unprovisioned':{'name':'other'}})),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:value.update(volumes=['x'])),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:value.update(name='other')),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:value['services']['api'].update(volumes=[{'type':'bind','source':'/x','target':'/c3po-capacity','read_only':True}])),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:value['services']['api'].update(volumes=['short:form'])),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:worker_service(value)['volumes'].append({'type':'bind','source':'/x','target':'/extra'})),
    ('RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:value['services'].update(broken='not a mapping')),
    ('COMPOSE_SERVICE_INVALID','MOUNT',lambda value:value['services'].pop('r2d2-worker')),
]

@pytest.mark.parametrize('code,mode,change',RENDER)
def test_the_render_as_the_file_says(code,mode,change):
    assert refused(mode,rendered(change))==code

def test_the_render_image():
    def unresolved(host):
        k6b.answer(host,lambda args:k6b.is_image(args) and args[-1]=='c3po/backend:production',lambda real:(1,b''))
    assert refused('MOUNT',unresolved)=='RENDER_IMAGE_UNRESOLVED'
    def moved(host):
        for image in host.docker.images:
            if 'c3po/backend:production' in image['RepoTags']:image['RepoTags'].remove('c3po/backend:production')
        for image in host.docker.images:
            if image['Id']==hostemu.OTHER:image['RepoTags'].append('c3po/backend:production')
    assert refused('MOUNT',moved)=='RENDER_IMAGE_CHANGED'
    def failing(host):host.docker.compose.config_returncode=1
    assert refused('MOUNT',failing)=='COMMAND_FAILED'

# ---------------------------------------------------------------- the lock, and what changes before it is held
def at_lock(action):
    """Something else happens on the host while this run asks for the lock (at its first flock call)."""
    def prepare(host):
        done=[False]
        def hook(host,name,detail,calls):
            if name=='flock' and not done[0]:done[0]=True;action(host)
        host.hook=hook
    return prepare

def test_the_lock_held_by_someone_else():
    assert refused('MOUNT',lambda host:host.lock_holder.update({k6b.LOCK:'EX'}))=='DEPLOY_LOCK_BUSY'

UNDER_LOCK=[
    ('ENV_FILE_CHANGED_BEFORE_THE_LOCK','MOUNT',lambda host:host.tree.get(hostemu.ENV_FILE).content.extend(b'C3PO_NEW=1\n')),
    ('ENV_FILE_CHANGED_BEFORE_THE_LOCK','DISABLE_FAST',attribute(hostemu.ENV_FILE,mtime=99)),
    ('COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK','MOUNT',lambda host:host.tree.get(hostemu.COMPOSE_FILE).content.extend(b'# deploy\n')),
    ('OVERRIDE_CHANGED_BEFORE_THE_LOCK','ENABLE',attribute(k6b.OVERRIDE_FILE,ctime=99)),
    ('DEPLOY_VERSION_MISMATCH','MOUNT',content(hostemu.DEPLOY+'/.deploy-version',b'1'*40+b'\n')),
    ('WORKER_CHANGED_BEFORE_THE_LOCK','MOUNT',lambda host:k6b.worker(host).update(RestartCount=1)),
    ('WORKER_CHANGED_BEFORE_THE_LOCK','ENABLE',stopped),
    ('WORKER_CHANGED_BEFORE_THE_LOCK','DISABLE_FAST',lambda host:k6b.worker(host).update(Id=hostemu.synthetic_id('another'))),
    ('WORKER_SERVICE_LEFTOVER_CONTAINER','MOUNT',lambda host:host.docker.containers.append(hostemu.container('0123456789ab_'+hostemu.WORKER,hostemu.BACKEND,'c3po/backend:production',[],running=False))),
    ('CONTAINER_LIST_INCONSISTENT','MOUNT',lambda host:k6b.answer(host,k6b.is_list,lambda real:(0,b''))),
    ('SECURITY_REBOOT_PENDING','ENABLE',lambda host:host.tree.add(k6b.PENDING,kind='file',mode=0o644)),
    ('DEPLOY_TREE_REPLACED','MOUNT',lambda host:k6b.swap_directory(host,hostemu.DEPLOY+'/c3po') if hasattr(k6b,'swap_directory') else attribute(hostemu.DEPLOY+'/c3po',ino=4242)(host)),
    ('OVERRIDE_DIRECTORY_REPLACED','MOUNT',attribute(k6b.LIVE,ino=4343)),
    ('LOCK_DIRECTORY_REPLACED','MOUNT',attribute(hostemu.LOCK_DIRECTORY,ino=4444)),
    ('CAPACITY_ROOT_REPLACED','ENABLE',attribute(k6b.CAPACITY,ino=4545)),
]

@pytest.mark.parametrize('code,mode,action',UNDER_LOCK)
def test_what_changes_while_the_lock_is_asked_for(code,mode,action):
    assert refused(mode,at_lock(action),unchanged=False)==code

def test_the_budget_before_the_first_effect():
    m,docs,host,budget=k6b.timed(0.0)
    budget.cost(6,'compose','config')                     # a first render of 6 s: allowance 13, needed 59, kept 61
    receipt=docs.run(host,**budget.options())
    assert receipt['status']=='REFUSED' and receipt['code']=='BUDGET_CANNOT_HOLD_BOTH_EFFECTS' and host.effect_commands()==[]
    m,docs,host,budget=k6b.timed(0.0)
    budget.cost(2,'container','inspect');budget.cost(2,'image','inspect')       # slow reads before the lock
    receipt=docs.run(host,**budget.options())
    assert receipt['status']=='REFUSED' and receipt['code']=='LOCK_NOT_TAKEN_BUDGET' and host.effect_commands()==[]


DISABLE_FINDINGS=[
    ('OVERRIDE_NOT_AS_DELIVERED','DISABLE_FAST',attribute(k6b.OVERRIDE_FILE,mode=0o644)),
    ('OVERRIDE_NOT_AS_DELIVERED','DISABLE_FULL',attribute(k6b.OVERRIDE_FILE,uid=1000)),
    ('WORKER_IMAGE_NOT_THE_SIGNED_ONE','DISABLE_FULL',other_image),
    ('IMAGE_REVISION_MISMATCH','DISABLE_FAST',label),
    ('DEPLOY_VERSION_MISMATCH','DISABLE_FULL',content(hostemu.DEPLOY+'/.deploy-version',b'0'*40+b'\n')),
    ('DEPLOY_VERSION_ABSENT','DISABLE_FAST',remove(hostemu.DEPLOY+'/.deploy-version')),
]

@pytest.mark.parametrize('code,mode,prepare',DISABLE_FINDINGS)
def test_a_disable_reports_what_a_mount_or_an_enable_refuses_on(code,mode,prepare):
    """The README's restart loops (a rotated release sha, an image with another package): a disable must still run."""
    m,docs,host=k6b.fresh(mode);prepare(host);receipt=docs.run(host)
    assert receipt['outcome']==m.COMPLETE_OUTCOME and code in receipt['precheck']['findings'],(receipt['code'],receipt['precheck'].get('findings'))
    assert k6b.env_bytes(host)==k6b.expected_env(host,k6b.AFTER[mode])
    assert refused('MOUNT' if code!='WORKER_IMAGE_NOT_THE_SIGNED_ONE' else 'ENABLE',prepare)==code

def test_a_disable_still_refuses_on_its_own_inputs():
    assert refused('DISABLE_FAST',lambda host:k6b.answer(host,k6b.is_image,lambda real:(1,b''),nth=1))=='IMAGE_ABSENT_OR_UNREADABLE'
    assert refused('DISABLE_FULL',env_lines(*k6b.BLOCK[:2]))=='ENV_CAPACITY_BLOCK_NOT_AS_SIGNED'

def retag(host):
    for image in host.docker.images:
        if 'c3po/backend:production' in (image.get('RepoTags') or []):image['RepoTags'].remove('c3po/backend:production')
    [other]=[item for item in host.docker.images if item['Id']==hostemu.OTHER];other['RepoTags'].append('c3po/backend:production')

def test_a_tag_moved_while_the_lock_is_waited_for():
    """Review finding 1: the render's image reference is resolved again under the lock."""
    assert refused('MOUNT',at_lock(retag),unchanged=False)=='RENDER_IMAGE_CHANGED_BEFORE_THE_LOCK'
    assert refused('DISABLE_FAST',at_lock(retag),unchanged=False)=='RENDER_IMAGE_CHANGED_BEFORE_THE_LOCK'
    def unresolved(host):
        for image in host.docker.images:
            if 'c3po/backend:production' in (image.get('RepoTags') or []):image['RepoTags'].remove('c3po/backend:production')
    assert refused('MOUNT',at_lock(unresolved),unchanged=False)=='RENDER_IMAGE_UNRESOLVED'

def test_the_capacity_config_read_again_under_the_lock():
    assert refused('ENABLE',at_lock(content(k6b.CAPACITY+'/config/'+k6b.CONFIG_NAME,b'{"replaced":1}')),unchanged=False)=='CAPACITY_CONFIG_HASH_MISMATCH'

def test_the_editor_s_name_is_free():
    def taken(host):
        def name(h):pass
        host.docker.containers.append(hostemu.container('hostops02-k6b-PLACEHOLDER',hostemu.BACKEND,'c3po/backend:production',[]))
    m,docs,host=k6b.fresh('MOUNT');host.docker.containers.append(hostemu.container('hostops02-k6b-'+docs.go16(),hostemu.BACKEND,'c3po/backend:production',[],running=False))
    before=k6b.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','EDITOR_NAME_TAKEN') and k6b.state_of(host)==before
    m,docs,host=k6b.fresh('MOUNT');host.docker.containers.append(hostemu.container('hostops02-k6b-'+docs.go16()+'-withdraw',hostemu.BACKEND,'c3po/backend:production',[],running=False))
    receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED','EDITOR_NAME_TAKEN')

def test_the_deploy_tree_proved_right_before_the_editor():
    """Review finding 2: the editor binds .env by its path; the path must lead to the tree read, right before it."""
    m,docs,host=k6b.fresh('MOUNT')
    k6b.during(host,k6b.is_list,lambda h:setattr(h.tree.get(hostemu.DEPLOY+'/c3po'),'ino',6161))
    receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED','DEPLOY_TREE_REPLACED') and host.container_runs()==[]

# ---------------------------------------------------------------- what the mutation list asked for, one case each
def test_cases_the_mutation_list_asked_for():
    assert refused('MOUNT',lambda host:k6b.replace(host,hostemu.DEPLOY+'/.deploy-version','fifo',uid=1000,gid=1000,mode=0o644))=='DEPLOY_VERSION_NOT_REGULAR'
    assert refused('MOUNT',lambda host:k6b.replace(host,hostemu.DEPLOY+'/.deploy-version','dir',uid=1000,gid=1000))=='DEPLOY_VERSION_NOT_REGULAR'
    assert refused('ENABLE',lambda host:k6b.replace(host,k6b.CAPACITY+'/config/'+k6b.CONFIG_NAME,'fifo',mode=0o600))=='CAPACITY_CONFIG_NOT_PRIVATE'
    assert refused('MOUNT',lambda host:k6b.replace(host,k6b.CAPACITY+'/go','file',mode=0o700))=='CAPACITY_TREE_NOT_PRIVATE'
    assert refused('MOUNT',lambda host:k6b.answer(host,k6b.is_mounts,lambda real:(0,b'{}\n')))=='MOUNTS_METADATA_INVALID'
    def marker_behind_a_link(host):host.tree.add('/run',mode=0o755);host.tree.add('/run/c3po-security',kind='symlink',mode=0o777)
    assert refused('MOUNT',marker_behind_a_link)=='REBOOT_STATE_UNAVAILABLE'
    def same_size(host):
        node=host.tree.get(hostemu.ENV_FILE);node.content[0:1]=b'D'                  # same size, same instants: only the bytes tell
    assert refused('MOUNT',at_lock(same_size),unchanged=False)=='ENV_FILE_CHANGED_BEFORE_THE_LOCK'

RENDER_MORE=[
    ('RENDER_IMAGE_INVALID','MOUNT',lambda value:worker_service(value).update(image='C3PO/Backend Production')),
    ('RENDER_VOLUMES_INVALID','MOUNT',lambda value:worker_service(value).update(volumes={})),
    ('RENDER_VOLUMES_INVALID','MOUNT',lambda value:worker_service(value)['volumes'].extend([{'type':'bind','source':'/x%d'%i,'target':'/t%d'%i} for i in range(62)])),
    ('WORKER_DATA_MOUNT_NOT_AS_SIGNED','MOUNT',lambda value:worker_service(value)['volumes'].append(dict([item for item in worker_service(value)['volumes'] if item['target']=='/app/day-d-data'][0]))),
]
@pytest.mark.parametrize('code,mode,change',RENDER_MORE)
def test_the_render_more(code,mode,change):
    assert refused(mode,rendered(change))==code


def test_more_cases_the_mutation_list_asked_for():
    def wrong_value(host):
        worker=k6b.worker(host);worker['Config']['Env']=[item if not item.startswith('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=') else 'C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE=/var/lib/other'
                                                         for item in worker['Config']['Env']]
    assert refused('ENABLE',wrong_value)=='WORKER_ENVIRONMENT_NOT_AS_FOUND_IN_THE_FILE'
    def api_too(value):value['services']['api']['volumes']=[dict(capacity_volume(value))]
    assert refused('MOUNT',rendered(api_too))=='RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED'
    assert refused('MOUNT',rendered(lambda value:capacity_volume(value).update(source='other_volume')))=='RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED'
    assert refused('MOUNT',at_lock(lambda host:k6b.replace(host,k6b.LOCK,'file',uid=1000,gid=1000,mode=0o644)),unchanged=False)=='LOCK_FILE_REPLACED'

def test_a_looping_worker_that_restarts_while_the_lock_is_waited_for_is_disabled():
    for mode in ('DISABLE_FAST','DISABLE_FULL'):
        m,docs,host=k6b.fresh(mode);worker=k6b.worker(host);worker['State'].update(Status='restarting',Running=False,Restarting=True)
        at_lock(lambda host:k6b.worker(host).update(RestartCount=k6b.worker(host)['RestartCount']+1))(host)
        receipt=docs.run(host);assert receipt['outcome']==m.COMPLETE_OUTCOME,receipt['code']


def test_an_executor_that_is_not_root_touches_nothing_not_even_the_umask():
    for actor in ((0,1000),(1000,0),(501,20)):
        m,docs,host=k6b.fresh('MOUNT');host.actor=actor;receipt=docs.run(host)
        assert receipt['code']=='EXECUTOR_IDENTITY' and not [entry for entry in host.log if entry[0]=='umask']


def test_the_process_is_made_non_dumpable_first():
    """As the token program (core section 14): before the deploy tree or .env is opened; refused otherwise, nothing opened."""
    m,docs,host=k6b.fresh('MOUNT');host.dumpable_refused=True;before=k6b.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','PROCESS_DUMPABLE_NOT_DISABLED') and k6b.state_of(host)==before
    assert receipt['process']=={'dumpable_disabled':False} and not [entry for entry in host.log if entry[0] in ('open','lstat','read','run')]
    m,docs,host=k6b.fresh('ENABLE');receipt=docs.run(host)
    assert receipt['process']=={'dumpable_disabled':True} and host.dumpable==0
    names=[entry[0] for entry in host.log];assert names.index('not_dumpable')<names.index('open')
