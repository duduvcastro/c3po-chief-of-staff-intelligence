"""Fixtures of K2a (catalog initialisation): request plans built from the emulated host exactly as a binder copies them
from the read-only receipts, and what the emulated container does. The container is a model, in Python, of the pinned
script and of the application code it calls (SessionJournalRoot with create=True); tests/test_real_script.py runs the
real script against the real modules of the release and compares, so that the model is not this file's opinion."""
import json
import os
from pathlib import Path
import re
import stat

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
JOURNAL='/var/lib/c3po-bar/journal'
PRIVATE_PARENT='/var/lib/c3po-bar'
CONFIG='/etc/c3po-bar/docker-cli'
TARGET='/c3po-bar-journal'
PARENT='/var/lib'
THROWAWAY='c3po-bar-rehearsal-20261003a'
REHEARSAL_ROOT=PARENT+'/'+THROWAWAY
REHEARSAL_CONFIG=REHEARSAL_ROOT+'.docker-cli'          # what a rehearsal gives docker as DOCKER_CONFIG, created by the run
EPOCH='R2D2-V2-SHADOW-2026-10-05'
DIAG='R2D2-V2-DIAG-K2A-REHEARSAL-20261003'
SCRIPT_SHA='715d7a660e7a2c4dd5c11287063726cc971156dd6fefc2365c431c9aee0f4bb7'
NAMES=['epoch.json','maintenance.lock']
EPOCH_GRAMMAR=r'R2D2-V2-(?:SHADOW|DIAG)-[A-Za-z0-9_-]{1,80}'          # validate_epoch, r2d2_v2_store.py:39 at dd4ec4bb

def K():return f.load(DIRECTORY)
def script():return K().m.script_bytes()
def expected_epoch_json(epoch,device,inode):
    return f.canonical({'schema':'MASSIVE_SESSION_ROOT_V1','epoch':epoch,'device':device,'inode':inode})

class Refusal(ValueError):pass
def catalog_model(fs,arguments,euid=0):
    """The pinned script, statement by statement, over a small file interface (listdir, stat, read, write). The calls
    it makes into the application are said as the application says them at dd4ec4bb: the private-directory and owner
    checks of the root, maintenance.lock created first, epoch.json written in place with the canonical bytes, an
    existing epoch.json compared byte for byte. Returns (exit status, standard output)."""
    try:
        root,epoch=arguments
        if not re.fullmatch(EPOCH_GRAMMAR,epoch):raise Refusal('EPOCH_INVALID')
        before=sorted(fs.listdir(root))
        if before and 'epoch.json' not in before:raise Refusal('CATALOG_INIT_ROOT_NOT_EMPTY')
        info=fs.stat(root)
        if stat.S_IMODE(info.st_mode)&0o077:raise Refusal('SOURCE_DIRECTORY_NOT_PRIVATE')
        if info.st_uid!=euid:raise Refusal('MASSIVE_SESSION_ROOT_OWNER')
        if 'maintenance.lock' not in before:fs.write(root+'/maintenance.lock',b'',0o600)
        expected=expected_epoch_json(epoch,info.st_dev,info.st_ino)
        if 'epoch.json' in before:
            if fs.read(root+'/epoch.json')!=expected:raise Refusal('MASSIVE_SESSION_MANIFEST_CHANGED')
        else:fs.write(root+'/epoch.json',expected,0o600)
        catalog=json.loads(fs.read(root+'/epoch.json'))
        receipt={'status':'CATALOG_READY','created':not before,'epoch':catalog['epoch'],'device':catalog['device'],'inode':catalog['inode'],
                 'entries':sorted(fs.listdir(root))}
    except Exception as error:
        code=error.args[0] if len(error.args)==1 and type(error.args[0]) is str else type(error).__name__
        return 1,(json.dumps({'status':'CATALOG_REFUSED','code':code},sort_keys=True)+'\n').encode()
    return 0,(json.dumps(receipt,sort_keys=True)+'\n').encode()

class RealDirectory:
    """The file interface of catalog_model over a real directory (for the comparison with the real script)."""
    def listdir(self,path):return os.listdir(path)
    def stat(self,path):return os.stat(path)
    def read(self,path):
        with open(path,'rb') as stream:return stream.read()
    def write(self,path,content,mode):
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode)
        try:os.write(fd,content)
        finally:os.close(fd)

def assert_readme_run(call):
    """What the engine was asked for is the README's run and nothing else."""
    assert call.stdin==script() and f.sha(call.stdin)==SCRIPT_SHA
    assert call.flags==['--rm','-i','--init','--read-only'] and call.name is None and call.network=='none' and call.read_only_root
    assert call.options=={'--pull':['never'],'--user':['0:0'],'--network':['none'],'--cap-drop':['ALL'],'--security-opt':['no-new-privileges']}
    assert len(call.mounts)==1 and call.mounts[0]['read_only'] is False and call.command[:4]==['python','-I','-B','-'] and len(call.command)==6
    source=call.mounts[0]['source']                # the unit's directory for a journal root, the rehearsal's own beside a throwaway root
    assert call.mounts[0]['target']==call.command[4] and call.environment=={'DOCKER_CONFIG':CONFIG if source.startswith(PRIVATE_PARENT+'/') else source+'.docker-cli'}

def container(call):
    """The emulated container of a correct run."""
    assert_readme_run(call);return catalog_model(call,call.command[4:])

def real_fields(host,journal=JOURNAL):
    return {'mode':'REAL','journal_chain':hostemu.rows(host,journal),'throwaway_name':None,'reference_chain':None,'container_journal_root':TARGET,
            'docker_config_chain':hostemu.rows(host,CONFIG),'image_id':hostemu.BACKEND,'image_revision':hostemu.REVISION,'epoch':EPOCH,
            'script_sha256':SCRIPT_SHA,'evidence_boot_id_sha256':f.BOOT_SHA}
def rehearsal_fields(host,parent=PARENT,name=THROWAWAY,reference=JOURNAL):
    return {'mode':'REHEARSAL','journal_chain':hostemu.rows(host,parent),'throwaway_name':name,'reference_chain':hostemu.rows(host,reference),
            'container_journal_root':TARGET,'docker_config_chain':hostemu.rows(host,CONFIG),'image_id':hostemu.BACKEND,'image_revision':hostemu.REVISION,
            'epoch':DIAG,'script_sha256':SCRIPT_SHA,'evidence_boot_id_sha256':f.BOOT_SHA}

def world():
    """The emulated host as supervisor operation 2 leaves it under placement A (everything of the supervisor empty)."""
    k=K();host=f.world(k);hostemu.provision_supervisor(host);host.docker.on_run=container;return k,host
def case(mode='REAL',now=None):
    """(docs, host): a bound fixture that completes on a fresh emulated host."""
    k,host=world();fields=real_fields(host) if mode=='REAL' else rehearsal_fields(host)
    return f.Docs(k,fields,now=now),host
def root_of(mode):return JOURNAL if mode=='REAL' else REHEARSAL_ROOT
def config_of(mode):return CONFIG if mode=='REAL' else REHEARSAL_CONFIG
def state_of(host):return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)


# ---------------------------------------------------------------- the release, when a tree of it is at hand
RELEASE='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
RELEASE_FILES={'c3po/deployment/massive-supervisor/README.md':'644c6211c7351de1dfd17d880842deaf4d5e5b34ea63d23a274c5f4e463461c5',
               'c3po/backend/app/r2d2_v2_massive_sessions.py':'c4ffe1c9095a81b0057dc2b7995198f25179015e5af963f137c7b8f7c1605312',
               'c3po/backend/app/r2d2_v2_massive_maintenance.py':'8946a93939162c33b19575681cb920359181a53bf27dacf3918b5a9d1a2052d9',
               'c3po/backend/app/r2d2_v2_store.py':'9f9887c267af10c5494ec1a4dd2628b05f74f40dd2bae34e340bf81f00575254',
               'c3po/backend/app/r2d2_v2_epoch_assembler.py':'8ef584e2dd5d0b41d33f06a00926877573c65b5540f450236910e07ba51ee37c'}
def release_tree():
    """A directory that holds the files of the release this operation is frozen against (each compared by hash), or
    None. Looked for in HOSTOPS02_TEST_RELEASE_TREE, in work/release of this operation directory (an extraction made
    with `git archive dd4ec4bb`), and in the directories above it (a checkout of the release that holds this one)."""
    candidates=[Path(os.environ['HOSTOPS02_TEST_RELEASE_TREE'])] if os.environ.get('HOSTOPS02_TEST_RELEASE_TREE') else []
    candidates+=[DIRECTORY/'work'/'release']+list(DIRECTORY.parents)[:6]
    for candidate in candidates:
        try:
            if all(f.sha((candidate/name).read_bytes())==pin for name,pin in RELEASE_FILES.items()):return candidate.resolve()
        except OSError:continue
    return None
