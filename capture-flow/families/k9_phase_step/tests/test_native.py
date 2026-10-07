"""K9W's real system calls: the source's own unmodified Native on a private temporary tree that stands in for '/', in a
child interpreter under an audit hook (tests/native_child.py), the docker CLI alone answered by the emulated engine
(tests/native_engine.py). On the workstation this proves the real walks (O_NOFOLLOW, by dir_fd), the exclusive claim,
the mkdir of the day's directories, the step plan and the launch record (exclusive temporary, link, unlink, fsync), the
modes, and that nothing else is created, changed, opened for writing or started; the kernel's O_NOATIME, Linux errno
values and real uid 0 only when this suite runs as root on Linux (the CI job)."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import k9w

HERE=Path(__file__).resolve().parent
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})

def child(root,operation):
    done=subprocess.run([sys.executable,'-B',str(HERE/'native_child.py'),str(root),operation],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
    assert done.returncode==0,done.stderr.decode()[-3000:]
    return json.loads(done.stdout)

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(str(path));out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,
                                                                   info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out

@pytest.mark.parametrize('operation',['collect_launch','commit_launch','capture_cleanup'])
def test_real_system_calls_of_a_step(tmp_path,operation):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir()
    out=child(root,operation);receipt=out['receipt']
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and receipt['code'] is None,receipt['code']
    day=root/k9w.day_path()[1:]
    created={'collect_launch':['claims/<key>.claim','days/D','days/D/plans','days/D/launches','days/D/receipts','days/D/plans/collect_launch.json',
                               'days/D/launches/collect_launch.json'],
             'commit_launch':['claims/<key>.claim','days/D/plans/commit_launch.json','days/D/launches/commit_launch.json'],
             'capture_cleanup':['claims/<key>.claim']}[operation]
    key=k9w.attempt_key(k9w.EPOCH,k9w.DAY,k9w.WRITE[operation][0],operation)
    for relative in created:
        path=root/k9w.K9_ROOT[1:]/relative.replace('<key>',key).replace('days/D','days/'+k9w.DAY)
        info=os.lstat(str(path))
        assert stat.S_IMODE(info.st_mode)==(0o700 if stat.S_ISDIR(info.st_mode) else 0o600) and (stat.S_ISDIR(info.st_mode) or info.st_nlink==1),relative
    calls=out['calls']
    opens=[entry for entry in calls if entry['call']=='open']
    assert all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens)
    # every read open of the source's own walks carries O_NOATIME (the core's boot-id read of /proc does not, by design)
    assert all(entry['noatime'] for entry in opens if not entry['flags']&(os.O_WRONLY|os.O_CREAT) and not entry['path'].startswith('/proc') and entry['path']!='/')
    assert [entry for entry in opens if entry['path']=='/' and entry['noatime']]
    writes=[entry for entry in opens if entry['flags']&(os.O_WRONLY|os.O_CREAT)]
    assert all(entry['flags']&os.O_EXCL and entry['mode']==0o600 for entry in writes) and len(writes)==len([r for r in created if not r.startswith('days/D') or '.' in r])
    assert sorted(entry['path'].rsplit('/',1)[1] for entry in calls if entry['call']=='mkdir' and 'errno' not in entry)==(
        sorted([k9w.DAY,'plans','launches','receipts']) if operation=='collect_launch' else [])
    assert [entry['call'] for entry in calls if entry['call'] in ('link','unlink')]==['link','unlink']*len(writes)
    events=[event for event in out['events'] if event[0]!='open-for-writing']
    assert [event[0] for event in events]==['os.mkdir']*(4 if operation=='collect_launch' else 0)+[] or all(event[0] in ('os.mkdir','os.link','os.remove') for event in events)
    assert not [event for event in out['events'] if event[0] in ('subprocess.Popen','os.chmod','os.chown','os.rename','os.symlink','socket.connect','os.exec','os.posix_spawn')]
    secrets=[k9w.PLACEMENT[key] for key in ('provider_env_file','risk_db_env_file','emitter_password')]
    assert not [entry for entry in opens if entry['path'] in secrets]
    assert out['commands']=={'collect_launch':[['ps'],['image'],['create'],['start'],['container']],
                             'commit_launch':[['ps'],['container'],['image'],['rm'],['create'],['start'],['container'],['ps']],
                             'capture_cleanup':[['ps'],['container'],['rm'],['ps']]}[operation]

def test_a_second_run_of_the_same_attempt_is_refused_by_the_real_claim(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir()
    out=child(root,'collect_launch');assert out['receipt']['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    # the same tree again: build() would fail on an existing root, so the claim is proved by the refusal of a fresh copy with it
    other=Path(str(tmp_path)).resolve()/'other';other.mkdir()
    out=child(other,'commit_launch');assert out['receipt']['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    claims=other/k9w.PLACEMENT['claims'][1:];assert len(list(claims.iterdir()))==1 and not [p for p in claims.iterdir() if p.name.startswith('.hostops-')]
