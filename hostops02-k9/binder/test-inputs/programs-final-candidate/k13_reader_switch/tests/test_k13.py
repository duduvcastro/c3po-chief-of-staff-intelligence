"""K13's own tests on the emulated host (tests/k13.py): every refusal of the plan and of the precheck, the three modes,
the reconcile cases, every way a switch can end, the readback, the budget edges, a failure and a death at every host
call, and what never leaves a run. The systemctl switches are emulated (ReaderHost); nothing here ran on a host."""
from datetime import datetime,timedelta
import json
import os

import pytest

import family as f
import hostemu
import k13
from family import refusal

ACTIVATE,RESTART,DEACTIVATE='ACTIVATE','RESTART','DEACTIVATE'

def run(mode=ACTIVATE,now=None,setup=None,change=None,host_change=None,**options):
    """One run: the fixture of the mode, an optional change of the host before the plan is read (setup), of the plan
    (change, then the chain is kept) or of the host after the plan was read (host_change)."""
    docs,host=k13.case(now or k13.at(mode),mode=mode,setup=setup)
    if change is not None:
        change(docs.plan);docs.chain()
    if host_change is not None:host_change(host)
    before=k13.state_of(host);receipt=docs.run(host,**options)
    assert f.sealed(receipt) and hostemu.SECRET.encode() not in f.line(receipt) and b'never-emit' not in f.line(receipt)
    assert host.fds=={},'every descriptor of the run is closed'
    return receipt,host,before

def refused(receipt,host,before,code):
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CHANGED',code),(receipt['code'],receipt.get('precheck'))
    assert k13.state_of(host)==before and host.switches==[] and host.mutating()==[]
    assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False
    assert receipt['mutating_calls']['succeeded']==0 and receipt['mutating_calls']['uncertain']==0

def complete(receipt,mode=ACTIVATE):
    outcome={ACTIVATE:'RETURNED_REQUIRES_LIVENESS_READBACK',RESTART:'RESTART_RETURNED_REQUIRES_LIVENESS_READBACK',
             DEACTIVATE:'DEACTIVATED_REQUIRES_STOP_READBACK'}[mode]
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW',outcome,None),(receipt['code'],receipt.get('switches'))

def node(host,path):return host.tree.get(path)
def content(host,path,raw):node(host,path).content=bytearray(raw)


# ---------------------------------------------------------------- static facts of the source
def test_activation_bytes_are_the_readme_constant_and_hash():
    m=k13.K().m
    assert m.ACTIVATION_BYTES==k13.ACTIVATION and f.sha(m.ACTIVATION_BYTES)==m.ACTIVATION_SHA256=='2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b'

def test_command_table_two_tools_fixed_words_and_classes():
    m=k13.K().m;rows=m.COMMANDS
    assert set(m.BINARIES)=={'docker','systemctl'}
    effects={name:(row['argv'],row['class']) for name,row in rows.items() if row['kind']=='EFFECT'}
    assert effects=={'enable_now_timer':(['enable','--now','c3po-reader.timer'],'SWITCH'),'start_service':(['start','--no-block','c3po-reader.service'],'QUICK'),
                     'reset_failed_service':(['reset-failed','c3po-reader.service'],'QUICK'),'disable_now_timer':(['disable','--now','c3po-reader.timer'],'SWITCH'),
                     'stop_service':(['stop','--no-block','c3po-reader.service'],'QUICK')}
    assert all(row['tool']=='systemctl' for name,row in rows.items() if row['kind']=='EFFECT')
    assert not [row for row in rows.values() if row['kind']=='CONTAINER'] and all(row['middle'] is None for row in rows.values() if row['kind']=='EFFECT')
    docker=[row['argv'][:2] for row in rows.values() if row['tool']=='docker']
    assert all(words[0] in ('image','container','ps','info') for words in docker) and not [w for w in docker if w[0] in ('run','exec','stop','rm','logs','top')]
    assert 'Env' not in m.CONTAINER_COMMAND_FORMAT and 'Env' not in m.SECURITY_OPTIONS_FORMAT
    assert m.MODE_EFFECTS=={'ACTIVATE':('enable_now_timer','start_service'),'RESTART':('reset_failed_service','start_service'),
                            'DEACTIVATE':('disable_now_timer','stop_service')}

def test_budget_figures_of_each_mode():
    m=k13.K().m
    assert [m.effects_budget(*m.MODE_EFFECTS[mode]) for mode in (ACTIVATE,RESTART,DEACTIVATE)]==[42,20,42] and m.SWITCH_FILE_ALLOWANCE_SECONDS==3

def test_success_criterion_follows_the_mode_and_effects_say_what_is_switched():
    m=k13.K().m
    for mode in (ACTIVATE,RESTART,DEACTIVATE):
        docs,host=k13.case(k13.at(mode),mode=mode);effects=m.effects_of(docs.plan)
        assert m.success_of(docs.plan)==effects['success_outcome']==m.MODE_OUTCOMES[mode] and docs.go['success_criterion']==m.MODE_OUTCOMES[mode]
        assert effects['switches']==[m.COMMANDS[name]['argv'] for name in m.MODE_EFFECTS[mode]] and effects['files_deleted'] is False
    assert json.loads((k13.DIRECTORY/'build'/'GO.UNBOUND.json').read_bytes())['success_criterion'] is None


def test_effects_of_each_mode_member_by_member():
    m=k13.K().m;chain=m.chain_effects
    docs,host=k13.case(k13.at(ACTIVATE));plan=docs.plan;files=plan['files']
    common={'operation':'GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01','epoch':'R2D2-V2-SHADOW-2026-10-05','files_deleted':False,'daemon_reload':'BY_ENABLE_OR_DISABLE_ONLY',
            'unit_names':['c3po-reader.service','c3po-reader.timer'],
            'unit_directory':chain(plan['unit_rows']),'evidence_boot_id_sha256':f.BOOT_SHA,
            'unit_files':{'c3po-reader.service':files['reader_service'],'c3po-reader.timer':files['reader_timer'],'c3po-reader-alert.service':files['reader_alert'],
                          'c3po-massive.service':files['producer_service']}}
    expected=dict(common,mode=ACTIVATE,success_outcome='RETURNED_REQUIRES_LIVENESS_READBACK',
                  switches=[['enable','--now','c3po-reader.timer'],['start','--no-block','c3po-reader.service']],
                  activation_env={'path':'/etc/c3po-reader/activation.env','sha256':'2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b',
                                  'action':'CREATE_IF_ABSENT_ACCEPT_IF_CONSTANT'},
                  launch_window={'days':['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09'],'utc':['07:30:00','20:00:00'],'late_from_utc':'13:28:30'},
                  launcher={'directory':chain(plan['launcher_rows']),'sha256':files['launcher']},pins_sha256=files['pins'],
                  journal={'root':chain(plan['journal_rows']),'container_root':'/c3po-bar-journal','free_floor_bytes':56706990080,'data_volume_device':hostemu.DATA_DEVICE},
                  release={'path':k13.RELEASE_DIRECTORY+'/'+k13.RELEASE_NAME,'sha256':f.sha(k13.RELEASE),'directory':chain(plan['release_rows'])},
                  image_id=hostemu.BACKEND,
                  bind_sources={'source_root':chain(plan['source_rows']),'capacity_root':chain(plan['capacity_rows']),'not_root_controlled':['/mnt/day-d-data']})
    assert m.effects_of(plan)==expected and docs.go['effects']==json.loads(f.canonical(expected))
    docs,host=k13.case(k13.at(RESTART),mode=RESTART);effects=m.effects_of(docs.plan)
    assert effects['switches']==[['reset-failed','c3po-reader.service'],['start','--no-block','c3po-reader.service']]
    assert effects['activation_env']['action']=='REQUIRED_CONSTANT' and effects['success_outcome']=='RESTART_RETURNED_REQUIRES_LIVENESS_READBACK'
    docs,host=k13.case(k13.at(DEACTIVATE),mode=DEACTIVATE);plan=docs.plan
    common.update(unit_files=None,unit_directory=None,bind_sources=None)
    assert m.effects_of(plan)==dict(common,mode=DEACTIVATE,success_outcome='DEACTIVATED_REQUIRES_STOP_READBACK',
        switches=[['disable','--now','c3po-reader.timer'],['stop','--no-block','c3po-reader.service']],
        activation_env={'path':'/etc/c3po-reader/activation.env','sha256':'2053f3f6f528ad7dc56d500666ac2cf48f79c3aadd3c98eb35b53ee92eff611b','action':'NOT_LOOKED_AT'},
        launch_window=None,launcher=None,pins_sha256=None,journal=None,release=None,image_id=None)


# ---------------------------------------------------------------- the plan, refused from its bytes (before any claim)
def plan_refusal(mode,change):
    docs,host=k13.case(k13.at(mode),mode=mode);change(docs.plan);docs.chain()
    code=refusal(docs.authenticate)
    receipt=docs.run(f.Untouchable());assert (receipt['status'],receipt['code'])==('REFUSED',code)
    return code

def setrow(key,index,**values):
    def change(plan):plan[key][index].update(values)
    return change
PLAN_CASES=[
    ('mode',ACTIVATE,lambda p:p.update(mode='REACTIVATE'),'MODE_INVALID'),
    ('mode_null',ACTIVATE,lambda p:p.update(mode=None),'MODE_INVALID'),
    ('boot',ACTIVATE,lambda p:p.update(evidence_boot_id_sha256='0'*64),'EVIDENCE_BOOT_UNBOUND'),
    ('unit_rows_short',ACTIVATE,lambda p:p.update(unit_rows=p['unit_rows'][:-1]),'CHAIN_ROW_INVALID'),
    ('unit_rows_writable',ACTIVATE,setrow('unit_rows',-1,mode=0o775),'CHAIN_ROW_UNSAFE'),
    ('unit_rows_group',ACTIVATE,setrow('unit_rows',-1,gid=4),'UNIT_CHAIN_NOT_ROOT_CONTROLLED'),
    ('unit_rows_setgid',ACTIVATE,setrow('unit_rows',1,mode=0o2755),'UNIT_CHAIN_NOT_ROOT_CONTROLLED'),
    ('files_keys',ACTIVATE,lambda p:p['files'].pop('pins'),'FILE_PINS_INVALID'),
    ('files_hex',ACTIVATE,lambda p:p['files'].update(launcher='A'*64),'FILE_PINS_INVALID'),
    ('files_null_activate',ACTIVATE,lambda p:p['files'].update(producer_service=None),'FILE_PINS_INVALID'),
    ('config_mode',ACTIVATE,setrow('config_rows',-1,mode=0o750),'CONFIG_DIRECTORY_NOT_PRIVATE'),
    ('config_group',ACTIVATE,setrow('config_rows',-1,gid=7),'CONFIG_DIRECTORY_NOT_PRIVATE'),
    ('config_parent_group',ACTIVATE,setrow('config_rows',1,gid=7),'CONFIG_DIRECTORY_NOT_PRIVATE'),
    ('config_setgid',ACTIVATE,setrow('config_rows',-1,mode=0o2700),'PARENT_SETGID'),
    ('config_unsafe',ACTIVATE,setrow('config_rows',1,uid=1000),'CHAIN_ROW_UNSAFE'),
    ('launcher_mode',ACTIVATE,setrow('launcher_rows',-1,mode=0o755),'LAUNCHER_DIRECTORY_NOT_PRIVATE'),
    ('launcher_elsewhere',ACTIVATE,lambda p:p['launcher_rows'][-2].update(inode=p['launcher_rows'][-2]['inode']+1),'LAUNCHER_DIRECTORY_NOT_PRIVATE'),
    ('launcher_path',ACTIVATE,lambda p:p.update(launcher_rows=p['config_rows']),'CHAIN_ROW_INVALID'),
    ('journal_mode',ACTIVATE,setrow('journal_rows',-1,mode=0o750),'JOURNAL_ROOT_NOT_PRIVATE'),
    ('journal_parent_group',ACTIVATE,setrow('journal_rows',-2,gid=3),'JOURNAL_ROOT_NOT_PRIVATE'),
    ('journal_owner',ACTIVATE,setrow('journal_rows',-1,uid=1000),'CHAIN_ROW_UNSAFE'),
    ('journal_on_data',ACTIVATE,lambda p:[row.update(device=hostemu.DATA_DEVICE) for row in p['journal_rows'][-1:]],'JOURNAL_ON_THE_DATA_VOLUME'),
    ('release_outside',ACTIVATE,lambda p:p.update(release_rows=p['journal_rows']),'RELEASE_NOT_IN_THE_DATA_VOLUME'),
    ('release_is_data',ACTIVATE,lambda p:p.update(release_rows=p['release_rows'][:-1]),'RELEASE_NOT_IN_THE_DATA_VOLUME'),
    ('release_empty',ACTIVATE,lambda p:p.update(release_rows=[]),'RELEASE_NOT_IN_THE_DATA_VOLUME'),
    ('release_unclean',ACTIVATE,lambda p:p['release_rows'][-1].update(path=hostemu.DATA+'/../x'),'RELEASE_NOT_IN_THE_DATA_VOLUME'),
    ('data_not_a_mount',ACTIVATE,lambda p:[row.update(device=p['release_rows'][1]['device']) for row in p['release_rows'][2:]],'DATA_VOLUME_NOT_A_MOUNT_POINT'),
    ('data_world_writable',ACTIVATE,setrow('release_rows',2,mode=0o777),'CHAIN_ROW_WORLD_WRITABLE'),
    ('release_keys',ACTIVATE,lambda p:p['release'].update(bytes=1),'RELEASE_PLAN_INVALID'),
    ('release_name',ACTIVATE,lambda p:p['release'].update(name='../release.json'),'RELEASE_PLAN_INVALID'),
    ('release_hash',ACTIVATE,lambda p:p['release'].update(sha256='0'*64),'RELEASE_PLAN_INVALID'),
    ('image',ACTIVATE,lambda p:p.update(image_id='c3po/backend:production'),'IMAGE_ID_INVALID'),
    ('floor_low',ACTIVATE,lambda p:p.update(journal_free_floor_bytes=53687091199),'FREE_FLOOR_BELOW_PRODUCER_FLOOR'),
    ('floor_bool',ACTIVATE,lambda p:p.update(journal_free_floor_bytes=True),'FREE_FLOOR_BELOW_PRODUCER_FLOOR'),
    ('restart_config',RESTART,setrow('config_rows',-1,mode=0o755),'CONFIG_DIRECTORY_NOT_PRIVATE'),
]+[('deactivate_'+key,DEACTIVATE,(lambda key:lambda p:p.update({key:[] if key.endswith('rows') else 'x'}))(key),'PLAN_MEMBER_NOT_USED_BY_MODE')
   for key in ('unit_rows','config_rows','launcher_rows','journal_rows','release_rows','release','files','image_id','journal_free_floor_bytes','source_rows','capacity_rows')]+[
   ('source_mode',ACTIVATE,setrow('source_rows',-1,mode=0o755),'SOURCE_ROOT_NOT_PRIVATE'),
   ('source_parent_group',ACTIVATE,setrow('source_rows',-2,gid=1000),'SOURCE_ROOT_NOT_PRIVATE'),
   ('source_parent_uid_1000',ACTIVATE,setrow('source_rows',-2,uid=1000),'CHAIN_ROW_UNSAFE'),
   ('source_path',ACTIVATE,lambda p:p.update(source_rows=p['journal_rows']),'CHAIN_ROW_INVALID'),
   ('capacity_mode',ACTIVATE,setrow('capacity_rows',-1,mode=0o750),'CAPACITY_ROOT_NOT_PRIVATE'),
   ('capacity_setgid',ACTIVATE,setrow('capacity_rows',-2,mode=0o2755),'CAPACITY_ROOT_NOT_PRIVATE'),
   ('capacity_owner',ACTIVATE,setrow('capacity_rows',-1,uid=1000),'CHAIN_ROW_UNSAFE'),
   ('capacity_path',ACTIVATE,lambda p:p.update(capacity_rows=p['config_rows']),'CHAIN_ROW_INVALID'),
   ('restart_source_mode',RESTART,setrow('source_rows',-1,mode=0o755),'SOURCE_ROOT_NOT_PRIVATE'),
   ('floor_below_five_sessions',ACTIVATE,lambda p:p.update(journal_free_floor_bytes=56706990079),'FREE_FLOOR_BELOW_PRODUCER_FLOOR'),
   ('floor_of_the_producer_alone',ACTIVATE,lambda p:p.update(journal_free_floor_bytes=53687091200),'FREE_FLOOR_BELOW_PRODUCER_FLOOR'),
   ('restart_floor_below_four_sessions',RESTART,lambda p:p.update(journal_free_floor_bytes=53687091200+4*603979776-1),'FREE_FLOOR_BELOW_PRODUCER_FLOOR')]
@pytest.mark.parametrize('label,mode,change,code',PLAN_CASES,ids=[case[0] for case in PLAN_CASES])
def test_plan_refusals_before_anything_is_touched(label,mode,change,code):
    assert plan_refusal(mode,change)==code

def test_evidence_must_cite_a_precheck_receipt():
    docs,host=k13.case(k13.at(ACTIVATE));docs.request['evidence']=[{'role':'PRIOR','operation':'GO_READONLY_SYNTHETIC_PRIOR_01','receipt_sha256':'a'*64}]
    docs.chain();assert refusal(docs.authenticate)=='EVIDENCE_OPERATION_MISSING'

def test_a_window_of_exactly_fifteen_minutes_is_accepted():
    docs,host=k13.case(k13.at(ACTIVATE));now=docs.now
    docs.shift(now,now+timedelta(seconds=900));docs.authenticate()
    docs.shift(now,now+timedelta(seconds=901));assert refusal(docs.authenticate)=='WINDOW_SPAN'

def test_the_launch_window_is_judged_in_utc_whatever_the_offset_of_the_clock():
    from datetime import timezone
    brt=timezone(timedelta(hours=-3))
    for instant,code in (('2026-10-07T07:35:00+00:00',None),('2026-10-07T07:25:00+00:00','READER_OUTSIDE_LAUNCH_WINDOW'),('2026-10-07T19:55:00+00:00',None)):
        now=datetime.fromisoformat(instant);docs,host=k13.case(now);receipt=docs.run(host,clock=lambda now=now:now.astimezone(brt))
        assert receipt['code']==code,(instant,receipt['code'])

def test_floor_is_the_producer_floor_plus_the_retention_of_the_sessions_left():
    for moment,sessions in (('2026-10-05T10:40:00+00:00',5),('2026-10-07T10:40:00+00:00',3),('2026-10-09T10:40:00+00:00',1)):
        floor=53687091200+603979776*sessions
        docs,host=k13.case(datetime.fromisoformat(moment));docs.plan['journal_free_floor_bytes']=floor;docs.chain();docs.authenticate()
        docs.plan['journal_free_floor_bytes']=floor-1;docs.chain();assert refusal(docs.authenticate)=='FREE_FLOOR_BELOW_PRODUCER_FLOOR'
    assert 53687091200+5*603979776==56706990080


# ---------------------------------------------------------------- the three modes, complete
def test_activate_creates_the_constant_file_then_enables_and_starts_with_exactly_these_commands():
    receipt,host,before=run(ACTIVATE);complete(receipt)
    item=node(host,k13.CONFIG+'/activation.env')
    assert bytes(item.content)==k13.ACTIVATION and (item.kind,item.uid,item.gid,item.mode,item.nlink)==('file',0,0,0o600,1)
    assert sorted(node(host,k13.CONFIG).children)==['activation.env','docker-cli','launcher','pins.env','secret.env']
    switches=[entry for entry in host.commands if entry['argv'][0]=='/usr/bin/systemctl' and entry['argv'][1] in ('enable','start','reset-failed','disable','stop')]
    assert [entry['argv'] for entry in switches]==[['/usr/bin/systemctl','enable','--now','c3po-reader.timer'],['/usr/bin/systemctl','start','--no-block','c3po-reader.service']]
    assert [entry['seconds'] for entry in switches]==[30,8] and all(entry['capture'] is False for entry in switches)
    assert host.effect_commands()==[] and not [entry for entry in host.commands if entry['argv'][1] in ('run','exec','stop','rm','logs')]
    assert receipt['activation_performed'] is True and receipt['daemon_reload_performed'] is True and receipt['reconcile'] is False
    assert receipt['activation_env']=='ABSENT' and receipt['ledger'][0]['state']=='INSTALLED_DURABLE' and receipt['objects_left_by_this_run']==1
    assert receipt['launch']=={'session':'2026-10-05','late':False} and receipt['commands_started']['EFFECT']==2
    assert receipt['after']['timer_enabled']=='enabled' and receipt['after']['service']['ActiveState']=='activating'
    assert receipt['after']['container']=={'status':'COMPLETE','exists':False}
    assert receipt['mutating_calls']=={'issued':6,'succeeded':6,'failed_nothing_changed':0,'uncertain':0}
    assert receipt['precheck']['engine']=={'options':3,'userns_or_rootless':False} and receipt['precheck']['image']['id']==hostemu.BACKEND
    assert receipt['files_deleted'] is False and receipt['phase_reached']=='EFFECTS'

def test_activate_reports_the_container_when_the_start_created_it():
    receipt,host,_=run(ACTIVATE,setup=lambda host:setattr(host,'start_creates_container',True));complete(receipt)
    item=receipt['after']['container'];reader=host.docker.container('c3po-reader')
    assert item['exists'] is True and item['id']==reader['Id'] and item['image_equal_the_pin'] is True and item['state']=='running'
    receipt,host,_=run(ACTIVATE,setup=lambda host:(setattr(host,'start_creates_container',True),setattr(host,'reader_image',hostemu.OTHER)));complete(receipt)
    assert receipt['after']['container']['image_equal_the_pin'] is False,'a fact, reported as read; the liveness read (K13r) judges it'

def test_activate_late_flag_and_window_edges():
    for instant,late in (('07:30:00',False),('13:28:29',False),('13:28:30',True),('19:59:59',True)):
        receipt,_,_=run(ACTIVATE,now=datetime.fromisoformat('2026-10-07T%s+00:00'%instant));complete(receipt)
        assert receipt['launch']=={'session':'2026-10-07','late':late},instant
    for instant in ('07:29:59','20:00:00','23:50:00','00:00:00'):
        receipt,host,before=run(ACTIVATE,now=datetime.fromisoformat('2026-10-07T%s+00:00'%instant));refused(receipt,host,before,'READER_OUTSIDE_LAUNCH_WINDOW')

def test_activate_and_restart_refuse_on_the_saturday_of_the_date_set_and_deactivate_does_not():
    now=datetime.fromisoformat('2026-10-10T12:00:00+00:00')
    for mode in (ACTIVATE,RESTART):
        receipt,host,before=run(mode,now=now);refused(receipt,host,before,'READER_NOT_A_SESSION_DAY')
    receipt,_,_=run(DEACTIVATE,now=now);complete(receipt,DEACTIVATE)
    receipt,_,_=run(DEACTIVATE,now=datetime.fromisoformat('2026-10-09T23:30:00+00:00'));complete(receipt,DEACTIVATE)

def test_restart_resets_and_starts_and_reloads_nothing():
    receipt,host,before=run(RESTART);complete(receipt,RESTART)
    assert host.switches==[['reset-failed','c3po-reader.service'],['start','--no-block','c3po-reader.service']]
    assert receipt['activation_performed'] is True and receipt['daemon_reload_performed'] is False and receipt['ledger']==[]
    assert k13.state_of(host)[0]==before[0],'RESTART creates nothing'

def test_restart_of_a_unit_that_is_inactive_not_failed():
    receipt,_,_=run(RESTART,setup=lambda host:host.units['c3po-reader.service'].update(ActiveState='inactive',SubState='dead'));complete(receipt,RESTART)

def test_deactivate_disables_and_stops_and_deletes_nothing():
    receipt,host,before=run(DEACTIVATE);complete(receipt,DEACTIVATE)
    assert host.switches==[['disable','--now','c3po-reader.timer'],['stop','--no-block','c3po-reader.service']]
    assert k13.state_of(host)[0]==before[0] and node(host,k13.CONFIG+'/activation.env') is not None
    assert receipt['activation_performed'] is True and receipt['daemon_reload_performed'] is True and receipt['after']['service']['ActiveState']=='deactivating'
    assert receipt['launch'] is None and not [entry for entry in host.log if entry[0]=='open' and '/etc/c3po-reader' in entry[1]]

def test_deactivate_of_a_reader_already_stopped_completes_without_change():
    def stopped(host):
        host.is_enabled[k13.TIMER]='disabled';host.units[k13.TIMER].update(ActiveState='inactive',SubState='dead',UnitFileState='disabled')
        host.units[k13.SERVICE].update(ActiveState='inactive',SubState='dead');host.docker.containers=[c for c in host.docker.containers if c['Name']!='/c3po-reader']
    receipt,_,_=run(DEACTIVATE,setup=stopped);complete(receipt,DEACTIVATE)
    receipt,_,_=run(DEACTIVATE,setup=lambda host:(stopped(host),setattr(host,'stop_settles',True)));complete(receipt,DEACTIVATE)

def test_deactivate_settled_stop_reads_inactive():
    receipt,host,_=run(DEACTIVATE,setup=lambda host:setattr(host,'stop_settles',True));complete(receipt,DEACTIVATE)
    assert receipt['after']['service']['ActiveState']=='inactive' and host.docker.container('c3po-reader') is None


# ---------------------------------------------------------------- reconcile (README operation 4)
def with_activation(raw=k13.ACTIVATION,mode=0o600,uid=0,links=1):
    def setup(host):
        item=host.tree.add(k13.CONFIG+'/activation.env',kind='file',mode=mode,uid=uid,content=raw);item.nlink=links
    return setup

def test_reconcile_after_a_crash_after_the_file_completes_the_switches_without_creating():
    receipt,host,before=run(ACTIVATE,setup=with_activation());complete(receipt)
    assert receipt['reconcile'] is True and receipt['activation_env']=='CONSTANT' and receipt['ledger']==[] and receipt['after']['activation_env']=='CONSTANT'
    assert host.switches==[['enable','--now','c3po-reader.timer'],['start','--no-block','c3po-reader.service']]
    assert k13.state_of(host)[0]==before[0] and receipt['objects_left_by_this_run']==0

def test_reconcile_of_an_active_reader_with_its_own_container():
    def setup(host):k13.activated(host)
    receipt,host,before=run(ACTIVATE,setup=setup);complete(receipt)
    reader=host.docker.container('c3po-reader')
    assert receipt['reconcile'] is True and receipt['precheck']['reconciled_container']['id']==reader['Id']
    assert [row['reader_like'] for row in receipt['precheck']['process_scan'] if row['name']=='c3po-reader']==[True]
    assert receipt['after']['container']['exists'] is True and receipt['after']['service']['ActiveState']=='active'

def test_reconcile_of_an_active_reader_changes_nothing_and_says_so():
    receipt,_,_=run(ACTIVATE,setup=k13.activated);complete(receipt)
    assert receipt['switches_changed_state'] is False and {item['changed'] for item in receipt['switches'].values()}=={False}
    receipt,_,_=run(ACTIVATE);complete(receipt);assert receipt['switches_changed_state'] is True
    assert receipt['switches']['enable_now_timer']['changed'] is True and receipt['switches']['start_service']['changed'] is True

def test_reconcile_refuses_an_active_reader_that_is_not_the_launcher_or_whose_unit_is_stale():
    for change,code in ((lambda h:h.docker.container('c3po-reader').update(Args=['-m','app.r2d2_v2_shadow_worker']),'READER_CONTAINER_NOT_THE_PINNED_READER'),
                        (lambda h:h.docker.container('c3po-reader').update(Path='/bin/sh'),'READER_CONTAINER_NOT_THE_PINNED_READER'),
                        (lambda h:h.units[k13.SERVICE].update(NeedDaemonReload='yes'),'READER_UNIT_NEEDS_DAEMON_RELOAD')):
        receipt,host,before=run(ACTIVATE,setup=lambda h,change=change:(k13.activated(h),change(h)));refused(receipt,host,before,code)

def test_reconcile_refuses_a_reader_replaced_between_the_listing_and_its_inspect():
    def setup(host):
        k13.activated(host);done=[]
        def hook(host,name,detail,calls):
            if name=='run' and detail[0][-1]=='c3po-reader' and detail[0][1:3]==['container','inspect'] and not done:
                done.append(1);old=host.docker.container('c3po-reader');host.docker.containers.remove(old);host.docker.containers.append(k13.reader_container())
        host.hook=hook
    docs,host=k13.case(k13.at(ACTIVATE),setup=setup);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','READER_CONTAINER_CHANGED') and host.switches==[]

def test_enable_that_fails_on_a_timer_already_enabled_may_have_reloaded_and_is_uncertain():
    def setup(host):
        with_activation()(host);host.is_enabled[k13.TIMER]='enabled';host.units[k13.TIMER].update(UnitFileState='enabled')
        host.switch_returncode['enable --now']=1;host.switch_no_effect.add('enable --now')
    receipt,host,_=run(ACTIVATE,setup=setup)
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','SWITCH_COMMAND_FAILED')
    assert receipt['switches']['enable_now_timer']['settled']=='UNKNOWN' and receipt['daemon_reload_performed'] is None

def test_reconcile_of_a_reader_still_starting_without_container():
    def setup(host):
        with_activation()(host);host.is_enabled[k13.TIMER]='enabled';host.units[k13.TIMER].update(ActiveState='active',SubState='waiting')
        host.units[k13.SERVICE].update(ActiveState='activating',SubState='start-pre')
    receipt,_,_=run(ACTIVATE,setup=setup);complete(receipt)

@pytest.mark.parametrize('setup',[with_activation(b'C3PO_R2D2_V2_SHADOW_ENABLED=false\nC3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true\n'),
                                  with_activation(k13.ACTIVATION+b'\n'),with_activation(k13.ACTIVATION[:-1]),with_activation(mode=0o644),
                                  with_activation(uid=1000),with_activation(links=2),with_activation(b'')],
                         ids=['other_bytes','one_more_byte','one_byte_less','mode_0644','owner','two_links','empty'])
def test_any_other_activation_file_is_a_refusal(setup):
    receipt,host,before=run(ACTIVATE,setup=setup);refused(receipt,host,before,'ACTIVATION_ENV_NOT_THE_CONSTANT')

def test_activation_file_that_is_a_directory_or_a_link_is_a_refusal():
    for kind in ('dir','symlink'):
        receipt,host,before=run(ACTIVATE,setup=lambda host,kind=kind:host.tree.add(k13.CONFIG+'/activation.env',kind=kind,mode=0o700));refused(receipt,host,before,'ACTIVATION_ENV_NOT_THE_CONSTANT')

def test_reconcile_refuses_a_reader_container_of_another_image_or_not_running():
    other=hostemu.OTHER
    for change in (lambda c:c.update(Image=other),lambda c:c['State'].update(Running=False,Status='exited')):
        def setup(host,change=change):
            k13.activated(host);change(host.docker.container('c3po-reader'))
        receipt,host,before=run(ACTIVATE,setup=setup)
        assert receipt['code'] in ('READER_CONTAINER_NOT_THE_PINNED_READER',);refused(receipt,host,before,receipt['code'])

def test_reconcile_refuses_its_own_container_restarting():
    def setup(host):
        k13.activated(host);host.docker.container('c3po-reader')['State'].update(Status='restarting',Running=False)
    receipt,host,before=run(ACTIVATE,setup=setup);refused(receipt,host,before,'READER_CONTAINER_NOT_THE_PINNED_READER')

def test_reconcile_refuses_a_second_reader_beside_its_own():
    def setup(host):
        k13.activated(host);item=k13.reader_container(name='c3po-reader-two');host.docker.containers.append(item)
    receipt,host,before=run(ACTIVATE,setup=setup);refused(receipt,host,before,'READER_PROCESS_FOUND')

def test_reconcile_with_the_service_stopped_refuses_a_leftover_reader_container():
    def setup(host):
        with_activation()(host);host.docker.containers.append(k13.reader_container(running=False))
    receipt,host,before=run(ACTIVATE,setup=setup);refused(receipt,host,before,'READER_CONTAINER_PRESENT')

def test_reconcile_refuses_a_service_in_a_transition_it_cannot_judge():
    def setup(host):
        with_activation()(host);host.units[k13.SERVICE].update(ActiveState='deactivating',SubState='stop')
    receipt,host,before=run(ACTIVATE,setup=setup);refused(receipt,host,before,'SERVICE_STATE_UNEXPECTED')


# ---------------------------------------------------------------- the precheck, one refusal at a time
def unit_path(name):return k13.UNITS+'/'+name
def bump(path,**values):
    def setup(host):
        item=host.tree.get(path)
        for key,value in values.items():setattr(item,key,value)
    return setup
def replace_signed(path,raw):
    """A file whose bytes differ from the fixture's and whose hash the plan signs: the hash guard passes, the content guard decides."""
    return lambda host:content(host,path,raw)
def unit_values(unit,**values):return lambda host:host.units[unit].update(values)
def after_plan(path,raw):return lambda host:content(host,path,raw)

PRECHECK=[
    ('boot',ACTIVATE,None,lambda h:content(h,'/proc/sys/kernel/random/boot_id',b'1f8fad5b-d9cb-469f-a165-70867728950e\n'),'EVIDENCE_FROM_EARLIER_BOOT'),
]
for unit in (k13.SERVICE,k13.TIMER,k13.ALERT,k13.PRODUCER):
    PRECHECK+=[('hash_'+unit,ACTIVATE,None,after_plan(unit_path(unit),b'[Unit]\n'),'UNIT_FILE_NOT_AS_SIGNED'),
               ('mode_'+unit,ACTIVATE,bump(unit_path(unit),mode=0o600),None,'UNIT_FILE_NOT_AS_SIGNED'),
               ('owner_'+unit,ACTIVATE,bump(unit_path(unit),uid=1000),None,'UNIT_FILE_NOT_AS_SIGNED'),
               ('group_'+unit,ACTIVATE,bump(unit_path(unit),gid=1000),None,'UNIT_FILE_NOT_AS_SIGNED'),
               ('links_'+unit,ACTIVATE,bump(unit_path(unit),nlink=2),None,'UNIT_FILE_NOT_AS_SIGNED'),
               ('absent_'+unit,ACTIVATE,None,lambda h,unit=unit:h.tree.remove(unit_path(unit)),'UNIT_FILE_NOT_AS_SIGNED'),
               ('large_'+unit,ACTIVATE,replace_signed(unit_path(unit),b'#'*65537),None,'UNIT_FILE_NOT_AS_SIGNED')]
PRECHECK+=[
    ('service_not_loaded',ACTIVATE,unit_values(k13.SERVICE,LoadState='not-found'),None,'READER_UNIT_NOT_LOADED'),
    ('timer_masked',ACTIVATE,unit_values(k13.TIMER,LoadState='masked'),None,'READER_UNIT_NOT_LOADED'),
    ('service_fragment',ACTIVATE,unit_values(k13.SERVICE,FragmentPath='/run/systemd/system/c3po-reader.service'),None,'READER_UNIT_NOT_THE_INSTALLED_FILE'),
    ('timer_drop_in',ACTIVATE,unit_values(k13.TIMER,DropInPaths='/etc/systemd/system/c3po-reader.timer.d/x.conf'),None,'READER_UNIT_NOT_THE_INSTALLED_FILE'),
    ('property_missing',ACTIVATE,None,lambda h:h.units[k13.SERVICE].pop('Result'),'UNIT_PROPERTIES_INVALID'),
    ('property_value',ACTIVATE,None,lambda h:h.units[k13.TIMER].update(SubState='dead;x'),'UNIT_PROPERTIES_INVALID'),
    ('property_id',ACTIVATE,None,lambda h:h.units[k13.SERVICE].update(Id='c3po-massive.service'),'UNIT_PROPERTIES_INVALID'),
    ('enabled_word',ACTIVATE,None,lambda h:h.is_enabled.update({k13.TIMER:'Enabled'}),'TIMER_ENABLED_INVALID'),
    ('reader_without_the_source_bind',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(source=None)),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_source_bind_elsewhere',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(source='/mnt/day-d-data/r2d2-v2-source-20261005')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_source_bind_other_target',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(source_target='/c3po-src')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_mount',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(container_journal='/c3po-journal')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_mount_source',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(journal='/var/lib/c3po-bar/journal2')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_data',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(data='/mnt/other')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_capacity',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(capacity='/var/lib/c3po-cap')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_config',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(config='/etc/c3po-reader2')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_writable_mount',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service().replace(b'target=/c3po-capacity,readonly',b'target=/c3po-capacity')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_fifth_mount',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service().replace(b'  @IMAGE',b'  --mount type=bind,source=/,target=/host,readonly \\\n  @IMAGE')
                                                  if False else k13.reader_service().replace(b'  --user 0:0',b'  --mount type=bind,source=/var,target=/v,readonly --user 0:0')),None,'READER_UNIT_MOUNTS_NOT_AS_SIGNED'),
    ('reader_image',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service(image=hostemu.OTHER)),None,'READER_UNIT_IMAGE_NOT_THE_PIN'),
    ('reader_image_once',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service().replace(b'--format {{.Id}} '+hostemu.BACKEND.encode(),b'--format {{.Id}} c3po')),None,'READER_UNIT_IMAGE_NOT_THE_PIN'),
    ('reader_placeholder',ACTIVATE,replace_signed(unit_path(k13.SERVICE),k13.reader_service().replace(b'--network c3po_internal',b'--network @NETWORK@')),None,'READER_UNIT_IMAGE_NOT_THE_PIN'),
    ('producer_journal',ACTIVATE,replace_signed(unit_path(k13.PRODUCER),k13.producer_service(container_journal='/c3po-journal')),None,'PRODUCER_UNIT_JOURNAL_NOT_AS_SIGNED'),
    ('producer_source',ACTIVATE,replace_signed(unit_path(k13.PRODUCER),k13.producer_service(journal='/var/lib/c3po-bar/journal2')),None,'PRODUCER_UNIT_JOURNAL_NOT_AS_SIGNED'),
    ('producer_argument',ACTIVATE,replace_signed(unit_path(k13.PRODUCER),k13.producer_service().replace(b'--journal-root /c3po-bar-journal ',b'--journal-root /c3po-other ')),None,'PRODUCER_UNIT_JOURNAL_NOT_AS_SIGNED'),
    ('launcher_hash',ACTIVATE,None,after_plan(k13.LAUNCHER_DIRECTORY+'/reader_launcher.py',b'# other\n'),'LAUNCHER_NOT_AS_SIGNED'),
    ('launcher_mode',ACTIVATE,bump(k13.LAUNCHER_DIRECTORY+'/reader_launcher.py',mode=0o644),None,'LAUNCHER_NOT_AS_SIGNED'),
    ('launcher_absent',ACTIVATE,None,lambda h:h.tree.remove(k13.LAUNCHER_DIRECTORY+'/reader_launcher.py'),'LAUNCHER_NOT_AS_SIGNED'),
    ('pins_hash',ACTIVATE,None,after_plan(k13.CONFIG+'/pins.env',k13.PINS+b'X=1\n'),'PINS_NOT_AS_SIGNED'),
    ('pins_mode',ACTIVATE,bump(k13.CONFIG+'/pins.env',mode=0o644),None,'PINS_NOT_AS_SIGNED'),
    ('pins_links',ACTIVATE,bump(k13.CONFIG+'/pins.env',nlink=2),None,'PINS_NOT_AS_SIGNED'),
    ('secret_absent',ACTIVATE,lambda h:h.tree.remove(k13.CONFIG+'/secret.env'),None,'SECRET_ENV_SHAPE'),
    ('secret_mode',ACTIVATE,bump(k13.CONFIG+'/secret.env',mode=0o640),None,'SECRET_ENV_SHAPE'),
    ('secret_owner',ACTIVATE,bump(k13.CONFIG+'/secret.env',uid=1000),None,'SECRET_ENV_SHAPE'),
    ('secret_group',ACTIVATE,bump(k13.CONFIG+'/secret.env',gid=1000),None,'SECRET_ENV_SHAPE'),
    ('secret_links',ACTIVATE,bump(k13.CONFIG+'/secret.env',nlink=2),None,'SECRET_ENV_SHAPE'),
    ('secret_link',ACTIVATE,lambda h:(h.tree.remove(k13.CONFIG+'/secret.env'),h.tree.add(k13.CONFIG+'/secret.env',kind='symlink',mode=0o600)),None,'SECRET_ENV_SHAPE'),
    ('docker_cli_absent',ACTIVATE,lambda h:h.tree.remove(k13.CONFIG+'/docker-cli'),None,'DOCKER_CLI_DIRECTORY_NOT_PRIVATE'),
    ('docker_cli_mode',ACTIVATE,bump(k13.CONFIG+'/docker-cli',mode=0o755),None,'DOCKER_CLI_DIRECTORY_NOT_PRIVATE'),
    ('docker_cli_owner',ACTIVATE,bump(k13.CONFIG+'/docker-cli',uid=1000),None,'DOCKER_CLI_DIRECTORY_NOT_PRIVATE'),
    ('docker_cli_file',ACTIVATE,lambda h:(h.tree.remove(k13.CONFIG+'/docker-cli'),h.tree.add(k13.CONFIG+'/docker-cli',kind='file',mode=0o700)),None,'DOCKER_CLI_DIRECTORY_NOT_PRIVATE'),
    ('epoch_other_epoch',ACTIVATE,lambda h:content(h,k13.JOURNAL+'/epoch.json',k13.epoch_bytes(h,'R2D2-V2-SHADOW-2026-09-28')),None,'CATALOG_NOT_THIS_EPOCH_AND_ROOT'),
    ('epoch_other_inode',ACTIVATE,lambda h:setattr(h.tree.get(k13.JOURNAL),'ino',h.tree.get(k13.JOURNAL).ino+0) or content(h,k13.JOURNAL+'/epoch.json',
        f.canonical({'schema':'MASSIVE_SESSION_ROOT_V1','epoch':k13.EPOCH,'device':h.tree.get(k13.JOURNAL).dev,'inode':h.tree.get(k13.JOURNAL).ino+1})),None,'CATALOG_NOT_THIS_EPOCH_AND_ROOT'),
    ('epoch_other_schema',ACTIVATE,lambda h:content(h,k13.JOURNAL+'/epoch.json',bytes(h.tree.get(k13.JOURNAL+'/epoch.json').content).replace(b'ROOT_V1',b'ROOT_V2')),None,'CATALOG_NOT_THIS_EPOCH_AND_ROOT'),
    ('epoch_mode',ACTIVATE,bump(k13.JOURNAL+'/epoch.json',mode=0o644),None,'CATALOG_FILE_NOT_PRIVATE'),
    ('epoch_absent',ACTIVATE,lambda h:h.tree.remove(k13.JOURNAL+'/epoch.json'),None,'CATALOG_FILE_NOT_PRIVATE'),
    ('lock_absent',ACTIVATE,lambda h:h.tree.remove(k13.JOURNAL+'/maintenance.lock'),None,'CATALOG_FILE_NOT_PRIVATE'),
    ('lock_mode',ACTIVATE,bump(k13.JOURNAL+'/maintenance.lock',mode=0o644),None,'CATALOG_FILE_NOT_PRIVATE'),
    ('lock_owner',ACTIVATE,bump(k13.JOURNAL+'/maintenance.lock',uid=1000),None,'CATALOG_FILE_NOT_PRIVATE'),
    ('lock_links',ACTIVATE,bump(k13.JOURNAL+'/maintenance.lock',nlink=2),None,'CATALOG_FILE_NOT_PRIVATE'),
    ('lock_directory',ACTIVATE,lambda h:(h.tree.remove(k13.JOURNAL+'/maintenance.lock'),h.tree.add(k13.JOURNAL+'/maintenance.lock',mode=0o600)),None,'CATALOG_FILE_NOT_PRIVATE'),
    ('release_hash',ACTIVATE,None,after_plan(k13.RELEASE_DIRECTORY+'/'+k13.RELEASE_NAME,b'{}'),'RELEASE_NOT_AS_SIGNED'),
    ('release_mode',ACTIVATE,bump(k13.RELEASE_DIRECTORY+'/'+k13.RELEASE_NAME,mode=0o644),None,'RELEASE_NOT_AS_SIGNED'),
    ('release_absent',ACTIVATE,lambda h:h.tree.remove(k13.RELEASE_DIRECTORY+'/'+k13.RELEASE_NAME),None,'RELEASE_NOT_AS_SIGNED'),
    ('engine_userns',ACTIVATE,lambda h:h.docker.info['SecurityOptions'].append('name=userns'),None,'ENGINE_USERNS_OR_ROOTLESS'),
    ('engine_rootless',ACTIVATE,lambda h:h.docker.info['SecurityOptions'].append('name=Rootless'),None,'ENGINE_USERNS_OR_ROOTLESS'),
    ('engine_shape',ACTIVATE,lambda h:h.docker.info.update(SecurityOptions=[['name=seccomp']]),None,'ENGINE_SECURITY_OPTIONS_INVALID'),
    ('engine_long',ACTIVATE,lambda h:h.docker.info.update(SecurityOptions=['x']*65),None,'ENGINE_SECURITY_OPTIONS_INVALID'),
    ('image_absent',ACTIVATE,lambda h:h.docker.images.pop(0),None,'COMMAND_FAILED'),
    ('image_resolves_elsewhere',ACTIVATE,lambda h:(h.docker.images.pop(0),h.docker.images[-1]['RepoTags'].append(hostemu.BACKEND)),None,'IMAGE_NOT_PRESENT'),
    ('build_sha',ACTIVATE,lambda h:[image['Config']['Labels'].update({'org.opencontainers.image.revision':'e'*40}) for image in h.docker.images],None,
     'PINS_BUILD_SHA_NOT_THE_IMAGE_REVISION'),
    ('scan_invalid',ACTIVATE,lambda h:h.docker.containers[0].update(Args='uvicorn'),None,'CONTAINER_COMMAND_INVALID'),
    ('scan_exec_ids',ACTIVATE,lambda h:h.docker.containers[0].update(ExecIDs=[1]),None,'CONTAINER_COMMAND_INVALID'),
    ('scan_long',ACTIVATE,lambda h:h.docker.containers[0].update(Args=['x']*257),None,'CONTAINER_COMMAND_INVALID'),
    ('worker_in_compose',ACTIVATE,lambda h:h.docker.containers[5].update(Args=['-m','app.r2d2_v2_shadow_worker']),None,'READER_PROCESS_FOUND'),
    ('launcher_in_compose',ACTIVATE,lambda h:h.docker.containers[1].update(Path='/c3po-reader/reader_launcher.py',Args=[]),None,'READER_PROCESS_FOUND'),
    ('reader_container_elsewhere',ACTIVATE,lambda h:h.docker.containers.append(k13.reader_container(name='by-hand')),None,'READER_PROCESS_FOUND'),
    ('reader_paused',ACTIVATE,lambda h:h.docker.containers.append(dict(k13.reader_container(name='by-hand'),State={'Status':'paused','Running':True,'Pid':1,
        'StartedAt':'x','Paused':True,'Restarting':False,'Dead':False,'ExitCode':0,'FinishedAt':'x'})),None,'READER_PROCESS_FOUND'),
    ('reader_container_exited',ACTIVATE,lambda h:h.docker.containers.append(k13.reader_container(running=False)),None,'READER_CONTAINER_PRESENT'),
    ('timer_enabled_before',ACTIVATE,lambda h:h.is_enabled.update({k13.TIMER:'enabled'}),None,'TIMER_ENABLED_BEFORE_ACTIVATION'),
    ('timer_active_before',ACTIVATE,unit_values(k13.TIMER,ActiveState='active'),None,'TIMER_ENABLED_BEFORE_ACTIVATION'),
    ('service_active_before',ACTIVATE,unit_values(k13.SERVICE,ActiveState='active'),None,'SERVICE_ACTIVE_BEFORE_ACTIVATION'),
    ('service_activating_before',ACTIVATE,unit_values(k13.SERVICE,ActiveState='activating'),None,'SERVICE_ACTIVE_BEFORE_ACTIVATION'),
    ('free_space',ACTIVATE,lambda h:h.vfs.update({hostemu.ROOT_DEVICE:type(h.vfs[hostemu.ROOT_DEVICE])(f_frsize=4096,f_blocks=1,f_bfree=1,f_bavail=56706990080//4096-1)}),
     None,'JOURNAL_FREE_SPACE_BELOW_FLOOR'),
    ('restart_without_activation',RESTART,lambda h:h.tree.remove(k13.CONFIG+'/activation.env'),None,'ACTIVATION_ENV_ABSENT'),
    ('restart_timer_disabled',RESTART,lambda h:h.is_enabled.update({k13.TIMER:'disabled'}),None,'TIMER_NOT_ENABLED'),
    ('restart_active',RESTART,unit_values(k13.SERVICE,ActiveState='active'),None,'SERVICE_NOT_STOPPED'),
    ('restart_deactivating',RESTART,unit_values(k13.SERVICE,ActiveState='deactivating'),None,'SERVICE_NOT_STOPPED'),
    ('restart_reload',RESTART,unit_values(k13.SERVICE,NeedDaemonReload='yes'),None,'READER_UNIT_NEEDS_DAEMON_RELOAD'),
    ('restart_leftover',RESTART,lambda h:h.docker.containers.append(k13.reader_container(running=False)),None,'READER_CONTAINER_PRESENT'),
    ('restart_other_reader',RESTART,lambda h:h.docker.containers.append(k13.reader_container(name='by-hand')),None,'READER_PROCESS_FOUND'),
    ('restart_activation_other',RESTART,lambda h:content(h,k13.CONFIG+'/activation.env',k13.ACTIVATION.replace(b'true',b'True')),None,'ACTIVATION_ENV_NOT_THE_CONSTANT'),
]
for key,path in (('units',k13.UNITS),('config',k13.CONFIG),('launcher',k13.LAUNCHER_DIRECTORY),('journal',k13.JOURNAL),('release',k13.RELEASE_DIRECTORY),
                 ('source',k13.SOURCE_ROOT),('capacity',k13.CAPACITY)):
    PRECHECK.append(('chain_'+key,ACTIVATE,None,bump(path,ino=99999),'PARENT_IDENTITY_MISMATCH'))
@pytest.mark.parametrize('label,mode,setup,host_change,code',PRECHECK,ids=[case[0] for case in PRECHECK])
def test_precheck_refusals_change_nothing(label,mode,setup,host_change,code):
    receipt,host,before=run(mode,setup=setup,host_change=host_change);refused(receipt,host,before,code)
    assert receipt['phase_reached']=='PRECHECK'

def test_deactivate_is_not_blocked_by_the_unit_files_and_reports_the_states_as_read():
    def setup(host):
        content(host,unit_path(k13.SERVICE),b'[Unit]\n');host.tree.get(k13.UNITS).mode=0o775
        host.units[k13.SERVICE].update(DropInPaths='/etc/systemd/system/c3po-reader.service.d/x.conf',NeedDaemonReload='yes')
        host.units[k13.TIMER].update(FragmentPath='/run/systemd/system/c3po-reader.timer')
    receipt,host,_=run(DEACTIVATE,setup=setup);complete(receipt,DEACTIVATE)
    units=receipt['precheck']['units'];assert units['service']['DropInPaths'].endswith('x.conf') and units['timer']['FragmentPath'].startswith('/run/')
    assert not [entry for entry in host.log if entry[0] in ('open','lstat','read') and entry[1].startswith('/etc/')]
    assert receipt['precheck']['chains']=={} and 'unit_files' not in receipt['precheck']

def test_the_new_york_rule_is_not_applied_to_deactivate_and_its_precheck_reads_no_reader_file():
    receipt,host,_=run(DEACTIVATE,setup=lambda h:(h.tree.remove(k13.CONFIG+'/secret.env'),h.docker.info['SecurityOptions'].append('userns')))
    complete(receipt,DEACTIVATE)
    assert not [entry for entry in host.commands if entry['argv'][1] in ('ps','info','image','container')]

def test_a_capacity_day_process_and_an_exited_worker_are_not_readers():
    def setup(host):
        host.docker.containers.append(dict(k13.reader_container(name='capacity-day-1'),Args=['-m','app.r2d2_v2_shadow_worker','--prepare-capacity-day']))
        host.docker.containers.append(k13.reader_container(name='old-worker',running=False,args=['-m','app.r2d2_v2_shadow_worker']))
    receipt,_,_=run(ACTIVATE,setup=setup);complete(receipt)
    scan={row['name']:row for row in receipt['precheck']['process_scan']}
    assert scan['capacity-day-1']['reader_like'] is False and 'old-worker' not in scan and len(scan)==9

def test_exec_sessions_are_counted_never_judged_and_no_command_word_leaves():
    def setup(host):
        host.docker.container('c3po-db-1')['ExecIDs']=['a'*64,'b'*64];host.docker.containers[0]['Args']=['--token','never-emit-argument-canary']
    receipt,_,_=run(ACTIVATE,setup=setup);complete(receipt)
    db=[row for row in receipt['precheck']['process_scan'] if row['name']=='c3po-db-1'];assert [row['exec_sessions'] for row in db]==[2]
    assert b'never-emit-argument-canary' not in f.line(receipt)
    assert b'uvicorn' not in f.line(receipt) and b'app.r2d2_worker' not in f.line(receipt)

def swap_at_open(path,remove=False):
    """Between the lstat of a guarded file and its open, the name is given to another file with the same bytes and
    metadata (another inode), or removed."""
    def setup(host):
        done=[];original=host.open
        def open_(name,flags,dir_fd=None):
            if dir_fd is not None and host.fds[dir_fd][3].rstrip('/')+'/'+name==path and not done:
                done.append(1);item=host.tree.get(path);host.tree.remove(path)
                if not remove:host.tree.add(path,kind='file',mode=item.mode,uid=item.uid,gid=item.gid,content=bytes(item.content))
            return original(name,flags,dir_fd)
        host.open=open_                       # an instance attribute of the emulated host, for this test only
    return setup
@pytest.mark.parametrize('path,code',[(k13.CONFIG+'/pins.env','PINS_NOT_AS_SIGNED'),(k13.UNITS+'/c3po-reader.service','UNIT_FILE_NOT_AS_SIGNED'),
                                      (k13.LAUNCHER_DIRECTORY+'/reader_launcher.py','LAUNCHER_NOT_AS_SIGNED'),(k13.JOURNAL+'/epoch.json','CATALOG_FILE_NOT_PRIVATE')])
def test_a_guarded_file_replaced_or_removed_between_its_lstat_and_its_open_is_refused(path,code):
    receipt,host,before=run(ACTIVATE,setup=swap_at_open(path));assert (receipt['status'],receipt['code'])==('REFUSED',code)
    receipt,host,before=run(ACTIVATE,setup=swap_at_open(path,remove=True));assert (receipt['status'],receipt['code'])==('REFUSED',code)

def test_an_os_error_while_reading_a_guarded_file_is_a_refusal_with_its_own_code():
    def setup(host):
        def hook(host,name,detail,calls):
            if name=='read' and detail[0]==k13.CONFIG+'/pins.env':raise OSError(5,'injected')
        host.hook=hook
    receipt,host,before=run(ACTIVATE,setup=setup);refused(receipt,host,before,'PRECHECK_OS_ERROR')

@pytest.mark.parametrize('value',['d\xe9ad','dead\nfoo','dead\nSubState=running'],ids=['non_ascii','line_without_equals','property_twice'])
def test_systemctl_output_that_is_not_one_property_per_line_is_refused(value):
    receipt,host,before=run(ACTIVATE,host_change=lambda h:h.units[k13.SERVICE].update(SubState=value));refused(receipt,host,before,'UNIT_PROPERTIES_INVALID')

def test_a_mount_line_with_more_options_after_readonly_is_refused():
    raw=k13.reader_service().replace(b'target=/c3po-capacity,readonly \\\n',b'target=/c3po-capacity,readonly,bind-propagation=rslave \\\n')
    receipt,host,before=run(ACTIVATE,setup=replace_signed(k13.UNITS+'/c3po-reader.service',raw));refused(receipt,host,before,'READER_UNIT_MOUNTS_NOT_AS_SIGNED')

def test_the_scan_refuses_an_inspect_that_is_not_the_container_listed():
    def path_none(host):host.docker.container('c3po-api-1')['Path']=None
    receipt,host,before=run(ACTIVATE,setup=path_none);refused(receipt,host,before,'CONTAINER_COMMAND_INVALID')
    def other(host):
        first=sorted(host.docker.containers,key=lambda item:item['Id'])[0];decoy=k13.reader_container(name='decoy',running=False)
        decoy['Name']='/'+first['Id'];host.docker.containers.insert(0,decoy)
    receipt,host,before=run(ACTIVATE,setup=other);refused(receipt,host,before,'CONTAINER_COMMAND_INVALID')

def test_decision_6_the_data_volume_bind_is_reported_never_accepted_silently():
    receipt,host,_=run(ACTIVATE);complete(receipt)
    assert receipt['binds_not_root_controlled']==['/mnt/day-d-data'] and receipt['effects']['bind_sources']['not_root_controlled']==['/mnt/day-d-data']
    assert set(receipt['precheck']['chains'])>={'source','capacity','journal','launcher'}
    receipt,_,_=run(DEACTIVATE);assert receipt['binds_not_root_controlled']==[]
    receipt,_,_=run(RESTART);complete(receipt,RESTART);assert receipt['binds_not_root_controlled']==['/mnt/day-d-data']

def test_the_source_bind_target_is_the_one_pins_env_names():
    def setup(host):
        content(host,unit_path(k13.SERVICE),k13.reader_service(source_target='/c3po-src'))
        content(host,k13.CONFIG+'/pins.env',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-src')))
    receipt,_,_=run(ACTIVATE,setup=setup);complete(receipt)

def test_secret_env_is_looked_at_by_lstat_only():
    receipt,host,_=run(ACTIVATE);complete(receipt)
    secret=k13.CONFIG+'/secret.env'
    assert [entry[0] for entry in host.log if len(entry)>1 and entry[1]==secret]==['lstat']
    assert b'secret.env' not in json.dumps(receipt['precheck']).encode() or receipt['precheck']['files']['secret_env']=='SHAPE_ONLY_AS_REQUIRED'
    assert set(receipt['precheck']['files'])=={'launcher','pins','release','secret_env','docker_cli','activation_env'}

def test_maintenance_lock_is_never_opened_and_nothing_is_opened_for_writing_but_the_temporary():
    receipt,host,_=run(ACTIVATE);complete(receipt)
    assert not [entry for entry in host.log if entry[0]=='open' and entry[1].endswith('maintenance.lock')]
    created=[entry for entry in host.log if entry[0] in ('create','mkdir','link','unlink')]
    temporary=k13.CONFIG+'/.hostops-%s-0.partial'%receipt['go_sha256'][:16]
    assert [entry[:2] for entry in created]==[('create',temporary),('link',temporary),('unlink',temporary)]

def test_free_space_at_the_floor_is_enough():
    def setup(host):host.vfs[hostemu.ROOT_DEVICE]=type(host.vfs[hostemu.ROOT_DEVICE])(f_frsize=4096,f_blocks=1,f_bfree=1,f_bavail=56706990080//4096)
    receipt,_,_=run(ACTIVATE,setup=setup);complete(receipt);assert receipt['precheck']['journal']['free_bytes']==56706990080


# ---------------------------------------------------------------- pins.env content (signed hash, content checked as well)
def pins_with(**changes):
    values=[(key,changes.get(key,value)) for key,value in k13.pins_values()]
    return values
PINS_CASES=[
    ('release_file',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_RELEASE_FILE='/app/day-d-data/r2d2-v2-release-20261005/other.json')),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('release_file_host_path',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_RELEASE_FILE=k13.RELEASE_DIRECTORY+'/'+k13.RELEASE_NAME)),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('release_sha',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_RELEASE_SHA='d'*64)),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('journal_dir',k13.pins_bytes(pins_with(C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR='/app/day-d-data/journal')),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('launcher_sha',k13.pins_bytes(pins_with(C3PO_READER_LAUNCHER_SHA256='e'*64)),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('build_sha',k13.pins_bytes(pins_with(C3PO_BUILD_SHA='f'*40)),'PINS_BUILD_SHA_NOT_THE_IMAGE_REVISION'),
    ('eleven_lines',k13.pins_bytes(k13.pins_values()[:-1]),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('thirteen_lines',k13.pins_bytes(k13.pins_values()+[('C3PO_DATABASE_URL','x')]),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('order',k13.pins_bytes(k13.pins_values()[1:2]+k13.pins_values()[:1]+k13.pins_values()[2:]),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('name_only',k13.PINS.replace(b'C3PO_R2D2_V2_SHADOW_POLL_SECONDS=1.0',b'C3PO_R2D2_V2_SHADOW_POLL_SECONDS'),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('empty_value',k13.PINS.replace(b'C3PO_R2D2_V2_SHADOW_POLL_SECONDS=1.0',b'C3PO_R2D2_V2_SHADOW_POLL_SECONDS='),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('space',k13.PINS.replace(b'=true',b'=true '),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('no_final_newline',k13.PINS[:-1],'PINS_CONTENT_NOT_AS_SIGNED'),
    ('crlf',k13.PINS.replace(b'\n',b'\r\n'),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('non_ascii',k13.PINS.replace(b'=1.0',b'=1.0\xc3\xa9'),'PINS_CONTENT_NOT_AS_SIGNED'),
    ('blank_line',k13.PINS+b'\n','PINS_CONTENT_NOT_AS_SIGNED'),
    ('trailing_line_without_newline',k13.PINS+b'C3PO_DATABASE_URL=x','PINS_CONTENT_NOT_AS_SIGNED'),
    ('too_large',k13.PINS+b'#'*4096,'PINS_NOT_AS_SIGNED'),
    ('source_dir_in_the_data_volume',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/app/day-d-data/r2d2-v2-source-20261005')),'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET'),
    ('source_dir_is_the_capacity_target',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-capacity')),'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET'),
    ('source_dir_is_the_launcher_target',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-reader')),'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET'),
    ('source_dir_is_the_journal_target',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-bar-journal')),'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET'),
    ('source_dir_two_deep',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/c3po-x/y')),'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET'),
    ('source_dir_not_c3po',k13.pins_bytes(pins_with(C3PO_R2D2_V2_SHADOW_SOURCE_DIR='/source')),'PINS_SOURCE_DIR_NOT_A_TOP_LEVEL_TARGET'),
]
@pytest.mark.parametrize('label,raw,code',PINS_CASES,ids=[case[0] for case in PINS_CASES])
def test_pins_content_cross_checks(label,raw,code):
    receipt,host,before=run(ACTIVATE,setup=replace_signed(k13.CONFIG+'/pins.env',raw));refused(receipt,host,before,code)


# ---------------------------------------------------------------- the switches: every way one can end
def form(host,words):host.switch_returncode[words]=1
def test_enable_that_fails_and_changes_nothing_after_the_file_is_a_partial_and_the_start_is_not_attempted():
    def setup(host):host.switch_returncode['enable --now']=1;host.switch_no_effect.add('enable --now')
    receipt,host,_=run(ACTIVATE,setup=setup)
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','SWITCH_COMMAND_FAILED')
    assert receipt['switches']['enable_now_timer']['settled']=='FAILED_NOTHING_CHANGED' and receipt['switches']['start_service']=={'started':False,'settled':'NOT_ATTEMPTED','changed':False}
    assert receipt['switches']['enable_now_timer']['changed'] is False and receipt['switches_changed_state'] is False
    assert host.switches==[['enable','--now','c3po-reader.timer']] and receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False
    assert node(host,k13.CONFIG+'/activation.env') is not None

def test_enable_that_fails_in_a_reconcile_changed_nothing_and_is_a_refusal():
    def setup(host):with_activation()(host);host.switch_returncode['enable --now']=1;host.switch_no_effect.add('enable --now')
    receipt,host,before=run(ACTIVATE,setup=setup)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED','REFUSED_NOTHING_CHANGED','SWITCH_COMMAND_FAILED')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0} and k13.state_of(host)==before

def test_enable_that_returns_zero_without_effect_is_uncertain():
    receipt,host,_=run(ACTIVATE,setup=lambda h:h.switch_no_effect.update({'enable --now','start --no-block'}))
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','SWITCH_NOT_READ_BACK_AS_DONE')
    # the command exited 0: the manager reloaded (systemctl reports success after the reload); the timer state is unknown
    assert receipt['switches']['enable_now_timer']['settled']=='UNKNOWN' and receipt['activation_performed'] is None and receipt['daemon_reload_performed'] is True

def test_enable_that_reports_failure_but_took_effect_is_done_and_the_run_stops():
    receipt,host,_=run(ACTIVATE,setup=lambda h:h.switch_returncode.update({'enable --now':1}))
    assert receipt['code']=='SWITCH_COMMAND_FAILED' and receipt['switches']['enable_now_timer']['settled']=='DONE' and receipt['activation_performed'] is True
    assert receipt['daemon_reload_performed'] is None,'reload said True only when the reloading switch exited 0'
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'

def test_enable_that_hangs_is_uncertain_and_nothing_follows():
    receipt,host,_=run(ACTIVATE,setup=lambda h:h.hang.add(('enable','--now')))
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','COMMAND_TIMEOUT')
    assert receipt['switches']['enable_now_timer']['settled']=='UNKNOWN' and receipt['switches']['start_service']['settled']=='NOT_ATTEMPTED'
    assert receipt['mutating_calls']['uncertain']==1 and receipt['activation_performed'] is None and receipt['switches_changed_state'] is None

def test_enable_that_hangs_after_its_effect_is_uncertain_even_when_the_readback_shows_it():
    receipt,host,_=run(ACTIVATE,setup=lambda h:h.hang_after.add(('enable','--now')))
    assert receipt['code']=='COMMAND_TIMEOUT' and receipt['switches']['enable_now_timer']['settled']=='UNKNOWN' and receipt['after']['timer_enabled']=='enabled'
    assert receipt['switches']['enable_now_timer']['changed'] is None,'what a switch that did not return changed is not attributed'

def test_start_that_fails_and_changes_nothing_is_a_partial_after_the_enable():
    def setup(host):host.switch_returncode['start --no-block']=1;host.switch_no_effect.add('start --no-block');host.timer_starts_service=False
    receipt,host,_=run(ACTIVATE,setup=setup)
    assert receipt['code']=='SWITCH_COMMAND_FAILED' and receipt['switches']['start_service']['settled']=='FAILED_NOTHING_CHANGED'
    assert receipt['switches']['enable_now_timer']['settled']=='DONE' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'

def test_start_that_returns_zero_while_the_unit_stays_inactive_is_uncertain():
    def setup(host):host.switch_no_effect.add('start --no-block');host.timer_starts_service=False
    receipt,_,_=run(ACTIVATE,setup=setup)
    assert receipt['code']=='SWITCH_NOT_READ_BACK_AS_DONE' and receipt['switches']['start_service']['settled']=='UNKNOWN'

def test_start_that_could_not_be_started_is_settled_as_nothing_changed():
    receipt,host,_=run(ACTIVATE,setup=lambda h:h.absent.add(('start','--no-block')))
    assert receipt['code']=='COMMAND_NOT_STARTED' and receipt['switches']['start_service']['settled']=='NOT_STARTED' and receipt['switches']['start_service']['changed'] is False
    assert receipt['mutating_calls']['failed_nothing_changed']==1 and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'

def test_first_switch_not_started_after_the_file_was_created_is_a_partial():
    receipt,host,_=run(ACTIVATE,setup=lambda h:h.absent.add(('enable','--now')))
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','COMMAND_NOT_STARTED') and host.switches==[]
    assert receipt['activation_performed'] is False

def test_readback_that_fails_leaves_every_switch_uncertain():
    def fail_after(host):
        previous=host.hook
        def hook(host,name,detail,calls):
            if name=='run' and host.switches and detail[0][1:2]==['is-enabled']:host.units[k13.TIMER]['SubState']='x;y'
        host.hook=hook
    receipt,host,_=run(ACTIVATE,setup=fail_after)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and receipt['code']=='UNIT_PROPERTIES_INVALID'
    assert {item['settled'] for item in receipt['switches'].values()}=={'UNKNOWN'} and receipt['after']['units']['status']=='UNAVAILABLE'

def test_activation_file_that_cannot_be_created_is_a_refusal_with_no_switch():
    receipt,host,before=run(ACTIVATE,setup=lambda h:setattr(h,'readonly',True))
    assert (receipt['status'],receipt['code'])==('REFUSED','FILESYSTEM_READ_ONLY') and host.switches==[] and k13.state_of(host)==before
    assert receipt['switches']=={'enable_now_timer':{'started':False,'settled':'NOT_ATTEMPTED','changed':False},'start_service':{'started':False,'settled':'NOT_ATTEMPTED','changed':False}}

def test_activation_file_that_appears_after_the_precheck_is_left_and_nothing_is_switched():
    def setup(host):
        def hook(host,name,detail,calls):
            if name=='create':host.tree.add(k13.CONFIG+'/activation.env',kind='file',mode=0o600,content=b'X=1\n')
        host.hook=hook
    receipt,host,_=run(ACTIVATE,setup=setup)
    assert receipt['code']=='DESTINATION_APPEARED_AFTER_PRECHECK' and host.switches==[] and bytes(node(host,k13.CONFIG+'/activation.env').content)==b'X=1\n'
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and receipt['ledger'][0]['state']=='NOT_CREATED'

def test_activation_file_changed_after_its_creation_is_found_by_the_readback():
    def setup(host):
        def hook(host,name,detail,calls):
            if name=='run' and detail[0][1:2]==['enable']:content(host,k13.CONFIG+'/activation.env',k13.ACTIVATION.replace(b'true',b'fals'))
        host.hook=hook
    receipt,_,_=run(ACTIVATE,setup=setup)
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','READBACK_HASH_MISMATCH')

def test_reconciled_activation_file_changed_during_the_run_is_found():
    def setup(host):
        with_activation()(host)
        def hook(host,name,detail,calls):
            if name=='run' and detail[0][1:2]==['enable']:content(host,k13.CONFIG+'/activation.env',k13.ACTIVATION.replace(b'true',b'fals'))
        host.hook=hook
    receipt,_,_=run(ACTIVATE,setup=setup)
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','ACTIVATION_ENV_CHANGED') and receipt['after']['activation_env']['status']=='UNAVAILABLE'

def test_the_container_fact_after_the_switch_is_never_a_gate():
    def setup(host):
        def hook(host,name,detail,calls):
            if name=='run' and host.switches and detail[0][1:2]==['ps']:host.docker.ps_returncode=1
        host.hook=hook
    receipt,_,_=run(ACTIVATE,setup=setup);complete(receipt)
    assert receipt['after']['container']=={'status':'UNAVAILABLE','code':'COMMAND_FAILED','returncode':1}

def test_restart_reset_that_fails_and_changes_nothing_is_a_refusal():
    def setup(host):host.switch_returncode['reset-failed']=1;host.switch_no_effect.add('reset-failed')
    receipt,host,before=run(RESTART,setup=setup)
    assert (receipt['status'],receipt['code'])==('REFUSED','SWITCH_COMMAND_FAILED') and k13.state_of(host)==before
    assert receipt['switches']['reset_failed_service']['settled']=='FAILED_NOTHING_CHANGED'

def test_restart_reset_returning_zero_on_a_unit_still_failed_is_uncertain():
    receipt,_,_=run(RESTART,setup=lambda h:h.switch_no_effect.update({'reset-failed','start --no-block'}))
    assert receipt['code']=='SWITCH_NOT_READ_BACK_AS_DONE' and receipt['switches']['reset_failed_service']['settled']=='UNKNOWN'

def test_restart_start_that_hits_the_start_limit_is_a_partial():
    def setup(host):host.switch_returncode['start --no-block']=1;host.switch_no_effect.add('start --no-block')
    receipt,_,_=run(RESTART,setup=setup)
    # the reset changed the service (failed -> inactive) and nothing is read between the two switches: the failed start
    # cannot be proved to have changed nothing
    assert receipt['code']=='SWITCH_COMMAND_FAILED' and receipt['switches']['start_service']['settled']=='UNKNOWN'
    assert receipt['switches']['reset_failed_service']['settled']=='DONE' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'

def test_deactivate_disable_that_fails_and_changes_nothing_is_a_refusal():
    def setup(host):host.switch_returncode['disable --now']=1;host.switch_no_effect.add('disable --now')
    receipt,host,before=run(DEACTIVATE,setup=setup)
    assert (receipt['status'],receipt['code'])==('REFUSED','SWITCH_COMMAND_FAILED') and k13.state_of(host)==before and receipt['daemon_reload_performed'] is False

def test_deactivate_disable_returning_zero_without_effect_is_uncertain():
    receipt,_,_=run(DEACTIVATE,setup=lambda h:h.switch_no_effect.add('disable --now'))
    assert receipt['code']=='SWITCH_NOT_READ_BACK_AS_DONE' and receipt['switches']['disable_now_timer']['settled']=='UNKNOWN'
    assert receipt['daemon_reload_performed'] is True and receipt['switches']['disable_now_timer']['changed'] is False

def test_deactivate_stop_without_effect_is_uncertain_and_a_failed_stop_that_changed_nothing_is_said():
    receipt,_,_=run(DEACTIVATE,setup=lambda h:h.switch_no_effect.add('stop --no-block'))
    assert receipt['code']=='SWITCH_NOT_READ_BACK_AS_DONE' and receipt['switches']['stop_service']['settled']=='UNKNOWN'
    def setup(host):host.switch_returncode['stop --no-block']=1;host.switch_no_effect.add('stop --no-block')
    receipt,_,_=run(DEACTIVATE,setup=setup)
    assert receipt['code']=='SWITCH_COMMAND_FAILED' and receipt['switches']['stop_service']['settled']=='FAILED_NOTHING_CHANGED'
    assert receipt['switches']['disable_now_timer']['settled']=='DONE' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'

def test_settle_reads_the_state_the_mode_requires():
    m=k13.K().m;before=('disabled','inactive','inactive')
    def one(name,after,returncode=0,before=before):
        state=m.Effects();state.issue();label=m.settle(state,name,{'returncode':returncode},before,after);return label,state.counts()
    running=('enabled','active','active')
    assert one('enable_now_timer',('enabled','inactive','inactive'),1,('enabled','inactive','inactive'))[0]=='UNKNOWN'
    assert one('disable_now_timer',('disabled','active','active'),1,('disabled','active','active'))[0]=='UNKNOWN'
    assert one('stop_service',('enabled','active','active'),1,running)[0]=='FAILED_NOTHING_CHANGED'
    assert one('disable_now_timer',('enabled','active','inactive'),1,running)[0]=='FAILED_NOTHING_CHANGED'
    assert one('stop_service',('disabled','inactive','active'),1,running)[0]=='FAILED_NOTHING_CHANGED'
    assert one('enable_now_timer',('enabled','active','inactive'))[0]=='DONE'
    assert one('enable_now_timer',('enabled','inactive','inactive'))[0]=='UNKNOWN'
    assert one('enable_now_timer',('disabled','active','inactive'))[0]=='UNKNOWN'
    assert one('enable_now_timer',before,1)==('FAILED_NOTHING_CHANGED',{'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0})
    assert one('enable_now_timer',before,0)[0]=='UNKNOWN'
    assert one('enable_now_timer',('disabled','inactive','failed'),1)[0]=='FAILED_NOTHING_CHANGED' and one('enable_now_timer',('disabled','active','inactive'),1)[0]=='UNKNOWN'
    assert one('start_service',('enabled','active','activating'))[0]=='DONE' and one('start_service',('enabled','active','active'))[0]=='DONE'
    assert one('start_service',('enabled','active','reloading'))[0]=='UNKNOWN'
    assert one('reset_failed_service',('enabled','active','inactive'))[0]=='DONE' and one('reset_failed_service',('enabled','active','inactive'),1)[0]=='FAILED_NOTHING_CHANGED'
    assert one('reset_failed_service',('enabled','active','failed'),1)[0]=='UNKNOWN'
    assert one('reset_failed_service',('enabled','active','failed'))[0]=='UNKNOWN'
    assert one('disable_now_timer',('disabled','inactive','active'))[0]=='DONE' and one('disable_now_timer',('disabled','active','active'))[0]=='UNKNOWN'
    assert one('disable_now_timer',('enabled','inactive','active'))[0]=='UNKNOWN'
    for state in ('inactive','deactivating','failed'):assert one('stop_service',('disabled','inactive',state))[0]=='DONE'
    for state in ('active','activating','reloading'):assert one('stop_service',('disabled','inactive',state))[0]=='UNKNOWN'
    assert one('stop_service',None)==('UNKNOWN',{'issued':1,'succeeded':0,'failed_nothing_changed':0,'uncertain':1})
    assert one('start_service',('enabled','active','inactive'),1)[0]=='FAILED_NOTHING_CHANGED'
    assert one('disable_now_timer',('disabled','inactive','failed'),1)[0]=='DONE' and one('disable_now_timer',('disabled','inactive','active'),1)[0]=='DONE'
    assert one('stop_service',('enabled','active','inactive'),1)[0]=='DONE' and one('reset_failed_service',('x','y','inactive'),1)[0]=='FAILED_NOTHING_CHANGED'


# ---------------------------------------------------------------- the budget
def budget_run(mode,left,costs=()):
    """A run that reaches the last refusal with `left` seconds of the 60: the precheck's commands take the rest."""
    docs,host=k13.case(k13.at(mode),mode=mode);budget=f.Budget(docs.now).attach(host)
    budget.cost(60-left,'is-enabled')                   # the precheck's one is-enabled carries the whole cost
    for words,seconds in costs:budget.cost(seconds,*words)
    before=k13.state_of(host);receipt=docs.run(host,**budget.options());return receipt,host,before
@pytest.mark.parametrize('mode,need',[(ACTIVATE,45),(RESTART,23),(DEACTIVATE,45)])
def test_budget_edge_before_the_first_effect(mode,need):
    receipt,host,before=budget_run(mode,need)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' or receipt['code']!='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT',receipt['code']
    assert receipt['precheck']['seconds_left_before_first_effect']==need
    receipt,host,before=budget_run(mode,need-0.5)
    refused(receipt,host,before,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT')

def test_a_switch_that_uses_its_whole_class_still_leaves_the_next_one_its_class():
    receipt,host,_=budget_run(ACTIVATE,45)
    assert receipt['code'] in (None,'SWITCH_NOT_READ_BACK_AS_DONE')
    docs,host=k13.case(k13.at(ACTIVATE));budget=f.Budget(docs.now).attach(host)
    budget.cost(15,'is-enabled').cost(30,'enable','--now')
    receipt=docs.run(host,**budget.options())
    # 60 - 15 (precheck) - 30 (enable) = 15 s left when the start is asked: 8 + 4 fit
    assert host.switches==[['enable','--now','c3po-reader.timer'],['start','--no-block','c3po-reader.service']]


# ---------------------------------------------------------------- failure and death at every host call
@pytest.mark.parametrize('mode',[ACTIVATE,RESTART,DEACTIVATE])
@pytest.mark.parametrize('kind',['death','oserror','runtime'])
def test_failure_or_death_at_every_host_call(mode,kind):
    docs,host=k13.case(k13.at(mode),mode=mode);docs.run(host);total=host.calls
    for index in range(1,total+1):
        docs,host=k13.case(k13.at(mode),mode=mode)
        def hook(host,name,detail,calls,index=index):
            if calls==index:
                if kind=='death':raise hostemu.Death()
                raise OSError(5,'injected') if kind=='oserror' else RuntimeError('injected')
        host.hook=hook;before=k13.state_of(host);receipt=docs.run(host)
        assert f.sealed(receipt) and 'injected' not in json.dumps(receipt)
        changed=k13.state_of(host)!=before
        if receipt['status']=='REFUSED':assert not changed and host.switches==[] or (not changed),(index,receipt['code'])
        if changed:assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' or receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW',(index,receipt)
        if receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW':assert kind!='death',index
        if kind=='death' and receipt['status']!='REFUSED':
            assert receipt['outcome']=='PARTIAL_SWITCH_STATE_REQUIRES_READBACK' and receipt['activation_performed'] is None and receipt['daemon_reload_performed'] is None


# ---------------------------------------------------------------- receipts
def test_receipt_reductions_keep_the_record_of_mutating_calls():
    m=k13.K().m
    receipt,_,_=run(ACTIVATE);body=dict(receipt);body.pop('metadata_sha256')
    m._reduce_scan(body);assert body['precheck']['process_scan']=={'containers':8,'reader_like':0}
    m._reduce_precheck(body);assert body['precheck']=={'reduced_for_size':True}
    reconciled,_,_=run(ACTIVATE,setup=k13.activated);body=dict(reconciled);m._reduce_scan(body)
    assert body['precheck']['process_scan']=={'containers':9,'reader_like':1}
    big=dict(receipt);big.pop('metadata_sha256');big['precheck']=dict(big['precheck'],padding=['x'*1000]*70);sealed=m.seal(big)
    assert sealed['size_reductions']==['PROCESS_SCAN_REDUCED_TO_COUNTS','PRECHECK_DROPPED'] and sealed['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert sealed['outcome']=='RECEIPT_REDUCED_STATE_REQUIRES_READBACK' and sealed['mutating_calls']==receipt['mutating_calls']

def test_receipt_carries_the_unit_states_before_and_after_and_no_environment():
    receipt,_,_=run(ACTIVATE);complete(receipt)
    units=receipt['precheck']['units']
    assert units['timer_enabled']=='disabled' and units['service']['FragmentPath']=='/etc/systemd/system/c3po-reader.service'
    line=f.line(receipt);assert b'C3PO_DATABASE_URL' not in line and b'postgresql' not in line
