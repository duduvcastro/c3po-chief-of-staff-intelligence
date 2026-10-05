"""The source's own Native on a real temporary tree, with the one thing a workstation has no real counterpart for
replaced: the docker CLI. Every file call K6a makes (the walks, the lstat and open of the release, the reads of the
environment file and of .deploy-version, the creations, the flock, the pause) is the unmodified Native's and reaches
the kernel; `run` alone is answered by the emulated engine of hostemu, which is shown the compose files the commands
name by reading them from the real tree. No docker binary is started, no host is contacted."""
import os
from pathlib import Path

import family as f
import hostemu
import k6a
import oslevel

BOOT=hostemu.BOOT
DATA=hostemu.DATA;DEPLOY=hostemu.DEPLOY

def build(root):
    """The tree K6a needs, as real directories and files under root (which stands for '/')."""
    root=Path(str(root))
    for path in ('proc/sys/kernel/random','usr/bin',DATA[1:]+'/r2d2-v2-live',DEPLOY[1:]+'/c3po',DEPLOY[1:]+'/runtime/security'):(root/path).mkdir(parents=True)
    for path in [root]+sorted(root.rglob('*')):os.chmod(path,0o755)
    def put(path,raw,mode):
        target=root/path[1:];target.write_bytes(raw);os.chmod(target,mode)
    put('/proc/sys/kernel/random/boot_id',BOOT,0o444);put('/usr/bin/docker',b'not a binary: never started',0o755)
    put(hostemu.PIN,b'',0o600);put(hostemu.ENV_FILE,('C3PO_DB_PASSWORD='+hostemu.SECRET+'\n').encode(),0o600)
    put(DEPLOY+'/.deploy-version',(hostemu.REVISION+'\n').encode(),0o644);put(hostemu.COMPOSE_FILE,b'services: {}\n',0o644)
    put(k6a.LOCK,b'',0o644)
    (root/k6a.RELEASE_DIRECTORY[1:]).mkdir();os.chmod(root/k6a.RELEASE_DIRECTORY[1:],0o700)
    put(k6a.RELEASE_DIRECTORY+'/'+k6a.RELEASE_NAME,k6a.RELEASE,0o600)
    return root

def fields(root):
    rows=oslevel.rows
    return {'data_root':DATA,'live_parent':rows(root,k6a.LIVE_PARENT),'directory_name':k6a.LEAF,'policy':k6a.policy_member(),'override_name':k6a.OVERRIDE_NAME,
            'release':{'parent':rows(root,DATA),'directory_name':k6a.RELEASE_LEAF,'file_name':k6a.RELEASE_NAME,'sha256':f.sha(k6a.RELEASE),'bytes':len(k6a.RELEASE)},
            'worker':{'image_id':hostemu.BACKEND,'mount_target':k6a.TARGET},
            'compose':{'project':hostemu.PROJECT,'env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE]},
            'deploy_directory':rows(root,DEPLOY),'lock':{'directory':rows(root,hostemu.LOCK_DIRECTORY),'wait_seconds':1},
            'evidence_boot_id_sha256':f.sha(BOOT.strip())}

def real_clocks(docs):
    """The two clocks of a run that really takes time: the monotonic clock of the machine, and a wall clock that starts
    at the fixture's instant (inside its window) and moves with it."""
    import time
    from datetime import timedelta
    start=time.monotonic()
    return {'clock':lambda:docs.now+timedelta(seconds=time.monotonic()-start),'monotonic':time.monotonic}

def engine(k,root,pause=None):
    """An instance of a subclass of the source's Native that overrides `run` only (and, when asked, the pause)."""
    emulated=k6a.world(k);root=str(root)
    class Engine(k.m.Native):
        commands=emulated.commands
        def run(self,argv,gate,seconds,capture=True,docker_config=None,stdin=None,variables=None,limit=65536):
            for index,word in enumerate(argv[:-1]):
                path=argv[index+1]
                if word=='-f' and path not in ('-',hostemu.COMPOSE_FILE) and emulated.tree.get(path) is None:
                    with open(root+path,'rb') as stream:emulated.tree.add(path,kind='file',mode=0o600,content=stream.read())      # the builtin open: not a call of the source
            return emulated.run(argv,gate,seconds,capture,docker_config,stdin,variables,limit)
    if pause is not None:Engine.pause=lambda self,seconds:pause.append(seconds)
    return Engine(),emulated
