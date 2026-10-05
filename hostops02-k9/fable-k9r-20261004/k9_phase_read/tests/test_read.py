"""K9R's observations, mode by mode, on the emulated host: every phase decision of RESULT (each reason, each of the
eight result operations, the runner's and the packaged executor's files), the readiness of PROBE (READY, NOT_READY,
every failure of the container and of its line), every finding of POLICY and of TREE, hostile filesystem states,
expiry, budget, and the privacy of the receipt (no secret, no symbol, no payload)."""
from datetime import timedelta
import json

import pytest

import family as f
import hostemu
import k9r

def run(operation='collect_result',host=None,**options):
    docs,fresh=k9r.case(operation,**options);host=host or fresh;before=k9r.state_of(host)
    receipt=docs.run(host);m=docs.k.m
    assert f.sealed(receipt) and host.mutating()==[] and k9r.state_of(host)==before and host.fds=={}
    line=f.line(receipt);assert k9r.CANARY.encode() not in line and hostemu.SECRET.encode() not in line and b'never-emit' not in line
    return m,receipt
def phase(receipt):return receipt['phase_result'],receipt['phase_reason']
def fresh(operation='collect_result',**options):
    k=f.load(k9r.DIRECTORY);return k,k9r.result_world(k,operation,**options)
def item(receipt,label):return receipt['items'][label]

# ---------------------------------------------------------------- RESULT: every collect completes on the files a good step leaves
@pytest.mark.parametrize('operation',[name for name,row in k9r.READ.items() if row[1]=='RESULT'])
def test_every_result_completes_on_the_files_its_step_leaves(operation):
    m,receipt=run(operation)
    assert receipt['status']==m.COMPLETE_STATUS and receipt['outcome']==m.COMPLETE_OUTCOME and phase(receipt)==('COMPLETE',None)
    assert receipt['launch_exit_code']==0 and receipt['commands_started']=={'READ':1,'CONTAINER':0,'EFFECT':0} and receipt['containers_run']==0
    outputs=item(receipt,'outputs');assert outputs['all_equal'] is True and outputs['files']==outputs['files_equal']>0
    assert b'S000' not in f.line(receipt) and b'synthetic' not in f.line(receipt)          # neither a symbol nor a byte of an output

def test_result_reads_its_container_by_id_with_its_own_format_and_nothing_else():
    k,host=fresh();m,receipt=run(host=host)
    commands=[entry['argv'][1:] for entry in host.commands];record=k9r.record
    assert len(commands)==1 and commands[0][:4]==['container','inspect','--format',m.K9_LAUNCHED_FORMAT] and len(commands[0][4])==64
    assert item(receipt,'launch_record')['container_id']==commands[0][4]

def test_counts_are_copied_only_in_their_grammar():
    m,receipt=run('collect_result');assert receipt['counts']=={'registry_symbols':105,'complete_bars':2000,'bar_conflicts':0,'logical_fetch_calls':41}
    m,receipt=run('components_result');assert receipt['counts']=={'daily_61':{'symbol_count':3,'incomplete_count':0},'logical_fetch_calls':12}
    for counts in ({'AAPL':1},{'aapl':1},{'brk':{'symbol_count':1}},{'symbols':1},{'logical_fetch_calls':-1},{'logical_fetch_calls':'1'}):
        k,host=fresh('collect_result',changes={'counts':counts});m,receipt=run(host=host)
        assert phase(receipt)==('UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP') and receipt['counts'] is None and b'AAPL' not in f.line(receipt)
    m,receipt=run('execute_result');assert receipt['counts']=={'READY':2,'COMPLETED_NULL':1}
    host=packaged_world('execute_result',changes={'outputs':{'assessment_manifest':{'path':'manifest.json','sha256':f.sha(b'{"assessment":1}')},
                                                            'output_manifest_sha256':f.sha(b'{"manifest":1}'),'risk_sha256':f.sha(b'{"risk":1}'),'counts':{'AAPL':1}}})
    m,receipt=run('execute_result',host=host);assert phase(receipt)==('UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP') and b'AAPL' not in f.line(receipt)

# ---------------------------------------------------------------- RESULT: each reason of the phase decision
def remove(host,path):host.tree.remove(path)
def test_no_day_directory_no_record_no_container():
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);m,receipt=run(host=host)
    assert phase(receipt)==('UNCERTAIN','DAY_DIRECTORY_ABSENT') and receipt['outcome']==m.MISMATCH_OUTCOME and 'PHASE_RESULT_UNCERTAIN' in receipt['findings']
    assert receipt['commands_started']['READ']==0
    k,host=fresh(with_step=False);remove(host,k9r.day_path('launches','collect_launch.json'));m,receipt=run(host=host)
    assert phase(receipt)==('UNCERTAIN','LAUNCH_RECORD_ABSENT')

@pytest.mark.parametrize('change',[{'attempt_key':'1'*64},{'day':'2026-10-07'},{'operation':'commit_launch'},{'container_name':'c3po-k9-20261006-other'},
                                   {'schema':'K9_LAUNCH_RECORD_V2'},{'started_at':'2026-10-05T21:50:30+00:00'},{'created_at':'2026-10-05T21:29:12+00:00'},
                                   {'container_id':'short'},{'timeout_seconds':0},{'timeout_seconds':7201},{'slot':'BOTH'},{'request_sha256':'0'*64},{'step_plan_sha256':'0'*64},{'extra':1}])
def test_a_launch_record_that_is_not_of_this_step(change):
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);container=k9r.launched(host,'collect_launch');k9r.record(host,'collect_launch',container,**change);k9r.step(host,'collect_launch')
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','LAUNCH_RECORD_INVALID') and 'LAUNCH_RECORD_INVALID' in receipt['findings']
    assert receipt['commands_started']['READ']==0                     # no container is inspected on a record that is not this step's

def test_a_launch_record_that_is_not_json_is_an_observation_that_failed():
    k,host=fresh();host.tree.get(k9r.day_path('launches','collect_launch.json')).content=bytearray(b'not json')
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','OBSERVATION_INCOMPLETE') and item(receipt,'launch_record')['code']=='LAUNCH_RECORD_INVALID'
    assert receipt['outcome']==m.PARTIAL_OUTCOME

def test_an_absent_container_or_a_failed_inspect_is_uncertain():
    k,host=fresh();host.docker.containers=[row for row in host.docker.containers if not row['Name'].startswith('/c3po-k9-')]
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','OBSERVATION_INCOMPLETE')
    assert item(receipt,'launched_container')['code']=='COMMAND_FAILED' and item(receipt,'launched_container')['returncode']==1
    k,host=fresh();host.absent={'docker'};m,receipt=run(host=host);assert item(receipt,'launched_container')['code']=='COMMAND_NOT_STARTED'
    k,host=fresh();host.hang={('container','inspect')};m,receipt=run(host=host);assert item(receipt,'launched_container')['code']=='COMMAND_TIMEOUT'

@pytest.mark.parametrize('labels',[{},{'c3po.k9.attempt_key':'1'*64,'c3po.k9.request_sha256':k9r.REQUEST_OF_THE_LAUNCH},
                                   {'c3po.k9.attempt_key':k9r.attempt_key(k9r.EPOCH,k9r.DAY,'causal_list','collect_launch'),'c3po.k9.request_sha256':'2'*64}])
def test_a_container_without_the_labels_of_this_attempt_is_not_the_recorded_one(labels):
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);container=k9r.launched(host,'collect_launch',labels=labels);k9r.record(host,'collect_launch',container);k9r.step(host,'collect_launch')
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','CONTAINER_NOT_AS_RECORDED') and 'LAUNCHED_CONTAINER_NOT_AS_RECORDED' in receipt['findings']

def test_a_container_of_another_image_or_name_is_not_the_recorded_one():
    k,host=fresh();container=[row for row in host.docker.containers if row['Name'].startswith('/c3po-k9-')][0];container['Image']=hostemu.OTHER
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','CONTAINER_NOT_AS_RECORDED') and item(receipt,'launched_container')['image_equal_signed'] is False
    k,host=fresh();container=[row for row in host.docker.containers if row['Name'].startswith('/c3po-k9-')][0];container['Name']='/c3po-k9-20261006-commit_launch'
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','CONTAINER_NOT_AS_RECORDED') and item(receipt,'launched_container')['name_equal'] is False

@pytest.mark.parametrize('state',['running','created','dead','paused','restarting'])
def test_a_container_that_has_not_exited_is_uncertain(state):
    k,host=fresh(state=state);m,receipt=run(host=host)
    assert phase(receipt)==('UNCERTAIN','CONTAINER_NOT_EXITED') and 'LAUNCHED_CONTAINER_NOT_EXITED' in receipt['findings']

def test_receipt_and_failed_both_present_and_markers_of_another_step():
    k,host=fresh(failed='FAILED');m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','RECEIPT_AND_FAILED_BOTH_PRESENT')
    k,host=fresh(started_changes={'attempt_key':'1'*64});m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','START_MARKER_NOT_OF_THIS_STEP')
    k,host=fresh(started_changes={'started_at':'2026-10-05T22:00:00+00:00'});m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','START_MARKER_NOT_OF_THIS_STEP')
    k,host=fresh(started=False);m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','RECEIPT_WITHOUT_START_MARKER')

@pytest.mark.parametrize('change',[{'step_plan_sha256':'1'*64},{'package_sha256':'1'*64},{'build_sha':'0'*40},{'status':'FAILED'},{'code':'X'},
                                   {'phase':'components'},{'operation':'collect_result'},{'day':'2026-10-07'},{'epoch':'R2D2-V2-SHADOW-2026-09-28'},
                                   {'completed_at':'2026-10-05T21:29:00+00:00'},{'completed_at':'2026-10-05T22:00:00+00:00'},{'schema':'K9_STEP_RECEIPT_V2'},
                                   {'outputs':{'day/../inputs/registry.json':'1'*64}},{'outputs':{'inputs/registry.json':'1'*64}},{'outputs':{'day/inputs/x':'XYZ'}},
                                   {'outputs':{'day/x%d'%index:'1'*64 for index in range(65)}},{'aggregates':{'source/a':{'files':1}}},{'aggregates':[]},
                                   {'extra':1}])
def test_a_receipt_that_is_not_of_this_step(change):
    k,host=fresh(changes=change);m,receipt=run(host=host)
    assert phase(receipt)==('UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP') and item(receipt,'outputs')['applicable'] is False

@pytest.mark.parametrize('exit_code,oom',[(1,False),(137,False),(0,True),(-1,False)])
def test_an_exit_that_contradicts_the_receipt(exit_code,oom):
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);container=k9r.launched(host,'collect_launch',exit_code=exit_code,oom=oom);k9r.record(host,'collect_launch',container);k9r.step(host,'collect_launch')
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','EXIT_CODE_CONTRADICTS_THE_RECEIPT') and receipt['launch_exit_code']==exit_code

def output_path(key):
    root,_,rest=key.partition('/');return (k9r.day_path() if root=='day' else k9r.SOURCE_ROOT)+'/'+rest
@pytest.mark.parametrize('damage',['content','absent','symlink','directory','fifo'])
def test_outputs_read_again_on_the_host(damage):
    k,host=fresh('collect_result');path=output_path('day/inputs/registry.json')
    if damage=='content':host.tree.get(path).content=bytearray(b'{"registry":"changed"}')
    else:
        remove(host,path)
        if damage!='absent':host.tree.add(path,kind={'symlink':'symlink','directory':'dir','fifo':'fifo'}[damage],dev=hostemu.DATA_DEVICE,mode=0o700)
    m,receipt=run(host=host);outputs=item(receipt,'outputs')
    assert phase(receipt)==('UNCERTAIN','OUTPUTS_NOT_AS_THE_RECEIPT_SAYS') and 'OUTPUT_NOT_AS_THE_RECEIPT_SAYS' in receipt['findings']
    assert outputs['files_absent']+outputs['files_different_or_not_regular']==1 and outputs['files_equal']==outputs['files']-1

def test_an_output_below_a_link_is_not_followed():
    k,host=fresh('collect_result');remove(host,k9r.day_path('inputs','registry.json'));remove(host,k9r.day_path('inputs','daily_contract.json'))
    for name in ('registry.receipt.json','daily_contract.receipt.json'):remove(host,k9r.day_path('inputs',name))
    remove(host,k9r.day_path('inputs'));host.tree.add(k9r.day_path('inputs'),kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','OUTPUTS_NOT_AS_THE_RECEIPT_SAYS') and item(receipt,'outputs')['files_different_or_not_regular']==4

@pytest.mark.parametrize('damage',['extra','missing','content','not_regular','symlink'])
def test_an_aggregate_is_every_regular_file_of_its_directory(damage):
    k,host=fresh('components_result');directory=k9r.SOURCE_ROOT+'/components/2026-10-06/daily_61'
    if damage=='extra':k9r.add_file(host,directory+'/F999.json',b'{}')
    if damage=='missing':remove(host,directory+'/F000.json')
    if damage=='content':host.tree.get(directory+'/F001.json').content=bytearray(b'{"c":9}')
    if damage=='not_regular':remove(host,directory+'/F002.json');host.tree.add(directory+'/F002.json',dev=hostemu.DATA_DEVICE,mode=0o700)
    if damage=='symlink':
        for index in range(3):remove(host,directory+'/F%03d.json'%index)
        remove(host,directory);host.tree.add(directory,kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
    m,receipt=run('components_result',host=host);outputs=item(receipt,'outputs')
    assert phase(receipt)==('UNCERTAIN','OUTPUTS_NOT_AS_THE_RECEIPT_SAYS') and outputs['aggregates']==1 and outputs['aggregates_equal']==0

@pytest.mark.parametrize('status,expected',[('FAILED',('FAILED','STEP_REPORTS_FAILED_OR_REFUSED')),('REFUSED',('FAILED','STEP_REPORTS_FAILED_OR_REFUSED')),
                                            ('DEADLINE',('UNCERTAIN','STEP_REPORTS_DEADLINE_OR_UNCERTAIN')),('COMPLETE',('UNCERTAIN','FAILED_RECEIPT_NOT_OF_THIS_STEP'))])
def test_a_step_that_reports_its_failure(status,expected):
    k,host=fresh(receipt=False,failed=status,exit_code=1);m,receipt=run(host=host)
    assert phase(receipt)==expected and receipt['step_receipt_sha256'] is not None
    if expected[0]=='FAILED':assert receipt['findings']==['PHASE_RESULT_FAILED'] and receipt['outcome']==m.MISMATCH_OUTCOME
    assert item(receipt,'step_receipts')['failed_status']==(status if status!='COMPLETE' else None)

def test_markers_without_a_receipt():
    k,host=fresh(receipt=False,exit_code=137);m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','STARTED_WITHOUT_RECEIPT')
    k,host=fresh(receipt=False,started=False,exit_code=0);m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','EXIT_ZERO_WITHOUT_RECEIPT')
    k,host=fresh(receipt=False,started=False,exit_code=2);m,receipt=run(host=host);assert phase(receipt)==('FAILED','EXITED_BEFORE_ITS_START_MARKER')

def test_metadata_of_the_step_files_is_a_finding_that_leaves_the_phase():
    k,host=fresh();host.tree.get(k9r.day_path()).mode=0o755;host.tree.get(k9r.day_path('launches','collect_launch.json')).mode=0o644
    host.tree.get(k9r.day_path('receipts','collect_launch.RECEIPT.json')).mode=0o640
    m,receipt=run(host=host)
    assert phase(receipt)==('UNCERTAIN','FINDINGS_BESIDE_THE_STEP') and receipt['outcome']==m.MISMATCH_OUTCOME   # never COMPLETE beside a finding
    assert {'DAY_DIRECTORY_NOT_PRIVATE','LAUNCH_RECORD_NOT_PRIVATE','STEP_FILE_NOT_PRIVATE'}<=set(receipt['findings'])

def test_a_day_directory_that_is_a_link_is_never_followed():
    k,host=fresh();host.tree.get(k9r.PLACEMENT['days']).children.pop(k9r.DAY)
    host.tree.add(k9r.day_path(),kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
    m,receipt=run(host=host);assert item(receipt,'day_directory')['code']=='SYMLINK_COMPONENT' and phase(receipt)==('UNCERTAIN','OBSERVATION_INCOMPLETE')

def test_signed_rows_of_days_that_differ_are_a_finding_and_nothing_below_is_read():
    docs,host=k9r.case('collect_result');docs.plan['parent_rows']['days']['rows'][-1]['inode']+=1;docs.chain();receipt=docs.run(host)
    assert 'PARENT_IDENTITY_MISMATCH' in receipt['findings'] and item(receipt,'day_directory')['code']=='DIRECTORY_NOT_HELD'
    assert item(receipt,'directory:DAYS')['fields_that_differ']=={'device':False,'inode':True,'uid':False,'gid':False,'mode':False}
    assert receipt['phase_result']=='UNCERTAIN'

def test_another_boot_is_a_finding_and_devices_are_not_compared():
    docs,host=k9r.case('collect_result');docs.plan['evidence_boot_id_sha256']='7'*64
    for name in k9r.CHAINS:
        for row in docs.plan['parent_rows'][name]['rows']:row['device']+=1000
    docs.chain();receipt=docs.run(host)
    assert receipt['findings']==['EVIDENCE_FROM_EARLIER_BOOT','PHASE_RESULT_UNCERTAIN'] and phase(receipt)==('UNCERTAIN','FINDINGS_BESIDE_THE_STEP')

def test_expiry_stops_the_run_and_the_phase_is_uncertain():
    docs,host=k9r.case('collect_result');now=docs.now;wall=[now]
    def hook(host,name,detail,calls):
        if name=='run':wall[0]=now+timedelta(minutes=6)
    host.hook=hook;receipt=docs.run(host,clock=lambda:wall[0])
    assert (receipt['status'],receipt['code'],receipt['phase_result'],receipt['phase_reason'])==(docs.k.m.PARTIAL_STATUS,'GO_EXPIRED','UNCERTAIN','RUN_STOPPED')

# ---------------------------------------------------------------- RESULT: the packaged risk CLI's own files
def packaged_world(operation='acquire_result',**options):
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);launch=k9r.READ[operation][2];container=k9r.launched(host,launch,exit_code=options.pop('exit_code',0))
    k9r.record(host,launch,container);k9r.packaged(host,launch,**options);return host

def test_the_packaged_receipt_names_its_namespace_form():
    m,receipt=run('acquire_result');assert item(receipt,'step_receipts')['namespace_form']=='DIAG_R4'
    host=packaged_world(namespace='R2D2-V2-SHADOW-2026-10-06');m,receipt=run('acquire_result',host=host)
    assert phase(receipt)==('COMPLETE',None) and item(receipt,'step_receipts')['namespace_form']=='SHADOW'
    host=packaged_world(namespace='R2D2-V2-SHADOW-2026-10-05');m,receipt=run('acquire_result',host=host)
    assert phase(receipt)==('UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP')

@pytest.mark.parametrize('change',[{'session_date':'2026-10-07'},{'status':'UNCERTAIN'},{'operation_activation':True},{'certification_granted':True},
                                   {'go_sha256':'1'*64},{'manifest_sha256':'1'*64},{'phase':'execute'},{'schema':'X'},{'extra':1},{'outputs':[]},{'completed_at':'2026-10-06T02:00:00+00:00'}])
def test_a_packaged_receipt_that_is_not_of_this_step(change):
    host=packaged_world(changes=change);m,receipt=run('acquire_result',host=host);assert phase(receipt)==('UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP')

def test_packaged_failures_and_a_changed_plan():
    host=packaged_world(receipt=False,failed='REFUSED',exit_code=2);m,receipt=run('acquire_result',host=host);assert phase(receipt)==('FAILED','STEP_REPORTS_FAILED_OR_REFUSED')
    host=packaged_world(receipt=False,failed='UNCERTAIN',exit_code=3);m,receipt=run('acquire_result',host=host);assert phase(receipt)==('UNCERTAIN','STEP_REPORTS_DEADLINE_OR_UNCERTAIN')
    host=packaged_world();host.tree.get(k9r.day_path('risk','plan','HOST_PLAN.json')).content=bytearray(b'{"changed":1}')
    m,receipt=run('acquire_result',host=host);assert phase(receipt)==('UNCERTAIN','EXIT_ZERO_WITHOUT_RECEIPT')     # another manifest: another spool
    host=packaged_world();host.tree.get(k9r.day_path('risk','plan','GO.json')).content=bytearray(b'{"changed":1}')
    m,receipt=run('acquire_result',host=host);assert phase(receipt)==('UNCERTAIN','START_MARKER_NOT_OF_THIS_STEP')
    host=packaged_world();remove(host,k9r.day_path('risk','plan','GO.json'))
    m,receipt=run('acquire_result',host=host);assert item(receipt,'step_receipts')['go_present'] is False and phase(receipt)==('UNCERTAIN','EXIT_ZERO_WITHOUT_RECEIPT')

@pytest.mark.parametrize('operation,path',[('acquire_result',('acquired','acquired.json')),('execute_result',('assessment','manifest.json')),
                                           ('execute_result',('risk-output','MANIFEST.json')),('execute_result',('risk-output','risk.json'))])
def test_packaged_outputs_read_again(operation,path):
    host=packaged_world(operation);host.tree.get(k9r.spool(*path)).content=bytearray(b'{"changed":1}')
    m,receipt=run(operation,host=host);assert phase(receipt)==('UNCERTAIN','OUTPUTS_NOT_AS_THE_RECEIPT_SAYS')

def test_a_packaged_reference_that_leaves_its_directory_is_refused():
    host=packaged_world('execute_result',changes={'outputs':{'assessment_manifest':{'path':'../x','sha256':'1'*64},'output_manifest_sha256':'1'*64,'risk_sha256':'1'*64}})
    m,receipt=run('execute_result',host=host);assert item(receipt,'outputs')['code']=='OUTPUT_REFERENCE_INVALID' and receipt['phase_result']=='UNCERTAIN'

# ---------------------------------------------------------------- PROBE
def probe_host(**knobs):
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);registry,bulk=k9r.provider_rows(**{key:knobs.pop(key) for key in ('eligible','present','conflicts','stale','unusable') if key in knobs})
    values=dict(registry=registry,bulk=bulk,token=k9r.CANARY,expect_date='2026-10-05');values.update(knobs)
    host.docker.on_run=k9r.ProbeContainer(k9r.fake_tree(**values));return host

def test_probe_ready_argv_environment_and_nothing_secret():
    host=probe_host();m,receipt=run('readiness_probe',host=host);probe=item(receipt,'probe')
    assert receipt['readiness']=='READY' and receipt['outcome']==m.K9_PROBE_OUTCOME and probe['present_eligible_symbols']==3840 and probe['required_minimum']==3800
    assert probe['registry_symbols']==4005 and probe['eligible_symbols']==4000 and probe['logical_fetch_calls']==2 and probe['previous_session']=='2026-10-05'
    runs=host.container_runs();assert len(runs)==1;argv=runs[0]['argv']
    prefix=['run','--rm','-i','--pull','never','--init','--user','0:0','--network','bridge','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
            '--memory','2g','--pids-limit','256','--env-file','/var/lib/c3po/r2d2-v2-k9-20261005/secrets/provider.env','--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true']
    assert argv[1:]==prefix+['--name','c3po-k9-20261006-readiness_probe',hostemu.BACKEND,'timeout','-s','KILL','36','python','-I','-B','-','2026-10-06',receipt['request_sha256']]
    assert runs[0]['stdin']==m.K9_PROBE_SNIPPET.encode('ascii') and runs[0]['seconds']==40 and runs[0]['variables']=={} and runs[0]['docker_config'] is None
    call=host.docker.runs[0];assert call.container_environment['C3PO_EODHD_API_TOKEN']==k9r.CANARY and call.container_environment['C3PO_R2D2_V2_PRODUCERS_ENABLED']=='true'
    assert not any(k9r.CANARY in word for entry in host.commands for word in entry['argv'])
    assert not any(entry[0]=='read' and 'secrets' in entry[1] for entry in host.log)            # the env file is the CLI's to read, never this run's
    assert [entry['argv'][1:3] for entry in host.commands]==[['image','inspect'],['run','--rm']]   # the image first, then the container

@pytest.mark.parametrize('present,ready',[(3800,True),(3799,False),(4000,True),(0,False)])
def test_probe_applies_95_of_100(present,ready):
    host=probe_host(present=present);m,receipt=run('readiness_probe',host=host)
    assert receipt['readiness']==('READY' if ready else 'NOT_READY') and (receipt['outcome']==m.K9_PROBE_OUTCOME)==ready
    if not ready:assert receipt['findings']==['PROVIDER_NOT_READY'] and receipt['status']==m.PARTIAL_STATUS and receipt['code']=='PROVIDER_NOT_READY'

def test_probe_with_no_eligible_name_is_not_ready_and_conflicts_are_diagnostics():
    host=probe_host(eligible=0,present=0);m,receipt=run('readiness_probe',host=host);assert receipt['readiness']=='NOT_READY'
    host=probe_host(eligible=3999,present=3999);m,receipt=run('readiness_probe',host=host)    # every name present, too few names: degenerate
    assert receipt['readiness']=='NOT_READY' and item(receipt,'probe')['present_eligible_symbols']==3999
    host=probe_host(eligible=100,present=100);m,receipt=run('readiness_probe',host=host);assert receipt['readiness']=='NOT_READY'
    host=probe_host(conflicts=3);m,receipt=run('readiness_probe',host=host);probe=item(receipt,'probe')
    assert receipt['readiness']=='READY' and probe['conflicting_eligible_symbols']==3 and probe['usable_eligible_symbols']==3837

@pytest.mark.parametrize('knobs,code',[({'fail_path':'/api/exchange-symbol-list/US'},'PROVIDER_REQUEST_FAILED'),({'fail_path':'/api/eod-bulk-last-day/US'},'PROVIDER_REQUEST_FAILED'),
                                       ({'package':'1'*64},'PACKAGE_NOT_THE_CERTIFIED_ONE'),({'import_error':True},'ImportError'),
                                       ({'settings_error':True},'RuntimeError'),({'token':'another'},'TOKEN_NOT_THE_ENV_FILE_ONE'),
                                       ({'bulk':'{"not":"a list"}'},'BULK_INVALID'),({'registry':[]},'REGISTRY_EMPTY'),
                                       ({'expect_date':'2026-10-02'},'BULK_DATE_NOT_THE_PREVIOUS_SESSION')])
def test_probe_snippet_failures_are_codes(knobs,code):
    host=probe_host(**knobs);m,receipt=run('readiness_probe',host=host);probe=item(receipt,'probe')
    assert probe['findings']==['PROBE_SNIPPET_FAILED'] and probe['snippet_code']==code and receipt['readiness']=='UNKNOWN' and probe['returncode']==1

def test_probe_refuses_before_the_close_of_the_previous_session():
    host=probe_host();host.docker.on_run=k9r.ProbeContainer(host.docker.on_run.tree,now='2026-10-05T19:59:59+00:00')
    m,receipt=run('readiness_probe',host=host);assert item(receipt,'probe')['snippet_code']=='PREVIOUS_SESSION_NOT_CLOSED'
    assert item(receipt,'probe')['logical_fetch_calls']==0

def test_probe_engine_failure_and_an_image_that_is_not_there():
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);docs,_=k9r.case('readiness_probe',constant=k9r.constants(image_id='sha256:'+'ee'*32))
    receipt=docs.run(host);assert item(receipt,'probe')['code']=='PROBE_NOT_STARTED_IMAGE_NOT_AS_SIGNED' and host.container_runs()==[]
    assert item(receipt,'image')['code']=='COMMAND_FAILED' and receipt['readiness']=='UNKNOWN' and receipt['status']==docs.k.m.PARTIAL_STATUS
    docs,host=k9r.case('readiness_probe');host.docker.on_run=lambda call:(125,b'');receipt=docs.run(host)
    assert item(receipt,'probe')['findings']==['PROBE_ENGINE_FAILURE'] and item(receipt,'probe')['returncode']==125 and receipt['readiness']=='UNKNOWN'

@pytest.mark.parametrize('damage',['absent','mode','owner','symlink','links'])
def test_probe_is_not_started_unless_the_env_file_is_roots_and_private(damage):
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);path=k9r.PLACEMENT['provider_env_file'];node=host.tree.get(path)
    if damage=='absent':remove(host,path)
    if damage=='mode':node.mode=0o644
    if damage=='owner':node.uid=1000
    if damage=='symlink':remove(host,path);host.tree.add(path,kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
    if damage=='links':node.nlink=2
    m,receipt=run('readiness_probe',host=host)
    assert item(receipt,'probe')['code']=='PROBE_NOT_STARTED_ENV_FILE_NOT_AS_REQUIRED' and host.container_runs()==[] and receipt['readiness']=='UNKNOWN'
    assert ('SECRET_FILE_ABSENT' if damage=='absent' else 'SECRET_FILE_NOT_PRIVATE') in receipt['findings']

def test_probe_is_not_started_when_the_secrets_directory_is_not_the_signed_one():
    docs,host=k9r.case('readiness_probe');docs.plan['parent_rows']['secrets']['rows'][-1]['inode']+=1;docs.chain();receipt=docs.run(host)
    assert 'PARENT_IDENTITY_MISMATCH' in receipt['findings'] and host.container_runs()==[] and item(receipt,'probe')['status']=='UNAVAILABLE'

def test_probe_timeout_and_budget():
    host=probe_host();host.hang={('run','--rm')};m,receipt=run('readiness_probe',host=host);probe=item(receipt,'probe')
    assert probe['code']=='COMMAND_TIMEOUT' and probe['container_may_still_exist'] is True and receipt['readiness']=='UNKNOWN'
    docs,host=k9r.case('readiness_probe');clock=f.Budget(docs.now).attach(host)
    def hook(host,name,detail,calls,previous=host.hook):
        if name=='lstat' and detail and str(detail[0]).endswith('provider.env'):clock.elapsed+=17
        previous(host,name,detail,calls)
    host.hook=hook;receipt=docs.run(host,**clock.options())
    assert item(receipt,'probe')['code']=='COMMAND_NOT_STARTED_BUDGET' and host.container_runs()==[] and item(receipt,'probe')['container_may_still_exist'] is False

BAD_LINES=[b'',b'garbage\n',b'{"status":"DONE"}\n',b'{}\n{}\n']
def done_line(**changes):
    line={'status':'DONE','readiness':'READY','day':'2026-10-06','previous_session':'2026-10-05','registry_symbols':4005,'eligible_symbols':4000,
          'present_eligible_symbols':3840,'required_minimum':3800,'usable_eligible_symbols':3840,'conflicting_eligible_symbols':0,'duplicate_eligible_rows':0,
          'bulk_rows':3841,'dated_rows':3841,'logical_fetch_calls':2,'registry_payload_sha256':'1'*64,'bulk_payload_sha256':'2'*64,'request_sha256':None,'python':'3.12.13'}
    line.update(changes);return line
HOSTILE=[{'readiness':'NOT_READY'},{'required_minimum':3801},{'present_eligible_symbols':4001},{'usable_eligible_symbols':3841},{'logical_fetch_calls':3},
         {'registry_symbols':105,'eligible_symbols':100,'present_eligible_symbols':96,'required_minimum':95,'usable_eligible_symbols':96,'bulk_rows':97,'dated_rows':97},
         {'day':'2026-10-07'},{'previous_session':'2026-10-06'},{'previous_session':'2026-09-01'},{'registry_symbols':-1},{'bulk_rows':True},
         {'registry_payload_sha256':'XYZ'},{'python':'3.12.13 (main)'},{'duplicate_eligible_rows':-1},{'duplicate_eligible_rows':1.5},{'symbols':['S000']},{'request_sha256':'0'*64},{'dated_rows':3842}]
@pytest.mark.parametrize('index',range(len(BAD_LINES)+len(HOSTILE)))
def test_probe_line_member_by_member(index):
    docs,host=k9r.case('readiness_probe')
    def answer(call):
        if index<len(BAD_LINES):return 0,BAD_LINES[index]
        line=done_line(request_sha256=call.command[-1]);line.update(HOSTILE[index-len(BAD_LINES)])
        return 0,json.dumps(line).encode()+b'\n'
    host.docker.on_run=answer;receipt=docs.run(host)
    assert item(receipt,'probe')['code']=='PROBE_OUTPUT_INVALID' and receipt['readiness']=='UNKNOWN' and receipt['outcome']==docs.k.m.PARTIAL_OUTCOME
    assert b'S000' not in f.line(receipt)

def test_a_probe_that_failed_with_a_message_or_nothing_is_a_failed_run():
    for code,out in ((1,b'{"status":"FAILED","code":"a message /x","logical_fetch_calls":0,"request_sha256":null}\n'),(137,b''),(1,b'Traceback\n'),
                     (1,b'{"status":"FAILED","code":"PROVIDER_REQUEST_FAILED","logical_fetch_calls":3,"request_sha256":null}\n')):
        docs,host=k9r.case('readiness_probe');host.docker.on_run=lambda call,code=code,out=out:(code,out);receipt=docs.run(host)
        assert item(receipt,'probe')['findings']==['PROBE_RUN_FAILED'] and b'a message' not in f.line(receipt)
    docs,host=k9r.case('readiness_probe');host.docker.on_run=lambda call:(126,b'');receipt=docs.run(host)
    assert item(receipt,'probe')['findings']==['PROBE_ENGINE_FAILURE']

def test_a_recheck_is_the_same_probe_under_its_own_name():
    m,receipt=run('readiness_recheck');assert receipt['readiness']=='READY' and item(receipt,'probe')['container_name']=='c3po-k9-20261006-readiness_recheck'

# ---------------------------------------------------------------- POLICY
def policy_receipt(change=None,constant=None):
    k=f.load(k9r.DIRECTORY);host=k9r.policy_world(k)
    if change:change(host)
    docs,_=k9r.case('policy_read',constant=constant);receipt=docs.run(host)
    assert f.sealed(receipt) and k9r.CANARY.encode() not in f.line(receipt) and host.fds=={} and host.mutating()==[];return docs.k.m,receipt

def test_policy_complete_reads_two_files_and_two_docker_reads_of_the_worker():
    m,receipt=policy_receipt();assert receipt['outcome']==m.K9_POLICY_OUTCOME
    assert item(receipt,'worker_environment')['live_names_equal']==4 and item(receipt,'policy_file')['inside_its_window'] is True

@pytest.mark.parametrize('change,finding',[
    (lambda host:k9r.remove(host,k9r.POLICY_DIRECTORY+'/policy.json') if hasattr(k9r,'remove') else host.tree.remove(k9r.POLICY_DIRECTORY+'/policy.json'),'POLICY_FILE_ABSENT'),
    (lambda host:setattr(host.tree.get(k9r.POLICY_DIRECTORY+'/policy.json'),'mode',0o644),'POLICY_FILE_NOT_PRIVATE'),
    (lambda host:setattr(host.tree.get(k9r.POLICY_DIRECTORY+'/policy.json'),'content',bytearray(k9r.POLICY+b'\n')),'POLICY_SHA_NOT_THE_SIGNED_ONE'),
    (lambda host:host.tree.remove(k9r.RELEASE_DIRECTORY+'/release.CERTIFIED.json'),'RELEASE_FILE_ABSENT'),
    (lambda host:setattr(host.tree.get(k9r.RELEASE_DIRECTORY+'/release.CERTIFIED.json'),'uid',1000),'RELEASE_FILE_NOT_PRIVATE'),
    (lambda host:setattr(host.tree.get(k9r.RELEASE_DIRECTORY+'/release.CERTIFIED.json'),'content',bytearray(b'{}')),'RELEASE_SHA_NOT_THE_SIGNED_ONE'),
    (lambda host:host.docker.container(hostemu.WORKER)['State'].update(Running=False,Status='exited'),'WORKER_NOT_RUNNING'),
    (lambda host:host.docker.container(hostemu.WORKER).update(Image=hostemu.OTHER),'WORKER_IMAGE_NOT_THE_SIGNED_ONE'),
    (lambda host:host.docker.container(hostemu.WORKER)['Config'].update(Env=[item for item in host.docker.container(hostemu.WORKER)['Config']['Env'] if 'LIVE_POLICY_SHA' not in item]),'WORKER_LIVE_NAMES_NOT_AS_SIGNED'),
    (lambda host:host.docker.container(hostemu.WORKER)['Config']['Env'].__setitem__(-1,'C3PO_R2D2_V2_SHADOW_RELEASE_SHA='+'0'*64),'WORKER_LIVE_NAMES_NOT_AS_SIGNED'),
    (lambda host:host.docker.container(hostemu.WORKER)['Config'].update(Env=[('C3PO_BUILD_SHA='+'0'*40 if item.startswith('C3PO_BUILD_SHA=') else item) for item in host.docker.container(hostemu.WORKER)['Config']['Env']]),'WORKER_BUILD_REVISION_MISMATCH')])
def test_policy_findings(change,finding):
    m,receipt=policy_receipt(change);assert finding in receipt['findings'] and receipt['outcome']==m.MISMATCH_OUTCOME

def test_policy_window_is_judged_at_the_instant_of_the_read():
    expired=f.canonical({'schema':'R2D2_V2_LIVE_POLICY_V1','valid_from':'2026-10-02T00:00:00+00:00','valid_until':'2026-10-06T12:00:00+00:00'})
    def change(host):
        host.tree.get(k9r.POLICY_DIRECTORY+'/policy.json').content=bytearray(expired);worker=host.docker.container(hostemu.WORKER)['Config']['Env']
        worker[:]=[('C3PO_R2D2_V2_LIVE_POLICY_SHA='+f.sha(expired) if entry.startswith('C3PO_R2D2_V2_LIVE_POLICY_SHA=') else entry) for entry in worker]
    m,receipt=policy_receipt(change,k9r.constants(policy_sha256=f.sha(expired)))
    assert receipt['findings']==['POLICY_OUTSIDE_ITS_WINDOW'] and item(receipt,'policy_file')['bytes_equal_signed'] is True
    unreadable=f.canonical({'schema':'R2D2_V2_LIVE_POLICY_V1','valid_from':'yesterday'})
    def change(host):
        host.tree.get(k9r.POLICY_DIRECTORY+'/policy.json').content=bytearray(unreadable);worker=host.docker.container(hostemu.WORKER)['Config']['Env']
        worker[:]=[('C3PO_R2D2_V2_LIVE_POLICY_SHA='+f.sha(unreadable) if entry.startswith('C3PO_R2D2_V2_LIVE_POLICY_SHA=') else entry) for entry in worker]
    m,receipt=policy_receipt(change,k9r.constants(policy_sha256=f.sha(unreadable)));assert receipt['findings']==['POLICY_WINDOW_UNREADABLE']

def test_policy_values_compared_travel_in_the_argv_and_are_not_secrets():
    k=f.load(k9r.DIRECTORY);host=k9r.policy_world(k);docs,_=k9r.case('policy_read');docs.run(host)
    words=' '.join(word for entry in host.commands for word in entry['argv'])
    assert f.sha(k9r.POLICY) in words and k9r.CANARY not in words and hostemu.SECRET not in words

# ---------------------------------------------------------------- TREE
def tree_receipt(change=None,constant=None):
    k=f.load(k9r.DIRECTORY);host=k9r.world(k)
    if change:change(host)
    docs,_=k9r.case('TREE',constant=constant);receipt=docs.run(host)
    assert f.sealed(receipt) and host.fds=={} and host.mutating()==[] and host.commands==[];line=f.line(receipt)
    assert k9r.CANARY.encode() not in line and b'reader:' not in line
    assert not any(entry[0]=='read' and ('secrets' in entry[1]) for entry in host.log)        # a secret file is never opened
    return docs.k.m,receipt,host

def test_tree_reports_the_boot_and_the_rows_a_binder_copies():
    m,receipt,host=tree_receipt();assert receipt['outcome']==m.K9_TREE_OUTCOME and receipt['boot_id_sha256']==f.BOOT_SHA
    for key,name in (('DAYS','days'),('SOURCE_ROOT','source_root'),('SECRETS','secrets'),('TOOLS','tools'),('CLAIMS','claims')):
        assert item(receipt,'directory:'+key)['observed_rows']==hostemu.rows(host,k9r.PLACEMENT[name])
    assert item(receipt,'secret:SECRETS/provider.env')=={'elapsed_ms':0,'exists':True,'findings':[],'links':1,'matches':True,'mode_octal':'0600','name':'provider.env',
                                                          'owner_gid':0,'owner_uid':0,'private':True,'status':'COMPLETE','type':'file'}

def test_tree_rows_are_what_the_week_signs():
    """The binder's step: the rows and the boot of a TREE receipt make the parent_rows of a K9 request that authenticates."""
    m,receipt,host=tree_receipt();docs,_=k9r.case('collect_result')
    docs.plan['parent_rows']={name:{'path':k9r.PLACEMENT[name],'rows':item(receipt,'directory:'+key)['observed_rows'],'open_root':k9r.open_root(name)}
                              for key,name in (('DAYS','days'),('SOURCE_ROOT','source_root'),('SECRETS','secrets'),('TOOLS','tools'),('CLAIMS','claims'))}
    docs.plan['evidence_boot_id_sha256']=receipt['boot_id_sha256'];docs.chain();docs.authenticate()

@pytest.mark.parametrize('name',['k9_root','days','tools','claims','secrets','emitter','source_root'])
def test_tree_every_directory_is_roots_and_private(name):
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(k9r.PLACEMENT[name]),'mode',0o750))
    assert 'DIRECTORY_NOT_ROOT_PRIVATE' in receipt['findings'] and receipt['outcome']==m.MISMATCH_OUTCOME

def test_tree_absent_directory_and_files():
    m,receipt,host=tree_receipt(lambda host:host.tree.remove(k9r.PLACEMENT['emitter']))
    assert 'PARENT_MISSING' in receipt['findings'] and item(receipt,'secret:EMITTER/password')['code']=='DIRECTORY_NOT_HELD'
    m,receipt,host=tree_receipt(lambda host:host.tree.remove(k9r.PLACEMENT['risk_db_env_file']));assert receipt['findings']==['SECRET_FILE_ABSENT']
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(k9r.PLACEMENT['emitter_password']),'gid',1000));assert receipt['findings']==['SECRET_FILE_NOT_PRIVATE']

def test_tree_runner_file():
    path=k9r.PLACEMENT['tools']+'/k9_runner-'+f.sha(k9r.RUNNER)+'.py'
    m,receipt,host=tree_receipt(lambda host:host.tree.remove(path));assert receipt['findings']==['RUNNER_FILE_ABSENT']
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(path),'content',bytearray(b'other')));assert receipt['findings']==['RUNNER_BYTES_NOT_THE_SIGNED_ONES']
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(path),'mode',0o644));assert receipt['findings']==['RUNNER_FILE_NOT_PRIVATE']

def test_tree_floor_mount_point_and_acceptable_rows():
    import types
    def shrink(blocks):
        def apply(host):
            old=host.vfs[hostemu.ROOT_DEVICE];host.vfs[hostemu.ROOT_DEVICE]=types.SimpleNamespace(f_frsize=4096,f_blocks=old.f_blocks,f_bfree=old.f_blocks,f_bavail=blocks)
        return apply
    m,receipt,host=tree_receipt(shrink(52428800-1))                # one block short of 200 GiB available; f_bfree far above it
    fs=item(receipt,'k9_filesystem')
    assert receipt['findings']==['DISK_FREE_BELOW_FLOOR'] and fs['hold'] is True and fs['days_bytes_available']==214748364800-4096 and fs['floor_bytes']==214748364800
    assert fs['source_root_on_the_filesystem_of_days'] is True and 'source_root_bytes_available' not in fs and fs['filesystem_type']=='NOT_EXPOSED_BY_THE_CORE'
    m,receipt,host=tree_receipt(shrink(52428800));assert receipt['findings']==[] and item(receipt,'k9_filesystem')['hold'] is False
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(k9r.PLACEMENT['days']),'dev',hostemu.DATA_DEVICE))
    assert item(receipt,'k9_filesystem')['days_bytes_available']==13200816*4096 and 'DISK_FREE_BELOW_FLOOR' in receipt['findings']   # days/ itself, not k9_root
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(k9r.DATA),'dev',hostemu.ROOT_DEVICE))
    assert receipt['findings']==['DATA_VOLUME_NOT_A_MOUNT_POINT','SEPTEMBER_SOURCE_ON_ANOTHER_DEVICE'] and item(receipt,'directory:SOURCE_ROOT')['mount_point_by_device_change']=='/'
    assert item(receipt,'directory:DAYS')['mount_point_by_device_change']=='/'
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get('/mnt'),'uid',1000));assert receipt['findings']==['DATA_VOLUME_ROWS_NOT_ACCEPTABLE']   # only the September read crosses /mnt
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(k9r.DATA),'mode',0o777));assert receipt['findings']==['DATA_VOLUME_ROWS_NOT_ACCEPTABLE']
    assert item(receipt,'directory:DAYS')['rows_acceptable_to_the_k9_requests'] is True     # the K9 chain does not cross the data volume

# ---------------------------------------------------------------- N-8: the K9 tree under a chain controlled by root alone
@pytest.mark.parametrize('path,change',[('/var/lib/c3po',{'uid':1000}),('/var/lib',{'mode':0o775}),('/var',{'mode':0o757}),
                                        ('/var/lib/c3po',{'mode':0o1777}),(k9r.K9_ROOT,{'uid':1000})])
def test_tree_every_ancestor_of_the_k9_tree_is_roots_and_closed(path,change):
    def apply(host):
        for key,value in change.items():setattr(host.tree.get(path),key,value)
    m,receipt,host=tree_receipt(apply)
    assert 'ROWS_NOT_ACCEPTABLE_TO_THE_K9_REQUESTS' in receipt['findings']
    keys=('K9_ROOT','DAYS','TOOLS','CLAIMS','SECRETS','EMITTER')+(('SOURCE_ROOT',) if path!=k9r.K9_ROOT else ())   # decision 6: the same chain
    for key in keys:
        found=item(receipt,'directory:'+key);assert found['rows_acceptable_to_the_k9_requests'] is False and path in found['components_not_root_controlled']

def test_tree_k9_chain_and_the_source_root_have_no_open_root():
    m,receipt,host=tree_receipt()
    assert item(receipt,'directory:DAYS')['open_root'] is None and item(receipt,'directory:SOURCE_ROOT')['open_root'] is None
    assert [row['path'] for row in item(receipt,'directory:SOURCE_ROOT')['observed_rows']]==['/','/var','/var/lib','/var/lib/c3po',k9r.SOURCE_ROOT]
    assert [row['path'] for row in item(receipt,'directory:K9_ROOT')['observed_rows']]==['/','/var','/var/lib','/var/lib/c3po',k9r.K9_ROOT]
    assert item(receipt,'directory:K9_ROOT')['components_not_root_controlled']==[] and item(receipt,'directory:SOURCE_ROOT')['components_not_root_controlled']==[]

def test_tree_missing_parent_of_the_k9_root_is_never_presumed():
    def change(host):
        lib=host.tree.get('/var/lib');lib.children.pop('c3po')
    m,receipt,host=tree_receipt(change)
    assert {'PARENT_MISSING'}<=set(receipt['findings']) and item(receipt,'k9_filesystem')['code']=='DIRECTORY_NOT_HELD'

def test_tree_k9_filesystem_one_device_not_the_data_volume():
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(k9r.PLACEMENT['days']),'dev',hostemu.DATA_DEVICE))
    assert 'K9_TREE_SPANS_FILESYSTEMS' in receipt['findings'] and item(receipt,'k9_filesystem')['directories_on_another_device']==['DAYS']
    def move(host):
        for path in (k9r.K9_ROOT,)+tuple(k9r.PLACEMENT[name] for name in ('days','tools','claims','secrets','emitter')):host.tree.get(path).dev=hostemu.DATA_DEVICE
    m,receipt,host=tree_receipt(move)
    assert 'SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS' in receipt['findings'] and item(receipt,'k9_filesystem')['days_inodes_available'] is None
    m,receipt,host=tree_receipt(lambda host:setattr(host.tree.get(k9r.SOURCE_ROOT),'dev',hostemu.DATA_DEVICE))
    assert receipt['findings']==['SOURCE_ROOT_NOT_ON_THE_FILESYSTEM_OF_DAYS'] and item(receipt,'k9_filesystem')['source_root_on_the_filesystem_of_days'] is False

def test_requests_refuse_k9_rows_with_an_open_root_or_an_operational_owner():
    docs,host=k9r.case('collect_result');docs.plan['parent_rows']['days']['rows'][3]['uid']=1000;docs.chain()
    assert f.refusal(docs.authenticate)=='CHAIN_ROW_UNSAFE'
    docs,host=k9r.case('collect_result');docs.plan['parent_rows']['secrets']['rows'][2]['mode']=0o775;docs.chain()
    assert f.refusal(docs.authenticate)=='CHAIN_ROW_UNSAFE'
    docs,host=k9r.case('collect_result');docs.plan['parent_rows']['source_root']['rows'][2]['uid']=1000;docs.chain()
    assert f.refusal(docs.authenticate)=='CHAIN_ROW_UNSAFE'                    # decision 6: the source root has no open root either

def test_a_source_root_that_diverges_from_its_signed_rows_is_never_used():
    k,host=fresh('publish_result');docs,_=k9r.case('publish_result');docs.plan['parent_rows']['source_root']['rows'][-1]['inode']+=1;docs.chain()
    receipt=docs.run(host)
    assert 'PARENT_IDENTITY_MISMATCH' in receipt['findings'] and item(receipt,'outputs')['code']=='DIRECTORY_NOT_HELD' and receipt['phase_result']=='UNCERTAIN'
    k,host=fresh('publish_result');docs,_=k9r.case('publish_result');done=[False]
    def hook(host,name,detail,calls):
        if name=='open' and str(detail[0]).endswith('/control') and not done[0]:done[0]=True;replace_directory(host,k9r.SOURCE_ROOT)
    host.hook=hook;receipt=docs.run(host)
    assert item(receipt,'outputs')['code']=='PARENT_REPLACED' and receipt['phase_result']=='UNCERTAIN'

def test_tree_link_in_the_chain_is_never_followed():
    def change(host):
        host.tree.get('/var/lib/c3po').children.pop('r2d2-v2-source-20261005')
        host.tree.add(k9r.SOURCE_ROOT,kind='symlink',mode=0o777)
    m,receipt,host=tree_receipt(change);assert item(receipt,'directory:SOURCE_ROOT')['findings']==['SYMLINK_COMPONENT']

# ---------------------------------------------------------------- reductions
def test_a_reduced_receipt_is_never_the_success_of_its_mode():
    m=f.load(k9r.DIRECTORY).m
    for step in (m._drop_rows,m._reduce_items):
        receipt={'expectations_met':True,'code':None,'items':{'directory:DAYS':{'status':'COMPLETE','observed_rows':[{}],'findings':[],'matches':True}}}
        step(receipt);assert receipt['expectations_met'] is False and receipt['code']=='RECEIPT_REDUCED_FOR_SIZE'
    docs,host=k9r.case('TREE');receipt=docs.run(host);big=dict(receipt);assert receipt['size_reductions']==[]

# ---------------------------------------------------------------- RESULT: what the inspect prints, member by member
INSPECT_CHANGES=[{'extra':1},{'id':'cd'*32},{'exit_code':'0'},{'exit_code':256},{'exit_code':True},{'attempt_key':'zz'},{'request_sha256':'Z'*64},
                 {'name':'no-slash'},{'image_id':'c3po/backend:production'},{'state':'gone'},{'running':'false'},{'oom_killed':None},{'finished_at':'x'*65}]
@pytest.mark.parametrize('change',INSPECT_CHANGES)
def test_the_inspect_line_member_by_member(change):
    k,host=fresh();docker=host.docker;real=type(docker).run
    def run(self,args,stdin=None,environment=None):
        code,out=real(self,args,stdin,environment)
        if args[:3]==['container','inspect','--format'] and 'OOMKilled' in args[3] and code==0:
            row=json.loads(out);row.update(change);out=(json.dumps(row)+'\n').encode()
        return code,out
    docker.run=run.__get__(docker);m,receipt=run_(host)
    assert item(receipt,'launched_container')['code']=='LAUNCHED_METADATA_INVALID' and phase(receipt)==('UNCERTAIN','OBSERVATION_INCOMPLETE')
def run_(host):
    docs,_=k9r.case('collect_result');receipt=docs.run(host);assert f.sealed(receipt);return docs.k.m,receipt


# ---------------------------------------------------------------- answers to the first mutation run
def test_a_failed_receipt_needs_a_constant_code():
    k,host=fresh(receipt=False,failed='FAILED',exit_code=1,changes={'code':'a message, not a code'});m,receipt=run(host=host)
    assert phase(receipt)==('UNCERTAIN','FAILED_RECEIPT_NOT_OF_THIS_STEP') and b'a message' not in f.line(receipt)

def test_a_packaged_failure_needs_a_failed_status():
    host=packaged_world(receipt=False,failed='COMPLETE',exit_code=2);m,receipt=run('acquire_result',host=host)
    assert phase(receipt)==('UNCERTAIN','FAILED_RECEIPT_NOT_OF_THIS_STEP')

def test_the_acquired_reference_is_the_one_name():
    host=packaged_world(changes={'outputs':{'batch_manifest_sha256':'d4'*32,'acquired_manifest':{'path':'other.json','sha256':'1'*64},'counts':{}}})
    m,receipt=run('acquire_result',host=host);assert item(receipt,'outputs')['code']=='OUTPUT_REFERENCE_INVALID'

def test_an_empty_aggregate_that_is_a_link_is_not_equal():
    k,host=fresh('components_result');path=k9r.day_path('receipts','components_launch.RECEIPT.json');body=json.loads(bytes(host.tree.get(path).content))
    body['aggregates']['source/components/2026-10-06/empty']={'files':0,'sha256':f.sha(f.canonical([]))};host.tree.get(path).content=bytearray(f.canonical(body))
    host.tree.add(k9r.SOURCE_ROOT+'/components/2026-10-06/empty',kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
    m,receipt=run('components_result',host=host);assert phase(receipt)==('UNCERTAIN','OUTPUTS_NOT_AS_THE_RECEIPT_SAYS') and item(receipt,'outputs')['aggregates_equal']==1

def test_the_image_revision_is_judged():
    host=probe_host();host.docker.find(hostemu.BACKEND)['Config']['Labels']['org.opencontainers.image.revision']='0'*40
    m,receipt=run('readiness_probe',host=host);assert receipt['findings']==['IMAGE_REVISION_MISMATCH'] and receipt['readiness']=='UNKNOWN'
    assert item(receipt,'probe')['code']=='PROBE_NOT_STARTED_IMAGE_NOT_AS_SIGNED' and host.container_runs()==[]     # no secret-bearing container

def test_stale_and_unusable_rows_are_counted_as_e28_counts_them():
    host=probe_host(present=96,stale=4,unusable=2);m,receipt=run('readiness_probe',host=host);probe=item(receipt,'probe')
    assert probe['present_eligible_symbols']==96 and probe['usable_eligible_symbols']==94 and probe['dated_rows']==97 and probe['bulk_rows']==101

def replace_directory(host,path):
    """Another directory under the same name: what a concurrent rename would leave (new inode, the same entries)."""
    import copy
    parent=host.tree.get(path.rsplit('/',1)[0]);name=path.rsplit('/',1)[1];node=copy.copy(parent.children[name]);host.tree.next+=1;node.ino=host.tree.next
    parent.children[name]=node

def test_the_secrets_directory_is_proved_again_before_each_use():
    docs,host=k9r.case('readiness_probe');done=[False]
    def hook(host,name,detail,calls):
        if name=='names' and str(detail[0]).endswith('/secrets') and not done[0]:done[0]=True;replace_directory(host,k9r.PLACEMENT['secrets'])
    host.hook=hook;receipt=docs.run(host)
    assert item(receipt,'secret:SECRETS/provider.env')['code']=='PARENT_REPLACED' and host.container_runs()==[] and 'DIRECTORY_REPLACED_DURING_RUN' in receipt['findings']
    docs,host=k9r.case('readiness_probe');done=[False]
    def hook(host,name,detail,calls):
        if name=='lstat' and str(detail[0]).endswith('/provider.env') and not done[0]:done[0]=True;replace_directory(host,k9r.PLACEMENT['secrets'])
    host.hook=hook;receipt=docs.run(host)
    assert item(receipt,'probe')['code']=='PARENT_REPLACED' and host.container_runs()==[] and receipt['readiness']=='UNKNOWN'

def test_a_directory_replaced_during_the_run_is_a_finding():
    docs,host=k9r.case('TREE');done=[False]
    def hook(host,name,detail,calls):
        if name=='lstat' and str(detail[0]).endswith('/password') and not done[0]:done[0]=True;replace_directory(host,k9r.PLACEMENT['days'])
    host.hook=hook;receipt=docs.run(host)
    assert receipt['findings']==['DIRECTORY_REPLACED_DURING_RUN'] and item(receipt,'directories_stable')['directories']['DAYS'] is False

def test_the_k9_root_is_proved_again_before_its_filesystem_is_judged():
    docs,host=k9r.case('TREE');done=[False]
    def hook(host,name,detail,calls):
        if name=='names' and str(detail[0])==k9r.SOURCE_ROOT and not done[0]:done[0]=True;replace_directory(host,k9r.K9_ROOT)
    host.hook=hook;receipt=docs.run(host)
    assert item(receipt,'k9_filesystem')['code']=='PARENT_REPLACED' and 'DIRECTORY_REPLACED_DURING_RUN' in receipt['findings']

# ---------------------------------------------------------------- rev 4: answers to the adversarial review of rev 3
def test_m2_a_source_root_or_a_directory_not_as_signed_makes_the_phase_uncertain():
    docs,host=k9r.case('collect_result');docs.plan['parent_rows']['source_root']['rows'][-1]['inode']+=1;docs.chain();receipt=docs.run(host)
    assert phase(receipt)==('UNCERTAIN','FINDINGS_BESIDE_THE_STEP') and 'PARENT_IDENTITY_MISMATCH' in receipt['findings']   # collect writes nothing there
    k,host=fresh('collect_result');host.tree.get('/var/lib/c3po').children.pop('r2d2-v2-source-20261005');m,receipt=run(host=host)
    assert phase(receipt)==('UNCERTAIN','FINDINGS_BESIDE_THE_STEP') and 'PARENT_MISSING' in receipt['findings']
    docs,host=k9r.case('collect_result');done=[False]
    def hook(host,name,detail,calls):
        if name=='open' and str(detail[0]).endswith('/inputs') and not done[0]:done[0]=True;replace_directory(host,k9r.SOURCE_ROOT)
    host.hook=hook;receipt=docs.run(host)
    assert receipt['findings']==['DIRECTORY_REPLACED_DURING_RUN','PHASE_RESULT_UNCERTAIN'] and receipt['phase_reason']=='FINDINGS_BESIDE_THE_STEP'

def test_m3_readiness_is_unknown_beside_any_other_finding():
    def other_boot(boot,present=3840):
        docs,_=k9r.case('readiness_probe');host=probe_host(present=present);docs.plan['evidence_boot_id_sha256']=boot;docs.chain();return docs.run(host)
    receipt=other_boot('7'*64);assert receipt['findings']==['EVIDENCE_FROM_EARLIER_BOOT'] and receipt['readiness']=='UNKNOWN' and item(receipt,'probe')['readiness']=='READY'
    receipt=other_boot('7'*64,present=10);assert receipt['readiness']=='UNKNOWN' and item(receipt,'probe')['readiness']=='NOT_READY'
    receipt=other_boot(f.BOOT_SHA,present=10);assert receipt['readiness']=='NOT_READY' and receipt['findings']==['PROVIDER_NOT_READY']

@pytest.mark.parametrize('where,change,reason',[
    ('marker',{'started_at':'2026-10-05T21:29:09+00:00'},'START_MARKER_NOT_OF_THIS_STEP'),          # before the record was created
    ('receipt',{'started_at':'2026-10-05T21:29:09+00:00'},'RECEIPT_NOT_OF_THIS_STEP'),
    ('receipt',{'completed_at':'2026-10-06T14:20:01+00:00'},'RECEIPT_NOT_OF_THIS_STEP')])               # after the container finished
def test_step_files_are_tied_to_the_launch_in_time(where,change,reason):
    options={'started_changes':change} if where=='marker' else {'changes':change}
    if where=='receipt' and 'completed_at' in change:
        k=f.load(k9r.DIRECTORY);host=k9r.world(k);container=k9r.launched(host,'collect_launch');container['State']['FinishedAt']='2026-10-05T21:39:59.999999999Z'
        k9r.record(host,'collect_launch',container);k9r.step(host,'collect_launch')
    else:k,host=fresh(**options)
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN',reason if where!='receipt' or 'completed_at' not in change else 'RECEIPT_NOT_OF_THIS_STEP')

@pytest.mark.parametrize('started_at',['2026-10-05T21:29:12.500000000Z','','0001-01-01T00:00:00Z garbage'])
def test_the_container_start_bounds_the_marker(started_at):
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);container=k9r.launched(host,'collect_launch');container['State']['StartedAt']=started_at
    k9r.record(host,'collect_launch',container);k9r.step(host,'collect_launch');m,receipt=run(host=host)
    assert phase(receipt)==('UNCERTAIN','START_MARKER_NOT_OF_THIS_STEP')

def test_the_packaged_chain_of_receipts():
    host=packaged_world();host.tree.get(k9r.spool('preflight.RECEIPT.json')).content=bytearray(b'{"other":1}')
    m,receipt=run('acquire_result',host=host);assert phase(receipt)==('UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP')
    host=packaged_world();host.tree.remove(k9r.spool('preflight.RECEIPT.json'))
    m,receipt=run('acquire_result',host=host);assert phase(receipt)==('UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP') and item(receipt,'step_receipts')['previous_receipt_present'] is False
    m,receipt=run('execute_result');assert phase(receipt)==('COMPLETE',None)                       # execute names the acquire receipt
    host=packaged_world(receipt=False,failed='REFUSED',exit_code=2);m,receipt=run('acquire_result',host=host)
    assert phase(receipt)==('FAILED','STEP_REPORTS_FAILED_OR_REFUSED')                            # previous null: accepted
    host=packaged_world(receipt=False,failed='REFUSED',exit_code=2);path=k9r.spool('acquire.FAILED.json')
    body=json.loads(bytes(host.tree.get(path).content));body['previous_receipt_sha256']='1'*64;host.tree.get(path).content=bytearray(f.canonical(body))
    m,receipt=run('acquire_result',host=host);assert phase(receipt)==('UNCERTAIN','FAILED_RECEIPT_NOT_OF_THIS_STEP')

@pytest.mark.parametrize('code,valid',[('PHASE_WINDOW_EXPIRED',True),('INTERRUPTED',True),('AAPL',False),('UNCLASSIFIED',False),('Bad_Code',False)])
def test_packaged_failure_codes_cannot_carry_a_symbol(code,valid):
    host=packaged_world(receipt=False,failed='REFUSED',exit_code=2);path=k9r.spool('acquire.FAILED.json')
    body=json.loads(bytes(host.tree.get(path).content));body['code']=code;host.tree.get(path).content=bytearray(f.canonical(body))
    m,receipt=run('acquire_result',host=host)
    assert phase(receipt)==(('FAILED','STEP_REPORTS_FAILED_OR_REFUSED') if valid else ('UNCERTAIN','FAILED_RECEIPT_NOT_OF_THIS_STEP')) and b'AAPL' not in f.line(receipt)

@pytest.mark.parametrize('code,valid',[('STEP_FAILED',True),('AAPL',False),('BRK_B',True),('A',False)])
def test_runner_failure_codes_need_an_underscore(code,valid):
    k,host=fresh(receipt=False,failed='FAILED',exit_code=1,changes={'code':code});m,receipt=run(host=host)
    assert phase(receipt)==(('FAILED','STEP_REPORTS_FAILED_OR_REFUSED') if valid else ('UNCERTAIN','FAILED_RECEIPT_NOT_OF_THIS_STEP'))

@pytest.mark.parametrize('code,valid',[('PROVIDER_REQUEST_FAILED',True),('ImportError',True),('AAPL',False),('aapl',False)])
def test_snippet_codes_cannot_carry_a_symbol(code,valid):
    docs,host=k9r.case('readiness_probe')
    host.docker.on_run=lambda call:(1,json.dumps({'status':'FAILED','code':code,'logical_fetch_calls':0,'request_sha256':None}).encode()+b'\n')
    receipt=docs.run(host)
    assert item(receipt,'probe')['findings']==(['PROBE_SNIPPET_FAILED'] if valid else ['PROBE_RUN_FAILED']) and b'AAPL' not in f.line(receipt)

@pytest.mark.parametrize('path,change',[('/var/lib',{'gid':1000}),('/var',{'mode':0o2755}),('/var/lib/c3po',{'gid':4})])
def test_tree_every_k9_component_in_the_group_of_root_and_not_setgid(path,change):
    def apply(host):
        for key,value in change.items():setattr(host.tree.get(path),key,value)
    m,receipt,host=tree_receipt(apply)
    assert receipt['findings']==['ROWS_NOT_ACCEPTABLE_TO_THE_K9_REQUESTS'] and path in item(receipt,'directory:DAYS')['components_not_root_controlled']
    assert item(receipt,'directory:SOURCE_ROOT')['rows_acceptable_to_the_k9_requests'] is False and path in item(receipt,'directory:SOURCE_ROOT')['components_not_root_controlled']

# ---------------------------------------------------------------- rev 4: answers to the trial mutation run
def unreadable_boot(host):
    def hook(host,name,detail,calls):
        if name=='read' and str(detail[0])=='/proc/sys/kernel/random/boot_id':raise OSError(5,'injected')
    host.hook=hook

def test_a_gap_without_a_finding_still_withholds_complete_and_ready():
    k,host=fresh();unreadable_boot(host);m,receipt=run(host=host)
    assert item(receipt,'boot')['status']=='UNAVAILABLE' and phase(receipt)==('UNCERTAIN','OBSERVATION_INCOMPLETE') and receipt['findings']==['PHASE_RESULT_UNCERTAIN']
    host=probe_host();unreadable_boot(host);m,receipt=run('readiness_probe',host=host)
    assert item(receipt,'probe')['readiness']=='READY' and receipt['readiness']=='UNKNOWN' and receipt['findings']==[]

def test_a_packaged_receipt_completed_after_its_container_finished_is_not_of_this_step():
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);container=k9r.launched(host,'acquire_launch');container['State']['FinishedAt']='2026-10-06T03:00:00.000000000Z'
    k9r.record(host,'acquire_launch',container);k9r.packaged(host,'acquire_launch');m,receipt=run('acquire_result',host=host)
    assert phase(receipt)==('UNCERTAIN','RECEIPT_NOT_OF_THIS_STEP') and item(receipt,'step_receipts')['started_valid'] is True

def test_a_marker_before_the_launch_record_is_not_of_this_step_even_after_the_container_start():
    k=f.load(k9r.DIRECTORY);host=k9r.world(k);container=k9r.launched(host,'collect_launch');container['State']['StartedAt']='2026-10-05T21:29:00.000000000Z'
    k9r.record(host,'collect_launch',container);k9r.step(host,'collect_launch',started_changes={'started_at':'2026-10-05T21:29:05+00:00'})
    m,receipt=run(host=host);assert phase(receipt)==('UNCERTAIN','START_MARKER_NOT_OF_THIS_STEP')

# ---------------------------------------------------------------- rev 4: the September secret sources K3-K9 signs from TREE
def test_tree_reads_the_september_sources_by_lstat_only():
    m,receipt,host=tree_receipt();found=item(receipt,'september_sources')
    assert receipt['findings']==[] and [row['path'] for row in found['components']]==list(k9r.SEPTEMBER)
    for row in found['components']:
        assert set(row)=={'path','exists','type','device','inode','uid','gid','mode_octal','mtime_ns','ctime_ns','nlink','is_link'} and row['is_link'] is False
        node=host.tree.get(row['path']);assert (row['device'],row['inode'],row['uid'],row['gid'],row['mtime_ns'],row['ctime_ns'],row['nlink'])==(node.dev,node.ino,node.uid,node.gid,node.mtime,node.ctime,node.nlink)
    assert [row['path'] for row in found['data_volume_rows']]==['/','/mnt',k9r.DATA] and found['data_volume_rows_acceptable'] is True
    for path in (k9r.SEPTEMBER[1],k9r.SEPTEMBER[4]):
        assert not [entry for entry in host.log if entry[0] in ('open','read') and entry[1]==path],'a secret source is never opened'
    line=f.line(receipt);assert 'size' not in json.dumps(found) and b'september-password' not in line and k9r.CANARY.encode() not in line

@pytest.mark.parametrize('damage,finding',[('absent_file','SEPTEMBER_SOURCE_ABSENT'),('absent_directory','SEPTEMBER_SOURCE_ABSENT'),('link','SEPTEMBER_SOURCE_IS_A_LINK'),
                                           ('directory_link','SEPTEMBER_SOURCE_IS_A_LINK'),('device','SEPTEMBER_SOURCE_ON_ANOTHER_DEVICE'),
                                           ('group_writable','SEPTEMBER_DIRECTORY_GROUP_OR_WORLD_WRITABLE'),('world_writable','SEPTEMBER_DIRECTORY_GROUP_OR_WORLD_WRITABLE'),
                                           ('not_regular','SEPTEMBER_SOURCE_NOT_A_REGULAR_FILE'),('not_directory','SEPTEMBER_SOURCE_NOT_A_DIRECTORY'),
                                           ('volume_not_mounted','DATA_VOLUME_NOT_A_MOUNT_POINT'),('mnt_operational','DATA_VOLUME_ROWS_NOT_ACCEPTABLE')])
def test_tree_september_findings(damage,finding):
    S=k9r.SEPTEMBER
    def apply(host):
        tree=host.tree
        if damage=='absent_file':tree.remove(S[4])
        if damage=='absent_directory':tree.get(k9r.DATA).children.pop('.r2d2-v2-risk-secrets')
        if damage=='link':tree.remove(S[1]);tree.add(S[1],kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
        if damage=='directory_link':tree.get(S[2]).children.pop('secret');tree.add(S[3],kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
        if damage=='device':tree.get(S[4]).dev=hostemu.ROOT_DEVICE
        if damage=='group_writable':tree.get(S[3]).mode=0o770
        if damage=='world_writable':tree.get(S[0]).mode=0o1777
        if damage=='not_regular':tree.remove(S[1]);tree.add(S[1],kind='fifo',mode=0o600,dev=hostemu.DATA_DEVICE)
        if damage=='not_directory':tree.get(S[2]).children.pop('secret');tree.add(S[3],kind='file',mode=0o600,dev=hostemu.DATA_DEVICE)
        if damage=='volume_not_mounted':tree.get(k9r.DATA).dev=hostemu.ROOT_DEVICE
        if damage=='mnt_operational':tree.get('/mnt').uid=1000
    m,receipt,host=tree_receipt(apply);found=item(receipt,'september_sources')
    assert finding in found['findings'] and receipt['outcome']==m.MISMATCH_OUTCOME
    assert not [entry for entry in host.log if entry[0] in ('open','read') and entry[1] in (S[1],S[4])]

# ---------------------------------------------------------------- the runner's rev 2: partial counts in FAILED and DEADLINE receipts
@pytest.mark.parametrize('status,expected',[('FAILED',('FAILED','STEP_REPORTS_FAILED_OR_REFUSED')),('DEADLINE',('UNCERTAIN','STEP_REPORTS_DEADLINE_OR_UNCERTAIN'))])
def test_partial_counts_of_a_failed_or_deadline_receipt_are_accepted_and_copied(status,expected):
    counts={'logical_fetch_calls':3,'http_attempts':120,'http_kib':2048,'bytes_written_kib':512}
    k,host=fresh(receipt=False,failed=status,exit_code=1,changes={'counts':counts});m,receipt=run(host=host)
    assert phase(receipt)==expected and item(receipt,'step_receipts')['failed_valid'] is True and receipt['counts']==counts

def test_the_source_root_is_proved_again_before_its_filesystem_is_compared():
    docs,host=k9r.case('TREE');done=[False]
    def hook(host,name,detail,calls):
        if name=='names' and str(detail[0])==k9r.SOURCE_ROOT and not done[0]:done[0]=True;replace_directory(host,k9r.SOURCE_ROOT)
    host.hook=hook;receipt=docs.run(host)
    assert item(receipt,'k9_filesystem')['code']=='PARENT_REPLACED' and 'DIRECTORY_REPLACED_DURING_RUN' in receipt['findings']
