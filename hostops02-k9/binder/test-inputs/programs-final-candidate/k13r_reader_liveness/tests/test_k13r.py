"""K13r's own tests on the emulated host (tests/k13r.py): both modes complete, every finding, every item that cannot be
observed (UNAVAILABLE, never an absence), the plan's refusals, a failure and a death at every host call, and what
never leaves a run. Nothing here ran on a host; docker top and docker logs are not used (not reading verbs of the core)."""
from datetime import timedelta
import json

import pytest

import family as f
import hostemu
import k13r
from family import refusal

def run(mode='LIVE',setup=None,host_change=None,**options):
    docs,host=k13r.case(mode=mode,setup=setup)
    if host_change is not None:host_change(host)
    before=k13r.state_of(host);receipt=docs.run(host,**options)
    assert f.sealed(receipt) and hostemu.SECRET.encode() not in f.line(receipt) and b'never-emit' not in f.line(receipt) and b'postgresql' not in f.line(receipt)
    assert k13r.state_of(host)==before and host.mutating()==[] and receipt['mutating_calls']['issued']==0 and receipt['writes']==0
    assert all(entry['argv'][1] in ('show','is-enabled','container','ps') for entry in host.commands)
    return receipt,host

def reader(host):return host.docker.container('c3po-reader')
def finding(receipt,code,item):
    assert (receipt['status'],receipt['outcome'])==('PARTIAL_METADATA_REQUIRES_REVIEW','READER_NOT_AS_EXPECTED') and code in receipt['findings'],receipt['findings']
    assert code in receipt['items'][item]['findings'] and receipt['items_not_complete']==[] and receipt['expectations_met'] is False

# ---------------------------------------------------------------- complete
def test_live_reads_every_item_with_exactly_these_commands():
    receipt,host=run('LIVE')
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','READER_LIVE_ALL_EXPECTATIONS_MET',None)
    assert sorted(receipt['items'])==['boot','command','container','containers','mounts','other_readers','service','timer']
    item=receipt['items'];own=reader(host)
    assert item['container']['id']==own['Id'] and item['container']['image_equal_the_pin'] is True and item['container']['restarts']==0
    assert item['container']['started_at']==own['State']['StartedAt'] and item['mounts']['count']==5 and item['other_readers']['scanned']==8
    assert item['mounts']['not_root_controlled_sources']==['/mnt/day-d-data'],'decision 6: the data volume bind is reported'
    assert item['command']=={'status':'COMPLETE','findings':[],'launcher_command':True,'init':True,'read_only_root':True,'uid_0':True,'elapsed_ms':0}
    assert item['service']['NRestarts']=='0' and item['timer']['enabled']=='enabled' and item['boot']['boot_id_sha256']==f.BOOT_SHA
    assert item['containers']['containers']==9
    inspected=[entry['argv'] for entry in host.commands if entry['argv'][1]=='container']
    assert all(argv[2]=='inspect' and argv[3]=='--format' and len(argv)==6 for argv in inspected)
    templates={argv[4] for argv in inspected};m=k13r.K().m
    assert templates=={m.CONTAINER_FORMAT,m.MOUNTS_FORMAT,m.COMMAND_FORMAT,m.SCAN_FORMAT} and not [t for t in templates if 'Env' in t]
    assert [argv[5] for argv in inspected if argv[4]==m.MOUNTS_FORMAT]==[own['Id']] and [argv[5] for argv in inspected if argv[4]==m.COMMAND_FORMAT]==[own['Id']]
    assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False and receipt['commands_started']=={'READ':15,'CONTAINER':0,'EFFECT':0}

def test_stopped_reads_no_container_inspect_of_the_reader():
    receipt,host=run('STOPPED')
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','READER_STOPPED_ALL_EXPECTATIONS_MET',None)
    assert sorted(receipt['items'])==['boot','containers','other_readers','service','timer'] and receipt['items']['containers']['reader'] is None

def test_stopped_accepts_a_failed_service():
    receipt,_=run('STOPPED',setup=lambda h:h.units['c3po-reader.service'].update(ActiveState='failed',SubState='failed',Result='exit-code'))
    assert receipt['outcome']=='READER_STOPPED_ALL_EXPECTATIONS_MET' and receipt['items']['service']['Result']=='exit-code'

def test_the_timer_is_read_without_nrestarts_which_a_timer_does_not_have():
    for mode in ('LIVE','STOPPED'):
        docs,host=k13r.case(mode=mode);assert 'NRestarts' not in host.units['c3po-reader.timer']
        receipt=docs.run(host);assert receipt['items']['timer']['status']=='COMPLETE' and receipt['expectations_met'] is True
        timer=[entry['argv'] for entry in host.commands if entry['argv'][1:3]==['show','c3po-reader.timer']][0]
        assert 'NRestarts' not in timer and timer[4::2]==['Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','Result']
        service=[entry['argv'] for entry in host.commands if entry['argv'][1:3]==['show','c3po-reader.service']][0];assert service[-1]=='NRestarts'
    receipt,_=run('LIVE',setup=lambda h:h.units['c3po-reader.timer'].update(NRestarts='0'))
    assert receipt['items']['timer']['status']=='COMPLETE','a property not asked for is ignored'
    receipt,_=run('LIVE',setup=lambda h:h.units['c3po-reader.timer'].pop('Result'))
    assert receipt['items']['timer']['code']=='UNIT_PROPERTIES_INVALID'

def test_success_criterion_follows_the_mode_and_effects_say_nothing_changes():
    m=k13r.K().m
    for mode,outcome in (('LIVE','READER_LIVE_ALL_EXPECTATIONS_MET'),('STOPPED','READER_STOPPED_ALL_EXPECTATIONS_MET')):
        docs,_=k13r.case(mode=mode);effects=m.effects_of(docs.plan)
        assert m.success_of(docs.plan)==outcome==effects['success_outcome']==docs.go['success_criterion']
        assert effects['writes']==0 and effects['side_effects']==[] and effects['image_id']==hostemu.BACKEND and effects['mode']==mode
        assert effects['evidence_boot_id_sha256']==f.BOOT_SHA and effects['operation']=='GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01'
        assert effects['epoch']=='R2D2-V2-SHADOW-2026-10-05'
        assert effects['source_bind']=={'source':'/var/lib/c3po/r2d2-v2-source-20261005','target':'/c3po-source'} and effects['binds_not_root_controlled']==['/mnt/day-d-data']
    live=m.effects_of(k13r.case(mode='LIVE')[0].plan)['expect'];stopped=m.effects_of(k13r.case(mode='STOPPED')[0].plan)['expect']
    assert live=={'service':'active','timer':'enabled and active','reader_container':'one, running, the signed image, five read-only binds, the launcher command','other_readers':'none'}
    assert stopped=={'service':'inactive or failed','timer':'disabled and inactive','reader_container':'none','other_readers':'none'}

def test_constants_of_the_reader():
    m=k13r.K().m
    assert [list(pair) for pair in m.READER_BINDS]+[[m.SOURCE_ROOT,'/c3po-source']]==[list(pair) for pair in k13r.BINDS] and m.NOT_ROOT_CONTROLLED_SOURCES==('/mnt/day-d-data',) and m.READER_ARGS==('-I','-B','/c3po-reader/reader_launcher.py')
    assert m.EVIDENCE_OPERATIONS==('GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01',) and m.MODE_OUTCOMES=={'LIVE':m.COMPLETE_OUTCOME,'STOPPED':m.STOPPED_OUTCOME}


# ---------------------------------------------------------------- the plan
@pytest.mark.parametrize('change,code',[(lambda p:p.update(source_target='/app/day-d-data/source'),'SOURCE_TARGET_INVALID'),
                                        (lambda p:p.update(source_target='/c3po-capacity'),'SOURCE_TARGET_INVALID'),
                                        (lambda p:p.update(source_target='/c3po-reader'),'SOURCE_TARGET_INVALID'),
                                        (lambda p:p.update(source_target='/c3po-bar-journal'),'SOURCE_TARGET_INVALID'),
                                        (lambda p:p.update(source_target=None),'SOURCE_TARGET_INVALID'),
                                        (lambda p:p.update(mode='RUNNING'),'MODE_INVALID'),(lambda p:p.update(mode=None),'MODE_INVALID'),
                                        (lambda p:p.update(image_id='c3po/backend:production'),'IMAGE_ID_INVALID'),
                                        (lambda p:p.update(image_id='sha256:'+'F'*64),'IMAGE_ID_INVALID'),
                                        (lambda p:p.update(evidence_boot_id_sha256='0'*64),'EVIDENCE_BOOT_UNBOUND'),
                                        (lambda p:p.update(evidence_boot_id_sha256=None),'EVIDENCE_BOOT_UNBOUND')])
def test_plan_refusals(change,code):
    docs,host=k13r.case();change(docs.plan);docs.chain()
    assert refusal(docs.authenticate)==code
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'])==('REFUSED',code)


# ---------------------------------------------------------------- findings, one at a time
def units(unit,**values):return lambda h:h.units[unit].update(values)
LIVE_FINDINGS=[
    ('boot',lambda h:setattr(h.tree.get('/proc/sys/kernel/random/boot_id'),'content',bytearray(b'1f8fad5b-d9cb-469f-a165-70867728950e\n')),'BOOT_NOT_THE_EVIDENCE','boot'),
    ('service_not_loaded',units('c3po-reader.service',LoadState='not-found'),'READER_UNIT_NOT_LOADED','service'),
    ('timer_fragment',units('c3po-reader.timer',FragmentPath='/run/systemd/system/c3po-reader.timer'),'READER_UNIT_NOT_THE_INSTALLED_FILE','timer'),
    ('service_drop_in',units('c3po-reader.service',DropInPaths='/etc/systemd/system/c3po-reader.service.d/x.conf'),'READER_UNIT_NOT_THE_INSTALLED_FILE','service'),
    ('service_activating',units('c3po-reader.service',ActiveState='activating'),'SERVICE_NOT_ACTIVE','service'),
    ('service_failed',units('c3po-reader.service',ActiveState='failed'),'SERVICE_NOT_ACTIVE','service'),
    ('timer_disabled',lambda h:h.is_enabled.update({'c3po-reader.timer':'disabled'}),'TIMER_NOT_ENABLED_AND_ACTIVE','timer'),
    ('timer_inactive',units('c3po-reader.timer',ActiveState='inactive'),'TIMER_NOT_ENABLED_AND_ACTIVE','timer'),
    ('container_exited',lambda h:reader(h)['State'].update(Running=False,Status='exited'),'READER_CONTAINER_NOT_RUNNING','containers'),
    ('container_image',lambda h:reader(h).update(Image=hostemu.OTHER),'READER_IMAGE_NOT_THE_PIN','container'),
    ('mount_writable',lambda h:reader(h)['Mounts'][0].update(RW=True),'READER_MOUNT_WRITABLE','mounts'),
    ('mount_missing',lambda h:reader(h)['Mounts'].pop(),'READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS','mounts'),
    ('mount_fifth',lambda h:reader(h)['Mounts'].append(k13r.mount('/var/run/docker.sock','/var/run/docker.sock')),'READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS','mounts'),
    ('mount_source',lambda h:reader(h)['Mounts'][1].update(Source='/var/lib/c3po-bar/journal2'),'READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS','mounts'),
    ('mount_target',lambda h:reader(h)['Mounts'][1].update(Destination='/c3po-journal'),'READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS','mounts'),
    ('mount_without_the_source_root',lambda h:reader(h).update(Mounts=[k13r.mount(s,t) for s,t in k13r.BINDS[:4]]),'READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS','mounts'),
    ('mount_source_root_elsewhere',lambda h:reader(h)['Mounts'][4].update(Destination='/c3po-src'),'READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS','mounts'),
    ('mount_volume',lambda h:reader(h)['Mounts'][2].update(Type='volume'),'READER_MOUNTS_NOT_THE_FIVE_READ_ONLY_BINDS','mounts'),
    ('command_worker',lambda h:reader(h).update(Args=['-m','app.r2d2_v2_shadow_worker']),'READER_COMMAND_NOT_THE_LAUNCHER','command'),
    ('command_unisolated',lambda h:reader(h).update(Args=['-B','/c3po-reader/reader_launcher.py']),'READER_COMMAND_NOT_THE_LAUNCHER','command'),
    ('command_path',lambda h:reader(h).update(Path='/bin/sh'),'READER_COMMAND_NOT_THE_LAUNCHER','command'),
    ('no_init',lambda h:reader(h)['HostConfig'].update(Init=False),'READER_WITHOUT_INIT','command'),
    ('init_null',lambda h:reader(h)['HostConfig'].update(Init=None),'READER_WITHOUT_INIT','command'),
    ('writable_root',lambda h:reader(h)['HostConfig'].update(ReadonlyRootfs=False),'READER_ROOT_NOT_READ_ONLY','command'),
    ('user',lambda h:reader(h)['Config'].update(User='1000:1000'),'READER_NOT_UID_0','command'),
    ('user_empty',lambda h:reader(h)['Config'].update(User=''),'READER_NOT_UID_0','command'),
    ('reader_elsewhere',lambda h:h.docker.containers.append(k13r.reader_container(name='by-hand')),'READER_PROCESS_ELSEWHERE','other_readers'),
    ('worker_in_compose',lambda h:h.docker.container('c3po-r2d2-worker-1').update(Args=['-m','app.r2d2_v2_shadow_worker']),'READER_PROCESS_ELSEWHERE','other_readers'),
    ('launcher_path_elsewhere',lambda h:h.docker.container('c3po-api-1').update(Path='/c3po-reader/reader_launcher.py',Args=None),'READER_PROCESS_ELSEWHERE','other_readers'),
]
@pytest.mark.parametrize('label,setup,code,item',LIVE_FINDINGS,ids=[row[0] for row in LIVE_FINDINGS])
def test_live_findings(label,setup,code,item):
    receipt,_=run('LIVE',setup=setup);finding(receipt,code,item)

STOPPED_FINDINGS=[
    ('service_active',units('c3po-reader.service',ActiveState='active'),'SERVICE_NOT_STOPPED','service'),
    ('service_reloading',units('c3po-reader.service',ActiveState='reloading'),'SERVICE_NOT_STOPPED','service'),
    ('service_deactivating',units('c3po-reader.service',ActiveState='deactivating'),'SERVICE_NOT_STOPPED','service'),
    ('service_activating',units('c3po-reader.service',ActiveState='activating'),'SERVICE_NOT_STOPPED','service'),
    ('timer_enabled',lambda h:h.is_enabled.update({'c3po-reader.timer':'enabled'}),'TIMER_NOT_DISABLED_AND_INACTIVE','timer'),
    ('timer_active',units('c3po-reader.timer',ActiveState='active'),'TIMER_NOT_DISABLED_AND_INACTIVE','timer'),
    ('container_left',lambda h:h.docker.containers.append(k13r.reader_container(running=False)),'READER_CONTAINER_PRESENT','containers'),
    ('reader_elsewhere',lambda h:h.docker.containers.append(k13r.reader_container(name='by-hand')),'READER_PROCESS_ELSEWHERE','other_readers'),
    ('stopped_not_loaded',units('c3po-reader.timer',LoadState='masked'),'READER_UNIT_NOT_LOADED','timer'),
]
@pytest.mark.parametrize('label,setup,code,item',STOPPED_FINDINGS,ids=[row[0] for row in STOPPED_FINDINGS])
def test_stopped_findings(label,setup,code,item):
    receipt,_=run('STOPPED',setup=setup);finding(receipt,code,item)

def test_facts_of_the_findings_are_reported_as_read():
    receipt,_=run('LIVE',setup=lambda h:reader(h).update(Image=hostemu.OTHER));assert receipt['items']['container']['image_equal_the_pin'] is False
    receipt,_=run('LIVE',setup=lambda h:reader(h)['Mounts'].append(k13r.mount('/x','/y')));assert receipt['items']['mounts']['count']==6
    receipt,_=run('LIVE',setup=lambda h:reader(h)['Mounts'].pop(0));assert receipt['items']['mounts']['not_root_controlled_sources']==[]
    receipt,_=run('LIVE',setup=lambda h:reader(h).update(Args=['-m','app.r2d2_v2_shadow_worker']));assert receipt['items']['command']['launcher_command'] is False

def test_a_reader_that_stops_between_the_listing_and_its_inspect_is_a_finding():
    def setup(host):
        def hook(host,name,detail,calls):
            if name=='run' and detail[0][1:3]==['container','inspect'] and detail[0][-1]=='c3po-reader':reader(host)['State'].update(Running=False,Status='exited')
        host.hook=hook
    docs,host=k13r.case(setup=setup);receipt=docs.run(host);assert host.mutating()==[]
    finding(receipt,'READER_CONTAINER_NOT_RUNNING','container')
    assert receipt['items']['containers']['findings']==[]

def decoy_of(target):
    """A stopped container named after the ID of another, listed first: the emulated CLI then answers an inspect of that ID
    with the decoy, so the printed ID is not the one asked for."""
    def setup(host):
        item=k13r.reader_container(name='decoy',running=False);item['Name']='/'+target(host)['Id'];host.docker.containers.insert(0,item)
    return setup
def test_an_inspect_that_answers_for_another_container_is_unavailable():
    receipt,_=run('LIVE',setup=decoy_of(reader))
    assert receipt['items']['command']['code']=='CONTAINER_COMMAND_INVALID' and receipt['outcome']=='READER_OBSERVATION_INCOMPLETE'
    receipt,_=run('LIVE',setup=decoy_of(lambda h:h.docker.container('c3po-api-1')))
    assert receipt['items']['other_readers']['code']=='CONTAINER_COMMAND_INVALID'

def test_the_source_bind_target_is_the_signed_one():
    docs,host=k13r.case(setup=lambda h:reader(h)['Mounts'][4].update(Destination='/c3po-src'));docs.plan['source_target']='/c3po-src';docs.chain()
    receipt=docs.run(host);assert receipt['outcome']=='READER_LIVE_ALL_EXPECTATIONS_MET',receipt['findings']

def test_a_window_of_fifteen_minutes_is_the_longest():
    docs,host=k13r.case();now=docs.now
    docs.shift(now,now+timedelta(seconds=900));docs.authenticate()
    docs.shift(now,now+timedelta(seconds=901));assert refusal(docs.authenticate)=='WINDOW_SPAN'

def test_a_capacity_day_process_and_an_exited_container_are_not_readers():
    def setup(host):
        host.docker.containers.append(k13r.reader_container(name='capacity-day-1',args=['-m','app.r2d2_v2_shadow_worker','--prepare-capacity-day']))
        host.docker.containers.append(k13r.reader_container(name='old',running=False))
    receipt,_=run('LIVE',setup=setup)
    assert receipt['outcome']=='READER_LIVE_ALL_EXPECTATIONS_MET' and receipt['items']['other_readers']['scanned']==9
def test_a_paused_reader_elsewhere_is_found():
    def setup(host):
        item=k13r.reader_container(name='paused');item['State'].update(Status='paused',Paused=True);host.docker.containers.append(item)
    receipt,_=run('LIVE',setup=setup);finding(receipt,'READER_PROCESS_ELSEWHERE','other_readers')
    assert receipt['items']['other_readers']['reader_like']==['paused']

def test_no_word_of_a_command_and_no_mount_of_another_container_leaves():
    def setup(host):host.docker.container('c3po-api-1')['Args']=['--token','never-emit-argument-canary']
    receipt,_=run('LIVE',setup=setup)
    assert b'never-emit-argument-canary' not in f.line(receipt) and b'/opt/x' not in f.line(receipt) and b'uvicorn' not in f.line(receipt)


# ---------------------------------------------------------------- what cannot be observed is UNAVAILABLE, never an absence
UNAVAILABLE=[
    ('service_property_missing',lambda h:h.units['c3po-reader.service'].pop('NRestarts'),'service','UNIT_PROPERTIES_INVALID'),
    ('service_property_value',lambda h:h.units['c3po-reader.service'].update(SubState='x;y'),'service','UNIT_PROPERTIES_INVALID'),
    ('service_id',lambda h:h.units['c3po-reader.service'].update(Id='c3po-massive.service'),'service','UNIT_PROPERTIES_INVALID'),
    ('service_non_ascii',lambda h:h.units['c3po-reader.service'].update(SubState='d\xe9ad'),'service','UNIT_PROPERTIES_INVALID'),
    ('service_line_without_equals',lambda h:h.units['c3po-reader.service'].update(SubState='dead\nfoo'),'service','UNIT_PROPERTIES_INVALID'),
    ('timer_word',lambda h:h.is_enabled.update({'c3po-reader.timer':'Enabled'}),'timer','TIMER_ENABLED_INVALID'),
    ('listing',lambda h:setattr(h.docker,'ps_returncode',1),'containers','COMMAND_FAILED'),
    ('mounts_shape',lambda h:reader(h)['Mounts'][0].update(RW='false'),'mounts','MOUNTS_INVALID'),
    ('mounts_not_a_list',lambda h:reader(h).update(Mounts={'a':1}),'mounts','MOUNTS_INVALID'),
    ('mounts_too_many',lambda h:reader(h).update(Mounts=[k13r.mount('/a','/b')]*17),'mounts','MOUNTS_INVALID'),
    ('mounts_source_type',lambda h:reader(h)['Mounts'][0].update(Source=None),'mounts','MOUNTS_INVALID'),
    ('command_args',lambda h:reader(h).update(Args='-I'),'command','CONTAINER_COMMAND_INVALID'),
    ('command_long',lambda h:reader(h).update(Args=['x']*257),'command','CONTAINER_COMMAND_INVALID'),
    ('command_path_type',lambda h:reader(h).update(Path=None),'command','CONTAINER_COMMAND_INVALID'),
    ('scan_args',lambda h:h.docker.container('c3po-api-1').update(Args=[1]),'other_readers','CONTAINER_COMMAND_INVALID'),
]
@pytest.mark.parametrize('label,setup,item,code',UNAVAILABLE,ids=[row[0] for row in UNAVAILABLE])
def test_unavailable_items_leave_the_others_in_the_receipt(label,setup,item,code):
    receipt,_=run('LIVE',setup=setup)
    assert (receipt['status'],receipt['outcome'])==('PARTIAL_METADATA_REQUIRES_REVIEW','READER_OBSERVATION_INCOMPLETE')
    assert receipt['items'][item]['status']=='UNAVAILABLE' and receipt['items'][item]['code']==code and item in receipt['items_not_complete']
    assert receipt['items']['boot']['status']=='COMPLETE' and receipt['expectations_met'] is False

def test_a_reader_absent_in_live_is_a_finding_and_its_inspects_unavailable():
    receipt,_=run('LIVE',setup=lambda h:h.docker.containers.remove(reader(h)))
    assert receipt['outcome']=='READER_OBSERVATION_INCOMPLETE' and receipt['code']=='READER_CONTAINER_NOT_RUNNING'
    assert [receipt['items'][name]['code'] for name in ('container','mounts','command')]==['READER_CONTAINER_ABSENT']*3

def test_a_listing_that_fails_never_reads_as_no_reader():
    receipt,_=run('STOPPED',setup=lambda h:setattr(h.docker,'ps_returncode',1))
    assert receipt['outcome']=='READER_OBSERVATION_INCOMPLETE' and receipt['items']['other_readers']['code']=='CONTAINER_LIST_UNAVAILABLE'
    assert receipt['items']['containers']['status']=='UNAVAILABLE'

def test_a_reader_replaced_between_two_reads_is_unavailable():
    def setup(host):
        done=[]
        def hook(host,name,detail,calls):
            if name=='run' and detail[0][1:3]==['container','inspect'] and detail[0][-1]=='c3po-reader' and not done:
                done.append(1);host.docker.containers.remove(reader(host));host.docker.containers.append(k13r.reader_container())
        host.hook=hook
    docs,host=k13r.case(setup=setup);receipt=docs.run(host)
    assert f.sealed(receipt) and host.mutating()==[] and receipt['items']['container']['code']=='READER_CONTAINER_CHANGED' and receipt['outcome']=='READER_OBSERVATION_INCOMPLETE'

def test_an_expiry_stops_the_run_and_keeps_what_was_observed():
    docs,host=k13r.case();ticks=[0]
    def clock():
        ticks[0]+=1;return docs.now if ticks[0]<12 else docs.now+timedelta(minutes=6)
    receipt=docs.run(host,clock=clock)
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','GO_EXPIRED') and receipt['items']

def test_executor_not_root_reads_nothing():
    docs,host=k13r.case();host.actor=(1000,1000);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','EXECUTOR_IDENTITY','BEFORE_ANY_OBSERVATION') and host.log==[]


# ---------------------------------------------------------------- failure and death at every host call
@pytest.mark.parametrize('mode',['LIVE','STOPPED'])
@pytest.mark.parametrize('kind',['death','oserror','runtime'])
def test_failure_or_death_at_every_host_call_changes_nothing_and_is_never_complete(mode,kind):
    docs,host=k13r.case(mode=mode);docs.run(host);total=host.calls
    for index in range(1,total+1):
        docs,host=k13r.case(mode=mode)
        def hook(host,name,detail,calls,index=index):
            if calls==index:
                if kind=='death':raise hostemu.Death()
                raise OSError(5,'injected') if kind=='oserror' else RuntimeError('injected')
        host.hook=hook;before=k13r.state_of(host);receipt=docs.run(host)
        assert f.sealed(receipt) and 'injected' not in json.dumps(receipt) and k13r.state_of(host)==before
        assert receipt['status']!='METADATA_ONLY_REQUIRES_REVIEW',(index,receipt['items'])


# ---------------------------------------------------------------- receipts
def test_receipt_reduction_keeps_status_findings_and_codes():
    m=k13r.K().m;receipt,_=run('LIVE');body=dict(receipt);body.pop('metadata_sha256')
    m._reduce_items(body);assert body['items']['mounts']=={'status':'COMPLETE','findings':[],'code':None}
    big=dict(receipt);big.pop('metadata_sha256');big['items']=dict(big['items'],**{'pad%d'%i:{'status':'COMPLETE','x':'y'*1000} for i in range(70)})
    sealed=m.seal(big);assert sealed['size_reductions'][0]=='ITEMS_REDUCED_TO_STATUS' and sealed['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
