from datetime import timedelta
import json
import os
from pathlib import Path
import pytest
from app import r2d2_v2_massive_supervisor as service
from app.r2d2_v2_massive_scheduler import MinuteExpiry
from test_r2d2_v2_minute_bars import MINUTE,calendar
from test_r2d2_v2_massive_stream import state


def test_rollback_five_ms_does_not_fail_or_fabricate_market_timestamp(calendar):
    stream,out=state(calendar);elapsed=[0.0]
    tick=MinuteExpiry(stream,MINUTE,monotonic=lambda:elapsed[0])
    elapsed[0]=150.001
    assert tick(MINUTE+timedelta(seconds=150))==0
    elapsed[0]=150.002
    assert tick(MINUTE+timedelta(seconds=149.995))==0
    elapsed[0]=150.01;received=MINUTE+timedelta(seconds=150.005)
    assert tick(received)==1
    assert out[0][1]['event']['at']==MINUTE.isoformat()
    assert out[0][1]['event']['available_at']==received.isoformat()


def test_forward_wall_jump_cannot_expire_before_monotonic_deadline(calendar):
    stream,out=state(calendar);elapsed=[0.0]
    tick=MinuteExpiry(stream,MINUTE,monotonic=lambda:elapsed[0])
    elapsed[0]=1
    assert tick(MINUTE+timedelta(hours=3))==0 and not out


def test_monotonic_reversal_refuses(calendar):
    stream,out=state(calendar);elapsed=[5.0]
    tick=MinuteExpiry(stream,MINUTE,monotonic=lambda:elapsed[0]);elapsed[0]=4.999
    with pytest.raises(Exception,match='MONOTONIC_REVERSED'):tick(MINUTE)
    assert not out


@pytest.fixture
def setup(tmp_path,calendar):
    for name in ('manifests','journal','state'):(tmp_path/name).mkdir(mode=0o700)
    manifest={'epoch':'test','session':MINUTE.date().isoformat(),'symbols':['AAPL'],'owner_uid':os.geteuid()}
    path=tmp_path/'manifests'/(manifest['session']+'.json');path.write_text(json.dumps(manifest));path.chmod(0o600)
    token=tmp_path/'token';token.write_text('test-secret\n');token.chmod(0o600)
    notices=[];calls=[]
    def runner(*args,**kwargs):
        calls.append(args);assert args[3]()=='test-secret'
        raise RuntimeError('test-secret must never escape')
    def invoke(**changes):
        options=dict(calendar=calendar,utcnow=lambda:MINUTE,monotonic=lambda:0,stop=lambda:False,notice=notices.append,runner=runner)
        options.update(changes)
        return service.supervised_attempt(tmp_path/'journal',tmp_path/'manifests',token,tmp_path/'state',**options)
    return tmp_path,invoke,notices,calls


def test_four_attempts_persist_across_invocations_then_refuse(setup):
    root,invoke,notices,calls=setup
    assert [invoke() for _ in range(5)]==[1,1,1,1,78]
    assert len(calls)==4 and len(list((root/'state').glob('*.attempt-*.json')))==4
    assert 'test-secret' not in json.dumps(notices)
    assert notices[-1]['status']=='DATA_GAP' and notices[-1]['provider_connected'] is False


def test_changed_manifest_cannot_reset_cap(setup):
    root,invoke,notices,calls=setup;assert invoke()==1
    p=next((root/'manifests').glob('*.json'));manifest=json.loads(p.read_text());manifest['symbols']=['MSFT'];p.write_text(json.dumps(manifest))
    assert invoke()==78 and len(calls)==1


@pytest.mark.parametrize('kind',['public','symlink','fifo'])
def test_unsafe_token_never_connects(setup,kind):
    root,invoke,notices,calls=setup;p=root/'token'
    if kind=='public':p.chmod(0o644)
    elif kind=='symlink':p.rename(root/'real-token');p.symlink_to(root/'real-token')
    else:p.unlink();os.mkfifo(p,0o600)
    assert invoke()==78 and calls==[]


def test_window_refusal_precedes_claim_secret_and_connection(setup,calendar):
    root,invoke,notices,calls=setup
    assert invoke(utcnow=lambda:calendar.details(MINUTE.date())['close'])==78
    assert calls==[] and list((root/'state').iterdir())==[]


def test_success_exits_without_requesting_restart(setup):
    root,invoke,notices,calls=setup
    assert invoke(runner=lambda *a,**k:{'status':'SESSION_LIMIT'})==0


def test_session_stop_uses_elapsed_time_under_wall_rollback(tmp_path,calendar,monkeypatch):
    from app.r2d2_v2_massive_producer import run_session
    elapsed=[0.0];wall=[MINUTE];observed=[]
    def fake(*args,**kwargs):
        duration=kwargs['max_seconds'];wall[0]-=timedelta(milliseconds=5)
        elapsed[0]=duration-.001;observed.append(kwargs['stop']())
        elapsed[0]=duration;observed.append(kwargs['stop']())
        return {'status':'STOPPED'}
    monkeypatch.setattr('app.r2d2_v2_massive_producer._run_session_root',fake)
    run_session(tmp_path,{'epoch':'test','session':MINUTE.date().isoformat(),'symbols':['AAPL'],'owner_uid':os.geteuid()},calendar,lambda:'test',
        utcnow=lambda:wall[0],monotonic=lambda:elapsed[0],stop=lambda:False,supervisor=lambda x:None)
    assert observed==[False,True]


def test_unit_binds_restart_backoff_cap_and_private_token_path():
    root=Path(__file__).resolve().parents[2]/'deployment'/'massive-supervisor'
    unit=(root/'c3po-massive.service').read_text()
    assert all(value in unit for value in ('Restart=on-failure','RestartSec=30s','StartLimitBurst=4','StartLimitIntervalSec=8h','RestartPreventExitStatus=78','--token-file /etc/c3po-bar/token'))
    assert 'MASSIVE_API_KEY=' not in unit


def test_competing_wrapper_cannot_open_second_connection(setup):
    root,invoke,notices,calls=setup;other=[]
    def active(*args,**kwargs):
        other.append(invoke())
        return {'status':'STOPPED'}
    assert invoke(runner=active)==0
    assert other==[78] and calls==[]
    assert len(list((root/'state').glob('*.attempt-*.json')))==1


def test_corrupt_prior_claim_never_replenishes_attempts(setup):
    root,invoke,notices,calls=setup;assert invoke()==1
    claim=next((root/'state').glob('*.attempt-*.json'));claim.write_bytes(b'not-json')
    assert invoke()==78 and len(calls)==1


def test_secret_loading_past_close_never_enters_provider_lifecycle(tmp_path,calendar,monkeypatch):
    from app.r2d2_v2_massive_producer import run_session
    close=calendar.details(MINUTE.date())['close'];wall=[close-timedelta(seconds=1)];elapsed=[0.]
    def token():wall[0]=close+timedelta(seconds=120);elapsed[0]=121.;return 'secret'
    monkeypatch.setattr('app.r2d2_v2_massive_producer._run_session_root',lambda *a,**k:pytest.fail('late provider lifecycle'))
    with pytest.raises(Exception,match='MASSIVE_SERVICE_WINDOW'):
        run_session(tmp_path,{'epoch':'test','session':MINUTE.date().isoformat(),'symbols':['AAPL'],'owner_uid':os.geteuid()},calendar,token,
            utcnow=lambda:wall[0],monotonic=lambda:elapsed[0],stop=lambda:False,supervisor=lambda x:None)


def test_secret_rollback_before_open_window_never_connects(tmp_path,calendar,monkeypatch):
    from app.r2d2_v2_massive_producer import run_session
    lower=calendar.details(MINUTE.date())['open']-timedelta(seconds=60);wall=[lower]
    def token():wall[0]-=timedelta(seconds=1);return 'secret'
    monkeypatch.setattr('app.r2d2_v2_massive_producer._run_session_root',lambda *a,**k:pytest.fail('before window'))
    with pytest.raises(Exception,match='MASSIVE_SERVICE_WINDOW'):
        run_session(tmp_path,{'epoch':'test','session':MINUTE.date().isoformat(),'symbols':['AAPL'],'owner_uid':os.geteuid()},calendar,token,
            utcnow=lambda:wall[0],monotonic=lambda:0,stop=lambda:False,supervisor=lambda x:None)
