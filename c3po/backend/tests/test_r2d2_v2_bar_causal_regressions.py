"""Independent end-to-end BAR boundaries and polling-cadence counterexamples."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import pytest
from app.r2d2_v2_composite_source import CompositeEventSource
from app.r2d2_v2_portfolio import apply_events
from app.r2d2_v2_sources import canonical
from tests.test_r2d2_v2_shadow_counterexamples import setup_state,INSTRUMENT,DAY

START=datetime(2026,9,8,15,0,tzinfo=timezone.utc)


class Feed:
    def __init__(self,items=()):self.items=list(items)
    def snapshot(self,*args,**kwargs):return {'status':'MISSING'}
    def causal_list(self,*args,**kwargs):return {'status':'MISSING'}
    def prepare_events(self,now,cursor,*,snapshot=None,receipt_cutoff=None,**kwargs):
        offset=cursor.get('n',0)
        through=snapshot['through'] if snapshot else len(self.items)
        events=[]
        for item in self.items[offset:through]:
            available=datetime.fromisoformat(item['available_at'])
            if available>now or receipt_cutoff is not None and available>receipt_cutoff:break
            events.append(item)
        return {'events':events,'diagnostics':[],'cursor':{'n':offset+len(events)},
            'snapshot':{'through':through},'has_more':offset+len(events)<through,
            'page':{'cutoff_received_at':events[-1]['available_at'] if events else None},
            'raw_receipts':{e['event_id']:e['envelope_sha256'] for e in events}}


def event(kind,at,received,sequence=0,**fields):
    item={'type':kind,'at':at.isoformat(),'available_at':received.isoformat(),
        'source_at':at.isoformat(),'source_id':'bars' if kind=='BAR' else 'ticks',
        'sequence':sequence,'event_id':kind+'-'+str(sequence),'session':DAY,
        'instrument_key':INSTRUMENT,'regular':True,**fields}
    item['envelope_sha256']=sha256(canonical(item)).hexdigest()
    return item


def bar(start,received,sequence=0,low=99.):
    return event('BAR',start,received,sequence,end_at=(start+timedelta(minutes=1)).isoformat(),
        open=100.,high=101.,low=low,close=100.,coverage_complete=True)


def saved(collector):
    return collector.store.read(collector.release.epoch)['state']


def collect(raw,bars,covered=START):
    collector,state,_=setup_state()
    state['coverage_until'][INSTRUMENT]=covered.isoformat()
    collector.source=CompositeEventSource(raw,bars)
    collector.store.atomic(collector.release.epoch,collector._initial(),lambda unused:(state,[],{}),covered)
    return collector


@pytest.mark.parametrize('fraction',[0,1])
@pytest.mark.parametrize('kind',['TRADE','QUOTE'])
def test_exact_boundary_and_microsecond_trade_wait_for_just_closed_bar(fraction,kind):
    boundary=START+timedelta(minutes=1)
    received=boundary+timedelta(microseconds=fraction)
    fields=({'price':110.} if kind=='TRADE' else {'bid':110.,'ask':110.,
        'bid_at':received.isoformat(),'ask_at':received.isoformat()})
    raw=Feed([event(kind,received,received,**fields)])
    bars=Feed([bar(START-timedelta(minutes=1),START+timedelta(seconds=1))])
    collector=collect(raw,bars,START-timedelta(minutes=1))
    collector.cycle(boundary+timedelta(seconds=5))
    row=saved(collector)['ledger']['research']['synthetic-entry']
    assert row['status']=='OPEN' and row['category'] is None
    assert saved(collector)['raw_source_cursor']['quote_trade']['n']==0
    bars.items.append(bar(START,boundary+timedelta(seconds=10),sequence=1,low=90.))
    collector.cycle(boundary+timedelta(seconds=11))
    row=saved(collector)['ledger']['research']['synthetic-entry']
    assert row['status']=='CLOSED' and row['category']=='lower_first'
    assert row['exit_cause']=='STOP' and not row['order_unknown']
    assert saved(collector)['raw_source_cursor']['quote_trade']['n']==1


@pytest.mark.parametrize('poll_offsets',[[],[91],[90,91,119],[60,90,119]])
def test_in_deadline_bar_classification_is_independent_of_poll_cadence(poll_offsets):
    bars=Feed();collector=collect(Feed(),bars)
    for seconds in poll_offsets:
        collector.cycle(START+timedelta(seconds=seconds))
        assert not saved(collector)['ledger']['research']['synthetic-entry']['order_unknown']
    bars.items.append(bar(START,START+timedelta(seconds=120)))
    collector.cycle(START+timedelta(seconds=120))
    row=saved(collector)['ledger']['research']['synthetic-entry']
    assert row['status']=='OPEN' and not row['order_unknown'] and row['category'] is None
    assert saved(collector)['coverage_until'][INSTRUMENT]==(START+timedelta(seconds=60)).isoformat()


@pytest.mark.parametrize('seconds,stale',[(90,False),(91,False),(149,False),(150,False),(150.000001,True)])
def test_bar_timeout_clock_is_ninety_seconds_after_required_minute_end(seconds,stale):
    collector=collect(Feed(),Feed())
    collector.cycle(START+timedelta(seconds=seconds))
    row=saved(collector)['ledger']['research']['synthetic-entry']
    assert row['order_unknown'] is stale


@pytest.mark.parametrize('intermediate',[False,True])
def test_late_bar_cannot_escape_stale_by_arriving_on_first_poll(intermediate):
    bars=Feed();collector=collect(Feed(),bars)
    if intermediate:collector.cycle(START+timedelta(seconds=151))
    bars.items.append(bar(START,START+timedelta(seconds=152)))
    collector.cycle(START+timedelta(seconds=152))
    row=saved(collector)['ledger']['research']['synthetic-entry']
    assert row['order_unknown'] and row['category']=='unobservable'


def test_bar_off_retains_original_ninety_seconds_from_coverage():
    collector=collect(Feed(),Feed())
    collector.source=Feed()
    collector.cycle(START+timedelta(seconds=90))
    assert not saved(collector)['ledger']['research']['synthetic-entry']['order_unknown']
    collector.cycle(START+timedelta(seconds=91))
    assert saved(collector)['ledger']['research']['synthetic-entry']['order_unknown']


@pytest.mark.parametrize('terminal_fraction',[0,1])
def test_late_bar_ending_at_or_before_terminal_cannot_keep_false_target(terminal_fraction):
    _,state,_=setup_state()
    boundary=START+timedelta(minutes=1)
    trade=event('TRADE',boundary+timedelta(microseconds=terminal_fraction),boundary+timedelta(microseconds=terminal_fraction),price=110.)
    state['ledger'],_=apply_events(state['ledger'],[trade])
    cash=state['ledger']['cash']
    state['ledger'],_=apply_events(state['ledger'],[bar(START,boundary+timedelta(seconds=10),low=90.)])
    row=state['ledger']['research']['synthetic-entry']
    assert row['exit_cause']=='TARGET' and row['category']=='unobservable' and row['order_unknown']
    assert state['ledger']['cash']==cash
