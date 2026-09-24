"""Offline executor -> accepted predecessor chain -> staging -> risk proof."""
import hashlib
import json
from datetime import timedelta

import pytest
from app import r2d2_v2_risk_stage as stage
from app import r2d2_v2_risk_host_executor as host
from test_r2d2_v2_risk_host_executor import package, Clock, certified_admission
from test_r2d2_v2_risk_runner import provider, reader, Connection
from test_r2d2_v2_risk_executor import NOW, encode


def put(path, value):
    raw=value if isinstance(value,bytes) else encode(value)
    path.write_bytes(raw);path.chmod(0o600)
    return stage.sha(raw)


def pipeline(tmp_path):
    root=tmp_path/'successor';root.mkdir(mode=0o700)
    (root/'control').mkdir(mode=0o700);(root/'receipts').mkdir(mode=0o700)
    order='a'*64;pins='b'*64;admission=certified_admission()
    namespace=admission['namespace'];session=admission['session']
    for phase in ('collect','build','publish','components','admission'):
        start=put(root/'control'/f'{phase}.started.json',{'phase':phase})
        scope={'phase':phase,'namespace':namespace,'session':session,'order_sha256':order,'pins_sha256':pins}
        doc={**(admission if phase=='admission' else {}),**scope,
             'schema':'CODEX_CERTIFIED_PHASE_RECEIPT_V1','status':'PASSED','start_sha256':start}
        receipt=put(root/'receipts'/f'{phase}.result.json',doc)
        put(root/'control'/f'{phase}.accepted.json',{'schema':'CODEX_CERTIFIED_PHASE_ACCEPTANCE_V1',**scope,
             'receipt_sha256':receipt,'driver_exit_code':0,'driver_status':'PASSED','post_state_unchanged':True})
        if phase=='admission':admission=doc
    put(root/'control/symbols.txt',b'SYNTH\n')
    args=package(tmp_path,admission_doc=admission);clock=Clock();calls=[];connection=Connection()
    def transport(request):calls.append(request);return provider(request)
    previous=None;acquire_counts=None
    for phase in host.PHASES:
        result=host.run_host_phase(phase=phase,**args,clock=clock,previous_receipt_sha256=previous,
                                  transport=transport,database_reader=reader(connection))
        previous=result['receipt_sha256']
        if phase=='acquire':acquire_counts=(len(calls),len(connection.calls))
    destination=args['spool_root']/args['manifest_sha256']
    manifest=result['outputs']['assessment_manifest']
    bundle=stage.build_bundle(destination/'assessment'/manifest['path'],manifest['sha256'])
    post_checks=[]
    def check_after():
        assert not (root/'control/risk-stage.accepted.json').exists()
        assert (len(calls),len(connection.calls))==acquire_counts
        post_checks.append(True)
    kwargs=dict(root=root,namespace=namespace,session=session,order_sha256=order,pins_sha256=pins,
        before_sha256='c'*64,scoped_counts=(1,1,2),check_after=check_after,
        execute_receipt_path=destination/'execute.RECEIPT.json',execute_receipt_sha256=previous,
        host_manifest_sha256=args['manifest_sha256'],host_go_sha256=args['go_sha256'])
    return bundle,kwargs,calls,connection,acquire_counts,post_checks,result


def test_full_executor_staging_wrapper_and_risk_no_acquisition_after_acquire(tmp_path):
    bundle,kwargs,calls,conn,counts,checks,host_result=pipeline(tmp_path)
    staged=stage.stage_risk_input_bundle(bundle,**kwargs)
    result=stage.execute_staged_risk(root=kwargs['root'],binding_sha256=staged['binding_sha256'],
        namespace=kwargs['namespace'],session=kwargs['session'],output_path=tmp_path/'published-risk',
        execution_at=NOW+timedelta(hours=1))
    assert result['risk_sha256']==host_result['outputs']['risk_sha256']
    assert len(checks)==2 and (len(calls),len(conn.calls))==counts


@pytest.mark.parametrize('mutation',['missing_phase','ack','symbols','assessment','receipt','admission'])
def test_wrapper_refuses_before_staging(tmp_path,mutation):
    bundle,kwargs,*_=pipeline(tmp_path);root=kwargs['root']
    if mutation=='missing_phase':(root/'receipts/components.result.json').unlink()
    if mutation=='ack':put(root/'control/build.accepted.json',{})
    if mutation=='symbols':put(root/'control/symbols.txt',b'OTHER\n')
    if mutation=='receipt':kwargs['execute_receipt_sha256']='d'*64
    if mutation in ('assessment','admission'):
        path=kwargs['execute_receipt_path'];doc=json.loads(path.read_bytes())
        if mutation=='assessment':doc['outputs']['assessment_manifest']['sha256']='d'*64
        else:doc['outputs']['admission_sha256']='d'*64
        kwargs['execute_receipt_sha256']=put(path,doc)
    with pytest.raises((ValueError,FileNotFoundError)):
        stage.stage_risk_input_bundle(bundle,**kwargs)
    assert not (root/'risk-inputs').exists() and not (root/'control/risk-stage.started.json').exists()


def test_risk_replay_rejects_different_host_result(tmp_path):
    bundle,kwargs,*_=pipeline(tmp_path)
    path=kwargs['execute_receipt_path'];doc=json.loads(path.read_bytes());doc['outputs']['risk_sha256']='d'*64
    kwargs['execute_receipt_sha256']=put(path,doc)
    staged=stage.stage_risk_input_bundle(bundle,**kwargs)
    with pytest.raises(ValueError,match='STAGE_EXECUTOR_RISK_MISMATCH'):
        stage.execute_staged_risk(root=kwargs['root'],binding_sha256=staged['binding_sha256'],
          namespace=kwargs['namespace'],session=kwargs['session'],output_path=tmp_path/'rejected-risk',
          execution_at=NOW+timedelta(hours=1))


def test_inventory_preserves_non_alphabetical_causal_bytes():
    inventory=stage.causal_inventory(b'ZZZ\nAAA\n',namespace='test',session='2026-09-18',markets={'AAA':'US','ZZZ':'US'})
    assert [r['symbol'] for r in inventory['symbols']]==['ZZZ','AAA']
    with pytest.raises(ValueError,match='SYMBOL_INVALID'):
        stage.causal_inventory('ÁAA\n'.encode(),namespace='test',session='2026-09-18',markets={})


def test_staging_budget_covers_measured_e8_and_remains_fail_closed(tmp_path, monkeypatch):
    import base64
    assert stage.MAX_TOTAL == 2 * 1024 * 1024 * 1024
    assert stage.MAX_TOTAL >= 958924104 * 1.5
    bundle, kwargs, *_, host_result = pipeline(tmp_path)
    total = sum(len(base64.b64decode(body)) for body in bundle['files'].values())
    manifest = kwargs['execute_receipt_path'].parent / 'assessment' / host_result['outputs']['assessment_manifest']['path']
    digest = host_result['outputs']['assessment_manifest']['sha256']
    validate = dict(namespace=kwargs['namespace'], session=kwargs['session'], symbols=['SYNTH'],
                    admission_sha256=host_result['outputs']['admission_sha256'])
    monkeypatch.setattr(stage, 'MAX_TOTAL', total)
    assert stage.build_bundle(manifest, digest) == bundle
    assert stage.validate_bundle(bundle, **validate)
    monkeypatch.setattr(stage, 'MAX_TOTAL', total - 1)
    with pytest.raises(ValueError, match='STAGE_TOTAL_LIMIT'):
        stage.build_bundle(manifest, digest)
    with pytest.raises(ValueError, match='STAGE_TOTAL_LIMIT'):
        stage.validate_bundle(bundle, **validate)
    assert not (kwargs['root'] / 'control/risk-stage.started.json').exists()
