"""The real system calls and processes of the capacity probe, made by the source's own unmodified Native on a private
temporary tree that stands in for '/', with a real program behind the docker binary. Nothing of Native is overridden
but the path of that binary (moved into the tree): the substitution of '/' and of the uid is made on the os module
(the core's tests/oslevel.py), and every system call is recorded with the arguments it received.

What stands for docker is a program at <tree>/usr/bin/docker. It answers the image read, the listing, the worker's
inspect and its mounts as the CLI would, logs every argv, the hash of its standard input, its environment and its
working directory, and for `run` executes the bytes it got on standard input with a real `python -I -B -`, after a
test-only prelude that it writes itself: CALENDAR with the release's own modules (when a tree of the release and an
interpreter with its requirements are at hand), IDENT and LOAD with a stub application whose AnchoredRoot reads the
real device and inode numbers of the bound tree (the prelude maps /c3po-capacity to <tree>/var/lib/c3po-capacity).
So the numbers the source reads on the host by descriptor and the numbers a process reads under the bind are the same
real numbers here; that a container sees the host's numbers through a bind is NOT shown by this test (DESIGN.md, U-B1).
No docker, no container, no host, no network."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

import pytest

import family as f
import kprobe
import oslevel

BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
IMAGE='sha256:'+'fb'*32
WORKER_ID='5'*64
VENV=kprobe.app_python()
STUB_ANCHORED='''import os, stat, hashlib, json
class ShadowIntegrityError(ValueError):
    pass
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()
class AnchoredRoot:
    """Test stub: the identity of the two components below the bind, read with real stat calls on the mapped tree."""
    def __init__(self, path, expected_identity=None):
        real = MAPPED + path[len('/c3po-capacity'):]
        top, leaf = os.stat(MAPPED, follow_symlinks=False), os.stat(real, follow_symlinks=False)
        if not stat.S_ISDIR(leaf.st_mode) or leaf.st_mode & 0o077:
            raise ShadowIntegrityError('ROOT_NOT_PRIVATE')
        self.identity = digest([['c3po-capacity', top.st_dev, top.st_ino], [os.path.basename(path), leaf.st_dev, leaf.st_ino]])
    def close(self):
        pass
'''
STUB_CONFIG='''class Settings:
    def __init__(self, **values):
        self.__dict__.update(values)
'''
STUB_BOOTSTRAP='''import hashlib
from .r2d2_v2_capacity_anchored import AnchoredRoot, MAPPED, ShadowIntegrityError
class Reader:
    def __init__(self, directory):
        self.directory = directory
    def read(self, name):
        with open(self.directory + '/' + name, 'rb') as handle:
            return handle.read()
class CapacityConfig:
    def __init__(self, settings):
        path = MAPPED + settings.r2d2_v2_capacity_config_file[len('/c3po-capacity'):]
        with open(path, 'rb') as handle:
            self.sha = hashlib.sha256(handle.read()).hexdigest()
        self.name = settings.r2d2_v2_capacity_config_file.rsplit('/', 1)[1]
        self.config_root = Reader(path.rsplit('/', 1)[0])
        if self.sha != settings.r2d2_v2_capacity_config_sha:
            raise ShadowIntegrityError('CAPACITY_CONFIG_HASH')
        self.veto_mode = settings.r2d2_v2_capacity_veto_mode
        self.roots = {name: AnchoredRoot('/c3po-capacity/' + name) for name in ('documents', 'go', 'payload')}
    def close(self):
        pass
'''
FAKE_DOCKER='''#!%(python)s -B
import hashlib,json,os,subprocess,sys
TREE=%(tree)r;IMAGE=%(image)r;REVISION=%(revision)r;WORKER=%(worker)r;LISTED=%(listed)r;MOUNTS=%(mounts)r;APP=%(app)r;APP_PYTHON=%(app_python)r;RELEASE=%(release)r;ENVIRONMENT=%(environment)r
arguments=sys.argv[1:];data=sys.stdin.buffer.read()
with open(TREE+'.docker.log','a') as log:
    log.write(json.dumps({'argv':arguments,'stdin_sha256':hashlib.sha256(data).hexdigest() if data else None,'cwd':os.getcwd(),
                          'environment':{key:value for key,value in os.environ.items() if not key.startswith('__CF')}},sort_keys=True)+'\\n')
if arguments[:3]==['image','inspect','--format'] and len(arguments)==5:
    if arguments[4]!=IMAGE:raise SystemExit(1)
    print(json.dumps({'id':IMAGE,'repo_tags':['c3po/backend:production'],'revision':REVISION}))
elif arguments[:4]==['ps','-a','--no-trunc','--format'] and len(arguments)==5:
    for row in LISTED:print(json.dumps(row))
elif arguments[:3]==['container','inspect','--format'] and len(arguments)==5 and '.Config.Env' in arguments[3]:
    if arguments[4]!=WORKER:raise SystemExit(1)
    import re
    expected=dict(re.findall(r'eq [.] "([A-Z0-9_]+)=([^"]*)"',arguments[3]))
    print(json.dumps({name:{'present':name in ENVIRONMENT,'equal':ENVIRONMENT.get(name)==value} for name,value in expected.items()}))
elif arguments[:3]==['container','inspect','--format'] and len(arguments)==5 and '.Mounts' in arguments[3]:
    if arguments[4]!=WORKER:raise SystemExit(1)
    print(json.dumps({'mounts':MOUNTS}))
elif arguments[:3]==['container','inspect','--format'] and len(arguments)==5:
    if arguments[4]!='c3po-r2d2-worker-1':raise SystemExit(1)
    print(json.dumps({'name':'/c3po-r2d2-worker-1','id':WORKER,'image_id':IMAGE,'image_reference':'c3po/backend:production','running':True,
                      'state':'running','started_at':'2026-10-05T20:40:00.000000000Z','host_pid':4242,'restarts':0,'health':None}))
elif arguments[:1]==['run']:
    assert arguments[arguments.index(IMAGE)+1:]==['python','-I','-B','-']
    prelude=('import sys as _s\\n_s.path.insert(0,%%r)\\n'%%(RELEASE if data.startswith(b'import json, sys') else APP)).encode()
    if data.startswith(b'import json, sys') and not RELEASE:raise SystemExit(70)
    done=subprocess.run([APP_PYTHON if data.startswith(b'import json, sys') else sys.executable,'-I','-B','-'],input=prelude+data,stdout=subprocess.PIPE,
                        env={'PATH':'/usr/bin:/bin'})
    sys.stdout.buffer.write(done.stdout);sys.stdout.flush();raise SystemExit(done.returncode)
else:raise SystemExit(64)
'''
ANOTHER={'id':'7'*64,'name':'c3po-api-1','state':'running'}

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('proc/sys/kernel/random','usr/bin','var/lib'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(str(path),0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    capacity=root/'var/lib/c3po-capacity';capacity.mkdir(mode=0o700);os.chmod(str(capacity),0o700)
    for name in kprobe.CHILDREN:(capacity/name).mkdir(mode=0o700);os.chmod(str(capacity/name),0o700)
    config=capacity/'config'/kprobe.CONFIG_NAME;config.write_bytes(kprobe.CONFIG);os.chmod(str(config),0o600)
    return root

def application(tmp_path,tree):
    directory=Path(str(tmp_path)).resolve()/'stub'/'app';directory.mkdir(parents=True)
    (directory/'__init__.py').write_text('')
    (directory/'r2d2_v2_capacity_anchored.py').write_text('MAPPED=%r\n'%str(tree/'var/lib/c3po-capacity')+STUB_ANCHORED)
    (directory/'config.py').write_text(STUB_CONFIG);(directory/'r2d2_v2_capacity_bootstrap.py').write_text(STUB_BOOTSTRAP)
    return str(directory.parent)

def engine(tree,tmp_path,listed=(ANOTHER,),mounts=None,release=None,app_python=None,environment=None):
    path=tree/'usr/bin/docker'
    if mounts is None:mounts=[{'type':'bind','source':'/var/lib/c3po-capacity','destination':'/c3po-capacity','rw':False}]
    path.write_text(FAKE_DOCKER%{'python':sys.executable,'tree':str(tree),'image':IMAGE,'revision':kprobe.RELEASE,'worker':WORKER_ID,'listed':list(listed),
                                 'mounts':mounts,'environment':environment if environment is not None else {'C3PO_R2D2_V2_SHADOW_RELEASE_SHA':kprobe.RELEASE_SHA,
                                 'C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE':'/var/lib/c3po-capacity'},'app':application(tmp_path,tree),'app_python':app_python or sys.executable,'release':release})
    os.chmod(str(path),0o755)

def run(tree,step):
    k=kprobe.K();m=k.m
    class Moved(m.Native):
        def run(self,argv,*arguments):return m.Native.run(self,[str(tree)+argv[0]]+list(argv[1:]),*arguments)
    fields=kprobe.fields(step,image_id=IMAGE,evidence_boot_id_sha256=f.sha(BOOT.strip()))
    if step!='CALENDAR':fields['capacity']={'root_path':'/var/lib/c3po-capacity','parent_rows':oslevel.rows(tree,'/var/lib')}
    docs=f.Docs(k,fields,now=kprobe.NOW[step])
    with oslevel.Substitute(tree) as record:receipt=docs.run(Moved())
    log=Path(str(tree)+'.docker.log');calls=[json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return docs,receipt,record.calls,calls

WRITING=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND|os.O_EXCL
def assert_read_only(calls):
    null=[entry for entry in calls if entry['call']=='open' and entry['path']=='ABSOLUTE:'+os.devnull]
    opens=[entry for entry in calls if entry['call']=='open' and entry not in null]
    assert opens and all(entry['flags']&os.O_NOFOLLOW and not entry['flags']&WRITING for entry in opens),'every open is O_NOFOLLOW and carries no write or create flag'
    assert all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens),'only "/" is opened by absolute path'
    assert not [entry for entry in calls if entry['call'] in ('mkdir','link','unlink','fsync','flock','umask','readlink')],'nothing that changes the tree'
def assert_docker(docker,expected,stdin):
    assert [call['argv'][:2] for call in docker]==expected
    for call in docker:
        assert call['cwd']=='/' and call['environment']=={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'},call['environment']
        assert (call['stdin_sha256'] is None)==(call['argv'][0]!='run')
    assert [call['stdin_sha256'] for call in docker if call['argv'][0]=='run']==[f.sha(raw) for raw in stdin]

def identities(tree):
    top=os.stat(str(tree/'var/lib/c3po-capacity'))
    return {name:kprobe.digest([['c3po-capacity',top.st_dev,top.st_ino],[name,os.stat(str(tree/'var/lib/c3po-capacity'/name)).st_dev,
                                                                          os.stat(str(tree/'var/lib/c3po-capacity'/name)).st_ino]]) for name in kprobe.CHILDREN}

def test_native_ident_reads_the_real_tree_and_two_runs_agree_with_the_numbers_it_read(tree,tmp_path):
    engine(tree,tmp_path);docs,receipt,calls,docker=run(tree,'IDENT');m=kprobe.K().m
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','ROOT_IDENTITIES_READ_TWICE_EQUAL_TO_THE_HOST',None),receipt
    assert receipt['host_identities']==identities(tree) and receipt['comparison']['runs_agree'] is True
    assert_docker(docker,[['image','inspect'],['ps','-a'],['run','--rm'],['run','--rm'],['ps','-a']],[m.scripts()['IDENT']]*2)
    runs=[call['argv'] for call in docker if call['argv'][0]=='run']
    assert runs[0]==m.RUN_PREFIX+['--name','hostops02-probe-ident-'+docs.go16()+'-1','--mount','type=bind,source=/var/lib/c3po-capacity,target=/c3po-capacity,readonly',
                                  IMAGE,'python','-I','-B','-'] and runs[1][16].endswith('-2')
    assert receipt['tree_after']=={'status':'COMPLETE','unchanged':True,'code':None}
    assert_read_only(calls)
    walked=[entry['path'] for entry in calls if entry['call']=='open']
    assert '/var/lib/c3po-capacity' in walked and all('/var/lib/c3po-capacity/'+name in walked for name in kprobe.CHILDREN)

def test_native_load_reads_the_config_and_the_worker_and_loads_with_the_bind(tree,tmp_path):
    engine(tree,tmp_path);docs,receipt,calls,docker=run(tree,'LOAD');m=kprobe.K().m
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','STATIC_CONFIG_LOADED_WITH_THE_WORKER_BIND',None),receipt
    assert receipt['precheck']['config_file']=={'regular':True,'private':True,'sha256_as_signed':True,'bytes':len(kprobe.CONFIG)}
    assert receipt['precheck']['worker']['id']==WORKER_ID and receipt['worker_after']['unchanged'] is True
    assert_docker(docker,[['image','inspect'],['container','inspect'],['container','inspect'],['container','inspect'],['ps','-a'],['run','--rm'],['ps','-a'],['container','inspect']],
                  [m.stdin_of(docs.plan)])
    assert docker[2]['argv']==['container','inspect','--format',m.MOUNTS_FORMAT,WORKER_ID]
    reads=[entry for entry in calls if entry['call']=='open' and entry['path'].endswith(kprobe.CONFIG_NAME)]
    assert len(reads)==1 and reads[0]['flags']&os.O_NONBLOCK and reads[0]['by_dir_fd']
    assert_read_only(calls)

def test_native_load_refuses_a_worker_whose_capacity_mount_is_writable_and_starts_nothing(tree,tmp_path):
    engine(tree,tmp_path,mounts=[{'type':'bind','source':'/var/lib/c3po-capacity','destination':'/c3po-capacity','rw':True}])
    docs,receipt,calls,docker=run(tree,'LOAD')
    assert (receipt['status'],receipt['code'])==('REFUSED','WORKER_CAPACITY_MOUNT_WRITABLE') and [call['argv'][0] for call in docker]==['image','container','container']
    assert_read_only(calls)

def test_native_ident_finds_a_child_that_is_not_private_and_starts_nothing(tree,tmp_path):
    os.chmod(str(tree/'var/lib/c3po-capacity/go'),0o750);engine(tree,tmp_path);docs,receipt,calls,docker=run(tree,'IDENT')
    assert (receipt['status'],receipt['code'])==('REFUSED','CAPACITY_CHILD_NOT_PRIVATE') and [call['argv'][0] for call in docker]==['image']
    assert_read_only(calls)

def test_native_ident_refuses_a_link_in_place_of_the_root(tree,tmp_path):
    root=tree/'var/lib/c3po-capacity';os.rename(str(root),str(tree/'var/lib/elsewhere'));os.symlink(str(tree/'var/lib/elsewhere'),str(root))
    engine(tree,tmp_path);docs,receipt,calls,docker=run(tree,'IDENT')
    assert (receipt['status'],receipt['code'])==('REFUSED','CAPACITY_ROOT_NOT_A_DIRECTORY') and [call['argv'][0] for call in docker]==['image']
    assert_read_only(calls)

def test_native_calendar_runs_the_real_calendar_pin_against_the_release(tree,tmp_path):
    release=kprobe.release_tree()
    if release is None or VENV is None:pytest.skip('no tree of the release or no interpreter with its requirements')
    engine(tree,tmp_path,release=str(release/'c3po'/'backend'),app_python=str(VENV));docs,receipt,calls,docker=run(tree,'CALENDAR');m=kprobe.K().m
    assert (receipt['status'],receipt['outcome'],receipt['code'])==('METADATA_ONLY_REQUIRES_REVIEW','CALENDAR_LINE_READ_IN_THE_IMAGE_AS_PINNED',None),receipt
    line=receipt['lines'][0]['line'];assert (line['epoch'],line['package_sha'],line['document_order_sha'])==(m.EPOCH_NAME,m.PACKAGE_SHA,m.DOCUMENT_ORDER)
    assert_docker(docker,[['image','inspect'],['ps','-a'],['run','--rm'],['ps','-a']],[m.scripts()['CALENDAR']])
    assert [call['argv'] for call in docker if call['argv'][0]=='run'][0]==m.RUN_PREFIX+['--name','hostops02-probe-calendar-'+docs.go16(),IMAGE,'python','-I','-B','-']
    assert_read_only(calls)

def test_the_stand_in_runs_no_calendar_pin_without_the_release(tree,tmp_path):
    engine(tree,tmp_path);docs,receipt,calls,docker=run(tree,'CALENDAR')
    assert (receipt['status'],receipt['code'])==('PARTIAL_METADATA_REQUIRES_REVIEW','OUTPUT_NOT_ONE_LINE') and receipt['lines'][0]['returncode']==70

def test_native_load_refuses_a_worker_without_the_release_pin_and_starts_nothing(tree,tmp_path):
    engine(tree,tmp_path,environment={'C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE':'/var/lib/c3po-capacity'})
    docs,receipt,calls,docker=run(tree,'LOAD')
    assert (receipt['status'],receipt['code'])==('REFUSED','WORKER_RELEASE_SHA_NOT_AS_SIGNED') and [call['argv'][0] for call in docker]==['image','container','container','container']
    assert_read_only(calls)
