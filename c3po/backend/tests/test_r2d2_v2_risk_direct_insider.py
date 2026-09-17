from __future__ import annotations
import json
from datetime import datetime,timedelta,timezone
from dataclasses import replace

from app.r2d2_v2_risk_acquisition import RiskAcquirer,HttpReply,SourceRequest
from app.r2d2_v2_risk_direct_insider import DirectInsiderAcquirer,assess_direct_insider,encode_receipt

NOW=datetime(2026,9,17,18,tzinfo=timezone.utc)
READ=NOW+timedelta(seconds=1)


def transaction(code='P',name='Synthetic Person',day='2026-09-01'):
    return {'name':name,'transactionCode':code,'transactionDate':day,'filingDate':day,'change':2,'share':20,'transactionPrice':5}


def build(transport,budget=128):
    return DirectInsiderAcquirer(RiskAcquirer(transport,lambda:READ),max_requests=budget)


def reply(payload,status=200):return HttpReply(status,json.dumps(payload).encode())


def assess(snapshot):return assess_direct_insider(snapshot,received_at=READ,computed_at=READ)


def test_nonempty_finnhub_normalizes_deduplicates_and_never_fallback():
    calls=[]
    def transport(request):
        calls.append(request)
        return reply({'symbol':'TEST','data':[transaction(),transaction(),transaction('S'),transaction('A')]})
    value,evidence,diagnostics=assess(build(transport).acquire('TEST',cutoff=NOW))
    assert len(calls)==1
    assert (value.total_count,value.buy_count,value.sell_count)==(2,1,1)
    assert evidence.coverage_verified and not diagnostics
    assert evidence.source_id.endswith('/finnhub')


def test_saturated_parent_splits_into_complete_nonoverlapping_leaves():
    calls=[]
    def transport(request):
        calls.append(request)
        if len(calls)==1:return reply({'symbol':'TEST','data':[transaction()]*100})
        return reply({'symbol':'TEST','data':[transaction(day=request.parameters['to'])]})
    snapshot=build(transport).acquire('TEST',cutoff=NOW)
    value,evidence,diagnostics=assess(snapshot)
    assert len(calls)==3 and evidence.coverage_verified and not diagnostics
    assert calls[1].parameters['from']==calls[0].parameters['from']
    assert calls[2].parameters['to']==calls[0].parameters['to']
    assert value.total_count==2


def test_saturated_single_day_is_unknown_no_fallback():
    calls=[]
    def transport(request):
        calls.append(request);return reply({'symbol':'TEST','data':[transaction(day=request.parameters['to'])]*100})
    value,evidence,diagnostics=assess(build(transport).acquire('TEST',cutoff=NOW))
    assert value is None and not evidence.coverage_verified
    assert 'FINNHUB_SINGLE_DAY_SATURATED' in diagnostics
    assert all(call.provider=='finnhub' for call in calls)


def test_request_budget_unknown_no_fallback():
    snapshot=build(lambda _:reply({'symbol':'TEST','data':[transaction()]*100}),budget=1).acquire('TEST',cutoff=NOW)
    value,evidence,diagnostics=assess(snapshot)
    assert value is None and not evidence.coverage_verified
    assert snapshot['acquisition_diagnostic']=='FINNHUB_REQUEST_BUDGET_EXHAUSTED'


def test_invalid_finnhub_envelope_never_triggers_fallback():
    for payload in ({'data':[]},{'symbol':'OTHER','data':[]},{'symbol':'TEST','data':None}):
        calls=[]
        def transport(request):calls.append(request);return reply(payload)
        value,evidence,_=assess(build(transport).acquire('TEST',cutoff=NOW))
        assert value is None and not evidence.coverage_verified and len(calls)==1


def test_http_failed_no_fallback():
    snapshot=build(lambda _:reply({'symbol':'TEST','data':[]},500)).acquire('TEST',cutoff=NOW)
    assert len(snapshot['finnhub_receipts'])==1 and not snapshot['eodhd_receipts']
    assert assess(snapshot)[1].coverage_verified is False


def test_empty_finnhub_empty_eodhd_requires_same_provider_identity():
    def transport(request):
        return reply({'symbol':'TEST','data':[]} if request.provider=='finnhub' else {'data':[],'links':{'next':None}})
    snapshot=build(transport).acquire('TEST',cutoff=NOW)
    assert assess(snapshot)[1].coverage_verified is False
    acquirer=RiskAcquirer(lambda _:reply({'General':{'Code':'TEST'}}),lambda:READ)
    identity=acquirer.fundamentals('TEST').receipts[0]
    snapshot=build(transport).acquire('TEST',cutoff=NOW,eodhd_identity=identity)
    value,evidence,diagnostics=assess(snapshot)
    assert value.total_count==0 and evidence.coverage_verified and not diagnostics
    assert evidence.source_at==READ
    assert evidence.source_id.endswith('/eodhd')


def test_empty_finnhub_uses_eodhd_only_without_union():
    def transport(request):
        if request.provider=='finnhub':return reply({'symbol':'TEST','data':[]})
        return reply({'data':[{'symbol':'TEST','filed_at':'2026-09-02','non_derivative':[{'reporting_owner_name':'Synthetic Person','transaction_code':'S','transaction_date':'2026-09-01','shares_amount':5}]}],'links':{'next':None}})
    value,evidence,diagnostics=assess(build(transport).acquire('TEST',cutoff=NOW))
    assert value.sell_count==1 and value.buy_count==0 and evidence.coverage_verified and not diagnostics


def test_non_directional_finnhub_is_zero_without_fallback():
    snapshot=build(lambda _:reply({'symbol':'TEST','data':[transaction('A')]})).acquire('TEST',cutoff=NOW)
    assert snapshot['eodhd_receipts']==[]
    assert assess(snapshot)[0].total_count==0


def test_boundary_transaction_not_in_score_does_not_trigger_fallback():
    row=transaction(day=(NOW-timedelta(days=180)).date().isoformat())
    snapshot=build(lambda _:reply({'symbol':'TEST','data':[row]})).acquire('TEST',cutoff=NOW)
    assert not snapshot['eodhd_receipts']
    assert assess(snapshot)[0].total_count==0


def test_tampered_receipt_or_changed_cutoff_refused():
    snapshot=build(lambda _:reply({'symbol':'TEST','data':[transaction()]})).acquire('TEST',cutoff=NOW)
    snapshot['finnhub_receipts'][0]['payload_sha256']='0'*64
    assert assess(snapshot)[1].coverage_verified is False


def test_lost_split_leaf_cannot_claim_coverage():
    n=0
    def transport(request):
        nonlocal n;n+=1
        return reply({'symbol':'TEST','data':[transaction()]*100 if n==1 else [transaction()]})
    snapshot=build(transport).acquire('TEST',cutoff=NOW)
    snapshot['finnhub_receipts'].pop()
    assert assess(snapshot)[1].coverage_verified is False


def test_invalid_transaction_date_is_unknown_not_zero():
    snapshot=build(lambda _:reply({'symbol':'TEST','data':[transaction(day='2026-9-1')]})).acquire('TEST',cutoff=NOW)
    assert assess(snapshot)[0] is None
    assert not snapshot['eodhd_receipts']


def test_provider_ignoring_subwindow_cannot_claim_coverage():
    calls=[]
    def transport(request):
        calls.append(request)
        return reply({'symbol':'TEST','data':[transaction()]*100 if len(calls)==1 else [transaction()]})
    snapshot=build(transport).acquire('TEST',cutoff=NOW)
    value,evidence,diagnostics=assess(snapshot)
    assert value is None and not evidence.coverage_verified
    assert 'FINNHUB_REQUEST_WINDOW_NOT_OBSERVED' in diagnostics


def test_continuation_metadata_splits_even_below_cap():
    calls=[]
    def transport(request):
        calls.append(request)
        payload={'symbol':'TEST','data':[transaction(day=request.parameters['to'])]}
        if len(calls)==1:payload['next']='provider-page-2'
        return reply(payload)
    value,evidence,diagnostics=assess(build(transport).acquire('TEST',cutoff=NOW))
    assert len(calls)==3 and evidence.coverage_verified and not diagnostics
