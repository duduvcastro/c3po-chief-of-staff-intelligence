"""Artifact-only CLI integration; synthetic providers, no network or production DB."""
import hashlib
import json
import stat
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from app import r2d2_v2_risk_host_executor as host
from test_r2d2_v2_risk_executor import fixture, encode, NOW
from test_r2d2_v2_risk_runner import provider, reader, Connection


def package(tmp_path, mutate=None, b3=False):
    replay, root, save = fixture(tmp_path)
    def put(name, value):
        raw=encode(value);path=root/name;path.write_bytes(raw);path.chmod(0o600)
        return {'path':name,'sha256':hashlib.sha256(raw).hexdigest()}
    scope={'namespace':replay['namespace'],'session_date':replay['session_date'],'cutoff_at':NOW.isoformat(),'phases':list(host.PHASES)}
    replay['admission']=put('admission.json',{'symbols':{'SYNTH':{}},'namespace':scope['namespace'],'session_date':scope['session_date']})
    if b3: replay['symbols'][0]={'symbol':'SYNTH','market':'B3'}
    save()
    runtime=Path(host.__file__).absolute().parents[1]
    pins={'schema':'RISK_HOST_SOURCE_PINS_V1','files':{p.relative_to(runtime).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (runtime/'app').rglob('*.py')}}
    spool=tmp_path/'spool';spool.mkdir(mode=0o700)
    windows={phase:{'not_before':NOW.isoformat(),'not_after':(NOW+timedelta(hours=2)).isoformat()} for phase in host.PHASES}
    plan={'schema':host.SCHEMA,**{k:v for k,v in scope.items() if k!='phases'},'phase_windows':windows,
          'runtime_source_root':str(runtime),'spool_root':str(spool),
          'source_pins':put('SOURCE_PINS.json',pins),'replay_manifest':put('manifest.json',replay),
          'admission':replay['admission'],'list':put('list.json',{'namespace':scope['namespace'],'session_date':scope['session_date'],'symbols':[{'symbol':'SYNTH','market':'B3' if b3 else 'US'}]}),
          'owner_order':put('order.json',{'schema':'R2D2_V2_RISK_HOST_ORDER_V1','scope':scope,'actions':['READ_PROVIDERS','READ_DATABASE','WRITE_PRIVATE_RISK_ARTIFACTS']}),
          'limits':{'max_symbols':1,'max_total_requests':20,'max_body_bytes':1048576,'max_total_bytes':10485760,'max_elapsed_seconds':3600}}
    if mutate:mutate(plan,put)
    planref=put('host-plan.json',plan)
    binding={'manifest_sha256':planref['sha256'],'owner_order_sha256':plan['owner_order']['sha256'],'source_pins_sha256':plan['source_pins']['sha256'],'list_sha256':plan['list']['sha256'],'admission_sha256':plan['admission']['sha256'],**scope,'phase_windows':windows}
    goref=put('go.json',{'schema':'R2D2_V2_RISK_HOST_GO_V1','verdict':'GO','scope':'RISK_ARTIFACT_ONLY','binding':binding})
    return dict(manifest_path=root/planref['path'],manifest_sha256=planref['sha256'],go_path=root/goref['path'],go_sha256=goref['sha256'],source_root=runtime,spool_root=spool)


class Clock:
    def __init__(self):self.value=NOW+timedelta(seconds=1)
    def __call__(self):self.value+=timedelta(seconds=1);return self.value


def test_cli_three_phases_actual_pipeline_private_outputs(tmp_path,monkeypatch,capsys):
    args=package(tmp_path);clock=Clock();calls=[]
    real=host.run_host_phase
    def transport(request):calls.append(request);return provider(request)
    def run(**kwargs):return real(**kwargs,clock=clock,transport=transport,database_reader=reader(Connection()))
    monkeypatch.setattr(host,'run_host_phase',run)
    previous=None
    for phase in host.PHASES:
        argv=['executor',phase]
        for key,value in args.items():argv.extend(['--'+key.replace('_path','').replace('_','-'),str(value)])
        if previous:argv.extend(['--previous-receipt-sha256',previous])
        monkeypatch.setattr(sys,'argv',argv)
        assert host.main()==0
        public=capsys.readouterr().out
        assert 'SYNTH' not in public and 'token' not in public.lower()
        previous=json.loads(public)['receipt_sha256']
    assert len(calls)==1
    destination=args['spool_root']/args['manifest_sha256']
    risk=json.loads((destination/'risk-output/risk.json').read_bytes())
    assert risk['symbols']['SYNTH']['value'] is not None
    assessment=json.loads((destination/'assessment/assessment-clock-0.json').read_bytes())
    assert assessment['computed_at']>NOW.isoformat() and assessment['available_at']>assessment['computed_at']
    for file in destination.rglob('*'):
        assert stat.S_IMODE(file.stat().st_mode)==(0o700 if file.is_dir() else 0o600)
    receipt=json.loads((destination/'execute.RECEIPT.json').read_bytes())
    assert receipt['operation_activation'] is False and receipt['certification_granted'] is False


@pytest.mark.parametrize('kind',['go_hash','source','admission','window','budget'])
def test_preflight_refusals_before_any_provider(tmp_path,kind):
    def mutate(plan,put):
        if kind=='admission':plan['admission']=put('wrong-admission.json',{'symbols':{'EXTRA':{}}})
        if kind=='budget':plan['limits']['max_total_bytes']=0
        if kind=='window':plan['phase_windows']['preflight']['not_after']=NOW.isoformat()
        if kind=='source':plan['source_pins']=put('bad-pins.json',{'schema':'RISK_HOST_SOURCE_PINS_V1','files':{}})
    args=package(tmp_path,mutate)
    if kind=='go_hash':args['go_sha256']='0'*64
    calls=[]
    with pytest.raises(ValueError):host.run_host_phase(phase='preflight',**args,clock=Clock(),transport=lambda r:calls.append(r))
    assert not calls and not list(args['spool_root'].iterdir())


def test_uncertain_acquire_never_replayed(tmp_path):
    args=package(tmp_path);clock=Clock()
    previous=host.run_host_phase(phase='preflight',**args,clock=clock)['receipt_sha256']
    def fail(*_):raise ValueError('synthetic DB failure')
    with pytest.raises(ValueError):host.run_host_phase(phase='acquire',**args,clock=clock,previous_receipt_sha256=previous,transport=provider,database_reader=fail)
    destination=args['spool_root']/args['manifest_sha256']
    assert (destination/'acquire.STARTED.json').exists() and not (destination/'acquire.RECEIPT.json').exists()
    with pytest.raises(FileExistsError):host.run_host_phase(phase='acquire',**args,clock=clock,previous_receipt_sha256=previous,transport=provider,database_reader=reader(Connection()))


def test_wrong_previous_receipt_blocks_acquire(tmp_path):
    args=package(tmp_path);clock=Clock()
    host.run_host_phase(phase='preflight',**args,clock=clock)
    with pytest.raises(ValueError):host.run_host_phase(phase='acquire',**args,clock=clock,previous_receipt_sha256='a'*64)
    assert not (args['spool_root']/args['manifest_sha256']/'acquire.STARTED.json').exists()


def test_b3_without_credentials_network_or_database(tmp_path,monkeypatch):
    from app import r2d2_v2_risk_runner as runner
    args=package(tmp_path,b3=True);clock=Clock()
    def forbid(**_):raise AssertionError('B3 cannot construct credentials')
    monkeypatch.setattr(runner,'runtime_dependencies',forbid)
    previous=None
    for phase in host.PHASES:
        result=host.run_host_phase(phase=phase,**args,clock=clock,previous_receipt_sha256=previous)
        previous=result['receipt_sha256']
    risk=json.loads((args['spool_root']/args['manifest_sha256']/'risk-output/risk.json').read_bytes())
    assert risk['symbols']['SYNTH']['value'] is None


def test_acquisition_byte_budget_leaves_uncertain_marker(tmp_path):
    args=package(tmp_path,lambda plan,_:plan['limits'].update(max_total_bytes=1));clock=Clock()
    previous=host.run_host_phase(phase='preflight',**args,clock=clock)['receipt_sha256']
    with pytest.raises(ValueError,match='BUDGET'):
        host.run_host_phase(phase='acquire',**args,clock=clock,previous_receipt_sha256=previous,transport=provider,database_reader=reader(Connection()))
    destination=args['spool_root']/args['manifest_sha256']
    assert (destination/'acquire.STARTED.json').exists()
    assert not (destination/'acquire.RECEIPT.json').exists()
    assert not (destination/'capture/MANIFEST.json').exists()
