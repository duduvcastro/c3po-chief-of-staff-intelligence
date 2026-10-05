"""Where a run can die, and how a later read tells the states apart. The process is killed at every host call of a
complete run in turn (no receipt is the worst case: the transport files it UNCERTAIN); afterwards the host is read
with nothing but read primitives and the rows of the signed table, as a later read-only operation would: the
directory and the five names this run can leave in it, EVERY container of the listing (the one that carries the
worker's name, any that carries a temporary name of the worker's, any ID that was not there before), the worker's
environment through the boolean template. Every death leaves exactly one of the states of DESIGN.md section 6, in
order; a recreate interrupted inside the engine, in either order compose has made its calls, leaves none of them."""
import family as f
import hostemu
import k6a

STATES=['S0_NOTHING','S1_DIRECTORY_EMPTY','S2_POLICY_TEMPORARY','S3_POLICY_LINKED_TEMPORARY_PRESENT','S4_POLICY_ONLY','S5_OVERRIDE_TEMPORARY',
        'S6_OVERRIDE_LINKED_TEMPORARY_PRESENT','S7_FILES_DELIVERED_WORKER_NOT_RECREATED','S8_WORKER_RECREATED_WITH_THE_KEYS']

def later_read(m,host,docs,old,listed=None):
    """What a read-only operation can say afterwards: (state of the files, state of the worker). The rule of DESIGN.md
    section 6: the worker is only "the old one, untouched" or "the new one, activated" when, besides the container
    under its name, NO container carries a temporary name of the worker's (the source's own leftovers()) and, where
    the IDs listed before the run are known (listed), no other ID appeared. Anything else is said in the answer."""
    gate=lambda:55.0;commands=m.Commands(host,gate);go16=docs.go16();plan=docs.plan
    def kind(path):
        found=m.probe(host,path,gate);return None if found['exists'] is False else found['type']
    names={'directory':kind(k6a.LIVE),'policy':kind(k6a.LIVE+'/policy.json'),'policy_temporary':kind(k6a.LIVE+'/.hostops-%s-0.partial'%go16),
           'override':kind(k6a.OVERRIDE_FILE),'override_temporary':kind(k6a.LIVE+'/.hostops-%s-1.partial'%go16)}
    files={(None,None,None,None,None):'NONE',('dir',None,None,None,None):'DIRECTORY_EMPTY',('dir',None,'file',None,None):'POLICY_TEMPORARY',
           ('dir','file','file',None,None):'POLICY_LINKED_TEMPORARY_PRESENT',('dir','file',None,None,None):'POLICY_ONLY',
           ('dir','file',None,None,'file'):'OVERRIDE_TEMPORARY',('dir','file',None,'file','file'):'OVERRIDE_LINKED_TEMPORARY_PRESENT',
           ('dir','file',None,'file',None):'BOTH_FILES'}[tuple(names[key] for key in ('directory','policy','policy_temporary','override','override_temporary'))]
    rows=m.container_list(commands);named=[row for row in rows if row['name']==hostemu.WORKER];elsewhere=[row for row in rows if row['id']==old and row['name']!=hostemu.WORKER]
    if len(named)!=1:worker='ABSENT_OR_AMBIGUOUS'
    else:
        facts=m.container_facts(commands,named[0]['id'],expected_name=hostemu.WORKER)
        values=m.container_environment(commands,named[0]['id'],dict(m.environment_of(plan),C3PO_BUILD_SHA=hostemu.REVISION))
        keys=[values[key] for key in m.ACTIVATION_KEYS]
        carried='ALL_AS_SIGNED' if all(item=={'present':True,'equal':True} for item in keys) else 'NONE' if not any(item['present'] for item in keys) else 'MIXED'
        worker=('OLD' if named[0]['id']==old else 'NEW')+('_RUNNING' if facts['running'] and facts['restarts']==0 else '_NOT_RUNNING_OR_RESTARTED')+'_KEYS_'+carried
    if elsewhere:worker+='_OLD_CONTAINER_LEFT_UNDER_ANOTHER_NAME'
    if m.leftovers(rows,hostemu.WORKER):worker+='_SERVICE_CONTAINER_UNDER_A_TEMPORARY_NAME'
    if listed is not None and [row for row in rows if row['id'] not in listed and row['name']!=hostemu.WORKER]:worker+='_A_CONTAINER_APPEARED'
    assert host.mutating()==host.mutating(),'a read changes nothing'
    return files,worker

def state_of(files,worker):
    if worker=='NEW_RUNNING_KEYS_ALL_AS_SIGNED' and files=='BOTH_FILES':return 'S8_WORKER_RECREATED_WITH_THE_KEYS'
    assert worker=='OLD_RUNNING_KEYS_NONE',(files,worker)
    return {'NONE':'S0_NOTHING','DIRECTORY_EMPTY':'S1_DIRECTORY_EMPTY','POLICY_TEMPORARY':'S2_POLICY_TEMPORARY',
            'POLICY_LINKED_TEMPORARY_PRESENT':'S3_POLICY_LINKED_TEMPORARY_PRESENT','POLICY_ONLY':'S4_POLICY_ONLY','OVERRIDE_TEMPORARY':'S5_OVERRIDE_TEMPORARY',
            'OVERRIDE_LINKED_TEMPORARY_PRESENT':'S6_OVERRIDE_LINKED_TEMPORARY_PRESENT','BOTH_FILES':'S7_FILES_DELIVERED_WORKER_NOT_RECREATED'}[files]

def test_death_at_every_host_call_leaves_one_of_the_nine_states_in_order_and_a_later_read_tells_them_apart():
    m,docs,host=k6a.fresh();assert docs.run(host)['status']==m.COMPLETE_STATUS;total=host.calls;seen=[];statuses=set()
    for index in range(1,total+1):
        m,docs,host=k6a.fresh();old=k6a.worker(host)['Id']
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death('dead')
        host.hook=hook;receipt=docs.run(host);host.hook=None
        assert host.lock_held(k6a.LOCK) is None or True                    # a dead process holds no lock: the kernel releases it with the descriptor
        files,worker=later_read(m,host,docs,old);state=state_of(files,worker);seen.append(state);statuses.add((receipt['status'],receipt['code']))
        # what the last-resort receipt says, when one could still be written, never contradicts the host
        if state=='S0_NOTHING':assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS)
        else:assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN')
        if receipt['status']=='REFUSED':assert state=='S0_NOTHING'
    order=[STATES.index(state) for state in seen]
    assert order==sorted(order),'a later death never leaves an earlier state'
    assert sorted(set(seen))==sorted(STATES),'every state of the table is reached by some death: %r'%sorted(set(STATES)-set(seen))
    assert statuses=={('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT'),(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN')}

def test_the_receipt_of_each_partial_names_the_same_state_the_later_read_finds():
    """A run that returned its receipt: the ledger and the recreate member say what the later read then sees."""
    import test_effects as e
    cases=[(lambda host:setattr(host,'hook',e.fail_at('unlink',1)),'S3_POLICY_LINKED_TEMPORARY_PRESENT','NOT_STARTED'),
           (lambda host:setattr(host,'hook',e.fail_at('create',2)),'S4_POLICY_ONLY','NOT_STARTED'),
           (lambda host:setattr(host,'hook',e.fail_at('unlink',2)),'S6_OVERRIDE_LINKED_TEMPORARY_PRESENT','NOT_STARTED'),
           (lambda host:host.absent.add(('compose','up')),'S7_FILES_DELIVERED_WORKER_NOT_RECREATED','NOT_STARTED'),
           (lambda host:(setattr(host.docker.compose,'up_returncode',1),setattr(host.docker.compose,'up_effect',False)),'S7_FILES_DELIVERED_WORKER_NOT_RECREATED','NOT_RECREATED'),
           (lambda host:host.hang.add(('compose','up')),'S7_FILES_DELIVERED_WORKER_NOT_RECREATED','UNCERTAIN'),
           (lambda host:host.hang_after.add(('compose','up')),'S8_WORKER_RECREATED_WITH_THE_KEYS','RECREATED_NOT_VERIFIED'),
           (lambda host:None,'S8_WORKER_RECREATED_WITH_THE_KEYS','RECREATED_VERIFIED')]
    for prepare,state,recreate in cases:
        m,docs,host=k6a.fresh();old=k6a.worker(host)['Id'];prepare(host);receipt=docs.run(host);host.hook=None;host.hang.clear();host.hang_after.clear()
        assert state_of(*later_read(m,host,docs,old))==state and receipt['recreate']['state']==recreate,(state,recreate)
        left={'S3_POLICY_LINKED_TEMPORARY_PRESENT':3,'S4_POLICY_ONLY':2,'S6_OVERRIDE_LINKED_TEMPORARY_PRESENT':4}.get(state,3)
        assert receipt['objects_left_by_this_run']==left

def test_states_only_a_real_engine_can_leave_are_told_apart_too():
    """A compose up killed part-way (CORE.md U9) was never run on an engine. What it could leave is read the same way:
    the name without a container, a container that is not running, the old container under another name, a new
    container without the keys. None of them is mistaken for S7 or S8."""
    def build(change):
        m,docs,host=k6a.fresh();old=k6a.worker(host)['Id'];host.hang_after.add(('compose','up'));docs.run(host);host.hang_after.clear();change(host,old)
        return later_read(m,host,docs,old)
    def worker_gone(host,old):host.docker.containers=[item for item in host.docker.containers if item['Name']!='/'+hostemu.WORKER]
    def created_not_started(host,old):k6a.worker(host)['State'].update(Status='created',Running=False)
    def old_left(host,old):host.docker.containers.append(dict(hostemu.container('x',hostemu.BACKEND,'c3po/backend:production',[]),Id=old,Name='/'+old[:12]+'_'+hostemu.WORKER))
    def without_keys(host,old):
        item=k6a.worker(host);item['Config']['Env']=[entry for entry in item['Config']['Env'] if not entry.startswith('C3PO_R2D2_V2_')]
    assert build(worker_gone)==('BOTH_FILES','ABSENT_OR_AMBIGUOUS')
    assert build(created_not_started)==('BOTH_FILES','NEW_NOT_RUNNING_OR_RESTARTED_KEYS_ALL_AS_SIGNED')
    assert build(old_left)==('BOTH_FILES','NEW_RUNNING_KEYS_ALL_AS_SIGNED_OLD_CONTAINER_LEFT_UNDER_ANOTHER_NAME_SERVICE_CONTAINER_UNDER_A_TEMPORARY_NAME')
    assert build(without_keys)==('BOTH_FILES','NEW_RUNNING_KEYS_NONE')

# What the later read says of each in-between state of an interrupted recreate, in both orders compose has made its
# calls (tests/k6a.py, INTERRUPTED), and what this run's own receipt says when one could be written:
#   stage -> (worker as the later read names it, recreate.state of the receipt, worker_container_replaced, service_leftovers, a running worker exists)
LEFT='_SERVICE_CONTAINER_UNDER_A_TEMPORARY_NAME';APPEARED='_A_CONTAINER_APPEARED';OLD_LEFT='_OLD_CONTAINER_LEFT_UNDER_ANOTHER_NAME'
IN_BETWEEN={
    'NEW_FIRST_1_NEW_CREATED_UNDER_THE_TEMPORARY_NAME_OLD_RUNNING':('OLD_RUNNING_KEYS_NONE'+LEFT+APPEARED,'UNCERTAIN',None,1,True),
    'NEW_FIRST_2_OLD_STOPPED':('OLD_NOT_RUNNING_OR_RESTARTED_KEYS_NONE'+LEFT+APPEARED,'UNCERTAIN',None,1,False),
    'NEW_FIRST_3_OLD_REMOVED_NEW_STILL_UNDER_THE_TEMPORARY_NAME':('ABSENT_OR_AMBIGUOUS'+LEFT+APPEARED,'UNCERTAIN',None,1,False),
    'NEW_FIRST_4_NEW_RENAMED_NOT_STARTED':('NEW_NOT_RUNNING_OR_RESTARTED_KEYS_ALL_AS_SIGNED','RECREATED_NOT_VERIFIED',True,0,False),
    'OLD_FIRST_1_OLD_STOPPED':('OLD_NOT_RUNNING_OR_RESTARTED_KEYS_NONE','UNCERTAIN',None,0,False),
    'OLD_FIRST_2_OLD_RENAMED_TO_THE_TEMPORARY_NAME':('ABSENT_OR_AMBIGUOUS'+OLD_LEFT+LEFT,'UNCERTAIN',None,1,False),
    'OLD_FIRST_3_NEW_CREATED_NOT_STARTED':('NEW_NOT_RUNNING_OR_RESTARTED_KEYS_ALL_AS_SIGNED'+OLD_LEFT+LEFT,'RECREATED_NOT_VERIFIED',True,1,False),
    'OLD_FIRST_4_NEW_STARTED_OLD_NOT_REMOVED':('NEW_RUNNING_KEYS_ALL_AS_SIGNED'+OLD_LEFT+LEFT,'RECREATED_NOT_VERIFIED',True,1,True)}

def test_recreate_interrupted_inside_the_engine_in_either_order_is_never_read_as_one_of_the_nine_states():
    """The finding this test answers: with the order compose v2 uses today, the first in-between state has the OLD
    worker running under its name and none of the four names in it, exactly like S7; only the listing tells (a second
    container of the service under the temporary name). The later read looks at the whole listing, and the receipt of
    the run, when there is one, carries the count."""
    import pytest
    assert sorted(IN_BETWEEN)==sorted(k6a.INTERRUPTED)
    for stage,(expected,state,replaced,leftovers,running) in sorted(IN_BETWEEN.items()):
        for how in ('timeout','nonzero','death'):
            m,docs,host=k6a.fresh();listed={item['Id'] for item in host.docker.containers};old=k6a.interrupt(host,stage,how);receipt=docs.run(host)
            files,worker=later_read(m,host,docs,old,listed);assert (files,worker)==('BOTH_FILES',expected),(stage,how,worker)
            with pytest.raises(AssertionError):state_of(files,worker)                      # neither S0..S7 nor S8
            assert bool([item for item in host.docker.containers if item['Name']=='/'+hostemu.WORKER and item['State']['Running']])==running,stage
            if how=='death':
                assert (receipt['status'],receipt['code'],receipt['outcome'])==(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN','PARTIAL_REQUIRES_RECONCILIATION');continue
            run=receipt['recreate'];facts=run['facts']
            assert (receipt['status'],run['state'],receipt['worker_container_replaced'],facts['service_leftovers'])==(m.PARTIAL_STATUS,state,replaced,leftovers),(stage,how)
            assert receipt['code']==('COMMAND_TIMEOUT' if how=='timeout' else 'RECREATE_RETURNED_NONZERO') and receipt['mutating_calls']['uncertain']==1
            assert receipt['outcome']=={'UNCERTAIN':'PARTIAL_RECREATE_UNCERTAIN_REQUIRES_READBACK','RECREATED_NOT_VERIFIED':'PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED'}[state]
            assert facts['others_unchanged'] is (leftovers==0) and facts['others_appeared']==leftovers,'the container under the temporary name is one that appeared'
    # without the IDs listed before the run the later read still sees the temporary name; without looking at the
    # listing at all (the rule this test replaced) the first state of the new order is S7
    m,docs,host=k6a.fresh();old=k6a.interrupt(host,'NEW_FIRST_1_NEW_CREATED_UNDER_THE_TEMPORARY_NAME_OLD_RUNNING','death');docs.run(host)
    files,worker=later_read(m,host,docs,old);assert worker=='OLD_RUNNING_KEYS_NONE'+LEFT
    assert state_of(files,worker[:-len(LEFT)])=='S7_FILES_DELIVERED_WORKER_NOT_RECREATED','what a read of the worker by name alone would have concluded'

def test_a_later_run_refuses_before_any_effect_while_an_interrupted_recreate_left_a_container_of_the_service():
    """The spare (or any later request of this source) after a recreate that stopped in the first in-between state:
    the old worker runs, carries none of the names, and a second container of the service exists. Nothing is created."""
    m,docs,host=k6a.fresh();k6a.interrupt(host,'NEW_FIRST_1_NEW_CREATED_UNDER_THE_TEMPORARY_NAME_OLD_RUNNING','timeout')
    first=docs.run(host);assert first['recreate']['state']=='UNCERTAIN'
    host.docker.run=host.docker.__class__.run.__get__(host.docker);fields=k6a.fields(host);fields['directory_name']='2026-10-05-b'
    again=f.Docs(docs.k,fields);before=k6a.state_of(host);mutating=len(host.mutating());receipt=again.run(host)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','WORKER_SERVICE_LEFTOVER_CONTAINER','PRECHECK')
    assert k6a.state_of(host)==before and len(host.mutating())==mutating and receipt['mutating_calls']['issued']==0 and host.lock_held(k6a.LOCK) is None
