"""K5 on the emulated host, both signed modes: the complete runs (and the two in sequence on one host), every precheck
refusal (nothing changed, no systemctl verb but show), every way the one effect can end, what the readback finds, the
session window, the plan, and what never reaches a receipt. No run waits: there is no pause in either mode."""
import ast
from datetime import datetime,timedelta,timezone
import json

import pytest

import family as f
import hostemu
import k5

def run(docs,host,**options):return docs.run(host,**options)
def outcome(receipt):return (receipt['status'],receipt['outcome'],receipt['code'])
NOTHING={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0}
PARTIAL='PARTIAL_METADATA_REQUIRES_REVIEW'
CREATING=('mkdir','create','write','link','unlink','umask','flock','pause')

# ---------------------------------------------------------------- complete runs
def test_activate_gives_exactly_enable_now_of_the_timer_and_reads_it_back():
    docs,host=k5.case();m=docs.k.m;receipt=run(docs,host)
    assert outcome(receipt)==(m.COMPLETE_STATUS,'TIMER_ENABLED_ACTIVE_RESET_PENDING',None) and f.sealed(receipt)
    assert k5.verbs(host)==[['enable','--now',k5.TIMER]] and receipt['mode']=='ACTIVATE'
    assert receipt['activation_performed'] is True and receipt['daemon_reload_performed'] is True
    assert receipt['mutating_calls']=={'issued':1,'succeeded':1,'failed_nothing_changed':0,'uncertain':0} and receipt['commands_started']['EFFECT']==1
    back=receipt['observed']['readback']
    assert back['timer']['UnitFileState']=='enabled' and back['timer']['ActiveState']=='active' and back['enablement_link']=={'exists':True,'type':'symlink'}
    assert back['entries']==receipt['precheck']['entries']=={'JOURNAL':2,'STATE':0,'DOCKER_CLI':0} and back['unit_files']=={'service':True,'timer':True}
    assert receipt['precheck']['token']=={'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1}
    assert not [entry for entry in host.log if entry[0] in CREATING]
    assert host.effect_commands()==[] and host.container_runs()==[] and host.fds=={}

def test_reset_gives_exactly_reset_failed_of_the_service_after_seeing_the_78():
    docs,host=k5.case(mode='RESET');m=docs.k.m;receipt=run(docs,host)
    assert outcome(receipt)==(m.COMPLETE_STATUS,'SERVICE_REFUSAL_78_SEEN_RESET_FAILED_VERIFIED',None) and f.sealed(receipt)
    assert k5.verbs(host)==[['reset-failed',k5.SERVICE]] and receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False
    assert receipt['observed']['service_before']['ExecMainStatus']=='78' and receipt['observed']['service_after']['ActiveState']=='inactive'
    assert receipt['mutating_calls']=={'issued':1,'succeeded':1,'failed_nothing_changed':0,'uncertain':0}
    assert not [entry for entry in host.log if entry[0] in CREATING]

def test_activate_then_reset_on_the_same_host_completes_both():
    docs,host=k5.case();assert run(docs,host)['code'] is None
    second=f.Docs(docs.k,k5.fields(host,'RESET'),now=k5.RESET_NOW);receipt=run(second,host)
    assert receipt['code'] is None and k5.verbs(host)==[['enable','--now',k5.TIMER],['reset-failed',k5.SERVICE]]
    assert host.systemd.service['ActiveState']=='inactive' and host.systemd.timer['ActiveState']=='active'

def test_the_token_is_only_lstat_ed_never_opened_or_read_and_nothing_secret_reaches_the_receipt():
    for mode in ('ACTIVATE','RESET'):
        docs,host=k5.case(mode=mode);receipt=run(docs,host);line=f.line(receipt);token=k5.PATHS['CONFIG']+'/token'
        assert not [entry for entry in host.log if entry[0] in ('open','read') and token in str(entry)]
        assert [entry for entry in host.log if entry[0]=='lstat' and entry[1]==token]
        assert k5.TOKEN_CANARY.strip() not in line and hostemu.SECRET.encode() not in line and b'never-emit' not in line and b'"size"' not in line
    tree=ast.parse((k5.DIRECTORY/'op.py').read_text())
    assert 'st_size' not in {node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)},'the source never names a size'
    names={node.id for node in ast.walk(tree) if isinstance(node,ast.Name)}|{node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not names&{'pause','sleep','acquire_lock','open_lock','probe_lock'},'nothing waits'

def test_the_command_table_and_the_effect_of_each_mode():
    m=k5.K().m
    for row in m.COMMANDS.values():
        if row['tool']=='systemctl':assert row['argv'][0] in ('show','enable','reset-failed') and row['middle'] is None
    assert m.COMMANDS['enable']['argv']==['enable','--now',k5.TIMER] and m.COMMANDS['reset_failed']['argv']==['reset-failed',k5.SERVICE]
    assert {name for name,row in m.COMMANDS.items() if row['kind']=='EFFECT'}=={'enable','reset_failed'} and m.EFFECT_OF_MODE=={'ACTIVATE':'enable','RESET':'reset_failed'}
    assert [m.COMMANDS[name]['class'] for name in ('enable','reset_failed')]==['SWITCH','SWITCH'] and not [row for row in m.COMMANDS.values() if row['kind']=='CONTAINER']
    assert set(m.CORE_PARTS)=={'core','runner','docker','parents'},'no lock part: nothing waits'

# ---------------------------------------------------------------- ACTIVATE: what the start the timer caused shows at the readback
@pytest.mark.parametrize('setup,code',[(lambda s:None,None),
                                       (lambda s:setattr(s,'start_after',1.0),None),
                                       (lambda s:setattr(s,'settle_after',1000.0),None),
                                       (lambda s:setattr(s,'outcome','1'),'SERVICE_START_NOT_A_REFUSAL'),
                                       (lambda s:setattr(s,'outcome','0'),'SERVICE_START_NOT_A_REFUSAL'),
                                       (lambda s:setattr(s,'outcome','125'),'SERVICE_START_NOT_A_REFUSAL'),
                                       (lambda s:setattr(s,'outcome','78-after-a-restart'),'SERVICE_START_NOT_A_REFUSAL'),
                                       (lambda s:setattr(s,'create_link',False),'ENABLEMENT_LINK_ABSENT'),
                                       (lambda s:setattr(s,'next_elapse',''),'ENABLE_NOT_VERIFIED'),
                                       (lambda s:setattr(s,'next_elapse','n/a'),'ENABLE_NOT_VERIFIED')])
def test_activate_judges_what_the_start_shows_without_waiting_for_it(setup,code):
    docs,host=k5.case();setup(host.systemd);receipt=run(docs,host)
    if code is None:assert receipt['code'] is None and receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    else:assert receipt['status']==PARTIAL and receipt['code']==code,(receipt['code'],receipt['findings'])
    assert not [entry for entry in host.log if entry[0]=='pause']

def test_a_claim_taken_by_the_start_is_a_finding():
    docs,host=k5.case();host.systemd.outcome='1';host.systemd.take_claim=True;receipt=run(docs,host)
    assert 'SUPERVISOR_ENTRIES_CHANGED' in receipt['findings'] and receipt['observed']['readback']['entries']['STATE']==1

def test_the_supervisor_container_while_the_start_runs_is_a_fact_in_activate():
    docs,host=k5.case();host.systemd.settle_after=1000.0;original=host.systemd.start_service
    def start():
        original();host.docker.containers.append(hostemu.container('c3po-massive',hostemu.BACKEND,hostemu.BACKEND,[],running=True))
    host.systemd.start_service=start;receipt=run(docs,host)
    assert receipt['code'] is None and receipt['observed']['readback']['supervisor_container_present'] is True

# ---------------------------------------------------------------- every end of the one effect
@pytest.mark.parametrize('setup,status,code,activation,uncertain',[
    (lambda host:setattr(host.systemd,'enable_effect',False),'REFUSED','ENABLE_FAILED_TIMER_UNCHANGED',False,0),
    (lambda host:(setattr(host.systemd,'enable_effect',False),setattr(host.systemd,'enable_rc',1)),'REFUSED','ENABLE_FAILED_TIMER_UNCHANGED',False,0),
    (lambda host:setattr(host.systemd,'enable_rc',1),PARTIAL,'ENABLE_NOT_VERIFIED',None,1),
    (lambda host:setattr(host,'hang_after',{('enable','--now')}),PARTIAL,'COMMAND_TIMEOUT',None,1),
    (lambda host:setattr(host,'hang',{('enable','--now')}),PARTIAL,'COMMAND_TIMEOUT',None,1),
    (lambda host:setattr(host,'absent',{('enable','--now')}),'REFUSED','COMMAND_NOT_STARTED',False,0)])
def test_every_end_of_the_enable(setup,status,code,activation,uncertain):
    docs,host=k5.case();setup(host);before=k5.state_of(host);receipt=run(docs,host)
    assert (receipt['status'],receipt['code'])==(status,code) and receipt['activation_performed'] is activation
    assert receipt['daemon_reload_performed'] is activation and receipt['mutating_calls']['uncertain']==uncertain
    if status=='REFUSED':assert k5.state_of(host)==before and receipt['outcome']=='REFUSED_NOTHING_CHANGED'
    assert receipt['observed']['readback']['entries']=={'JOURNAL':2,'STATE':0,'DOCKER_CLI':0}

@pytest.mark.parametrize('setup,status,code,uncertain',[
    (lambda host:setattr(host.systemd,'reset_effect',False),'REFUSED','RESET_FAILED_SERVICE_STILL_FAILED',0),
    (lambda host:setattr(host.systemd,'reset_rc',1),PARTIAL,'RESET_NOT_VERIFIED',1),
    (lambda host:setattr(host,'hang',{('reset-failed',)}),PARTIAL,'COMMAND_TIMEOUT',1),
    (lambda host:setattr(host,'hang_after',{('reset-failed',)}),PARTIAL,'COMMAND_TIMEOUT',1),
    (lambda host:setattr(host,'absent',{('reset-failed',)}),'REFUSED','COMMAND_NOT_STARTED',0)])
def test_every_end_of_the_reset(setup,status,code,uncertain):
    docs,host=k5.case(mode='RESET');setup(host);before=k5.state_of(host);receipt=run(docs,host)
    assert (receipt['status'],receipt['code'])==(status,code) and receipt['mutating_calls']['uncertain']==uncertain
    if status=='REFUSED':assert k5.state_of(host)==before

def _at_reset(action):
    def hook(host,name,detail,calls):
        if name=='run' and 'reset-failed' in detail[0]:action(host)
    return hook
@pytest.mark.parametrize('action,code',[
    (lambda host:host.docker.containers.append(hostemu.container('c3po-massive',hostemu.BACKEND,hostemu.BACKEND,[],running=True)),'SUPERVISOR_CONTAINER_LEFT'),
    (lambda host:host.tree.remove(k5.LINK),'ENABLEMENT_LINK_ABSENT'),
    (lambda host:host.systemd.timer.update(ActiveState='inactive'),'TIMER_NOT_ACTIVE_AFTER_RUN'),
    (lambda host:host.tree.get(k5.UNITS+'/'+k5.TIMER).content.extend(b'#'),'UNIT_FILE_CHANGED'),
    (lambda host:host.tree.add(k5.PATHS['STATE']+'/2026-10-05.claim-1',kind='file',mode=0o600),'SUPERVISOR_ENTRIES_CHANGED')])
def test_reset_judges_what_it_left(action,code):
    docs,host=k5.case(mode='RESET');host.hook=_at_reset(action);receipt=run(docs,host)
    assert (receipt['status'],receipt['code'])==(PARTIAL,code)

def test_a_service_that_starts_again_after_the_reset_is_a_finding():
    docs,host=k5.case(mode='RESET');host.systemd.after_reset_shows=[{},{'ActiveState':'activating','SubState':'start'}];receipt=run(docs,host)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'SERVICE_NOT_IDLE_AFTER_RESET')

def test_a_failed_readback_is_a_finding_never_a_complete():
    docs,host=k5.case();seen=[0]
    def hook(host_,name,detail,calls):
        if name=='run' and detail[0][1:3]==['ps','-a']:
            seen[0]+=1
            if seen[0]==2:raise OSError(5,'injected')
    host.hook=hook;receipt=run(docs,host)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'READBACK_INCOMPLETE') and receipt['activation_performed'] is True

# ---------------------------------------------------------------- refusals before the effect: nothing changed, no verb
def _tree(path,**attributes):
    def change(host):
        node=host.tree.get(path)
        for key,value in attributes.items():setattr(node,key,value)
    return change
def _add(path,**attributes):return lambda host:host.tree.add(path,**attributes)
def _remove(path):return lambda host:host.tree.remove(path)
def _service(**values):return lambda host:host.systemd.service.update(values)
def _timer(**values):return lambda host:host.systemd.timer.update(values)
def _docker_inactive(host):host.units['docker.service']['ActiveState']='inactive'
def _container(host):host.docker.containers.append(hostemu.container('c3po-massive',hostemu.BACKEND,hostemu.BACKEND,[],running=False))
def _retention_elsewhere(host):host.docker.images[0]['RepoTags'].remove(k5.RETENTION);host.docker.images[3]['RepoTags'].append(k5.RETENTION)
def _image_absent(host):host.docker.images.pop(0)
def _image_answers_another(host):
    found=host.docker.find;other=host.docker.images[3]
    host.docker.find=lambda reference:other if reference==hostemu.BACKEND else found(reference)
def _boot(host):host.tree.get('/proc/sys/kernel/random/boot_id').content=bytearray(b'11111111-2222-3333-4444-555555555555\n')
def _token_link(host):host.tree.remove(k5.PATHS['CONFIG']+'/token');host.tree.add(k5.PATHS['CONFIG']+'/token',kind='symlink',mode=0o777)
COMMON=[('token absent',_remove(k5.PATHS['CONFIG']+'/token'),'TOKEN_ABSENT'),
        ('token mode',_tree(k5.PATHS['CONFIG']+'/token',mode=0o644),'TOKEN_METADATA'),
        ('token owner',_tree(k5.PATHS['CONFIG']+'/token',uid=1000),'TOKEN_METADATA'),
        ('token group',_tree(k5.PATHS['CONFIG']+'/token',gid=1000),'TOKEN_METADATA'),
        ('token link',_token_link,'TOKEN_METADATA'),
        ('token two links',_tree(k5.PATHS['CONFIG']+'/token',nlink=2),'TOKEN_METADATA'),
        ('journal third entry',_add(k5.PATHS['JOURNAL']+'/producer.lock',kind='file',mode=0o600),'SUPERVISOR_ENTRIES_NOT_AS_SIGNED'),
        ('a claim',_add(k5.PATHS['STATE']+'/2026-10-05.claim-1',kind='file',mode=0o600),'SUPERVISOR_ENTRIES_NOT_AS_SIGNED'),
        ('docker cli config',_add(k5.PATHS['DOCKER_CLI']+'/config.json',kind='file',mode=0o600),'SUPERVISOR_ENTRIES_NOT_AS_SIGNED'),
        ('service bytes',lambda host:host.tree.get(k5.UNITS+'/'+k5.SERVICE).content.extend(b'#'),'UNIT_FILE_NOT_AS_INSTALLED'),
        ('timer mode',_tree(k5.UNITS+'/'+k5.TIMER,mode=0o664),'UNIT_FILE_NOT_AS_INSTALLED'),
        ('timer owner',_tree(k5.UNITS+'/'+k5.TIMER,uid=1000),'UNIT_FILE_NOT_AS_INSTALLED'),
        ('timer links',_tree(k5.UNITS+'/'+k5.TIMER,nlink=2),'UNIT_FILE_NOT_AS_INSTALLED'),
        ('timer identity',lambda host:setattr(host.tree.get(k5.UNITS+'/'+k5.TIMER),'ino',9999),'UNIT_FILE_NOT_AS_INSTALLED'),
        ('service absent',_remove(k5.UNITS+'/'+k5.SERVICE),'PRECHECK_OS_ERROR'),
        ('drop-in of the service',_add(k5.UNITS+'/'+k5.SERVICE+'.d'),'DROP_IN_PRESENT'),
        ('drop-in of the timer',_add(k5.UNITS+'/'+k5.TIMER+'.d'),'DROP_IN_PRESENT'),
        ('drop-in directory a link',lambda host:host.tree.add(k5.UNITS+'/'+k5.TIMER+'.d',kind='symlink',mode=0o777),'DROP_IN_PRESENT'),
        ('timer drop-in path',_timer(DropInPaths='/run/systemd/system/c3po-massive.timer.d/x.conf'),'DROP_IN_PRESENT'),
        ('service drop-in path',_service(DropInPaths='/etc/systemd/system/c3po-massive.service.d/x.conf'),'DROP_IN_PRESENT'),
        ('wants is a link',lambda host:(host.tree.remove(k5.UNITS+'/timers.target.wants'),host.tree.add(k5.UNITS+'/timers.target.wants',kind='symlink')),'UNIT_PATH_UNREADABLE'),
        ('docker inactive',_docker_inactive,'DOCKER_SERVICE_NOT_ACTIVE'),
        ('container present',_container,'SUPERVISOR_CONTAINER_PRESENT'),
        ('retention elsewhere',_retention_elsewhere,'RETENTION_TAG_ELSEWHERE'),
        ('image absent',_image_absent,'COMMAND_FAILED'),
        ('image inspect answers another image',_image_answers_another,'IMAGE_ID_MISMATCH'),
        ('another boot',_boot,'EVIDENCE_FROM_EARLIER_BOOT'),
        ('unit directory changed',_tree(k5.UNITS,mode=0o750),'PARENT_IDENTITY_MISMATCH'),
        ('state root replaced',lambda host:setattr(host.tree.get(k5.PATHS['STATE']),'ino',7777),'PARENT_IDENTITY_MISMATCH'),
        ('show output not ascii',lambda host:host.systemd.timer.update(Result='succ\xe8s'),'PROPERTY_OUTPUT_INVALID'),
        ('identity',lambda host:setattr(host,'actor',(0,1000)),'EXECUTOR_IDENTITY')]
ACTIVATE_ONLY=[('enablement link',_add(k5.LINK,kind='symlink',mode=0o777),'ENABLEMENT_LINK_PRESENT'),
               ('timer enabled',_timer(UnitFileState='enabled'),'TIMER_NOT_DISABLED_AND_INACTIVE'),
               ('timer active',_timer(ActiveState='active'),'TIMER_NOT_DISABLED_AND_INACTIVE'),
               ('service failed',_service(ActiveState='failed',SubState='failed',Result='exit-code'),'SERVICE_NOT_IDLE'),
               ('service failed before and left inactive',_service(Result='exit-code'),'SERVICE_NOT_IDLE'),
               ('service ran',_service(InvocationID='0'*31+'1'),'SERVICE_NOT_IDLE'),
               ('service running',_service(ActiveState='active',SubState='running'),'SERVICE_NOT_IDLE'),
               ('service bad setting',_service(LoadState='bad-setting'),'UNIT_LOAD_STATE'),
               ('service not loaded yet',_service(LoadState='not-found'),'UNIT_LOAD_STATE'),
               ('timer not loaded yet',_timer(LoadState='not-found'),'UNIT_LOAD_STATE'),
               ('service another fragment',_service(FragmentPath='/run/systemd/system/c3po-massive.service'),'UNIT_NOT_THE_INSTALLED_FRAGMENT'),
               ('timer another fragment',_timer(FragmentPath='/usr/lib/systemd/system/c3po-massive.timer'),'UNIT_NOT_THE_INSTALLED_FRAGMENT'),
               ('timer masked',_timer(LoadState='masked'),'UNIT_LOAD_STATE')]
RESET_ONLY=[('link absent',_remove(k5.LINK),'ENABLEMENT_LINK_ABSENT'),
            ('link a file',lambda host:(host.tree.remove(k5.LINK),host.tree.add(k5.LINK,kind='file',mode=0o644)),'ENABLEMENT_LINK_ABSENT'),
            ('timer disabled',_timer(UnitFileState='disabled'),'TIMER_NOT_ENABLED_AND_ACTIVE'),
            ('timer inactive',_timer(ActiveState='inactive'),'TIMER_NOT_ENABLED_AND_ACTIVE'),
            ('timer without next elapse',_timer(NextElapseUSecRealtime=''),'TIMER_NOT_ENABLED_AND_ACTIVE'),
            ('timer another fragment',_timer(FragmentPath='/usr/lib/systemd/system/c3po-massive.timer'),'TIMER_NOT_ENABLED_AND_ACTIVE'),
            ('timer not loaded',_timer(LoadState='not-found'),'TIMER_NOT_ENABLED_AND_ACTIVE'),
            ('service still starting',_service(ActiveState='activating',SubState='start'),'SERVICE_NOT_REFUSED_78'),
            ('service exit 1',_service(ExecMainStatus='1'),'SERVICE_NOT_REFUSED_78'),
            ('service restarted',_service(NRestarts='1'),'SERVICE_NOT_REFUSED_78'),
            ('service killed',_service(Result='signal',ExecMainCode='2',ExecMainStatus='9'),'SERVICE_NOT_REFUSED_78'),
            ('service exit code but not exited',_service(ExecMainCode='2'),'SERVICE_NOT_REFUSED_78'),
            ('service failed substate other',_service(SubState='dead'),'SERVICE_NOT_REFUSED_78'),
            ('service already reset',_service(ActiveState='inactive',SubState='dead',Result='success'),'SERVICE_NOT_REFUSED_78'),
            ('service never ran',_service(InvocationID=''),'SERVICE_NOT_REFUSED_78'),
            ('service another fragment',_service(FragmentPath='/run/x.service'),'SERVICE_NOT_REFUSED_78'),
            ('service not loaded',_service(LoadState='error'),'SERVICE_NOT_REFUSED_78'),
            ('another start refused',_service(InvocationID='%032x'%0xdef9),'SERVICE_INVOCATION_NOT_THE_SIGNED_ONE')]

@pytest.mark.parametrize('mode,label,change,code',[('ACTIVATE',)+row for row in COMMON+ACTIVATE_ONLY]+[('RESET',)+row for row in COMMON+RESET_ONLY],
                         ids=['ACTIVATE '+row[0] for row in COMMON+ACTIVATE_ONLY]+['RESET '+row[0] for row in COMMON+RESET_ONLY])
def test_every_precheck_refuses_with_nothing_changed_and_no_verb_given(mode,label,change,code):
    docs,host=k5.case(mode=mode);change(host);before=k5.state_of(host);receipt=run(docs,host)
    assert outcome(receipt)==('REFUSED',docs.k.m.REFUSED_OUTCOME,code),receipt.get('precheck')
    assert receipt['mutating_calls']==NOTHING and receipt['phase_reached']=='PRECHECK' and k5.verbs(host)==[] and k5.state_of(host)==before
    assert receipt['activation_performed'] is False and receipt['daemon_reload_performed'] is False and host.fds=={}

def test_a_slow_precheck_refuses_before_the_effect_when_its_class_reserve_and_reads_do_not_fit():
    docs,host=k5.case();m=docs.k.m;budget=f.Budget(docs.now).attach(host).cost(11,'ps').cost(6,'image','inspect')
    before=k5.state_of(host);receipt=run(docs,host,**budget.options())
    assert outcome(receipt)==('REFUSED',m.REFUSED_OUTCOME,'BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT') and k5.verbs(host)==[] and k5.state_of(host)==before
    need=m.effects_budget('enable')+m.AFTER_EFFECT_READ_SECONDS
    assert need==38 and receipt['precheck']['seconds_left_before_the_effect']<need
    docs,host=k5.case();budget=f.Budget(docs.now).attach(host).cost(9,'ps').cost(6,'image','inspect');receipt=run(docs,host,**budget.options())
    assert receipt['code'] is None,'with the class, the reserve and the reads still fitting, the same run completes'

def test_the_clock_inside_the_session_window_refuses_even_when_the_signed_window_does_not_say_so():
    for mode in ('ACTIVATE','RESET'):
        docs,host=k5.case(mode=mode);inside=datetime(2026,10,5,15,0,tzinfo=timezone.utc)
        receipt=docs.perform(host,clock=lambda:inside)
        assert (receipt['status'],receipt['code'])==('REFUSED','CLOCK_INSIDE_SESSION_WINDOW') and k5.verbs(host)==[]

@pytest.mark.parametrize('start,minutes,ok',[('2026-10-05T12:44:00',15,True),('2026-10-05T12:45:00',15,False),('2026-10-05T12:58:59',1,False),
                                             ('2026-10-06T16:00:00',15,False),('2026-10-07T19:45:00',15,False),('2026-10-08T19:46:00',15,False),
                                             ('2026-10-08T20:00:00',15,True),('2026-10-09T20:38:00',15,True),('2026-10-09T09:00:00',15,True),
                                             ('2026-10-10T14:00:00',15,True),('2026-10-06T23:30:00',15,True),('2026-10-07T00:00:00',15,True)])
def test_the_gate_must_lie_wholly_outside_the_session_window_with_its_margin(start,minutes,ok):
    for mode in ('ACTIVATE','RESET'):
        docs,host=k5.case(mode=mode);begin=datetime.fromisoformat(start+'+00:00');docs.shift(begin,begin+timedelta(minutes=minutes))
        if ok:docs.authenticate(clock=lambda:begin)
        else:assert f.refusal(lambda:docs.authenticate(clock=lambda:begin))=='WINDOW_INSIDE_SESSION_WINDOW'

# ---------------------------------------------------------------- the plan, refused from its bytes
def _set(path,value):
    def change(plan):
        target=plan
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
    return change
PLAN=[(('invocation_id',),'%032x'%1,'INVOCATION_ID_INVALID'),(('invocation_id',),'','INVOCATION_ID_INVALID'),(('mode',),'REAL','MODE_INVALID'),(('mode',),None,'MODE_INVALID'),(('mode',),'activate','MODE_INVALID'),
      (('expected_entries','JOURNAL'),3,'EXPECTED_ENTRIES_INVALID'),(('expected_entries','JOURNAL'),2.0,'EXPECTED_ENTRIES_INVALID'),
      (('expected_entries','DOCKER_CLI'),1,'EXPECTED_ENTRIES_INVALID'),(('expected_entries','DOCKER_CLI'),False,'EXPECTED_ENTRIES_INVALID'),
      (('expected_entries','STATE'),-1,'EXPECTED_ENTRIES_INVALID'),(('expected_entries','STATE'),True,'EXPECTED_ENTRIES_INVALID'),
      (('expected_entries','OTHER'),0,'EXPECTED_ENTRIES_INVALID'),
      (('image_id',),'c3po/backend:production','IMAGE_PLAN_INVALID'),(('retention_reference',),'sha256:'+'fb'*32,'IMAGE_PLAN_INVALID'),
      (('retention_reference',),'massive-supervisor-epoch03','IMAGE_PLAN_INVALID'),
      (('units','service','name'),'other.service','UNITS_INVALID'),(('units','timer','sha256'),'0'*64,'UNITS_INVALID'),
      (('units','timer','bytes'),0,'UNITS_INVALID'),(('units','timer','inode'),0,'UNITS_INVALID'),(('units','other'),{},'UNITS_INVALID'),
      (('units','service','extra'),1,'UNITS_INVALID'),
      (('supervisor_paths','STATE',-1,'mode'),0o750,'SUPERVISOR_PATH_NOT_PRIVATE'),(('supervisor_paths','JOURNAL',-1,'uid'),1000,'CHAIN_ROW_UNSAFE'),
      (('supervisor_paths','CONFIG',-1,'gid'),5,'SUPERVISOR_PATH_NOT_PRIVATE'),
      (('supervisor_paths','CONFIG'),None,'CHAIN_ROW_INVALID'),(('supervisor_paths','EXTRA'),[],'SUPERVISOR_PATHS_INVALID'),
      (('unit_directory',-1,'mode'),0o775,'CHAIN_ROW_UNSAFE'),(('unit_directory',-1,'gid'),5,'UNIT_DIRECTORY_NOT_ROOT'),
      (('unit_directory',),None,'CHAIN_ROW_INVALID'),(('evidence_boot_id_sha256',),'0'*64,'EVIDENCE_BOOT_UNBOUND')]

@pytest.mark.parametrize('path,value,code',PLAN,ids=['.'.join(map(str,row[0]))+'='+repr(row[1])[:20] for row in PLAN])
def test_every_member_of_the_plan_has_its_constant_refusal(path,value,code):
    docs,host=k5.case();_set(path,value)(docs.plan);docs.chain();assert f.refusal(docs.authenticate)==code
    receipt=run(docs,f.Untouchable());assert (receipt['status'],receipt['code'])==('REFUSED',code)

def test_the_shipped_unbound_plan_and_the_fixture_name_exactly_the_plan_keys():
    k=k5.K();m=k.m;docs,host=k5.case()
    assert set(k5.fields(host))==set(m.PLAN_KEYS) and m.SCOPE['daemon_reload_owner'].startswith('OPERATION_5_ACTIVATION_GO')
    unbound=json.loads((k.dir/'REQUEST.UNBOUND.json').read_bytes())['plan']
    assert all(unbound[key] is None for key in m.PLAN_KEYS) and m.ACTIVATION_ALLOWED is True and m.WRITES_ALLOWED is True and m.DATE_CLASS=='WRITE_SESSIONS'
    assert json.loads((k.dir/'GO.UNBOUND.json').read_bytes())['success_criterion'] is None

def test_effects_are_exactly_what_the_signers_see():
    for mode,command,reset,reload in (('ACTIVATE',['enable','--now',k5.TIMER],None,True),('RESET',['reset-failed',k5.SERVICE],78,False)):
        docs,host=k5.case(mode=mode);m=docs.k.m;effects=m.effects_of(docs.plan)
        assert sorted(effects)==sorted(['operation','mode','unit_directory','units','supervisor_paths','expected_entries','image_id','retention_reference',
            'command','reset_failed_only_after_exit_status','invocation_id','forbidden_utc','evidence_boot_id_sha256','activation','daemon_reload',
            'service_started_or_enabled_directly','waits','files_written_by_this_process','containers_started_by_this_process'])
        assert (effects['operation'],effects['mode'],effects['command'],effects['reset_failed_only_after_exit_status'])==('GO_WRITE_HOSTOPS02_SUPERVISOR_ACTIVATE_01',mode,command,reset)
        assert effects['forbidden_utc']=={'days':['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09'],'from':'12:59:00','until':'20:00:00'}
        assert (effects['activation'],effects['daemon_reload'],effects['service_started_or_enabled_directly'],effects['waits'])==(True,reload,False,False)
        assert (effects['files_written_by_this_process'],effects['containers_started_by_this_process'])==(0,0) and effects['units']==docs.plan['units']
        assert effects['expected_entries']=={'JOURNAL':2,'STATE':0,'DOCKER_CLI':0} and effects['image_id']==hostemu.BACKEND and effects['retention_reference']==k5.RETENTION
        assert effects['evidence_boot_id_sha256']==f.BOOT_SHA and effects['unit_directory']['path']==k5.UNITS and effects['unit_directory']['row']==docs.plan['unit_directory'][-1]
        assert sorted(effects['supervisor_paths'])==sorted(k5.PATHS) and all(effects['supervisor_paths'][key]['path']==path for key,path in k5.PATHS.items())
        assert effects['invocation_id']==(None if mode=='ACTIVATE' else '%032x'%0xabc1)
        assert m.success_of(docs.plan)==('TIMER_ENABLED_ACTIVE_RESET_PENDING' if mode=='ACTIVATE' else 'SERVICE_REFUSAL_78_SEEN_RESET_FAILED_VERIFIED')
    assert m.EVIDENCE_OPERATIONS==('GO_READONLY_SUPERVISOR_READBACK_01','GO_WRITE_UNITS_EXCLUSIVE_INSTALL_01')
    assert m.SCOPE['token']=='/etc/c3po-bar/token' and m.SCOPE['supervisor_container']=='c3po-massive' and m.SCOPE['journal_entries']==2

@pytest.mark.parametrize('value',[None,'','%031x'%1,'%032X'%0xabc,'%033x'%1,1])
def test_reset_needs_the_invocation_id_of_one_start(value):
    docs,host=k5.case(mode='RESET');docs.plan['invocation_id']=value;docs.chain();assert f.refusal(docs.authenticate)=='INVOCATION_ID_INVALID'

def test_a_start_after_the_reset_is_a_finding():
    docs,host=k5.case(mode='RESET');host.systemd.after_reset_shows=[{},{'InvocationID':'%032x'%0xbeef}];receipt=run(docs,host)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'SERVICE_STARTED_AGAIN')

def test_activate_readback_carries_the_invocation_id_a_reset_will_bind():
    docs,host=k5.case();receipt=run(docs,host)
    assert receipt['observed']['readback']['service']['InvocationID']==host.systemd.service['InvocationID']!=''
