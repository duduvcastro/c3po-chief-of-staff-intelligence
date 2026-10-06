"""Fonte real em emulador inerte; não envia GO nem observa um host operativo."""
import pytest
import fixtures as fx


class FirstStop(Exception):
    pass


class FirstDeath(BaseException):
    pass


@pytest.mark.parametrize('kind', ['private_dry_exception', 'source_refusal', 'base_exception'])
def test_first_gate_propagates_exact_exception_before_clocks_host_or_effects(kind):
    docs,_=fx.case();m=docs.k.m;state=m.Effects()
    error=FirstStop('private dry gate') if kind=='private_dry_exception' else (m.Refused('SYNTHETIC_FIRST_GATE_REFUSAL') if kind=='source_refusal' else FirstDeath('synthetic death'))
    calls=[]
    def gate():calls.append('gate');raise error
    def forbidden_clock():raise AssertionError('clock touched before first gate refusal')
    with pytest.raises(type(error)) as caught:
        docs.perform(fx.f.Untouchable(),gate=gate,state=state,clock=forbidden_clock,monotonic=forbidden_clock)
    assert caught.value is error and calls==['gate']
    assert state.started is False and state.clean() and state.pending is False and state.counts()=={'issued':0,'succeeded':0,'failed_nothing_changed':0,'uncertain':0}


def test_commands_and_reader_constructors_have_no_host_clock_gate_or_claim_observation():
    docs,_=fx.case();m=docs.k.m;host=fx.f.Untouchable()
    def forbidden():raise AssertionError('constructor observed clock or gate')
    commands=m.Commands(host,forbidden)
    reader=m.BootstrapReader(docs.plan,host,forbidden,commands,{},forbidden,forbidden)
    assert reader.held=={} and reader.worker_id is None and reader.boot_hash is None
    assert commands.started=={'READ':0,'CONTAINER':0,'EFFECT':0}


def test_later_gate_refusal_stays_a_receipt_and_has_no_claim_effect():
    docs,host=fx.case();m=docs.k.m;before=host.tree.snapshot();calls=[]
    def gate():
        calls.append('gate')
        if len(calls)==2:raise m.Refused('SYNTHETIC_LATER_GATE_REFUSAL')
        return 60
    receipt=docs.perform(host,gate=gate)
    assert receipt['status']==m.REFUSED_STATUS and receipt['code']=='SYNTHETIC_LATER_GATE_REFUSAL'
    assert receipt['claim']['state']=='NOT_ATTEMPTED' and receipt['nothing_changed_by_this_run'] is True
    assert calls==['gate','gate'] and not fx.mutations(host) and host.tree.snapshot()==before


def test_later_gate_failure_after_claim_fsync_is_consumed_partial_and_never_unlinked():
    docs,host=fx.case();m=docs.k.m;after_effect=[False];calls=[]
    def hook(host,name,detail,count):
        if name=='fsync' and detail[0]==m.K9_PLACEMENT['claims']:after_effect[0]=True
    host.hook=hook
    def gate():
        calls.append('gate')
        if after_effect[0]:raise FirstDeath('synthetic postclaim gate failure')
        return 60
    receipt=docs.perform(host,gate=gate)
    assert len(calls)>2 and after_effect[0]
    assert receipt['status']==m.PARTIAL_STATUS and receipt['outcome']==m.PARTIAL_OUTCOME
    assert receipt['claim']['usage_consumed'] is True and receipt['claim']['possible_creation'] is True
    assert receipt['dependents_hold'] is True and receipt['nothing_changed_by_this_run'] is False
    assert host.tree.get(receipt['claim']['path']) is not None
    assert not [call for call in host.log if call[0]=='unlink']
