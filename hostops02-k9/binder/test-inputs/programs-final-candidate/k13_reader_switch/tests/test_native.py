"""K13 with the real system calls, made by the source's own Native on a private temporary tree that stands in for '/'
(tests/native_support.py: the substitution of the core's tests/oslevel.py, the data volume on its own device, and
the docker CLI and systemctl answered by the emulated engine). On the workstation this proves the real lstat/open/read
of every guarded file by dir_fd without following a link, the real exclusive temporary, link, unlink and fsync of
activation.env, a real race at its final name and a real process death at each step, with macOS errno values as an
ordinary user reported as root; the kernel's O_NOATIME, Linux errno values and real uid 0 only when this suite runs
as root on Linux (the Linux-root CI job: NOT RUN by the author)."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import k13
import native_child
import native_support

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
READ_ONLY_OPEN=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
ACTIVATION=k13.CONFIG+'/activation.env'

@pytest.fixture
def tree(tmp_path):return native_support.build_tree(tmp_path)

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,info.st_mtime_ns,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out

def child(root,plan,tmp_path,point=None):
    path=Path(str(tmp_path))/'fields.json';path.write_bytes(json.dumps(plan).encode())
    command=[sys.executable,'-B',str(Path(native_child.__file__)),str(root),str(path)]+([point] if point else [])
    return subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=dict(ENV,HOME=os.environ.get('HOME','')),timeout=120)

def run(root,mode='ACTIVATE',change=None,setup=None,plan=None):
    k=k13.K();plan=native_support.fields(root,mode) if plan is None else plan
    if change is not None:change(plan)
    host,emulated=native_support.engine(k,root,setup=setup if setup is not None else (k13.activated if mode=='DEACTIVATE' else None))
    old=os.umask(0o027)
    try:
        with native_support.Volume(root) as record:receipt=f.Docs(k,plan,now=k13.at(mode)).run(host)
    finally:os.umask(old)
    receipt['_calls']=record.calls;receipt['_switches']=emulated.switches;return receipt

def read_primitives(calls):
    opens=[entry for entry in calls if entry['call']=='open' and not entry['flags']&os.O_CREAT]
    assert opens and all(entry['flags']&os.O_NOFOLLOW for entry in opens),'every open is O_NOFOLLOW'
    assert all(not entry['flags']&READ_ONLY_OPEN for entry in opens),'a read open carries no write, create or truncate flag'
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    directories=[entry for entry in opens if entry['flags']&os.O_DIRECTORY and not entry['path'].startswith('/proc') and entry['path']!='/']
    assert directories and all(entry['noatime'] for entry in directories),'every directory of a walk is opened O_NOATIME'
    stats=[entry for entry in calls if entry['call']=='stat']
    assert stats and all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats),'every stat is an lstat relative to a held descriptor'
    assert not [entry for entry in opens if entry['path'] in (k13.CONFIG+'/secret.env',k13.JOURNAL+'/maintenance.lock')],'secret.env and the lock are never opened'
    return opens

def test_native_activate_creates_only_activation_env_with_exactly_these_system_calls(tree,tmp_path):
    before=snapshot(tree);done=child(tree,native_support.fields(tree),tmp_path)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    result=json.loads(done.stdout);receipt,events,calls=result['receipt'],result['events'],result['calls']
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','RETURNED_REQUIRES_LIVENESS_READBACK',None),receipt['code']
    target=tree/ACTIVATION.lstrip('/');info=os.lstat(target)
    assert target.read_bytes()==k13.ACTIVATION and (stat.S_IMODE(info.st_mode),info.st_nlink,stat.S_ISREG(info.st_mode))==(0o600,1,True)
    assert receipt['ledger'][0]['inode']==info.st_ino and result['switches']==[['enable','--now','c3po-reader.timer'],['start','--no-block','c3po-reader.service']]
    read_primitives(calls)
    secret=[entry for entry in calls if entry.get('path')==k13.CONFIG+'/secret.env'];assert [entry['call'] for entry in secret]==['stat']
    temporary=k13.CONFIG+'/.hostops-%s-0.partial'%result['go16']
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    assert [(entry['call'],entry['path']) for entry in changing]==[('open',temporary),('link',ACTIVATION),('unlink',temporary)]
    wanted=os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    assert changing[0]['flags']&wanted==wanted and changing[0]['mode']==0o600 and not changing[0]['flags']&(os.O_TRUNC|os.O_APPEND)
    assert changing[1]['follow_symlinks'] is False and changing[1]['same_directory'] and all(entry['by_dir_fd'] for entry in changing)
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077]
    assert [event[0] for event in events if event[0] not in ('open',)]==['open-for-writing','os.link','os.remove']
    after=snapshot(tree);assert sorted(set(after)-set(before))==[ACTIVATION.lstrip('/')]
    assert {name:value for name,value in after.items() if name!=ACTIVATION.lstrip('/') and name!='etc/c3po-reader'}=={
        name:value for name,value in before.items() if name!='etc/c3po-reader'},'nothing else changed'

def test_native_reconcile_changes_nothing_on_disk(tree):
    (tree/ACTIVATION.lstrip('/')).write_bytes(k13.ACTIVATION);os.chmod(tree/ACTIVATION.lstrip('/'),0o600)
    before=snapshot(tree);receipt=run(tree)
    assert receipt['code'] is None and receipt['reconcile'] is True and snapshot(tree)==before
    assert not [entry for entry in receipt['_calls'] if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    read_primitives(receipt['_calls'])

def test_native_restart_and_deactivate_change_nothing_on_disk(tree):
    (tree/ACTIVATION.lstrip('/')).write_bytes(k13.ACTIVATION);os.chmod(tree/ACTIVATION.lstrip('/'),0o600);before=snapshot(tree)
    receipt=run(tree,'RESTART',setup=k13.failed);assert receipt['code'] is None and receipt['outcome']=='RESTART_RETURNED_REQUIRES_LIVENESS_READBACK'
    receipt=run(tree,'DEACTIVATE');assert receipt['code'] is None and receipt['outcome']=='DEACTIVATED_REQUIRES_STOP_READBACK'
    assert not [entry for entry in receipt['_calls'] if entry['call']=='open' and entry['path'].startswith(k13.CONFIG)]
    assert snapshot(tree)==before

@pytest.mark.parametrize('label,action,code',[
    ('secret_mode',lambda root:os.chmod(root/'etc/c3po-reader/secret.env',0o640),'SECRET_ENV_SHAPE'),
    ('secret_link',lambda root:(os.unlink(root/'etc/c3po-reader/secret.env'),os.symlink('/etc/passwd',root/'etc/c3po-reader/secret.env')),'SECRET_ENV_SHAPE'),
    ('activation_link',lambda root:os.symlink('pins.env',root/'etc/c3po-reader/activation.env'),'ACTIVATION_ENV_NOT_THE_CONSTANT'),
    ('activation_other',lambda root:(root/'etc/c3po-reader/activation.env').write_bytes(b'C3PO_R2D2_V2_SHADOW_ENABLED=true\n'),'ACTIVATION_ENV_NOT_THE_CONSTANT'),
    ('unit_link',lambda root:(os.rename(root/'etc/systemd/system/c3po-reader.timer',root/'etc/systemd/system/x.timer'),
                              os.symlink('x.timer',root/'etc/systemd/system/c3po-reader.timer')),'UNIT_FILE_NOT_AS_SIGNED'),
    ('epoch_link',lambda root:(os.rename(root/'var/lib/c3po-bar/journal/epoch.json',root/'var/lib/c3po-bar/journal/e'),
                               os.symlink('e',root/'var/lib/c3po-bar/journal/epoch.json')),'CATALOG_FILE_NOT_PRIVATE'),
    ('launcher_fifo',lambda root:(os.unlink(root/'etc/c3po-reader/launcher/reader_launcher.py'),os.mkfifo(root/'etc/c3po-reader/launcher/reader_launcher.py',0o600)),
     'LAUNCHER_NOT_AS_SIGNED'),
    ('journal_replaced',lambda root:(os.rename(root/'var/lib/c3po-bar/journal',root/'var/lib/c3po-bar/old'),os.mkdir(root/'var/lib/c3po-bar/journal',0o700)),
     'PARENT_IDENTITY_MISMATCH'),
])
def test_native_refusals_after_the_plan_was_read_change_nothing(tree,label,action,code):
    plan=native_support.fields(tree);action(tree);before=snapshot(tree)
    receipt=run(tree,plan=plan)
    assert (receipt['status'],receipt['code'])==('REFUSED',code) and snapshot(tree)==before and receipt['_switches']==[]

def test_native_race_at_the_final_name_leaves_the_other_file_and_switches_nothing(tree):
    k=k13.K();plan=native_support.fields(tree);host,emulated=native_support.engine(k,tree)
    native=type(host)
    class Racing(native):
        def link(self,source,target,dir_fd):
            descriptor=os.open(str(tree/ACTIVATION.lstrip('/')),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)        # the builtin os, outside the source
            os.write(descriptor,b'X=1\n');os.close(descriptor)
            return native.link(self,source,target,dir_fd)
    old=os.umask(0o027)
    try:
        with native_support.Volume(tree):receipt=f.Docs(k,plan,now=k13.at('ACTIVATE')).run(Racing())
    finally:os.umask(old)
    assert receipt['code']=='DESTINATION_APPEARED_AFTER_PRECHECK' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert (tree/ACTIVATION.lstrip('/')).read_bytes()==b'X=1\n' and emulated.switches==[]
    assert sorted(path.name for path in (tree/'etc/c3po-reader').iterdir())==['activation.env','docker-cli','launcher','pins.env','secret.env']

@pytest.mark.parametrize('point,left',[('in_write','TEMPORARY'),('after_write','TEMPORARY'),('after_link','BOTH'),('after_unlink','FINAL'),('after_enable','FINAL')])
def test_native_death_leaves_what_a_later_read_finds(tree,tmp_path,point,left):
    done=child(tree,native_support.fields(tree),tmp_path,point)
    assert done.returncode==137 and done.stdout==b'',done.stderr.decode()[-2000:]
    names=sorted(path.name for path in (tree/'etc/c3po-reader').iterdir() if path.name not in ('docker-cli','launcher','pins.env','secret.env'))
    temporary=[name for name in names if name.startswith('.hostops-') and name.endswith('-0.partial')]
    final=(tree/ACTIVATION.lstrip('/'))
    if left=='TEMPORARY':assert names==temporary and len(temporary)==1 and k13.ACTIVATION.startswith((tree/'etc/c3po-reader'/temporary[0]).read_bytes())
    if left=='BOTH':assert len(temporary)==1 and final.read_bytes()==k13.ACTIVATION and os.lstat(final).st_nlink==2
    if left=='FINAL':assert names==['activation.env'] and final.read_bytes()==k13.ACTIVATION and os.lstat(final).st_nlink==1
    # a constant file left by a death is exactly what the reconcile of the same payload accepts
    if left=='FINAL':
        receipt=run(tree);assert receipt['code'] is None and receipt['reconcile'] is True
