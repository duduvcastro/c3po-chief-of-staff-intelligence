"""Failed provider data is local to a name; evidence integrity remains batch-fatal."""
from copy import deepcopy
import hashlib
import json
from datetime import timedelta
import pytest
from app.r2d2_v2_risk_executor import execute_private_risk
from app import r2d2_v2_risk_host_executor as host
from test_r2d2_v2_risk_executor import fixture, encode, NOW
from test_r2d2_v2_risk_host_executor import package, Clock, certified_admission
from test_r2d2_v2_risk_runner import provider, reader, Connection


def mixed(replay, root, failure, method='fundamentals'):
    def put(name, raw):
        path=root/name;path.write_bytes(raw);path.chmod(0o600)
        return {'path':name,'sha256':hashlib.sha256(raw).hexdigest()}
    def clone(value):
        if isinstance(value,dict):
            if set(value)=={'path','sha256'}:
                raw=(root/value['path']).read_bytes().replace(b'SYNTH',b'SECOND')
                return put('second-'+value['path'],raw)
            return {k:clone(v) for k,v in value.items()}
        if isinstance(value,list):return [clone(v) for v in value]
        return 'SECOND' if value=='SYNTH' else value
    second=clone(deepcopy(replay['symbols'][0]))
    for spec in second['sources'].values():
        if 'receipt' in spec:
            doc=json.loads((root/spec['receipt']['path']).read_bytes())
            doc['payload_sha256']=spec['body']['sha256']
            spec['receipt']=put(spec['receipt']['path'],encode(doc))
    replay['symbols'].append(second)
    spec=replay['symbols'][0]['sources'][method]
    doc=json.loads((root/spec['receipt']['path']).read_bytes())
    if failure=='http':doc.update(status=503,diagnostic='HTTP_FAILED')
    if failure=='transport':doc.update(status=None,diagnostic='TRANSPORT_FAILED')
    if failure=='json':spec['body']=put(method+'.body',b'not json');doc['payload_sha256']=spec['body']['sha256']
    if failure=='diagnostic':doc.update(status=200,diagnostic='JSON_INVALID')
    if failure=='wrong_symbol':
        doc.update(status=503,diagnostic='HTTP_FAILED');doc['request']['path']=doc['request']['path'].replace('SYNTH','FOREIGN')
    if failure=='future':doc.update(status=503,diagnostic='HTTP_FAILED',received_at=(NOW+timedelta(days=1)).isoformat())
    if failure=='inner_hash':doc.update(status=503,diagnostic='HTTP_FAILED',payload_sha256='0'*64)
    spec['receipt']=put(spec['receipt']['path'],encode(doc))
    if failure=='outer_hash':(root/spec['body']['path']).write_bytes(b'tampered')


@pytest.mark.parametrize('method',['fundamentals','grades','institutional'])
@pytest.mark.parametrize('failure',['http','transport','json','diagnostic'])
def test_mixed_replay_null_only_failed_name(tmp_path,method,failure):
    replay,root,save=fixture(tmp_path);mixed(replay,root,failure,method)
    result=execute_private_risk(**save())
    assert result['counts']=={'READY':1,'COMPLETED_NULL':1}
    data=json.loads((tmp_path/'output/assessments.private.json').read_bytes())
    assert data['SYNTH']['risk']['value'] is None
    assert data['SYNTH']['status']=='COMPLETED_NULL'
    assert data['SYNTH']['source_responses_complete'] is False
    assert 'SOURCE_INCOMPLETE' in data['SYNTH']['diagnostics']
    assert data['SYNTH']['coverage']['verified'] is False
    assert data['SECOND']['status']=='READY' and data['SECOND']['risk']['value'] is not None
    assert not result['certification_granted']


@pytest.mark.parametrize('failure',['outer_hash','inner_hash','future','wrong_symbol'])
def test_integrity_failure_still_refuses_entire_replay(tmp_path,failure):
    replay,root,save=fixture(tmp_path);mixed(replay,root,failure)
    with pytest.raises(ValueError):execute_private_risk(**save())
    assert not (tmp_path/'output').exists()


@pytest.mark.parametrize('failure',['http','json','transport'])
def test_host_assessment_staging_execute_mixed_sources(tmp_path,failure):
    def mutate(plan,put):
        root=tmp_path/'input';replay=json.loads((root/plan['replay_manifest']['path']).read_bytes())
        mixed(replay,root,failure)
        admission=certified_admission();admission['counts']['symbols']=2
        causal=admission['native_result']['causal_readback'];causal['selected_count']=2
        causal['symbols_file_sha256']=hashlib.sha256(b'SYNTH\nSECOND\n').hexdigest()
        plan['admission']=put('admission.json',admission);replay['admission']=plan['admission']
        plan['replay_manifest']=put('manifest.json',replay)
        plan['list']=put('list.json',{'namespace':plan['namespace'],'session_date':plan['session_date'],
            'symbols':[{'symbol':e['symbol'],'market':e['market']} for e in replay['symbols']]})
        plan['limits']['max_symbols']=2
    args=package(tmp_path,mutate);clock=Clock();previous=None
    for phase in host.PHASES:
        result=host.run_host_phase(phase=phase,**args,clock=clock,previous_receipt_sha256=previous,
            transport=provider,database_reader=reader(Connection()))
        previous=result['receipt_sha256']
    output=args['spool_root']/args['manifest_sha256']/'risk-output'
    execution=json.loads((output/'execution.json').read_bytes())
    assert execution['counts']=={'READY':1,'COMPLETED_NULL':1}
    data=json.loads((output/'assessments.private.json').read_bytes())
    assert 'SOURCE_INCOMPLETE' in data['SYNTH']['diagnostics']
    assert data['SECOND']['status']=='READY'
