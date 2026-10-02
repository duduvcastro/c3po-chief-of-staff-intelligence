from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
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
# The catalog-init script of the README (operation 4b), pinned here as a literal: the README states its own hash,
# so the two could otherwise change together unnoticed.
CATALOG_INIT_SHA256='715d7a660e7a2c4dd5c11287063726cc971156dd6fefc2365c431c9aee0f4bb7'
# The two journal placements of the README, with its own example pairs (host path, container path). A is outside
# the data volume, expected on the host's root filesystem (the receipt did not read that); B is a leaf of the data volume.
PLACEMENTS={'A':('/var/lib/c3po-bar/journal','/c3po-bar-journal'),
    'B':('/mnt/day-d-data/r2d2-v2-massive-epoch03','/app/day-d-data/r2d2-v2-massive-epoch03')}
DATA_VOLUME=Path('/mnt/day-d-data');DATA_TARGET=Path('/app/day-d-data');DEPLOY_TREE=Path('/opt/chief-of-staff-digital')
HOST_STATE_ROOT=Path('/var/lib/c3po-bar/supervisor');HOST_CONFIG_DIR=Path('/etc/c3po-bar')
# The unit's own container targets: the state root, the configuration directory and the tmpfs.
FIXED_TARGETS=(Path('/var/lib/c3po-bar/supervisor'),Path('/etc/c3po-bar'),Path('/tmp'))
# Read-only host receipt the README attributes its host facts to. Nothing here was measured by a test.
RECEIPT_OPERATION='GO_READONLY_SUPERVISOR_HOSTFACTS_01'
RECEIPT_STDOUT_SHA256='47abfa0a93d1ffbd7b90fd72a3e414a9c54ce3debda8e70ae679d45be36e528b'
RECEIPT_DATA_VOLUME_AVAILABLE=54070542336;RECEIPT_ROOT_FILESYSTEM_AVAILABLE=595212316672
# Top-level directories the image or the runtime provides: under placement A the container journal root is one new
# top-level directory, none of these. The README's own list is read from the document and compared with this one.
PROVIDED_TOP_LEVEL=frozenset('app bin boot dev etc home lib lib64 media mnt opt proc root run sbin srv sys tmp usr var'.split())
# The owner's decision record for placement A in this epoch, as the README cites it. Not hashed by any test.
DECISION_RECORD='DUDU_DECISION_BAR_JOURNAL_ON_MAIN_DISK.json'
DECISION_SHA256='76dcff838b5bb9feb54bbc3ee3f4de0567012571bcc6469d5c2b3cf326df64a0'


def unit_text():return (UNIT_ROOT/'c3po-massive.service').read_text()


def exec_start(unit):
    lines=[line for line in unit.replace('\\\n',' ').splitlines() if line.startswith('ExecStart=')]
    assert len(lines)==1
    return shlex.split(lines[0][len('ExecStart='):])


def run_options(argv,image):
    """(options before the image, command after it); only --rm/--init/--read-only are valueless."""
    assert argv[:2]==['/usr/bin/docker','run'] and argv.count(image)==1
    at=argv.index(image);head=argv[2:at];options=[];index=0
    while index<len(head):
        assert head[index].startswith('--')
        if head[index] in ('--rm','--init','--read-only'):options.append((head[index],None));index+=1
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
    assert all(value in lines for value in ('Requires=docker.service','TimeoutStartSec=60s','TimeoutStopSec=30s','KillMode=control-group',
        'ExecStop=-/usr/bin/docker stop -t 25 c3po-massive','ExecStopPost=-/usr/bin/docker stop -t 25 c3po-massive'))
    # The leftover removal may fail (leading '-'); the image check may not: a missing image fails the start
    # before any container is created.
    assert [line for line in lines if line.startswith('ExecStartPre=')]==['ExecStartPre=-/usr/bin/docker rm c3po-massive',
        'ExecStartPre=/usr/bin/docker image inspect --format {{.Id}} @IMAGE_ID@']
    assert [sum(line.startswith(key+'=') for line in lines) for key in ('TimeoutStartSec','TimeoutStopSec','RestartSec',
        'StartLimitBurst','StartLimitIntervalSec','RestartPreventExitStatus')]==[1]*6
    after=[line for line in lines if line.startswith('After=')]
    assert len(after)==1 and 'docker.service' in after[0].split('=',1)[1].split()
    assert [line for line in lines if line.startswith('Environment')]==['Environment=DOCKER_CONFIG=@HOST_CONFIG_DIR@/docker-cli']
    assert not any(line.lstrip().startswith('#') for line in lines)
    assert [sum(line.startswith(key+'=') for line in lines) for key in ('ExecStartPre','ExecStart','ExecStop','ExecStopPost')]==[2,1,1,1]


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
    assert options==[('--rm',None),('--init',None),('--restart','no'),('--name','c3po-massive'),('--pull','never'),('--user','0:0'),('--workdir','/app'),
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
    assert unit.count('@HOST_CONFIG_DIR@')==3 and unit.count('@IMAGE_ID@')==2 and unit.count('@NETWORK@')==1
    # None of these in the template is what makes the shlex rendering equivalent to systemd's own parsing.
    assert not set('%$"\';')&set(unit)


def test_unit_forbids_unsafe_container_options():
    unit=unit_text();argv=exec_start(unit)
    forbidden={'-d','--detach','-t','-i','-e','--env','--env-file','-v','--volume','--privileged',
        '--cap-add','--cidfile','--pid','--ipc','--tty','--interactive','--device','--add-host','--publish','-p','--userns'}
    assert not forbidden&set(argv) and not any(value.split('=',1)[0] in forbidden for value in argv)
    # The only restart policy is the explicit "no"; --init is a bare flag. systemd owns every restart.
    assert [argv[index+1] for index,value in enumerate(argv) if value=='--restart']==['no'] and argv.count('--init')==1
    assert not any(value.startswith(('--restart=','--init=')) for value in argv)
    assert not any(value in unit for value in ('docker.sock','DOCKER_HOST','c3po/backend:production',':rollback','/opt/c3po-bar',
        'User=','Group=','TZ=','rm -f','--force','ProtectSystem','ReadOnlyPaths','ReadWritePaths','MASSIVE_API_KEY','--token-env'))
    stops=re.findall(r'^ExecStop(?:Post)?=-/usr/bin/docker stop -t (\d+) c3po-massive$',unit,re.M)
    grace=int(dict(run_options(argv,'@IMAGE_ID@')[0])['--stop-timeout'])
    limit=re.search(r'^TimeoutStopSec=(\d+)s$',unit,re.M)
    assert limit is not None and stops==['25','25'] and grace==25<int(limit.group(1))==30


def overlaps(one,other):return one==other or one in other.parents or other in one.parents


def within(path,tree):return path==tree or tree in path.parents


def placement_refusal(placement,host,container,*,state=HOST_STATE_ROOT,config=HOST_CONFIG_DIR):
    """The refusals of the README's "Substitution grammar" that follow from the paths alone.

    A reading of the prose, not the installer (which is not in this repository). "The journal root is a mount
    point" and "the values differ from the signed ones" need the host and the authorisation; they are not here."""
    host,container,state,config=(Path(value) for value in (host,container,state,config))
    if any(overlaps(host,other) for other in (state,config)):return 'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT'
    if any(overlaps(container,other) for other in FIXED_TARGETS):return 'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'
    if any(within(other,DATA_VOLUME) for other in (state,config)):return 'PRIVATE_ROOT_INSIDE_DATA_VOLUME'
    if placement=='A':
        if within(host,DATA_VOLUME):return 'A_HOST_JOURNAL_INSIDE_DATA_VOLUME'
        if within(host,DEPLOY_TREE):return 'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE'
        # Exactly one component below "/", and not a directory the image or the runtime provides (/app among them).
        if len(container.parts)!=2:return 'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL'
        if container.name in PROVIDED_TOP_LEVEL:return 'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY'
        return None
    if placement=='B':
        if host.parent!=DATA_VOLUME:return 'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME'
        if container!=DATA_TARGET/host.name:return 'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF'
        return None
    return 'PLACEMENT_UNKNOWN'


def rendered_unit(host_journal,container_journal):
    values={'@IMAGE_ID@':'sha256:'+'a'*64,'@HOST_JOURNAL_ROOT@':host_journal,'@CONTAINER_JOURNAL_ROOT@':container_journal,
        '@HOST_STATE_ROOT@':str(HOST_STATE_ROOT),'@HOST_CONFIG_DIR@':str(HOST_CONFIG_DIR),'@NETWORK@':'bridge'}
    assert set(values)==PLACEHOLDERS
    unit=unit_text()
    for name,value in values.items():unit=unit.replace(name,value)
    assert '@' not in unit
    return unit,values


@pytest.mark.parametrize('placement',sorted(PLACEMENTS))
def test_rendered_unit_paths_match_the_signed_placement(monkeypatch,placement):
    from app.config import Settings
    unit,values=rendered_unit(*PLACEMENTS[placement])
    assert placement_refusal(placement,*PLACEMENTS[placement]) is None
    assert 'RequiresMountsFor='+' '.join((PLACEMENTS[placement][0],str(HOST_STATE_ROOT),str(HOST_CONFIG_DIR))) in unit.splitlines()
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
    host_journal=Path(mounts[str(journal)])
    compose=(UNIT_ROOT.parents[1]/'compose.yml').read_text()
    worker=re.search(r'^  r2d2-worker:\n((?:    .*\n|\n)+)',compose,re.M)
    assert worker is not None and re.search(r'^      - \S+:'+re.escape(str(DATA_TARGET))+'$',worker.group(1),re.M)
    dockerfile=(UNIT_ROOT.parents[1]/'backend'/'Dockerfile').read_text()
    if placement=='A':
        # Outside the data volume and outside the image's tree: next to the state root on the host, directly below
        # "/" in the container. No compose service is given either path, so every consumer binds it explicitly.
        assert host_journal.parent==HOST_STATE_ROOT.parent==Path('/var/lib/c3po-bar') and not within(host_journal,DATA_VOLUME)
        assert journal.parent==Path('/') and not within(journal,Path('/app')) and not within(journal,DATA_TARGET)
        assert str(host_journal.parent) not in compose and str(journal) not in compose
        # The image creates neither the journal target nor the unit's two fixed targets: all three are mount points
        # the runtime adds under --read-only.
        assert re.search(r'^WORKDIR /app$',dockerfile,re.M) and not any(str(value) in dockerfile for value in (journal,*FIXED_TARGETS[:2]))
    else:
        # Same leaf below the data mount on both sides: host /mnt/day-d-data/<leaf> is /app/day-d-data/<leaf>.
        assert journal.parent==DATA_TARGET and host_journal.name==journal.name and host_journal.parent==DATA_VOLUME
    # r2d2-worker is NOT the journal reader (it runs app.r2d2_worker); it only shows how the backend image mounts the
    # data volume and that neither compose nor the image selects a user. The reader's launcher must match both.
    assert re.search(r'^    command: \["python", "-m", "app\.r2d2_worker"\]$',worker.group(1),re.M)
    assert 'r2d2_v2_shadow_worker' not in compose
    assert not re.search(r'^    user:',worker.group(1),re.M)
    assert not re.search(r'^\s*USER\b',dockerfile,re.M)
    assert state_root!=journal and journal not in state_root.parents and state_root not in journal.parents
    for target in (str(state_root),'/etc/c3po-bar'):
        assert not within(Path(mounts[target]),DATA_VOLUME) and not overlaps(Path(mounts[target]),host_journal)
    monkeypatch.setenv('C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR',str(journal))
    assert Settings().r2d2_v2_massive_journal_dir==journal


def test_placement_refusals_follow_the_readme_grammar():
    readme=(UNIT_ROOT/'README.md').read_text();a_host,a_container=PLACEMENTS['A'];b_host,b_container=PLACEMENTS['B']
    path=re.compile(r'^/[A-Za-z0-9._/-]+$')
    assert all(path.match(value) and not value.endswith('/') and not {'','.','..'}&set(value.split('/')[1:])
        for pair in PLACEMENTS.values() for value in pair)
    cases={('A',a_host,a_container):None,('B',b_host,b_container):None,
        # A pair of one placement presented as the other.
        ('A',b_host,a_container):'A_HOST_JOURNAL_INSIDE_DATA_VOLUME',('A',str(DATA_VOLUME),a_container):'A_HOST_JOURNAL_INSIDE_DATA_VOLUME',
        ('A',a_host,b_container):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',('A',a_host,'/app'):'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY',
        # Placement A: one new top-level directory. Deeper paths, and system trees the overlap rule does not reach.
        ('A',a_host,'/app/journal'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',('A',a_host,'/usr/journal'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',
        ('A',a_host,'/srv/c3po-bar-journal'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',('A',a_host,a_container+'/nested'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',
        ('A',a_host,'/run/c3po/journal'):'A_CONTAINER_JOURNAL_NOT_TOP_LEVEL',
        **{('A',a_host,'/'+name):'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY' for name in ('usr','lib','lib64','bin','sbin','proc','sys','dev','run',
            'boot','home','media','mnt','opt','root','srv')},
        ('A',a_host,'/c3po-bar-journal-2'):None,
        ('A',str(DEPLOY_TREE/'runtime'/'journal'),a_container):'A_HOST_JOURNAL_INSIDE_DEPLOY_TREE',
        ('B',a_host,b_container):'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME',
        ('B',str(DATA_VOLUME/'nested'/'leaf'),str(DATA_TARGET/'leaf')):'B_HOST_JOURNAL_NOT_A_LEAF_OF_DATA_VOLUME',
        ('B',b_host,str(DATA_TARGET/'another-leaf')):'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF',('B',b_host,a_container):'B_CONTAINER_JOURNAL_NOT_THE_SAME_LEAF',
        # Every placement: the journal root against the state root, the configuration directory and the unit's targets.
        ('A',str(HOST_STATE_ROOT),a_container):'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',('A',str(HOST_STATE_ROOT.parent),a_container):'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',
        ('A',str(HOST_STATE_ROOT/'journal'),a_container):'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',('B',str(HOST_CONFIG_DIR/'journal'),b_container):'HOST_JOURNAL_OVERLAPS_PRIVATE_ROOT',
        ('A',a_host,'/var/lib/c3po-bar'):'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET',('A',a_host,'/etc/c3po-bar/journal'):'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET',
        ('A',a_host,'/tmp/journal'):'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET',('B',b_host,'/var'):'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'}
    assert {case:placement_refusal(*case) for case in cases}==cases
    assert placement_refusal('A',a_host,a_container,state=DATA_VOLUME/'state')==placement_refusal('B',b_host,b_container,
        config=DATA_VOLUME/'etc')=='PRIVATE_ROOT_INSIDE_DATA_VOLUME'
    assert placement_refusal('C',a_host,a_container)=='PLACEMENT_UNKNOWN'
    # Placement A's container path: every provided top-level directory is refused (three of them already by the
    # overlap with the unit's own targets), nothing below "/" but one component passes, and the example does.
    caught_earlier={'etc','tmp','var'}
    assert {name:placement_refusal('A',a_host,'/'+name) for name in sorted(PROVIDED_TOP_LEVEL)}=={name:'CONTAINER_JOURNAL_OVERLAPS_FIXED_TARGET'
        if name in caught_earlier else 'A_CONTAINER_JOURNAL_PROVIDED_DIRECTORY' for name in sorted(PROVIDED_TOP_LEVEL)}
    assert all(placement_refusal('A',a_host,'/'+name+'/journal') is not None for name in sorted(PROVIDED_TOP_LEVEL))
    assert Path(a_container).parts==('/',a_container[1:]) and a_container[1:] not in PROVIDED_TOP_LEVEL and placement_refusal('A',a_host,a_container) is None
    listed=re.findall(r'The installer refuses at least these top-level directories: ((?:`/[a-z0-9]+`(?:, )?)+)\. The list is a floor; the rule is the sentence before it\.',readme)
    assert len(listed)==1 and listed[0].split(', ')==['`/'+name+'`' for name in sorted(PROVIDED_TOP_LEVEL)]
    assert PROVIDED_TOP_LEVEL>={'app','bin','boot','dev','etc','home','lib','lib64','media','mnt','opt','proc','root','run','sbin','srv','sys','tmp','usr','var'}
    # The sibling layout of placement A is not an overlap: journal and state root share only their private parent.
    assert Path(a_host).parent==HOST_STATE_ROOT.parent and not overlaps(Path(a_host),HOST_STATE_ROOT)
    # The prose those refusals read.
    assert all(value in readme for value in (
        '**the placement and the pair (`@HOST_JOURNAL_ROOT@`, `@CONTAINER_JOURNAL_ROOT@`) are signed in the authorisation**',
        '- **in every placement**, a host journal root that is a filesystem root (a mount point); a host journal root that equals, '
        'contains or is contained in the state root or the configuration directory; a container journal root that equals, contains '
        'or is contained in one of the unit\'s two fixed targets, `/var/lib/c3po-bar/supervisor` and `/etc/c3po-bar`, or its tmpfs '
        '`/tmp`; and a state root or a configuration directory inside the data volume;',
        '- **under placement A**, a host journal root that is the data volume or lies inside it; a host journal root inside the deploy tree',
        'and a container journal root that is not **exactly one new top-level directory**: it must be `/<name>`, a single component '
        'directly below `/` and nothing deeper, and `<name>` must not be a directory, or any other entry, that the image or the runtime '
        'provides at `/`. The installer refuses at least these top-level directories: `/app`, `/bin`, `/boot`, `/dev`, `/etc`, `/home`, '
        '`/lib`, `/lib64`, `/media`, `/mnt`, `/opt`, `/proc`, `/root`, `/run`, `/sbin`, `/srv`, `/sys`, `/tmp`, `/usr`, `/var`. The list is '
        'a floor; the rule is the sentence before it. So `/app` and everything inside it are refused, and so are `/usr`, `/lib`, `/bin`, '
        '`/proc`, `/sys`, `/dev`, `/run` and every path below them, which the character grammar and the overlap rule of the previous item '
        'would let through;',
        '- **under placement B**, a host journal root that is not directly inside the data volume, and a `@CONTAINER_JOURNAL_ROOT@` '
        'that is not `/app/day-d-data/<leaf>` with the same `<leaf>` as `@HOST_JOURNAL_ROOT@`.',
        'So under placement A the container journal root is one new top-level directory, `/<name>`, outside `/app`, the image\'s own tree, '
        'and outside every other tree the image or the runtime provides; under placement B it is `/app/day-d-data/<leaf>`. The example of '
        'placement A, `'+a_container+'`, satisfies that rule.'))
    # The looser rule this replaces let /usr, /lib, /proc and the like through.
    assert not any(value in readme for value in ('and a container journal root that is `/app` or lies inside it;',
        'So the container journal root is an absolute path outside `/app`'))
    # The first draft's absolute coupling of the journal root to the data volume is gone.
    assert 'when the journal root is not directly inside the data volume, or when' not in readme
    # The deploy tree and how a deploy treats it, as the pipeline has them.
    pipeline=(UNIT_ROOT.parents[2]/'.github'/'workflows'/'c3po-pipeline.yml').read_text()
    assert '          APP_DIR='+str(DEPLOY_TREE)+'\n' in pipeline and '          rsync -a --delete \\\n' in pipeline
    assert '"$RELEASE_DIR/" "$APP_DIR/"' in pipeline and '`rsync -a --delete`' in readme


@pytest.fixture
def container(tmp_path,calendar,monkeypatch):
    """Container layout on temporary directories: data(0755)/journal(0700), sibling state, etc/{manifests,token}.

    That is placement B. With placement='A' the journal is outside the data directory, next to the state root below
    one private parent (private(0700)/{journal,state}), and the data directory is created only to show it stays empty."""
    from app import r2d2_v2_massive_producer as producer
    from app.r2d2_v2_massive_producer import run_session
    monkeypatch.setattr(producer,'MIN_SESSION_FREE_BYTES',1)
    previous=os.umask(0o022);day=MINUTE.date().isoformat()
    def private(path,text):
        with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as output:output.write(text)
    def layout(name,*,owner_uid=None,nested_state=False,placement='B'):
        base=tmp_path.resolve()/name;base.mkdir(mode=0o700)
        tree=SimpleNamespace(data=base/'data',journal=base/'data'/'journal',etc=base/'etc',manifests=base/'etc'/'manifests',
            token=base/'etc'/'token',state=base/'data'/'journal'/'state' if nested_state else base/'state',day=day)
        tree.data.mkdir(mode=0o755)
        if placement=='A':
            assert not nested_state
            tree.private=base/'private';tree.journal=tree.private/'journal';tree.state=tree.private/'state'
            tree.private.mkdir(mode=0o700)
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


def test_placement_a_leaves_the_data_directory_untouched_and_measures_free_space_on_the_journal_root(container,monkeypatch):
    from app import r2d2_v2_massive_producer as producer
    layout,produce=container;tree=layout('outside',placement='A')
    identity=lambda path:(os.stat(path).st_dev,os.stat(path).st_ino)
    measured=[];forced=[None];real=os.fstatvfs
    def fstatvfs(fd):
        info=os.fstat(fd);capacity=real(fd) if forced[0] is None else SimpleNamespace(f_bavail=forced[0],f_frsize=1)
        measured.append(((info.st_dev,info.st_ino),capacity.f_bavail*capacity.f_frsize))
        return capacity
    monkeypatch.setattr(os,'fstatvfs',fstatvfs)
    assert not within(tree.journal,tree.data) and not overlaps(tree.journal,tree.state) and tree.journal.parent==tree.state.parent
    code,notices,connects=produce(tree)
    assert code==0 and len(connects)==1 and notices[-1]['status']=='STOPPED'
    # Writer and reader agree on a journal that no data mount reaches, and the data directory stays empty.
    source=reader(tree.journal);result=poll(source)
    assert source.journals.ready_sessions()==(tree.day,) and result['diagnostics']==[] and result['events']
    assert list(tree.data.iterdir())==[] and sorted(path.name for path in tree.private.iterdir())==['journal','state']
    assert sorted(os.listdir(tree.journal))==['epoch.json','maintenance.lock','producer.lock','session_date='+tree.day]
    # The floor is read on the descriptor of the journal root itself (f_bavail x f_frsize), and every later
    # measurement is on a directory inside it: never on the data directory, the state root or the configuration.
    inside={identity(os.path.join(parent,name)) for parent,directories,_ in os.walk(tree.journal) for name in ['.']+directories}
    assert measured[0][0]==identity(tree.journal) and {seen for seen,_ in measured}<=inside
    assert not inside&{identity(path) for path in (tree.data,tree.state,tree.etc,tree.private)}
    started=[notice for notice in notices if notice['status']=='RETAINED_BUDGET_START']
    assert len(started)==1 and started[0]['storage']['free_bytes']==measured[0][1]
    # One byte below the real floor on that filesystem: exit 1 with no connection, the claim spent, and only the
    # producer lock in an otherwise empty journal root.
    low=layout('outside-low',placement='A');del measured[:]
    monkeypatch.setattr(producer,'MIN_SESSION_FREE_BYTES',50*1024**3);forced[0]=53687091200-1
    code,notices,connects=produce(low)
    assert code==1 and connects==[] and measured==[(identity(low.journal),53687091199)]
    gaps=[notice for notice in notices if notice['status']=='DATA_GAP']
    assert len(gaps)==1 and gaps[0]['reason']=='MASSIVE_SERVICE_LOW_DISK' and gaps[0]['provider_connected'] is False
    assert gaps[0]['storage']['free_bytes']==53687091199
    assert notices[-1]=={'status':'FAILED','session':low.day,'reason':'SUPERVISOR_PRODUCER_FAILURE','code':'MASSIVE_SERVICE_LOW_DISK'}
    assert sorted(os.listdir(low.journal))==['producer.lock'] and list(low.data.iterdir())==[]
    assert claims(low)==[low.day+'.attempt-1.json']


def test_ancestors_of_the_journal_root_are_checked_for_links_and_access_not_for_owner_or_mode(container):
    from app.r2d2_v2_massive_sessions import SessionJournalRoot
    from app.r2d2_v2_sources import _open_directory
    from app.r2d2_v2_store import ShadowIntegrityError
    layout,produce=container;root=os.geteuid()==0
    # Owner: unless the tests run as uid 0, some ancestor of every temporary tree ("/" at least) belongs to another
    # uid, and every other test of this file already passes below it.
    tree=layout('owner')
    assert root or [path for path in tree.journal.parents if os.stat(path).st_uid!=os.geteuid()]
    # Mode: a parent that group and others may write, and a parent the process itself may not write, change nothing.
    for mode in (0o777,0o555):
        tree=layout('parent-%o'%mode);tree.data.chmod(mode)
        try:
            code,notices,connects=produce(tree)
            assert code==0 and len(connects)==1 and stat.S_IMODE(os.stat(tree.data).st_mode)==mode
            assert poll(reader(tree.journal))['diagnostics']==[]
        finally:tree.data.chmod(0o755)
    # A symbolic link among the ancestors is refused by every opener, although it leads to the same sound directory.
    tree=layout('linked');alias=tree.data.parent/'alias';alias.symlink_to(tree.data);linked=alias/'journal'
    SessionJournalRoot(tree.journal,EPOCH,create=True)
    assert os.stat(linked).st_ino==os.stat(tree.journal).st_ino
    for refused in (lambda:_open_directory(linked),lambda:SessionJournalRoot(linked,EPOCH),lambda:SessionJournalRoot(linked,EPOCH,create=True)):
        with pytest.raises(OSError):refused()
    with pytest.raises(ShadowIntegrityError,match='^MASSIVE_SESSION_ROOT_UNVERIFIED$'):reader(linked)
    through=SimpleNamespace(**vars(tree));through.journal=linked
    code,notices,connects=produce(through)
    assert code==1 and connects==[] and claims(tree)==[tree.day+'.attempt-1.json']
    assert notices[-1]=={'status':'FAILED','session':tree.day,'reason':'SUPERVISOR_PRODUCER_FAILURE','code':'MASSIVE_SERVICE_FAILURE'}
    assert sorted(os.listdir(tree.journal))==['epoch.json','maintenance.lock'] and poll(reader(tree.journal))['diagnostics']==[]
    # An ancestor the process cannot read, or cannot search, fails the walk itself. uid 0 overrides permission bits
    # unless its capabilities are dropped (the unit drops them all), so this part needs a process that is not uid 0.
    if not root:
        for mode in (0o300,0o600):
            tree.data.chmod(mode)
            try:
                with pytest.raises(PermissionError):_open_directory(tree.journal)
                with pytest.raises(ShadowIntegrityError,match='^MASSIVE_SESSION_ROOT_UNVERIFIED$'):reader(tree.journal)
            finally:tree.data.chmod(0o755)
        assert poll(reader(tree.journal))['diagnostics']==[]


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


def catalog_init_script(readme):
    found=re.findall(r'^<!-- catalog-init-script:begin -->\n```python\n(.*?)```\n<!-- catalog-init-script:end -->$',readme,re.S|re.M)
    assert len(found)==1
    return found[0]


def test_readme_catalog_init_script_runs_against_the_real_catalog(container,monkeypatch,capsys):
    """Executes the exact script text of the README (operation 4b) and then the reader path."""
    from app.r2d2_v2_store import ShadowIntegrityError
    readme=(UNIT_ROOT/'README.md').read_text();script=catalog_init_script(readme)
    assert script.endswith('\n') and len(script.splitlines())<=24
    assert 'Its SHA-256 is `'+hashlib.sha256(script.encode()).hexdigest()+'`' in readme
    assert hashlib.sha256(script.encode()).hexdigest()==CATALOG_INIT_SHA256 and readme.count(CATALOG_INIT_SHA256)==1
    layout,produce=container;epoch='R2D2-V2-SHADOW-CATALOG-INIT';program=compile(script,'catalog-init.py','exec')
    def run(root,*arguments):
        with monkeypatch.context() as patch:
            # `python -I -B - <root> <epoch>`: the program arrives on stdin and sees only its two arguments.
            patch.setattr(sys,'argv',['-',str(root),*arguments]);patch.setattr(sys,'path',list(sys.path))
            try:exec(program,{'__name__':'__main__'});code=0
            except SystemExit as refused:code=refused.code
        lines=capsys.readouterr().out.splitlines()
        assert len(lines)==1
        return code,json.loads(lines[0])
    tree=layout('init');root=os.stat(tree.journal)
    assert run(tree.journal,epoch)==(0,{'status':'CATALOG_READY','created':True,'epoch':epoch,'device':root.st_dev,
        'inode':root.st_ino,'entries':['epoch.json','maintenance.lock']})
    assert all(stat.S_IMODE(os.lstat(tree.journal/name).st_mode)==0o600 for name in os.listdir(tree.journal))
    created=tree_snapshot(tree.journal)
    # Same epoch again: idempotent, nothing rewritten.
    code,receipt=run(tree.journal,epoch)
    assert code==0 and receipt['created'] is False and receipt['epoch']==epoch and tree_snapshot(tree.journal)==created
    # Another epoch, a malformed epoch, a missing argument: refused, the bound root is untouched.
    assert run(tree.journal,'R2D2-V2-SHADOW-OTHER')==(1,{'status':'CATALOG_REFUSED','code':'MASSIVE_SESSION_MANIFEST_CHANGED'})
    assert run(tree.journal,'not an epoch')==(1,{'status':'CATALOG_REFUSED','code':'EPOCH_INVALID'})
    assert run(tree.journal)[0]==1 and tree_snapshot(tree.journal)==created
    # The reader path (no create) accepts the initialised root for that epoch only.
    source=reader(tree.journal,epoch);result=poll(source)
    assert source.journals.ready_sessions()==() and result['diagnostics']==[] and result['events']==[]
    with pytest.raises(ShadowIntegrityError,match='^MASSIVE_SESSION_ROOT_UNVERIFIED$'):reader(tree.journal,'R2D2-V2-SHADOW-OTHER')
    assert tree_snapshot(tree.journal)==created
    # A root that is not empty and has no catalog is refused before anything is created in it.
    for name in ('producer.lock','lost+found'):
        other=layout('occupied-'+name[:4])
        if name=='producer.lock':(other.journal/name).touch(mode=0o600)
        else:(other.journal/name).mkdir(mode=0o700)
        before=tree_snapshot(other.journal)
        assert run(other.journal,epoch)==(1,{'status':'CATALOG_REFUSED','code':'CATALOG_INIT_ROOT_NOT_EMPTY'})
        assert tree_snapshot(other.journal)==before
    fresh=layout('malformed')
    assert run(fresh.journal,'not an epoch')[0]==1 and list(fresh.journal.iterdir())==[]
    # The documented run: the unit's image and journal mount only, no network, the script on stdin, and the same
    # empty docker CLI configuration directory as the unit, set as a prefix of that one command.
    command=re.search(r'^DOCKER_CONFIG=\S+ docker run --rm -i .*?< catalog-init\.py$',readme,re.S|re.M)
    assert command is not None and len(re.findall(r'^(?:\S+ )?docker run --rm -i ',readme,re.M))==1
    # The journal mount is a parameter of the command. It is rendered here with each placement's pair, the top-level
    # container path of placement A included, and must be the unit's own journal mount for the same pair.
    assert command.group(0).count('<HOST_JOURNAL_ROOT>')==1 and command.group(0).count('<CONTAINER_JOURNAL_ROOT>')==2
    assert not any(value in command.group(0) for value in ('/app','day-d-data','/var/lib','/mnt'))
    for placement,(host,target) in sorted(PLACEMENTS.items()):
        argv=shlex.split(command.group(0).replace('\\\n',' ').replace('<HOST_JOURNAL_ROOT>',host).replace('<CONTAINER_JOURNAL_ROOT>',target)
            .replace('<IMAGE_ID>','IMAGE').replace('< catalog-init.py',''))
        assert 'Environment='+argv[0].replace('<HOST_CONFIG_DIR>','@HOST_CONFIG_DIR@') in unit_text().splitlines()
        assert argv[1:]==['docker','run','--rm','-i','--pull','never','--init','--user','0:0','--network','none','--read-only',
            '--cap-drop','ALL','--security-opt','no-new-privileges','--mount','type=bind,source='+host+',target='+target,
            'IMAGE','python','-I','-B','-',target,'$epoch']
        options,tail=run_options(exec_start(rendered_unit(host,target)[0]),'sha256:'+'a'*64)
        assert [value for name,value in options if name=='--mount'][0]==argv[argv.index('--mount')+1]
        assert tail[tail.index('--journal-root')+1]==argv[-2]==target
    assert ('under placement A `/var/lib/c3po-bar/journal` and `/c3po-bar-journal`, so the mount reads '
        '`type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal` and the script\'s first argument is `/c3po-bar-journal`') in readme
    # The script names no journal path: it takes the root from its first argument and adds only the image's /app.
    assert 'day-d-data' not in script and 'c3po-bar' not in script and "sys.path.insert(0, '/app')" in script and 'root, epoch = sys.argv[1:]' in script


def test_readme_names_the_operations_in_order_and_the_substitution_grammar(monkeypatch):
    readme=(UNIT_ROOT/'README.md').read_text()
    headings=[line for line in readme.splitlines() if re.match(r'### (\d[a-z]?\. |Owner token delivery)',line)]
    assert headings==['### 1. Preflight (read-only)','### 2. Provisioning (directories and configuration)',
        '### Owner token delivery (between operations 2 and 4)',
        '### 3. Exclusive unit installation (no activation, no overwrite)','### 4. Readback / conference',
        '### 4b. Catalog initialisation (own authorisation, before the first prepare-capacity-day)','### 5. Activation']
    order=[readme.index(value) for value in ('### Catalog initialisation\n','### Daily order\n','1. **The catalog exists**',
        '2. **`prepare-capacity-day`**','3. **That day\'s manifest**','4. **09:29 New York time: the producer run.**','5. **The reader**')]
    assert order==sorted(order)
    assert all(value in readme for value in ('with Massive bars enabled — it must be','RELEASE_EBAR_SOURCE_REQUIRED',
        'after the producer has marked that day\'s session ready','decision of the activation rite','waiting_admission_coverage',
        'size within 1–4096','IFS= read -rs token_line','set -o noclobber','mv -T /etc/c3po-bar/token.new /etc/c3po-bar/token',
        '56706990080','**Late manifest.**','**Accepted risk for this epoch.**'))
    # The recipe writes only a non-empty value and reports only a file it has just written.
    assert ('\nIFS= read -rs token_line\n[ -n "$token_line" ] && printf \'%s\\n\' "$token_line" > /etc/c3po-bar/token'
        ' && stat -c \'%u %g %a %h\' /etc/c3po-bar/token\nunset token_line\nexit\n') in readme
    # 4b keeps its name and its heading, and the recommended place is right after operation 2.
    assert all(value in readme for value in ('Recommended sequence: 1 preflight → 2 provisioning (with the retention tag) → '
        '**4b catalog initialisation** → owner token delivery → 3 exclusive unit installation → 4 readback → 5 activation.',
        '**new directory under a new authorisation**','**Exactly one polling reader runs against a journal root.**',
        '**Exactly one polling reader may run against a journal root.**','**Exception: a stop during a lock wait.**',
        '`SOURCE_DIRECTORY_NOT_PRIVATE`','**The switch happens between session days**','**Known wart: a wrong number of arguments.**',
        'written in the 4b authorisation','strictly below `MIN_SESSION_FREE_BYTES`'))
    assert not any(value in readme for value in ('with Massive bars disabled**','no separate catalog initialisation step',
        'that rite\'s decision; it is not settled here','the next attempt comes 30 seconds later','At or below the floor',
        'the reader is not polling while the producer starts','a directory refusal',
        'bounds the two precondition commands and the launch of the docker CLI together',
        '4 readback → 4b catalog initialisation → 5 activation','under a second in these runs',
        'under one second for a full 4096-event page','No test of that file can hang'))
    # A replacement directory always moves the bind source; it moves the reader's journal directory too whenever the
    # container path changes (always under placement B). The name written here is the one the settings read, and it
    # takes a path outside /app as readily as a leaf of the data mount.
    from app.config import Settings
    variable='C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR'
    for value in (PLACEMENTS['A'][1],'/app/day-d-data/another-leaf'):
        monkeypatch.setenv(variable,value)
        assert Settings().r2d2_v2_massive_journal_dir==Path(value)
    assert readme.count("the reader's `"+variable+"`, which must equal the new `@CONTAINER_JOURNAL_ROOT@`")==2
    assert all(value in readme for value in ('A replacement directory always changes `@HOST_JOURNAL_ROOT@`, and with it the bind source of '
        'every consumer outside this directory','under placement A the signed container path may stay as it is',
        'whenever the container path changes (always under placement B, where it carries the leaf)'))
    assert '`'+variable+'` equal to `@CONTAINER_JOURNAL_ROOT@`, **explicitly**' in readme
    # Creating that leaf and running 4b on it are two authorisations.
    assert all(value in readme for value in ('a new directory and **two** further authorisations, not one',
        'has its own authorisation again (two in all, see the sequence above)'))
    assert all(value in readme for value in ('`^/[A-Za-z0-9._/-]+$`','`^sha256:[0-9a-f]{64}$`','`^[A-Za-z0-9][A-Za-z0-9_.-]*$`',
        '`host`, `none` and `container:*` are **forbidden in production**','**must fail if any `@` survives**',
        'one GO each','python -m app.r2d2_v2_shadow_worker','**No compose service launches that module.**',
        'MASSIVE_SESSION_ROOT_UNVERIFIED','MASSIVE_MAINTENANCE_BUSY','c3po/backend:massive-supervisor-'))
    assert all(name in readme for name in PLACEHOLDERS)


def cited(module,first,last=None):
    """Lines first..last (1-based, inclusive) of an app module, as the README cites them."""
    lines=(UNIT_ROOT.parents[1]/'backend'/'app'/(module+'.py')).read_text().splitlines()
    return '\n'.join(lines[first-1:last or first])


def test_readme_describes_both_journal_placements_and_what_is_checked_above_the_root():
    from app.r2d2_v2_epoch_assembler import EPOCH as signed_epoch
    readme=(UNIT_ROOT/'README.md').read_text();(a_host,a_container),(b_host,b_container)=PLACEMENTS['A'],PLACEMENTS['B']
    assert ('```\nplacement A: outside the data volume, expected on the host\'s root filesystem\n'
        'host      '+a_host+'                  (next to /var/lib/c3po-bar/supervisor)\n'
        'container '+a_container+'                          (producer --journal-root; reader journal directory)\n\n'
        'placement B: directly inside the data volume\n'
        'host      <C3PO_DAY_D_DATA_MOUNT_SOURCE>/<leaf>      (for example '+b_host+')\n'
        'container /app/day-d-data/<leaf>                     (producer --journal-root; reader journal directory)\n```\n') in readme
    # The epoch named in the document is the one the code assembles; placement A is the owner's decision for it.
    assert signed_epoch=='R2D2-V2-SHADOW-2026-10-05'
    assert ('**Epoch `'+signed_epoch+'` uses placement A, by decision of the owner.** The decision is on record as `'+DECISION_RECORD
        +'`, SHA-256 `'+DECISION_SHA256+'` (name and hash as relayed for this revision; the record\'s bytes prevail).') in readme
    assert readme.count(DECISION_RECORD)==readme.count(DECISION_SHA256)==1 and DECISION_SHA256!=RECEIPT_STDOUT_SHA256
    assert all(value in readme for value in ('ORDEM_EPOCA_03, revision 2','and that **nothing is deleted or moved**',
        'on a filesystem **chosen in the authorisation**','The placement and the pair (host path, container path) are signed in the authorisation',
        '| `@HOST_JOURNAL_ROOT@` | 2 | Host path of the dedicated journal root, in the placement signed in the authorisation. | `'+a_host+'` |',
        '| `@CONTAINER_JOURNAL_ROOT@` | 2 | The same directory as seen inside every container that is given it. | `'+a_container+'` |',
        'The two journal examples are those of placement A. Under placement B they would be `'+b_host+'` and `'+b_container+'`.',
        # What placement A implies.
        '**Placement A: outside the data volume.**','- **No compose service sees the journal.**',
        '- **Every consumer bind-mounts it explicitly, at the same container path.**','- **The container path is outside `/app`**',
        '- **The free-space floor is measured on the root filesystem**','Under placement A **the data volume is not touched at all**',
        '  | placement A: `'+a_host+'` = `@HOST_JOURNAL_ROOT@` | `root:root` | 0700 | empty; created new below `/var/lib/c3po-bar`, expected on the root filesystem (read back below) |',
        '  | placement B: `<data volume>/<leaf>` = `@HOST_JOURNAL_ROOT@` | `root:root` | 0700 | empty; created new inside the data mount |',
        '| placement A: `'+a_host+'` | as above |','| placement B: `<data volume>/<leaf>` | as above |',
        '  - **placement A:** by an **explicit bind** of the journal root, `type=bind,source=@HOST_JOURNAL_ROOT@,target=@CONTAINER_JOURNAL_ROOT@`',
        'Mounting the data volume at `/app/day-d-data` does **not** provide the journal',
        '  - **placement B:** mounting the data volume at `/app/day-d-data` is enough, because the journal root is a leaf of it;',
        '**every other container that builds the V2 collector**','**has not been run on any engine**',
        # What placement B implies, and what the code does and does not check above the journal root.
        '**Placement B: directly inside the data volume.**','- **The data volume root\'s owner and mode are recorded, not changed.**',
        'it is **not** root-owned','**The owner and the mode bits of an ancestor are not examined.**',
        'does **not** make the producer or the reader refuse a `root:root` 0700 journal root below it',
        'each ancestor must grant it read and search through its ordinary bits',
        '**Not exercised anywhere:** uid 0 without capabilities below an ancestor owned by uid 1000'))
    # The bind every consumer uses is the unit's own journal mount.
    assert '--mount type=bind,source=@HOST_JOURNAL_ROOT@,target=@CONTAINER_JOURNAL_ROOT@ ' in unit_text()
    # The first draft's absolutes: the journal root is no longer said to be in the data volume, nor reachable through
    # the compose services' data mount, without naming the placement.
    assert not any(value in readme for value in ('The journal root lives inside the existing data volume',
        'Host path of the dedicated journal root, inside the data volume.','which is the data volume. Below it',
        'mounting the data volume at `/app/day-d-data` satisfies this','only the new journal leaf',
        'All objects are `root:root`.','its ancestors are checked only for symbolic links.'))
    # Each citation of the ancestor walk and of the owner checks names lines that hold what the text says.
    walk=cited('r2d2_v2_sources',161,173);private=cited('r2d2_v2_sources',155,158)
    assert walk.startswith('def _open_directory(root: Path) -> int:') and walk.count('_private_directory(fd)')==1
    assert 'for part in root.parts[1:]:\n            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)' in walk
    # The privacy check comes after the loop, on the last descriptor only; nothing in the walk reads an owner.
    assert walk.index('_private_directory(fd)')>walk.index('fd = new') and 'st_uid' not in walk and 'st_uid' not in private
    assert private.startswith('def _private_directory(fd: int) -> None:') and 'SOURCE_DIRECTORY_NOT_PRIVATE' in private
    for module,first,last,text in (('r2d2_v2_massive_maintenance',21,23,'MASSIVE_MAINTENANCE_ROOT'),
            ('r2d2_v2_massive_producer',124,126,'MASSIVE_PRODUCER_ROOT_UNSAFE'),('r2d2_v2_massive_sessions',195,196,'MASSIVE_SESSION_ROOT_OWNER')):
        assert text in cited(module,first,last) and 'st_uid' in cited(module,first,last) and 'os.fstat(directory)' in cited(module,first,last)
        assert '`'+module+'.py` lines %d–%d'%(first,last) in readme
    assert 'any(p.is_symlink() for p in (root, *root.parents))' in cited('r2d2_v2_massive_journal',53)
    spool=cited('r2d2_v2_massive_spool',62,72)
    assert 'os.mkdir(part, mode=0o700, dir_fd=fd)' in spool and 'except FileExistsError:' in spool and 'os.O_NOFOLLOW, dir_fd=fd)' in spool
    worker=cited('r2d2_v2_shadow_worker',55,70)
    assert worker.startswith('def _with_massive_source(settings, source, release):')
    assert 'SessionJournalRoot(settings.r2d2_v2_massive_journal_dir, release.epoch)' in worker
    assert all(value in readme for value in ('(`_open_directory`, `r2d2_v2_sources.py` lines 161–173)','`_private_directory` (lines 155–158',
        '(`MassiveJournal.open_reader`, `r2d2_v2_massive_journal.py` line 53)','(`MassiveSpool._open_root`, `r2d2_v2_massive_spool.py` lines 62–72)',
        '(`_with_massive_source`, `r2d2_v2_shadow_worker.py` lines 55–70)'))


def test_readme_reads_the_free_space_gate_on_the_journal_filesystem_and_attributes_host_facts_to_the_receipt():
    from app import r2d2_v2_massive_producer as producer
    readme=(UNIT_ROOT/'README.md').read_text()
    floor=producer.MIN_SESSION_FREE_BYTES;session=producer.MAX_SESSION_EVIDENCE_BYTES+producer.MAX_SESSION_INDEX_BYTES;five=floor+5*session
    data=RECEIPT_DATA_VOLUME_AVAILABLE;root=RECEIPT_ROOT_FILESYSTEM_AVAILABLE
    assert (floor,session,five)==(53687091200,603979776,56706990080)
    # The gate is read on the journal root, with the producer's own arithmetic.
    assert ('4. Free space **on the journal root\'s filesystem**, read on the journal root itself (`df -B1 --output=avail <HOST_JOURNAL_ROOT>`), '
        'is at least **%d bytes (the 50 GiB floor) plus %d bytes (576 MiB) for each session that will be retained before space is next '
        'freed, plus the expected growth of every other writer on that filesystem over the same period**. For five sessions and no other '
        'growth that is %d bytes.'%(floor,session,five)) in readme
    assert cited('r2d2_v2_massive_producer',61,62)=="    capacity=os.fstatvfs(directory)\n    usage['free_bytes']=capacity.f_bavail*capacity.f_frsize"
    assert cited('r2d2_v2_massive_producer',301)=='    with _producer_directory(root) as directory:'
    assert cited('r2d2_v2_massive_producer',304)=='            before=_storage_usage(directory,sessions=True)'
    assert "usage['free_bytes']<MIN_SESSION_FREE_BYTES" in cited('r2d2_v2_massive_producer',103)
    assert "before['free_bytes']<MIN_SESSION_FREE_BYTES" in cited('r2d2_v2_massive_producer',307)
    assert all(value in readme for value in ('`os.fstatvfs` on the descriptor of the journal directory, free bytes `f_bavail × f_frsize` '
        '(`_storage_usage`, `r2d2_v2_massive_producer.py` lines 61–62; the descriptor is the journal root opened at line 301 and measured at line 304)',
        'measured with `fstatvfs` on **the journal root\'s own filesystem**, whichever that is',
        'Under placement A they are the writers of the root filesystem','Under placement B they are the writers of the data volume.',
        'the producer stops when the **root filesystem** falls below 50 GiB','(`r2d2_v2_massive_producer.py` lines 103 and 307)',
        '9. The placement: the journal root is at the signed host path, on the filesystem the authorisation names, and is not a mount point'))
    assert not any(value in readme for value in ('--output=avail <data volume>','every other writer on the data volume over the same period',
        'The data volume had about 50.4 GiB free on 2026-10-01'))
    # The figures of both filesystems, each derived here from the receipt's two readings and the code's constants.
    assert 0<data-floor<session and data<five<root
    assert all(value in readme for value in (
        '     | Filesystem | Bytes available | Against the floor (%d) | Against five sessions (%d) |'%(floor,five),
        '     | data volume (placement B) | %d | %d above: less than one session (%d) | **%d short** |'%(data,data-floor,session,five-data),
        '     | root filesystem `/` (placement A, only if the journal root\'s mount point is `/`) | %d | %d above | %d above |'%(root,root-floor,root-five),
        'the data volume is %d bytes above the producer\'s floor, less than one session\'s own budget, while the root filesystem has %d '
        'bytes available'%(data-floor,root),'%d bytes available, %d above the floor, less than one session\'s own budget'%(data,data-floor),
        'with **%d bytes available**;'%data,'- the host\'s root filesystem: **%d bytes available**;'%root))
    assert (data-floor,five-data,root-floor,root-five)==(383451136,2636447744,541525225472,538505326592)
    # The second figure is the receipt's reading of "/". That placement A's journal root is on that filesystem is the
    # expectation, not a receipt fact: the document says so where the placement is introduced and where the figure is used.
    assert all(value in readme for value in (
        'bytes available (see "Activation gate"). **That figure is the receipt\'s reading of `/`, not of the journal root**, which did not exist '
        'yet: that `/var/lib` is on the root filesystem is the expectation, not a receipt fact, and the figure applies to placement A only if '
        'the readback shows that the mount point of the journal root is `/` (operation 1 reads which filesystem it would be on; operations 2 '
        'and 4 read its mount point back once it exists).',
        '**That `/var/lib` is on the host\'s root filesystem is the expectation, not a receipt fact**: the receipt of 2026-10-02 measured the '
        'bytes available on `/` and the absence of `/var/lib/c3po-bar`, and did not read which filesystem `/var/lib` belongs to. Operation 1 '
        'reads which filesystem the journal root would be on; operations 2 and 4 read back its mount point once it exists. Wherever this document says "the root filesystem" for placement A, or uses the '
        'receipt\'s figure for it, that holds only if the readback shows that mount point to be `/`.',
        'The second row is the receipt\'s reading of `/`: the receipt did not read which filesystem `/var/lib` belongs to, so that row applies '
        'to placement A only if the readback shows that the mount point of the journal root is `/`.',
        '(for placement A the filesystem that holds `/var/lib`, expected to be the root filesystem; for placement B the data volume',
        '- **The free-space floor is measured on the root filesystem**, if that is where the readback finds the journal root',
        'Under placement A that is expected to be the host\'s root filesystem (the readback decides); under placement B, the data volume.',
        '| as above | Expected on the root filesystem (operations 2 and 4 read its mount point back), created by operation 2'))
    # Stated as settled, these were not receipt facts.
    assert not any(value in readme for value in ('The host path is a new directory on the host\'s root filesystem',
        'placement A: outside the data volume, on the host\'s root filesystem','| root filesystem (placement A) |',
        'created new below `/var/lib/c3po-bar`, on the root filesystem |','| as above | On the root filesystem, created',
        'Under placement A that is the host\'s root filesystem;','(the root filesystem for placement A;'))
    # Attribution: one receipt, named once with its hash, and no host fact stated without it.
    block=re.search(r'^\*\*The receipt of 2026-10-02\.\*\* .*?^The receipt did \*\*not\*\* observe [^\n]*$',readme,re.S|re.M)
    assert block is not None and readme.count(RECEIPT_STDOUT_SHA256)==block.group(0).count(RECEIPT_STDOUT_SHA256)==1
    assert ('is on record as operation `'+RECEIPT_OPERATION+'`, receipt stdout SHA-256 `'+RECEIPT_STDOUT_SHA256+'`') in block.group(0)
    assert all(value in block.group(0) for value in ('A second read-only reading, on 2026-10-02 UTC',
        '**the author of this document measured nothing on the host**',
        '- Docker server 29.5.3, with the containerd snapshotter; no user-namespace remapping; not rootless;',
        '- the `docker-init` executable at `/usr/libexec/docker/docker-init`;','- systemd 255;',
        '- the data volume: the bind source of `/app/day-d-data`, a filesystem of its own, whose root directory is owned by uid 1000, gid 1000, mode 0755',
        '- nothing of the supervisor provisioned, as on 2026-10-01.',
        'The receipt did **not** observe the unit under systemd, a container start with `--init`, or any item of the rehearsal.'))
    assert all(value in block.group(0) for value in ('Nor did it read **which filesystem `/var/lib` belongs to**: it measured the bytes available '
        'on `/` and found no `/var/lib/c3po-bar`.','is therefore an expectation, not a fact of the receipt'))
    facts=('29.5.3','/usr/libexec/docker/docker-init','systemd 255',str(data),str(root),'containerd snapshotter')
    outside=readme.replace(block.group(0),'')
    stated=[line for line in outside.splitlines() if any(fact in line for fact in facts) and not line.startswith('     | ')]
    assert len(stated)>=7 and all('he receipt of 2026-10-02' in line for line in stated)
    assert 'from the receipt of 2026-10-02 (operation `'+RECEIPT_OPERATION+'`), not measured by this document\'s author on the host:' in outside
    # What the receipt did not observe keeps its wording, and the readback is not replaced by it.
    assert all(value in readme for value in ('None of it has been observed on the production host.',
        'A container start with `--init` on the host was not observed.','That the daemon starts a container with it was **not observed**',
        'They do not replace the readback: operation 4 reads each of them again.',
        'The gate is met by the readback of operation 4, on the journal root that operation 2 created, not by this table.'))
    assert 'Which path the daemon resolves was not established' not in readme
    # The smoke's journal target is still the shape of placement B, and the document says so instead of claiming more.
    pipeline=(UNIT_ROOT.parents[2]/'.github'/'workflows'/'c3po-pipeline.yml').read_text()
    assert '"@CONTAINER_JOURNAL_ROOT@": "'+PLACEMENTS['B'][1]+'",' in pipeline and PLACEMENTS['A'][1] not in pipeline
    assert all(value in readme for value in ('The smoke renders `@CONTAINER_JOURNAL_ROOT@` as `'+PLACEMENTS['B'][1]+'`, the shape of placement B',
        'Not proven anywhere yet: a journal mount target directly below `/` under `--read-only` (placement A\'s container path)',
        '**The pipeline smoke still renders a container journal root of placement B\'s shape**'))


def test_readme_states_what_placement_a_changes_and_never_requires_the_data_volume():
    readme=(UNIT_ROOT/'README.md').read_text()
    # The first draft's statements that held for the data volume only, in the words it used.
    assert not any(value in readme for value in ('The journal root must be inside the data volume.','must be inside the data volume',
        '`RequiresMountsFor` is inert if systemd has no mount unit for the data volume','A change of the data disk\'s device number',
        'from the other root containers that mount the whole data volume read-write (api, r2d2-worker, shadow-candidate)'))
    # What takes their place: each of the three bullets says what holds under placement A and what under placement B.
    assert all(value in readme for value in (
        'Under placement B those containers include the compose services that mount the whole data volume read-write (`api`, `r2d2-worker`, '
        '`r2d2-shadow-candidate-worker`). Under placement A no compose service mounts the journal root, so the containers that can reach it are '
        'the ones given the explicit bind; host root and anyone with Docker access still can. The token and the claims stay outside the data '
        'volume in both placements for the same reason.',
        '- `RequiresMountsFor` names the journal root, the state root and the configuration directory. Under placement A all three are expected '
        'to be on the root filesystem, which is always mounted; if the readback confirms it, the line adds no real condition *(documented systemd '
        'behaviour, not observed)*. In either case the unit does not depend on the data volume at all under placement A. Under placement B it is '
        'inert if systemd has no mount unit for the data volume.',
        '- A change of the device number of the journal root\'s filesystem across a reboot makes both sides refuse the root, because the catalog '
        'binds device and inode; there is no in-code recovery. Under placement A that filesystem is expected to be the host\'s root filesystem, '
        'under placement B it is the data disk. Whether either number is stable across reboots of this host was not observed.'))
    # "Never a mount point" is about the host path: in a container the journal root is always a bind-mount target.
    assert ('**On the host** it is never a filesystem root (a mount point); that is a statement about the host path only, because in every '
        'container the journal root is the target of a bind mount and so a mount point there. It neither contains nor is contained in the '
        'state root or the configuration directory.') in readme
    assert 'Never a filesystem root on the host; nothing else may be placed inside it.' in readme
    assert not any(value in readme for value in ('It is never a filesystem root (a mount point), and','Never a filesystem root; nothing else'))
    # /app is the image's tree; /app/day-d-data is a mount target below it, not something the image holds.
    assert ('- **The container path is outside `/app`**: one new top-level directory, for example `'+PLACEMENTS['A'][1]+'`, under the rule of '
        '"Substitution grammar" (a single component below `/` that is not a directory the image or the runtime provides). `/app` is the '
        'image\'s own tree, and `/app/day-d-data` below it is where the compose services, and a reader that also needs the data volume, mount '
        'that volume.') in readme
    assert 'holds `/app/day-d-data`' not in readme
    dockerfile=(UNIT_ROOT.parents[1]/'backend'/'Dockerfile').read_text()
    assert re.search(r'^WORKDIR /app$',dockerfile,re.M) and 'day-d-data' not in dockerfile


def test_pipeline_exercises_rendered_unit_on_a_real_engine():
    pipeline=(UNIT_ROOT.parents[2]/'.github'/'workflows'/'c3po-pipeline.yml').read_text()
    start=pipeline.index('      - name: Exercise the Massive supervisor unit against the backend image\n')
    step=pipeline[start:pipeline.index('\n      - name: ',start+1)]
    assert pipeline.index("--tag c3po/backend:pr-validation")<start
    assert all('"'+name+'"' in step for name in PLACEHOLDERS) and '"@NETWORK@": "none"' in step
    assert all(value in step for value in ('c3po/deployment/massive-supervisor/c3po-massive.service',
        "docker image inspect --format '{{.Id}}' c3po/backend:pr-validation",'^sha256:[0-9a-f]{64}$',
        'line.startswith("ExecStartPre=/")','["/usr/bin/docker", "image", "inspect", "--format", "{{.Id}}", image]',
        'sudo env "DOCKER_CONFIG=$base/etc/docker-cli" "${check[@]}"','[ "$seen" = "$id" ] ||','"--init" not in argv',
        "docker info --format '{{.InitBinary}}'",
        'sudo install -d -m 0700 -o 0 -g 0','sudo env "DOCKER_CONFIG=$base/etc/docker-cli" "${argv[@]}"',
        '[ "$rc" -eq 78 ] ||','"status": "DATA_GAP"','sudo find "$base/state" "$base/data/journal" -mindepth 1',
        "docker ps -a --filter 'name=^c3po-massive$' -q"))
    assert 'continue-on-error' not in step and 'MASSIVE_API_KEY' not in step and 'secrets.' not in step
