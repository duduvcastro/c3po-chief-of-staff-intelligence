"""OP_READBACK on the emulated host: the complete operation 4, read-only, item by item.
Synthetic local tests only. No SSH, host, real credential, docker binary or operational GO."""
from datetime import timedelta
import json
import os
import types

import pytest

import family as f
import hostemu

k=f.load('readback');m=k.m
UNITS='/etc/systemd/system'
SERVICE=UNITS+'/c3po-massive.service';TIMER=UNITS+'/c3po-massive.timer'
# The fixtures of this file are those of placement A, the placement signed for the first epoch: the journal root next
# to the state root, on the root filesystem. What is specific to placement B (the data volume) asks for it by name.
VALUES=f.VALUES_A;JOURNAL=VALUES['HOST_JOURNAL_ROOT'];B_JOURNAL=f.VALUES['HOST_JOURNAL_ROOT'];CLI='/etc/c3po-bar/docker-cli';TOKEN='/etc/c3po-bar/token'
RENDERED=f.reference_render(VALUES);B_RENDERED=f.reference_render(f.VALUES)
ROOT_DEVICE,DATA_DEVICE=801,811
ITEMS={'actor','boot','units','values','layout','token','catalog','free_space','conflicts','docker_init','systemd_version','docker_unit',
       'unit:c3po-massive.service','unit:c3po-massive.timer','timer_enabled','image','retention_tag','docker_daemon','docker_config',
       'reboot_marker','clock'}

AVAILABLE=13200816*4096                     # the data volume as the HOSTFACTS_01 receipt read it: 54070542336 bytes
ROOT_AVAILABLE=145315507*4096               # the root filesystem in the same receipt: 595212316672 bytes
FREED=AVAILABLE+f.FREED_BYTES               # placement B after space was freed on the data volume under another authorisation
INIT='/usr/libexec/docker/docker-init'

def ready(*,token=True,files=True,loaded=True,placement='A',freed=0,**fields):
    """files: whether operation 4b has left its two catalog files; fields['catalog']: what the request signs.
    Free space is what the receipt read on both filesystems unless freed says how much was freed on the data volume."""
    host,provision,install=f.ready_host(k,token=token,catalog=files,loaded=loaded,placement=placement,freed=freed)
    if not files:fields.setdefault('catalog','NOT_YET')
    return host,f.Docs(k,f.readback_fields(k,host,provision,install,**fields))
def refusal(action):
    with pytest.raises(m.Refused) as caught:action()
    return str(caught.value)
def run(host,docs):
    before=host.tree.snapshot();times={path:(host.tree.get(path).atime,host.tree.get(path).mtime) for path in host.tree.paths()}
    receipt=docs.run(host)
    assert host.tree.snapshot()==before and host.mutating()==[],'a readback changes nothing'
    assert {path:(host.tree.get(path).atime,host.tree.get(path).mtime) for path in host.tree.paths()}==times,'not even an access time'
    assert f.sealed(receipt) and set(receipt['items'])==ITEMS and receipt['writes']==0 and receipt['activation_authorized'] is False
    text=json.dumps(receipt)
    for canary in ('never-emit','canary'):assert canary not in text
    assert not [entry for entry in host.log if entry[0] in ('open','read') and entry[1]==TOKEN],'the token is never opened'
    assert not [entry for entry in host.log if entry[0] in ('open','read') and entry[1].startswith(JOURNAL+'/')],'no catalog file is opened'
    return receipt
def mismatch(host,docs,*findings,item=None):
    """Everything was observed, at least one expectation is not met: exit 2, every other item still in the receipt."""
    receipt=run(host,docs)
    assert (receipt['status'],receipt['outcome'])==(m.PARTIAL_STATUS,'OBSERVED_ALL_EXPECTATIONS_NOT_MET'),(receipt['outcome'],receipt['findings'],receipt['items_not_complete'])
    assert receipt['findings']==sorted(findings) and receipt['expectations_met'] is False and receipt['items_not_complete']==[] and receipt['code']==sorted(findings)[0]
    if item:assert receipt['items'][item]['matches'] is False and set(receipt['items'][item]['findings'])<=set(findings)
    return receipt
def partial(host,docs,*names,findings=None):
    """At least one item could not be observed: it is UNAVAILABLE with a constant code, never an absence."""
    receipt=run(host,docs)
    assert (receipt['status'],receipt['outcome'])==(m.PARTIAL_STATUS,'PARTIAL_OBSERVED'),(receipt['outcome'],receipt['findings'],receipt['items_not_complete'])
    assert receipt['items_not_complete']==sorted(names) and receipt['expectations_met'] is False
    for name in names:
        value=receipt['items'][name];assert value['status'] in ('UNAVAILABLE','PARTIAL') and value.get('exists') is not False and value.get('matches') is None
    if findings is not None:assert receipt['findings']==sorted(findings)
    return receipt


# ---------------------------------------------------------------- what the GO shows
def test_effects_shown_in_the_go_are_exactly_this_literal():
    """Written out by hand: a member that disappears from effects_of, or changes meaning, fails here."""
    host,docs=ready();plan=docs.plan;units=hostemu.rows(host,UNITS)
    node=lambda path:{'device':host.tree.get(path).dev,'inode':host.tree.get(path).ino}
    identities={'unit_directory':units,'service':node(SERVICE),'timer':node(TIMER),
                'layout':{'SUP_CONFIG':node('/etc/c3po-bar'),'SUP_MANIFESTS':node('/etc/c3po-bar/manifests'),'SUP_DOCKER_CLI':node(CLI),
                          'SUP_STATE_PARENT':node('/var/lib/c3po-bar'),'SUP_STATE':node('/var/lib/c3po-bar/supervisor'),'SUP_JOURNAL':node(JOURNAL)},
                'data_volume_rows':None,'catalog':node(JOURNAL)}
    expected={'operation':'GO_READONLY_SUPERVISOR_READBACK_01','mode':'GATE','install_receipt_sha256':plan['install']['receipt_sha256'],
              'install_outcome':'UNITS_INSTALLED_NOT_ACTIVATED_NOT_RELOADED','provision_receipt_sha256':plan['provision']['receipt_sha256'],
              'evidence_boot_id_sha256':f.BOOT_SHA,
              'units':{'c3po-massive.service':f.sha(RENDERED),'c3po-massive.timer':'ec61b1d6cbd1d604e5c2177d186f9045e67bf21ecc092498691591dfd9164ee6'},
              'substitutions':{'IMAGE_ID':hostemu.BACKEND,'HOST_JOURNAL_ROOT':'/var/lib/c3po-bar/journal','CONTAINER_JOURNAL_ROOT':'/c3po-bar-journal',
                               'HOST_STATE_ROOT':'/var/lib/c3po-bar/supervisor','HOST_CONFIG_DIR':'/etc/c3po-bar','NETWORK':'bridge'},
              'network_allowlist':['bridge'],'journal_placement':'A','journal_mount_point':'/','deploy_tree_path':'/opt/chief-of-staff-digital','data_volume_read':False,
              'layout_paths':{'SUP_CONFIG':'/etc/c3po-bar','SUP_MANIFESTS':'/etc/c3po-bar/manifests','SUP_DOCKER_CLI':'/etc/c3po-bar/docker-cli',
                              'SUP_STATE_PARENT':'/var/lib/c3po-bar','SUP_STATE':'/var/lib/c3po-bar/supervisor','SUP_JOURNAL':'/var/lib/c3po-bar/journal'},
              'data_volume_path':'/mnt/day-d-data','token_path':'/etc/c3po-bar/token','image_id':hostemu.BACKEND,
              'image_revision':'69c8e632802a06f81c32edc825462a6d2efe6485','retention_reference':'c3po/backend:massive-supervisor-epoch03',
              'free_space_floor_bytes':56706990080,'sessions_retained':5,'other_writers_allowance_bytes':0,
              'unit_directory_row':{'path':'/etc/systemd/system','device':801,'inode':4001,'uid':0,'gid':0,'mode':0o755},
              'data_volume_root_row':None,
              'identities_sha256':f.sha(f.canonical(identities)),
              'catalog':{'expected':'INITIALISED','receipt_sha256':'c'*64},'gates_activation_readback':True,'writes':0,'activation':False}
    assert f.canonical(m.effects_of(plan))==f.canonical(expected)==f.canonical(docs.go['effects'])
    assert len(f.sha(RENDERED))==64 and len(plan['install']['receipt_sha256'])==64 and plan['install']['receipt_sha256']!=plan['provision']['receipt_sha256']
    # placement B: the members that differ, literally
    host,docs=ready(placement='B');effects=docs.go['effects'];identities.update(service=node(SERVICE),timer=node(TIMER),data_volume_rows=hostemu.rows(host,hostemu.DATA),catalog=node(B_JOURNAL))
    identities['layout']={key:node(path) for key,path in (('SUP_CONFIG','/etc/c3po-bar'),('SUP_MANIFESTS','/etc/c3po-bar/manifests'),('SUP_DOCKER_CLI',CLI),
                          ('SUP_STATE_PARENT','/var/lib/c3po-bar'),('SUP_STATE','/var/lib/c3po-bar/supervisor'),('SUP_JOURNAL',B_JOURNAL))}
    assert (effects['journal_placement'],effects['journal_mount_point'],effects['deploy_tree_path'],effects['data_volume_read'])==('B','/mnt/day-d-data',None,True)
    assert effects['data_volume_root_row']=={'path':'/mnt/day-d-data','device':811,'inode':4005,'uid':1000,'gid':1000,'mode':0o755}
    assert effects['layout_paths']['SUP_JOURNAL']=='/mnt/day-d-data/r2d2-v2-massive-epoch03' and effects['substitutions']==f.VALUES
    assert effects['units']['c3po-massive.service']==f.sha(B_RENDERED) and effects['identities_sha256']==f.sha(f.canonical(identities))

@pytest.mark.parametrize('placement',['A','B'])
def test_every_identity_the_readback_compares_is_bound_into_the_go_effects(placement):
    """A request whose pinned device or inode changes cannot keep the effects (and so the GO) it had."""
    host,docs=ready(placement=placement);before=f.canonical(m.effects_of(docs.plan));changes=[]
    assert (docs.plan['data_volume']['rows'] is None)==(placement=='A')
    for label,target in ([('unit_directory/%d'%index,row) for index,row in enumerate(docs.plan['unit_directory'])]+
                         [('data_volume/%d'%index,row) for index,row in enumerate(docs.plan['data_volume']['rows'] or [])]+
                         [('service',docs.plan['service']),('timer',docs.plan['timer']),('catalog',docs.plan['catalog'])]+
                         [('layout/'+key,docs.plan['layout'][key]) for key in m.LAYOUT_KEYS]):
        for field in ('device','inode')+(('uid','gid','mode') if 'uid' in target else ()):
            saved=target[field];target[field]=saved+1;changes.append(label+'/'+field)
            assert f.canonical(m.effects_of(docs.plan))!=before,label+'/'+field
            docs.chain(effects=False);assert refusal(docs.authenticate)=='EFFECTS_BINDING',label+'/'+field
            target[field]=saved
    assert len(changes)==2*9+5*(len(docs.plan['unit_directory'])+len(docs.plan['data_volume']['rows'] or []))==(38 if placement=='A' else 53)
    docs.chain();docs.authenticate()


# ---------------------------------------------------------------- everything met
def test_all_observed_all_expectations_met_is_the_only_exit_zero():
    host,docs=ready();receipt=run(host,docs);items=receipt['items']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,'READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET',None)
    assert receipt['findings']==[] and receipt['expectations_met'] is True and all(item['status']=='COMPLETE' for item in items.values())
    assert all(item['matches'] is True for item in items.values())
    files=items['units']['files']
    assert (files['c3po-massive.service']['sha256'],files['c3po-massive.service']['bytes'])==(f.sha(RENDERED),len(RENDERED))
    assert (files['c3po-massive.timer']['sha256'],files['c3po-massive.timer']['bytes'])==(f.sha(f.TIMER),234)
    assert items['values']['extracted']==VALUES and (items['values']['signed_placement'],items['values']['extracted_values_conform_to_the_signed_placement'])==('A',True)
    assert items['token']=={'exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1,
        'size_within_1_4096':True,'configuration_directory_entries':3,'configuration_directory_entries_expected':3,'status':'COMPLETE','findings':[],'matches':True}
    assert items['catalog']['known_files']=={name:{'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1} for name in ('epoch.json','maintenance.lock')}
    # the floor of five sessions, on the filesystem of the journal root, with nothing freed: the root filesystem as the receipt read it
    space=items['free_space'];assert space['bytes_available_to_non_root_f_bavail']==ROOT_AVAILABLE==595212316672 and space['at_or_above_signed_floor'] is True
    assert (space['signed_floor_bytes'],space['sessions_retained'],space['other_writers_allowance_bytes'],space['bytes_above_signed_floor'])==(56706990080,5,0,538505326592)
    assert space['filesystem_device']==ROOT_DEVICE
    # under placement A nothing of the data volume is read; the journal root is on its parent's filesystem and is no mount point
    assert items['layout']['data_volume']=={'status':'COMPLETE','read':False,'reason':'placement A: the data volume is not part of the layout and nothing of it is read'}
    assert items['layout']['journal_filesystem']=={'placement':'A','signed_mount_point':'/','status':'COMPLETE','device':ROOT_DEVICE,'parent_device':ROOT_DEVICE,
                                                   'mount_point_by_device_change':'/','mount_point_equals_signed':True,'journal_root_is_a_mount_point':False}
    assert not [entry for entry in host.log if type(entry[1]) is str and entry[1].startswith('/mnt')]
    assert items['docker_config']=={'path':CLI,'entries_before':0,'entries_after':0,'status':'COMPLETE','findings':[],'matches':True}
    assert items['docker_daemon']['init_binary']=='docker-init' and items['docker_daemon']['server_version_number']==[29,5]
    assert items['docker_init']['present_paths']==[INIT] and items['docker_init']['present_not_counted_paths']==[]
    assert items['docker_init']['candidates'][INIT]=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0755','device':801,'inode':4004}
    assert items['timer_enabled']['word']=='disabled' and items['timer_enabled']['returncode']==1
    assert items['image']['id']==hostemu.BACKEND and items['retention_tag']['id']==hostemu.BACKEND and items['retention_tag']['reference']=='c3po/backend:'+f.TAG
    assert (items['image']['signed_revision'],items['image']['revision_equal_signed'],items['image']['production_reference_among_repo_tags'])==(hostemu.REVISION,True,True)
    assert 'signed_revision' not in items['retention_tag'] and items['systemd_version']['first_line']=='systemd 255 (255.4-1ubuntu8.17)'
    assert items['unit:c3po-massive.service']['load_state']=='loaded' and items['unit:c3po-massive.service']['load_states_that_are_findings']==['bad-setting','error','masked']
    assert receipt['file_contents_read']==['the two signed unit files',m.BOOT_ID_PATH] and receipt['secret_bytes_read']==0
    assert sorted({entry[1] for entry in host.log if entry[0]=='read'})==sorted([m.BOOT_ID_PATH,SERVICE,TIMER])
    assert len(f.line(receipt))<24576 and receipt['size_reductions']==[]
    # placement B after space was freed: the data volume root is recorded as observed, not required to be root's
    host,docs=ready(placement='B',freed=f.FREED_BYTES);receipt=run(host,docs);items=receipt['items']
    assert receipt['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET' and items['values']['extracted']==f.VALUES and items['values']['signed_placement']=='B'
    assert items['layout']['data_volume']['rows'][-1]['uid']==1000 and items['layout']['data_volume']['recorded_not_required_to_be_root'] is True
    assert items['layout']['journal_filesystem']=={'placement':'B','signed_mount_point':'/mnt/day-d-data','status':'COMPLETE','device':DATA_DEVICE,'parent_device':DATA_DEVICE,
                                                   'mount_point_by_device_change':'/mnt/day-d-data','mount_point_equals_signed':True,'journal_root_is_a_mount_point':False}
    assert (items['free_space']['bytes_available_to_non_root_f_bavail'],items['free_space']['filesystem_device'])==(FREED,DATA_DEVICE)

def test_only_the_signed_commands_run_and_docker_gets_the_unit_configuration_directory():
    host,docs=ready();run(host,docs);commands=host.commands
    table=[row[1] for row in m.COMMANDS.values()]
    for command in commands:
        argv=command['argv'];tool=argv[0].rsplit('/',1)[1]
        assert any(argv[1:1+len(prefix)]==prefix for prefix in table) and argv[0] in ('/usr/bin/docker','/usr/bin/systemctl')
        assert command['docker_config']==(CLI if tool=='docker' else None)
        if tool=='systemctl':assert argv[1] in ('--version','show','is-enabled')
    assert [command['argv'][1:3] for command in commands]==[['--version'],['show','docker.service'],['show','c3po-massive.service'],['show','c3po-massive.timer'],
        ['is-enabled','c3po-massive.timer'],['image','inspect'],['image','inspect'],['info','--format'],['version','--format']]
    assert [command['argv'][-1] for command in commands[5:7]]==[hostemu.BACKEND,'c3po/backend:'+f.TAG]
    assert sum(1 for command in commands if command['argv'][1]=='info')==1


# ---------------------------------------------------------------- request validation
def invalid(change,**options):
    host,docs=ready(**options);change(docs.plan);docs.chain()
    code=refusal(docs.authenticate);result=docs.run(host)
    assert (result['status'],result['code'],result['outcome'])==('REFUSED',code,'REFUSED_NOTHING_OBSERVED') and host.log==[];return code

def test_request_shape_and_every_open_parameter():
    for change,code in (
            (lambda plan:plan.update(mode='AUDIT'),'MODE_INVALID'),(lambda plan:plan.update(mode=None),'MODE_INVALID'),
            (lambda plan:plan.update(install=None),'RECEIPTS_INVALID'),(lambda plan:plan.update(provision={}),'RECEIPTS_INVALID'),
            (lambda plan:plan['install'].update(receipt_sha256=None),'INSTALL_RECEIPT_UNBOUND'),(lambda plan:plan['install'].update(receipt_sha256='0'*64),'INSTALL_RECEIPT_UNBOUND'),
            (lambda plan:plan['install'].update(outcome='PARTIAL_REQUIRES_RECONCILIATION'),'INSTALL_RECEIPT_UNBOUND'),(lambda plan:plan['install'].update(outcome=None),'INSTALL_RECEIPT_UNBOUND'),
            (lambda plan:plan['provision'].update(receipt_sha256=None),'PROVISION_RECEIPT_UNBOUND'),(lambda plan:plan.update(evidence_boot_id_sha256=None),'EVIDENCE_BOOT_UNBOUND'),
            (lambda plan:plan.update(unit_directory=None),'CHAIN_ROW_INVALID'),(lambda plan:plan['unit_directory'][3].update(device=None),'CHAIN_ROW_INVALID'),
            (lambda plan:plan.update(data_volume=None),'DATA_VOLUME_INVALID'),(lambda plan:plan['data_volume'].update(path=None),'DATA_VOLUME_INVALID'),
            (lambda plan:plan['data_volume'].update(rows=hostemu.rows(hostemu.world(),hostemu.DATA)),'DATA_VOLUME_INVALID'),     # placement A signs no row of the data volume
            (lambda plan:plan['data_volume'].update(path='/var/lib'),'PRIVATE_ROOT_INSIDE_DATA_VOLUME'),(lambda plan:plan['data_volume'].update(path='/var/lib/c3po-bar/journal'),'A_HOST_JOURNAL_INSIDE_DATA_VOLUME'),
            (lambda plan:plan.update(journal_placement=None),'PLACEMENT_UNKNOWN'),(lambda plan:plan.update(journal_placement='C'),'PLACEMENT_UNKNOWN'),
            (lambda plan:plan.update(journal_placement='B',deploy_tree_path=None),'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'),
            (lambda plan:plan.update(deploy_tree_path=None),'DEPLOY_TREE_PATH'),(lambda plan:plan.update(deploy_tree_path='/var/lib/c3po-bar'),'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE'),
            (lambda plan:plan['substitutions'].update(CONTAINER_JOURNAL_ROOT='/app/day-d-data/journal'),'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'),
            (lambda plan:plan['substitutions'].update(CONTAINER_JOURNAL_ROOT='/srv'),'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY'),
            (lambda plan:plan.update(journal_mount_point=None),'JOURNAL_MOUNT_POINT_UNBOUND'),(lambda plan:plan.update(journal_mount_point='var'),'JOURNAL_MOUNT_POINT_UNBOUND'),
            (lambda plan:plan.update(journal_mount_point='/mnt/day-d-data'),'JOURNAL_MOUNT_POINT_UNBOUND'),          # the journal root is not below it
            (lambda plan:plan.update(journal_mount_point='/var/lib/c3po-bar/journal'),'JOURNAL_MOUNT_POINT_UNBOUND'),  # the journal root itself is never a mount point
            (lambda plan:plan['substitutions'].update(HOST_JOURNAL_ROOT='/mnt/day-d-data/journal'),'A_HOST_JOURNAL_INSIDE_DATA_VOLUME'),
            (lambda plan:plan.update(network_allowlist=[]),'NETWORK_ALLOWLIST'),(lambda plan:plan['substitutions'].update(NETWORK='host'),'NETWORK_NOT_AUTHORIZED'),
            (lambda plan:plan['substitutions'].update(IMAGE_ID=None),'IMAGE_ID'),(lambda plan:plan['substitutions'].update(HOST_STATE_ROOT=None),'PATH_INVALID'),
            (lambda plan:plan.update(substitutions=None),'SUBSTITUTION_KEYS'),(lambda plan:plan['substitutions'].update(NETWORK='c3po'),'NETWORK_NOT_AUTHORIZED'),
            (lambda plan:plan.update(service=None),'UNITS_INVALID'),(lambda plan:plan['service'].update(device=None),'UNITS_INVALID'),
            (lambda plan:plan['timer'].update(inode=0),'UNITS_INVALID'),(lambda plan:plan['service'].update(device=None,inode=None),'UNITS_INVALID'),
            (lambda plan:plan['layout']['SUP_STATE'].update(device=None,inode=None),'LAYOUT_INVALID'),(lambda plan:plan['timer'].update(extra=1),'UNITS_INVALID'),
            (lambda plan:plan['service'].update(rendered_sha256=None),'RENDERED_HASH_MISMATCH'),(lambda plan:plan['service'].update(rendered_bytes=None),'RENDERED_SIZE_MISMATCH'),
            (lambda plan:plan['service'].update(template_b64=plan['timer']['template_b64']),'TEMPLATE_HASH_MISMATCH'),
            (lambda plan:plan['timer'].update(rendered_sha256='3'*64),'RENDERED_HASH_MISMATCH'),
            (lambda plan:plan.update(layout=None),'LAYOUT_INVALID'),(lambda plan:plan['layout'].pop('SUP_STATE'),'LAYOUT_INVALID'),
            (lambda plan:plan['layout']['SUP_JOURNAL'].update(inode=None),'LAYOUT_INVALID'),(lambda plan:plan['layout'].update(OTHER={'device':1,'inode':2}),'LAYOUT_INVALID'),
            (lambda plan:plan.update(retention_reference=None),'TAG_INVALID'),(lambda plan:plan.update(retention_reference='c3po/backend:production'),'TAG_INVALID'),
            (lambda plan:plan.update(retention_reference='c3po/backend:rollback'),'TAG_INVALID'),(lambda plan:plan.update(retention_reference='other/backend:massive-supervisor-x'),'TAG_INVALID'),
            # the floor is the gate's formula on two signed terms: 53687091200 + 603979776 per session + the allowance
            (lambda plan:plan.update(free_space_floor_bytes=None),'FLOOR_NOT_THE_GATE_FORMULA'),(lambda plan:plan.update(free_space_floor_bytes=53687091200),'FLOOR_NOT_THE_GATE_FORMULA'),
            (lambda plan:plan.update(free_space_floor_bytes=56706990080.0),'FLOOR_NOT_THE_GATE_FORMULA'),(lambda plan:plan.update(free_space_floor_bytes=0),'FLOOR_NOT_THE_GATE_FORMULA'),
            (lambda plan:plan.update(free_space_floor_bytes=56706990079),'FLOOR_NOT_THE_GATE_FORMULA'),(lambda plan:plan.update(free_space_floor_bytes=56706990081),'FLOOR_NOT_THE_GATE_FORMULA'),
            (lambda plan:plan.update(free_space_floor_bytes=54291070976),'FLOOR_NOT_THE_GATE_FORMULA'),          # the one-session number under a five-session signature
            (lambda plan:plan.update(sessions_retained=4),'FLOOR_NOT_THE_GATE_FORMULA'),(lambda plan:plan.update(other_writers_allowance_bytes=1),'FLOOR_NOT_THE_GATE_FORMULA'),
            (lambda plan:plan.update(sessions_retained=0,free_space_floor_bytes=53687091200),'FLOOR_TERMS_INVALID'),(lambda plan:plan.update(sessions_retained=None),'FLOOR_TERMS_INVALID'),
            (lambda plan:plan.update(sessions_retained=5.0),'FLOOR_TERMS_INVALID'),(lambda plan:plan.update(sessions_retained=True),'FLOOR_TERMS_INVALID'),
            (lambda plan:plan.update(sessions_retained=367,free_space_floor_bytes=f.floor_bytes(367)),'FLOOR_TERMS_INVALID'),
            (lambda plan:plan.update(other_writers_allowance_bytes=None),'FLOOR_TERMS_INVALID'),(lambda plan:plan.update(other_writers_allowance_bytes=-1,free_space_floor_bytes=56706990079),'FLOOR_TERMS_INVALID'),
            (lambda plan:plan.update(image_revision=None),'IMAGE_REVISION_UNBOUND'),(lambda plan:plan.update(image_revision='69c8e63'),'IMAGE_REVISION_UNBOUND'),
            (lambda plan:plan.update(image_revision='UNBOUND'),'IMAGE_REVISION_UNBOUND'),
            (lambda plan:plan.update(catalog=None),'CATALOG_INVALID'),(lambda plan:plan['catalog'].update(expected=None),'CATALOG_INVALID'),
            (lambda plan:plan['catalog'].update(expected='MAYBE'),'CATALOG_INVALID'),(lambda plan:plan['catalog'].update(receipt_sha256=None),'CATALOG_INVALID'),
            (lambda plan:plan['catalog'].update(inode=None),'CATALOG_INVALID'),(lambda plan:plan['catalog'].update(expected='NOT_YET'),'CATALOG_INVALID')):
        assert invalid(change)==code
    for change,code in ((lambda plan:plan['data_volume'].update(rows=None),'CHAIN_ROW_INVALID'),(lambda plan:plan['data_volume'].update(path='/mnt'),'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'),
                        (lambda plan:plan['data_volume']['rows'].pop(),'CHAIN_ROW_INVALID'),(lambda plan:plan.update(deploy_tree_path='/opt/chief-of-staff-digital'),'DEPLOY_TREE_PATH'),
                        (lambda plan:plan.update(journal_placement='A',deploy_tree_path='/opt/chief-of-staff-digital'),'A_HOST_JOURNAL_INSIDE_DATA_VOLUME'),
                        (lambda plan:plan['substitutions'].update(CONTAINER_JOURNAL_ROOT='/c3po-bar-journal'),'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF')):
        assert invalid(change,placement='B',freed=f.FREED_BYTES)==code
    for sessions,allowance,floor in ((1,0,54291070976),(5,0,56706990080),(5,1073741824,57780731904),(366,0,53687091200+603979776*366)):
        host,docs=ready(sessions=sessions,allowance=allowance);assert docs.plan['free_space_floor_bytes']==floor;docs.authenticate()
        assert (docs.go['effects']['free_space_floor_bytes'],docs.go['effects']['sessions_retained'],docs.go['effects']['other_writers_allowance_bytes'])==(floor,sessions,allowance)

def test_reconciliation_is_a_signed_mode_that_can_never_exit_zero():
    host,docs=ready(mode='RECONCILIATION')
    assert docs.go['success_criterion']=='RECONCILIATION_OBSERVED_NOTHING_GATED' and docs.go['effects']['gates_activation_readback'] is False
    receipt=run(host,docs)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'RECONCILIATION_OBSERVED_NOTHING_GATED','INSTALL_RECEIPT_NOT_COMPLETE')
    assert receipt['findings']==['INSTALL_RECEIPT_NOT_COMPLETE'] and receipt['expectations_met'] is False and receipt['items_not_complete']==[]
    assert k.l is not None and {'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(receipt['status'],2)==2
    # after an uncertain transport there is no install receipt: hash and identities are null, and everything is still read
    host,docs=ready(mode='RECONCILIATION')
    docs.plan['install']={'receipt_sha256':None,'outcome':None};docs.plan['provision']={'receipt_sha256':None};docs.plan['evidence_boot_id_sha256']=None
    for item in (docs.plan['service'],docs.plan['timer'])+tuple(docs.plan['layout'].values()):item.update(device=None,inode=None)
    docs.chain();receipt=run(host,docs)
    assert receipt['outcome']=='RECONCILIATION_OBSERVED_NOTHING_GATED' and receipt['items']['units']['files']['c3po-massive.service']['identity_equal_install_receipt'] is None
    assert receipt['items']['units']['files']['c3po-massive.service']['sha256']==f.sha(RENDERED) and receipt['items']['layout']['paths']['SUP_STATE']['identity_equal_provision_receipt'] is None
    # the GO of a gate readback is not a GO for a reconciliation, and the reverse
    host,docs=ready(mode='RECONCILIATION');docs.go['success_criterion']='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET';docs.chain(criterion=False)
    assert refusal(docs.authenticate)=='GO_CRITERION'
    host,docs=ready();docs.go['success_criterion']='RECONCILIATION_OBSERVED_NOTHING_GATED';docs.chain(criterion=False);assert refusal(docs.authenticate)=='GO_CRITERION'
    # a mismatch in reconciliation mode stays a finding next to the mandatory one
    host,docs=ready(mode='RECONCILIATION');host.tree.remove(TOKEN);receipt=run(host,docs)
    assert receipt['findings']==['INSTALL_RECEIPT_NOT_COMPLETE','TOKEN_ABSENT'] and receipt['outcome']=='RECONCILIATION_OBSERVED_NOTHING_GATED'


# ---------------------------------------------------------------- units and values
def test_unit_files_bytes_metadata_identity_and_the_values_on_disk():
    host,docs=ready();host.tree.remove(TIMER);receipt=mismatch(host,docs,'UNIT_ABSENT',item='units');assert receipt['items']['units']['files']['c3po-massive.timer']=={'exists':False}
    host,docs=ready();host.tree.remove(SERVICE);receipt=partial(host,docs,'values',findings=['UNIT_ABSENT']);assert receipt['items']['values']['code']=='SERVICE_BYTES_UNAVAILABLE'
    host,docs=ready();host.tree.remove(TIMER);host.tree.add(TIMER,kind='symlink',mode=0o777);mismatch(host,docs,'UNIT_NOT_REGULAR',item='units')
    for change in (lambda node:setattr(node,'mode',0o600),lambda node:setattr(node,'uid',1000),lambda node:setattr(node,'gid',4),lambda node:setattr(node,'nlink',2)):
        host,docs=ready();change(host.tree.get(SERVICE));mismatch(host,docs,'UNIT_METADATA',item='units')
    host,docs=ready();host.tree.get(TIMER).ino+=1000;mismatch(host,docs,'UNIT_IDENTITY_CHANGED',item='units')
    host,docs=ready();host.tree.get(SERVICE).content=bytearray(RENDERED.replace(b'--cap-drop ALL',b'--cap-add ALL'))
    receipt=mismatch(host,docs,'UNIT_BYTES_MISMATCH','VALUES_NOT_EXTRACTABLE');assert receipt['items']['values']['extracted'] is None
    host,docs=ready();host.tree.get(SERVICE).content=bytearray(RENDERED[:-1]+b'\n\n')                 # one byte more
    mismatch(host,docs,'UNIT_BYTES_MISMATCH','VALUES_NOT_EXTRACTABLE')
    other=dict(VALUES,NETWORK='c3po_c3po_internal');host,docs=ready();host.tree.get(SERVICE).content=bytearray(f.reference_render(other))
    receipt=mismatch(host,docs,'UNIT_BYTES_MISMATCH','VALUES_MISMATCH')
    assert receipt['items']['values']['extracted']==other and receipt['items']['values']['signed']==VALUES,'what is on disk is reported, not the request echoed'
    assert receipt['items']['values']['extracted_values_conform_to_the_signed_placement'] is True,'another network is not another placement'
    # the unit on disk is the one of the OTHER placement: the values differ, and they break the signed placement's own rules
    host,docs=ready();host.tree.get(SERVICE).content=bytearray(B_RENDERED);receipt=mismatch(host,docs,'PLACEMENT_MISMATCH','UNIT_BYTES_MISMATCH','VALUES_MISMATCH')
    values=receipt['items']['values'];assert (values['signed_placement'],values['extracted_values_conform_to_the_signed_placement'],values['placement_rule_broken'])==('A',False,'A_HOST_JOURNAL_INSIDE_DATA_VOLUME')
    assert values['extracted']==f.VALUES
    host,docs=ready(placement='B',freed=f.FREED_BYTES);host.tree.get(SERVICE).content=bytearray(RENDERED)
    receipt=mismatch(host,docs,'PLACEMENT_MISMATCH','UNIT_BYTES_MISMATCH','VALUES_MISMATCH');assert receipt['items']['values']['placement_rule_broken']=='B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'
    host,docs=ready();host.tree.get(TIMER).content=bytearray(f.TIMER.replace(b'09:29:00',b'09:30:00'));mismatch(host,docs,'UNIT_BYTES_MISMATCH',item='units')
    host,docs=ready();host.tree.get(UNITS).mode=0o775;receipt=mismatch(host,docs,'UNIT_DIRECTORY_IDENTITY_MISMATCH',item='units')
    assert receipt['items']['units']['unit_directory'][-1]['mode']==0o775 and receipt['items']['units']['files']['c3po-massive.service']['bytes_equal_signed_render'] is True
    host,docs=ready();host.tree.get(SERVICE).content=bytearray(b'x'*65537);receipt=partial(host,docs,'units','values');assert receipt['items']['units']['code']=='FILE_TOO_LARGE'
    host,docs=ready();count=[0]
    def grow(host,name,detail,calls):
        if name=='read' and detail[0]==SERVICE:
            count[0]+=1
            if count[0]==1:host.tree.get(SERVICE).mtime+=1
    host.hook=grow;receipt=docs.run(host);assert receipt['items']['units']['code']=='UNIT_CHANGED_DURING_READ' and receipt['outcome']=='PARTIAL_OBSERVED'
    host,docs=ready();host.tree.remove('/etc/systemd');host.tree.add('/etc/systemd',kind='symlink',mode=0o777)
    receipt=docs.run(host);assert receipt['items']['units']['code']=='SYMLINK_COMPONENT' and receipt['outcome']=='PARTIAL_OBSERVED'


# ---------------------------------------------------------------- layout, token, catalog, space
def test_layout_owner_mode_identity_and_the_data_volume_recorded_not_required_to_be_root():
    host,docs=ready();host.tree.remove('/etc/c3po-bar/manifests');mismatch(host,docs,'CONFIG_DIRECTORY_ENTRIES','LAYOUT_ENTRY_ABSENT',item='layout')
    for change in (lambda node:setattr(node,'mode',0o750),lambda node:setattr(node,'uid',1000),lambda node:setattr(node,'gid',1000)):
        host,docs=ready();change(host.tree.get('/var/lib/c3po-bar/supervisor'));mismatch(host,docs,'LAYOUT_METADATA',item='layout')
    host,docs=ready();host.tree.get('/var/lib/c3po-bar').ino+=1000;mismatch(host,docs,'LAYOUT_IDENTITY_CHANGED',item='layout')
    # placement B: the data volume root is compared with its signed rows; under placement A a change there is not even read
    host,docs=ready(placement='B',freed=f.FREED_BYTES);host.tree.get(hostemu.DATA).mode=0o775;receipt=mismatch(host,docs,'DATA_VOLUME_ROW_CHANGED',item='layout')
    assert receipt['items']['layout']['data_volume']['rows'][-1]['mode']==0o775
    host,docs=ready(placement='B',freed=f.FREED_BYTES);host.tree.get(hostemu.DATA).uid=0;mismatch(host,docs,'DATA_VOLUME_ROW_CHANGED')     # becoming root's is a change too
    host,docs=ready();host.tree.get(hostemu.DATA).mode=0o775;host.tree.get(hostemu.DATA).uid=0;assert run(host,docs)['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
    # the journal root is never a mount point: its device is the device of the directory it is in, in both placements
    for placement,journal,other in (('A',JOURNAL,DATA_DEVICE),('B',B_JOURNAL,ROOT_DEVICE)):
        host,docs=ready(placement=placement,freed=f.FREED_BYTES if placement=='B' else 0);node=host.tree.get(journal);node.dev=other
        for child in node.children.values():child.dev=other
        docs.plan['layout']['SUP_JOURNAL']['device']=other;docs.plan['catalog']['device']=other;docs.chain()
        host.vfs[other]=types.SimpleNamespace(**hostemu.ROOT_VFS);receipt=mismatch(host,docs,'JOURNAL_ROOT_IS_A_MOUNT_POINT',item='layout')
        assert receipt['items']['layout']['journal_filesystem']['journal_root_is_a_mount_point'] is True and receipt['items']['layout']['journal_filesystem']['device']==other
    host,docs=ready();host.tree.remove('/var/lib/c3po-bar');host.tree.add('/var/lib/c3po-bar',kind='symlink',mode=0o777)
    receipt=partial(host,docs,'catalog','free_space','layout');layout=receipt['items']['layout']
    assert layout['paths']['SUP_JOURNAL']['code']=='SYMLINK_COMPONENT' and layout['journal_filesystem']=={'placement':'A','signed_mount_point':'/','status':'NOT_OBSERVED'},'not observed is not "no mount point"'
    # the filesystem of the journal root must be the one the authorisation names. The receipt of 2026-10-02 read /var/lib on the
    # device of "/", but in an earlier boot: if it is a mount of its own now, the root filesystem's free space says nothing about the journal root
    def remount(host,path,device):
        def walk(node):
            node.dev=device
            for child in node.children.values():walk(child)
        walk(host.tree.get(path));host.vfs[device]=types.SimpleNamespace(**hostemu.ROOT_VFS)
    for path in ('/var','/var/lib','/var/lib/c3po-bar'):
        host,docs=ready();remount(host,path,899)
        for key in ('SUP_STATE_PARENT','SUP_STATE','SUP_JOURNAL'):docs.plan['layout'][key]['device']=899
        docs.plan['catalog']['device']=899;docs.chain();receipt=mismatch(host,docs,'JOURNAL_FILESYSTEM_MISMATCH',item='layout');found=receipt['items']['layout']['journal_filesystem']
        assert (found['mount_point_by_device_change'],found['signed_mount_point'],found['mount_point_equals_signed'],found['device'])==(path,'/',False,899)
        assert receipt['items']['free_space']['filesystem_device']==899,'and the free-space item says on which device it measured'
        docs.plan['journal_mount_point']=path;docs.chain();assert run(host,docs)['items']['layout']['journal_filesystem']['mount_point_equals_signed'] is True
    host,docs=ready(placement='B',freed=f.FREED_BYTES);docs.plan['journal_mount_point']='/mnt';docs.chain();mismatch(host,docs,'JOURNAL_FILESYSTEM_MISMATCH',item='layout')
    host,docs=ready();host.tree.add('/etc/c3po-bar/manifests/2026-10-05.json',kind='file',mode=0o600,content=b'{"symbols":["never-emit-symbol-canary"]}')
    receipt=run(host,docs);assert receipt['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET' and receipt['items']['layout']['entry_counts']['SUP_MANIFESTS']['entries']==1
    host,docs=ready(placement='B',freed=f.FREED_BYTES);host.tree.remove('/var/lib/c3po-bar');host.tree.add('/var/lib/c3po-bar',kind='symlink',mode=0o777)
    receipt=partial(host,docs,'layout');paths=receipt['items']['layout']['paths']
    assert paths['SUP_STATE']=={'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','exists':None,'at':'/var/lib/c3po-bar','path':'/var/lib/c3po-bar/supervisor'}

def test_docker_configuration_directory_must_be_empty_and_is_never_handed_to_docker_otherwise():
    host,docs=ready();host.tree.add(CLI+'/config.json',kind='file',mode=0o600,content=b'{"proxies":"never-emit-proxy-canary"}')
    receipt=partial(host,docs,'docker_config','docker_daemon','image','retention_tag',findings=['DOCKER_CONFIG_NOT_EMPTY'])
    assert not [command for command in host.commands if command['argv'][0].endswith('docker')],'no docker process sees a non-empty or unverified configuration directory'
    assert receipt['items']['image']['code']=='DOCKER_CONFIG_DIRECTORY_UNAVAILABLE'
    host,docs=ready();host.tree.get(CLI).mode=0o755;receipt=partial(host,docs,'docker_config','docker_daemon','image','retention_tag',findings=['LAYOUT_METADATA'])
    assert not [command for command in host.commands if command['argv'][0].endswith('docker')]
    host,docs=ready()
    def writes(docker,args):
        if args[0]=='info':host.tree.add(CLI+'/contexts',mode=0o755)
    host.docker.before=writes;before=host.tree.snapshot();receipt=docs.run(host)
    assert receipt['findings']==['DOCKER_CONFIG_CHANGED_DURING_RUN'] and receipt['items']['docker_config']['entries_before']==0 and receipt['items']['docker_config']['entries_after']==1
    assert receipt['outcome']=='OBSERVED_ALL_EXPECTATIONS_NOT_MET'

def test_token_is_metadata_only_and_an_absent_token_fails_closed_without_discarding_the_rest():
    host,docs=ready(token=False);receipt=mismatch(host,docs,'TOKEN_ABSENT',item='token')
    assert receipt['items']['token']=={'exists':False,'configuration_directory_entries':2,'configuration_directory_entries_expected':2,
                                       'status':'COMPLETE','findings':['TOKEN_ABSENT'],'matches':False}
    assert receipt['items']['units']['matches'] is True and receipt['items']['image']['matches'] is True and receipt['status']!=m.COMPLETE_STATUS
    for size,within in ((1,True),(4096,True),(0,False),(4097,False),(65536,False)):
        host,docs=ready(token=False);host.tree.add(TOKEN,kind='file',mode=0o600,content=b'k'*size)
        receipt=run(host,docs) if within else mismatch(host,docs,'TOKEN_SIZE_POLICY',item='token')
        token=receipt['items']['token'];assert token['size_within_1_4096'] is within and set(token)=={'exists','type','uid','gid','mode_octal','links','size_within_1_4096',
            'configuration_directory_entries','configuration_directory_entries_expected','status','findings','matches'}
        assert size<=1 or size not in [value for value in token.values() if type(value) is int],'the size itself never leaves the process'
    host,docs=ready(token=False);host.tree.add(TOKEN,kind='file',mode=0o600,content=b'k'*3333);assert '3333' not in json.dumps(run(host,docs))
    for change in (lambda node:setattr(node,'mode',0o640),lambda node:setattr(node,'mode',0o400),lambda node:setattr(node,'uid',1000),lambda node:setattr(node,'gid',1000),
                   lambda node:setattr(node,'nlink',2)):
        host,docs=ready();change(host.tree.get(TOKEN));mismatch(host,docs,'TOKEN_METADATA',item='token')
    for kind in ('symlink','dir','fifo'):
        host,docs=ready(token=False);host.tree.add(TOKEN,kind=kind,mode=0o600)
        receipt=mismatch(host,docs,'TOKEN_NOT_REGULAR',item='token');assert receipt['items']['token']['size_within_1_4096'] is None
    host,docs=ready(token=False);host.tree.add(TOKEN,kind='symlink',mode=0o777);mismatch(host,docs,'TOKEN_METADATA','TOKEN_NOT_REGULAR',item='token')
    host,docs=ready();receipt=run(host,docs);text=json.dumps(receipt)
    assert 'never-emit-token-canary' not in text and f.sha(b'never-emit-token-canary-0123456789\n') not in text and '"35"' not in text

def test_configuration_directory_holds_the_two_directories_and_the_token_and_nothing_else():
    """An abandoned token.new, an editor backup, a copy: counted on the descriptor held, never named, never opened."""
    for name,kind in (('token.new','file'),('token~','file'),('.token.swp','file'),('backup','dir'),('token.bak','symlink')):
        host,docs=ready();host.tree.add('/etc/c3po-bar/'+name,kind=kind,mode=0o600,content=b'never-emit-token-canary' if kind=='file' else b'')
        receipt=mismatch(host,docs,'CONFIG_DIRECTORY_ENTRIES',item='token');token=receipt['items']['token']
        assert (token['configuration_directory_entries'],token['configuration_directory_entries_expected'],token['exists'])==(4,3,True)
        assert name not in json.dumps(receipt) and not [entry for entry in host.log if entry[0] in ('open','read','lstat') and entry[1]=='/etc/c3po-bar/'+name]
    host,docs=ready(token=False);host.tree.add('/etc/c3po-bar/token.new',kind='file',mode=0o600,content=b'x')
    receipt=mismatch(host,docs,'CONFIG_DIRECTORY_ENTRIES','TOKEN_ABSENT',item='token');assert receipt['items']['token']['configuration_directory_entries']==3
    host,docs=ready()
    for index in range(5):host.tree.add('/etc/c3po-bar/manifests/2026-10-%02d.json'%(5+index),kind='file',mode=0o600)     # manifests live one level down: not counted here
    assert run(host,docs)['items']['token']['configuration_directory_entries']==3

def test_catalog_names_and_metadata_against_the_signed_expectation():
    host,docs=ready(files=False);receipt=run(host,docs);assert receipt['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET' and receipt['items']['catalog']['entries']==0
    host,docs=ready(catalog='NOT_YET');receipt=mismatch(host,docs,'CATALOG_UNEXPECTED',item='catalog');assert receipt['items']['catalog']['entries']==2
    host,docs=ready(files=False,catalog='NOT_YET');host.tree.add(JOURNAL+'/producer.lock',kind='file',mode=0o600,dev=ROOT_DEVICE);mismatch(host,docs,'CATALOG_UNEXPECTED',item='catalog')
    host,docs=ready();host.tree.remove(JOURNAL+'/epoch.json');mismatch(host,docs,'CATALOG_ENTRIES',item='catalog')
    host,docs=ready();host.tree.remove(JOURNAL+'/epoch.json');host.tree.remove(JOURNAL+'/maintenance.lock');mismatch(host,docs,'CATALOG_ENTRIES',item='catalog')
    host,docs=ready();host.tree.add(JOURNAL+'/producer.lock',kind='file',mode=0o600,dev=ROOT_DEVICE)
    receipt=mismatch(host,docs,'CATALOG_ENTRIES',item='catalog');assert receipt['items']['catalog']['other_entries']==1 and 'producer.lock' not in json.dumps(receipt['items']['catalog'])
    host,docs=ready();host.tree.add(JOURNAL+'/session_date=2026-10-05',dev=ROOT_DEVICE);mismatch(host,docs,'CATALOG_ENTRIES',item='catalog')
    for change in (lambda node:setattr(node,'mode',0o644),lambda node:setattr(node,'uid',1000),lambda node:setattr(node,'nlink',2),lambda node:setattr(node,'kind','dir')):
        host,docs=ready();change(host.tree.get(JOURNAL+'/maintenance.lock'));mismatch(host,docs,'CATALOG_METADATA',item='catalog')
    host,docs=ready();docs.plan['catalog']['inode']+=1;docs.chain();mismatch(host,docs,'CATALOG_IDENTITY_MISMATCH',item='catalog')
    host,docs=ready();docs.plan['catalog']['device']+=1;docs.chain();mismatch(host,docs,'CATALOG_IDENTITY_MISMATCH',item='catalog')
    host,docs=ready();host.tree.remove(JOURNAL);receipt=partial(host,docs,'catalog','free_space',findings=['LAYOUT_ENTRY_ABSENT'])
    assert receipt['items']['catalog']=={'status':'UNAVAILABLE','code':'OS_ERROR','errno':2},'the journal root being gone is not an empty catalog'
    host,docs=ready()
    for index in range(70):host.tree.add(JOURNAL+'/extra-%02d'%index,kind='file',dev=ROOT_DEVICE)
    receipt=partial(host,docs,'catalog','free_space');assert receipt['items']['catalog']['code']=='CATALOG_ENTRY_LIMIT'

def test_on_the_host_as_the_receipt_read_it_the_floor_is_met_under_placement_a_and_never_under_placement_b():
    """HOSTFACTS_01, 2026-10-02T01:51:44Z: 54070542336 bytes available on the data volume, 595212316672 on the root
    filesystem. README activation gate item 4 asks, on the filesystem of the journal root, for 53687091200 + 603979776 per
    retained session + the allowance. Placement B (journal in the data volume) cannot meet it for one session or for
    five until space is freed; placement A, the owner's decision for the first epoch, meets it with nothing freed."""
    world=hostemu.world();assert world.vfs[DATA_DEVICE].f_bavail*4096==AVAILABLE==54070542336 and world.vfs[ROOT_DEVICE].f_bavail*4096==ROOT_AVAILABLE==595212316672
    assert AVAILABLE-53687091200==383451136<603979776
    for sessions,floor,short in ((5,56706990080,2636447744),(1,54291070976,220528640)):
        host,docs=ready(placement='B',sessions=sessions);assert docs.plan['free_space_floor_bytes']==floor
        receipt=mismatch(host,docs,'FREE_SPACE_BELOW_FLOOR',item='free_space');space=receipt['items']['free_space']
        assert (space['bytes_available_to_non_root_f_bavail'],space['signed_floor_bytes'],space['bytes_above_signed_floor'],space['filesystem_device'])==(AVAILABLE,floor,-short,DATA_DEVICE)
        assert {'METADATA_ONLY_REQUIRES_REVIEW':0,'REFUSED':1}.get(receipt['status'],2)==2 and space['at_or_above_signed_floor'] is False
    # freeing exactly what is short meets the floor; one block less does not
    host,docs=ready(placement='B',freed=2636447744);assert run(host,docs)['items']['free_space']['bytes_above_signed_floor']==0
    host,docs=ready(placement='B',freed=2636447744-4096);mismatch(host,docs,'FREE_SPACE_BELOW_FLOOR',item='free_space')
    # placement A: the same request terms, measured on the journal root itself, which is on the root filesystem
    for sessions,floor in ((5,56706990080),(1,54291070976),(366,53687091200+603979776*366)):
        host,docs=ready(sessions=sessions);space=run(host,docs)['items']['free_space']
        assert (space['bytes_available_to_non_root_f_bavail'],space['signed_floor_bytes'],space['at_or_above_signed_floor'],space['filesystem_device'])==(ROOT_AVAILABLE,floor,True,ROOT_DEVICE)
        assert not [entry for entry in host.log if entry[0]=='fstatvfs' and entry[1]!=JOURNAL],'the figure is read on the journal root and nowhere else'

def test_free_space_is_the_producer_figure_against_the_signed_floor():
    host,docs=ready(sessions=1,allowance=ROOT_AVAILABLE-54291070976);assert docs.plan['free_space_floor_bytes']==ROOT_AVAILABLE
    assert run(host,docs)['items']['free_space']['at_or_above_signed_floor'] is True
    host,docs=ready(sessions=1,allowance=ROOT_AVAILABLE-54291070976+1);receipt=mismatch(host,docs,'FREE_SPACE_BELOW_FLOOR',item='free_space')
    assert receipt['items']['free_space']['bytes_available_to_non_root_f_bavail']==ROOT_AVAILABLE and receipt['items']['free_space']['signed_floor_bytes']==ROOT_AVAILABLE+1
    host,docs=ready();host.vfs[ROOT_DEVICE]=types.SimpleNamespace(f_frsize=4096,f_blocks=162243833,f_bfree=145319603,f_bavail=13107200-1)
    mismatch(host,docs,'FREE_SPACE_BELOW_FLOOR',item='free_space')              # root still has room: the figure is f_bavail, as the producer measures
    host,docs=ready();host.vfs[ROOT_DEVICE]=types.SimpleNamespace(f_frsize=0,f_blocks=1,f_bfree=1,f_bavail=1)
    receipt=partial(host,docs,'free_space');assert receipt['items']['free_space']['code']=='STATVFS_INVALID' and receipt['items']['catalog']['status']=='COMPLETE'
    # a data volume without room does not matter under placement A, and the root filesystem does not matter under placement B
    host,docs=ready();host.vfs[DATA_DEVICE]=types.SimpleNamespace(f_frsize=4096,f_blocks=25656558,f_bfree=10,f_bavail=10);assert run(host,docs)['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'
    host,docs=ready(placement='B',freed=f.FREED_BYTES);host.vfs[ROOT_DEVICE]=types.SimpleNamespace(f_frsize=4096,f_blocks=162243833,f_bfree=10,f_bavail=10)
    assert run(host,docs)['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'


# ---------------------------------------------------------------- drop-ins, links, manager, docker
def test_drop_ins_enablement_links_shadows_and_leftovers_are_findings():
    for path,kind,code in ((UNITS+'/c3po-massive.service.d','dir','DROP_IN_PRESENT'),('/run/systemd/system/service.d','dir','DROP_IN_PRESENT'),
                           ('/usr/lib/systemd/system/c3po-.timer.d','dir','DROP_IN_PRESENT'),(UNITS+'/timers.target.wants/c3po-massive.timer','symlink','ENABLEMENT_LINK_PRESENT'),
                           ('/usr/lib/systemd/system/timers.target.wants/c3po-massive.timer','symlink','ENABLEMENT_LINK_PRESENT'),
                           ('/run/systemd/transient/c3po-massive.service','file','UNIT_SHADOWED_IN_OTHER_PATH'),
                           ('/run/systemd/generator.early/c3po-massive.timer','file','UNIT_SHADOWED_IN_OTHER_PATH'),
                           (UNITS+'/c3po-massive.service.wants','dir','OWN_DEPENDENCY_DIRECTORY_PRESENT'),
                           (UNITS+'/c3po-massive.timer.requires','dir','OWN_DEPENDENCY_DIRECTORY_PRESENT'),
                           ('/usr/lib/systemd/system/c3po-massive.service.upholds','dir','OWN_DEPENDENCY_DIRECTORY_PRESENT'),
                           ('/run/systemd/system/c3po-massive.timer.wants','dir','OWN_DEPENDENCY_DIRECTORY_PRESENT'),
                           (UNITS+'/.hostops-0123456789abcdef-0.partial','file','PRIOR_TEMPORARY_PRESENT')):
        host,docs=ready();host.tree.add(path,kind=kind,mode=0o777 if kind=='symlink' else 0o755)
        receipt=mismatch(host,docs,code,item='conflicts')
        if code!='PRIOR_TEMPORARY_PRESENT':assert receipt['items']['conflicts']['conflict_rows'][0]['directory']==os.path.dirname(path) if kind!='symlink' else True
    host,docs=ready();host.tree.remove('/usr/lib');host.tree.add('/usr/lib',kind='symlink',mode=0o777)
    receipt=partial(host,docs,'conflicts');assert receipt['items']['conflicts']['directories']['/usr/lib/systemd/system']['code']=='SYMLINK_COMPONENT'
    # links inside the unit's own dependency directory: dependencies of the installed unit that no drop-in and no property shows
    host,docs=ready();host.tree.add(UNITS+'/c3po-massive.service.wants/other.service',kind='symlink',mode=0o777)
    receipt=mismatch(host,docs,'OWN_DEPENDENCY_DIRECTORY_PRESENT',item='conflicts')
    assert receipt['items']['conflicts']['conflict_rows']==[{'code':'OWN_DEPENDENCY_DIRECTORY_PRESENT','directory':UNITS,'name':'c3po-massive.service.wants','within':None}]
    # an alias of an installed unit, in the install directory or in another lookup directory
    for directory,target in ((UNITS,'c3po-massive.service'),('/run/systemd/system','/etc/systemd/system/c3po-massive.timer')):
        host,docs=ready();host.tree.add(directory+'/backup'+target[-8:].replace('.service','')+('.service' if target.endswith('.service') else ''),kind='symlink',mode=0o777).target=target
        receipt=mismatch(host,docs,'ALIAS_LINK_PRESENT',item='conflicts');assert receipt['items']['conflicts']['conflict_rows'][0]['within']==target.rsplit('/',1)[-1]

def unit(host,name,**changes):host.units[name]=dict(host.units[name],**changes)
def test_manager_view_timer_disabled_units_inactive_and_nothing_else_attached():
    host,docs=ready(loaded=False);receipt=run(host,docs)
    assert receipt['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET' and receipt['items']['unit:c3po-massive.timer']['load_state']=='not-found'
    for state in ('loaded','not-found','stub','merged'):                 # no daemon-reload has run: these are reported, not findings
        host,docs=ready();unit(host,'c3po-massive.service',LoadState=state);assert run(host,docs)['items']['unit:c3po-massive.service']['load_state']==state
    for state in ('bad-setting','error','masked'):                       # wrong at any reload state: the first place systemd's own parse shows
        for name in ('c3po-massive.service','c3po-massive.timer'):
            host,docs=ready();unit(host,name,LoadState=state);receipt=mismatch(host,docs,'UNIT_LOAD_STATE',item='unit:'+name)
            assert receipt['items']['unit:'+name]['load_state']==state
    for name,changes,findings in (
            ('c3po-massive.timer',{'ActiveState':'active','SubState':'waiting'},['UNIT_NOT_INACTIVE']),('c3po-massive.service',{'ActiveState':'failed'},['UNIT_NOT_INACTIVE']),
            ('c3po-massive.service',{'ActiveState':'activating'},['UNIT_NOT_INACTIVE']),
            ('c3po-massive.timer',{'UnitFileState':'enabled'},['ENABLEMENT_SOURCES_DISAGREE','TIMER_NOT_DISABLED']),
            ('c3po-massive.timer',{'UnitFileState':'masked'},['ENABLEMENT_SOURCES_DISAGREE','TIMER_NOT_DISABLED']),
            ('c3po-massive.service',{'FragmentPath':'/run/systemd/transient/c3po-massive.service'},['FRAGMENT_PATH_MISMATCH']),
            ('c3po-massive.timer',{'FragmentPath':'/usr/lib/systemd/system/c3po-massive.timer'},['FRAGMENT_PATH_MISMATCH']),
            ('c3po-massive.service',{'DropInPaths':'/etc/systemd/system/c3po-massive.service.d/override.conf /run/x.conf'},['DROP_IN_REPORTED_BY_MANAGER']),
            ('c3po-massive.timer',{'WantedBy':'timers.target'},['REVERSE_DEPENDENCY_REPORTED_BY_MANAGER']),
            ('c3po-massive.service',{'RequiredBy':'other.service'},['REVERSE_DEPENDENCY_REPORTED_BY_MANAGER']),
            ('c3po-massive.service',{'TriggeredBy':'other.timer'},['TRIGGER_REPORTED_BY_MANAGER']),
            ('c3po-massive.timer',{'TriggeredBy':'c3po-massive.timer'},['TRIGGER_REPORTED_BY_MANAGER'])):
        host,docs=ready();unit(host,name,**changes);mismatch(host,docs,*findings)
    for word in ('enabled','enabled-runtime','static','masked','linked','indirect','generated','bad'):
        host,docs=ready();host.is_enabled['c3po-massive.timer']=word;receipt=mismatch(host,docs,'ENABLEMENT_SOURCES_DISAGREE','TIMER_NOT_DISABLED')
        assert receipt['items']['timer_enabled']['word']==word
    host,docs=ready();del host.is_enabled['c3po-massive.timer'];receipt=partial(host,docs,'timer_enabled')
    assert receipt['items']['timer_enabled']['code']=='IS_ENABLED_NO_ANSWER','no answer is never read as disabled'
    host,docs=ready();unit(host,'c3po-massive.timer',Id='other.timer');receipt=partial(host,docs,'unit:c3po-massive.timer');assert receipt['items']['unit:c3po-massive.timer']['code']=='UNIT_ID_MISMATCH'
    host,docs=ready();unit(host,'docker.service',ActiveState='inactive');mismatch(host,docs,'DOCKER_UNIT_NOT_ACTIVE',item='docker_unit')
    host,docs=ready();del host.units['docker.service'];mismatch(host,docs,'DOCKER_UNIT_NOT_ACTIVE',item='docker_unit')
    for line,number in ((b'systemd 239 (239-58.el8)\n',239),(b'systemd 219\n',219)):
        host,docs=ready();host.systemd_version=line;receipt=mismatch(host,docs,'SYSTEMD_TOO_OLD',item='systemd_version');assert receipt['items']['systemd_version']['number']==number
    host,docs=ready();host.systemd_version=b'systemd 240\n';run(host,docs)
    host,docs=ready();host.systemd_version=b'no version here\n';receipt=partial(host,docs,'systemd_version');assert receipt['items']['systemd_version']['code']=='VERSION_LINE_INVALID'

def test_image_by_id_retention_tag_at_the_same_id_init_binary_and_docker_version():
    reference='c3po/backend:'+f.TAG
    host,docs=ready();host.docker.images[0]['RepoTags'].remove(reference);host.docker.images[1]['RepoTags'].append(reference)
    receipt=mismatch(host,docs,'RETENTION_TAG_MISMATCH',item='retention_tag');assert receipt['items']['retention_tag']['id']==hostemu.OTHER and receipt['items']['image']['matches'] is True
    host,docs=ready();host.docker.images[0]['RepoTags'].remove(reference)
    receipt=partial(host,docs,'retention_tag');assert receipt['items']['retention_tag']['code']=='IMAGE_ABSENT_OR_UNREADABLE','a failed inspect is never read as absence'
    host,docs=ready();host.docker.images[0]['Id']='sha256:'+'ee'*32;receipt=partial(host,docs,'image',findings=['RETENTION_TAG_MISMATCH'])
    host,docs=ready();original=host.docker.find
    def find(wanted):
        item=original(wanted);return dict(item,RepoTags=['c3po/backend:production']) if wanted==reference and item is not None else item
    host.docker.find=find;mismatch(host,docs,'RETENTION_TAG_MISMATCH',item='retention_tag')          # right ID, but the reference is not among its tags
    for version,findings in (('20.10.0',[]),('20.9.9',['DOCKER_TOO_OLD']),('19.03.15',['DOCKER_TOO_OLD']),('29.0.0-rc.1',[]),('20.10',[])):
        host,docs=ready();host.docker.version['Server']['Version']=version
        receipt=mismatch(host,docs,*findings,item='docker_daemon') if findings else run(host,docs);assert receipt['items']['docker_daemon']['server_version']==version
    host,docs=ready();host.docker.info['InitBinary']='';mismatch(host,docs,'INIT_BINARY_MISSING',item='docker_daemon')
    host,docs=ready();host.tree.remove(INIT);receipt=mismatch(host,docs,'INIT_BINARY_MISSING');assert receipt['items']['docker_init']['any_present'] is False
    host,docs=ready();host.tree.remove('/usr/libexec');host.tree.add('/usr/libexec',kind='symlink',mode=0o777)
    receipt=partial(host,docs,'docker_daemon','docker_init');assert receipt['items']['docker_init']['any_present'] is None and 'INIT_BINARY_MISSING' not in receipt['findings']
    # a name that merely exists is not an init binary: only a regular file of root, not writable by group or other, with an execute bit, counts
    for kind,attributes in (('symlink',{'mode':0o777}),('dir',{'mode':0o755}),('fifo',{'mode':0o755}),('file',{'mode':0o644}),('file',{'mode':0o755,'uid':1000}),
                            ('file',{'mode':0o775}),('file',{'mode':0o757})):
        host,docs=ready();host.tree.remove(INIT);host.tree.add(INIT,kind=kind,**attributes)
        receipt=mismatch(host,docs,'INIT_BINARY_MISSING',item='docker_daemon');item=receipt['items']['docker_init']
        assert (item['any_present'],item['present_paths'],item['present_not_counted_paths'],item['status'])==(False,[],[INIT],'COMPLETE'),(kind,attributes)
        assert item['candidates'][INIT]['exists'] is True,'the row is still reported'
    for mode in (0o755,0o555,0o700,0o100,0o4755):
        host,docs=ready();host.tree.get(INIT).mode=mode;assert run(host,docs)['items']['docker_init']['present_paths']==[INIT]
    host,docs=ready();host.tree.add('/usr/bin/docker-init',kind='symlink',mode=0o777);item=run(host,docs)['items']['docker_init']    # one usable, one not
    assert (item['present_paths'],item['present_not_counted_paths'],item['any_present'])==([INIT],['/usr/bin/docker-init'],True)
    # the pinned image: its revision label against the signed one, and whether it still is the production image (reported)
    host,docs=ready(revision='1'*40);receipt=mismatch(host,docs,'IMAGE_REVISION_MISMATCH',item='image')
    assert (receipt['items']['image']['revision_label'],receipt['items']['image']['signed_revision'],receipt['items']['retention_tag']['matches'])==(hostemu.REVISION,'1'*40,True)
    host,docs=ready();del host.docker.images[0]['Config']['Labels']['org.opencontainers.image.revision']
    receipt=mismatch(host,docs,'IMAGE_REVISION_MISMATCH',item='image');assert receipt['items']['image']['revision_label'] is None
    host,docs=ready();host.docker.images[0]['RepoTags'].remove('c3po/backend:production');host.docker.images[1]['RepoTags'].append('c3po/backend:production')
    receipt=run(host,docs);assert receipt['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET','after a later deploy the unit keeps its ID by design'
    assert receipt['items']['image']['production_reference_among_repo_tags'] is False and receipt['items']['image']['production_reference_reported_not_gated'] is True
    host,docs=ready();host.docker.images[0]['RepoTags']+=['c3po/backend:extra-%d'%index for index in range(9)]
    host.docker.images[0]['RepoTags'].remove('c3po/backend:production');assert run(host,docs)['items']['image']['production_reference_among_repo_tags'] is None
    host,docs=ready();host.docker.info['ServerVersion']='';receipt=partial(host,docs,'docker_daemon');assert receipt['items']['docker_daemon']['code']=='DAEMON_INFO_EMPTY'
    host,docs=ready();host.docker.info['SecurityOptions']=['name=rootless','name=userns'];receipt=run(host,docs)
    assert receipt['items']['docker_daemon']['rootless_reported'] is True and receipt['items']['docker_daemon']['userns_remap_reported'] is True
    host,docs=ready();host.tree.add('/run/reboot-required',kind='file');receipt=run(host,docs)
    assert receipt['items']['reboot_marker']['exists'] is True and receipt['outcome']=='READBACK_ALL_OBSERVED_ALL_EXPECTATIONS_MET'

def test_commands_that_fail_hang_or_cannot_be_trusted_mark_only_their_own_items():
    host,docs=ready();host.tree.get('/usr/bin/systemctl').mode=0o775
    receipt=partial(host,docs,'docker_unit','systemd_version','timer_enabled','unit:c3po-massive.service','unit:c3po-massive.timer')
    assert receipt['items']['docker_unit']['code']=='BINARY_UNAVAILABLE_OR_UNSAFE' and receipt['items']['image']['status']=='COMPLETE'
    assert not [command for command in host.commands if command['argv'][0].endswith('systemctl')]
    host,docs=ready();host.hang.add('docker');receipt=partial(host,docs,'docker_daemon','image','retention_tag')
    assert [receipt['items'][name]['code'] for name in ('image','retention_tag','docker_daemon')]==['COMMAND_TIMEOUT','COMMAND_TIMEOUT','COMMAND_SKIPPED_AFTER_TIMEOUT']
    assert len([command for command in host.commands if command['argv'][0].endswith('docker')])==2 and receipt['items']['units']['matches'] is True
    host,docs=ready();host.noatime_available=False;receipt=docs.run(host);assert receipt['outcome']=='PARTIAL_OBSERVED' and receipt['items']['units']['code']=='NOATIME_UNAVAILABLE'


# ---------------------------------------------------------------- boot, window, size
def test_evidence_from_an_earlier_boot_is_one_finding_and_device_numbers_are_not_compared():
    host,docs=ready();host.tree.get(m.BOOT_ID_PATH).content=bytearray(b'11111111-2222-3333-4444-555555555555\n')
    receipt=mismatch(host,docs,'EVIDENCE_FROM_EARLIER_BOOT',item='boot');assert receipt['items']['boot']['device_numbers_compared'] is False
    def renumber(host):
        def walk(node):
            if node.dev==811:node.dev=898
            for child in node.children.values():walk(child)
        walk(host.tree.root);host.vfs[898]=host.vfs[811]
    host,docs=ready(placement='B',freed=f.FREED_BYTES);host.tree.get(m.BOOT_ID_PATH).content=bytearray(b'11111111-2222-3333-4444-555555555555\n');renumber(host)
    # the catalog itself binds the device: that one is a real finding in any boot
    mismatch(host,docs,'CATALOG_IDENTITY_MISMATCH','EVIDENCE_FROM_EARLIER_BOOT')
    host,docs=ready(placement='B',freed=f.FREED_BYTES);renumber(host);mismatch(host,docs,'CATALOG_IDENTITY_MISMATCH','DATA_VOLUME_ROW_CHANGED','LAYOUT_IDENTITY_CHANGED')
    host,docs=ready();host.tree.remove(m.BOOT_ID_PATH);receipt=partial(host,docs,'boot');assert receipt['items']['boot']['code']=='OS_ERROR'

def test_window_expiry_during_the_readback_keeps_what_was_read_and_starts_nothing_more():
    host,docs=ready();wall=[f.NOW];calls=[0]
    def clock():
        calls[0]+=1
        if calls[0]>40:wall[0]=f.NOW+timedelta(minutes=6)
        return wall[0]
    receipt=docs.run(host,clock=clock)
    assert (receipt['status'],receipt['outcome'])==(m.PARTIAL_STATUS,'PARTIAL_OR_WINDOW_EXPIRED') and f.sealed(receipt)
    expired=[name for name,item in receipt['items'].items() if item.get('code')=='GO_EXPIRED'];assert expired and receipt['items']['boot']['status']=='COMPLETE'
    assert host.commands==[] or len(host.commands)<9

def test_receipt_at_the_caps_needs_no_reduction_and_reduction_never_yields_complete(monkeypatch):
    host,docs=ready()
    for directory in m.LOOKUP_DIRECTORIES:
        host.tree.add(directory)
        for name in m.UNITS:
            for candidate in m.drop_in_names(name)+[name]:host.tree.add(directory+'/'+candidate,mode=0o755)
            for index in range(3):host.tree.add(directory+'/target-%d.target.wants/%s'%(index,name),kind='symlink',mode=0o777)
    receipt=docs.run(host)
    assert receipt['items']['conflicts']['findings_truncated'] is True and len(receipt['items']['conflicts']['conflict_rows'])==64
    assert receipt['size_reductions']==[] and len(f.line(receipt))<40000 and receipt['outcome']=='OBSERVED_ALL_EXPECTATIONS_NOT_MET'
    host,docs=ready();monkeypatch.setattr(m,'RECEIPT_LIMIT',9000);receipt=docs.run(host)
    assert receipt['status']==m.PARTIAL_STATUS and receipt['outcome']=='PARTIAL_OBSERVED' and receipt['size_reductions'] and f.sealed(receipt) and len(f.line(receipt))<=9000
