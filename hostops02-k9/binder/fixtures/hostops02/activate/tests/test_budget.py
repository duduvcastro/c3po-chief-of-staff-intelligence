"""The 60 seconds of a run, in figures: what is kept for the recreate before the lock is asked for, how long the lock
is waited for, what a slow render does, and what is left for the two readings of the new worker."""
from datetime import timedelta
import errno
import fcntl

import family as f
import hostemu
import k6a

def asked(host):
    """The requests for the lock this run made (the release in the end is not one)."""
    return [entry for entry in host.log if entry[0]=='flock' and entry[2]!=fcntl.LOCK_UN]

def test_a_monday_like_run_in_figures():
    """Every docker read 0.3 s, each render 2 s, the recreate 23 s (the whole activation of 2026-09-28 took 23 s)."""
    m,docs,host,budget=k6a.timed(0.3);budget.cost(2.0,'config').cost(23.0,'up');receipt=docs.run(host,**budget.options())
    assert receipt['status']==m.COMPLETE_STATUS and 32990<=receipt['clock']['monotonic_elapsed_ms']<=33000
    assert receipt['budget']=={'first_render_milliseconds':2000,'render_allowance_seconds':5,'needed_before_first_effect_seconds':43,
                               'kept_while_waiting_for_the_lock_seconds':45,'left_when_the_lock_was_asked_for_milliseconds':56800,
                               'left_before_first_effect_milliseconds':56200,'render_from_the_files_milliseconds':2000}
    assert receipt['recreate']['milliseconds']==23000,'how long the recreate command took is in the receipt'
    assert receipt['recreate']['facts']['milliseconds_between_checks']==3900 and receipt['recreate']['facts']['settle_pause_taken'] is True

def test_the_lock_is_waited_for_at_most_the_signed_seconds_and_never_past_what_the_recreate_needs():
    # free at the ninth attempt: taken, and the run completes
    m,docs,host,budget=k6a.timed();host.lock_holder[k6a.LOCK]='EX';host.lock_released_after=8;receipt=docs.run(host,**budget.options())
    assert receipt['status']==m.COMPLETE_STATUS and receipt['precheck']['lock_attempts']==9 and host.paused==2.0+3
    # held throughout, nothing else slow: 60 - 43 kept = 17 s of wait, not the signed 20
    m,docs,host,budget=k6a.timed();host.lock_holder[k6a.LOCK]='EX';before=k6a.state_of(host);receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','DEPLOY_LOCK_BUSY','PRECHECK') and 16.5<=host.paused<=17.0
    assert k6a.state_of(host)==before and host.mutating()==[] and host.lock_held(k6a.LOCK) is None and host.fds=={}
    # a Monday-like precheck (3.2 s) and a 2 s render: 56.8 - 45 kept = 11.8 s of wait
    m,docs,host,budget=k6a.timed(0.3);budget.cost(2.0,'config');host.lock_holder[k6a.LOCK]='EX';receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==('REFUSED','DEPLOY_LOCK_BUSY') and 11.25<=host.paused<=11.8 and host.mutating()==[]
    # the signed wait is the limit when it is the shorter one
    m,docs,host,budget=k6a.timed();docs.plan['lock']['wait_seconds']=5;docs.chain();host.lock_holder[k6a.LOCK]='EX';receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==('REFUSED','DEPLOY_LOCK_BUSY') and 4.5<=host.paused<=5.0
    m,docs,host,budget=k6a.timed();docs.plan['lock']['wait_seconds']=0;docs.chain();host.lock_holder[k6a.LOCK]='EX';receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==('REFUSED','DEPLOY_LOCK_BUSY') and host.paused==0 and [entry[2] for entry in asked(host)]==[fcntl.LOCK_EX|fcntl.LOCK_NB]
    # a holder that only shares the lock excludes an exclusive request as well
    m,docs,host,budget=k6a.timed();host.lock_holder[k6a.LOCK]='SH';receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==('REFUSED','DEPLOY_LOCK_BUSY')

def test_lock_that_cannot_be_asked_for_or_is_not_the_named_file_any_more():
    m,docs,host=k6a.fresh()
    def hook(host,name,detail,calls):
        if name=='flock':raise OSError(errno.ENOLCK,'no locks')
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],host.mutating())==('REFUSED','LOCK_UNAVAILABLE',[])
    m,docs,host=k6a.fresh();done=[]
    def hook(host,name,detail,calls):
        if name=='flock' and not done:
            done.append(1);host.tree.remove(k6a.LOCK);host.tree.add(k6a.LOCK,kind='file',uid=1000,gid=1000,mode=0o644)     # replaced while it is being taken
    host.hook=hook;receipt=docs.run(host)
    assert (receipt['status'],receipt['code'],host.mutating())==('REFUSED','LOCK_FILE_REPLACED',[]) and host.fds=={} and host.locks=={}

def test_run_refuses_before_the_lock_when_what_is_left_cannot_hold_the_recreate():
    # slow reads: five commands of 4 s before the lock; the first render took 4 s, so its repetition is given 9 s
    m,docs,host,budget=k6a.timed(4.0);before=k6a.state_of(host);receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','LOCK_NOT_TAKEN_BUDGET','PRECHECK')
    assert receipt['budget']['render_allowance_seconds']==9 and receipt['budget']['kept_while_waiting_for_the_lock_seconds']==49 and receipt['budget']['left_when_the_lock_was_asked_for_milliseconds']==40000
    assert k6a.state_of(host)==before and host.mutating()==[] and asked(host)==[],'the lock is not even asked for'
    # a GO with 20 s of its window left: the same refusal, whatever the host does
    m,docs,host=k6a.fresh();budget=f.Budget(docs.now+timedelta(seconds=280)).attach(host);receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'])==('REFUSED','LOCK_NOT_TAKEN_BUDGET') and host.mutating()==[]
    # the window ends 44 s after the start: 44 > 43 kept, the lock is taken at once and the run completes inside the window
    m,docs,host=k6a.fresh();budget=f.Budget(docs.now+timedelta(seconds=256)).attach(host);receipt=docs.run(host,**budget.options())
    assert receipt['status']==m.COMPLETE_STATUS

def test_run_refuses_after_the_lock_and_before_the_first_creation_when_the_reads_under_it_were_slow():
    m,docs,host,budget=k6a.timed();budget.cost(20.0,'ps');before=k6a.state_of(host);receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED','BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT','PRECHECK')
    assert receipt['budget']['left_before_first_effect_milliseconds']==40000 and receipt['precheck']['lock_attempts']==1
    assert k6a.state_of(host)==before and host.mutating()==[] and host.lock_held(k6a.LOCK) is None,'the lock was taken and is released'

def test_render_from_the_files_is_given_twice_what_the_first_render_took():
    # a 5 s render: 11 s are kept for its repetition, and a repetition of 9 s still leaves the recreate its whole class
    m,docs,host,budget=k6a.timed();budget.cost(5.0,'-','config').cost(9.0,k6a.OVERRIDE_FILE,'config').cost(23.0,'up');receipt=docs.run(host,**budget.options())
    assert receipt['status']==m.COMPLETE_STATUS and receipt['budget']['render_allowance_seconds']==11 and receipt['budget']['needed_before_first_effect_seconds']==49
    # the floor is 3 s and the ceiling the class of the render (15 s)
    for seconds,allowance in ((0.0,3),(0.9,3),(1.0,3),(1.5,4),(7.0,15),(7.5,15)):
        m,docs,host,budget=k6a.timed();budget.cost(seconds,'-','config');receipt=docs.run(host,**budget.options())
        assert receipt['budget']['render_allowance_seconds']==allowance,seconds

def test_render_from_the_files_that_is_much_slower_than_the_first_leaves_the_recreate_not_started():
    """The one way the budget makes a partial: the files exist, the repetition of the render took far more than twice
    the first, and the recreate no longer fits. It is not started; the worker is untouched."""
    m,docs,host,budget=k6a.timed();budget.cost(30.0,k6a.OVERRIDE_FILE,'config');worker=k6a.worker(host)['Id'];receipt=docs.run(host,**budget.options())
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_OBJECTS_LEFT_WORKER_NOT_RECREATED','COMMAND_NOT_STARTED_BUDGET')
    assert receipt['recreate']['state']=='NOT_STARTED' and receipt['recreate']['started'] is False and receipt['worker_container_replaced'] is False
    assert receipt['mutating_calls']=={'issued':10,'succeeded':9,'failed_nothing_changed':1,'uncertain':0} and receipt['objects_left_by_this_run']==3
    assert k6a.worker(host)['Id']==worker and not [entry for entry in host.commands if 'up' in entry['argv']]

def test_recreate_that_uses_its_whole_class_still_leaves_room_for_both_readings():
    m,docs,host,budget=k6a.timed(0.3);budget.cost(2.0,'config').cost(30.0,'up');receipt=docs.run(host,**budget.options())
    assert receipt['status']==m.COMPLETE_STATUS and 39990<=receipt['clock']['monotonic_elapsed_ms']<=40000 and receipt['recreate']['facts']['settle_pause_taken'] is True

def test_when_no_time_is_left_for_the_pause_the_worker_is_read_twice_at_once_and_the_run_says_verified_once():
    """The recreate started with exactly its class and the reserve left (the repetition of the render used all its
    allowance and more) and took its whole class: the pause does not fit. The run never claims two readings apart."""
    m,docs,host,budget=k6a.timed();budget.cost(6.0,'-','config').cost(19.5,k6a.OVERRIDE_FILE,'config').cost(30.0,'up');receipt=docs.run(host,**budget.options())
    facts=receipt['recreate']['facts']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.PARTIAL_STATUS,'PARTIAL_WORKER_RECREATED_NOT_FULLY_VERIFIED','SECOND_CHECK_NOT_APART')
    assert receipt['recreate']['state']=='RECREATED_VERIFIED_ONCE' and facts['settle_pause_taken'] is False and facts['second_check_passed'] is True and host.paused==0
    assert receipt['worker_container_replaced'] is True and receipt['mutating_calls']['uncertain']==1

def test_no_ordinary_slowness_makes_a_partial():
    """With commands that take the same time each time they run, whatever that time and however long the lock is held,
    a run either refuses with nothing changed or completes."""
    seen=set()
    for seconds in (0.0,0.2,0.5,1.0,1.5,2.0,3.0,5.0):
        for released in (None,1,10,40,70,10**6):
            for recreate in (5.0,23.0,29.0):
                m,docs,host,budget=k6a.timed(seconds);budget.cost(recreate,'up')
                if released is not None:host.lock_holder[k6a.LOCK]='EX';host.lock_released_after=released
                before=k6a.state_of(host);receipt=docs.run(host,**budget.options());seen.add((receipt['status'],receipt['code']))
                assert receipt['status'] in (m.COMPLETE_STATUS,'REFUSED'),(seconds,released,recreate,receipt['code'])
                if receipt['status']=='REFUSED':assert k6a.state_of(host)==before and host.mutating()==[]
                assert receipt['clock']['monotonic_elapsed_ms']<60000 and host.lock_held(k6a.LOCK) is None
    assert seen=={(m.COMPLETE_STATUS,None),('REFUSED','DEPLOY_LOCK_BUSY'),('REFUSED','LOCK_NOT_TAKEN_BUDGET')}
