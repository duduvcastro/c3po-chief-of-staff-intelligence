"""K9W on the emulated host: every operation completes on the host the eve leaves before it, with exactly the argv, the
files and the container the contracts say; the read program (K9R) and the runner find what they expect; the removal
rule (exited, by the record's ID, labels and image checked, never running); removal-only; every need not met; every
engine refusal; every effect that fails, hangs or is contradicted by its readback; the mount sources proved again
before start; budget; privacy."""
import json
from datetime import timedelta
from pathlib import Path
import sys

import pytest

import family as f
import hostemu
import k9w

def load():return f.load(k9w.DIRECTORY)
def run(operation,change=None,docs_change=None,**options):
    """One run on the prepared host; change(host) alters it first, docs_change(docs) the documents."""
    docs,host=k9w.case(operation)
    if change is not None:change(host)
    if docs_change is not None:docs_change(docs);docs.chain()
    return docs.run(host,**options),host,docs
def k9_names(host):return sorted(item['Name'][1:] for item in host.docker.containers if item['Name'].startswith('/c3po-k9-'))
def node(host,path):return host.tree.get(path)
def doc(host,path):return json.loads(bytes(node(host,path).content))
def effect_argv(host):return [entry['argv'][1:] for entry in host.commands if entry['argv'][1:2] in (['create'],['start'],['rm'],['run'])]
def claim_path(docs):return k9w.PLACEMENT['claims']+'/'+docs.plan['attempt_key']+'.claim'
COMPLETE='METADATA_ONLY_REQUIRES_REVIEW';PARTIAL='PARTIAL_METADATA_REQUIRES_REVIEW'

# ---------------------------------------------------------------- every operation completes, with the files of the contracts
@pytest.mark.parametrize('operation',sorted(k9w.WRITE))
def test_every_operation_completes_on_the_host_the_eve_leaves(operation):
    receipt,host,docs=run(operation);m=docs.k.m;step=m.K9W_STEPS[operation]
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(COMPLETE,m.success_of(docs.plan),None),receipt['code']
    assert receipt['mutating_calls']['uncertain']==0 and receipt['expectations_met'] is True and f.sealed(receipt)
    claim=node(host,claim_path(docs))
    assert claim.kind=='file' and (claim.uid,claim.gid,claim.mode,claim.nlink)==(0,0,0o600,1)
    assert json.loads(bytes(claim.content))=={'epoch':k9w.EPOCH,'day':k9w.DAY,'phase':step['phase'],'operation':operation,'slot':'PRIMARY',
                                              'request_sha256':docs.pins().request}
    claims=node(host,k9w.PLACEMENT['claims']);assert sorted(claims.children)==[docs.plan['attempt_key']+'.claim']         # no temporary left
    removed=step['removes']
    if removed:assert 'c3po-k9-20261006-'+removed not in k9_names(host) and receipt['removed'] is True
    if step['mode']=='CLEANUP':
        assert effect_argv(host)==[['rm',host.docker.removed[0]]] and k9_names(host)==[];return
    plan_raw=bytes(node(host,k9w.day_path('plans',operation+'.json')).content);plan=json.loads(plan_raw)
    assert m.canonical(plan)==plan_raw and receipt['step_plan_sha256']==k9w.sha(plan_raw)
    assert set(plan)=={'schema','epoch','day','k9_phase','k9_operation','slot','attempt_key','request_sha256','go_sha256','run_not_after','constants',
                       'network_class','database','risk','step_row'}
    assert (plan['schema'],plan['epoch'],plan['day'],plan['k9_phase'],plan['k9_operation'],plan['slot'],plan['attempt_key'])==(
        'K9_STEP_PLAN_V1',k9w.EPOCH,k9w.DAY,step['phase'],operation,'PRIMARY',docs.plan['attempt_key'])
    assert plan['request_sha256']==docs.pins().request and plan['go_sha256']==docs.pins().go and plan['network_class']==step['network']
    assert set(plan['constants'])=={'package_sha256','code_revision','act_b_sha256','release_sha256','policy_sha256','runner_sha256','risk_source_pins_sha256',
                                    'risk_limits','disk_floor_bytes'} and plan['constants']['risk_limits']==k9w.LIMITS
    assert plan['database']==({'host':'db','port':5432,'dbname':'c3po','role':'c3po_v2_causal_emitter'} if operation in ('commit_launch','publish_launch') else None)
    assert plan['risk']==(docs.plan['bind'] if operation=='bind' else None)
    assert plan['step_row']['operation']==operation and plan['step_row']['step_table_sha256']==m.K9W_STEP_TABLE_SHA256
    if step['mode']=='LAUNCH':assert plan['run_not_after']==docs.plan['run_not_after']
    else:assert plan['run_not_after']==(k9w.at(docs.plan['window']['expires_at'])+timedelta(seconds=60)).isoformat()
    def keys(value):
        if type(value) is dict:return list(value)+sum((keys(item) for item in value.values()),[])
        return sum((keys(item) for item in value),[]) if type(value) is list else []
    import re
    assert all(re.fullmatch('[a-z][a-z0-9_]{0,63}',key) for key in keys(plan))            # constant lower-case keys only, at every depth
    if step['mode']=='ATTACHED':
        call=host.docker.attached[-1];assert call.name=='c3po-k9-20261006-'+operation and call.labels=={'c3po.k9.attempt_key':docs.plan['attempt_key'],
                                                                                                         'c3po.k9.request_sha256':docs.pins().request}
        assert receipt['receipt']['complete'] is True and 'c3po-k9-20261006-'+operation not in k9_names(host)        # --rm: the engine removed it
        return
    created=host.docker.created[-1];item=host.docker.container(created.name)
    assert item['State']['Status']=='running' and item['Config']['Labels']=={'c3po.k9.attempt_key':docs.plan['attempt_key'],'c3po.k9.request_sha256':docs.pins().request}
    record_raw=bytes(node(host,k9w.day_path('launches',operation+'.json')).content);record=json.loads(record_raw)
    assert m.canonical(record)==record_raw and receipt['launch_record_sha256']==k9w.sha(record_raw)
    assert record=={'schema':'K9_LAUNCH_RECORD_V1','epoch':k9w.EPOCH,'day':k9w.DAY,'operation':operation,'slot':'PRIMARY','attempt_key':docs.plan['attempt_key'],
                    'request_sha256':docs.pins().request,'step_plan_sha256':k9w.sha(plan_raw),'container_id':item['Id'],'container_name':'c3po-k9-20261006-'+operation,
                    'created_at':docs.now.isoformat(),'started_at':docs.now.isoformat(),'timeout_seconds':receipt['timeout_seconds']}
    limit=k9w.at(docs.plan['run_not_after']);assert receipt['timeout_seconds']==int((limit-docs.now).total_seconds())-5
    assert created.command[:4]==['timeout','-s','KILL',str(receipt['timeout_seconds'])]
    assert all((n.uid,n.gid,n.mode)==(0,0,0o600) for n in (node(host,k9w.day_path('plans',operation+'.json')),node(host,k9w.day_path('launches',operation+'.json'))))

def test_collect_creates_the_day_directories_root_private_and_nothing_else():
    receipt,host,docs=run('collect_launch')
    for name in ('',)+('plans','launches','receipts'):
        n=node(host,k9w.day_path(name) if name else k9w.day_path());assert n.kind=='dir' and (n.uid,n.gid,n.mode)==(0,0,0o700),name
    assert sorted(node(host,k9w.day_path()).children)==['launches','plans','receipts']
    assert sorted(node(host,k9w.day_path('plans')).children)==['collect_launch.json'] and sorted(node(host,k9w.day_path('launches')).children)==['collect_launch.json']
    assert [row['state'] for row in receipt['ledger']['directories']]==['CREATED_DURABLE']*4 and [row['state'] for row in receipt['ledger']['files']]==['INSTALLED_DURABLE']*3
    assert receipt['objects_left_by_this_run']==7

def test_the_read_program_finds_complete_what_this_program_launched():
    """K9R RESULT, with its own sealed bytes, on the host K9W left plus the runner's two files: COMPLETE."""
    k9r_dir=Path(k9w.DIRECTORY).parent/'k9_phase_read'
    if not (k9r_dir/'build'/'ASSEMBLY.json').is_file():pytest.skip('K9R is not beside this directory')
    r=f.load(k9r_dir);constants=k9w.constants(probe_snippet_sha256=r.m.K9_PROBE_SNIPPET_SHA256,readiness_rule=dict(r.m.K9_READINESS_RULE))
    # K9R compiled with its own placement (it may still carry N-8's source root): its plan signs its own object and the
    # chains of its own paths; the files under test (days/<D>, the launch record, the labels, the receipts) are K9W's.
    read_constants=dict(constants,placement=dict(r.m.K9_PLACEMENT))
    for operation,result in (('commit_launch','commit_result'),('collect_launch','collect_result')):
        docs,host=k9w.case(operation);docs.plan['constants']=constants;docs.chain();receipt=docs.run(host);assert receipt['status']==COMPLETE
        item=host.docker.container('c3po-k9-20261006-'+operation)
        item['State'].update(Status='exited',Running=False,ExitCode=0,StartedAt=docs.now.strftime('%Y-%m-%dT%H:%M:%S.000000000Z'),
                             FinishedAt=(docs.now+timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%S.000000000Z'))
        record=doc(host,k9w.day_path('launches',operation+'.json'))
        identity={'epoch':k9w.EPOCH,'day':k9w.DAY,'phase':'causal_list','operation':operation,'attempt_key':docs.plan['attempt_key'],'step_plan_sha256':record['step_plan_sha256']}
        started=identity['step_plan_sha256'] and dict(identity,schema='K9_STEP_STARTED_V1',started_at=docs.now.isoformat())
        k9w.add_file(host,k9w.day_path('receipts',operation+'.STARTED.json'),f.canonical(started))
        k9w.add_file(host,k9w.day_path('receipts',operation+'.RECEIPT.json'),f.canonical(dict(identity,schema='K9_STEP_RECEIPT_V1',status='COMPLETE',code=None,
            started_at=docs.now.isoformat(),completed_at=docs.now.isoformat(),package_sha256=k9w.PACKAGE,build_sha=k9w.REVISION,outputs={},aggregates={},counts={'logical_fetch_calls':1})))
        later=k9w.at(docs.plan['run_not_after'])+timedelta(seconds=1)
        theirs=r.m.K9_PLACEMENT['source_root']
        if host.tree.get(theirs) is None:host.tree.add(theirs,mode=0o700,dev=hostemu.DATA_DEVICE if theirs.startswith(k9w.DATA+'/') else hostemu.ROOT_DEVICE)
        read_chains={name:{'path':r.m.K9_PLACEMENT[name],'rows':hostemu.rows(host,r.m.K9_PLACEMENT[name]),'open_root':r.m.k9_parent_open_root(r.m.K9_PLACEMENT[name])}
                     for name in k9w.CHAINS}
        plan={'mode':'RESULT','epoch':k9w.EPOCH,'day':k9w.DAY,'k9_phase':'causal_list','k9_operation':result,'slot':'PRIMARY',
              'attempt_key':k9w.attempt_key(k9w.EPOCH,k9w.DAY,'causal_list',result),'run_not_after':docs.plan['run_not_after'],'constants':read_constants,
              'parent_rows':read_chains,'evidence_boot_id_sha256':f.BOOT_SHA,'policy_read':None}
        read=f.Docs(r,plan,now=later,minutes=5).run(host)
        assert 'phase_result' in read,(read['status'],read['code'])
        assert (read['status'],read['phase_result'],read['code'])==(COMPLETE,'COMPLETE',None),(read['phase_result'],read.get('phase_reason'),read['code'])

def test_spare_slot_completes_and_a_second_slot_of_the_same_attempt_is_refused_by_the_claim():
    receipt,host,docs=run('commit_launch',docs_change=lambda docs:docs.plan.update(slot='SPARE'))
    assert receipt['status']==COMPLETE and doc(host,claim_path(docs))['slot']=='SPARE'
    other,_=k9w.case('commit_launch');before=k9w.state_of(host);again=other.run(host)
    assert (again['status'],again['code'])==('REFUSED','CLAIM_EXISTS') and k9w.state_of(host)==before

# ---------------------------------------------------------------- removal rule (section 3.2 of the note; N-3)
def collect_item(host):return host.docker.container('c3po-k9-20261006-collect_launch')
def test_the_previous_container_is_removed_by_its_id_only_when_exited_with_its_labels():
    receipt,host,docs=run('commit_launch');argv=effect_argv(host)
    assert argv[0][0]=='rm' and len(argv[0])==2 and argv[0][1] not in ('c3po-k9-20261006-collect_launch',) and len(argv[0][1])==64
    assert [word[0] for word in argv]==['rm','create','start']
    for state in ('running','created','restarting','paused','dead'):
        def change(host,state=state):
            item=collect_item(host);item['State'].update(Status=state,Running=state=='running')
        docs,host=k9w.case('commit_launch');change(host);before=k9w.state_of(host);result=docs.run(host)
        assert (result['status'],result['code'])==('REFUSED','UNCERTAIN_PREVIOUS_RUNNING') and k9w.state_of(host)==before,state
    for labels in ({},{'c3po.k9.attempt_key':'ab'*32,'c3po.k9.request_sha256':k9w.REQUEST_OF},{'c3po.k9.attempt_key':k9w.attempt_key(k9w.EPOCH,k9w.DAY,'causal_list','collect_launch'),
                                                                                              'c3po.k9.request_sha256':'ab'*32}):
        docs,host=k9w.case('commit_launch');collect_item(host)['Config']['Labels']=labels;before=k9w.state_of(host);result=docs.run(host)
        assert (result['status'],result['code'])==('REFUSED','PREVIOUS_CONTAINER_NOT_AS_RECORDED') and k9w.state_of(host)==before
    docs,host=k9w.case('commit_launch');collect_item(host)['Image']=hostemu.OTHER;result=docs.run(host)
    assert (result['status'],result['code'])==('REFUSED','PREVIOUS_CONTAINER_NOT_AS_RECORDED')
    docs,host=k9w.case('commit_launch');collect_item(host)['Name']='/c3po-k9-20261006-other';result=docs.run(host)
    assert (result['status'],result['code'])==('REFUSED','PREVIOUS_CONTAINER_NOT_AS_RECORDED')
    for changes in ({'container_name':'c3po-k9-20261006-other'},{'attempt_key':'ab'*32},{'operation':'commit_launch'},{'day':'2026-10-07'},{'schema':'X'},
                    {'container_id':'XYZ'},{'request_sha256':'0'*64},{'extra':1}):
        def change(host,changes=changes):
            path=k9w.day_path('launches','collect_launch.json');body=doc(host,path);body.update(changes);node(host,path).content=bytearray(f.canonical(body))
        docs,host=k9w.case('commit_launch');change(host);before=k9w.state_of(host);result=docs.run(host)
        assert (result['status'],result['code'])==('REFUSED','PREVIOUS_LAUNCH_RECORD_INVALID') and k9w.state_of(host)==before,changes
    docs,host=k9w.case('commit_launch');node(host,k9w.day_path('launches','collect_launch.json')).mode=0o644;result=docs.run(host)
    assert (result['status'],result['code'])==('REFUSED','PREVIOUS_LAUNCH_RECORD_INVALID')
    docs,host=k9w.case('commit_launch');node(host,k9w.day_path('launches','collect_launch.json')).content=bytearray(b'{"a":1,"a":2}');result=docs.run(host)
    assert (result['status'],result['code'])==('REFUSED','PREVIOUS_LAUNCH_RECORD_INVALID')

def test_a_previous_container_already_gone_is_not_removed_and_the_step_goes_on():
    def gone(host):host.docker.containers.remove(collect_item(host))
    receipt,host,docs=run('commit_launch',gone)
    assert receipt['status']==COMPLETE and [argv[0] for argv in effect_argv(host)]==['create','start'] and receipt['checks']['previous']['present'] is False
    def no_record(host):host.tree.remove(k9w.day_path('launches','collect_launch.json'))
    receipt,host,docs=run('commit_launch',no_record)          # the predecessor's launch record is gone too: not complete, nothing to remove
    assert (receipt['status'],receipt['code'])==('REFUSED','REFUSED_PREDECESSOR_NOT_COMPLETE')
    # a container of the previous step's name with no record is never removed (reported by name)
    receipt,host,docs=run('sources_launch',lambda host:host.tree.remove(k9w.day_path('launches','components_launch.json')))
    assert receipt['status']==COMPLETE and 'c3po-k9-20261006-components_launch' in k9_names(host) and receipt['checks']['previous']=={'removes':'components_launch',
                                                                                                                                      'name_listed':True,'record':False}

def test_removal_failures():
    receipt,host,docs=run('commit_launch',lambda host:setattr(host.docker,'rm_returncode',1))
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'PREVIOUS_CONTAINER_NOT_REMOVED','REMOVE')
    assert [argv[0] for argv in effect_argv(host)]==['rm'] and receipt['mutating_calls']['uncertain']==0 and receipt['removed'] is False
    def nonzero_but_gone(host):
        host.docker.rm_returncode=None;original=host.docker.run
        def run_(args,stdin=None,environment=None):
            code,out=original(args,stdin,environment)
            return (1,b'') if args[:1]==['rm'] else (code,out)
        host.docker.run=run_
    receipt,host,docs=run('commit_launch',nonzero_but_gone)          # rm says 1 and the container is gone: the step stops
    assert (receipt['status'],receipt['code'])==(PARTIAL,'PREVIOUS_CONTAINER_REMOVAL_STATUS_NONZERO') and [argv[0] for argv in effect_argv(host)]==['rm']
    receipt,host,docs=run('commit_launch',lambda host:setattr(host.docker,'rm_effect',False))       # rm says 0 and the container is still listed
    assert (receipt['status'],receipt['code'])==(PARTIAL,'PREVIOUS_CONTAINER_NOT_REMOVED') and receipt['mutating_calls']['uncertain']==1 and receipt['removed'] is False
    def hang(host):host.hang_after.add(('rm',))
    receipt,host,docs=run('commit_launch',hang)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'COMMAND_TIMEOUT','REMOVE') and receipt['mutating_calls']['uncertain']==1
    def absent(host):host.absent.add(('rm',))
    receipt,host,docs=run('commit_launch',absent)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'COMMAND_NOT_STARTED') and receipt['mutating_calls']['uncertain']==0
    def unlisted(host):
        original=host.docker.run;count=[0]
        def run_(args,stdin=None,environment=None):
            if args[:1]==['ps']:
                count[0]+=1
                if count[0]>1:return 1,b''
            return original(args,stdin,environment)
        host.docker.run=run_;host.docker.rm_returncode=1
    receipt,host,docs=run('commit_launch',unlisted)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'REMOVAL_READBACK_UNAVAILABLE') and receipt['mutating_calls']['uncertain']==1
    def unlisted_later(host):
        original=host.docker.run;count=[0]
        def run_(args,stdin=None,environment=None):
            if args[:1]==['ps']:
                count[0]+=1
                if count[0]>1:return 1,b''
            return original(args,stdin,environment)
        host.docker.run=run_
    for operation in ('commit_launch','stage'):             # rm said 0, the listing after the step's own effect fails
        receipt,host,docs=run(operation,unlisted_later)
        assert (receipt['status'],receipt['code'])==(PARTIAL,'REMOVAL_READBACK_UNAVAILABLE') and receipt['mutating_calls']['uncertain']==1,operation
    def removal_ignored(host):host.docker.rm_effect=False
    receipt,host,docs=run('stage',removal_ignored)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'PREVIOUS_CONTAINER_NOT_REMOVED')

# ---------------------------------------------------------------- removal-only and refusals of needs
def test_removal_only_when_a_predecessor_is_not_complete():
    cases={'receipt absent':lambda host:host.tree.remove(k9w.day_path('receipts','collect_launch.RECEIPT.json')),
           'marker absent':lambda host:host.tree.remove(k9w.day_path('receipts','collect_launch.STARTED.json')),
           'failed present':lambda host:k9w.add_file(host,k9w.day_path('receipts','collect_launch.FAILED.json'),b'{}'),
           'plan changed':lambda host:setattr(node(host,k9w.day_path('plans','collect_launch.json')),'content',bytearray(b'{"other":1}')),
           'plan absent':lambda host:host.tree.remove(k9w.day_path('plans','collect_launch.json')),
           'exit code':lambda host:collect_item(host)['State'].update(ExitCode=1),
           'oom':lambda host:collect_item(host)['State'].update(OOMKilled=True),
           'receipt public':lambda host:setattr(node(host,k9w.day_path('receipts','collect_launch.RECEIPT.json')),'mode',0o644),
           'record of another plan':lambda host:setattr(node(host,k9w.day_path('launches','collect_launch.json')),'content',
                                                         bytearray(f.canonical(dict(doc(host,k9w.day_path('launches','collect_launch.json')),step_plan_sha256='ab'*32))))}
    def marker_changed(**changes):
        def change(host):
            path=k9w.day_path('receipts','collect_launch.STARTED.json');body=doc(host,path);body.update(changes);node(host,path).content=bytearray(f.canonical(body))
        return change
    for key,value in (('step_plan_sha256','ab'*32),('attempt_key','ab'*32),('schema','K9_STEP_STARTED_V2'),('started_at','2026-10-06T23:00:00+00:00'),('extra',1)):
        cases['marker '+key]=marker_changed(**{key:value})
    def receipt_changed(**changes):
        def change(host):
            path=k9w.day_path('receipts','collect_launch.RECEIPT.json');body=doc(host,path);body.update(changes);node(host,path).content=bytearray(f.canonical(body))
        return change
    for key,value in (('status','FAILED'),('code','X_Y'),('package_sha256','ab'*32),('build_sha','ab'*20),('attempt_key','ab'*32),('operation','commit_launch'),
                      ('phase','components'),('day','2026-10-07'),('epoch','R2D2-V2-SHADOW-2026-09-28'),('schema','K9_STEP_RECEIPT_V2'),('step_plan_sha256','ab'*32),
                      ('completed_at','2026-10-06T23:00:00+00:00'),('started_at','2026-10-05T21:45:00+00:00'),('outputs',{'day/../x':'ab'*32}),('outputs',{'day/a':'xyz'}),
                      ('aggregates',{'day/a':{'files':1}}),('counts',{'AAPL':1}),('counts',{'calls':1}),('counts',{'logical_fetch_calls':-1}),
                      ('counts',{'logical_fetch_calls':{'deep_er':{'x_y':1}}}),('extra',1)):
        cases['receipt '+key]=receipt_changed(**{key:value})
    for name,change in cases.items():
        receipt,host,docs=run('commit_launch',change)
        assert (receipt['status'],receipt['outcome'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'K9_REMOVAL_ONLY_PREDECESSOR_NOT_COMPLETE',
                                                                                              'REFUSED_PREDECESSOR_NOT_COMPLETE','REMOVAL_ONLY'),(name,receipt['code'])
        assert [argv[0] for argv in effect_argv(host)]==['rm'] and k9_names(host)==[] and node(host,claim_path(docs)) is not None,name
        assert node(host,k9w.day_path('plans','commit_launch.json')) is None and receipt['mutating_calls']['uncertain']==0
        assert receipt['needs_not_met']==['REFUSED_PREDECESSOR_NOT_COMPLETE']
    # nothing to remove: a refusal, nothing changed, no claim
    def nothing(host):
        host.docker.containers.remove(collect_item(host));host.tree.remove(k9w.day_path('receipts','collect_launch.RECEIPT.json'))
    docs,host=k9w.case('commit_launch');nothing(host);before=k9w.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','REFUSED_PREDECESSOR_NOT_COMPLETE') and k9w.state_of(host)==before

def test_needs_of_each_step():
    def refuses(operation,change,code,removes=False):
        docs,host=k9w.case(operation);change(host);before=k9w.state_of(host);receipt=docs.run(host)
        if removes:
            assert (receipt['status'],receipt['outcome'],receipt['code'])==(PARTIAL,'K9_REMOVAL_ONLY_PREDECESSOR_NOT_COMPLETE',code),(operation,receipt['code'])
            assert [argv[0] for argv in effect_argv(host)]==['rm']
        else:assert (receipt['status'],receipt['code'])==('REFUSED',code) and k9w.state_of(host)==before,(operation,receipt['code'])
        return receipt
    refuses('collect_launch',k9w.layout,'DAY_DIRECTORY_EXISTS')
    refuses('collect_launch',lambda host:k9w.add_dir(host,k9w.day_path()),'DAY_LAYOUT_INVALID')
    refuses('commit_launch',lambda host:k9w.add_dir(host,k9w.day_path('causal')),'DESTINATION_EXISTS',True)
    refuses('publish_launch',lambda host:k9w.add_dir(host,k9w.day_path('control')),'DESTINATION_EXISTS',True)
    refuses('publish_launch',lambda host:k9w.add_file(host,k9w.day_path('relay'),b''),'DESTINATION_EXISTS',True)
    refuses('components_launch',lambda host:(k9w.add_dir(host,k9w.SOURCE_ROOT+'/components'),k9w.add_dir(host,k9w.SOURCE_ROOT+'/components/'+k9w.DAY)),'DESTINATION_EXISTS',True)
    refuses('components_launch',lambda host:setattr(node(host,k9w.day_path('control','symbols.txt')),'content',bytearray(b'S000\n')),'SYMBOLS_NOT_AS_PUBLISHED',True)
    refuses('components_launch',lambda host:host.tree.remove(k9w.day_path('control','symbols.txt')),'SYMBOLS_NOT_AS_PUBLISHED',True)
    refuses('sources_launch',lambda host:k9w.add_dir(host,k9w.day_path('risk')),'DESTINATION_EXISTS',True)
    refuses('sources_launch',lambda host:setattr(host.vfs[hostemu.ROOT_DEVICE],'f_bavail',214748364800//4096-1),'DISK_FREE_BELOW_FLOOR')
    def one_byte_short(host):host.vfs[hostemu.ROOT_DEVICE].f_frsize=1;host.vfs[hostemu.ROOT_DEVICE].f_bavail=214748364800-1
    refuses('collect_launch',one_byte_short,'DISK_FREE_BELOW_FLOOR')
    docs,host=k9w.case('collect_launch');host.vfs[hostemu.ROOT_DEVICE].f_frsize=1;host.vfs[hostemu.ROOT_DEVICE].f_bavail=214748364800
    assert docs.run(host)['status']==COMPLETE                                           # exactly the floor is enough
    refuses('sources_launch',lambda host:setattr(node(host,k9w.PLACEMENT['risk_db_env_file']),'mode',0o640),'ENV_FILE_NOT_PRIVATE')
    refuses('sources_launch',lambda host:setattr(node(host,k9w.PLACEMENT['provider_env_file']),'uid',1000),'ENV_FILE_NOT_PRIVATE')
    refuses('sources_launch',lambda host:setattr(node(host,k9w.PLACEMENT['provider_env_file']),'gid',1000),'ENV_FILE_NOT_PRIVATE')
    refuses('sources_launch',lambda host:setattr(node(host,k9w.PLACEMENT['provider_env_file']),'nlink',2),'ENV_FILE_NOT_PRIVATE')
    refuses('sources_launch',lambda host:host.tree.remove(k9w.PLACEMENT['risk_db_env_file']),'ENV_FILE_NOT_PRIVATE')
    def env_link(host):
        host.tree.remove(k9w.PLACEMENT['provider_env_file']);host.tree.add(k9w.PLACEMENT['provider_env_file'],kind='symlink',mode=0o600)
    refuses('sources_launch',env_link,'ENV_FILE_NOT_PRIVATE')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.PLACEMENT['emitter_password']),'mode',0o644),'EMITTER_SECRET_NOT_PRIVATE')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.PLACEMENT['emitter']),'mode',0o750),'EMITTER_SECRET_NOT_PRIVATE')
    refuses('commit_launch',lambda host:host.tree.remove(k9w.PLACEMENT['emitter_password']),'EMITTER_SECRET_NOT_PRIVATE')
    refuses('publish_launch',lambda host:host.tree.remove(k9w.PLACEMENT['emitter_password']),'EMITTER_SECRET_NOT_PRIVATE')
    refuses('commit_launch',lambda host:host.tree.remove(k9w.PLACEMENT['tools']+'/k9_runner-'+k9w.RUNNER_SHA256+'.py'),'RUNNER_FILE_NOT_AS_REQUIRED')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.PLACEMENT['tools']+'/k9_runner-'+k9w.RUNNER_SHA256+'.py'),'mode',0o644),'RUNNER_FILE_NOT_AS_REQUIRED')
    refuses('bind',lambda host:k9w.add_file(host,k9w.day_path('risk','plan','HOST_PLAN.json'),b'x'),'DESTINATION_EXISTS')
    refuses('bind',lambda host:k9w.add_dir(host,k9w.day_path('risk','spool')),'DESTINATION_EXISTS')
    refuses('bind',lambda host:host.tree.remove(k9w.day_path('risk','plan','replay.private.json'))
            or host.tree.remove(k9w.day_path('risk','plan','risk-input-names.private.json')) or host.tree.remove(k9w.day_path('risk','plan')),'INPUT_DIRECTORY_ABSENT')
    refuses('bind',lambda host:host.tree.remove(k9w.day_path('receipts','publish_launch.RECEIPT.json')),'REFUSED_PREDECESSOR_NOT_COMPLETE')
    refuses('preflight',lambda host:setattr(node(host,k9w.day_path('risk','plan','GO.json')),'content',bytearray(b'{"other":1}\n')),'RISK_PLAN_NOT_AS_BOUND')
    refuses('preflight',lambda host:host.tree.remove(k9w.day_path('risk','spool')),'INPUT_DIRECTORY_ABSENT')
    refuses('preflight',lambda host:k9w.add_dir(host,k9w.spool()),'DESTINATION_EXISTS')
    def window_closed(host):
        raw=k9w.canonical({'schema':'R2D2_V2_RISK_HOST_PLAN_V1','phase_windows':{'preflight':{'not_before':'2026-10-06T02:39:00+00:00','not_after':'2026-10-06T02:44:59+00:00'}}})
        node(host,k9w.day_path('risk','plan','HOST_PLAN.json')).content=bytearray(raw)
    refuses('preflight',window_closed,'RISK_PLAN_NOT_AS_BOUND')                        # the bind receipt no longer names these bytes
    refuses('acquire_launch',lambda host:host.tree.remove(k9w.spool('preflight.RECEIPT.json')),'REFUSED_PREDECESSOR_NOT_COMPLETE',True)
    refuses('acquire_launch',lambda host:k9w.add_file(host,k9w.spool('preflight.FAILED.json'),b'{}'),'REFUSED_PREDECESSOR_NOT_COMPLETE',True)
    refuses('acquire_launch',lambda host:k9w.add_file(host,k9w.spool('acquire.STARTED.json'),b'{}'),'DESTINATION_EXISTS',True)
    for key,value in (('namespace','R2D2-V2-SHADOW-2026-10-06'),('session_date','2026-10-07'),('status','UNCERTAIN'),('operation_activation',True),
                      ('certification_granted',True),('manifest_sha256','ab'*32),('go_sha256','ab'*32),('phase','acquire'),('schema','X'),('extra',1),
                      ('completed_at','2026-10-06T23:00:00+00:00')):
        refuses('acquire_launch',lambda host,key=key,value=value:k9w.packaged_receipt(host,'preflight',changes={key:value}),'REFUSED_PREDECESSOR_NOT_COMPLETE',True)
    def acquire_window(host):
        windows=dict(k9w.WINDOWS,acquire={'not_before':'2026-10-06T02:42:00+00:00','not_after':'2026-10-06T03:46:59+00:00'})
        raw=k9w.canonical({'schema':'R2D2_V2_RISK_HOST_PLAN_V1','synthetic':True,'phase_windows':windows})+b'\n'
        node(host,k9w.day_path('risk','plan','HOST_PLAN.json')).content=bytearray(raw)
    refuses('acquire_launch',acquire_window,'REFUSED_PREDECESSOR_NOT_COMPLETE',True)         # another plan: its spool has no preflight receipt
    refuses('execute_launch',lambda host:host.tree.remove(k9w.spool('acquire.RECEIPT.json')),'REFUSED_PREDECESSOR_NOT_COMPLETE',True)
    refuses('execute_launch',lambda host:host.docker.container('c3po-k9-20261006-acquire_launch')['State'].update(ExitCode=2),'REFUSED_PREDECESSOR_NOT_COMPLETE',True)
    refuses('stage',lambda host:k9w.add_file(host,k9w.SOURCE_ROOT+'/components/'+k9w.DAY+'/risk.json',b'x'),'DESTINATION_EXISTS',True)
    refuses('stage',lambda host:host.tree.remove(k9w.SOURCE_ROOT+'/components/'+k9w.DAY),'INPUT_DIRECTORY_ABSENT',True)
    refuses('stage',lambda host:host.tree.remove(k9w.spool('execute.RECEIPT.json')),'REFUSED_PREDECESSOR_NOT_COMPLETE',True)
    refuses('capture_launch',lambda host:host.tree.remove(k9w.day_path('receipts','publish_launch.RECEIPT.json')),'REFUSED_PREDECESSOR_NOT_COMPLETE')
    refuses('capture_launch',lambda host:host.tree.remove(k9w.day_path()),'DAY_DIRECTORY_ABSENT')
    refuses('capture_cleanup',lambda host:host.docker.containers.remove(host.docker.container('c3po-k9-20261006-capture_launch')),'CLEANUP_NOTHING_TO_REMOVE')
    refuses('capture_cleanup',lambda host:host.tree.remove(k9w.day_path('launches','capture_launch.json')),'CLEANUP_NOTHING_TO_REMOVE')
    refuses('capture_cleanup',lambda host:host.docker.container('c3po-k9-20261006-capture_launch')['State'].update(Status='running',Running=True),'UNCERTAIN_PREVIOUS_RUNNING')
    # the windows of the plan of the packaged risk phase: preflight outside it
    def preflight_window(host):
        windows=dict(k9w.WINDOWS,preflight={'not_before':'2026-10-06T02:39:00+00:00','not_after':'2026-10-06T02:44:59+00:00'})
        raw=k9w.canonical({'schema':'R2D2_V2_RISK_HOST_PLAN_V1','synthetic':True,'phase_windows':windows})+b'\n'
        path=k9w.day_path('risk','plan','HOST_PLAN.json');node(host,path).content=bytearray(raw)
        receipt=k9w.day_path('receipts','bind.RECEIPT.json');body=doc(host,receipt);body['outputs']['day/risk/plan/HOST_PLAN.json']=k9w.sha(raw)
        node(host,receipt).content=bytearray(f.canonical(body))
    refuses('preflight',preflight_window,'RISK_PHASE_WINDOW_NOT_OPEN')

def test_engine_and_tree_refusals_change_nothing():
    def refuses(operation,change,code,**options):
        docs,host=k9w.case(operation);change(host);before=k9w.state_of(host);receipt=docs.run(host,**options)
        assert (receipt['status'],receipt['code'])==('REFUSED',code) and k9w.state_of(host)==before,(operation,receipt['code'])
    refuses('commit_launch',lambda host:host.docker.images.pop(0),'COMMAND_FAILED')
    refuses('commit_launch',lambda host:host.docker.images[0]['Config']['Labels'].update({'org.opencontainers.image.revision':'ab'*20}),'IMAGE_NOT_THE_SIGNED_ONE')
    refuses('commit_launch',lambda host:k9w.container_of(host,'readiness_recheck' if False else 'components_launch',state='running'),'ANOTHER_K9_CONTAINER_ACTIVE')
    refuses('commit_launch',lambda host:k9w.container_of(host,'commit_launch',state='exited'),'CONTAINER_NAME_IN_USE')
    refuses('commit_launch',lambda host:setattr(host.docker,'ps_returncode',1),'COMMAND_FAILED')
    refuses('commit_launch',lambda host:k9w.add_file(host,k9w.PLACEMENT['claims']+'/'+k9w.attempt_key(k9w.EPOCH,k9w.DAY,'causal_list','commit_launch')+'.claim',b'{}'),'CLAIM_EXISTS')
    refuses('commit_launch',lambda host:setattr(host,'actor',(1000,1000)),'EXECUTOR_IDENTITY')
    refuses('commit_launch',lambda host:setattr(node(host,'/proc/sys/kernel/random/boot_id'),'content',bytearray(b'11111111-2222-3333-4444-555555555555\n')),'EVIDENCE_FROM_EARLIER_BOOT')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.PLACEMENT['days']),'mode',0o755),'PARENT_IDENTITY_MISMATCH')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.SOURCE_ROOT),'ino',99999),'PARENT_IDENTITY_MISMATCH')
    def source_link(host):
        host.tree.remove(k9w.SOURCE_ROOT);host.tree.add(k9w.SOURCE_ROOT,kind='symlink',mode=0o777,dev=hostemu.DATA_DEVICE)
    refuses('collect_launch',source_link,'PARENT_SYMLINK_COMPONENT')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.day_path()),'mode',0o750),'DAY_DIRECTORY_NOT_PRIVATE')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.day_path()),'gid',1000),'DAY_DIRECTORY_NOT_PRIVATE')
    refuses('commit_launch',lambda host:host.tree.remove(k9w.day_path('receipts')) if not node(host,k9w.day_path('receipts')).children else
            [host.tree.remove(k9w.day_path('receipts',name)) for name in list(node(host,k9w.day_path('receipts')).children)] and host.tree.remove(k9w.day_path('receipts')),'DAY_LAYOUT_INVALID')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.day_path('launches')),'mode',0o755),'DAY_LAYOUT_INVALID')
    def plans_link(host):
        for name in list(node(host,k9w.day_path('plans')).children):host.tree.remove(k9w.day_path('plans',name))
        host.tree.remove(k9w.day_path('plans'));host.tree.add(k9w.day_path('plans'),kind='symlink',mode=0o777)
    refuses('commit_launch',plans_link,'SYMLINK_COMPONENT')

def test_every_bind_source_is_root_controlled_on_the_filesystem_of_days():
    """Decision 6: a bind source that is not root's private directory on days/' filesystem refuses before any effect."""
    def refuses(operation,change,code):
        docs,host=k9w.case(operation);change(host);before=k9w.state_of(host);receipt=docs.run(host)
        assert (receipt['status'],receipt['code'])==('REFUSED',code) and k9w.state_of(host)==before,(operation,receipt['code'])
    refuses('commit_launch',lambda host:setattr(node(host,k9w.PLACEMENT['emitter']),'dev',hostemu.DATA_DEVICE),'MOUNT_SOURCE_NOT_ROOT_CONTROLLED')
    refuses('stage',lambda host:setattr(node(host,k9w.day_path('receipts')),'dev',hostemu.DATA_DEVICE),'MOUNT_SOURCE_NOT_ROOT_CONTROLLED')
    refuses('publish_launch',lambda host:setattr(node(host,k9w.SOURCE_ROOT),'mode',0o750),'PARENT_IDENTITY_MISMATCH')      # walked against the signed rows
    docs,host=k9w.case('publish_launch');receipt=docs.run(host)
    assert receipt['status']==COMPLETE and receipt['checks']['engine']['mount_sources_root_controlled'] is True
    assert receipt['checks']['chains']['source_root_on_the_filesystem_of_days'] is True
    # uid, gid and mode of DAY, DAY_RECEIPTS, EMITTER are refused earlier (DAY_DIRECTORY_NOT_PRIVATE, DAY_LAYOUT_INVALID,
    # EMITTER_SECRET_NOT_PRIVATE) and those of TOOLS and SOURCE_ROOT by their signed rows: here the device is what is new
    refuses('commit_launch',lambda host:setattr(node(host,k9w.day_path('receipts')),'mode',0o750),'DAY_LAYOUT_INVALID')
    refuses('commit_launch',lambda host:setattr(node(host,k9w.PLACEMENT['emitter']),'uid',1000),'EMITTER_SECRET_NOT_PRIVATE')

def test_budget_before_the_first_effect():
    m=load().m
    for operation,needed in (('commit_launch',44),('collect_launch',36),('bind',48),('stage',36),('capture_cleanup',16)):
        docs,host=k9w.case(operation);budget=f.Budget(docs.now).attach(host).cost(60-needed+1-0.5,'ps')
        before=k9w.state_of(host);receipt=docs.run(host,**budget.options())
        assert (receipt['status'],receipt['code'])==('REFUSED','BUDGET_INSUFFICIENT') and k9w.state_of(host)==before,(operation,receipt['code'])
        assert receipt['checks']['budget']['seconds_needed']==needed
        docs,host=k9w.case(operation);budget=f.Budget(docs.now).attach(host).cost(60-needed-1,'ps');receipt=docs.run(host,**budget.options())
        assert receipt['status']==COMPLETE,(operation,receipt['code'])

# ---------------------------------------------------------------- the effects that fail, hang or are contradicted
def test_needs_are_not_looked_at_past_an_incomplete_predecessor_and_the_readbacks_stop_a_step():
    receipt,host,docs=run('publish_launch',lambda host:(host.tree.remove(k9w.day_path('receipts','commit_launch.RECEIPT.json')),
                                                         setattr(node(host,k9w.PLACEMENT['provider_env_file']),'mode',0o644)))
    assert (receipt['status'],receipt['outcome'],receipt['needs_not_met'])==(PARTIAL,'K9_REMOVAL_ONLY_PREDECESSOR_NOT_COMPLETE',['REFUSED_PREDECESSOR_NOT_COMPLETE'])
    def no_day(host):
        host.docker.containers=[item for item in host.docker.containers if not item['Name'].startswith('/c3po-k9-')]
        def drop(path):
            for name in list(node(host,path).children):
                child=path+'/'+name
                if node(host,child).kind=='dir':drop(child)
                host.tree.remove(child)
        drop(k9w.day_path());host.tree.remove(k9w.day_path())
    docs,host=k9w.case('commit_launch');no_day(host);before=k9w.state_of(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['code'])==('REFUSED','DAY_DIRECTORY_ABSENT') and k9w.state_of(host)==before
    def failing(event,suffix,occurrence=1,error=5):
        def change(host):
            seen=[0]
            def hook(host,name,detail,calls):
                if name==event and str(detail[0]).endswith(suffix) and not (event=='open' and detail[1]&(os.O_WRONLY|os.O_CREAT)):
                    seen[0]+=1
                    if seen[0]==occurrence:raise OSError(error,'injected')
            host.hook=hook
        return change
    import os
    claim='/'+k9w.attempt_key(k9w.EPOCH,k9w.DAY,'causal_list','commit_launch')+'.claim'
    receipt,host,docs=run('commit_launch',failing('open',claim))
    assert (receipt['status'],receipt['phase_reached'],receipt['code'])==(PARTIAL,'CLAIM','READBACK_UNAVAILABLE') and k9_names(host).count('c3po-k9-20261006-collect_launch')==1
    receipt,host,docs=run('commit_launch',failing('open','/plans/commit_launch.json'))
    assert (receipt['status'],receipt['phase_reached'],receipt['code'])==(PARTIAL,'STEP_PLAN','READBACK_UNAVAILABLE') and host.docker.created==[]
    receipt,host,docs=run('collect_launch',failing('mkdir','/days/'+k9w.DAY,error=28))
    assert (receipt['status'],receipt['phase_reached'],receipt['code'])==('REFUSED','DIRECTORIES','FILESYSTEM_FULL') or \
           (receipt['status'],receipt['phase_reached'],receipt['code'])==(PARTIAL,'DIRECTORIES','FILESYSTEM_FULL')
    assert host.docker.created==[] and node(host,k9w.day_path()) is None
    receipt,host,docs=run('collect_launch',failing('mkdir','/days/'+k9w.DAY+'/launches',error=28))
    assert (receipt['status'],receipt['phase_reached'],receipt['code'])==(PARTIAL,'DIRECTORIES','FILESYSTEM_FULL') and host.docker.created==[]
    receipt,host,docs=run('collect_launch',failing('names','/days/'+k9w.DAY,occurrence=2))
    assert (receipt['status'],receipt['phase_reached'],receipt['code'])==(PARTIAL,'STEP_PLAN','READBACK_UNAVAILABLE') and host.docker.created==[]

def test_create_and_start_failures():
    receipt,host,docs=run('commit_launch',lambda host:setattr(host.docker,'create_returncode',125))
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'CREATE_FAILED','CREATE') and receipt['mutating_calls']['uncertain']==0
    assert node(host,k9w.day_path('launches','commit_launch.json')) is None and receipt['removed'] is True
    receipt,host,docs=run('commit_launch',lambda host:setattr(host.docker,'create_output',b'not an id\n'))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'CREATE_FAILED') and receipt['mutating_calls']['uncertain']==1        # a container exists by name
    receipt,host,docs=run('commit_launch',lambda host:host.hang_after.add(('create',)))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'COMMAND_TIMEOUT') and receipt['mutating_calls']['uncertain']==1
    receipt,host,docs=run('commit_launch',lambda host:setattr(host.docker,'start_returncode',1))
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'START_FAILED','START') and receipt['mutating_calls']['uncertain']==0
    assert node(host,k9w.day_path('launches','commit_launch.json')) is None and host.docker.container('c3po-k9-20261006-commit_launch')['State']['Status']=='created'
    def started_anyway(host):host.docker.start_returncode=1;host.docker.start_failure_after_effect=True
    receipt,host,docs=run('commit_launch',started_anyway)            # start says 1 and the container runs: uncertain, never "nothing changed"
    assert (receipt['status'],receipt['code'])==(PARTIAL,'START_FAILED') and receipt['mutating_calls']['uncertain']==1
    receipt,host,docs=run('commit_launch',lambda host:setattr(host.docker,'start_effect',False))   # start says 0 and the container stays created
    assert (receipt['status'],receipt['code'])==(PARTIAL,'LAUNCHED_CONTAINER_NOT_AS_BUILT') and receipt['mutating_calls']['uncertain']==1
    for change in (lambda item:item.update(Image=hostemu.OTHER),lambda item:item.update(Name='/c3po-k9-20261006-other')):
        receipt,host,docs=run('commit_launch',lambda host,change=change:setattr(host.docker,'on_start',change))
        assert (receipt['status'],receipt['code'])==(PARTIAL,'LAUNCHED_CONTAINER_NOT_AS_BUILT')
    docs,host=k9w.case('commit_launch');budget=f.Budget(docs.now).attach(host).cost(1,'create');receipt=docs.run(host,**budget.options())
    record=doc(host,k9w.day_path('launches','commit_launch.json'))
    assert receipt['status']==COMPLETE and k9w.at(record['created_at'])<k9w.at(record['started_at'])        # each instant read before its own command
    def record_unreadable(host):
        seen=[0]
        def hook(host,name,detail,calls):
            if name=='open' and str(detail[0]).endswith('/launches/commit_launch.json') and not detail[1]&(os.O_WRONLY|os.O_CREAT):raise OSError(5,'injected')
        host.hook=hook
    import os
    receipt,host,docs=run('commit_launch',record_unreadable)
    assert (receipt['status'],receipt['phase_reached'],receipt['code'])==(PARTIAL,'LAUNCH_RECORD','READBACK_UNAVAILABLE')
    receipt,host,docs=run('commit_launch',lambda host:host.hang_after.add(('start',)))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'COMMAND_TIMEOUT') and receipt['mutating_calls']['uncertain']==1
    def started_but_gone(host):host.docker.on_start=lambda item:host.docker.containers.remove(item)
    receipt,host,docs=run('commit_launch',started_but_gone)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'LAUNCHED_CONTAINER_NOT_AS_BUILT') and node(host,k9w.day_path('launches','commit_launch.json')) is not None
    def exits_at_once(host):host.docker.on_start=lambda item:item['State'].update(Status='exited',Running=False,ExitCode=0)
    receipt,host,docs=run('commit_launch',exits_at_once);assert receipt['status']==COMPLETE           # a step that ended already is still launched
    def label_lost(host):host.docker.on_start=lambda item:item['Config']['Labels'].pop('c3po.k9.request_sha256')
    receipt,host,docs=run('commit_launch',label_lost);assert (receipt['status'],receipt['code'])==(PARTIAL,'LAUNCHED_CONTAINER_NOT_AS_BUILT')

def test_capture_launched_early_lives_to_its_fixed_end_and_hold_needs_spend_nothing():
    receipt,host,docs=run('capture_launch',docs_change=lambda docs:docs.shift(k9w.at('2026-10-06T13:31:00+00:00'),k9w.at('2026-10-06T13:36:00+00:00')),
                          clock=lambda:k9w.at('2026-10-06T13:31:00+00:00'))
    assert receipt['status']==COMPLETE and receipt['timeout_seconds']==32*60-5          # not capped at ceiling + 900 (the runner stops at 14:02)
    for operation in ('sources_launch','commit_launch'):
        docs,host=k9w.case(operation);host.vfs[hostemu.ROOT_DEVICE].f_bavail=214748364800//4096-1;before=k9w.state_of(host);receipt=docs.run(host)
        assert (receipt['status'],receipt['code'])==('REFUSED','DISK_FREE_BELOW_FLOOR') and k9w.state_of(host)==before   # the previous container stays
        host.vfs[hostemu.ROOT_DEVICE].f_bavail=214748364800//4096+1;again=docs.run(host);assert again['status']==COMPLETE,operation   # the same request, later

def test_mount_sources_proved_again_before_start_and_after():
    def swap(host):
        def after(item):
            node(host,k9w.SOURCE_ROOT).ino=88888                                    # another directory now stands at the source root's name
        original=host.docker.run
        def run_(args,stdin=None,environment=None):
            result=original(args,stdin,environment)
            if args[:1]==['create']:after(None)
            return result
        host.docker.run=run_
    receipt,host,docs=run('publish_launch',swap)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'MOUNT_SOURCE_REPLACED_BEFORE_START','START')
    assert receipt['mount_sources_replaced']==['SOURCE'] and receipt['created_container_removed'] is True and host.docker.started==[]
    assert [argv[0] for argv in effect_argv(host)]==['rm','create','rm'] and 'c3po-k9-20261006-publish_launch' not in k9_names(host)
    assert node(host,k9w.day_path('launches','publish_launch.json')) is None and receipt['mutating_calls']['uncertain']==0
    def after_start(host):host.docker.on_start=lambda item:setattr(node(host,k9w.SOURCE_ROOT),'ino',77777)
    receipt,host,docs=run('publish_launch',after_start)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'MOUNT_SOURCE_REPLACED_AROUND_START') and receipt['mount_sources_replaced_after_start']==['SOURCE']
    # a launch that does not mount the source root does not depend on it after its prechecks
    def swap_late(host):host.docker.on_start=lambda item:setattr(node(host,k9w.SOURCE_ROOT),'ino',77777)
    receipt,host,docs=run('sources_launch',swap_late);assert receipt['status']==COMPLETE
    def before_stage(host):
        original=host.docker.run
        def run_(args,stdin=None,environment=None):
            if args[:1]==['rm']:node(host,k9w.SOURCE_ROOT).ino=66666
            return original(args,stdin,environment)
        host.docker.run=run_
    receipt,host,docs=run('stage',before_stage)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'MOUNT_SOURCE_REPLACED_BEFORE_START') and host.docker.attached==[]

def test_attached_results():
    m=load().m
    def attached(**options):
        def change(host):host.docker.on_run=k9w.Attached(**options)
        return change
    receipt,host,docs=run('bind',attached(returncode=1,failed=True))
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(PARTIAL,'K9_STEP_RAN_NOT_COMPLETE','STEP_FAILED_SYNTHETIC') and receipt['mutating_calls']['uncertain']==0
    receipt,host,docs=run('bind',attached(returncode=0,receipt=False))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE')
    receipt,host,docs=run('bind',attached(returncode=1))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'EXIT_CODE_CONTRADICTS_THE_RECEIPT')
    receipt,host,docs=run('bind',attached(returncode=125,receipt=False,marker=False))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_ENGINE_REFUSED') and receipt['mutating_calls']['uncertain']==0
    assert receipt['receipt']['engine_refused'] is True and receipt['mutating_calls']['failed_nothing_changed']==1
    for options in ({'documents':{'OWNER_ORDER.json':b'{"other":1}'}},                                   # another owner order
                    {'claimed':{'day/risk/plan/SOURCE_PINS.json':'ab'*32}},                              # other source pins
                    {'claimed':{'day/risk/plan/HOST_PLAN.json':'ab'*32}},                                # a plan hash the file does not have
                    {'claimed':{'day/risk/plan/GO.json':'ab'*32}},{'claimed':{'day/risk/plan/OWNER_ORDER.json':k9w.sha(b'x')}}):
        receipt,host,docs=run('bind',attached(**options))
        assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE'),options
    def knob(**values):
        def change(host):
            host.docker.on_run=k9w.Attached()
            for key,value in values.items():setattr(host.docker.on_run,key,value)
        return change
    receipt,host,docs=run('bind',knob(no_spool=True));assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE')
    receipt,host,docs=run('stage',knob(risk=b'{"other":1}'));assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE')
    receipt,host,docs=run('stage',knob(during=lambda call:setattr(call.docker.host.tree.get(k9w.SOURCE_ROOT),'ino',55555)))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'MOUNT_SOURCE_REPLACED_AROUND_THE_RUN') and receipt['mount_sources_replaced_after_run']==['SOURCE']
    receipt,host,docs=run('bind',attached(returncode=1,receipt=False,marker=False))                       # not the engine's status: the step ran
    assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE') and receipt['receipt']['engine_refused'] is False
    for line in (b'',b'{}\n',b'x\n','STRIPPED'):
        receipt,host,docs=run('bind',attached(line=line))
        assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RESULT_LINE_NOT_THE_RECEIPT') and receipt['receipt']['result_line_is_the_receipt'] is False
    receipt,host,docs=run('stage',attached(line=b''))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RESULT_LINE_NOT_THE_RECEIPT')
    receipt,host,docs=run('bind',attached(changes={'step_plan_sha256':'ab'*32}))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE')
    receipt,host,docs=run('bind',lambda host:host.hang_after.add(('run','--rm')))
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==(PARTIAL,'COMMAND_TIMEOUT','ATTACHED') and receipt['mutating_calls']['uncertain']==1
    receipt,host,docs=run('bind',lambda host:host.absent.add(('run','--rm')))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'COMMAND_NOT_STARTED') and receipt['mutating_calls']['uncertain']==0
    receipt,host,docs=run('preflight',attached(returncode=2,receipt=False,failed=True))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'PHASE_OUTSIDE_WINDOW')
    def marker_of_another_plan(host):
        original=k9w.Attached()
        def run_(call):
            code,out=original(call);base=k9w.spool('preflight.STARTED.json')
            node=host.tree.get(base);node.content=bytearray(k9w.canonical({'phase':'preflight','manifest_sha256':'ab'*32,'go_sha256':'cd'*32,'started_at':k9w.GRID['preflight']}))
            return code,out
        host.docker.on_run=run_
    receipt,host,docs=run('preflight',marker_of_another_plan)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE')
    receipt,host,docs=run('preflight',attached(changes={'namespace':'R2D2-V2-SHADOW-2026-10-06'}))
    assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE')
    def wrong_risk(host):
        host.docker.on_run=k9w.Attached()
        original=host.docker.on_run
        def run_(call):
            code,out=original(call);call.docker.host.tree.get(k9w.SOURCE_ROOT+'/components/'+k9w.DAY+'/risk.json').content=bytearray(b'other');return code,out
        host.docker.on_run=run_
    receipt,host,docs=run('stage',wrong_risk)
    assert (receipt['status'],receipt['code'])==(PARTIAL,'ATTACHED_RECEIPT_NOT_COMPLETE') and receipt['removed'] is True

# ---------------------------------------------------------------- privacy and what is never done
def test_no_secret_is_read_or_printed_and_nothing_but_the_signed_commands_runs():
    for operation in sorted(k9w.WRITE):
        receipt,host,docs=run(operation);line=f.line(receipt)
        assert k9w.CANARY.encode() not in line and hostemu.SECRET.encode() not in line and b'never-emit' not in line
        secret_paths={k9w.PLACEMENT[key] for key in ('provider_env_file','risk_db_env_file','emitter_password')}
        assert not [entry for entry in host.log if entry[0] in ('open','read') and entry[1] in secret_paths],operation
        verbs=[entry['argv'][1:3] for entry in host.commands]
        assert all(verb[0] in ('image','container','ps','create','start','rm','run') for verb in verbs)
        assert not [entry for entry in host.commands if set(entry['argv'])&{'-f','--force','-v','--volumes','exec','kill','stop','--privileged'}]
        assert all(entry['variables']=={} and entry['docker_config'] is None and entry['stdin'] is None for entry in host.commands)
        assert host.fds=={}
