"""The real system calls of K2a, made by the source's own unmodified Native on a private temporary tree that stands in
for '/', with a real process behind the docker binary. Nothing of Native is overridden but the path of that binary
(moved into the temporary tree): the substitution of '/' and of the uid is made on the os module (the core's
tests/oslevel.py), and every system call is recorded with the arguments it received.

What stands for docker is a program at <tree>/usr/bin/docker. For `run` it executes the bytes it gets on standard input
with `python -B -` on the REAL directory the bind names: in mode "release" those bytes are the pinned script and the
application modules are those of the release (k2a.release_tree; skipped without one), so the catalog on disk is the
application's own and the operation's readback is checked against it, not against a model. No docker, no container, no
host. On the workstation this proves the real mkdir, fsync, scandir of a held descriptor after another process added
entries, O_NOFOLLOW, and lstat of a symbolic link, as an ordinary user reported as root with a marker bit for
O_NOATIME; the kernel's O_NOATIME, Linux errno values and real uid 0 only when the suite runs as root on Linux."""
import json
import os
from pathlib import Path
import stat
import sys

import pytest

import family as f
import k2a
import oslevel

BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
IMAGE='sha256:'+'fb'*32
rows=oslevel.rows
FAKE_DOCKER='''#!%(python)s -B
import hashlib,json,os,subprocess,sys
TREE=%(tree)r;IMAGE=%(image)r;REVISION=%(revision)r;BACKEND=%(backend)r;AFTER=%(after)r
arguments=sys.argv[1:];data=sys.stdin.buffer.read()
with open(TREE+'.docker.log','a') as log:
    log.write(json.dumps({'argv':arguments,'stdin_sha256':hashlib.sha256(data).hexdigest() if data else None,'cwd':os.getcwd(),
                          'environment':{key:value for key,value in os.environ.items() if not key.startswith('__CF')}},sort_keys=True)+'\\n')
if arguments[:3]==['image','inspect','--format'] and len(arguments)==5:
    if arguments[4]!=IMAGE:raise SystemExit(1)
    print(json.dumps({'id':IMAGE,'repo_tags':['c3po/backend:production'],'revision':REVISION}))
elif arguments[:4]==['ps','-a','--no-trunc','--format'] and len(arguments)==5:pass
elif arguments[:1]==['run']:
    fields=dict(item.split('=',1) for item in [word for word in arguments if word.startswith('type=bind,')][0].split(','))
    command=arguments[arguments.index(IMAGE)+1:];root=TREE+fields['source']
    assert command[:4]==['python','-I','-B','-'] and command[4]==fields['target'] and len(command)==6
    done=subprocess.run([sys.executable,'-B','-',root,command[5]],input=data,stdout=subprocess.PIPE,cwd=BACKEND)
    if AFTER=='SYMLINK':
        os.rename(root+'/epoch.json',TREE+'.moved-epoch.json');os.symlink(TREE+'.moved-epoch.json',root+'/epoch.json')
    elif AFTER=='MODE':os.chmod(root+'/epoch.json',0o644)
    elif AFTER=='EXTRA':os.close(os.open(root+'/producer.lock',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600))
    sys.stdout.buffer.write(done.stdout);sys.stdout.flush();raise SystemExit(done.returncode)
else:raise SystemExit(64)
'''
# What the fake engine runs when no tree of the release is at hand: the effect of the script, said in a few lines
# (the same statements as k2a.catalog_model). It arrives on standard input in place of the pinned bytes.
MODEL=b'''import json,os,sys
root,epoch=sys.argv[1:];before=sorted(os.listdir(root));info=os.stat(root)
os.close(os.open(os.path.join(root,'maintenance.lock'),os.O_RDWR|os.O_CREAT,0o600))
raw=json.dumps({'schema':'MASSIVE_SESSION_ROOT_V1','epoch':epoch,'device':info.st_dev,'inode':info.st_ino},sort_keys=True,separators=(',',':')).encode()
fd=os.open(os.path.join(root,'epoch.json'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,raw);os.fsync(fd);os.close(fd)
print(json.dumps({'status':'CATALOG_READY','created':not before,'epoch':epoch,'device':info.st_dev,'inode':info.st_ino,'entries':sorted(os.listdir(root))},sort_keys=True))
'''

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('etc','var/lib','proc/sys/kernel/random','usr/bin'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    for path in ('etc/c3po-bar','etc/c3po-bar/docker-cli','var/lib/c3po-bar','var/lib/c3po-bar/journal'):
        (root/path).mkdir();os.chmod(root/path,0o700)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    return root

def engine(tree,script,after=None):
    """Installs the fake docker; returns the bytes that must travel on standard input for it to act ('release': the
    pinned script itself, nothing is replaced)."""
    backend=''
    if script=='release':
        release=k2a.release_tree()
        if release is None:pytest.skip('no tree of the release at hand (HOSTOPS02_TEST_RELEASE_TREE)')
        backend=str(release/'c3po'/'backend')
    path=tree/'usr/bin/docker'
    path.write_text(FAKE_DOCKER%{'python':sys.executable,'tree':str(tree),'image':IMAGE,'revision':k2a.RELEASE,'backend':backend or str(tree),'after':after})
    os.chmod(path,0o755)
def fields(tree,mode):
    common={'container_journal_root':k2a.TARGET,'docker_config_chain':rows(tree,k2a.CONFIG),'image_id':IMAGE,'image_revision':k2a.RELEASE,
            'script_sha256':k2a.SCRIPT_SHA,'evidence_boot_id_sha256':f.sha(BOOT.strip())}
    if mode=='REAL':return dict(common,mode='REAL',journal_chain=rows(tree,k2a.JOURNAL),throwaway_name=None,reference_chain=None,epoch=k2a.EPOCH)
    return dict(common,mode='REHEARSAL',journal_chain=rows(tree,k2a.PARENT),throwaway_name=k2a.THROWAWAY,reference_chain=rows(tree,k2a.JOURNAL),epoch=k2a.DIAG)
def run(tree,mode,script,monkeypatch,plan=None):
    """One run in this process with the module's own Native; only the path of the docker binary is moved into the tree."""
    k=k2a.K();m=k.m
    if script=='model':monkeypatch.setattr(m,'script_bytes',lambda:MODEL)          # the fake engine has no application to import
    class Moved(m.Native):
        def run(self,argv,*arguments):return m.Native.run(self,[str(tree)+argv[0]]+list(argv[1:]),*arguments)
    docs=f.Docs(k,plan or fields(tree,mode));old=os.umask(0o027)
    try:
        with oslevel.Substitute(tree) as record:receipt=docs.run(Moved())
    finally:os.umask(old)
    monkeypatch.undo()
    log=Path(str(tree)+'.docker.log');calls=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return receipt,record.calls,calls
def snapshot(root):
    out={}
    for path in sorted([root]+list(root.rglob('*'))):
        info=os.lstat(path);out[str(path.relative_to(root))]=(stat.S_IFMT(info.st_mode),stat.S_IMODE(info.st_mode),info.st_nlink,info.st_ino,
                                                              info.st_size if stat.S_ISREG(info.st_mode) else None)
    return out
WRITING=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
def assert_read_primitives(calls):
    # subprocess opens /dev/null itself for the standard error (and the standard input) of a command; every other open is the source's own
    null=[entry for entry in calls if entry['call']=='open' and entry['path']=='ABSOLUTE:'+os.devnull]
    opens=[entry for entry in calls if entry['call']=='open' and entry not in null]
    assert opens and all(entry['flags']&os.O_NOFOLLOW and not entry['flags']&WRITING for entry in opens),'every open is O_NOFOLLOW and carries no write or create flag'
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    directories=[entry for entry in opens if entry['flags']&os.O_DIRECTORY and not entry['path'].startswith('/proc') and entry['path']!='/']
    assert directories and all(entry['noatime'] for entry in directories),'every directory of a walk is opened O_NOATIME'
    stats=[entry for entry in calls if entry['call']=='stat']
    assert stats and all(entry['follow_symlinks'] is False and entry['by_dir_fd'] for entry in stats),'every stat is an lstat relative to a held descriptor'
    assert all(entry['path']!='?' for entry in calls if entry['call'] in ('fstat','fsync')) and all(entry['by_fd'] for entry in calls if entry['call']=='scandir')
    assert not [entry for entry in calls if entry['call'] in ('link','unlink','readlink','flock')]

@pytest.mark.parametrize('script',['release','model'])
@pytest.mark.parametrize('mode',['REAL','REHEARSAL'])
def test_native_run_with_a_real_process_behind_docker_verifies_the_catalog_the_script_wrote(tree,monkeypatch,mode,script):
    engine(tree,script);before=snapshot(tree);receipt,calls,docker=run(tree,mode,script,monkeypatch)
    path=k2a.root_of(mode);root=tree/path.lstrip('/');epoch=k2a.EPOCH if mode=='REAL' else k2a.DIAG;info=os.stat(root)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','CATALOG_READY_VERIFIED' if mode=='REAL' else 'REHEARSAL_CATALOG_READY_VERIFIED',None),receipt
    # on the real disk: the two files, as the application (or its stand-in) wrote them
    assert sorted(os.listdir(root))==k2a.NAMES and (root/'epoch.json').read_bytes()==k2a.expected_epoch_json(epoch,info.st_dev,info.st_ino) and (root/'maintenance.lock').read_bytes()==b''
    assert [stat.S_IMODE(os.lstat(root/name).st_mode) for name in k2a.NAMES]==[0o600,0o600] and stat.S_IMODE(info.st_mode)==0o700
    assert receipt['journal_root']=={'path':path,'device':info.st_dev,'inode':info.st_ino,'created_by_this_run':mode=='REHEARSAL'}
    assert (receipt['script_line']['device'],receipt['script_line']['inode'],receipt['script_line']['status'])==(info.st_dev,info.st_ino,'CATALOG_READY')
    held=receipt['catalog'];assert (held['status'],held['entries'],held['other_entries'],held['root_unchanged'],held['epoch_json']['equal_to_the_expected_bytes'])==('COMPLETE',2,0,True,True)
    assert held['epoch_json']['sha256']==f.sha((root/'epoch.json').read_bytes()),'a listing of the held descriptor made after another process wrote sees its two files'
    # what this process itself did to the tree: nothing in REAL, two mkdirs and four fsyncs in REHEARSAL
    assert_read_primitives(calls)
    changing=[entry for entry in calls if entry['call'] in ('mkdir','link','unlink') or (entry['call']=='open' and entry['flags']&os.O_CREAT)]
    synced=[entry['path'] for entry in calls if entry['call']=='fsync']
    if mode=='REAL':assert changing==[] and synced==[]
    else:
        assert [(entry['call'],entry['path'],entry['mode'],entry['by_dir_fd']) for entry in changing]==[('mkdir',k2a.REHEARSAL_CONFIG,0o700,True),('mkdir',k2a.REHEARSAL_ROOT,0o700,True)]
        assert synced==[k2a.REHEARSAL_CONFIG,'/var/lib',k2a.REHEARSAL_ROOT,'/var/lib']
        assert sorted(os.listdir(tree/'var/lib/c3po-bar/journal'))==[],'the real journal root is only read'
        given=os.lstat(tree/k2a.REHEARSAL_CONFIG.lstrip('/'));assert stat.S_ISDIR(given.st_mode) and stat.S_IMODE(given.st_mode)==0o700 and os.listdir(tree/k2a.REHEARSAL_CONFIG.lstrip('/'))==[]
    assert [entry['mask'] for entry in calls if entry['call']=='umask']==[0o077]
    # in the journal root nothing is opened but epoch.json, read-only, without following a link; the lock file is never opened
    inside=[entry for entry in calls if entry['call']=='open' and entry['path'].startswith(path+'/')]
    assert [entry['path'] for entry in inside]==[path+'/epoch.json'] and inside[0]['flags']&(os.O_NOFOLLOW|os.O_NONBLOCK)==os.O_NOFOLLOW|os.O_NONBLOCK
    # the engine was asked exactly this, with the fixed environment and the configuration directory of the mode: the
    # unit's in REAL, the one this run created in REHEARSAL (no process of a rehearsal is given the unit's)
    environment={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','DOCKER_CONFIG':k2a.config_of(mode)}
    assert [entry['argv'][:2] for entry in docker]==[['image','inspect'],['ps','-a'],['run','--rm'],['ps','-a']] and all(entry['environment']==environment and entry['cwd']=='/' for entry in docker)
    assert docker[2]['argv']==k2a.K().m.RUN_PREFIX+['--mount','type=bind,source=%s,target=%s'%(path,k2a.TARGET),IMAGE,'python','-I','-B','-',k2a.TARGET,epoch]
    assert docker[2]['stdin_sha256']==(k2a.SCRIPT_SHA if script=='release' else f.sha(MODEL)) and docker[0]['stdin_sha256'] is None
    # nothing else of the tree changed
    after=snapshot(tree);new=sorted(set(after)-set(before))
    expected=[path.lstrip('/')+'/'+name for name in k2a.NAMES]+([path.lstrip('/'),k2a.REHEARSAL_CONFIG.lstrip('/')] if mode=='REHEARSAL' else [])
    assert new==sorted(expected) and {name:(value[0],value[1],value[3],value[4]) for name,value in after.items() if name in before and name!=path.lstrip('/')}=={name:(value[0],value[1],value[3],value[4]) for name,value in before.items() if name!=path.lstrip('/')}
    assert sorted(os.listdir(tree/'etc/c3po-bar/docker-cli'))==[]

def test_native_refusals_start_no_process_and_change_nothing(tree,monkeypatch):
    engine(tree,'model')
    def refused(receipt,code,docker,count=0):
        assert (receipt['status'],receipt['code'],receipt['root_verdict'])==('REFUSED',code,'UNTOUCHED_NO_CONTAINER_STARTED') and len(docker)==count,(receipt['code'],docker)
    journal=tree/'var/lib/c3po-bar/journal';plan=fields(tree,'REAL')
    (journal/'producer.lock').touch(mode=0o600);before=snapshot(tree);receipt,calls,docker=run(tree,'REAL','model',monkeypatch,plan)
    refused(receipt,'JOURNAL_ROOT_NOT_EMPTY',docker);assert snapshot(tree)==before
    (journal/'producer.lock').unlink();os.rename(journal,tree/'var/lib/c3po-bar/real');os.symlink('real',journal);before=snapshot(tree)
    receipt,calls,docker=run(tree,'REAL','model',monkeypatch,plan);refused(receipt,'PARENT_SYMLINK_COMPONENT',docker);assert snapshot(tree)==before
    os.unlink(journal);os.rename(tree/'var/lib/c3po-bar/real',journal);os.chmod(journal,0o750)
    receipt,calls,docker=run(tree,'REAL','model',monkeypatch,plan);refused(receipt,'PARENT_IDENTITY_MISMATCH',docker)
    os.chmod(journal,0o700);(tree/'etc/c3po-bar/docker-cli/config.json').write_bytes(b'{}')
    receipt,calls,docker=run(tree,'REAL','model',monkeypatch,plan);refused(receipt,'DOCKER_CONFIG_DIRECTORY_NOT_EMPTY',docker)
    (tree/'etc/c3po-bar/docker-cli/config.json').unlink();plan=fields(tree,'REHEARSAL');(tree/'var/lib'/k2a.THROWAWAY).mkdir(mode=0o700);before=snapshot(tree)
    receipt,calls,docker=run(tree,'REHEARSAL','model',monkeypatch,plan);refused(receipt,'DESTINATION_PRESENT',docker);assert snapshot(tree)==before
    (tree/'var/lib'/k2a.THROWAWAY).rmdir();(tree/'var/lib'/(k2a.THROWAWAY+'.docker-cli')).symlink_to('/nonexistent');before=snapshot(tree)
    receipt,calls,docker=run(tree,'REHEARSAL','model',monkeypatch,plan);refused(receipt,'DESTINATION_PRESENT',docker);assert snapshot(tree)==before
    (tree/'var/lib'/(k2a.THROWAWAY+'.docker-cli')).unlink();os.chmod(tree/'usr/bin/docker',0o775)
    receipt,calls,docker=run(tree,'REHEARSAL','model',monkeypatch,plan);refused(receipt,'BINARY_UNAVAILABLE_OR_UNSAFE',docker)
    assert not (tree/'var/lib'/k2a.THROWAWAY).exists() and not (tree/'var/lib'/(k2a.THROWAWAY+'.docker-cli')).exists(),'no directory is created for a docker that cannot be started'
    os.chmod(tree/'usr/bin/docker',0o755);receipt,calls,docker=run(tree,'REHEARSAL','model',monkeypatch,plan)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and len(docker)==4,'with every cause removed the same request plan completes'

@pytest.mark.parametrize('after,code,status',[('SYMLINK','CATALOG_READBACK_MISMATCH','COMPLETE'),('MODE','CATALOG_READBACK_MISMATCH','COMPLETE'),('EXTRA','CATALOG_READBACK_MISMATCH','COMPLETE')])
def test_native_readback_sees_a_real_symbolic_link_a_real_mode_and_a_real_third_entry(tree,monkeypatch,after,code,status):
    engine(tree,'model',after);receipt,calls,docker=run(tree,'REAL','model',monkeypatch);held=receipt['catalog']
    assert (receipt['status'],receipt['code'],receipt['root_verdict'],held['status'])==('PARTIAL_METADATA_REQUIRES_REVIEW',code,'NOT_TO_BE_USED_AGAIN',status)
    assert receipt['script_line']['status']=='CATALOG_READY' and receipt['mutating_calls']['uncertain']==1
    if after=='SYMLINK':
        assert held['files']['epoch.json']['type']=='symlink' and held['epoch_json'] is None
        assert not [entry for entry in calls if entry['call']=='open' and entry['path'].endswith('/epoch.json')],'a link is never opened, so never followed'
    if after=='MODE':assert held['files']['epoch.json']['mode_octal']=='0644' and held['epoch_json']['equal_to_the_expected_bytes'] is True
    if after=='EXTRA':assert (held['entries'],held['other_entries'])==(3,1) and b'producer.lock' not in f.line(receipt)

def test_native_noatime_is_required_and_fails_closed_where_the_platform_lacks_it(monkeypatch):
    m=k2a.K().m
    if hasattr(os,'O_NOATIME'):assert m.Native().noatime()==os.O_NOATIME
    monkeypatch.delattr(os,'O_NOATIME',raising=False)
    with pytest.raises(m.Refused,match='NOATIME_UNAVAILABLE'):m.Native().noatime()
