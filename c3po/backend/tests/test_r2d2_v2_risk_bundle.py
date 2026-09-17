from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.r2d2_v2_risk_acquisition import SourceReceipt, SourceRequest
from app.r2d2_v2_risk_bundle import PrivateSnapshot, build_risk_bundle, fundamental_candidates, prepare_path_a
from app.r2d2_v2_risk_source import CanonicalRiskInputs, canonical_risk_score, InsiderActivity, InstitutionalPositions

NOW = datetime(2026, 9, 17, 18, tzinfo=timezone.utc)
DAYS = ['2026-06-30', '2026-03-31', '2025-12-31', '2025-09-30']


def body(value):
    return json.dumps(value, sort_keys=True).encode()


def receipt(provider, path, parameters, payload):
    raw = body(payload)
    return SourceReceipt(SourceRequest(provider, path, parameters), NOW-timedelta(seconds=1), NOW,
                         200, raw, hashlib.sha256(raw).hexdigest(), None)


def raw_fundamentals():
    return {'General': {'Code': 'SYNTH', 'UpdatedAt': '2026-09-16', 'CurrencyCode': 'USD'},
            'Highlights': {'QuarterlyEarningsGrowthYOY': -25, 'EBITDA': 100},
            'Technicals': {'Beta': 1.2},
            'Financials': {
                'Income_Statement': {'quarterly': {d: {'date': d, 'ebitda': 25, 'currency_symbol': 'USD'} for d in DAYS}},
                'Cash_Flow': {'quarterly': {d: {'date': d, 'freeCashFlow': -5, 'currency_symbol': 'USD'} for d in DAYS}},
                'Balance_Sheet': {'quarterly': {DAYS[0]: {'date': DAYS[0], 'shortLongTermDebtTotal': 200, 'shortTermDebt': 100,
                                                        'longTermDebt': 100, 'currency_symbol': 'USD'}}}}}


def arguments():
    return dict(symbol='SYNTH', market='US',
        fundamentals=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.US',{},raw_fundamentals()),
        grades=receipt('fmp','/stable/grades',{'symbol':'SYNTH'},[{'symbol':'SYNTH','date':'2026-09-01','gradingCompany':'Synthetic','action':'Upgrade'}]),
        institutional=receipt('fmp','/stable/institutional-ownership/symbol-positions-summary',{'symbol':'SYNTH','year':2026,'quarter':2},
                              [{'symbol':'SYNTH','year':2026,'quarter':2,'date':'2026-06-30','newPositions':4,'increasedPositions':5,'reducedPositions':3,'closedPositions':2}]),
        insider_snapshot=PrivateSnapshot(body({'symbol':'SYNTH','market':'US','query_cutoff_at':NOW.isoformat(),'events':[],
            'sync':{'source':'sync_sec','symbol':'SYNTH','window_start':(NOW-timedelta(days=180)).isoformat(),
                    'window_end':NOW.isoformat(),'completed_at':NOW.isoformat(),'complete':True}}),NOW,'transaction'),
        official_snapshot=PrivateSnapshot(body({'symbol':'SYNTH','market':'US','outputs':None}),NOW,'transaction'),
        computed_at=NOW,available_at=NOW,decision_at=NOW)


def test_ready_bundle_with_full_fixture_evidence():
    result = build_risk_bundle(**arguments())
    assert result['status'] == 'READY'
    assert result['calculation']['inputs']['earnings_growth'] == -.25
    assert result['calculation']['inputs']['debt_to_ebitda'] == 2
    assert result['calculation']['inputs']['free_cashflow'] == -20
    assert result['path_a']['growth_normalization']['divided_by_100'] is True
    assert result['production_connected'] is False
    assert result == build_risk_bundle(**arguments())


@pytest.mark.parametrize('beta,growth,ebitda,fcf,debt',[
    (1.2,-25,25,-5,200),(.3,.02,-25,30,200), (2.5,-2,80,0,0),(.85,2.01,25,4,1), (1,-2.01,100,-30,1000)])
def test_path_a_equivalence_actual_analyze(beta,growth,ebitda,fcf,debt):
    from app.one_pager import OnePagerService
    raw=raw_fundamentals()
    raw['Technicals']['Beta']=beta
    raw['Highlights']['QuarterlyEarningsGrowthYOY']=growth
    for row in raw['Financials']['Income_Statement']['quarterly'].values(): row['ebitda']=ebitda
    for row in raw['Financials']['Cash_Flow']['quarterly'].values(): row['freeCashFlow']=fcf
    raw['Financials']['Balance_Sheet']['quarterly'][DAYS[0]].update(shortLongTermDebtTotal=debt,shortTermDebt=debt,longTermDebt=0)
    prepared=prepare_path_a(raw,symbol='SYNTH',overlay=None,fx_rate=None,quote_price=None)
    inputs,_=fundamental_candidates(prepared)
    values=CanonicalRiskInputs(**inputs,insider_activity=InsiderActivity(0,0,0),institutional_positions=InstitutionalPositions(4,5,3,2),recent_grade_actions=('upgrade',))
    expected=object.__new__(OnePagerService)._analyze('SYNTH','US',{'price':100,'as_of':NOW},prepared,role='producer',
        insider_activity={'total_count':0,'buy_count':0,'sell_count':0},institutional_positions={'new_positions':4,'increased_positions':5,'reduced_positions':3,'closed_positions':2},recent_grades=[{'action':'upgrade'}])['risk_score']
    assert canonical_risk_score(values)==expected


@pytest.mark.parametrize('missing', ['beta','earnings_growth','free_cashflow','debt_to_ebitda','insider_activity','institutional_positions','recent_grade_actions'])
def test_each_uncovered_input_prevents_ready(missing):
    kwargs=arguments()
    if missing in {'beta','earnings_growth','free_cashflow','debt_to_ebitda'}:
        raw=raw_fundamentals()
        if missing=='beta': raw['Technicals'].pop('Beta')
        elif missing=='earnings_growth': raw['Highlights'].pop('QuarterlyEarningsGrowthYOY')
        else:
            section='Cash_Flow' if missing=='free_cashflow' else 'Income_Statement'
            raw['Financials'][section]['quarterly'].pop(DAYS[-1])
        kwargs['fundamentals']=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.US',{},raw)
    elif missing=='insider_activity':
        snap=kwargs['insider_snapshot'].payload();snap['sync']['window_start']=(NOW-timedelta(days=90)).isoformat()
        kwargs['insider_snapshot']=replace(kwargs['insider_snapshot'],body=body(snap))
    elif missing=='institutional_positions':
        item=kwargs['institutional'];kwargs['institutional']=receipt('fmp',item.request.path,item.request.parameters,[])
    else:
        item=kwargs['grades'];kwargs['grades']=receipt('fmp',item.request.path,item.request.parameters,[])
    result=build_risk_bundle(**kwargs)
    assert result['status']=='COMPLETED_NULL'
    assert result['risk']['value'] is None


@pytest.mark.parametrize('beta',[0,-1])
def test_nonpositive_beta_is_completed_null(beta):
    kwargs=arguments();raw=raw_fundamentals();raw['Technicals']['Beta']=beta
    kwargs['fundamentals']=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.US',{},raw)
    assert build_risk_bundle(**kwargs)['status']=='COMPLETED_NULL'


def test_overlay_changes_inputs_and_receipt():
    kwargs=arguments()
    overlay={'as_of':DAYS[0],'quarterlyIncome':[{'date':d,'ebitda':50,'currency_symbol':'USD'} for d in DAYS],
             'quarterlyCashFlow':[{'date':d,'freeCashFlow':20,'currency_symbol':'USD'} for d in DAYS]}
    kwargs['official_snapshot']=PrivateSnapshot(body({'symbol':'SYNTH','market':'US','outputs':overlay,
        'source_at':'2026-07-15T12:00:00+00:00','available_at':'2026-07-15T12:00:01+00:00'}),NOW,'transaction')
    result=build_risk_bundle(**kwargs)
    assert result['path_a']['official_overlay_applied'] is True
    assert result['status']=='READY'
    assert result['calculation']['inputs']['debt_to_ebitda']==1
    assert result['calculation']['inputs']['free_cashflow']==80
    assert result==build_risk_bundle(**kwargs)


def test_future_official_snapshot_not_ready():
    kwargs=arguments();kwargs['official_snapshot']=replace(kwargs['official_snapshot'],received_at=NOW+timedelta(seconds=1))
    assert build_risk_bundle(**kwargs)['status']!='READY'


def test_payload_hash_tamper_rejected():
    kwargs=arguments();kwargs['fundamentals']=replace(kwargs['fundamentals'],payload_sha256='0'*64)
    with pytest.raises(ValueError,match='BINDING'): build_risk_bundle(**kwargs)


def test_later_decision_preserves_factual_query_window():
    kwargs=arguments(); kwargs.update(computed_at=NOW+timedelta(seconds=2), available_at=NOW+timedelta(seconds=3), decision_at=NOW+timedelta(seconds=4))
    result=build_risk_bundle(**kwargs)
    assert result['status']=='READY'
    assert result['path_a']['insider_query_cutoff_at']==NOW.isoformat()


def test_missing_query_cutoff_never_invented():
    kwargs=arguments(); snap=kwargs['insider_snapshot'].payload(); snap.pop('query_cutoff_at')
    kwargs['insider_snapshot']=replace(kwargs['insider_snapshot'],body=body(snap))
    result=build_risk_bundle(**kwargs)
    assert result['status']=='COMPLETED_NULL'
    assert 'INSIDER_QUERY_CUTOFF_MISSING' in result['diagnostics']


def test_http_failure_not_accepted_even_diagnostic_missing():
    kwargs=arguments(); kwargs['fundamentals']=replace(kwargs['fundamentals'],status=500)
    with pytest.raises(ValueError,match='BINDING'): build_risk_bundle(**kwargs)


def test_b3_remains_completed_null():
    kwargs=arguments();kwargs['market']='B3';raw=raw_fundamentals()
    kwargs['fundamentals']=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.SA',{},raw)
    for key in ['insider_snapshot','official_snapshot']:
        snap=kwargs[key].payload();snap['market']='B3';kwargs[key]=replace(kwargs[key],body=body(snap))
    result=build_risk_bundle(**kwargs)
    assert result['status']=='COMPLETED_NULL'
    assert 'B3_COMPLETED_NULL_RC5' in result['diagnostics']


def test_foreign_fx_precedes_official_overlay():
    raw=raw_fundamentals();raw['General']['Code']='MHVYF'
    converted=prepare_path_a(raw,symbol='MHVYF',overlay=None,fx_rate=100,quote_price=20)
    before,_=fundamental_candidates(converted)
    assert before['free_cashflow']==pytest.approx(-.2)
    overlay={'as_of':DAYS[0], 'quarterlyCashFlow':[{'date':d,'freeCashFlow':30,'currency_symbol':'USD'} for d in DAYS]}
    after,_=fundamental_candidates(prepare_path_a(raw,symbol='MHVYF',overlay=overlay,fx_rate=100,quote_price=20))
    assert after['free_cashflow']==120
    assert after['debt_to_ebitda']==before['debt_to_ebitda']


def test_ttm_duplicate_does_not_prove_four_quarters():
    kwargs=arguments();raw=raw_fundamentals();raw['Financials']['Cash_Flow']['quarterly'][DAYS[-1]]['date']=DAYS[0]
    kwargs['fundamentals']=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.US',{},raw)
    assert build_risk_bundle(**kwargs)['status']=='COMPLETED_NULL'


def test_ttm_currency_mismatch_does_not_prove_coverage():
    kwargs=arguments();raw=raw_fundamentals();raw['Financials']['Cash_Flow']['quarterly'][DAYS[-1]]['currency_symbol']='JPY'
    kwargs['fundamentals']=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.US',{},raw)
    assert build_risk_bundle(**kwargs)['status']=='COMPLETED_NULL'


def test_one_debt_leg_cannot_silently_supply_missing_zero_leg():
    kwargs=arguments();raw=raw_fundamentals();balance=raw['Financials']['Balance_Sheet']['quarterly'][DAYS[0]]
    balance.pop('shortLongTermDebtTotal');balance.pop('longTermDebt')
    kwargs['fundamentals']=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.US',{},raw)
    assert build_risk_bundle(**kwargs)['status']=='COMPLETED_NULL'


def test_b3_requires_no_provider_or_db_snapshot():
    result=build_risk_bundle(symbol='PETR4',market='B3',computed_at=NOW,available_at=NOW,decision_at=NOW)
    assert result['status']=='COMPLETED_NULL'
    assert result['risk']['value'] is None
    assert 'B3_COMPLETED_NULL_RC5' in result['diagnostics']


def test_institutional_quarter_uses_acquisition_clock_not_later_decision():
    kwargs=arguments();source=kwargs['institutional'];row=source.payload()[0]
    row.update(quarter=1,date='2026-03-31')
    source=receipt('fmp',source.request.path,{'symbol':'SYNTH','year':2026,'quarter':1},[row])
    acquisition=datetime(2026,8,18,22,tzinfo=timezone.utc)
    kwargs['institutional']=replace(source,started_at=acquisition,received_at=acquisition+timedelta(seconds=1))
    result=build_risk_bundle(**kwargs)
    assert result['status']=='READY'
    assert result['path_a']['institutional_query_at']==acquisition.isoformat()


def test_grades_window_stays_at_acquisition_for_later_decision():
    kwargs=arguments();source=kwargs['grades'];row=source.payload()[0]
    row['date']=(source.started_at.date()-timedelta(days=90)).isoformat()
    kwargs['grades']=receipt('fmp',source.request.path,source.request.parameters,[row])
    kwargs['decision_at']=NOW+timedelta(days=1)
    result=build_risk_bundle(**kwargs)
    assert result['status']=='READY'
    assert result['calculation']['inputs']['recent_grade_actions']==['upgrade']


@pytest.mark.parametrize('clock_case',['missing','future_source','future_available','future_period'])
def test_official_overlay_unknown_or_future_provenance_never_ready(clock_case):
    kwargs=arguments()
    overlay={'as_of':DAYS[0],'quarterlyCashFlow':[{'date':d,'freeCashFlow':20,'currency_symbol':'USD'} for d in DAYS]}
    snapshot={'symbol':'SYNTH','market':'US','outputs':overlay,
              'source_at':'2026-07-15T12:00:00+00:00','available_at':'2026-07-15T12:00:01+00:00'}
    if clock_case=='missing':snapshot.pop('source_at')
    if clock_case=='future_source':snapshot['source_at']=(NOW+timedelta(seconds=1)).isoformat()
    if clock_case=='future_available':snapshot['available_at']=(NOW+timedelta(seconds=1)).isoformat()
    if clock_case=='future_period':overlay['as_of']='2026-12-31'
    kwargs['official_snapshot']=PrivateSnapshot(body(snapshot),NOW,'transaction')
    result=build_risk_bundle(**kwargs)
    assert result['status']=='COMPLETED_NULL'
    assert 'OFFICIAL_OVERLAY_PROVENANCE_NOT_CAUSAL' in result['diagnostics']


def test_empty_fmp_grades_not_covered_by_eodhd_identity():
    kwargs=arguments();source=kwargs['grades'];kwargs['grades']=receipt('fmp',source.request.path,source.request.parameters,[])
    result=build_risk_bundle(**kwargs)
    assert result['status']=='COMPLETED_NULL'
    assert result['calculation']['evidence']['recent_grade_actions']['coverage_verified'] is False
    assert 'GRADES_EMPTY_COVERAGE_UNKNOWN' in result['diagnostics']
    assert 'COVERAGE_UNKNOWN_RECENT_GRADE_ACTIONS' in result['diagnostics']


def test_only_old_fmp_grades_do_not_invent_current_window_source_clock():
    kwargs=arguments();source=kwargs['grades'];row=source.payload()[0];row['date']='2025-01-01'
    kwargs['grades']=receipt('fmp',source.request.path,source.request.parameters,[row])
    result=build_risk_bundle(**kwargs)
    assert result['status']=='COMPLETED_NULL'
    assert result['calculation']['evidence']['recent_grade_actions']['source_at'] is None
    assert 'GRADES_WINDOW_SOURCE_AT_UNKNOWN' in result['diagnostics']


def test_institutional_provider_date_identity_declared_in_receipt():
    kwargs=arguments();source=kwargs['institutional'];row=source.payload()[0]
    row.pop('year');row.pop('quarter')
    kwargs['institutional']=receipt('fmp',source.request.path,source.request.parameters,[row])
    result=build_risk_bundle(**kwargs)
    assert result['status']=='READY'
    assert result['path_a']['institutional_identity_normalization']=='STRICT_QUARTER_END_DATE'


def test_zero_ttm_ebitda_fallback_does_not_claim_ttm_coverage():
    kwargs=arguments();raw=raw_fundamentals()
    for row in raw['Financials']['Income_Statement']['quarterly'].values():row['ebitda']=0
    raw['Highlights']['EBITDA']=500
    kwargs['fundamentals']=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.US',{},raw)
    result=build_risk_bundle(**kwargs)
    assert result['calculation']['inputs']['debt_to_ebitda']==.4
    assert result['status']=='COMPLETED_NULL'
    assert 'EBITDA_ZERO_TTM_FALLBACK_UNCOVERED' in result['diagnostics']


def test_direct_insider_new_receipt_is_not_fake_sync_sec():
    from app.r2d2_v2_risk_direct_insider import DirectInsiderAcquirer
    from app.r2d2_v2_risk_acquisition import RiskAcquirer,HttpReply
    kwargs=arguments();completed=NOW+timedelta(seconds=1)
    def transport(_):
        return HttpReply(200,body({'symbol':'SYNTH','data':[{'name':'Example','transactionDate':'2026-09-01','transactionCode':'P'}]}))
    snapshot=DirectInsiderAcquirer(RiskAcquirer(transport,lambda:completed)).acquire('SYNTH',cutoff=NOW)
    kwargs.update(insider_snapshot=PrivateSnapshot(body(snapshot),completed,'direct-acquisition'),computed_at=completed,available_at=completed,decision_at=completed)
    result=build_risk_bundle(**kwargs)
    assert result['status']=='READY'
    assert result['calculation']['evidence']['insider_activity']['source_id']=='DIRECT_INSIDER_RC4BIS/finnhub'
    assert result['calculation']['inputs']['insider_activity']['buy_count']==1
    assert 'INSIDER_WINDOW_PARTIAL' not in result['diagnostics']


def test_overlay_growth_keeps_candidate_but_refuses_wrong_source_clock():
    kwargs=arguments()
    overlay={'as_of':DAYS[0],'quarterlyIncome':[{'date':DAYS[0],'netIncome':200,'ebitda':25,'currency_symbol':'USD'},
                                            {'date':'2025-06-30','netIncome':100,'ebitda':25,'currency_symbol':'USD'}]}
    snap={'symbol':'SYNTH','market':'US','outputs':overlay,'source_at':'2026-07-15T12:00:00+00:00','available_at':'2026-07-15T12:00:01+00:00'}
    kwargs['official_snapshot']=PrivateSnapshot(body(snap),NOW,'transaction')
    result=build_risk_bundle(**kwargs)
    assert result['calculation']['inputs']['earnings_growth']==1
    assert result['status']=='COMPLETED_NULL'
    assert 'GROWTH_OVERLAY_PROVENANCE_UNRESOLVED' in result['diagnostics']


def test_nonpositive_beta_explains_policy_null():
    kwargs=arguments();raw=raw_fundamentals();raw['Technicals']['Beta']=0
    kwargs['fundamentals']=receipt('eodhd','/api/v1.1/fundamentals/SYNTH.US',{},raw)
    assert 'BETA_NONPOSITIVE_COMPLETED_NULL_RC5' in build_risk_bundle(**kwargs)['diagnostics']


def test_b3_policy_clock_chain_preserved_with_delayed_publication():
    result=build_risk_bundle(symbol='PETR4',market='B3',computed_at=NOW,available_at=NOW+timedelta(seconds=1),decision_at=NOW+timedelta(seconds=2))
    assert result['status']=='COMPLETED_NULL'
    assert not any(code.startswith('COMPONENT_NOT_CAUSAL') for code in result['diagnostics'])
