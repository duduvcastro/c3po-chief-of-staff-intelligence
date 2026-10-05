"""K6b, the 60 seconds in figures (emulated clock: each command costs what the case says, a pause costs itself).
needed before the first effect = edit class (8) + recreate class (30) + reserve (4) + render allowance (twice the
first render, at least 3, at most 15) + files (1) + settle (3); kept while waiting for the lock = needed + 2."""
import pytest

import family as f
import hostemu
import k6b

MONDAY=[(0.3,('container','inspect')),(0.3,('image','inspect')),(0.3,('ps',)),(2,('compose','config')),(2,('run','--rm')),(23,('compose','up'))]

def go(costs,mode='MOUNT',prepare=None):
    m,docs,host,budget=k6b.timed(0.0,mode)
    for seconds,words in costs:budget.cost(seconds,*words)
    if prepare is not None:prepare(host,budget)
    receipt=docs.run(host,**budget.options());return m,receipt,host,budget

def test_monday_like_figures_complete():
    m,receipt,host,budget=go(MONDAY)
    assert receipt['outcome']==m.COMPLETE_OUTCOME and abs(budget.elapsed-35.9)<0.01
    assert receipt['budget']=={'first_render_milliseconds':2000,'render_allowance_seconds':5,'needed_before_first_effect_seconds':51,
                               'kept_while_waiting_for_the_lock_seconds':53,'left_when_the_lock_was_asked_for_milliseconds':56500,
                               'left_before_first_effect_milliseconds':55600,'render_after_the_edit_milliseconds':2000}

def test_a_recreate_of_its_whole_class_still_completes_with_the_pause():
    m,receipt,host,budget=go(MONDAY[:-1]+[(30,('compose','up'))])
    assert receipt['outcome']==m.COMPLETE_OUTCOME and receipt['recreate']['facts']['settle_pause_taken'] is True

def test_the_lock_held_throughout():
    m,receipt,host,budget=go([],prepare=lambda host,budget:host.lock_holder.update({k6b.LOCK:'EX'}))
    assert (receipt['code'],receipt['budget']['needed_before_first_effect_seconds'])==('DEPLOY_LOCK_BUSY',49) and 8.5<=budget.elapsed<=9.0
    m,receipt,host,budget=go(MONDAY,prepare=lambda host,budget:host.lock_holder.update({k6b.LOCK:'EX'}))
    assert receipt['code']=='DEPLOY_LOCK_BUSY' and 6.5<=budget.elapsed<=7.0 and host.effect_commands()==[]

def test_a_lock_released_inside_the_wait():
    def prepare(host,budget):host.lock_holder[k6b.LOCK]='EX';host.lock_released_after=8
    m,receipt,host,budget=go(MONDAY,prepare=prepare)
    assert receipt['outcome']==m.COMPLETE_OUTCOME and receipt['precheck']['lock_attempts']==9

def test_slow_reads_before_the_lock_refuse_before_it_is_asked_for():
    m,receipt,host,budget=go([(2,('container','inspect')),(2,('image','inspect')),(2,('compose','config'))])
    assert receipt['code']=='LOCK_NOT_TAKEN_BUDGET' and host.effect_commands()==[]

def test_a_first_render_of_six_seconds_cannot_hold_both_effects():
    m,receipt,host,budget=go([(6,('compose','config'))])
    assert receipt['code']=='BUDGET_CANNOT_HOLD_BOTH_EFFECTS' and receipt['budget']['needed_before_first_effect_seconds']==59
    m,receipt,host,budget=go([(5,('compose','config'))])                    # allowance 11: kept 59, but 55 left when the lock is asked for
    assert receipt['code']=='LOCK_NOT_TAKEN_BUDGET' and receipt['budget']['needed_before_first_effect_seconds']==57
    m,receipt,host,budget=go([(3,('compose','config'))])                    # allowance 7: kept 55, 57 left
    assert receipt['outcome']==m.COMPLETE_OUTCOME and receipt['budget']['needed_before_first_effect_seconds']==53

def test_time_lost_under_the_lock_refuses_before_the_first_effect():
    def prepare(host,budget):
        def slow(host):budget.elapsed+=12                      # the reads made again under the lock take 12 s
        k6b.during(host,k6b.is_list,slow)
    m,receipt,host,budget=go([],prepare=prepare)
    assert receipt['code']=='BUDGET_INSUFFICIENT_BEFORE_FIRST_EFFECT' and host.effect_commands()==[]

def test_a_render_after_the_edit_slower_than_its_allowance_withdraws_the_edit():
    def prepare(host,budget):
        host.lock_holder[k6b.LOCK]='EX';host.lock_released_after=35
        def slow(host):budget.elapsed+=16
        k6b.during(host,k6b.is_render,slow,nth=2)
    m,receipt,host,budget=go([(2,('run','--rm'))],prepare=prepare)
    assert (receipt['outcome'],receipt['code'])==(m.WITHDRAWN_OUTCOME,'RENDER_AFTER_EDIT_OVER_ITS_ALLOWANCE') and k6b.env_bytes(host)==k6b.expected_env(host,0)
    assert receipt['recreate']['state']=='NOT_STARTED' and receipt['env_withdraw']['state']=='EDITED'
    # 1 s over its allowance of 3 s is enough: the recreate is never started late
    def prepare(host,budget):
        def slow(host):budget.elapsed+=4
        k6b.during(host,k6b.is_render,slow,nth=2)
    m,receipt,host,budget=go([],prepare=prepare)
    assert (receipt['outcome'],receipt['code'])==(m.WITHDRAWN_OUTCOME,'RENDER_AFTER_EDIT_OVER_ITS_ALLOWANCE')
    def prepare(host,budget):
        def slow(host):budget.elapsed+=3
        k6b.during(host,k6b.is_render,slow,nth=2)
    m,receipt,host,budget=go([],prepare=prepare)
    assert receipt['outcome']==m.COMPLETE_OUTCOME
    # no time left for the withdrawal either: the edit stays, said so
    def prepare(host,budget):
        host.lock_holder[k6b.LOCK]='EX';host.lock_released_after=35
        def slow(host):budget.elapsed+=40
        k6b.during(host,k6b.is_render,slow,nth=2)
    m,receipt,host,budget=go([(2,('run','--rm'))],prepare=prepare)
    assert receipt['outcome'] in (m.ENV_ONLY_OUTCOME,m.UNCERTAIN_OUTCOME) and receipt['env_withdraw']['state'] in ('NOT_STARTED',)

def test_constants_of_the_budget():
    m=k6b.load().m
    assert (m.SETTLE_SECONDS,m.SECOND_CHECK_RESERVE_SECONDS,m.FILES_ALLOWANCE_SECONDS,m.UNDER_LOCK_ALLOWANCE_SECONDS,m.RENDER_ALLOWANCE_FLOOR_SECONDS)==(3,2,1,2,3)
    assert m.effects_budget('edit_env','recreate')==42


def test_the_signed_wait_is_the_bound():
    m,docs,host,budget=k6b.timed(0.0)
    docs.plan['lock']['wait_seconds']=1;docs.chain();host.lock_holder[k6b.LOCK]='EX'
    receipt=docs.run(host,**budget.options())
    assert receipt['code']=='DEPLOY_LOCK_BUSY' and budget.elapsed<=1.5

def test_no_pause_when_less_than_its_reserve_is_left():
    m,docs,host,budget=k6b.timed(0.0)
    def late(h):
        left=60-budget.elapsed;budget.elapsed+=left-4.5                       # 4.5 s left after the first reading of the new worker
    k6b.during(host,k6b.is_inspect,late,nth=3)
    receipt=docs.run(host,**budget.options())
    assert (receipt['outcome'],receipt['code'],receipt['recreate']['state'])==(m.NOT_VERIFIED_OUTCOME,'SECOND_CHECK_NOT_APART','RECREATED_VERIFIED_ONCE')
    assert receipt['recreate']['facts']['settle_pause_taken'] is False
