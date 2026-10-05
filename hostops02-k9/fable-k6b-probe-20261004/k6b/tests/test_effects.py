"""K6b, every way the run can end after the precheck: the editor not started, refusing, lying, hanging before or after
its effect, replacing the file; the render after the edit not as signed (the edit withdrawn, or the withdrawal
failing); the recreate not started, failing with nothing changed, timing out before or after its effect; each
criterion after the recreate broken alone; and the death of the process at every host call of a complete run, after
which a read of the host finds one of the three states the order of the effects allows."""
import json

import pytest

import family as f
import hostemu
import k6b

def run(mode='MOUNT',prepare=None,state=None):
    m,docs,host=k6b.fresh(mode,state=state);before=k6b.env_bytes(host);old=k6b.worker(host)['Id']
    if prepare is not None:prepare(host)
    receipt=docs.run(host)
    assert hostemu.SECRET not in json.dumps(receipt) and f.sha(before) not in json.dumps(receipt)
    assert host.fds=={} and not host.lock_held(k6b.LOCK)
    return m,receipt,host,before,old

def edited(host,mode):return k6b.env_bytes(host)==k6b.expected_env(host,k6b.AFTER[mode])

# ---------------------------------------------------------------- the editor
def test_editor_not_started_is_a_refusal_with_nothing_changed():
    m,receipt,host,before,old=run(prepare=lambda host:host.absent.add(('run','--rm')))
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('REFUSED',m.REFUSED_OUTCOME,'COMMAND_NOT_STARTED')
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0}
    assert k6b.env_bytes(host)==before and k6b.worker(host)['Id']==old and receipt['env_file_after']=='UNCHANGED' and receipt['phase_reached']=='EFFECTS'

def test_editor_that_refuses_changes_nothing():
    """Something appended a line after the precheck read the file: the editor finds the block no longer trailing."""
    def prepare(host):host.editor.before=lambda host:host.tree.get(hostemu.ENV_FILE).content.extend(b'C3PO_RACE=1\n')
    m,receipt,host,before,old=run('ENABLE',prepare=prepare)
    # the editor refused and wrote nothing, but the file is no longer the one read: the run cannot say nothing changed
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW',m.UNCERTAIN_OUTCOME,'ENV_FILE_NOT_AS_EDITED')
    assert receipt['env_edit']['status']=='ENV_EDIT_REFUSED' and receipt['env_edit']['code']=='ENV_CAPACITY_LINES_NOT_TRAILING' and receipt['env_edit']['state']=='OTHER'
    assert k6b.worker(host)['Id']==old

def test_editor_refusal_on_an_unchanged_file_says_its_code():
    def prepare(host):host.editor.effect=False;host.editor.returncode=1;host.editor.output=b'{"code": "ENV_CAPACITY_BLOCK_NOT_AS_SIGNED", "status": "ENV_EDIT_REFUSED"}\n'
    m,receipt,host,before,old=run(prepare=prepare)
    assert (receipt['status'],receipt['code'])==('REFUSED','ENV_CAPACITY_BLOCK_NOT_AS_SIGNED') and k6b.env_bytes(host)==before
    assert receipt['env_edit']=={'started':True,'returned':True,'returncode':1,'status':'ENV_EDIT_REFUSED','code':'ENV_CAPACITY_BLOCK_NOT_AS_SIGNED','state':'UNCHANGED'}

def test_editor_that_says_done_and_did_nothing():
    """An unchanged file after an editor that did not say it refused is not 'nothing changed' (it may have edited another file)."""
    def prepare(host):host.editor.effect=False
    m,receipt,host,before,old=run(prepare=prepare)
    assert (receipt['outcome'],receipt['code'],receipt['env_file_after'])==(m.UNCERTAIN_OUTCOME,'ENV_EDIT_FILE_UNCHANGED','UNKNOWN')
    assert receipt['mutating_calls']['uncertain']==1 and k6b.worker(host)['Id']==old and k6b.env_bytes(host)==before

def test_editor_that_edits_and_says_something_else():
    for output,returncode in ((b'garbage\n',0),(b'{"code": null, "status": "ENV_EDIT_DONE"}\n',3),(b'{"code": null, "status": "ENV_EDIT_DONE"}\n{}\n',0),
                              (b'{"code": "lower case", "status": "ENV_EDIT_DONE"}\n',0),(b'{"status": "ENV_EDIT_DONE"}\n',0),(b'{"code": null, "status": "OTHER"}\n',0)):
        def prepare(host,output=output,returncode=returncode):host.editor.output=output;host.editor.returncode=returncode
        m,receipt,host,before,old=run(prepare=prepare)
        # the file is as edited but the editor did not confirm it: no withdrawal is inferred; the edit stays, said so
        assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW',m.ENV_ONLY_OUTCOME,'ENV_EDIT_STATUS_NOT_DONE'),output
        assert edited(host,'MOUNT') and k6b.worker(host)['Id']==old and receipt['env_file_after']=='EDITED' and receipt['failure_phase']=='BEFORE_THE_RECREATE'
        assert receipt['recreate']['state']=='NOT_STARTED' and receipt['env_withdraw']['state']=='NOT_STARTED'
        assert receipt['mutating_calls']['uncertain']>=1                       # an edit the editor did not confirm is never settled as done

def test_editor_that_writes_other_bytes_or_replaces_the_file():
    def other(host):host.editor.after=lambda host:host.tree.get(hostemu.ENV_FILE).content.extend(b'C3PO_MORE=1\n')
    m,receipt,host,before,old=run(prepare=other)
    assert (receipt['outcome'],receipt['code'],receipt['env_file_after'])==(m.UNCERTAIN_OUTCOME,'ENV_FILE_NOT_AS_EDITED','UNKNOWN') and k6b.worker(host)['Id']==old
    def replaced(host):host.editor.after=lambda host:setattr(host.tree.get(hostemu.ENV_FILE),'ino',123456)
    m,receipt,host,before,old=run(prepare=replaced)
    assert (receipt['outcome'],receipt['code'])==(m.UNCERTAIN_OUTCOME,'ENV_FILE_NOT_AS_EDITED')
    def owner(host):host.editor.after=lambda host:setattr(host.tree.get(hostemu.ENV_FILE),'uid',0)
    m,receipt,host,before,old=run(prepare=owner)
    assert (receipt['outcome'],receipt['code'])==(m.UNCERTAIN_OUTCOME,'ENV_FILE_NOT_AS_EDITED')
    def gone(host):host.editor.after=lambda host:host.tree.remove(hostemu.ENV_FILE)
    m,receipt,host,before,old=run(prepare=gone)
    assert (receipt['outcome'],receipt['code'])==(m.UNCERTAIN_OUTCOME,'ENV_FILE_UNREADABLE_AFTER_THE_EDIT')

def test_editor_that_hangs_before_or_after_its_effect_is_uncertain():
    m,receipt,host,before,old=run(prepare=lambda host:host.hang.add(('run','--rm')))
    assert (receipt['outcome'],receipt['env_file_after'])==(m.UNCERTAIN_OUTCOME,'UNKNOWN') and receipt['code']=='COMMAND_TIMEOUT'
    assert receipt['mutating_calls']=={'issued':1,'succeeded':0,'failed_nothing_changed':0,'uncertain':1}
    assert receipt['env_edit']['state']=='UNCHANGED' and receipt['env_edit']['returned'] is False and k6b.worker(host)['Id']==old
    assert receipt['env_edit']['container_left'] is False                     # the emulated engine lists no container of that name
    m,receipt,host,before,old=run(prepare=lambda host:host.hang_after.add(('run','--rm')))
    assert (receipt['outcome'],receipt['env_file_after'])==(m.UNCERTAIN_OUTCOME,'UNKNOWN') and receipt['env_edit']['state']=='EDITED'
    assert receipt['mutating_calls']['uncertain']==1 and k6b.worker(host)['Id']==old and receipt['env_withdraw']['state']=='NOT_STARTED'
    # a container of the editor's name still listed after its CLI was killed is said
    def left(host):
        host.hang_after.add(('run','--rm'))
        host.editor.before=lambda h:h.docker.containers.append(hostemu.container('hostops02-k6b-'+'x'*16,hostemu.BACKEND,'c3po/backend:production',[]))
    m,docs,host=k6b.fresh('MOUNT');left(host)
    def named(h):
        for item in h.docker.containers:
            if item['Name'].startswith('/hostops02-k6b-'):item['Name']='/hostops02-k6b-'+docs.go16()
    host.editor.after=named;receipt=docs.run(host)
    assert receipt['env_edit']['container_left'] is True and receipt['outcome']==m.UNCERTAIN_OUTCOME

# ---------------------------------------------------------------- the render after the edit, and the withdrawal
def second_render(change):
    def prepare(host):
        def reply(real):
            code,out=real();value=json.loads(out);change(value);return code,json.dumps(value).encode()+b'\n'
        k6b.answer(host,k6b.is_render,reply,nth=2)
    return prepare
def wrong_mount(value):
    for item in value['services']['r2d2-worker']['volumes']:
        if item['target']=='/c3po-capacity':item.update(read_only=False)

@pytest.mark.parametrize('mode',('MOUNT','ENABLE','DISABLE_FAST','DISABLE_FULL'))
def test_render_after_the_edit_not_as_signed_withdraws_the_edit(mode):
    m,receipt,host,before,old=run(mode,second_render(wrong_mount))
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW',m.WITHDRAWN_OUTCOME,'RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED')
    assert k6b.env_bytes(host)==before and k6b.worker(host)['Id']==old and receipt['env_file_after']=='RESTORED'
    assert receipt['env_withdraw']['state']=='EDITED' and receipt['mutating_calls']=={'issued':2,'succeeded':2,'failed_nothing_changed':0,'uncertain':0}
    assert host.editor.calls[1]['before']==[k6b.BLOCK[:k6b.AFTER[mode]]] and host.editor.calls[1]['after']==k6b.BLOCK[:k6b.BEFORE[mode]]
    assert not [entry for entry in host.commands if 'up' in entry['argv']]

def test_render_after_the_edit_that_fails_or_drops_a_name():
    m,receipt,host,before,old=run(prepare=lambda host:k6b.answer(host,k6b.is_render,lambda real:(1,b''),nth=2))
    assert (receipt['outcome'],receipt['code'])==(m.WITHDRAWN_OUTCOME,'COMMAND_FAILED') and k6b.env_bytes(host)==before
    m,receipt,host,before,old=run(prepare=second_render(lambda value:value['services']['r2d2-worker']['environment'].pop('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE')))
    assert (receipt['outcome'],receipt['code'])==(m.WITHDRAWN_OUTCOME,'RENDER_CAPACITY_ENVIRONMENT_MISMATCH')
    def image(value):value['services']['r2d2-worker']['image']='c3po/backend:rollback'
    m,receipt,host,before,old=run(prepare=second_render(image))
    assert (receipt['outcome'],receipt['code'])==(m.WITHDRAWN_OUTCOME,'RENDER_IMAGE_CHANGED')

def test_withdrawal_that_does_nothing_or_does_not_start():
    def nothing(host):
        second_render(wrong_mount)(host);host.editor.after=lambda host:setattr(host.editor,'effect',False)
    m,receipt,host,before,old=run(prepare=nothing)
    assert (receipt['outcome'],receipt['code'],receipt['env_file_after'])==(m.ENV_ONLY_OUTCOME,'RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','EDITED')
    assert receipt['env_withdraw']['state']=='UNCHANGED' and edited(host,'MOUNT')
    def absent(host):
        second_render(wrong_mount)(host);host.editor.after=lambda host:host.absent.add(('run','--rm'))
    m,receipt,host,before,old=run(prepare=absent)
    assert (receipt['outcome'],receipt['env_file_after'])==(m.ENV_ONLY_OUTCOME,'EDITED') and receipt['env_withdraw']['state']=='NOT_STARTED'
    def hangs(host):
        second_render(wrong_mount)(host);host.editor.after=lambda host:host.hang.add(('run','--rm'))
    m,receipt,host,before,old=run(prepare=hangs)
    assert (receipt['outcome'],receipt['env_file_after'])==(m.UNCERTAIN_OUTCOME,'UNKNOWN')
    def other(host):
        second_render(wrong_mount)(host);calls=[0]
        def after(host):
            calls[0]+=1
            if calls[0]==2:host.tree.get(hostemu.ENV_FILE).content.extend(b'C3PO_MORE=1\n')
        host.editor.after=after
    m,receipt,host,before,old=run(prepare=other)
    assert (receipt['outcome'],receipt['env_file_after'])==(m.UNCERTAIN_OUTCOME,'UNKNOWN') and receipt['env_withdraw']['state']=='OTHER'

def test_lock_replaced_during_the_edit():
    def prepare(host):host.editor.after=lambda host:k6b.replace(host,k6b.LOCK,'file',uid=1000,gid=1000,mode=0o644)
    m,receipt,host,before,old=run(prepare=prepare)
    # the lock is no longer provably held: no second edit; the file stays as edited and the receipt says so
    assert (receipt['outcome'],receipt['code'],receipt['env_file_after'])==(m.ENV_ONLY_OUTCOME,'LOCK_FILE_REPLACED','EDITED') and edited(host,'MOUNT')
    assert receipt['env_withdraw']['state']=='NOT_STARTED'

def test_a_directory_swapped_right_before_the_recreate():
    for path,code in ((k6b.LIVE,'OVERRIDE_DIRECTORY_REPLACED'),(hostemu.LOCK_DIRECTORY,'LOCK_DIRECTORY_REPLACED'),(hostemu.DEPLOY+'/c3po','DEPLOY_TREE_REPLACED')):
        def prepare(host,path=path):k6b.during(host,k6b.is_render,lambda host:setattr(host.tree.get(path),'ino',5151),nth=2)
        m,receipt,host,before,old=run(prepare=prepare)
        assert (receipt['outcome'],receipt['code'])==(m.WITHDRAWN_OUTCOME,code) and k6b.env_bytes(host)==before and k6b.worker(host)['Id']==old

# ---------------------------------------------------------------- the recreate
def test_recreate_not_started_withdraws_the_edit_a_recreate_that_ran_never_does():
    m,receipt,host,before,old=run(prepare=lambda host:host.absent.add(('compose','up')))
    assert (receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.WITHDRAWN_OUTCOME,'COMMAND_NOT_STARTED','NOT_STARTED') and k6b.env_bytes(host)==before
    assert receipt['failure_phase']=='BEFORE_THE_RECREATE'
    # after the recreate was started: a separate state, no rollback inferred from what it did
    def failing(host):host.docker.compose.up_returncode=1;host.docker.compose.up_effect=False
    m,receipt,host,before,old=run(prepare=failing)
    assert (receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.RECREATE_FAILED_OUTCOME,'RECREATE_FAILED_CONTAINER_UNCHANGED','NOT_RECREATED')
    assert receipt['worker_container_replaced'] is False and k6b.worker(host)['Id']==old and edited(host,'MOUNT')
    assert receipt['env_withdraw']['state']=='NOT_STARTED' and receipt['failure_phase']=='AFTER_THE_RECREATE_STARTED' and receipt['env_file_after']=='EDITED'
    def silent(host):host.docker.compose.up_effect=False
    m,receipt,host,before,old=run(prepare=silent)
    assert (receipt['outcome'],receipt['code'])==(m.RECREATE_FAILED_OUTCOME,'RECREATE_RETURNED_ZERO_CONTAINER_UNCHANGED') and edited(host,'MOUNT')
    # the withdrawal itself not started: the edit stays, said so
    def both(host):host.absent.add(('compose','up'));host.docker.compose.after_up=None;host.editor.after=lambda h:h.absent.add(('run','--rm'))
    m,receipt,host,before,old=run(prepare=both)
    assert (receipt['outcome'],receipt['env_file_after'])==(m.ENV_ONLY_OUTCOME,'EDITED') and edited(host,'MOUNT')

def test_recreate_that_times_out():
    m,receipt,host,before,old=run(prepare=lambda host:host.hang.add(('compose','up')))
    assert (receipt['outcome'],receipt['recreate']['state'])==(m.UNCERTAIN_OUTCOME,'UNCERTAIN') and receipt['worker_container_replaced'] is None
    m,receipt,host,before,old=run(prepare=lambda host:host.hang_after.add(('compose','up')))
    assert (receipt['outcome'],receipt['recreate']['state'],receipt['code'])==(m.NOT_VERIFIED_OUTCOME,'RECREATED_NOT_VERIFIED','COMMAND_TIMEOUT')

def after_up(change):
    def prepare(host):host.docker.compose.after_up=lambda compose,new:change(host,new)
    return prepare
def drop_env(name):
    def change(host,new):new['Config']['Env']=[item for item in new['Config']['Env'] if not item.startswith(name+'=')]
    return change

CRITERIA=[
    ('ENVIRONMENT_NOT_AS_SIGNED','MOUNT',drop_env('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE')),
    ('ENVIRONMENT_NOT_AS_SIGNED','ENABLE',drop_env('C3PO_R2D2_V2_CAPACITY_REQUIRED')),
    ('ENVIRONMENT_NOT_AS_SIGNED','DISABLE_FAST',lambda host,new:new['Config']['Env'].append('C3PO_R2D2_V2_CAPACITY_REQUIRED=true')),
    ('ENVIRONMENT_NOT_AS_SIGNED','MOUNT',drop_env(k6b.KEYS[0])),
    ('ENVIRONMENT_NOT_AS_SIGNED','MOUNT',drop_env('C3PO_BUILD_SHA')),
    ('MOUNTS_NOT_AS_SIGNED','MOUNT',lambda host,new:new.update(Mounts=[])),
    ('MOUNTS_NOT_AS_SIGNED','ENABLE',lambda host,new:[item.update(RW=True) for item in new['Mounts'] if item['Destination']=='/c3po-capacity']),
    ('MOUNTS_NOT_AS_SIGNED','DISABLE_FULL',lambda host,new:[item.update(Name='x') for item in new['Mounts'] if item['Destination']=='/c3po-capacity']),
    ('WORKER_RESTARTED_AFTER_RECREATE','MOUNT',lambda host,new:new.update(RestartCount=1)),
    ('WORKER_NOT_RUNNING_AFTER_RECREATE','MOUNT',lambda host,new:new['State'].update(Status='restarting',Running=False)),
    ('WORKER_IMAGE_CHANGED','MOUNT',lambda host,new:new.update(Image=hostemu.OTHER)),
    ('OTHER_CONTAINERS_CHANGED','MOUNT',lambda host,new:host.docker.containers.append(hostemu.container('c3po-oneoff-run-1',hostemu.BACKEND,'c3po/backend:production',[]))),
    ('ENV_FILE_NOT_AS_EDITED','MOUNT',lambda host,new:host.tree.get(hostemu.ENV_FILE).content.extend(b'C3PO_LATER=1\n')),
    ('COMPOSE_FILE_CHANGED','MOUNT',lambda host,new:host.tree.get(hostemu.COMPOSE_FILE).content.extend(b'# x\n')),
    ('OVERRIDE_CHANGED','ENABLE',lambda host,new:setattr(host.tree.get(k6b.OVERRIDE_FILE),'mtime',77)),
    ('LOCK_FILE_REPLACED','MOUNT',lambda host,new:k6b.replace(host,k6b.LOCK,'file',uid=1000,gid=1000,mode=0o644)),
    ('OLD_CONTAINER_STILL_PRESENT','MOUNT',None),
]

@pytest.mark.parametrize('code,mode,change',CRITERIA)
def test_each_criterion_broken_alone(code,mode,change):
    if change is None:
        def change(host,new,mode=mode):
            old=hostemu.container('0123456789ab_x',hostemu.BACKEND,'c3po/backend:production',[]);old['Id']=CRITERIA_OLD[0];host.docker.containers.append(old)
    m,docs,host=k6b.fresh(mode);CRITERIA_OLD[:]=[k6b.worker(host)['Id']]
    after_up(change)(host);receipt=docs.run(host)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW',m.NOT_VERIFIED_OUTCOME,code),receipt['code']
    assert receipt['worker_container_replaced'] is True and receipt['recreate']['state'] in ('RECREATED_VERIFIED_ONCE','RECREATED_NOT_VERIFIED')
    assert receipt['env_withdraw']['state']=='NOT_STARTED' and receipt['env_file_after']=='EDITED'      # never withdrawn under a new worker
CRITERIA_OLD=[None]

def test_a_worker_that_dies_between_the_two_readings():
    m,docs,host=k6b.fresh('ENABLE')
    def pause(host,name,detail,calls):
        if name=='pause':k6b.worker(host)['State'].update(Status='restarting',Running=False);k6b.worker(host)['RestartCount']=1
    host.hook=pause;receipt=docs.run(host)
    assert (receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.NOT_VERIFIED_OUTCOME,'WORKER_CHANGED_BETWEEN_THE_TWO_CHECKS','RECREATED_NOT_VERIFIED')

def test_readbacks_that_fail_are_unavailable_not_absent():
    m,docs,host=k6b.fresh('MOUNT')
    k6b.answer(host,k6b.is_mounts,lambda real:(1,b''),nth=2);receipt=docs.run(host)
    assert (receipt['outcome'],receipt['code'])==(m.NOT_VERIFIED_OUTCOME,'READBACK_UNAVAILABLE') and receipt['recreate']['unavailable']=={'MOUNTS':'COMMAND_FAILED'}
    m,docs,host=k6b.fresh('MOUNT')
    k6b.answer(host,k6b.is_inspect,lambda real:(1,b''),nth=3);receipt=docs.run(host)
    assert receipt['outcome'] in (m.NOT_VERIFIED_OUTCOME,m.UNCERTAIN_OUTCOME) and 'WORKER' in receipt['recreate']['unavailable']

# ---------------------------------------------------------------- the death of the process at every host call
STATES=['S0_NOTHING','S1_ENV_EDITED_WORKER_OLD','S2_ENV_EDITED_WORKER_NEW']
@pytest.mark.parametrize('mode',('MOUNT','ENABLE','DISABLE_FAST','DISABLE_FULL'))
def test_death_at_every_host_call_leaves_one_of_three_states_in_order(mode):
    m,docs,host=k6b.fresh(mode);assert docs.run(host)['status']==m.COMPLETE_STATUS;total=host.calls;seen=[];statuses=set()
    for index in range(1,total+1):
        m,docs,host=k6b.fresh(mode);before=k6b.env_bytes(host);old=k6b.worker(host)['Id']
        def hook(host,name,detail,calls,index=index):
            if calls==index:raise hostemu.Death('dead')
        host.hook=hook;receipt=docs.run(host);host.hook=None
        env=k6b.env_bytes(host);worker=k6b.worker(host);edited=env==k6b.expected_env(host,k6b.AFTER[mode])
        if env==before and worker['Id']==old:state='S0_NOTHING'
        elif edited and worker['Id']==old:state='S1_ENV_EDITED_WORKER_OLD'
        elif edited and worker['Id']!=old:state='S2_ENV_EDITED_WORKER_NEW'
        else:raise AssertionError('a state the order of the effects does not allow, at call %d'%index)
        seen.append(state);statuses.add((receipt['status'],receipt['code']))
        if state=='S0_NOTHING':assert receipt['status'] in ('REFUSED',m.PARTIAL_STATUS)
        else:assert (receipt['status'],receipt['code'])==(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN')
        if receipt['status']=='REFUSED':assert state=='S0_NOTHING'
    order=[STATES.index(state) for state in seen]
    assert order==sorted(order),'a later death never leaves an earlier state'
    assert sorted(set(seen))==STATES
    assert statuses=={('REFUSED','RUN_FAILED_BEFORE_ANY_EFFECT'),(m.PARTIAL_STATUS,'RUN_ESCAPED_STATE_UNKNOWN')}

def test_the_deploy_tree_swapped_during_the_editor_is_never_nothing_changed():
    """Review finding 2: the editor edits the file at the path; the run reads through what it holds. A path that no
    longer leads there makes the edit unknown, never a refusal."""
    def prepare(host):host.editor.before=lambda h:setattr(h.tree.get(hostemu.DEPLOY),'ino',7171)
    m,receipt,host,before,old=run(prepare=prepare)
    assert receipt['status']!='REFUSED' and receipt['env_edit']['state']=='UNREADABLE' and receipt['outcome']==m.UNCERTAIN_OUTCOME


def test_no_withdrawal_once_the_lock_is_no_longer_the_one_held():
    def prepare(host):
        second_render(wrong_mount)(host)
        k6b.during(host,k6b.is_render,lambda h:k6b.replace(h,k6b.LOCK,'file',uid=1000,gid=1000,mode=0o644),nth=2)
    m,receipt,host,before,old=run(prepare=prepare)
    assert (receipt['outcome'],receipt['code'],receipt['env_file_after'])==(m.ENV_ONLY_OUTCOME,'RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','EDITED')
    assert receipt['env_withdraw']['state']=='NOT_STARTED'
    # the lock replaced right after a render that failed for another reason (not the lock check): still no withdrawal
    def later(host):
        k6b.answer(host,k6b.is_render,lambda real:(k6b.replace(host,k6b.LOCK,'file',uid=1000,gid=1000,mode=0o644),(1,b''))[1],nth=2)
    m,receipt,host,before,old=run(prepare=later)
    assert (receipt['outcome'],receipt['code'],receipt['env_withdraw']['state'])==(m.ENV_ONLY_OUTCOME,'COMMAND_FAILED','NOT_STARTED') and edited(host,'MOUNT')

def test_a_withdrawal_not_authorized_is_never_run():
    m,docs,host=k6b.fresh('ENABLE');docs.plan['withdrawal_authorized']=False;docs.chain();second_render(wrong_mount)(host)
    receipt=docs.run(host)
    assert (receipt['outcome'],receipt['code'],receipt['env_withdraw']['state'])==(m.ENV_ONLY_OUTCOME,'RENDER_CAPACITY_MOUNT_NOT_AS_SIGNED','NOT_STARTED')
    assert k6b.env_bytes(host)==k6b.expected_env(host,5) and host.editor.calls and len(host.editor.calls)==1

def test_the_bind_source_chain_is_reported_not_judged():
    m,receipt,host,before,old=run()
    assert receipt['precheck']['bind_source_root_controlled'] is False and receipt['effects']['bind_source_chain']['all_root_controlled'] is False

def test_render_after_the_edit_without_the_activation_names():
    for mode in ('MOUNT','ENABLE'):
        m,receipt,host,before,old=run(mode,second_render(lambda value:value['services']['r2d2-worker']['environment'].pop(k6b.KEYS[2])))
        assert (receipt['outcome'],receipt['code'])==(m.WITHDRAWN_OUTCOME,'RENDER_ACTIVATION_ENVIRONMENT_MISMATCH')
    m,receipt,host,before,old=run('DISABLE_FAST',second_render(lambda value:value['services']['r2d2-worker']['environment'].pop(k6b.KEYS[2])))
    assert receipt['outcome']!=m.WITHDRAWN_OUTCOME                                  # a disable reports it and goes on
