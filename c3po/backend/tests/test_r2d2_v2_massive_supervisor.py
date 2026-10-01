from datetime import timedelta
import json
import os
from pathlib import Path
import re
import shlex
import stat
from types import SimpleNamespace
from typing import Any
import pytest
from app import r2d2_v2_massive_supervisor as service
from app.r2d2_v2_massive_scheduler import MinuteExpiry
from test_r2d2_v2_minute_bars import MINUTE,calendar
from test_r2d2_v2_massive_stream import state
from test_r2d2_v2_massive_transport import Socket

UNIT_ROOT=Path(__file__).resolve().parents[2]/'deployment'/'massive-supervisor'
PLACEHOLDERS={'@IMAGE_ID@','@HOST_JOURNAL_ROOT@','@CONTAINER_JOURNAL_ROOT@','@HOST_STATE_ROOT@','@HOST_CONFIG_DIR@','@NETWORK@'}
SUPERVISOR_TAIL=['python','-B','-m','app.r2d2_v2_massive_supervisor','--journal-root','@CONTAINER_JOURNAL_ROOT@',
    '--manifest-directory','/etc/c3po-bar/manifests','--token-file','/etc/c3po-bar/token','--state-root','/var/lib/c3po-bar/supervisor']
EPOCH='R2D2-V2-CONTAINER-LAYOUT'


def unit_text():return (UNIT_ROOT/'c3po-massive.service').read_text()


def exec_start(unit):
    lines=[line for line in unit.replace('\\\n',' ').splitlines() if line.startswith('ExecStart=')]
    assert len(lines)==1
    return shlex.split(lines[0][len('ExecStart='):])


def run_options(argv,image):
    """(options before the image, command after it); only --rm/--read-only are valueless."""
    assert argv[:2]==['/usr/bin/docker','run'] and argv.count(image)==1
    at=argv.index(image);head=argv[2:at];options=[];index=0
    while index<len(head):
        assert head[index].startswith('--')
        if head[index] in ('--rm','--read-only'):options.append((head[index],None));index+=1
        else:options.append((head[index],head[index+1]));index+=2
    return options,argv[at+1:]


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
    notices=[];calls=[];elapsed=[0.0]
    def runner(*args,**kwargs):
        calls.append(args);assert args[3]()=='test-secret'
        raise RuntimeError('test-secret must never escape')
    def invoke(**changes):
        options=dict(calendar=calendar,utcnow=lambda:MINUTE,monotonic=lambda:elapsed[0],stop=lambda:False,notice=notices.append,runner=runner,
            sleep=lambda seconds:elapsed.__setitem__(0,elapsed[0]+seconds))
        options.update(changes)
        return service.supervised_attempt(tmp_path/'journal',tmp_path/'manifests',token,tmp_path/'state',**options)
    return tmp_path,invoke,notices,calls


def test_five_attempts_persist_across_invocations_then_refuse(setup):
    root,invoke,notices,calls=setup
    assert [invoke() for _ in range(6)]==[1,1,1,1,1,78]
    assert len(calls)==5 and len(list((root/'state').glob('*.attempt-*.json')))==5
    assert [n['seconds'] for n in notices if n['status']=='BACKOFF']==[30,60,120,240]
    assert notices[-1]['code']=='SUPERVISOR_ATTEMPTS_EXHAUSTED'
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
    unit=unit_text();lines=unit.splitlines()
    assert all(value in unit for value in ('Restart=on-failure','RestartSec=1s','StartLimitBurst=6','StartLimitIntervalSec=8h','RestartPreventExitStatus=78','--token-file /etc/c3po-bar/token'))
    assert 'MASSIVE_API_KEY=' not in unit
    assert 'OnBootSec=30s' in (UNIT_ROOT/'c3po-massive.timer').read_text()
    assert all(value in lines for value in ('Requires=docker.service','TimeoutStopSec=30s','KillMode=control-group',
        'ExecStartPre=-/usr/bin/docker rm c3po-massive','ExecStop=-/usr/bin/docker stop -t 25 c3po-massive',
        'ExecStopPost=-/usr/bin/docker stop -t 25 c3po-massive'))
    after=[line for line in lines if line.startswith('After=')]
    assert len(after)==1 and 'docker.service' in after[0].split('=',1)[1].split()
    assert [line for line in lines if line.startswith('Environment')]==['Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli']
    assert not any(line.lstrip().startswith('#') for line in lines)
    assert [sum(line.startswith(key+'=') for line in lines) for key in ('ExecStartPre','ExecStart','ExecStop','ExecStopPost')]==[1,1,1,1]


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


def test_two_minute_provider_outage_retains_later_retry(setup):
    root,invoke,notices,calls=setup;elapsed=[0.0];attempts=[]
    def runner(*a,**k):
        attempts.append(elapsed[0])
        if elapsed[0]<120:raise RuntimeError('unavailable')
        return {'status':'STOPPED'}
    def run():
        return invoke(runner=runner,monotonic=lambda:elapsed[0],
            utcnow=lambda:MINUTE+timedelta(seconds=elapsed[0]),
            sleep=lambda seconds:elapsed.__setitem__(0,elapsed[0]+seconds))
    assert [run(),run(),run(),run()]==[1,1,1,0]
    assert attempts==[0,30,90,210]


def test_stop_during_backoff_sends_no_second_provider_attempt(setup):
    root,invoke,notices,calls=setup;assert invoke()==1
    elapsed=[0.0]
    assert invoke(monotonic=lambda:elapsed[0],stop=lambda:elapsed[0]>=2,
        sleep=lambda seconds:elapsed.__setitem__(0,elapsed[0]+seconds))==0
    assert len(calls)==1 and notices[-1]['status']=='STOPPED'


def test_window_closes_during_backoff_refuses_without_second_attempt(setup,calendar):
    root,invoke,notices,calls=setup;assert invoke()==1
    elapsed=[0.0];before=calendar.details(MINUTE.date())['close']-timedelta(seconds=2)
    assert invoke(monotonic=lambda:elapsed[0],utcnow=lambda:before+timedelta(seconds=elapsed[0]),
        sleep=lambda seconds:elapsed.__setitem__(0,elapsed[0]+seconds))==78
    assert len(calls)==1 and notices[-1]['code']=='SUPERVISOR_WINDOW'


def test_backoff_clock_rollback_refuses_without_second_attempt(setup):
    root,invoke,notices,calls=setup;assert invoke()==1
    elapsed=[1.0]
    assert invoke(monotonic=lambda:elapsed[0],sleep=lambda seconds:elapsed.__setitem__(0,0.0))==78
    assert len(calls)==1 and notices[-1]['code']=='SUPERVISOR_MONOTONIC'


def test_safe_refusal_code_never_echoes_arbitrary_exception_data():
    from app.r2d2_v2_sources import SourceUnavailable
    assert service.refusal_code(SourceUnavailable('SUPERVISOR_WINDOW'))=='SUPERVISOR_WINDOW'
    for error in (RuntimeError('secret-token'),SourceUnavailable('secret-token'),SourceUnavailable(['secret-token'])):
        assert service.refusal_code(error)=='SUPERVISOR_UNVERIFIED'
    assert service.refusal_code(OSError(13,'secret-path'))=='SUPERVISOR_FILE_UNAVAILABLE'


def test_boot_outside_session_refuses_before_files_are_read(tmp_path,calendar,monkeypatch):
    monkeypatch.setattr(service,'private_bytes',lambda *a:pytest.fail('boot outside window read a private file'))
    notices=[];now=calendar.details(MINUTE.date())['open']-timedelta(minutes=10)
    assert service.supervised_attempt(tmp_path,tmp_path,tmp_path/'token',tmp_path,calendar=calendar,
        utcnow=lambda:now,monotonic=lambda:0,stop=lambda:False,notice=notices.append)==78
    assert notices[-1]['code']=='SUPERVISOR_WINDOW'


def test_unit_container_flags_are_pinned():
    unit=unit_text();options,tail=run_options(exec_start(unit),'@IMAGE_ID@')
    assert options==[('--rm',None),('--name','c3po-massive'),('--pull','never'),('--user','0:0'),('--workdir','/app'),
        ('--network','@NETWORK@'),('--read-only',None),('--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=256m'),
        ('--cap-drop','ALL'),('--security-opt','no-new-privileges'),('--pids-limit','512'),('--stop-timeout','25'),
        ('--mount','type=bind,source=@HOST_JOURNAL_ROOT@,target=@CONTAINER_JOURNAL_ROOT@'),
        ('--mount','type=bind,source=@HOST_STATE_ROOT@,target=/var/lib/c3po-bar/supervisor'),
        ('--mount','type=bind,source=@HOST_CONFIG_DIR@,target=/etc/c3po-bar,readonly')]
    mounts=[value for name,value in options if name=='--mount']
    assert len(mounts)==3 and all(value.startswith('type=bind,source=') for value in mounts)
    assert [value for value in mounts if value.endswith(',readonly')]==[mounts[2]] and ',target=/etc/c3po-bar,' in mounts[2]
    assert tail==SUPERVISOR_TAIL
    assert set(re.findall(r'@[A-Z_]+@',unit))==PLACEHOLDERS and unit.count('@')==2*len(re.findall(r'@[A-Z_]+@',unit))
    assert unit.count('@HOST_CONFIG_DIR@')==3 and unit.count('@IMAGE_ID@')==1 and unit.count('@NETWORK@')==1
    # None of these in the template is what makes the shlex rendering equivalent to systemd's own parsing.
    assert not set('%$"\';')&set(unit)


def test_unit_forbids_unsafe_container_options():
    unit=unit_text();argv=exec_start(unit)
    forbidden={'--init','--restart','-d','--detach','-t','-i','-e','--env','--env-file','-v','--volume','--privileged',
        '--cap-add','--cidfile','--pid','--ipc','--tty','--interactive','--device','--add-host','--publish','-p','--userns'}
    assert not forbidden&set(argv) and not any(value.split('=',1)[0] in forbidden for value in argv)
    assert not any(value in unit for value in ('docker.sock','DOCKER_HOST','c3po/backend:production',':rollback','/opt/c3po-bar',
        'User=','Group=','TZ=','rm -f','--force','ProtectSystem','ReadOnlyPaths','ReadWritePaths','MASSIVE_API_KEY','--token-env'))
    stops=re.findall(r'^ExecStop(?:Post)?=-/usr/bin/docker stop -t (\d+) c3po-massive$',unit,re.M)
    grace=int(dict(run_options(argv,'@IMAGE_ID@')[0])['--stop-timeout'])
    limit=re.search(r'^TimeoutStopSec=(\d+)s$',unit,re.M)
    assert limit is not None and stops==['25','25'] and grace==25<int(limit.group(1))==30


def test_rendered_unit_paths_match_backend_data_mount(monkeypatch):
    from app.config import Settings
    values={'@IMAGE_ID@':'sha256:'+'a'*64,'@HOST_JOURNAL_ROOT@':'/mnt/day-d-data/r2d2-v2-massive-epoch03',
        '@CONTAINER_JOURNAL_ROOT@':'/app/day-d-data/r2d2-v2-massive-epoch03','@HOST_STATE_ROOT@':'/var/lib/c3po-bar/supervisor',
        '@HOST_CONFIG_DIR@':'/etc/c3po-bar','@NETWORK@':'bridge'}
    assert set(values)==PLACEHOLDERS
    unit=unit_text()
    for name,value in values.items():unit=unit.replace(name,value)
    assert '@' not in unit
    options,tail=run_options(exec_start(unit),values['@IMAGE_ID@'])
    arguments=dict(zip(tail[4::2],tail[5::2]));mounts={}
    for name,value in options:
        if name=='--mount':
            fields=dict(item.split('=',1) for item in value.split(',') if '=' in item);mounts[fields['target']]=fields['source']
    assert set(arguments)=={'--journal-root','--manifest-directory','--token-file','--state-root'}
    assert all(Path(value).is_absolute() for value in list(arguments.values())+list(mounts)+list(mounts.values()))
    journal=Path(arguments['--journal-root']);state_root=Path(arguments['--state-root'])
    assert set(mounts)=={str(journal),str(state_root),'/etc/c3po-bar'}
    assert Path(arguments['--manifest-directory']).parent==Path(arguments['--token-file']).parent==Path('/etc/c3po-bar')
    # Same leaf below the data mount on both sides: host /mnt/day-d-data/<leaf> is /app/day-d-data/<leaf>.
    host_journal=Path(mounts[str(journal)])
    assert journal.parent==Path('/app/day-d-data') and host_journal.name==journal.name and host_journal.parent==Path('/mnt/day-d-data')
    compose=(UNIT_ROOT.parents[1]/'compose.yml').read_text()
    worker=re.search(r'^  r2d2-worker:\n((?:    .*\n|\n)+)',compose,re.M)
    assert worker is not None and re.search(r'^      - \S+:/app/day-d-data$',worker.group(1),re.M)
    # r2d2-worker is NOT the journal reader (it runs app.r2d2_worker); it only shows how the backend image mounts the
    # data volume and that neither compose nor the image selects a user. The reader's launcher must match both.
    assert re.search(r'^    command: \["python", "-m", "app\.r2d2_worker"\]$',worker.group(1),re.M)
    assert 'r2d2_v2_shadow_worker' not in compose
    assert not re.search(r'^    user:',worker.group(1),re.M)
    assert not re.search(r'^\s*USER\b',(UNIT_ROOT.parents[1]/'backend'/'Dockerfile').read_text(),re.M)
    assert state_root!=journal and journal not in state_root.parents and state_root not in journal.parents
    for target in (str(state_root),'/etc/c3po-bar'):
        assert host_journal.parent not in Path(mounts[target]).parents and Path(mounts[target])!=host_journal.parent
    monkeypatch.setenv('C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR',str(journal))
    assert Settings().r2d2_v2_massive_journal_dir==journal


@pytest.fixture
def container(tmp_path,calendar,monkeypatch):
    """Container layout on temporary directories: data(0755)/journal(0700), sibling state, etc/{manifests,token}."""
    from app import r2d2_v2_massive_producer as producer
    from app.r2d2_v2_massive_producer import run_session
    monkeypatch.setattr(producer,'MIN_SESSION_FREE_BYTES',1)
    previous=os.umask(0o022);day=MINUTE.date().isoformat()
    def private(path,text):
        with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as output:output.write(text)
    def layout(name,*,owner_uid=None,nested_state=False):
        base=tmp_path.resolve()/name;base.mkdir(mode=0o700)
        tree=SimpleNamespace(data=base/'data',journal=base/'data'/'journal',etc=base/'etc',manifests=base/'etc'/'manifests',
            token=base/'etc'/'token',state=base/'data'/'journal'/'state' if nested_state else base/'state',day=day)
        tree.data.mkdir(mode=0o755)
        for path in (tree.journal,tree.state,tree.etc,tree.manifests):path.mkdir(mode=0o700)
        private(tree.manifests/(day+'.json'),json.dumps({'epoch':EPOCH,'session':day,'symbols':['AAPL'],
            'owner_uid':os.geteuid() if owner_uid is None else owner_uid}))
        private(tree.token,'test-secret\n')
        return tree
    def produce(tree):
        socket=Socket(['[{"ev":"status","status":"auth_success"}]']);stopped=[False];connects=[];notices=[]
        def recv(timeout):
            if socket.frames:return socket.frames.pop(0)
            stopped[0]=True;raise TimeoutError()
        socket.recv=recv
        def connect(uri,**options):connects.append(uri);return socket
        code=service.supervised_attempt(tree.journal,tree.manifests,tree.token,tree.state,calendar=calendar,
            utcnow=lambda:MINUTE,monotonic=lambda:0,stop=lambda:stopped[0],notice=notices.append,
            runner=lambda *a,**k:run_session(*a,connector=connect,**k))
        assert 'test-secret' not in json.dumps(notices)
        return code,notices,connects
    try:yield layout,produce
    finally:os.umask(previous)


def reader(journal,epoch=EPOCH):
    from app.r2d2_v2_shadow import EBAR_AMENDMENT_SHA
    from app.r2d2_v2_shadow_worker import _with_massive_source
    settings=SimpleNamespace(r2d2_v2_massive_bars_enabled=True,r2d2_v2_massive_journal_dir=journal)
    composite:Any=_with_massive_source(settings,object(),SimpleNamespace(mode='CERTIFIED',ebar_amendment_sha=EBAR_AMENDMENT_SHA,epoch=epoch))
    return composite.massive


def poll(source)->Any:return source.prepare_events(MINUTE+timedelta(minutes=5),{})


def tree_snapshot(root):
    found={}
    for parent,directories,files in os.walk(root):
        for name in ['.']+directories+files:
            info=os.lstat(os.path.join(parent,name))
            found[os.path.relpath(os.path.join(parent,name),root)]=(info.st_mode,info.st_uid,info.st_size,info.st_mtime_ns,info.st_dev,info.st_ino)
    return found


def claims(tree):return sorted(path.name for path in tree.state.glob('*.attempt-*.json'))


def test_container_layout_writer_and_reader_agree(container):
    layout,produce=container;tree=layout('agree')
    code,notices,connects=produce(tree)
    assert code==0 and connects==['wss://socket.massive.com/stocks'] and notices[-1]['status']=='STOPPED'
    assert claims(tree)==[tree.day+'.attempt-1.json']
    assert sorted(path.name for path in tree.state.iterdir())==sorted(claims(tree)+['producer.lock'])
    before=tree_snapshot(tree.journal)
    source=reader(tree.journal)
    assert source.journals.ready_sessions()==(tree.day,)
    result=poll(source)
    assert result['diagnostics']==[] and result['events'] and result['cursor']['sessions'][tree.day]>0
    assert all(event['instrument_key']=='US:AAPL' for event in result['events'])
    after=tree_snapshot(tree.journal)
    assert after==before and len(before)>6
    assert all(uid==os.geteuid() and not mode&0o077 for mode,uid,*_ in before.values())
    root=os.stat(tree.journal);catalog=json.loads((tree.journal/'epoch.json').read_text())
    assert (catalog['epoch'],catalog['device'],catalog['inode'])==(EPOCH,root.st_dev,root.st_ino)
    assert sorted(os.listdir(tree.journal))==['epoch.json','maintenance.lock','producer.lock','session_date='+tree.day]
    assert stat.S_IMODE(os.stat(tree.data).st_mode)==0o755 and stat.S_IMODE(root.st_mode)==0o700
    assert all(stat.S_IMODE(os.lstat(tree.state/name).st_mode)==0o600 for name in os.listdir(tree.state))


def test_reader_guards_stay_strict_for_container_layout(container,monkeypatch):
    from app.r2d2_v2_massive_sessions import SessionJournalRoot
    from app.r2d2_v2_sources import SourceUnavailable
    from app.r2d2_v2_store import ShadowIntegrityError
    layout,produce=container;tree=layout('strict');unverified=[{'code':'MASSIVE_SESSION_SOURCE_UNVERIFIED'}]
    assert produce(tree)[0]==0
    source=reader(tree.journal);assert poll(source)['diagnostics']==[]
    # Writer uid differs from reader uid: refused when the reader starts and at every poll.
    with monkeypatch.context() as other:
        other.setattr(os,'geteuid',lambda uid=os.geteuid()+1:uid)
        with pytest.raises(SourceUnavailable,match='^MASSIVE_SESSION_ROOT_OWNER$'):SessionJournalRoot(tree.journal,EPOCH)
        with pytest.raises(ShadowIntegrityError,match='^MASSIVE_SESSION_ROOT_UNVERIFIED$'):reader(tree.journal)
        assert poll(source)['diagnostics']==unverified
    assert poll(source)['diagnostics']==[]
    tree.journal.chmod(0o750)
    with pytest.raises(SourceUnavailable):SessionJournalRoot(tree.journal,EPOCH)
    with pytest.raises(ShadowIntegrityError,match='^MASSIVE_SESSION_ROOT_UNVERIFIED$'):reader(tree.journal)
    assert poll(source)['diagnostics']==unverified
    tree.journal.chmod(0o700);assert poll(source)['diagnostics']==[]
    foreign=tree.journal/'lost+found';foreign.mkdir(mode=0o700)
    assert poll(reader(tree.journal))['diagnostics']==unverified
    foreign.rmdir();assert poll(source)['diagnostics']==[]
    # The attempt journal may not live inside the session catalog.
    nested=layout('nested',nested_state=True);code,notices,connects=produce(nested)
    assert code==1 and connects==[] and notices[-1]=={'status':'FAILED','session':nested.day,
        'reason':'SUPERVISOR_PRODUCER_FAILURE','code':'MASSIVE_SERVICE_STORAGE_UNVERIFIED'}
    stranger=layout('stranger',owner_uid=os.geteuid()+1);code,notices,connects=produce(stranger)
    assert code==78 and connects==[] and list(stranger.state.iterdir())==[] and list(stranger.journal.iterdir())==[]
    assert notices[-1]['code']=='SUPERVISOR_MANIFEST' and notices[-1]['provider_connected'] is False
    # Token misprovision is seen only after the claim: it costs one attempt and ends the day.
    exposed=layout('exposed');exposed.etc.chmod(0o755);code,notices,connects=produce(exposed)
    assert code==78 and connects==[] and claims(exposed)==[exposed.day+'.attempt-1.json']
    assert notices[-1]['status']=='DATA_GAP' and notices[-1]['provider_connected'] is False
    assert list(exposed.journal.iterdir())==[]


def test_reader_refuses_empty_root_and_catalog_creation_is_idempotent(container):
    from app.r2d2_v2_massive_sessions import SessionJournalRoot
    from app.r2d2_v2_sources import SourceUnavailable
    from app.r2d2_v2_store import ShadowIntegrityError
    layout,produce=container;tree=layout('catalog')
    with pytest.raises(ShadowIntegrityError,match='^MASSIVE_SESSION_ROOT_UNVERIFIED$'):reader(tree.journal)
    assert list(tree.journal.iterdir())==[]
    SessionJournalRoot(tree.journal,EPOCH,create=True)
    assert sorted(os.listdir(tree.journal))==['epoch.json','maintenance.lock']
    assert all(stat.S_IMODE(os.lstat(tree.journal/name).st_mode)==0o600 for name in os.listdir(tree.journal))
    created=tree_snapshot(tree.journal)
    SessionJournalRoot(tree.journal,EPOCH,create=True)
    source=reader(tree.journal);result=poll(source)
    assert source.journals.ready_sessions()==() and result['diagnostics']==[] and result['events']==[]
    assert tree_snapshot(tree.journal)==created
    with pytest.raises(SourceUnavailable,match='^MASSIVE_SESSION_MANIFEST_CHANGED$'):SessionJournalRoot(tree.journal,'OTHER-EPOCH',create=True)
    with pytest.raises(ShadowIntegrityError,match='^MASSIVE_SESSION_ROOT_UNVERIFIED$'):reader(tree.journal,'OTHER-EPOCH')
    assert tree_snapshot(tree.journal)==created
    code,notices,connects=produce(tree)
    assert code==0 and len(connects)==1
    assert tree_snapshot(tree.journal)['epoch.json']==created['epoch.json']
    assert source.journals.ready_sessions()==(tree.day,) and poll(source)['diagnostics']==[]


def test_readme_names_the_five_operations_and_the_substitution_grammar():
    readme=(UNIT_ROOT/'README.md').read_text()
    headings=[line for line in readme.splitlines() if re.match(r'### \d\. ',line)]
    assert headings==['### 1. Preflight (read-only)','### 2. Provisioning (directories and configuration)',
        '### 3. Exclusive unit installation (no activation, no overwrite)','### 4. Readback / conference','### 5. Activation']
    assert all(value in readme for value in ('`^/[A-Za-z0-9._/-]+$`','`^sha256:[0-9a-f]{64}$`','`^[A-Za-z0-9][A-Za-z0-9_.-]*$`',
        '`host`, `none` and `container:*` are **forbidden in production**','**must fail if any `@` survives**',
        'one GO each','python -m app.r2d2_v2_shadow_worker','**No compose service launches that module.**',
        'MASSIVE_SESSION_ROOT_UNVERIFIED','MASSIVE_MAINTENANCE_BUSY','c3po/backend:massive-supervisor-'))
    assert all(name in readme for name in PLACEHOLDERS)


def test_pipeline_exercises_rendered_unit_on_a_real_engine():
    pipeline=(UNIT_ROOT.parents[2]/'.github'/'workflows'/'c3po-pipeline.yml').read_text()
    start=pipeline.index('      - name: Exercise the Massive supervisor unit against the backend image\n')
    step=pipeline[start:pipeline.index('\n      - name: ',start+1)]
    assert pipeline.index("--tag c3po/backend:pr-validation")<start
    assert all('"'+name+'"' in step for name in PLACEHOLDERS) and '"@NETWORK@": "none"' in step
    assert all(value in step for value in ('c3po/deployment/massive-supervisor/c3po-massive.service',
        "docker image inspect --format '{{.Id}}' c3po/backend:pr-validation",'^sha256:[0-9a-f]{64}$',
        'sudo install -d -m 0700 -o 0 -g 0','sudo env "DOCKER_CONFIG=$base/etc/docker-cli" "${argv[@]}"',
        '[ "$rc" -eq 78 ] ||','"status": "DATA_GAP"','sudo find "$base/state" "$base/data/journal" -mindepth 1',
        "docker ps -a --filter 'name=^c3po-massive$' -q"))
    assert 'continue-on-error' not in step and 'MASSIVE_API_KEY' not in step and 'secrets.' not in step
