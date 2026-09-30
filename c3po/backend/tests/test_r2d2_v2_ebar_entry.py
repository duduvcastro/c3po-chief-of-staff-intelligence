"""Offline E-BAR-1 D1/D2 transition, with restart/replay and adverse quotes."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import pytest
from app import r2d2_v2_shadow as shadow
from app.r2d2_v2_contract import entry_geometry
from app.r2d2_v2_store import utc
from test_r2d2_v2_shadow_counterexamples import setup_state, fake_evaluations, batch, causal, DAY, OPEN, INSTRUMENT


def pending(monkeypatch, decision=OPEN):
    fake_evaluations(monkeypatch)
    collector,state,session=setup_state(position=False)
    collector.minute_entry=True
    journals=[]
    collector._capture(state,journals,session,batch(),utc(decision),causal=causal())
    entry=session['entries_pending'][INSTRUMENT]
    entry['evaluation']['atr14']=2.0
    entry['evaluation']['adv20']=1000000.0
    return collector,state,session,entry,journals


def quote(at, **changes):
    return {'type':'QUOTE','instrument_key':INSTRUMENT,'regular':True,'at':at,
        'available_at':at,'bid_at':at,'ask_at':at,'bid':101.,'ask':101.1,**changes}


def frontier(received, at=None, sequence=0):
    """Another name's quote received after entry_at: the source passed it."""
    from test_r2d2_v2_shadow_counterexamples import source_event
    at=at or received
    return source_event('QUOTE',at=at,available_at=received,sequence=sequence,instrument_key='US:FRONT',
        source_id='frontier-source',event_id=f'frontier-{sequence}',bid=50.,ask=50.01,bid_at=at,ask_at=at,regular=True)


@pytest.mark.parametrize('seconds',[0,.001,20,59])
def test_always_next_minute_and_no_early_episode(monkeypatch,seconds):
    decision=utc(OPEN)+timedelta(seconds=seconds)
    collector,state,session,entry,journals=pending(monkeypatch,decision.isoformat())
    assert entry['entry_at']=='2026-09-08T14:01:00+00:00'
    assert 0<(utc(entry['entry_at'])-decision).total_seconds()<=60
    assert not state['ledger']['research']
    assert journals[-1]['decision_at']==decision.isoformat()


def test_restart_entry_uses_entry_mid_frozen_atr_and_fixed_maturity(monkeypatch):
    collector,state,session,entry,journals=pending(monkeypatch)
    at=entry['entry_at']
    collector._entries(state,journals,session,{},[quote(at)],utc(at))
    record=next(iter(state['ledger']['research'].values()))
    assert record['decision_at']==OPEN and record['opened_at']==at and record['entry_at']==at
    assert record['geometry']==entry_geometry(101.05,2.)
    assert record['maturity_at']=='2026-09-21T19:55:00+00:00'
    cash=state['ledger']['cash']
    state=deepcopy(state);session=state['sessions'][DAY]
    rebuilt,_,_=setup_state(position=False)
    rebuilt.minute_entry=True
    rebuilt._entries(state,[],session,{},[quote(at)],utc(at))
    assert len(state['ledger']['research'])==1 and state['ledger']['cash']==cash


@pytest.mark.parametrize('age,reason',[(10,None),(10.001,'ENTRY_QUOTE_STALE_OR_FUTURE')])
def test_both_quote_sides_age_inclusive(monkeypatch,age,reason):
    collector,state,session,entry,journals=pending(monkeypatch)
    at=entry['entry_at'];old=(utc(at)-timedelta(seconds=age)).isoformat()
    collector._entries(state,journals,session,{},[quote(at,bid_at=old)],utc(at))
    assert journals[-1]['reason']==reason
    assert bool(state['ledger']['research'])==(reason is None)


@pytest.mark.parametrize('changes,reason',[
    ({'ask_at':None},'ENTRY_QUOTE_STALE_OR_FUTURE'),
    ({'bid':None},'ENTRY_QUOTE_INVALID'),
    ({'bid':4.,'ask':4.},'ENTRY_QUOTE_PRICE_BELOW_MINIMUM'),
    ({'bid':100.,'ask':101.},'ENTRY_QUOTE_SPREAD_TOO_WIDE'),
    ({'available_at':'2026-09-08T14:01:01+00:00'},'ENTRY_QUOTE_MISSING'),
])
def test_entry_quote_guards_never_substitute_trade_or_later_quote(monkeypatch,changes,reason):
    collector,state,session,entry,journals=pending(monkeypatch)
    at=entry['entry_at']
    collector._entries(state,journals,session,{},[quote(at,**changes)],utc(at))
    assert journals[-1]['reason']==reason
    assert not state['ledger']['research'] and not session['entries_pending']


def test_restart_uses_provider_quote_available_by_entry_even_when_read_later(monkeypatch):
    collector,state,session,entry,journals=pending(monkeypatch)
    at=utc(entry['entry_at']);before=(at-timedelta(seconds=5)).isoformat()
    collector._entries(state,journals,session,{},[quote(before)],utc(before))
    assert journals[-1]['type']=='ENTRY_QUOTE_OBSERVED'
    state=deepcopy(state);session=state['sessions'][DAY]
    collector._entries(state,journals,session,{},[quote(at.isoformat(),bid=200.,ask=200.)],at+timedelta(seconds=1))
    assert next(iter(state['ledger']['research'].values()))['geometry']['P']==200.


def test_source_capability_alone_does_not_activate_ebar():
    collector,_,_=setup_state(position=False)
    assert collector.minute_entry is False


def test_cycle_first_bar_begins_at_entry_and_preentry_trade_does_not_close(monkeypatch):
    from test_r2d2_v2_shadow_counterexamples import source_event
    collector,state,session,entry,journals=pending(monkeypatch)
    at=entry['entry_at']
    earlier=source_event('TRADE',at='2026-09-08T14:00:59+00:00',price=200.,regular=True)
    q=source_event('QUOTE',at=at,sequence=1,bid=101.,ask=101.1,bid_at=at,ask_at=at,regular=True)
    received=(utc(at)+timedelta(milliseconds=1)).isoformat()
    state,journals,_=collector._cycle(state,{},[earlier,q,frontier(received)],[],utc(received))
    record=next(iter(state['ledger']['research'].values()))
    assert record['status']=='OPEN' and record['opened_at']==at
    end=(utc(at)+timedelta(minutes=1)).isoformat()
    bar=source_event('BAR',at=at,available_at=end,sequence=2,end_at=end,
        open=101.,high=101.1,low=101.,close=101.,regular=True,coverage_complete=True)
    state,journals,_=collector._cycle(state,{},[bar],[],utc(end))
    record=next(iter(state['ledger']['research'].values()))
    assert record['status']=='OPEN' and not record['order_unknown']
    assert 'PARTIAL_ENTRY_BAR_WITHOUT_TRADES' not in record['flags']


def test_missing_entry_quote_is_final_after_restart(monkeypatch):
    # Missing is decided only once a later receipt proves the source passed
    # entry_at; the clock reaching entry_at alone proves nothing (see below).
    collector,state,session,entry,journals=pending(monkeypatch)
    at=utc(entry['entry_at'])
    state,journals,_=collector._cycle(state,{},[],[],at)
    assert INSTRUMENT in session['entries_pending'] and not state['ledger']['research']
    received=at+timedelta(milliseconds=5)
    state,journals,_=collector._cycle(state,{},[frontier(received.isoformat())],[],received)
    assert not state['ledger']['research']
    assert session['candidates'][INSTRUMENT]['entry_reason']=='ENTRY_QUOTE_MISSING'
    assert journals[-2]['frontier_at']==received.isoformat()
    state=deepcopy(state)
    collector._entries(state,[],state['sessions'][DAY],{},[quote(at.isoformat())],at+timedelta(seconds=1))
    assert not state['ledger']['research']


def test_backlogged_entry_quote_is_used_as_after_restart(monkeypatch):
    # P2-5: at the first cycle after entry_at the quote received before it is
    # still in the source backlog. Live must wait, as a restart would read it.
    runs=[]
    for live in (True,False):
        collector,state,session,entry,journals=pending(monkeypatch)
        at=utc(entry['entry_at'])
        late=quote((at-timedelta(seconds=1)).isoformat(),bid=100.,ask=100.)
        late.update(event_id='late-quote',source_id='quote-source',sequence=0,envelope_sha256='a'*64)
        if live:
            state,_,_=collector._cycle(state,{},[],[],at+timedelta(seconds=1))
            assert INSTRUMENT in session['entries_pending']
        now=at+timedelta(seconds=2)
        state,_,_=collector._cycle(state,{},[late,frontier((at+timedelta(seconds=1)).isoformat())],[],now)
        record=next(iter(state['ledger']['research'].values()))
        runs.append((record['opened_at'],record['geometry']))
    assert runs[0]==runs[1] and runs[0][1]['P']==100.


@pytest.mark.parametrize('backlog,reason',[(False,'ENTRY_QUOTE_FRONTIER_TIMEOUT'),(True,None)])
def test_unproven_entry_frontier_wait_is_bounded(monkeypatch,backlog,reason):
    collector,state,session,entry,journals=pending(monkeypatch)
    at=utc(entry['entry_at'])
    collector._entries(state,journals,session,{},[quote((at-timedelta(seconds=1)).isoformat())],at-timedelta(seconds=1))
    edge=at+shadow.ENTRY_FRONTIER_WAIT
    state,_,_=collector._cycle(state,{},[],[],edge,frontier={'held':{},'backlog':False})
    assert INSTRUMENT in session['entries_pending']
    state,journals,_=collector._cycle(state,{},[],[],edge+timedelta(milliseconds=1),
                                      frontier={'held':{},'backlog':backlog})
    assert (INSTRUMENT in session['entries_pending'])==(reason is None)
    assert session['candidates'][INSTRUMENT].get('entry_reason')==reason
    assert not state['ledger']['research']


def test_quote_held_behind_composite_barrier_blocks_entry(monkeypatch):
    collector,state,session,entry,journals=pending(monkeypatch)
    at=utc(entry['entry_at'])
    now=at+timedelta(seconds=2)
    held={INSTRUMENT:at-timedelta(seconds=1)}
    state,_,_=collector._cycle(state,{},[frontier((at+timedelta(seconds=1)).isoformat())],[],now,
                               frontier={'held':held,'backlog':False})
    assert INSTRUMENT in session['entries_pending'] and entry['frontier_at']
    assert shadow._held_receipts({'barrier':{'pending_raw':{'raw-x':{'instrument_key':INSTRUMENT,
        'available_at':held[INSTRUMENT].isoformat()}}}})==held
    assert shadow._held_receipts({'barrier':{'pending_raw':{'raw-x':{}}}})=={'*':shadow.datetime.min.replace(
        tzinfo=shadow.timezone.utc)}
    released=quote((at-timedelta(seconds=1)).isoformat(),bid=100.,ask=100.)
    released.update(event_id='held-quote',source_id='quote-source',sequence=0,envelope_sha256='a'*64)
    state,_,_=collector._cycle(state,{},[released],[],now+timedelta(seconds=1),frontier={'held':{},'backlog':False})
    assert next(iter(state['ledger']['research'].values()))['geometry']['P']==100.


def test_ebar_release_requires_same_amendment_in_all_three_consents():
    from test_r2d2_v2_store_worker import release_body, verify
    from app.r2d2_v2_calendar import ShadowCalendar
    from app.r2d2_v2_store import ShadowIntegrityError
    body=release_body()
    body['ebar_amendment_sha']=shadow.EBAR_AMENDMENT_SHA
    with pytest.raises(ShadowIntegrityError,match='PACKAGE_CONSENT_BINDING_MISMATCH'):
        verify(body,ShadowCalendar())
    for consent in body['package_consents']:
        consent['ebar_amendment_sha']=shadow.EBAR_AMENDMENT_SHA
    release=verify(body,ShadowCalendar())
    assert release.ebar_amendment_sha==shadow.EBAR_AMENDMENT_SHA
    body['ebar_amendment_sha']='f'*64
    with pytest.raises(ShadowIntegrityError,match='RELEASE_EBAR_POLICY_MISMATCH'):
        verify(body,ShadowCalendar())


def test_bad_entry_geometry_persists_reason_without_episode(monkeypatch):
    collector,state,session,entry,journals=pending(monkeypatch)
    entry['evaluation']['atr14']=1000.
    at=entry['entry_at']
    collector._entries(state,journals,session,{},[quote(at)],utc(at))
    assert journals[-1]['reason']=='ENTRY_QUOTE_GEOMETRY_INELIGIBLE'
    assert not state['ledger']['research']


@pytest.mark.parametrize('observed',[False,True])
def test_restart_next_session_finishes_entry_without_rescheduling(monkeypatch,observed):
    # P3: a pending entry of a closed session is never admitted the next day
    # with the previous session's opened_at, even with a valid quote held.
    collector,state,session,entry,journals=pending(monkeypatch)
    if observed:
        at=utc(entry['entry_at'])
        collector._entries(state,journals,session,{},[quote((at-timedelta(seconds=1)).isoformat())],at-timedelta(seconds=1))
        assert entry['quote']
    state['last_session']=DAY
    state['ledger']['session']=DAY
    state,journals,_=collector._cycle(state,{},[],[],utc('2026-09-09T14:00:00+00:00'))
    assert not state['sessions'][DAY]['entries_pending']
    assert state['sessions'][DAY]['candidates'][INSTRUMENT]['entry_reason']=='ENTRY_SESSION_CLOSED'
    assert next(j for j in journals if j['type']=='CANDIDATE_ENTRY')['reason']=='ENTRY_SESSION_CLOSED'
    assert not state['ledger']['research']


@pytest.mark.parametrize('delay',[0,1,45])
def test_spooled_quote_entry_is_poll_cadence_independent(monkeypatch,delay):
    collector,state,session,entry,journals=pending(monkeypatch)
    at=utc(entry['entry_at'])
    q=quote((at-timedelta(seconds=1)).isoformat(),bid=100.,ask=100.)
    collector._entries(state,journals,session,{},[q],at+timedelta(seconds=delay))
    record=next(iter(state['ledger']['research'].values()))
    assert record['geometry']['P']==100. and record['opened_at']==at.isoformat()


def test_later_snapshot_does_not_gain_spool_receipt_authority(monkeypatch):
    collector,state,session,entry,journals=pending(monkeypatch)
    entry['quote']=None
    at=utc(entry['entry_at'])
    row=batch()['universe']['instruments'][0]
    row['quote']={'bid':100.,'ask':100.,'available_at':at.isoformat(),
        'entry_evidence':'IMMUTABLE_EVENT',
        'bid_source_at':at.isoformat(),'ask_source_at':at.isoformat()}
    collector._entries(state,journals,session,{'universe':{'instruments':[row]}},[],at+timedelta(seconds=1))
    assert journals[-1]['reason']=='ENTRY_QUOTE_MISSING'
