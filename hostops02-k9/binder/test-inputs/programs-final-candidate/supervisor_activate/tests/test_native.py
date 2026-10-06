"""The real system calls of K5, made by the source's own unmodified Native on a private temporary tree that stands in
for '/', with real processes behind the systemctl and docker binaries. Nothing of Native is overridden but the path of
those binaries (moved into the temporary tree); the substitution of '/' and of the uid is made on the os module (the
core's tests/oslevel.py), and every system call is recorded with the arguments it received.

What stands for systemctl is a program at <tree>/usr/bin/systemctl that keeps the unit states in a JSON file beside the
tree and answers show, daemon-reload, enable --now of the timer and reset-failed of the service the way the emulation
of k5.py does; enable creates the real link timers.target.wants/c3po-massive.timer in the tree and starts the service,
which shows its refusal at the next show. No systemd, no docker, no host. On the workstation this proves the real
runner with two tools, the real read of the unit files, the lstat of the token and of the link, and the counts of held
directories, in both modes, as an ordinary user reported as root."""
import json
import os
from pathlib import Path
import stat
import sys
import time

import pytest

import family as f
import k5
import oslevel

BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
IMAGE='sha256:'+'fb'*32
rows=oslevel.rows
FAKE_SYSTEMCTL='''#!%(python)s -B
import json,os,sys
TREE=%(tree)r;STATE=TREE+'.systemd.json';SERVICE='c3po-massive.service';TIMER='c3po-massive.timer'
arguments=sys.argv[1:]
with open(STATE) as handle:state=json.load(handle)
state['calls'].append(arguments)
def save():
    with open(STATE,'w') as handle:json.dump(state,handle)
if arguments==['daemon-reload']:state['reloads']+=1
elif arguments==['enable','--now',TIMER]:
    os.symlink('/etc/systemd/system/'+TIMER,TREE+'/etc/systemd/system/timers.target.wants/'+TIMER)
    state['timer'].update(UnitFileState='enabled',ActiveState='active',SubState='waiting',NextElapseUSecRealtime='Tue 2026-10-06 09:29:00 EDT',LastTriggerUSec='Mon 2026-10-05 18:00:01 -03')
    state['service'].update(ActiveState='activating',SubState='start',InvocationID='%%032x'%%0xabc1);state['polls']=0
elif arguments==['reset-failed',SERVICE]:
    if state['service']['ActiveState']=='failed':state['service'].update(ActiveState='inactive',SubState='dead',Result='success')
elif arguments[:1]==['show'] and len(arguments)>=4 and arguments[2::2]==['-p']*((len(arguments)-2)//2):
    unit=arguments[1];values=state['service'] if unit==SERVICE else state['timer'] if unit==TIMER else state['docker']
    if unit==SERVICE and values['ActiveState']=='activating':
        state['polls']+=1
        if state['polls']>=state['settle_after_polls']:values.update(ActiveState='failed',SubState='failed',Result='exit-code',ExecMainCode='1',ExecMainStatus='78')
    sys.stdout.write(''.join('%%s=%%s\\n'%%(key,values[key]) for key in arguments[3::2]))
else:
    save();raise SystemExit(64)
save()
'''
FAKE_DOCKER='''#!%(python)s -B
import json,sys
IMAGE=%(image)r;REVISION=%(revision)r
arguments=sys.argv[1:]
with open(%(log)r,'a') as log:log.write(json.dumps(arguments)+'\\n')
if arguments[:3]==['image','inspect','--format'] and len(arguments)==5:
    if arguments[4] not in (IMAGE,'c3po/backend:massive-supervisor-epoch03'):raise SystemExit(1)
    print(json.dumps({'id':IMAGE,'repo_tags':['c3po/backend:massive-supervisor-epoch03','c3po/backend:production'],'revision':REVISION}))
elif arguments[:4]==['ps','-a','--no-trunc','--format'] and len(arguments)==5:pass
else:raise SystemExit(64)
'''

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('etc/systemd/system/timers.target.wants','var/lib','proc/sys/kernel/random','usr/bin'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    for path in ('etc/c3po-bar','etc/c3po-bar/manifests','etc/c3po-bar/docker-cli','var/lib/c3po-bar','var/lib/c3po-bar/supervisor','var/lib/c3po-bar/journal'):
        (root/path).mkdir();os.chmod(root/path,0o700)
    for name in ('epoch.json','maintenance.lock'):
        (root/'var/lib/c3po-bar/journal'/name).write_bytes(b'{}' if name=='epoch.json' else b'');os.chmod(root/'var/lib/c3po-bar/journal'/name,0o600)
    token=root/'etc/c3po-bar/token';token.write_bytes(k5.TOKEN_CANARY);os.chmod(token,0o600)
    for name,content in ((k5.SERVICE,k5.SERVICE_BYTES),(k5.TIMER,k5.TIMER_BYTES)):
        (root/'etc/systemd/system'/name).write_bytes(content);os.chmod(root/'etc/systemd/system'/name,0o644)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    return root

def install(tree,settle_after_polls=1,activated=False):
    for name,text in (('systemctl',FAKE_SYSTEMCTL%{'python':sys.executable,'tree':str(tree)}),
                      ('docker',FAKE_DOCKER%{'python':sys.executable,'image':IMAGE,'revision':k5.hostemu.REVISION,'log':str(tree)+'.docker.log'})):
        path=tree/'usr/bin'/name;path.write_text(text);os.chmod(path,0o755)
    model=k5.Systemd.__new__(k5.Systemd);k5.Systemd.__init__(model,type('H',(),{'paused':0})())
    if activated:
        os.symlink('/etc/systemd/system/'+k5.TIMER,tree/'etc/systemd/system/timers.target.wants'/k5.TIMER)
        model.timer.update(UnitFileState='enabled',ActiveState='active',SubState='waiting',NextElapseUSecRealtime='Tue 2026-10-06 09:29:00 EDT')
        model.service.update(ActiveState='failed',SubState='failed',Result='exit-code',ExecMainCode='1',ExecMainStatus='78',InvocationID='%032x'%0xabc1)
    state={'calls':[],'reloads':0,'polls':0,'settle_after_polls':settle_after_polls,'service':model.service,'timer':model.timer,
           'docker':{'Id':'docker.service','LoadState':'loaded','ActiveState':'active','SubState':'running','UnitFileState':'enabled'}}
    Path(str(tree)+'.systemd.json').write_text(json.dumps(state))

def unit(tree,name):
    info=os.lstat(tree/'etc/systemd/system'/name);raw=(tree/'etc/systemd/system'/name).read_bytes()
    return {'name':name,'sha256':f.sha(raw),'bytes':len(raw),'device':info.st_dev,'inode':info.st_ino}
def fields(tree,mode='ACTIVATE'):
    return {'mode':mode,'unit_directory':rows(tree,k5.UNITS),'units':{'service':unit(tree,k5.SERVICE),'timer':unit(tree,k5.TIMER)},
            'supervisor_paths':{key:rows(tree,path) for key,path in k5.PATHS.items()},'expected_entries':{'JOURNAL':2,'STATE':0,'DOCKER_CLI':0},
            'image_id':IMAGE,'retention_reference':k5.RETENTION,'invocation_id':None if mode=='ACTIVATE' else '%032x'%0xabc1,
            'evidence_boot_id_sha256':f.sha(BOOT.strip())}

def run(tree,plan=None,now=None):
    k=k5.K();m=k.m
    class Moved(m.Native):
        def run(self,argv,*arguments):return m.Native.run(self,[str(tree)+argv[0]]+list(argv[1:]),*arguments)
    now=now or k5.NOW;docs=f.Docs(k,plan or fields(tree),now=now)
    with oslevel.Substitute(tree) as record:receipt=docs.run(Moved(),clock=lambda:now,monotonic=time.monotonic)
    state=json.loads(Path(str(tree)+'.systemd.json').read_text())
    return receipt,record.calls,state

def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_ino,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out
WRITING=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL

def test_native_activate_with_real_processes_behind_systemctl_and_docker(tree):
    install(tree);before=snapshot(tree);receipt,calls,state=run(tree)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','TIMER_ENABLED_ACTIVE_RESET_PENDING',None),receipt
    assert [call for call in state['calls'] if call[0]!='show']==[['enable','--now',k5.TIMER]]
    assert receipt['observed']['readback']['service']['ExecMainStatus']=='78' and receipt['observed']['readback']['enablement_link']=={'exists':True,'type':'symlink'}
    null=[entry for entry in calls if entry['call']=='open' and entry['path']=='ABSOLUTE:'+os.devnull]
    opens=[entry for entry in calls if entry['call']=='open' and entry not in null]
    assert opens and all(entry['flags']&os.O_NOFOLLOW and not entry['flags']&WRITING for entry in opens)
    assert not [entry for entry in calls if entry['call'] in ('mkdir','link','unlink','fsync','umask','flock')]
    assert not [entry for entry in opens if entry['path'].endswith('/token')],'the token is never opened'
    assert [entry for entry in calls if entry['call']=='stat' and entry['path']=='/etc/c3po-bar/token' and entry['follow_symlinks'] is False]
    assert sorted(entry['path'] for entry in opens if entry['path'].startswith('/etc/systemd/system/c3po-massive'))==['/etc/systemd/system/'+k5.SERVICE]*2+['/etc/systemd/system/'+k5.TIMER]*2
    after=snapshot(tree);assert sorted(set(after)-set(before))==['etc/systemd/system/timers.target.wants/'+k5.TIMER]
    assert os.readlink(tree/'etc/systemd/system/timers.target.wants'/k5.TIMER)=='/etc/systemd/system/'+k5.TIMER
    assert {name:value for name,value in after.items() if name in before}==before
    assert k5.TOKEN_CANARY.strip() not in f.line(receipt)

def test_native_reset_with_real_processes(tree):
    install(tree,activated=True);before=snapshot(tree);receipt,calls,state=run(tree,fields(tree,'RESET'),k5.RESET_NOW)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','SERVICE_REFUSAL_78_SEEN_RESET_FAILED_VERIFIED',None),receipt
    assert [call for call in state['calls'] if call[0]!='show']==[['reset-failed',k5.SERVICE]] and state['service']['ActiveState']=='inactive'
    assert snapshot(tree)==before and not [entry for entry in calls if entry['call'] in ('mkdir','link','unlink','fsync','umask','flock')]

def test_native_refusals_give_no_verb_and_change_nothing(tree):
    install(tree);plan=fields(tree)
    (tree/'var/lib/c3po-bar/supervisor/2026-10-05.claim-1').write_bytes(b'');before=snapshot(tree);receipt,calls,state=run(tree,plan)
    assert (receipt['status'],receipt['code'])==('REFUSED','SUPERVISOR_ENTRIES_NOT_AS_SIGNED') and [c for c in state['calls'] if c[0]!='show']==[] and snapshot(tree)==before
    (tree/'var/lib/c3po-bar/supervisor/2026-10-05.claim-1').unlink();os.chmod(tree/'etc/c3po-bar/token',0o640)
    receipt,calls,state=run(tree,plan);assert (receipt['status'],receipt['code'])==('REFUSED','TOKEN_METADATA')
    os.chmod(tree/'etc/c3po-bar/token',0o600);os.symlink('/nowhere',tree/'etc/systemd/system/timers.target.wants'/k5.TIMER)
    receipt,calls,state=run(tree,plan);assert (receipt['status'],receipt['code'])==('REFUSED','ENABLEMENT_LINK_PRESENT')
    os.unlink(tree/'etc/systemd/system/timers.target.wants'/k5.TIMER);os.chmod(tree/'usr/bin/systemctl',0o775)
    receipt,calls,state=run(tree,plan);assert (receipt['status'],receipt['code'])==('REFUSED','BINARY_UNAVAILABLE_OR_UNSAFE') and state['calls']==[]
    os.chmod(tree/'usr/bin/systemctl',0o755);receipt,calls,state=run(tree,plan)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW','with every cause removed the same plan completes'
