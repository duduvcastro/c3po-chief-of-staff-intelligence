"""What each failure after the precheck leaves, and what the receipt says about it. From the first creation on nothing
refuses unless nothing has changed: a run that left anything is PARTIAL, with one of three outcomes that say whether
the worker was touched, and with the facts read after the recreate. The lock is released and no descriptor is left
in every case."""
import errno
import json

import pytest

import family as f
import hostemu
import k6a

OBJECTS='PARTIAL_OBJECTS_LEFT_WORKER_NOT_RECREATED'
NOT_VERIFIED='PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED'
UNCERTAIN='PARTIAL_RECREATE_UNCERTAIN_REQUIRES_READBACK'

def fail_at(name,number=1,error=errno.EIO,then=None):
    """The nth host call of that name raises an OS error (or, with then, something else happens right before it)."""
    count=[0]
    def hook(host,event,detail,calls):
        if event==name:
            count[0]+=1
            if count[0]==number:
                if then is not None:then(host)
                else:raise OSError(error,'injected')
    return hook
def run(prepare):
    m,docs,host=k6a.fresh();worker=k6a.worker(host)['Id'];prepare(host);receipt=docs.run(host)
    assert host.lock_held(k6a.LOCK) is None and host.fds=={} and host.locks=={} and f.sealed(receipt),'the lock is released and every descriptor closed'
    assert hostemu.SECRET not in json.dumps(receipt) and len(f.line(receipt))<=m.RECEIPT_LIMIT
    return m,docs,host,receipt,worker
def untouched(host,receipt,worker):
    """The worker is the container it was, and the receipt says so."""
    assert k6a.worker(host)['Id']==worker and receipt['worker_container_replaced'] is False and receipt['pre_existing_objects_modified'] is False
    assert not [entry for entry in host.log if entry[0]=='compose-recreate']

# ---------------------------------------------------------------- the first creation: a clean failure is still a refusal
@pytest.mark.parametrize('error,code',[(errno.EROFS,'FILESYSTEM_READ_ONLY'),(errno.ENOSPC,'FILESYSTEM_FULL'),(errno.EDQUOT,'FILESYSTEM_FULL'),
                                        (errno.EACCES,'FILESYSTEM_ACCESS_DENIED'),(errno.EPERM,'FILESYSTEM_ACCESS_DENIED'),(errno.EIO,'FILESYSTEM_ERROR')])
def test_first_creation_that_fails_changes_nothing_and_is_a_refusal(error,code):
    def prepare(host):host.hook=fail_at('mkdir',error=error)
    m,docs,host=k6a.fresh();prepare(host);before=k6a.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,'EFFECTS')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0} and receipt['directories'][0]['state']=='NOT_CREATED'
    assert k6a.state_of(host)==before and [entry[0] for entry in host.mutating()]==['mkdir'] and receipt['objects_left_by_this_run']==0,'one creating call, refused by the kernel'
    assert host.lock_held(k6a.LOCK) is None and host.fds=={}
    assert [row['state'] for row in receipt['ledger']]==['NOT_ATTEMPTED']*2 and receipt['recreate']['state']=='NOT_STARTED'

def test_destination_that_appears_after_the_precheck_is_left_alone_and_the_run_is_a_refusal():
    def appears(host):host.tree.add(k6a.LIVE,dev=hostemu.DATA_DEVICE,mode=0o755,uid=1000)
    m,docs,host,receipt,worker=run(lambda host:setattr(host,'hook',fail_at('mkdir',then=appears)))
    assert (receipt['status'],receipt['code'])==('REFUSED','DESTINATION_APPEARED_AFTER_PRECHECK') and receipt['objects_left_by_this_run']==0
    node=host.tree.get(k6a.LIVE);assert (node.uid,node.mode,dict(node.children))==(1000,0o755,{}),'what appeared is not touched'
    untouched(host,receipt,worker)

# ---------------------------------------------------------------- the directory and the two files
def group(host):host.creator=(0,5)
def device(host):host.created_device=hostemu.ROOT_DEVICE
DIRECTORY=[('created with another group',group,'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH'),('created on another device',device,'CREATED_METADATA_MISMATCH','CREATED_METADATA_MISMATCH'),
           ('not durable',lambda host:setattr(host,'hook',fail_at('fsync')),'FSYNC_FAILED','CREATED_NOT_DURABLE'),
           ('cannot be opened after the mkdir',lambda host:setattr(host,'hook',fail_at('open',1,then=None) if False else after_mkdir_open_fails()),'CREATED_OPEN_FAILED','CREATED_UNVERIFIED')]
def after_mkdir_open_fails():
    seen=[]
    def hook(host,event,detail,calls):
        if event=='mkdir':seen.append(1)
        elif event=='open' and seen and detail[0]==k6a.LIVE:raise OSError(errno.EIO,'injected')
    return hook
@pytest.mark.parametrize('label,prepare,code,state',DIRECTORY,ids=[case[0] for case in DIRECTORY])
def test_directory_that_exists_and_is_not_as_required_stops_the_run_before_any_file(label,prepare,code,state):
    m,docs,host,receipt,worker=run(prepare)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,OBJECTS,code) and receipt['directories'][0]['state']==state
    assert [row['state'] for row in receipt['ledger']]==['NOT_ATTEMPTED']*2 and receipt['objects_left_by_this_run']==1 and receipt['recreate']['state']=='NOT_STARTED'
    assert host.tree.get(k6a.LIVE) is not None and dict(host.tree.get(k6a.LIVE).children)=={} and not [entry for entry in host.commands if entry['argv'][-3:]==['config','--format','json'] and k6a.OVERRIDE_FILE in entry['argv']]
    untouched(host,receipt,worker)

def altered(name):
    def change(host):host.tree.get(k6a.LIVE+'/'+name).content=bytearray(b'{"altered":true}')
    return change
def foreign(host):host.tree.add(k6a.LIVE+'/foreign',kind='file',dev=hostemu.DATA_DEVICE)
def moved_parent(host):host.tree.get(k6a.LIVE_PARENT).ino=9500
FILES=[
    # label, prepare, code, states of the two rows, objects left
    ('policy: temporary cannot be created',lambda host:setattr(host,'hook',fail_at('create',1,errno.ENOSPC)),'FILESYSTEM_FULL',('NOT_CREATED','NOT_ATTEMPTED'),1),
    ('policy: write fails, temporary withdrawn',lambda host:setattr(host,'hook',fail_at('write',1,errno.ENOSPC)),'FILESYSTEM_FULL',('NOT_CREATED','NOT_ATTEMPTED'),1),
    ('policy: fsync fails, temporary withdrawn',lambda host:setattr(host,'hook',fail_at('fsync',3)),'FSYNC_FAILED',('NOT_CREATED','NOT_ATTEMPTED'),1),
    ('policy: created with another group, temporary withdrawn',lambda host:setattr(host,'hook',fail_at('create',1,then=group)),'CREATED_METADATA_MISMATCH',('NOT_CREATED','NOT_ATTEMPTED'),1),
    ('policy: link fails, temporary withdrawn',lambda host:setattr(host,'hook',fail_at('link',1,errno.EIO)),'FILESYSTEM_ERROR',('NOT_CREATED','NOT_ATTEMPTED'),1),
    ('policy: the temporary cannot be removed after the link',lambda host:setattr(host,'hook',fail_at('unlink',1)),'TEMPORARY_REMOVAL_FAILED',('LINKED_TEMPORARY_PRESENT','NOT_ATTEMPTED'),3),
    ('policy: the directory cannot be synced after the link',lambda host:setattr(host,'hook',fail_at('fsync',4)),'FSYNC_FAILED',('LINKED_TEMPORARY_PRESENT','NOT_ATTEMPTED'),3),
    ('policy: the directory cannot be synced after the removal of the temporary',lambda host:setattr(host,'hook',fail_at('fsync',5)),'FSYNC_FAILED',('INSTALLED_NOT_DURABLE','NOT_ATTEMPTED'),2),
    ('override: the directory cannot be synced after the link',lambda host:setattr(host,'hook',fail_at('fsync',7)),'FSYNC_FAILED',('INSTALLED_DURABLE','LINKED_TEMPORARY_PRESENT'),4),
    ('override: the directory cannot be synced after the removal of the temporary',lambda host:setattr(host,'hook',fail_at('fsync',8)),'FSYNC_FAILED',('INSTALLED_DURABLE','INSTALLED_NOT_DURABLE'),3),
    ('override: temporary cannot be created',lambda host:setattr(host,'hook',fail_at('create',2,errno.EDQUOT)),'FILESYSTEM_FULL',('INSTALLED_DURABLE','NOT_CREATED'),2),
    ('override: write fails, temporary withdrawn',lambda host:setattr(host,'hook',fail_at('write',2,errno.EIO)),'FILESYSTEM_ERROR',('INSTALLED_DURABLE','NOT_CREATED'),2),
    ('override: link fails, temporary withdrawn',lambda host:setattr(host,'hook',fail_at('link',2,errno.EIO)),'FILESYSTEM_ERROR',('INSTALLED_DURABLE','NOT_CREATED'),2),
    ('override: the temporary cannot be removed after the link',lambda host:setattr(host,'hook',fail_at('unlink',2)),'TEMPORARY_REMOVAL_FAILED',('INSTALLED_DURABLE','LINKED_TEMPORARY_PRESENT'),4),
    ('policy bytes altered right after the delivery',lambda host:setattr(host,'hook',fail_at('unlink',2,then=altered('policy.json'))),'READBACK_HASH_MISMATCH',('INSTALLED_DURABLE','INSTALLED_DURABLE'),3),
    ('override bytes altered right after the delivery',lambda host:setattr(host,'hook',fail_at('unlink',2,then=altered('compose.override.json'))),'READBACK_HASH_MISMATCH',('INSTALLED_DURABLE','INSTALLED_DURABLE'),3),
    ('a foreign entry appears in the directory',lambda host:setattr(host,'hook',fail_at('unlink',2,then=foreign)),'READBACK_MISMATCH',('INSTALLED_DURABLE','INSTALLED_DURABLE'),3),
    ('the parent is replaced while the files are written',lambda host:setattr(host,'hook',fail_at('create',2,then=moved_parent)),'PARENT_REPLACED',('INSTALLED_DURABLE','TEMPORARY_ONLY'),3),
]
@pytest.mark.parametrize('label,prepare,code,states,left',FILES,ids=[case[0] for case in FILES])
def test_file_that_is_not_delivered_or_not_as_signed_stops_the_run_before_the_recreate(label,prepare,code,states,left):
    m,docs,host,receipt,worker=run(prepare)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(m.PARTIAL_STATUS,OBJECTS,code,'EFFECTS'),receipt['code']
    assert tuple(row['state'] for row in receipt['ledger'])==states and receipt['objects_left_by_this_run']==left and receipt['directories'][0]['state']=='CREATED_DURABLE'
    assert receipt['recreate']['state']=='NOT_STARTED' and receipt['commands_started']['EFFECT']==0 and receipt['readback'] is None
    assert not [entry for entry in host.commands if k6a.OVERRIDE_FILE in entry['argv']],'neither the render from the files nor the recreate is started'
    untouched(host,receipt,worker)

# ---------------------------------------------------------------- between the files and the recreate, under the lock
def second_render(reply):return lambda host:k6a.answer(host,k6a.is_render,reply,nth=2)
def changed_render(change):
    def reply(real):
        code,out=real();rendered=json.loads(out);change(rendered['services']['r2d2-worker']);return code,json.dumps(rendered).encode()
    return reply
def second_render_hangs(host,event,detail,calls):
    if event=='run' and 'config' in detail[0] and k6a.OVERRIDE_FILE in detail[0]:host.hang.add(('compose','config'))
def replace_lock(host):
    host.tree.remove(k6a.LOCK);host.tree.add(k6a.LOCK,kind='file',uid=1000,gid=1000,mode=0o644)
def swaps(path,**how):return lambda host:k6a.during(host,k6a.is_render,lambda host:k6a.swap_directory(host,path,**how),nth=2)
BEFORE_UP=[
    # while the render from the files runs (the last command before the recreate), a directory this run holds is swapped by name
    ('the release directory is swapped by name before the recreate',swaps(k6a.RELEASE_DIRECTORY,content=b'{"other":"bytes"}'),'RELEASE_DIRECTORY_REPLACED',0),
    ('the project directory is swapped by name before the recreate',swaps(k6a.PROJECT_DIRECTORY),'DEPLOY_TREE_REPLACED',0),
    ('the lock directory is swapped by name before the recreate',swaps(hostemu.LOCK_DIRECTORY),'LOCK_DIRECTORY_REPLACED',0),
    ('the render from the files fails',second_render(lambda real:(14,b'')),'COMMAND_FAILED',0),
    ('the render from the files is not JSON',second_render(lambda real:(0,b'yaml: line 1')),'COMPOSE_RENDER_INVALID',0),
    ('the render from the files hangs',lambda host:setattr(host,'hook',second_render_hangs),'COMMAND_TIMEOUT',0),
    ('the render from the files lost a value',second_render(changed_render(lambda service:service['environment'].pop(k6a.KEYS[3]))),'RENDER_ENVIRONMENT_MISMATCH',0),
    ('the render from the files has another build revision',second_render(changed_render(lambda service:service['environment'].update(C3PO_BUILD_SHA='development'))),'RENDER_BUILD_REVISION',0),
    ('the render from the files names another image',second_render(changed_render(lambda service:service.update(image='c3po/backend:rollback'))),'RENDER_IMAGE_CHANGED',0),
    ('the render from the files lost the bind',second_render(changed_render(lambda service:service.update(volumes=[]))),'WORKER_MOUNT_NOT_AS_SIGNED',0),
    ('the lock file was replaced while the files were written',lambda host:setattr(host,'hook',fail_at('unlink',2,then=replace_lock)),'LOCK_FILE_REPLACED',0),
    ('compose cannot be started for the recreate',lambda host:host.absent.add(('compose','up')),'COMMAND_NOT_STARTED',1),
]
@pytest.mark.parametrize('label,prepare,code,failed',BEFORE_UP,ids=[case[0] for case in BEFORE_UP])
def test_recreate_that_is_not_started_leaves_the_files_and_an_untouched_worker(label,prepare,code,failed):
    m,docs,host,receipt,worker=run(prepare)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,OBJECTS,code),receipt['code']
    assert receipt['recreate']['state']=='NOT_STARTED' and receipt['recreate']['started'] is False and receipt['recreate']['facts'] is None
    assert receipt['mutating_calls']=={'issued':9+failed,'succeeded':9,'failed_nothing_changed':failed,'uncertain':0} and receipt['objects_left_by_this_run']==3
    assert sorted(host.tree.get(k6a.LIVE).children)==['compose.override.json','policy.json'] and [row['state'] for row in receipt['ledger']]==['INSTALLED_DURABLE']*2
    untouched(host,receipt,worker)

# ---------------------------------------------------------------- the recreate itself
def test_recreate_that_compose_refuses_with_the_worker_proved_unchanged():
    def refuses(host):host.docker.compose.up_returncode=1;host.docker.compose.up_effect=False
    m,docs,host,receipt,worker=run(refuses);facts=receipt['recreate']['facts']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,OBJECTS,'RECREATE_FAILED_CONTAINER_UNCHANGED')
    assert (receipt['recreate']['state'],receipt['recreate']['returned'],receipt['recreate']['returncode'])==('NOT_RECREATED',True,1)
    assert receipt['mutating_calls']=={'issued':10,'succeeded':9,'failed_nothing_changed':1,'uncertain':0},'a read proved that nothing changed'
    assert (facts['worker_is_new'],facts['old_container_gone'],facts['others_unchanged'],facts['environment_as_signed'])==(False,False,True,False)
    untouched(host,receipt,worker)
    # the same when compose says 0 and did nothing
    m,docs,host,receipt,worker=run(lambda host:setattr(host.docker.compose,'up_effect',False))
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,OBJECTS,'RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED','NOT_RECREATED')
    untouched(host,receipt,worker)

def test_recreate_that_compose_refuses_is_never_called_unchanged_when_the_worker_is_not_proved_so():
    """Compose says no, and the worker restarted, stopped, or cannot be read: the call is uncertain, not failed."""
    def refuses(change):
        def prepare(host):
            host.docker.compose.up_returncode=1;host.docker.compose.up_effect=False
            k6a.during(host,k6a.is_inspect,change,nth=3)                   # right before the first reading after the command
        return prepare
    def restarted(host):k6a.worker(host)['State']['StartedAt']='2026-10-05T08:51:00.000000000Z'
    def stopped(host):k6a.worker(host)['State'].update(Status='exited',Running=False)
    def unreadable(host):host.docker.inspect_returncode=1
    def another(host):host.docker.containers.pop(0)
    def counted(host):k6a.worker(host)['RestartCount']+=1
    def paused(host):k6a.worker(host)['State'].update(Status='paused')
    def flag(host):k6a.worker(host)['State'].update(Running=False)
    for change,code,state in ((restarted,'RECREATE_RETURNED_NONZERO','UNCERTAIN'),(stopped,'RECREATE_RETURNED_NONZERO','UNCERTAIN'),(counted,'RECREATE_RETURNED_NONZERO','UNCERTAIN'),
                              (paused,'RECREATE_RETURNED_NONZERO','UNCERTAIN'),(flag,'RECREATE_RETURNED_NONZERO','UNCERTAIN'),
                              (unreadable,'RECREATE_RETURNED_NONZERO','UNCERTAIN'),(another,'RECREATE_RETURNED_NONZERO','UNCERTAIN')):
        m,docs,host,receipt,worker=run(refuses(change))
        assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,UNCERTAIN,code,state),change.__name__
        assert receipt['mutating_calls']=={'issued':10,'succeeded':9,'failed_nothing_changed':0,'uncertain':1} and receipt['worker_container_replaced'] is None
        assert receipt['pre_existing_objects_modified'] is True,'not known to be untouched'

def test_recreate_that_returned_0_and_left_the_old_container_restarted_says_not_recreated():
    def prepare(host):
        host.docker.compose.up_effect=False
        k6a.during(host,k6a.is_inspect,lambda host:k6a.worker(host)['State'].update(StartedAt='2026-10-05T08:51:00.000000000Z'),nth=3)
    m,docs,host,receipt,worker=run(prepare)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,UNCERTAIN,'WORKER_NOT_RECREATED','UNCERTAIN')
    assert receipt['recreate']['facts']['worker_is_new'] is False and receipt['worker_container_replaced'] is None

def test_recreate_call_is_settled_in_every_case_so_nothing_stays_pending():
    for prepare,counts in ((lambda host:None,(10,0,0)),(lambda host:setattr(host.docker.compose,'up_returncode',1),(9,0,1)),
                           (lambda host:(setattr(host.docker.compose,'up_returncode',1),setattr(host.docker.compose,'up_effect',False)),(9,1,0)),
                           (lambda host:host.hang.add(('compose','up')),(9,0,1)),(lambda host:host.absent.add(('compose','up')),(9,1,0))):
        m,docs,host=k6a.fresh();prepare(host);state=m.Effects();docs.perform(host,state=state)
        assert state.pending is False and (state.succeeded,state.failed,state.uncertain())==counts

def test_listing_after_the_recreate_must_show_the_name_once_and_with_the_inspected_id():
    def after(change):
        def reply(real):
            code,out=real();rows=[json.loads(line) for line in out.splitlines()];rows=change(rows) or rows
            return code,b''.join(json.dumps(row).encode()+b'\n' for row in rows)
        return lambda host:k6a.answer(host,k6a.is_list,reply,nth=2)
    def twice(rows):return rows+[dict(row,id='e'*64) for row in rows if row['name']==hostemu.WORKER]
    def other_id(rows):
        for row in rows:
            if row['name']==hostemu.WORKER:row['id']='f'*64
    for change in (twice,other_id):
        m,docs,host,receipt,worker=run(after(change))
        assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,NOT_VERIFIED,'WORKER_NOT_FOUND_AFTER_RECREATE'),change.__name__
        assert receipt['recreate']['facts']['worker_listed_once'] is False and receipt['recreate']['facts']['worker_is_new'] is True
    # the inspect fails and the listing shows the name twice: nothing says which container is the worker
    def blind(host):
        after(twice)(host);host.docker.compose.after_up=lambda compose,new:setattr(compose.docker,'inspect_returncode',1)
    m,docs,host,receipt,worker=run(blind);facts=receipt['recreate']['facts']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,UNCERTAIN,'WORKER_NOT_FOUND_AFTER_RECREATE')
    assert (facts['worker_listed_once'],facts['worker_is_new'],receipt['worker_container_replaced'])==(False,None,None)

def test_recreate_that_happened_although_compose_says_it_failed():
    m,docs,host,receipt,worker=run(lambda host:setattr(host.docker.compose,'up_returncode',1))
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,NOT_VERIFIED,'RECREATE_RETURNED_NONZERO')
    assert receipt['recreate']['state']=='RECREATED_NOT_VERIFIED' and receipt['worker_container_replaced'] is True and k6a.worker(host)['Id']!=worker
    assert receipt['mutating_calls']['uncertain']==1 and receipt['recreate']['facts']['second_check_passed'] is True

def test_recreate_that_times_out_is_uncertain_whatever_the_readback_shows():
    # killed before it did anything: the worker is the old one, and the run still does not say "nothing changed"
    m,docs,host,receipt,worker=run(lambda host:host.hang.add(('compose','up')))
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,UNCERTAIN,'COMMAND_TIMEOUT')
    assert (receipt['recreate']['state'],receipt['recreate']['started'],receipt['recreate']['returned'])==('UNCERTAIN',True,False)
    assert receipt['recreate']['facts']['worker_is_new'] is False and receipt['worker_container_replaced'] is None and k6a.worker(host)['Id']==worker
    assert receipt['mutating_calls']=={'issued':10,'succeeded':9,'failed_nothing_changed':0,'uncertain':1}
    # killed after the engine had replaced the container: recreated, every fact read, and still not complete
    m,docs,host,receipt,worker=run(lambda host:host.hang_after.add(('compose','up')));facts=receipt['recreate']['facts']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,NOT_VERIFIED,'COMMAND_TIMEOUT')
    assert receipt['recreate']['state']=='RECREATED_NOT_VERIFIED' and receipt['worker_container_replaced'] is True and k6a.worker(host)['Id']!=worker
    assert all(facts[key] is True for key in ('worker_is_new','old_container_gone','running','environment_as_signed','others_unchanged','second_check_passed'))

def env_of(new,change):
    values=dict(item.split('=',1) for item in new['Config']['Env']);change(values);new['Config']['Env']=['%s=%s'%pair for pair in values.items()]
def loops(compose,new):new['RestartCount']=3;new['State'].update(Status='restarting',Running=True)
def restarted_once(compose,new):new['RestartCount']=1
def exited(compose,new):new['State'].update(Status='exited',Running=False)
def other_value(compose,new):env_of(new,lambda values:values.update({k6a.KEYS[1]:'6'*64}))
def lost_value(compose,new):env_of(new,lambda values:values.pop(k6a.KEYS[2]))
def other_build(compose,new):env_of(new,lambda values:values.update(C3PO_BUILD_SHA='development'))
def other_image(compose,new):new['Image']=hostemu.OTHER
def removes_another(compose,new):compose.docker.containers.pop(0)
def recreates_another(compose,new):compose.docker.containers[0]['Id']='a'*64
def renames_another(compose,new):compose.docker.containers[0]['Name']='/c3po-api-2'
def adds_another(compose,new):compose.docker.containers.append(hostemu.container('stray',hostemu.BACKEND,'c3po/backend:production',[]))
def leaves_the_old_one(old):
    def after_up(compose,new):
        compose.docker.containers.append(dict(hostemu.container('left',hostemu.BACKEND,'c3po/backend:production',[]),Id=old,Name='/'+old[:12]+'_'+hostemu.WORKER))
    return after_up
def removes_the_worker(compose,new):compose.docker.containers.remove(new)
def edits_env_file(compose,new):compose.docker.host.tree.get(hostemu.ENV_FILE).mtime+=1
def alters_policy(compose,new):compose.docker.host.tree.get(k6a.LIVE+'/policy.json').content=bytearray(b'{}')
def removes_override(compose,new):compose.docker.host.tree.remove(k6a.OVERRIDE_FILE)
def chmods_directory(compose,new):compose.docker.host.tree.get(k6a.LIVE).mode=0o755
def replaces_lock(compose,new):replace_lock(compose.docker.host)
def touches_compose(compose,new):compose.docker.host.tree.get(hostemu.COMPOSE_FILE).mtime+=1
def edits_compose(compose,new):
    node=compose.docker.host.tree.get(hostemu.COMPOSE_FILE);node.content=bytearray(bytes(node.content).replace(b'{}',b'[]'))
def copies_release(compose,new):k6a.replace(compose.docker.host,k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME,'file',mode=0o600,content=k6a.RELEASE)
def swaps_release(compose,new):k6a.swap_directory(compose.docker.host,k6a.RELEASE_DIRECTORY,content=b'{"other":"bytes"}')
def swaps_release_for_a_copy(compose,new):k6a.swap_directory(compose.docker.host,k6a.RELEASE_DIRECTORY)
def swaps_project(compose,new):k6a.swap_directory(compose.docker.host,k6a.PROJECT_DIRECTORY)
def swaps_lock_directory(compose,new):k6a.swap_directory(compose.docker.host,hostemu.LOCK_DIRECTORY)
AFTER_UP=[
    ('the new worker restarts in a loop',loops,'WORKER_NOT_RUNNING_AFTER_RECREATE','RECREATED_NOT_VERIFIED','running',False),
    ('the new worker exited',exited,'WORKER_NOT_RUNNING_AFTER_RECREATE','RECREATED_NOT_VERIFIED','running',False),
    ('the new worker counted one restart',restarted_once,'WORKER_RESTARTED_AFTER_RECREATE','RECREATED_NOT_VERIFIED','restarts',1),
    ('the new worker runs another image',other_image,'WORKER_IMAGE_CHANGED','RECREATED_NOT_VERIFIED','image_is_the_signed_one',False),
    ('a signed name has another value',other_value,'ENVIRONMENT_NOT_AS_SIGNED','RECREATED_NOT_VERIFIED','environment_as_signed',False),
    ('a signed name is absent',lost_value,'ENVIRONMENT_NOT_AS_SIGNED','RECREATED_NOT_VERIFIED','environment_as_signed',False),
    ('the build revision is another',other_build,'ENVIRONMENT_NOT_AS_SIGNED','RECREATED_NOT_VERIFIED','environment_as_signed',False),
    ('another container is gone',removes_another,'OTHER_CONTAINERS_CHANGED','RECREATED_NOT_VERIFIED','others_unchanged',False),
    ('another container was recreated too',recreates_another,'OTHER_CONTAINERS_CHANGED','RECREATED_NOT_VERIFIED','others_unchanged',False),
    ('another container was renamed',renames_another,'OTHER_CONTAINERS_CHANGED','RECREATED_NOT_VERIFIED','others_unchanged',False),
    ('a container appeared',adds_another,'OTHER_CONTAINERS_CHANGED','RECREATED_NOT_VERIFIED','others_unchanged',False),
    ('the environment file changed during the recreate',edits_env_file,'ENV_FILE_CHANGED','RECREATED_NOT_VERIFIED','env_file_unchanged',False),
    ('the policy was altered during the recreate',alters_policy,'FILES_NOT_AS_DELIVERED','RECREATED_NOT_VERIFIED','files_as_delivered',False),
    ('the override was removed during the recreate',removes_override,'FILES_NOT_AS_DELIVERED','RECREATED_NOT_VERIFIED','files_as_delivered',False),
    ('the directory was opened to others during the recreate',chmods_directory,'FILES_NOT_AS_DELIVERED','RECREATED_NOT_VERIFIED','files_as_delivered',False),
    ('the lock file was replaced during the recreate',replaces_lock,'LOCK_FILE_REPLACED','RECREATED_NOT_VERIFIED','lock_still_named',False),
    ('the lock directory was swapped by name during the recreate',swaps_lock_directory,'LOCK_FILE_REPLACED','RECREATED_NOT_VERIFIED','lock_still_named',False),
    ('the compose file was written again during the recreate',touches_compose,'COMPOSE_FILE_CHANGED','RECREATED_NOT_VERIFIED','compose_file_unchanged',False),
    ('the compose file was edited in place during the recreate',edits_compose,'COMPOSE_FILE_CHANGED','RECREATED_NOT_VERIFIED','compose_file_unchanged',False),
    ('the project directory was swapped by name during the recreate',swaps_project,'COMPOSE_FILE_CHANGED','RECREATED_NOT_VERIFIED','compose_file_unchanged',False),
    ('the release was replaced by a copy during the recreate',copies_release,'RELEASE_CHANGED','RECREATED_NOT_VERIFIED','release_unchanged',False),
    ('the release directory was swapped by name for other bytes during the recreate',swaps_release,'RELEASE_CHANGED','RECREATED_NOT_VERIFIED','release_unchanged',False),
    ('the release directory was swapped by name for a copy during the recreate',swaps_release_for_a_copy,'RELEASE_CHANGED','RECREATED_NOT_VERIFIED','release_unchanged',False),
]
@pytest.mark.parametrize('label,after_up,code,state,fact,value',AFTER_UP,ids=[case[0] for case in AFTER_UP])
def test_recreate_that_returned_0_and_one_criterion_is_not_met(label,after_up,code,state,fact,value):
    m,docs,host,receipt,worker=run(lambda host:setattr(host.docker.compose,'after_up',after_up))
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,NOT_VERIFIED,code),receipt['code']
    assert receipt['recreate']['state']==state and receipt['recreate']['facts'][fact]==value and receipt['readback'] is None
    assert receipt['worker_container_replaced'] is True and receipt['mutating_calls']=={'issued':10,'succeeded':9,'failed_nothing_changed':0,'uncertain':1}
    implied={'running':('second_check_passed',),'restarts':('second_check_passed',)}.get(fact,())      # the second reading asks for the same two things
    others=[key for key,item in receipt['recreate']['facts'].items() if item is False and key not in (fact,'others_states_unchanged')+implied]
    assert others==[],'only the criterion that was broken says so: %r'%others

def test_what_changed_among_the_other_containers_is_said_in_numbers():
    """others_unchanged alone does not tell an unrelated container that came or went from a service of the project
    that was recreated. The three counts do, by name; none of them decides."""
    for after_up,counts in ((None,(0,0,0,0)),(removes_another,(0,1,0,0)),(recreates_another,(0,0,1,0)),(renames_another,(1,1,0,0)),(adds_another,(1,0,0,0))):
        m,docs,host,receipt,worker=run(lambda host:setattr(host.docker.compose,'after_up',after_up));facts=receipt['recreate']['facts']
        assert (facts['others_appeared'],facts['others_gone'],facts['others_same_name_new_id'],facts['service_leftovers'])==counts,after_up
        assert facts['others_unchanged'] is (counts==(0,0,0,0)) and (receipt['status']==m.COMPLETE_STATUS) is (counts==(0,0,0,0))
    # a container that was listed under the lock and ended while the recreate ran (docker run --rm of another operation)
    def ends(host):
        host.docker.containers.append(hostemu.container('hostops02-k11-0123456789abcdef',hostemu.BACKEND,'c3po/backend:production',[]))
        host.docker.compose.after_up=lambda compose,new:compose.docker.containers.pop()
    m,docs,host,receipt,worker=run(ends);facts=receipt['recreate']['facts']
    assert (receipt['code'],facts['others_appeared'],facts['others_gone'],facts['others_same_name_new_id'])==('OTHER_CONTAINERS_CHANGED',0,1,0)
    # the old container left under the temporary name of a recreate: one that appeared, and a leftover of the service
    m,docs,host=k6a.fresh();old=k6a.worker(host)['Id'];host.docker.compose.after_up=leaves_the_old_one(old);facts=docs.run(host)['recreate']['facts']
    assert (facts['others_appeared'],facts['others_gone'],facts['others_same_name_new_id'],facts['service_leftovers'])==(1,0,0,1)
    # the listing cannot be made: the counts are unknown, not zero
    m,docs,host,receipt,worker=run(lambda host:setattr(host.docker.compose,'after_up',lambda compose,new:setattr(compose.docker,'ps_returncode',1)))
    facts=receipt['recreate']['facts'];assert [facts[key] for key in ('others_appeared','others_gone','others_same_name_new_id','service_leftovers','others_unchanged')]==[None]*5

def test_deploy_tree_that_is_not_reached_by_its_name_any_more_fails_everything_read_through_it():
    """The deploy tree changes its mode while the recreate runs: the environment file, the compose file and the lock
    directory are all reached through it, and none of the three is said to be unchanged on the word of a descriptor."""
    def after_up(compose,new):compose.docker.host.tree.get(hostemu.DEPLOY).mode=0o750
    m,docs,host,receipt,worker=run(lambda host:setattr(host.docker.compose,'after_up',after_up));facts=receipt['recreate']['facts']
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,NOT_VERIFIED,'ENV_FILE_CHANGED','RECREATED_NOT_VERIFIED')
    assert (facts['env_file_unchanged'],facts['compose_file_unchanged'],facts['lock_still_named'],facts['release_unchanged'],facts['files_as_delivered'])==(False,False,False,True,True)
    assert len([entry for entry in host.log if entry[0]=='open' and entry[1]==hostemu.ENV_FILE])==2,'opened at the first look and under the lock; not again through a directory that is not the named one'

def test_old_container_left_under_another_name_and_worker_that_is_gone():
    m,docs,host=k6a.fresh();old=k6a.worker(host)['Id'];host.docker.compose.after_up=leaves_the_old_one(old);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,'OLD_CONTAINER_STILL_PRESENT','RECREATED_NOT_VERIFIED')
    assert receipt['recreate']['facts']['old_container_gone'] is False and receipt['recreate']['facts']['others_unchanged'] is False
    m,docs,host,receipt,worker=run(lambda host:setattr(host.docker.compose,'after_up',removes_the_worker))
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,UNCERTAIN,'WORKER_NOT_FOUND_AFTER_RECREATE','UNCERTAIN')
    assert receipt['recreate']['facts']['worker_listed_once'] is False and receipt['recreate']['unavailable']['WORKER']=='COMMAND_FAILED' and receipt['worker_container_replaced'] is None

def test_new_worker_that_restarts_between_the_two_readings_is_caught_by_the_second():
    def prepare(restart):
        def on_pause(host):restart(k6a.worker(host))
        return lambda host:setattr(host,'on_pause',on_pause)
    def again(new):new['State']['StartedAt']='2026-10-05T08:50:59.000000000Z';new['RestartCount']=1
    def counted(new):new['RestartCount']=1
    def stopped(new):new['State'].update(Status='exited',Running=False)
    def later(new):new['State']['StartedAt']='2026-10-05T08:50:59.000000000Z'
    for restart in (again,counted,stopped,later):
        m,docs,host,receipt,worker=run(prepare(restart));facts=receipt['recreate']['facts']
        assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,NOT_VERIFIED,'WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS'),restart.__name__
        assert receipt['recreate']['state']=='RECREATED_NOT_VERIFIED' and facts['settle_pause_taken'] is True and facts['second_check_passed'] is False and facts['running'] is True
    # the same container, no longer under the worker's name (renamed away between the two readings): by ID it is found, and it is not the worker
    def renamed(host):k6a.worker(host)['Name']='/'+hostemu.WORKER+'-old'
    m,docs,host,receipt,worker=run(lambda host:setattr(host,'on_pause',renamed))
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['recreate']['unavailable'])==(m.PARTIAL_STATUS,NOT_VERIFIED,'READBACK_UNAVAILABLE',{'SECOND_CHECK':'CONTAINER_METADATA_INVALID'})
    assert receipt['recreate']['state']=='RECREATED_VERIFIED_ONCE' and receipt['recreate']['facts']['second_check_passed'] is None
    # replaced once more between the two readings: the second reading is by ID and finds nothing
    def replaced(host):k6a.worker(host)['Id']='c'*64
    m,docs,host,receipt,worker=run(lambda host:setattr(host,'on_pause',replaced))
    assert (receipt['status'],receipt['code'],receipt['recreate']['unavailable'])==(m.PARTIAL_STATUS,'READBACK_UNAVAILABLE',{'SECOND_CHECK':'COMMAND_FAILED'})
    assert receipt['recreate']['state']=='RECREATED_VERIFIED_ONCE' and receipt['recreate']['facts']['second_check_passed'] is None

def test_readback_that_cannot_be_made_is_never_read_as_success():
    def after(change):return lambda host:setattr(host.docker.compose,'after_up',lambda compose,new:change(compose.docker.host))
    def no_inspect(host):host.docker.inspect_returncode=1
    def no_listing(host):host.docker.ps_returncode=1
    def no_docker(host):host.hang.add('docker')
    def no_env_file(host):k6a.replace(host,hostemu.ENV_FILE,'symlink')
    def no_compose_file(host):k6a.replace(host,hostemu.COMPOSE_FILE,'symlink')
    def other_release(host):host.tree.get(k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME).content=bytearray(k6a.RELEASE[:-1]+b'x')
    def no_release(host):host.tree.remove(k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME)
    for change,code,outcome,state,steps in (
            (no_inspect,'READBACK_UNAVAILABLE',NOT_VERIFIED,'RECREATED_NOT_VERIFIED',{'WORKER':'COMMAND_FAILED'}),
            (no_listing,'READBACK_UNAVAILABLE',NOT_VERIFIED,'RECREATED_NOT_VERIFIED',{'CONTAINERS':'COMMAND_FAILED'}),
            (no_docker,'READBACK_UNAVAILABLE',UNCERTAIN,'UNCERTAIN',{'WORKER':'COMMAND_TIMEOUT','CONTAINERS':'COMMAND_TIMEOUT'}),
            (no_env_file,'READBACK_UNAVAILABLE',NOT_VERIFIED,'RECREATED_NOT_VERIFIED',{'ENV_FILE':'ENV_FILE_NOT_REGULAR'}),
            (no_compose_file,'READBACK_UNAVAILABLE',NOT_VERIFIED,'RECREATED_NOT_VERIFIED',{'COMPOSE_FILE':'COMPOSE_FILE_NOT_REGULAR'}),
            (other_release,'READBACK_UNAVAILABLE',NOT_VERIFIED,'RECREATED_NOT_VERIFIED',{'RELEASE':'RELEASE_HASH_MISMATCH'}),
            (no_release,'READBACK_UNAVAILABLE',NOT_VERIFIED,'RECREATED_NOT_VERIFIED',{'RELEASE':'RELEASE_NOT_INSTALLED'})):
        m,docs,host,receipt,worker=run(after(change))
        assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.PARTIAL_STATUS,outcome,code,state),change.__name__
        assert receipt['recreate']['unavailable']==steps and receipt['mutating_calls']['uncertain']==1 and k6a.worker(host)['Id']!=worker
    # the listing alone still says which container carries the name when the inspect fails
    m,docs,host,receipt,worker=run(after(no_inspect));facts=receipt['recreate']['facts']
    assert (facts['worker_listed_once'],facts['worker_is_new'],facts['old_container_gone'],facts['running'],facts['second_check_passed'])==(True,True,True,None,None)

def test_window_that_ends_during_the_recreate_leaves_an_uncertain_partial():
    m,docs,host=k6a.fresh(minutes=1);budget=f.Budget(docs.now).attach(host);budget.cost(70.0,'up');worker=k6a.worker(host)['Id']
    receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,UNCERTAIN,'READBACK_UNAVAILABLE')
    assert receipt['recreate']['unavailable']['WORKER']=='COMMAND_NOT_STARTED' or receipt['recreate']['unavailable']['WORKER']=='GO_EXPIRED'
    assert k6a.worker(host)['Id']!=worker and receipt['worker_container_replaced'] is None and receipt['clock'] is not None and host.lock_held(k6a.LOCK) is None

def test_death_of_the_process_is_an_escaped_partial_that_names_no_state():
    for event,number,issued in (('mkdir',1,1),('create',1,2),('write',1,3),('link',1,4),('unlink',1,5),('create',2,6),('link',2,8),('unlink',2,9)):
        m,docs,host=k6a.fresh();count=[0]
        def hook(host,name,detail,calls,event=event,number=number):
            if name==event:
                count[0]+=1
                if count[0]==number:raise hostemu.Death('dead')
        host.hook=hook;receipt=docs.run(host)
        assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(m.PARTIAL_STATUS,'PARTIAL_REQUIRES_RECONCILIATION','RUN_ESCAPED_STATE_UNKNOWN','ESCAPED')
        assert receipt['mutating_calls']=={'issued':issued,'succeeded':issued-1,'failed_nothing_changed':0,'uncertain':1} and f.sealed(receipt)
    # at the recreate command itself
    m,docs,host=k6a.fresh()
    def hook(host,name,detail,calls):
        if name=='run' and 'up' in detail[0]:raise hostemu.Death('dead')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['mutating_calls'])==(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN',{'issued':10,'succeeded':9,'failed_nothing_changed':0,'uncertain':1})
    # before anything was created: a refusal
    m,docs,host=k6a.fresh()
    def hook(host,name,detail,calls):
        if name=='run':raise KeyboardInterrupt()
    host.hook=hook;before=k6a.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT','BEFORE_ANY_EFFECT') and k6a.state_of(host)==before

def test_reduced_receipt_is_never_complete():
    m,docs,host=k6a.fresh();big=m.RECEIPT_LIMIT
    original=m.envelope
    try:
        m.envelope=lambda status,outcome,code,bound:original(status,outcome,code,dict(bound,precheck={'padding':'x'*big}))
        receipt=docs.run(host)
    finally:m.envelope=original
    assert (receipt['status'],receipt['outcome'])==(m.PARTIAL_STATUS,'RECEIPT_REDUCED_STATE_REQUIRES_READBACK') and receipt['size_reductions']==['PRECHECK_DROPPED']
    assert receipt['precheck']=={'reduced_for_size':True} and receipt['recreate']['state']=='RECREATED_VERIFIED' and len(f.line(receipt))<=m.RECEIPT_LIMIT+m.SEAL_OVERHEAD
