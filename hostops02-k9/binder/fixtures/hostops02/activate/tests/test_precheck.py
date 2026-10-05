"""Everything K6a looks at before its first creation, each on a host that is not as signed: hostile filesystem states
(a link, another owner, another mode, another device, an object in the way, foreign content), a worker, an image or a
compose project that is not what the request says, hostile answers of the docker CLI, and things that change between
the first look and the lock. Every case is REFUSED at PRECHECK with a constant code and nothing changed: no creating
call, no effect command, the lock not held, no descriptor left."""
import json

import pytest

import family as f
import hostemu
import k6a

RELEASE_FILE=k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME
VERSION=hostemu.DEPLOY+'/.deploy-version'

def refused(prepare,code,same=True,plan=None):
    m,docs,host=k6a.fresh();prepare(host)
    if plan is not None:
        plan(docs.plan);docs.chain()
    before=k6a.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==('REFUSED','REFUSED_NOTHING_CHANGED',code,'PRECHECK'),(code,receipt['code'])
    if same:assert k6a.state_of(host)==before
    assert host.mutating()==[] and receipt['mutating_calls']=={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0} and receipt['objects_left_by_this_run']==0
    assert host.tree.get(k6a.LIVE) is None or k6a.state_of(host)==before,'nothing was created'
    assert receipt['recreate']['state']=='NOT_STARTED' and receipt['recreate']['started'] is False and receipt['worker_container_replaced'] is False
    assert receipt['commands_started']['EFFECT']==0 and not [entry for entry in host.commands if 'up' in entry['argv']]
    assert host.lock_held(k6a.LOCK) is None and host.fds=={} and host.locks=={} and f.sealed(receipt)
    assert hostemu.SECRET not in json.dumps(receipt)
    return receipt

def node(path,**members):
    def prepare(host):
        for key,value in members.items():setattr(host.tree.get(path),key,value)
    return prepare
def put(path,kind,**attributes):return lambda host:k6a.replace(host,path,kind,**attributes) and None
def gone(path):return lambda host:host.tree.remove(path)
def content(path,raw):return lambda host:setattr(host.tree.get(path),'content',bytearray(raw))
def actor(*ids):return lambda host:setattr(host,'actor',ids)
def linked_elsewhere(host):
    """The release directory replaced by a link to a directory that holds the same bytes."""
    real=host.tree.get(k6a.RELEASE_DIRECTORY);host.tree.remove(k6a.RELEASE_DIRECTORY)
    host.tree.get(hostemu.DATA).children['elsewhere']=real;host.tree.add(k6a.RELEASE_DIRECTORY,kind='symlink',dev=hostemu.DATA_DEVICE,target='elsewhere')

FILESYSTEM=[
    ('executor gid not 0',actor(0,5),'EXECUTOR_IDENTITY'),('executor not root',actor(1000,1000),'EXECUTOR_IDENTITY'),
    ('another boot',content('/proc/sys/kernel/random/boot_id',b'1f8fad5b-d9cb-469f-a165-70867728950e\n'),'EVIDENCE_FROM_EARLIER_BOOT'),
    ('boot id unreadable',content('/proc/sys/kernel/random/boot_id',b'garbage\n'),'BOOT_ID_INVALID'),
    ('no O_NOATIME',lambda host:setattr(host,'noatime_available',False),'NOATIME_UNAVAILABLE'),
    # the parent of the live directory
    ('live parent another inode',node(k6a.LIVE_PARENT,ino=9001),'PARENT_IDENTITY_MISMATCH'),('live parent another mode',node(k6a.LIVE_PARENT,mode=0o700),'PARENT_IDENTITY_MISMATCH'),
    ('live parent another owner',node(k6a.LIVE_PARENT,uid=1000),'PARENT_IDENTITY_MISMATCH'),('live parent another group',node(k6a.LIVE_PARENT,gid=1000),'PARENT_IDENTITY_MISMATCH'),
    ('live parent on another device',node(k6a.LIVE_PARENT,dev=hostemu.ROOT_DEVICE),'PARENT_IDENTITY_MISMATCH'),
    ('data root another inode',node(hostemu.DATA,ino=9002),'PARENT_IDENTITY_MISMATCH'),
    ('live parent a symbolic link',put(k6a.LIVE_PARENT,'symlink'),'PARENT_SYMLINK_COMPONENT'),('data root a symbolic link',put(hostemu.DATA,'symlink'),'PARENT_SYMLINK_COMPONENT'),
    ('live parent a file',put(k6a.LIVE_PARENT,'file'),'PARENT_NOT_DIRECTORY'),('live parent absent',gone(k6a.LIVE_PARENT),'PARENT_MISSING'),
    # the destination must not exist, whatever it is
    ('destination a directory',put(k6a.LIVE,'dir',mode=0o700),'DESTINATION_PRESENT'),('destination a file',put(k6a.LIVE,'file'),'DESTINATION_PRESENT'),
    ('destination a symbolic link',put(k6a.LIVE,'symlink'),'DESTINATION_PRESENT'),('destination a fifo',put(k6a.LIVE,'fifo'),'DESTINATION_PRESENT'),
    # the maintenance pin
    ('pin absent',gone(hostemu.PIN),'MAINTENANCE_PIN_ABSENT'),('pin a directory',put(hostemu.PIN,'dir'),'MAINTENANCE_PIN_ABSENT'),
    ('pin a symbolic link',put(hostemu.PIN,'symlink'),'MAINTENANCE_PIN_ABSENT'),('pin a fifo',put(hostemu.PIN,'fifo'),'MAINTENANCE_PIN_ABSENT'),
    # the release an earlier operation installed
    ('release directory absent',gone(k6a.RELEASE_DIRECTORY),'RELEASE_NOT_INSTALLED'),('release directory a link to the same bytes',linked_elsewhere,'RELEASE_DIRECTORY_NOT_AS_INSTALLED'),
    ('release directory a file',put(k6a.RELEASE_DIRECTORY,'file'),'RELEASE_DIRECTORY_NOT_AS_INSTALLED'),
    ('release directory open to others',node(k6a.RELEASE_DIRECTORY,mode=0o755),'RELEASE_DIRECTORY_NOT_AS_INSTALLED'),
    ('release directory of another owner',node(k6a.RELEASE_DIRECTORY,uid=1000),'RELEASE_DIRECTORY_NOT_AS_INSTALLED'),
    ('release directory of another group',node(k6a.RELEASE_DIRECTORY,gid=1000),'RELEASE_DIRECTORY_NOT_AS_INSTALLED'),
    ('release directory on another device',node(k6a.RELEASE_DIRECTORY,dev=hostemu.ROOT_DEVICE),'RELEASE_DIRECTORY_NOT_AS_INSTALLED'),
    ('release file absent',gone(RELEASE_FILE),'RELEASE_NOT_INSTALLED'),('release file a symbolic link',put(RELEASE_FILE,'symlink'),'RELEASE_FILE_NOT_AS_INSTALLED'),
    ('release file a fifo',put(RELEASE_FILE,'fifo'),'RELEASE_FILE_NOT_AS_INSTALLED'),('release file a directory',put(RELEASE_FILE,'dir'),'RELEASE_FILE_NOT_AS_INSTALLED'),
    ('release file readable by others',node(RELEASE_FILE,mode=0o644),'RELEASE_FILE_NOT_AS_INSTALLED'),('release file of another owner',node(RELEASE_FILE,uid=1000),'RELEASE_FILE_NOT_AS_INSTALLED'),
    ('release file of another group',node(RELEASE_FILE,gid=5),'RELEASE_FILE_NOT_AS_INSTALLED'),('release file with two links',node(RELEASE_FILE,nlink=2),'RELEASE_FILE_NOT_AS_INSTALLED'),
    ('release bytes differ',content(RELEASE_FILE,k6a.RELEASE[:-1]+b'x'),'RELEASE_HASH_MISMATCH'),('release one byte longer',content(RELEASE_FILE,k6a.RELEASE+b'\n'),'RELEASE_HASH_MISMATCH'),
    ('release empty',content(RELEASE_FILE,b''),'RELEASE_HASH_MISMATCH'),('release larger than the limit',content(RELEASE_FILE,b'x'*65537),'FILE_TOO_LARGE'),
    # the deploy tree
    ('deploy tree another inode',node(hostemu.DEPLOY,ino=9003),'PARENT_IDENTITY_MISMATCH'),('deploy tree a symbolic link',put(hostemu.DEPLOY,'symlink'),'PARENT_SYMLINK_COMPONENT'),
    ('deploy version absent',gone(VERSION),'DEPLOY_VERSION_ABSENT'),('deploy version a symbolic link',put(VERSION,'symlink'),'DEPLOY_VERSION_NOT_REGULAR'),
    ('deploy version a directory',put(VERSION,'dir'),'DEPLOY_VERSION_NOT_REGULAR'),('another revision deployed',content(VERSION,b'4de7095ad51bce19ea4b685d5c708d0a72986d76\n'),'DEPLOY_VERSION_MISMATCH'),
    ('deploy version empty',content(VERSION,b''),'DEPLOY_VERSION_MISMATCH'),('deploy version with more text',content(VERSION,(hostemu.REVISION+'\nx\n').encode()),'DEPLOY_VERSION_MISMATCH'),
    ('deploy version too large',content(VERSION,b'd'*200),'FILE_TOO_LARGE'),
    ('environment file absent',gone(hostemu.ENV_FILE),'ENV_FILE_ABSENT'),('environment file a symbolic link',put(hostemu.ENV_FILE,'symlink'),'ENV_FILE_NOT_REGULAR'),
    ('environment file a fifo',put(hostemu.ENV_FILE,'fifo'),'ENV_FILE_NOT_REGULAR'),('environment file too large',content(hostemu.ENV_FILE,b'A=1\n'*262145),'FILE_TOO_LARGE'),
    # the compose project of the deploy tree: its directory by name, never through a link; its file a regular file
    ('project directory absent',gone(k6a.PROJECT_DIRECTORY),'COMPOSE_FILE_ABSENT'),('project directory a symbolic link',put(k6a.PROJECT_DIRECTORY,'symlink'),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY'),
    ('project directory a file',put(k6a.PROJECT_DIRECTORY,'file'),'COMPOSE_DIRECTORY_NOT_A_DIRECTORY'),
    ('compose file absent',gone(hostemu.COMPOSE_FILE),'COMPOSE_FILE_ABSENT'),('compose file a symbolic link',put(hostemu.COMPOSE_FILE,'symlink'),'COMPOSE_FILE_NOT_REGULAR'),
    ('compose file a fifo',put(hostemu.COMPOSE_FILE,'fifo'),'COMPOSE_FILE_NOT_REGULAR'),('compose file a directory',put(hostemu.COMPOSE_FILE,'dir'),'COMPOSE_FILE_NOT_REGULAR'),
    ('compose file too large',content(hostemu.COMPOSE_FILE,b'#'*1048577),'FILE_TOO_LARGE'),
    # the lock
    ('lock file absent',gone(k6a.LOCK),'LOCK_FILE_ABSENT'),('lock file a symbolic link',put(k6a.LOCK,'symlink'),'LOCK_FILE_NOT_REGULAR'),
    ('lock file a directory',put(k6a.LOCK,'dir'),'LOCK_FILE_NOT_REGULAR'),('lock file with two links',node(k6a.LOCK,nlink=2),'LOCK_FILE_NOT_REGULAR'),
    ('lock directory another inode',node(hostemu.LOCK_DIRECTORY,ino=9004),'PARENT_IDENTITY_MISMATCH'),('lock directory a symbolic link',put(hostemu.LOCK_DIRECTORY,'symlink'),'PARENT_SYMLINK_COMPONENT'),
    # a security reboot is pending (c3po-pipeline.yml:655-658 refuses a deploy on the same marker)
    ('reboot pending',put(k6a.PENDING,'file'),'SECURITY_REBOOT_PENDING'),('reboot marker a directory',put(k6a.PENDING,'dir'),'SECURITY_REBOOT_PENDING'),
    ('reboot marker a symbolic link',put(k6a.PENDING,'symlink'),'SECURITY_REBOOT_PENDING'),
    ('reboot marker behind a symbolic link',put('/run/c3po-security','symlink'),'REBOOT_STATE_UNAVAILABLE'),
    ('reboot marker below a file',put('/run/c3po-security','file'),'COMPONENT_NOT_DIRECTORY'),
]
@pytest.mark.parametrize('label,prepare,code',FILESYSTEM,ids=[case[0] for case in FILESYSTEM])
def test_hostile_filesystem_states_refuse_before_any_effect(label,prepare,code):refused(prepare,code)

def test_release_parent_is_walked_by_its_own_signed_rows():
    """The release may lie in another directory than the data root: its parent is pinned like every other."""
    def build():
        k=k6a.load();host=f.world(k);k6a.prepare(host);parent=hostemu.DATA+'/releases'
        host.tree.add(parent,dev=hostemu.DATA_DEVICE,mode=0o755);moved=host.tree.get(k6a.RELEASE_DIRECTORY);host.tree.remove(k6a.RELEASE_DIRECTORY)
        host.tree.get(parent).children[k6a.RELEASE_LEAF]=moved
        fields=k6a.fields(host);fields['release']['parent']=hostemu.rows(host,parent);return k.m,f.Docs(k,fields),host,parent
    m,docs,host,parent=build();receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and docs.go['effects']['recreate']['environment']['C3PO_R2D2_V2_SHADOW_RELEASE_FILE']=='/app/day-d-data/releases/r2d2-v2-release-20261005/release.CERTIFIED.json'
    for change,code in ((dict(ino=9100),'PARENT_IDENTITY_MISMATCH'),(dict(mode=0o775),'PARENT_IDENTITY_MISMATCH')):
        m,docs,host,parent=build()
        for key,value in change.items():setattr(host.tree.get(parent),key,value)
        receipt=docs.run(host);assert (receipt['status'],receipt['code'],host.mutating())==('REFUSED',code,[])
    m,docs,host,parent=build();k6a.replace(host,parent,'symlink');receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED','PARENT_SYMLINK_COMPONENT')

def test_release_whose_signed_size_is_not_the_size_of_the_installed_bytes_and_release_swapped_while_it_is_opened():
    refused(lambda host:None,'RELEASE_HASH_MISMATCH',plan=lambda plan:plan['release'].update(bytes=len(k6a.RELEASE)+1))
    refused(lambda host:None,'RELEASE_HASH_MISMATCH',plan=lambda plan:plan['release'].update(bytes=len(k6a.RELEASE)-1))
    # the name shows another file between the lstat and the open: the same bytes, another inode
    def swapped(host):
        original=host.lstat;done=[]
        def lstat(name,dir_fd):
            result=original(name,dir_fd)
            if name==k6a.RELEASE_NAME and not done:
                done.append(1);k6a.replace(host,RELEASE_FILE,'file',mode=0o600,content=k6a.RELEASE)
            return result
        host.lstat=lstat
    refused(swapped,'RELEASE_FILE_NOT_AS_INSTALLED',same=False)

def test_project_directory_swapped_while_it_is_opened_and_identity_checked_before_anything_else():
    # the name shows another directory between the lstat and the open
    def swapped(host):
        original=host.lstat;done=[]
        def lstat(name,dir_fd):
            result=original(name,dir_fd)
            if name==hostemu.PROJECT and host.path_of(dir_fd)==hostemu.DEPLOY and not done:
                done.append(1);k6a.swap_directory(host,k6a.PROJECT_DIRECTORY)
            return result
        host.lstat=lstat
    refused(swapped,'COMPOSE_DIRECTORY_NOT_A_DIRECTORY',same=False)
    # CORE.md rule 3: the executor first. Not even the umask of the process is set for an executor that is not root.
    m,docs,host=k6a.fresh();host.actor=(1000,1000);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','EXECUTOR_IDENTITY') and host.log==[] and host.calls==0 and host.mask==0o022

def test_reached_by_name_says_no_only_for_a_directory_that_was_replaced_and_raises_a_window_that_ended():
    """The answer of Pinned.verify, as the operation reads it: True, False for a path that no longer leads to the
    descriptor held, and never False for an expired window (that is raised, with its own code)."""
    m=k6a.load().m
    class Holder:
        def __init__(self,code=None):self.code,self.asked=code,[]
        def verify(self,gate):
            self.asked.append(gate)
            if self.code:raise m.Refused(self.code)
    held=Holder();assert m.reached_by_name(held,'gate') is True and held.asked==['gate'] and m.reached_by_name(Holder('PARENT_REPLACED'),None) is False
    for code in ('GO_EXPIRED','CLOCK_REVERSED'):assert f.refusal(lambda:m.reached_by_name(Holder(code),None))==code
    # on the host: the three directories are proved again under the lock by a fresh walk from "/" (four walks more than the first look made)
    m,docs,host=k6a.fresh();docs.run(host);names=[entry[0] for entry in host.log];lock=names.index('flock');made=names.index('mkdir')
    again=[entry[1] for entry in host.log[lock:made] if entry[0]=='lstat']
    for path in (k6a.RELEASE_DIRECTORY,k6a.PROJECT_DIRECTORY,hostemu.LOCK_DIRECTORY,hostemu.DATA,hostemu.DEPLOY):assert path in again,path

# ---------------------------------------------------------------- room on the data volume, knowable before the first creation
SPACE=[('one block below the floor',dict(f_bavail=255),'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR'),('nothing left for a non-root writer',dict(f_bavail=0),'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR'),
       ('blocks free for root only',dict(f_bavail=0,f_bfree=1000000),'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR'),
       ('seven inodes left',dict(f_files=6553600,f_favail=7),'DATA_VOLUME_FREE_INODES_BELOW_FLOOR'),('no inode left',dict(f_files=6553600,f_favail=0),'DATA_VOLUME_FREE_INODES_BELOW_FLOOR'),
       ('a block count that is not a number',dict(f_bavail=None),'STATVFS_INVALID'),('a block size of zero',dict(f_frsize=0),'STATVFS_INVALID')]
@pytest.mark.parametrize('label,members,code',SPACE,ids=[case[0] for case in SPACE])
def test_data_volume_without_room_refuses_before_any_effect(label,members,code):
    receipt=refused(lambda host:k6a.data_volume(host,**members),code)
    if code!='STATVFS_INVALID':assert receipt['precheck']['free_bytes']==members.get('f_bavail',hostemu.DATA_VFS['f_bavail'])*4096,'the figure that decided is in the receipt'
    assert receipt['precheck']['lock_attempts']==1,'asked under the lock, right before the first creation'
def test_room_is_asked_of_the_filesystem_of_the_live_parent_and_the_floor_is_exact():
    """1 MiB for a non-root writer (the floor of install_release) and, where the filesystem counts inodes, eight."""
    for members,seen in ((dict(f_bavail=256),(1048576,None)),(dict(f_files=6553600,f_favail=8),(hostemu.DATA_VFS['f_bavail']*4096,8)),
                         (dict(f_files=0,f_favail=0),(hostemu.DATA_VFS['f_bavail']*4096,None)),         # a filesystem that counts no inodes is judged by its bytes
                         (dict(f_files=6553600,f_favail=None),(hostemu.DATA_VFS['f_bavail']*4096,None)),(dict(f_files=None,f_favail=3),(hostemu.DATA_VFS['f_bavail']*4096,None)),
                         (dict(f_files=6553600,f_favail='7'),(hostemu.DATA_VFS['f_bavail']*4096,None)),(dict(f_files=6553600,f_favail=8,f_ffree=0),(hostemu.DATA_VFS['f_bavail']*4096,8))):
        m,docs,host=k6a.fresh();k6a.data_volume(host,**members);receipt=docs.run(host)
        assert receipt['status']==m.COMPLETE_STATUS and (receipt['precheck']['free_bytes'],receipt['precheck']['free_inodes'])==seen,members
    # the root filesystem is not the one asked
    import types
    m,docs,host=k6a.fresh();host.vfs[hostemu.ROOT_DEVICE]=types.SimpleNamespace(f_frsize=4096,f_blocks=1,f_bfree=0,f_bavail=0,f_files=10,f_favail=0)
    assert docs.run(host)['status']==m.COMPLETE_STATUS
    # a filesystem that cannot be asked is not taken for one with room
    import errno
    def hook(host,name,detail,calls):
        if name=='fstatvfs':raise OSError(errno.EIO,'injected')
    refused(lambda host:setattr(host,'hook',hook),'PRECHECK_OS_ERROR')

# ---------------------------------------------------------------- a container left by an interrupted recreate of the service
LEFT='0123456789ab_'+hostemu.WORKER
LEFTOVERS=[(LEFT,'created'),(LEFT,'exited'),(LEFT,'running'),('x_'+hostemu.WORKER,'created'),('fedcba987654_'+hostemu.WORKER,'dead')]
@pytest.mark.parametrize('name,state',LEFTOVERS,ids=['%s %s'%case for case in LEFTOVERS])
def test_container_of_the_service_under_a_temporary_name_refuses_before_any_effect(name,state):
    """compose would remove or replace it during the recreate: the listing could not stay as it was, and the run
    would end PARTIAL with the worker already replaced. It is knowable under the lock, before the first creation."""
    receipt=refused(lambda host:host.docker.containers.append(k6a.service_container(name,state)),'WORKER_SERVICE_LEFTOVER_CONTAINER')
    assert receipt['precheck']['lock_attempts']==1,'seen in the listing made under the lock'
def test_container_whose_name_only_resembles_the_worker_s_is_another_container():
    """A one-off container of the service (compose run), a second replica, a container of another project: none
    carries the temporary name of a recreate, and each stays as it was."""
    for name in (hostemu.WORKER+'-run-0123456789ab',hostemu.WORKER[:-1]+'10','legacy-'+hostemu.WORKER,hostemu.WORKER+'_0123456789ab','0123456789ab_c3po-api-1',
                 '0123456789ab_'+hostemu.WORKER+'0','0123456789ab_'+hostemu.WORKER+'-run-ab12'):          # the temporary name is a whole name, not a part of one
        m,docs,host=k6a.fresh();host.docker.containers.append(k6a.service_container(name,'exited'));receipt=docs.run(host)
        assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['containers_listed']==9 and receipt['recreate']['facts']['service_leftovers']==0,name

@pytest.mark.parametrize('members',[dict(source=hostemu.DATA+'/'),dict(source='/mnt//day-d-data'),dict(source='/mnt/./day-d-data'),dict(target=k6a.TARGET+'/'),
                                     dict(target='/app//day-d-data'),dict(read_only=False),dict(source=hostemu.DATA+'/',target=k6a.TARGET+'/')])
def test_bind_of_the_data_root_is_recognised_however_compose_spells_its_two_paths(members):
    """The source comes from the host's environment file: a trailing or doubled slash names the same directory."""
    m,docs,host=k6a.fresh();data_mount(**members)(host);receipt=docs.run(host)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['render']['data_root_bound_at_the_signed_target'] is True

def test_destination_that_cannot_be_read_is_not_taken_for_absent():
    """A component of the way to the destination becomes a link after the pinned walk and before the probe: the probe
    says UNAVAILABLE, not absent, and the run refuses."""
    def swapped(host):
        original=host.open;opened=[]
        def open_(name,flags,dir_fd=None):
            if name=='/':
                opened.append(1)
                if len(opened)==3:k6a.replace(host,k6a.LIVE_PARENT,'symlink')         # the third walk from "/" is the probe of the destination
            return original(name,flags,dir_fd)
        host.open=open_
    refused(swapped,'DESTINATION_PRESENT',same=False)

def test_descriptor_is_closed_when_the_directory_it_holds_cannot_be_pinned_and_precheck_failures_have_constant_codes():
    import errno
    for kind,code in ((lambda:OSError(errno.EIO,'injected'),'PRECHECK_OS_ERROR'),(lambda:RuntimeError('injected'),'PRECHECK_FAILED')):
        m,docs,host=k6a.fresh();count=[0]
        def hook(host,name,detail,calls,kind=kind):
            if name=='fstat' and detail[0]==k6a.LIVE_PARENT:
                count[0]+=1
                if count[0]==2:raise kind()                    # the fstat of Pinned(): the walk has returned its descriptor
        host.hook=hook;receipt=docs.run(host)
        assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'PRECHECK') and host.fds=={} and host.mutating()==[]
        assert 'injected' not in json.dumps(receipt)

# ---------------------------------------------------------------- the worker, its image, the compose project
def container(**members):
    def prepare(host):
        item=k6a.worker(host)
        for key,value in members.items():
            if key=='state':item['State'].update(value)
            else:item[key]=value
    return prepare
def environment(change):
    def prepare(host):
        item=k6a.worker(host);values=dict(entry.split('=',1) for entry in item['Config']['Env']);change(values)
        item['Config']['Env']=['%s=%s'%pair for pair in values.items()]
    return prepare
def image(change):return lambda host:change(host.docker.images[0])
def base(change):return lambda host:change(host.docker.compose.base['services']['r2d2-worker'])
def volumes(value):return base(lambda service:service.__setitem__('volumes',value))
def data_mount(**members):
    def change(service):
        entry=[item for item in service['volumes'] if item['target']==k6a.TARGET][0]
        for key,value in members.items():
            if value is ...:entry.pop(key,None)
            else:entry[key]=value
    return base(change)
def extra_mount(entry):return base(lambda service:service['volumes'].append(entry))
def no_worker(host):host.docker.containers=[item for item in host.docker.containers if item['Name']!='/'+hostemu.WORKER]
def no_image(host):host.docker.images=[item for item in host.docker.images if item['Id']!=hostemu.BACKEND]
def unsafe_binary(host):host.tree.get('/usr/bin/docker').mode=0o775
def unsafe_directory(host):host.tree.get('/usr/bin').uid=1000
def render_without(key):
    def prepare(host):
        rendered=json.loads(json.dumps(host.docker.compose.base));service=rendered['services']['r2d2-worker']
        service['environment']=dict(service['environment'],**k6a.environment());service['environment'].pop(key)
        host.docker.compose.config_output=json.dumps(rendered).encode()
    return prepare
def render_with(key,value):
    def prepare(host):
        rendered=json.loads(json.dumps(host.docker.compose.base));service=rendered['services']['r2d2-worker']
        service['environment']=dict(service['environment'],**k6a.environment());service['environment'][key]=value
        host.docker.compose.config_output=json.dumps(rendered).encode()
    return prepare

ENGINE=[
    ('no worker container',no_worker,'COMMAND_FAILED'),('worker exited',container(state={'Status':'exited','Running':False}),'WORKER_NOT_RUNNING'),
    ('worker restarting',container(state={'Status':'restarting','Running':True}),'WORKER_NOT_RUNNING'),('worker paused',container(state={'Status':'paused','Running':True}),'WORKER_NOT_RUNNING'),
    ('worker on another image',container(Image=hostemu.OTHER),'WORKER_IMAGE_NOT_THE_SIGNED_ONE'),
    ('image not in the store',no_image,'IMAGE_ABSENT_OR_UNREADABLE'),
    ('image of another revision',image(lambda item:item['Config']['Labels'].update({'org.opencontainers.image.revision':'4de7095ad51bce19ea4b685d5c708d0a72986d76'})),'IMAGE_REVISION_MISMATCH'),
    ('image without a revision label',image(lambda item:item['Config'].update(Labels={})),'IMAGE_REVISION_MISMATCH'),
    ('worker built from another revision',environment(lambda values:values.update(C3PO_BUILD_SHA='4de7095ad51bce19ea4b685d5c708d0a72986d76')),'WORKER_BUILD_REVISION'),
    ('worker without a build revision',environment(lambda values:values.pop('C3PO_BUILD_SHA')),'WORKER_BUILD_REVISION'),
    ('worker with a longer build revision',environment(lambda values:values.update(C3PO_BUILD_SHA=hostemu.REVISION+'0')),'WORKER_BUILD_REVISION'),
    # compose
    ('render fails',lambda host:setattr(host.docker.compose,'config_returncode',1),'COMMAND_FAILED'),
    ('render is not JSON',lambda host:setattr(host.docker.compose,'config_output',b'services:\n  r2d2-worker: {}\n'),'COMPOSE_RENDER_INVALID'),
    ('render has a duplicate key',lambda host:setattr(host.docker.compose,'config_output',b'{"services":{},"services":{}}'),'COMPOSE_RENDER_INVALID'),
    ('render without services',lambda host:setattr(host.docker.compose,'config_output',b'{"name":"c3po"}'),'COMPOSE_RENDER_INVALID'),
    ('render larger than the class',lambda host:setattr(host.docker.compose,'config_output',b'{"services":{"x":"'+b'y'*1048576+b'"}}'),'COMMAND_OUTPUT_LIMIT'),
    ('render without the worker service',lambda host:host.docker.compose.base['services'].pop('r2d2-worker'),'COMPOSE_SERVICE_INVALID'),
    ('render with an environment that is a list',lambda host:setattr(host.docker.compose,'config_output',b'{"services":{"r2d2-worker":{"image":"c3po/backend:production","environment":["A=1"]}}}'),'COMPOSE_SERVICE_INVALID'),
    ('render with a value that is a number',lambda host:setattr(host.docker.compose,'config_output',b'{"services":{"r2d2-worker":{"image":"c3po/backend:production","environment":{"A":1}}}}'),'COMPOSE_SERVICE_INVALID'),
    ('the compose file no longer interpolates the build revision',base(lambda service:service['environment'].pop('C3PO_BUILD_SHA')),'RENDER_BUILD_REVISION'),
    ('render of another image tag',base(lambda service:service.__setitem__('image','c3po/backend:rollback')),'RENDER_IMAGE_CHANGED'),
    ('render of an image that is not in the store',base(lambda service:service.__setitem__('image','c3po/backend:absent')),'RENDER_IMAGE_UNRESOLVED'),
    ('render of an image reference that is an option',base(lambda service:service.__setitem__('image','--help')),'RENDER_IMAGE_INVALID'),
    ('render of an image reference with a space',base(lambda service:service.__setitem__('image','c3po/backend production')),'RENDER_IMAGE_INVALID'),
    # the bind of the data root in the render
    ('render without volumes',base(lambda service:service.pop('volumes')),'RENDER_VOLUMES_INVALID'),('render volumes not a list',volumes({'a':1}),'RENDER_VOLUMES_INVALID'),
    ('render volume without a target',volumes([{'type':'bind','source':hostemu.DATA}]),'RENDER_VOLUMES_INVALID'),('render volume in the short syntax',volumes([hostemu.DATA+':'+k6a.TARGET]),'RENDER_VOLUMES_INVALID'),
    ('more volumes than the limit',base(lambda service:service['volumes'].extend({'type':'volume','source':'v%d'%index,'target':'/v%d'%index} for index in range(62))),'RENDER_VOLUMES_INVALID'),
    ('no volume covers the files',volumes([]),'WORKER_MOUNT_NOT_AS_SIGNED'),('data root bound one level up',data_mount(target='/app'),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('the data root as the source of a volume that is not a bind',data_mount(type='volume'),'WORKER_MOUNT_NOT_AS_SIGNED'),('data root mounted elsewhere',data_mount(target='/app/data'),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('a named volume at the target',data_mount(type='volume',source='c3po_day_d_data'),'WORKER_MOUNT_NOT_AS_SIGNED'),('another host directory at the target',data_mount(source='/mnt/other'),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('the bind is read-only',data_mount(read_only=True),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('the bind source one level up',data_mount(source=hostemu.DATA+'/..'),'WORKER_MOUNT_NOT_AS_SIGNED'),('the bind source with two leading slashes',data_mount(source='/'+hostemu.DATA),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('the bind source relative',data_mount(source=hostemu.DATA[1:]),'WORKER_MOUNT_NOT_AS_SIGNED'),('the bind without a source',data_mount(source=...),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('the bind source a number',data_mount(source=7),'WORKER_MOUNT_NOT_AS_SIGNED'),('the bind target one level up',data_mount(target=k6a.TARGET+'/..'),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('another volume shadows the live directory',extra_mount({'type':'volume','source':'x','target':k6a.TARGET+'/r2d2-v2-live'}),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('another volume shadows the release directory',extra_mount({'type':'bind','source':'/mnt/x','target':k6a.TARGET+'/'+k6a.RELEASE_LEAF}),'WORKER_MOUNT_NOT_AS_SIGNED'),
    ('a second volume above the target',extra_mount({'type':'bind','source':'/mnt/x','target':'/app'}),'WORKER_MOUNT_NOT_AS_SIGNED'),
    # the docker binary and the engine
    ('no docker binary',gone('/usr/bin/docker'),'BINARY_UNAVAILABLE_OR_UNSAFE'),('docker binary writable by its group',unsafe_binary,'BINARY_UNAVAILABLE_OR_UNSAFE'),
    ('directory of the docker binary not root-owned',unsafe_directory,'BINARY_UNAVAILABLE_OR_UNSAFE'),
    ('docker hangs',lambda host:host.hang.add('docker'),'COMMAND_TIMEOUT'),('compose hangs',lambda host:host.hang.add(('compose','config')),'COMMAND_TIMEOUT'),
    ('docker cannot be started',lambda host:host.absent.add('docker'),'COMMAND_NOT_STARTED'),
    ('the listing fails',lambda host:setattr(host.docker,'ps_returncode',1),'COMMAND_FAILED'),('inspect fails',lambda host:setattr(host.docker,'inspect_returncode',1),'COMMAND_FAILED'),
]
ENGINE+=[('worker already carries %s'%key,environment(lambda values,key=key:values.update({key:'anything'})),'WORKER_ALREADY_CARRIES_THE_KEYS') for key in k6a.KEYS]
ENGINE+=[('worker already carries an empty '+k6a.KEYS[0],environment(lambda values:values.update({k6a.KEYS[0]:''})),'WORKER_ALREADY_CARRIES_THE_KEYS'),
         ('worker already activated with the signed values',environment(lambda values:values.update(k6a.environment())),'WORKER_ALREADY_CARRIES_THE_KEYS')]
ENGINE+=[('render lacks %s'%key,render_without(key),'RENDER_ENVIRONMENT_MISMATCH') for key in k6a.KEYS]
ENGINE+=[('render gives %s another value'%key,render_with(key,'/app/day-d-data/other'),'RENDER_ENVIRONMENT_MISMATCH') for key in k6a.KEYS]
@pytest.mark.parametrize('label,prepare,code',ENGINE,ids=[case[0] for case in ENGINE])
def test_worker_image_and_project_that_are_not_as_signed_refuse_before_any_effect(label,prepare,code):refused(prepare,code)

# ---------------------------------------------------------------- hostile answers of the docker CLI
def says(match,reply,nth=None):return lambda host:k6a.answer(host,match,reply,nth)
def fixed(code,out):return lambda real:(code,out)
def edited(change):
    def reply(real):
        code,out=real();row=json.loads(out);change(row);return code,json.dumps(row).encode()+b'\n'
    return reply
def listing(change):
    def reply(real):
        code,out=real();rows=[json.loads(line) for line in out.splitlines()];rows=change(rows) or rows
        return code,b''.join(json.dumps(row).encode()+b'\n' for row in rows)
    return reply
def other_name(rows):
    for row in rows:
        if row['name']==hostemu.WORKER:row['name']='c3po-r2d2-worker-2'
def twice(rows):return rows+[dict(row,id='e'*64) for row in rows if row['name']==hostemu.WORKER]
def same_id_twice(rows):return rows+[dict(rows[0],name='copy')]
ANSWERS=[
    ('inspect answers for another container',says(k6a.is_inspect,edited(lambda row:row.update(name='/c3po-api-1'))),'CONTAINER_METADATA_INVALID'),
    ('inspect answers without a member',says(k6a.is_inspect,edited(lambda row:row.pop('restarts'))),'CONTAINER_METADATA_INVALID'),
    ('inspect answers with one more member',says(k6a.is_inspect,edited(lambda row:row.update(env=['A=1']))),'CONTAINER_METADATA_INVALID'),
    ('inspect answers with a restart count that is text',says(k6a.is_inspect,edited(lambda row:row.update(restarts='0'))),'CONTAINER_METADATA_INVALID'),
    ('inspect answers with an unknown state',says(k6a.is_inspect,edited(lambda row:row.update(state='fine'))),'CONTAINER_METADATA_INVALID'),
    ('inspect answers with a short ID',says(k6a.is_inspect,edited(lambda row:row.update(id=row['id'][:12]))),'CONTAINER_METADATA_INVALID'),
    ('inspect says running with the flag false',says(k6a.is_inspect,edited(lambda row:row.update(running=False))),'WORKER_NOT_RUNNING'),
    ('inspect says the flag true and the state paused',says(k6a.is_inspect,edited(lambda row:row.update(state='paused'))),'WORKER_NOT_RUNNING'),
    ('inspect answers nothing',says(k6a.is_inspect,fixed(0,b'')),'DOCUMENT_SIZE'),('inspect answers with text',says(k6a.is_inspect,fixed(0,b'Error: no such object\n')),'JSON_INVALID'),
    ('inspect answers with a list',says(k6a.is_inspect,fixed(0,b'[{}]\n')),'DOCUMENT_TYPE'),('inspect answers with a duplicate key',says(k6a.is_inspect,fixed(0,b'{"id":"a","id":"b"}\n')),'DUPLICATE_KEY'),
    ('inspect floods its output',says(k6a.is_inspect,fixed(0,b'x'*70000)),'COMMAND_OUTPUT_LIMIT'),('inspect exits 125',says(k6a.is_inspect,fixed(125,b'')),'COMMAND_FAILED'),
    ('image inspect answers with another ID',says(k6a.is_image,edited(lambda row:row.update(id=hostemu.OTHER))),'IMAGE_REVISION_MISMATCH'),
    ('image inspect answers without the tags',says(k6a.is_image,edited(lambda row:row.pop('repo_tags'))),'IMAGE_METADATA_INVALID'),
    ('image inspect answers with an ID that is not one',says(k6a.is_image,edited(lambda row:row.update(id='backend'))),'IMAGE_METADATA_INVALID'),
    ('the image reference of the render resolves to another image',says(k6a.is_image,edited(lambda row:row.update(id=hostemu.OTHER)),nth=2),'RENDER_IMAGE_CHANGED'),
    ('the environment template answers equal for an absent name',says(k6a.is_environment,edited(lambda row:row[k6a.KEYS[0]].update(present=False,equal=True))),'ENVIRONMENT_METADATA_INVALID'),
    ('the environment template answers without a name',says(k6a.is_environment,edited(lambda row:row.pop(k6a.KEYS[1]))),'ENVIRONMENT_METADATA_INVALID'),
    ('the environment template answers with one more name',says(k6a.is_environment,edited(lambda row:row.update(PATH={'present':True,'equal':False}))),'ENVIRONMENT_METADATA_INVALID'),
    ('the environment template answers with text for a boolean',says(k6a.is_environment,edited(lambda row:row['C3PO_BUILD_SHA'].update(equal='true'))),'ENVIRONMENT_METADATA_INVALID'),
    ('the environment template prints the environment',says(k6a.is_environment,fixed(0,('["DB_PASSWORD=%s"]\n'%hostemu.SECRET).encode())),'DOCUMENT_TYPE'),
    ('the environment template fails',says(k6a.is_environment,fixed(1,b'')),'COMMAND_FAILED'),
    ('the listing does not show the worker',says(k6a.is_list,listing(other_name)),'CONTAINER_LIST_INCONSISTENT'),
    ('the listing shows the name of the worker with another ID',says(k6a.is_list,listing(lambda rows:[row.update(id='e'*64) for row in rows if row['name']==hostemu.WORKER] and None)),'CONTAINER_LIST_INCONSISTENT'),
    ('the listing shows the name of the worker twice',says(k6a.is_list,listing(twice)),'CONTAINER_LIST_INCONSISTENT'),
    ('the listing shows one ID twice',says(k6a.is_list,listing(same_id_twice)),'CONTAINER_LIST_INVALID'),
    ('the listing has a line that is not JSON',says(k6a.is_list,fixed(0,b'CONTAINER ID   IMAGE\n')),'JSON_INVALID'),
    ('the listing has a row with an unknown state',says(k6a.is_list,listing(lambda rows:rows[0].update(state='up'))),'CONTAINER_LIST_INVALID'),
    ('the listing has a row with another member',says(k6a.is_list,listing(lambda rows:rows[0].update(image='x'))),'CONTAINER_LIST_INVALID'),
    ('the listing has more rows than the limit',says(k6a.is_list,listing(lambda rows:rows+[{'id':'%064x'%index,'name':'n%d'%index,'state':'exited'} for index in range(130)])),'CONTAINER_LIST_INVALID'),
    ('the render exits 0 with an error text',says(k6a.is_render,fixed(0,b'no configuration file provided: not found\n')),'COMPOSE_RENDER_INVALID'),
    ('the render exits 14',says(k6a.is_render,fixed(14,b'')),'COMMAND_FAILED'),
    ('the render answers with an empty object',says(k6a.is_render,fixed(0,b'{}\n')),'COMPOSE_RENDER_INVALID'),
]
@pytest.mark.parametrize('label,prepare,code',ANSWERS,ids=[case[0] for case in ANSWERS])
def test_hostile_answers_of_the_docker_cli_refuse_before_any_effect(label,prepare,code):
    receipt=refused(prepare,code);assert hostemu.SECRET not in json.dumps(receipt)

# ---------------------------------------------------------------- what changes between the first look and the lock
def restarted(host):k6a.worker(host)['State']['StartedAt']='2026-10-05T08:49:59.000000000Z'
def recreated(host):k6a.worker(host)['Id']='b'*64
def counted(host):k6a.worker(host)['RestartCount']=1
def stopped(host):k6a.worker(host)['State'].update(Status='exited',Running=False)
def rewritten(host):host.tree.get(hostemu.ENV_FILE).mtime+=1                       # the same bytes, written again
def edited_in_place(host):                                                         # other bytes of the same length, every stat value kept
    node=host.tree.get(hostemu.ENV_FILE);node.content=bytearray(bytes(node.content).replace(b'canary',b'CANARY'))
def env_replaced(host):
    raw=bytes(host.tree.get(hostemu.ENV_FILE).content);k6a.replace(host,hostemu.ENV_FILE,'file',uid=1000,gid=1000,mode=0o600,content=raw)
def release_replaced(host):k6a.replace(host,RELEASE_FILE,'file',mode=0o600,content=k6a.RELEASE)      # the same bytes in a new file
def release_rewritten(host):host.tree.get(RELEASE_FILE).content=bytearray(k6a.RELEASE[:-1]+b'x')
def redeployed(host):host.tree.get(VERSION).content=bytearray(b'4de7095ad51bce19ea4b685d5c708d0a72986d76\n')
def compose_rewritten(host):host.tree.get(hostemu.COMPOSE_FILE).mtime+=1                # the same bytes, written again
def compose_edited_in_place(host):                                                 # other bytes of the same length, every stat value kept
    node=host.tree.get(hostemu.COMPOSE_FILE);node.content=bytearray(bytes(node.content).replace(b'{}',b'[]'))
def compose_replaced(host):
    raw=bytes(host.tree.get(hostemu.COMPOSE_FILE).content);k6a.replace(host,hostemu.COMPOSE_FILE,'file',uid=1000,gid=1000,mode=0o644,content=raw)
def project_changed(host):
    """What a deploy that ends while this run waits for the lock does: the compose file is another, and so is the render."""
    host.docker.compose.base['services']['r2d2-worker']['volumes'][1]['source']='/mnt/elsewhere'
    k6a.replace(host,hostemu.COMPOSE_FILE,'file',uid=1000,gid=1000,mode=0o644,content=b'services: {another: {}}\n')
def release_directory_swapped(host):k6a.swap_directory(host,k6a.RELEASE_DIRECTORY,content=b'{"other":"bytes"}')
def release_directory_swapped_for_a_copy(host):k6a.swap_directory(host,k6a.RELEASE_DIRECTORY)
def project_directory_swapped(host):k6a.swap_directory(host,k6a.PROJECT_DIRECTORY)
def lock_directory_swapped(host):k6a.swap_directory(host,hostemu.LOCK_DIRECTORY)
def deploy_tree_reowned(host):host.tree.get(hostemu.DEPLOY).mode=0o750
def data_root_reowned(host):host.tree.get(hostemu.DATA).gid=0
BETWEEN=[
    ('the compose file was written again',compose_rewritten,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK'),('the compose file was edited in place',compose_edited_in_place,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK'),
    ('the compose file was replaced by a copy',compose_replaced,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK'),('the compose file was removed',gone(hostemu.COMPOSE_FILE),'COMPOSE_FILE_ABSENT'),
    ('a deploy changed the project',project_changed,'COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK'),
    ('the release directory was swapped by name for other bytes',release_directory_swapped,'RELEASE_DIRECTORY_REPLACED'),
    ('the release directory was swapped by name for a copy',release_directory_swapped_for_a_copy,'RELEASE_DIRECTORY_REPLACED'),
    ('the project directory was swapped by name',project_directory_swapped,'DEPLOY_TREE_REPLACED'),('the deploy tree changed its mode',deploy_tree_reowned,'DEPLOY_TREE_REPLACED'),
    ('the lock directory was swapped by name',lock_directory_swapped,'LOCK_DIRECTORY_REPLACED'),('the data root changed its group',data_root_reowned,'RELEASE_DIRECTORY_REPLACED'),
    ('the worker restarted',restarted,'WORKER_CHANGED_BEFORE_THE_LOCK'),('the worker was recreated by someone else',recreated,'WORKER_CHANGED_BEFORE_THE_LOCK'),
    ('the worker counted a restart',counted,'WORKER_CHANGED_BEFORE_THE_LOCK'),('the worker stopped',stopped,'WORKER_CHANGED_BEFORE_THE_LOCK'),
    ('the environment file was written again',rewritten,'ENV_FILE_CHANGED_BEFORE_THE_LOCK'),('the environment file was edited in place',edited_in_place,'ENV_FILE_CHANGED_BEFORE_THE_LOCK'),
    ('the environment file was replaced by a copy',env_replaced,'ENV_FILE_CHANGED_BEFORE_THE_LOCK'),
    ('the release was replaced by a copy',release_replaced,'RELEASE_CHANGED_BEFORE_THE_LOCK'),('the release was rewritten',release_rewritten,'RELEASE_HASH_MISMATCH'),
    ('another revision was deployed',redeployed,'DEPLOY_VERSION_MISMATCH'),('a reboot became pending',put(k6a.PENDING,'file'),'SECURITY_REBOOT_PENDING'),
    ('the release was removed',gone(RELEASE_FILE),'RELEASE_NOT_INSTALLED'),('the environment file was removed',gone(hostemu.ENV_FILE),'ENV_FILE_ABSENT'),
]
@pytest.mark.parametrize('label,action,code',BETWEEN,ids=[case[0] for case in BETWEEN])
def test_what_changes_between_the_first_look_and_the_lock_refuses_before_any_effect(label,action,code):
    """The change is made right before the image reference of the render is resolved: after everything was read once,
    before the lock is asked for. What is read again under the lock finds it."""
    def prepare(host):k6a.during(host,k6a.is_image,action,nth=2)
    refused(prepare,code,same=False)

def test_release_swapped_by_name_is_refused_although_the_descriptor_held_still_shows_the_signed_bytes():
    """The data root belongs to the operational account: it can rename the release directory away and put another
    under the name. Every read through the descriptor held would still find the signed bytes, and the path written
    into the worker's environment would hold others. The name is proved again under the lock."""
    m,docs,host=k6a.fresh();k6a.during(host,k6a.is_image,release_directory_swapped,nth=2);before=k6a.worker(host)['Id'];receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','RELEASE_DIRECTORY_REPLACED','PRECHECK') and host.mutating()==[]
    assert bytes(host.tree.get(RELEASE_FILE).content)!=k6a.RELEASE and bytes(host.tree.get(k6a.RELEASE_DIRECTORY+'.moved-away/'+k6a.RELEASE_NAME).content)==k6a.RELEASE
    assert k6a.worker(host)['Id']==before and host.tree.get(k6a.LIVE) is None and host.fds=={}

def test_edit_of_the_compose_file_that_keeps_every_stat_value_is_still_seen():
    m,docs,host=k6a.fresh();node=host.tree.get(hostemu.COMPOSE_FILE);before=node.stat()
    k6a.during(host,k6a.is_image,compose_edited_in_place,nth=2);receipt=docs.run(host);after=node.stat()
    assert (before.st_size,before.st_mtime_ns,before.st_ctime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns,after.st_ino)
    assert (receipt['status'],receipt['code'])==('REFUSED','COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK') and host.mutating()==[]

def test_edit_of_the_environment_file_that_keeps_every_stat_value_is_still_seen():
    """The signature alone would not see it: the bytes are hashed in memory and compared."""
    m,docs,host=k6a.fresh();node=host.tree.get(hostemu.ENV_FILE);before=node.stat()
    k6a.during(host,k6a.is_image,edited_in_place,nth=2);receipt=docs.run(host);after=node.stat()
    assert (before.st_size,before.st_mtime_ns,before.st_ctime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns,after.st_ino)
    assert (receipt['status'],receipt['code'])==('REFUSED','ENV_FILE_CHANGED_BEFORE_THE_LOCK') and host.mutating()==[]
