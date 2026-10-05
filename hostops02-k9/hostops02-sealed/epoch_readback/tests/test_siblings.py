"""K11 against the two writes it rehearses, as their sources stand beside it: install_release (K10) and activate (K6a).
The dry run is worth what its predicates are worth: they must be the predicates of those two sources, not a reading of
them. Every test here loads the sibling's own assembled source and compares constants, bytes and verdicts. A sibling
that is not there (the private copies of a mutation run, a directory moved alone) skips its tests; a sibling that is
there and disagrees fails them, and then one of the two sources is wrong for Monday.
Binding step: this file is run again, by command, after the siblings are sealed (CONTRACT.txt section 8)."""
import copy
import json
import sys
import types

import pytest

import family as f
import hostemu
import k11

SIBLINGS=k11.DIRECTORY.parent
def sibling(name):
    directory=SIBLINGS/name
    if not (directory/'build'/'ASSEMBLY.json').is_file():pytest.skip('the sibling operation %s is not beside this one'%name)
    return f.load(directory)
def own():return f.load(k11.DIRECTORY).m
def activate_plan():
    """What activate's pure helpers read of its plan, for the places and values the K11 fixture signs."""
    return {'data_root':hostemu.DATA,'live_parent':[{'path':k11.LIVE_PARENT}],'directory_name':k11.LIVE_NAME,'policy':{'name':'policy.json','sha256':f.sha(k11.POLICY)},
            'release':{'parent':[{'path':hostemu.DATA}],'directory_name':k11.RELEASE_DIRECTORY,'file_name':k11.RELEASE_FILE,'sha256':f.sha(k11.RELEASE)},
            'worker':{'image_id':hostemu.BACKEND,'mount_target':k11.DATA_TARGET},'compose':{'project':hostemu.PROJECT}}

def test_constants_this_source_shares_with_install_release_and_activate_are_equal():
    m=own();a=sibling('activate').m;i=sibling('install_release').m
    assert m.CORE_SHA256==a.CORE_SHA256==i.CORE_SHA256,'the three sources of Monday are assembled from one core generation'
    assert tuple(m.LIVE_KEYS)==tuple(a.ACTIVATION_KEYS) and (m.BUILD_KEY,m.WORKER_SERVICE)==(a.BUILD_KEY,a.WORKER_SERVICE)
    assert (m.MONDAY_ENV_FILE,m.MONDAY_COMPOSE_FILE,m.MONDAY_VERSION_NAME,m.MONDAY_LOCK_DIRECTORY,m.MONDAY_LOCK_NAME)==(
        a.ENV_FILE_NAME,a.COMPOSE_FILE_NAME,a.DEPLOY_VERSION_NAME,a.LOCK_RELATIVE_DIRECTORY,a.LOCK_FILE_NAME)
    assert (m.MONDAY_DATA_VOLUME,m.MONDAY_DATA_TARGET,m.MONDAY_RELEASE_DIRECTORY,m.MONDAY_RELEASE_FILE)==(i.DATA_VOLUME,i.CONTAINER_DATA_VOLUME,i.RELEASE_DIRECTORY_NAME,i.RELEASE_FILE_NAME)
    assert m.PIN_NAME==a.PIN_NAME==i.MAINTENANCE_PIN_NAME and m.REBOOT_PENDING==a.REBOOT_PENDING_PATH
    assert m.EPOCH_NAME==a.EPOCH_NAME==i.RELEASE_EPOCH and m.FIRST_SESSION_DAY==i.FIRST_SESSION and m.RUNTIME_ORDER_SHA256==a.RUNTIME_ORDER_SHA256
    assert (hostemu.REVISION,k11.PACKAGE)==(a.EPOCH_REVISION,a.EPOCH_PACKAGE_SHA256) and (m.RELEASE_SCHEMA_NAME,m.POLICY_SCHEMA_NAME)==(i.RELEASE_SCHEMA_NAME,a.LIVE_POLICY_SCHEMA)
    assert (m.RELEASE_DIRECTORY_MODE,m.RELEASE_FILE_MODE)==(i.PRIVATE_DIRECTORY_MODE,i.PRIVATE_FILE_MODE)==(a.PRIVATE_DIRECTORY_MODE,a.PRIVATE_FILE_MODE)
    assert m.MAX_RENDERED_VOLUMES==64 and 'len(volumes)<=64' in (SIBLINGS/'activate'/'op.py').read_text()
    # the floors a full dry run signs are the constants of the two writes (CONTRACT.txt section 7); the fixture carries them
    assert k11.LIMITS['data_volume_free_bytes']==i.FREE_BYTES_FLOOR==a.FREE_BYTES_FLOOR and k11.LIMITS['data_volume_free_inodes']==a.FREE_INODES_FLOOR
    for numbers in (dict(f_files=1000,f_favail=7),dict(f_files=0,f_favail=0),dict(f_files=1000),dict(f_files=1000,f_favail=True),dict(f_files=None,f_favail=3),dict(f_favail=3),{},
                    dict(f_files=10**12,f_favail=10**11)):
        host=types.SimpleNamespace(fstatvfs=lambda fd:types.SimpleNamespace(**numbers));assert m.free_inodes(host,3)==a.free_inodes(host,3),numbers
    for name in ('0123456789ab_'+hostemu.WORKER,'other-'+hostemu.WORKER,hostemu.WORKER+'_old',hostemu.WORKER,'_'+hostemu.WORKER,'x_c3po-r2d2-shadow-candidate-worker-1','ab_'+hostemu.WORKER+'0'):
        rows=[{'id':'a'*64,'name':name,'state':'exited'}];assert bool(a.leftovers(rows,hostemu.WORKER))==name.endswith('_'+hostemu.WORKER)
    assert m.MAX_RELEASE_BYTES<=i.MAX_RELEASE_BYTES<=m.MAX_INSTALLED_BYTES==a.MAX_RELEASE_BYTES,'a release the dry run can carry is one install_release can install'

def test_override_a_full_dry_run_signs_is_byte_for_byte_the_file_activate_writes():
    m=own();a=sibling('activate').m;plan=activate_plan();environment=a.environment_of(plan)
    assert environment==json.loads(k11.override_bytes())['services']['r2d2-worker']['environment']
    assert a.override_of(plan)==k11.override_bytes()==m.activate_override(environment)
    assert a.worker_name(plan)==hostemu.WORKER=='%s-%s-1'%(hostemu.PROJECT,m.WORKER_SERVICE)
    assert a.plain('/app//day-d-data/.')==m.plain('/app//day-d-data/.')=='/app/day-d-data' and a.plain(None) is m.plain(None) is None and m.plain(7)==a.plain(7)==7

def test_rule_for_the_bind_of_the_data_volume_gives_the_verdict_of_activate_on_every_case():
    """The differential: activate's own service_of() and this source's data_bind_of() on the same renders."""
    import test_readback
    m=own();a=sibling('activate').m;plan=activate_plan();environment=a.environment_of(plan)
    for change,code,bound in test_readback.VOLUMES:
        worker={'image':'c3po/backend:production','environment':dict(environment,C3PO_BUILD_SHA=hostemu.REVISION),
                'volumes':[{'type':'bind','source':hostemu.DATA,'target':k11.DATA_TARGET,'bind':{'create_host_path':True}}]}
        change(worker);rendered={'services':{'r2d2-worker':worker}}
        try:a.service_of(copy.deepcopy(rendered),plan);verdict=None
        except a.Refused as error:verdict=str(error)
        found=m.data_bind_of(worker.get('volumes'),[environment[m.LIVE_KEYS[0]],environment[m.LIVE_KEYS[2]]],hostemu.DATA,k11.DATA_TARGET)
        assert verdict==code=={None:'RENDER_VOLUMES_INVALID',False:'WORKER_MOUNT_NOT_AS_SIGNED',True:None}[found] and found is bound,(code,verdict,found)

def test_rows_the_dry_run_calls_acceptable_are_rows_install_release_and_activate_accept():
    m=own();a=sibling('activate').m;i=sibling('install_release').m
    def judged(rows,module,volume):
        try:module.validate_chain(copy.deepcopy(rows),rows[-1]['path'],open_root=hostemu.DATA,receives_entry=True)
        except module.Refused as error:return str(error)
        return None if volume is None or module.mount_point_of(rows)==volume else 'DATA_VOLUME_NOT_A_MOUNT_POINT'
    states=[lambda host:None,lambda host:setattr(host.tree.get(hostemu.DATA),'mode',0o777),lambda host:setattr(host.tree.get(hostemu.DATA),'mode',0o2775),
            lambda host:setattr(host.tree.get(hostemu.DATA),'mode',0o1777),lambda host:setattr(host.tree.get('/mnt'),'mode',0o775),lambda host:setattr(host.tree.get('/mnt'),'uid',1000),
            lambda host:setattr(host.tree.get(k11.LIVE_PARENT),'mode',0o2700),lambda host:setattr(host.tree.get(k11.LIVE_PARENT),'mode',0o777),
            lambda host:(setattr(host.tree.get(hostemu.DATA),'dev',hostemu.ROOT_DEVICE),host.vfs.__setitem__(hostemu.ROOT_DEVICE,host.vfs[hostemu.DATA_DEVICE]))]
    for prepare in states:
        docs,host=k11.case('PRE',signed_rows=False);prepare(host);receipt=docs.run(host)
        release,live=receipt['items']['directory:RELEASE_PARENT'],receipt['items']['directory:LIVE_PARENT']
        assert release['rows_refusal']==judged(hostemu.rows(host,hostemu.DATA),i,i.DATA_VOLUME) and release['rows_acceptable_to_a_write'] is (release['rows_refusal'] is None)
        assert live['rows_refusal']==judged(hostemu.rows(host,k11.LIVE_PARENT),a,None) and live['rows_acceptable_to_a_write'] is (live['rows_refusal'] is None)
        assert ('DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS' in receipt['findings']) is (release['rows_refusal'] is not None or live['rows_refusal'] is not None)

def test_revision_file_the_readback_accepts_is_one_activate_accepts_and_the_other_way_round():
    path=str(SIBLINGS/'activate'/'tests');sibling('activate');sys.path.insert(0,path)
    try:import k6a
    finally:sys.path.remove(path)
    version=hostemu.DEPLOY+'/.deploy-version'
    for content in ((hostemu.REVISION+'\n').encode(),hostemu.REVISION.encode(),hostemu.REVISION.encode()+b'\r\n',b' '+hostemu.REVISION.encode()+b'\n\n',
                    hostemu.REVISION.encode()+b'\n'*88,hostemu.REVISION.encode()+b'\n'*89,hostemu.REVISION[:39].encode()+b'\n',hostemu.REVISION.encode()+b'0\n',hostemu.REVISION.upper().encode()+b'\n',b'\n',b'0'*40+b'\n'):
        m,docs,host=k6a.fresh();host.tree.get(version).content=bytearray(content);accepted=docs.run(host)['status']==m.COMPLETE_STATUS
        docs,host=k11.case('POST');host.tree.get(version).content=bytearray(content);receipt=docs.run(host)
        assert (receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW') is accepted,(content,receipt['findings'],receipt['items_not_complete'])
    assert own().MAX_REVISION_FILE_BYTES==128 and 'DEPLOY_VERSION_NAME,directory.fd,gate,128)' in (SIBLINGS/'activate'/'op.py').read_text()

def test_limits_the_fixture_signs_leave_activate_its_budget_on_its_own_emulated_run():
    """activate's own source on its own fixture, with every quick docker read as slow as the signed quick_ms and each
    render as slow as the signed render_ms: it must still reach its recreate and complete. One millisecond beyond is
    what the dry run reports as a finding; the figures here are what makes the proposed limits (3000, 1500) safe."""
    path=str(SIBLINGS/'activate'/'tests');sibling('activate');sys.path.insert(0,path)
    try:import k6a
    finally:sys.path.remove(path)
    quick,render=k11.LIMITS['quick_ms']/1000.0,k11.LIMITS['render_ms']/1000.0
    m,docs,host,budget=k6a.timed(quick);budget.cost(render,'config').cost(23.0,'up');receipt=docs.run(host,**budget.options())
    assert receipt['status']==m.COMPLETE_STATUS,(receipt['code'],receipt.get('budget'))
    figures=receipt['budget'];assert figures['first_render_milliseconds']==k11.LIMITS['render_ms']
    assert figures['left_when_the_lock_was_asked_for_milliseconds']>figures['kept_while_waiting_for_the_lock_seconds']*1000
    assert figures['left_before_first_effect_milliseconds']>=figures['needed_before_first_effect_seconds']*1000+2000,'two seconds of slack at the last refusal before the first effect'
    # and a host twice as slow as the limits is one activate refuses on before any effect: the dry run would have said so
    m,docs,host,budget=k6a.timed(2*quick);budget.cost(2*render,'config').cost(23.0,'up');receipt=docs.run(host,**budget.options())
    assert receipt['status']=='REFUSED' and receipt['code'] in ('LOCK_NOT_TAKEN_BUDGET','BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT') and host.mutating()==[]

def test_what_activate_and_install_release_refuse_on_before_any_effect_is_a_finding_of_the_full_dry_run():
    """The same host states, put to the sibling's own source on its own fixture and to the dry run on its fixture."""
    path=str(SIBLINGS/'activate'/'tests');sibling('activate');sys.path.insert(0,path)
    try:import k6a
    finally:sys.path.remove(path)
    def carries(host):host.docker.container(hostemu.WORKER)['Config']['Env'].append(k11.KEYS[0]+'=')
    def stands(host):host.tree.add(k11.LIVE_HOST,dev=hostemu.DATA_DEVICE,mode=0o700)
    def read_only(host):
        for item in host.docker.compose.base['services']['r2d2-worker']['volumes']:
            if item['target']==k11.DATA_TARGET:item['read_only']=True
    def pending(host):host.tree.add('/run/c3po-security/reboot.pending',kind='file')
    def no_pin(host):host.tree.remove(hostemu.PIN)
    def leftover(host):host.docker.containers.append(hostemu.container('0123456789ab_'+hostemu.WORKER,hostemu.BACKEND,'c3po/backend:production',[],running=False))
    def volume(**numbers):
        def prepare(host):
            old=host.vfs[hostemu.DATA_DEVICE];host.vfs[hostemu.DATA_DEVICE]=types.SimpleNamespace(**dict(dict(f_frsize=old.f_frsize,f_blocks=old.f_blocks,f_bfree=old.f_bfree,f_bavail=old.f_bavail),**numbers))
        return prepare
    def no_version(host):host.tree.remove(hostemu.DEPLOY+'/.deploy-version')
    def no_compose_file(host):host.tree.remove(hostemu.COMPOSE_FILE)
    def no_lock(host):host.tree.remove(hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME)
    def stopped(host):host.docker.container(hostemu.WORKER)['State'].update(Status='exited',Running=False)
    assert (k6a.LIVE,k6a.TARGET)==(k11.LIVE_HOST,k11.DATA_TARGET)
    for prepare,refusal,finding in ((carries,'WORKER_ALREADY_CARRIES_THE_KEYS','WORKER_ALREADY_CARRIES_A_LIVE_NAME'),(stands,'DESTINATION_PRESENT','LIVE_DIRECTORY_ALREADY_EXISTS'),
                                    (read_only,'WORKER_MOUNT_NOT_AS_SIGNED','WORKER_MOUNT_NOT_AS_SIGNED'),(pending,'SECURITY_REBOOT_PENDING','REBOOT_PENDING_MARKER_PRESENT'),
                                    (leftover,'WORKER_SERVICE_LEFTOVER_CONTAINER','WORKER_SERVICE_LEFTOVER_CONTAINER'),(volume(f_bavail=0),'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR','DATA_VOLUME_FREE_SPACE_BELOW_FLOOR'),
                                    (volume(f_files=1000,f_favail=7),'DATA_VOLUME_FREE_INODES_BELOW_FLOOR','DATA_VOLUME_FREE_INODES_BELOW_FLOOR'),
                                    (no_version,'DEPLOY_VERSION_ABSENT','DEPLOYED_REVISION_FILE_ABSENT'),(no_compose_file,'COMPOSE_FILE_ABSENT','COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR'),
                                    (no_lock,'LOCK_FILE_ABSENT','LOCK_FILE_ABSENT'),(stopped,'WORKER_NOT_RUNNING','WORKER_NOT_RUNNING'),
                                    (no_pin,'MAINTENANCE_PIN_ABSENT','MAINTENANCE_PIN_ABSENT')):
        m,docs,host=k6a.fresh();prepare(host);receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED',refusal) and host.mutating()==[]
        docs,host=k11.case('PRE');prepare(host);receipt=docs.run(host);assert finding in receipt['findings'] and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW',(refusal,receipt['findings'])
    # and a host on which neither source finds anything: activate completes on its fixture, the full dry run on its own
    m,docs,host=k6a.fresh();assert docs.run(host)['status']==m.COMPLETE_STATUS
    docs,host=k11.case('PRE');receipt=docs.run(host);assert receipt['findings']==[] and receipt['outcome']==own().PRE_OUTCOME

def test_what_install_release_refuses_on_before_any_effect_is_a_finding_of_the_full_dry_run():
    path=str(SIBLINGS/'install_release'/'tests');sibling('install_release');sys.path.insert(0,path)
    try:import k10
    finally:sys.path.remove(path)
    def foreign_pin(host):host.tree.get(hostemu.PIN).uid=1000
    def no_pin(host):host.tree.remove(hostemu.PIN)
    def stands(host):host.tree.add(k11.RELEASE_HOST,dev=hostemu.DATA_DEVICE,mode=0o700)
    def full(host):
        old=host.vfs[hostemu.DATA_DEVICE];host.vfs[hostemu.DATA_DEVICE]=types.SimpleNamespace(f_frsize=old.f_frsize,f_blocks=old.f_blocks,f_bfree=0,f_bavail=0)
    assert (k10.BASE,k10.NAME)==(k11.RELEASE_HOST,k11.RELEASE_FILE)
    for prepare,refusal,finding in ((foreign_pin,'MAINTENANCE_PIN_NOT_ROOT_OWNED','MAINTENANCE_PIN_NOT_ROOT_OWNED'),(no_pin,'MAINTENANCE_PIN_ABSENT','MAINTENANCE_PIN_ABSENT'),
                                    (stands,'DESTINATION_PRESENT','RELEASE_TARGET_ALREADY_EXISTS'),(full,'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR','DATA_VOLUME_FREE_SPACE_BELOW_FLOOR')):
        docs,host=k10.case();prepare(host);receipt=docs.run(host);assert (receipt['status'],receipt['code'])==('REFUSED',refusal) and host.mutating()==[],receipt['code']
        docs,host=k11.case('PRE');prepare(host);receipt=docs.run(host);assert receipt['findings']==[finding] and receipt['outcome']=='OBSERVED_ALL_EXPECTATIONS_NOT_MET'


# ---------------------------------------------------------------- the inventory: no refusal of a write goes unaccounted for
# Every constant code in the two sibling sources, with where this source stands to it. The siblings were still being
# repaired when this was written: a code that appears in one of them and is not in these tables fails the test below,
# and whoever binds Monday then decides, here and in writing, whether the dry run must find the state behind it.
#   FOUND    a state of the host before the write's first effect; the dry run finds it under the names given
#   BINDING  refused from the bytes of the write's own request, locally, before any claim: no host state
#   INSTANT  a change between two looks of the write's own run, or the clock of that run: nothing a read on another day can see
#   AFTER    the write's own effects and their readback
#   WORD     an upper-case word of the source that is no code
FOUND,BINDING,INSTANT,AFTER,WORD='FOUND','BINDING','INSTANT','AFTER','WORD'
ACTIVATE={
 'EXECUTOR_IDENTITY':(FOUND,['EXECUTOR_IDENTITY']),'EVIDENCE_FROM_EARLIER_BOOT':(FOUND,['EVIDENCE_FROM_EARLIER_BOOT']),'DESTINATION_PRESENT':(FOUND,['LIVE_DIRECTORY_ALREADY_EXISTS']),
 'MAINTENANCE_PIN_ABSENT':(FOUND,['MAINTENANCE_PIN_ABSENT','MAINTENANCE_PIN_NOT_REGULAR']),'RELEASE_NOT_INSTALLED':(FOUND,['RELEASE_DIRECTORY_ABSENT','RELEASE_FILE_ABSENT']),
 'RELEASE_DIRECTORY_NOT_AS_INSTALLED':(FOUND,['RELEASE_DIRECTORY_NOT_A_DIRECTORY','RELEASE_DIRECTORY_METADATA','RELEASE_DIRECTORY_IS_A_MOUNT_POINT']),
 'RELEASE_FILE_NOT_AS_INSTALLED':(FOUND,['RELEASE_FILE_NOT_REGULAR','RELEASE_FILE_METADATA']),'RELEASE_HASH_MISMATCH':(FOUND,['RELEASE_FILE_BYTES_MISMATCH']),
 'DEPLOY_VERSION_ABSENT':(FOUND,['DEPLOYED_REVISION_FILE_ABSENT']),'DEPLOY_VERSION_NOT_REGULAR':(FOUND,['FILE_NOT_REGULAR']),'DEPLOY_VERSION_MISMATCH':(FOUND,['DEPLOYED_REVISION_MISMATCH']),
 'ENV_FILE_ABSENT':(FOUND,['COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR']),'ENV_FILE_NOT_REGULAR':(FOUND,['COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR']),
 'COMPOSE_FILE_ABSENT':(FOUND,['COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR']),'COMPOSE_FILE_NOT_REGULAR':(FOUND,['COMPOSE_INPUT_ABSENT_OR_NOT_REGULAR']),
 'COMPOSE_DIRECTORY_NOT_A_DIRECTORY':(FOUND,['COMPONENT_NOT_DIRECTORY','SYMLINK_COMPONENT']),
 'WORKER_NOT_RUNNING':(FOUND,['WORKER_NOT_RUNNING']),'WORKER_IMAGE_NOT_THE_SIGNED_ONE':(FOUND,['WORKER_IMAGE_MISMATCH']),'IMAGE_ABSENT_OR_UNREADABLE':(FOUND,['VERIFY_ENGINE_FAILURE','IMAGE_ID_MISMATCH']),
 'IMAGE_REVISION_MISMATCH':(FOUND,['IMAGE_REVISION_MISMATCH','IMAGE_ID_MISMATCH']),'WORKER_BUILD_REVISION':(FOUND,['WORKER_BUILD_REVISION_MISMATCH']),
 'WORKER_ALREADY_CARRIES_THE_KEYS':(FOUND,['WORKER_ALREADY_CARRIES_A_LIVE_NAME']),'RENDER_BUILD_REVISION':(FOUND,['RENDER_BUILD_REVISION_MISMATCH']),
 'RENDER_ENVIRONMENT_MISMATCH':(FOUND,['RENDER_ENVIRONMENT_NOT_AS_SIGNED']),'RENDER_IMAGE_INVALID':(FOUND,['RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE']),
 'RENDER_IMAGE_UNRESOLVED':(FOUND,['RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE','IMAGE_ID_MISMATCH']),'RENDER_IMAGE_CHANGED':(FOUND,['RENDER_IMAGE_NOT_THE_SIGNED_REFERENCE','IMAGE_ID_MISMATCH']),
 'RENDER_VOLUMES_INVALID':(FOUND,['RENDER_VOLUMES_INVALID']),'WORKER_MOUNT_NOT_AS_SIGNED':(FOUND,['WORKER_MOUNT_NOT_AS_SIGNED']),'SECURITY_REBOOT_PENDING':(FOUND,['REBOOT_PENDING_MARKER_PRESENT']),
 'REBOOT_STATE_UNAVAILABLE':(FOUND,['SYMLINK_COMPONENT']),'WORKER_SERVICE_LEFTOVER_CONTAINER':(FOUND,['WORKER_SERVICE_LEFTOVER_CONTAINER']),
 'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR':(FOUND,['DATA_VOLUME_FREE_SPACE_BELOW_FLOOR']),'DATA_VOLUME_FREE_INODES_BELOW_FLOOR':(FOUND,['DATA_VOLUME_FREE_INODES_BELOW_FLOOR']),
 'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT':(FOUND,['DOCKER_CALL_SLOWER_THAN_THE_SIGNED_LIMIT','RENDER_SLOWER_THAN_THE_SIGNED_LIMIT']),
 **{code:(BINDING,None) for code in ('CHAIN_ROW_INVALID','COMPOSE_NOT_THE_DEPLOY_LAYOUT','COMPOSE_REQUEST_INVALID','DIRECTORY_NAME_INVALID','EVIDENCE_BOOT_UNBOUND','FILE_PATH_INVALID',
    'LIVE_PARENT_OUTSIDE_DATA_ROOT','LOCK_NOT_THE_DEPLOYMENT_LOCK','LOCK_REQUEST_INVALID','OVERRIDE_NAME_INVALID','PATHS_OVERLAP','PATH_INVALID','POLICY_BYTES_NOT_THE_SIGNED_HASH',
    'POLICY_CAPACITY','POLICY_IDENTITY','POLICY_JSON_INVALID','POLICY_NOT_EPOCH_WIDE','POLICY_PACKAGE','POLICY_RECERTIFICATION','POLICY_REQUEST_INVALID','POLICY_REVISION',
    'POLICY_RUNTIME_ORDER','POLICY_SCHEMA','POLICY_WINDOW','POLICY_WINDOW_DOES_NOT_COVER_THE_GO','RELEASE_OUTSIDE_DATA_ROOT','RELEASE_REQUEST_INVALID','WORKER_REQUEST_INVALID')},
 **{code:(INSTANT,None) for code in ('COMPOSE_FILE_CHANGED_BEFORE_THE_LOCK','ENV_FILE_CHANGED_BEFORE_THE_LOCK','RELEASE_CHANGED_BEFORE_THE_LOCK','WORKER_CHANGED_BEFORE_THE_LOCK',
    'DEPLOY_TREE_REPLACED','LOCK_DIRECTORY_REPLACED','RELEASE_DIRECTORY_REPLACED','LOCK_FILE_REPLACED','CONTAINER_LIST_INCONSISTENT','PRECHECK_FAILED')},
 **{code:(AFTER,None) for code in ('COMMAND_NOT_STARTED','CREATION_FAILED','INSTALL_FAILED','COMPOSE_FILE_CHANGED','ENV_FILE_CHANGED','RELEASE_CHANGED','ENVIRONMENT_NOT_AS_SIGNED',
    'FILES_NOT_AS_DELIVERED','OLD_CONTAINER_STILL_PRESENT','OTHER_CONTAINERS_CHANGED','READBACK_FAILED','READBACK_UNAVAILABLE','RECREATED_NOT_VERIFIED','RECREATE_FAILED_CONTAINER_UNCHANGED',
    'RECREATE_PRECHECK_FAILED','RECREATE_RETURNED_NONZERO','RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED','SECOND_CHECK_NOT_APART','WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS',
    'WORKER_IMAGE_CHANGED','WORKER_NOT_FOUND_AFTER_RECREATE','WORKER_NOT_RECREATED','WORKER_NOT_RUNNING_AFTER_RECREATE')},
 'READ':(WORD,None)}
INSTALL_RELEASE={
 'EXECUTOR_IDENTITY':(FOUND,['EXECUTOR_IDENTITY']),'EVIDENCE_FROM_EARLIER_BOOT':(FOUND,['EVIDENCE_FROM_EARLIER_BOOT']),'DESTINATION_PRESENT':(FOUND,['RELEASE_TARGET_ALREADY_EXISTS']),
 'MAINTENANCE_PIN_ABSENT':(FOUND,['MAINTENANCE_PIN_ABSENT']),'MAINTENANCE_PIN_NOT_A_REGULAR_FILE':(FOUND,['MAINTENANCE_PIN_NOT_REGULAR']),
 'MAINTENANCE_PIN_NOT_ROOT_OWNED':(FOUND,['MAINTENANCE_PIN_NOT_ROOT_OWNED']),'DATA_VOLUME_FREE_SPACE_BELOW_FLOOR':(FOUND,['DATA_VOLUME_FREE_SPACE_BELOW_FLOOR']),
 'DATA_VOLUME_NOT_A_MOUNT_POINT':(FOUND,['DATA_VOLUME_NOT_A_MOUNT_POINT','DIRECTORY_NOT_ACCEPTABLE_TO_THE_WRITE_THAT_FOLLOWS']),
 **{code:(BINDING,None) for code in ('EVIDENCE_BOOT_UNBOUND','RELEASE_BYTES_NOT_THE_SIGNED_HASH','RELEASE_EPOCH_NOT_THIS_EPOCH','RELEASE_FIELDS_INVALID','RELEASE_FIRST_SESSION_NOT_THIS_EPOCH',
    'RELEASE_NOT_A_CERTIFIED_V3_RELEASE','RELEASE_NOT_JSON','RELEASE_PATH_NOT_THE_SIGNED_CONSTANT','RELEASE_PLAN_INVALID','WINDOW_NOT_ON_THE_FIRST_SESSION_DAY_IN_NEW_YORK')},
 **{code:(INSTANT,None) for code in ('BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT','NOT_THE_FIRST_SESSION_DAY_IN_NEW_YORK','PRECHECK_FAILED')},
 **{code:(AFTER,None) for code in ('CREATION_FAILED','INSTALL_FAILED','READBACK_UNAVAILABLE')}}
def codes_of(path):
    """Every upper-case word a source gives as a code: the last argument of a need(), the argument of a Refused(), the
    name of a criterion, a fallback after `or` / `else`, a `stop=`."""
    import re
    text=path.read_text();found=set()
    for pattern in (r",\s*'([A-Z][A-Z0-9_]{3,})'\)",r"Refused\('([A-Z][A-Z0-9_]{3,})'\)",r"\(\s*'([A-Z][A-Z0-9_]{3,})'\s*,\s*facts\[",r"stop='([A-Z][A-Z0-9_]{3,})'",
                    r"else '([A-Z][A-Z0-9_]{3,})'",r"or '([A-Z][A-Z0-9_]{3,})'"):found|=set(re.findall(pattern,text))
    return found
@pytest.mark.parametrize('name,table',[('activate',ACTIVATE),('install_release',INSTALL_RELEASE)])
def test_every_code_of_the_two_writes_is_accounted_for_and_what_is_a_state_of_the_host_is_found_here(name,table):
    k=sibling(name);found=codes_of(SIBLINGS/name/'op.py');mine=f.load(k11.DIRECTORY).source.decode('ascii')
    assert found-set(table)==set(),'a code of %s this source has no stand on: decide where the dry run finds it, or why it cannot'%name
    assert set(table)-found==set(),'a code this source accounts for is no longer in %s'%name
    for code,(kind,names) in table.items():
        assert kind in (FOUND,BINDING,INSTANT,AFTER,WORD) and (kind==FOUND)==(names is not None)
        for item in names or []:assert "'%s'"%item in mine,(code,item)
