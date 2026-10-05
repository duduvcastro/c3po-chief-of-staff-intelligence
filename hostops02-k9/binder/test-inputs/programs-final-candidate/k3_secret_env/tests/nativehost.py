"""The private tree that stands in for "/" in the native tests of K3, and the one thing of the host they cannot have: the
docker CLI. The source's own Native makes every file system call for real (the core's tests/oslevel.py substitutes "/"
and reports the test user as root); only NativeRunner.run is replaced, by a subclass that answers the four fixed docker
reads from the core's emulated engine (tests/hostemu.py) instead of starting a process. No docker binary is ever
started by these tests, on the workstation or anywhere."""
import os
from pathlib import Path

import hostemu
import k3env

BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
CONFIG='/etc/c3po-reader'

def build(root):
    """The tree: boot_id, /usr/bin/docker (a plain file, never executed), /etc/c3po-reader 0700 with docker-cli/ 0700, as
    the reader provisioning of 2026-10-03 left it."""
    root=Path(str(root))
    for path in ('proc/sys/kernel/random','usr/bin','etc'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(str(path),0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    docker=root/'usr/bin/docker';docker.write_bytes(b'NOT A BINARY: never executed\n');os.chmod(str(docker),0o755)
    for path in (CONFIG,CONFIG+'/docker-cli'):
        (root/path.lstrip('/')).mkdir(mode=0o700);os.chmod(str(root/path.lstrip('/')),0o700)
    return root

def engine(value=k3env.VALUE):
    """The emulated engine with one running worker (compose project c3po, service r2d2-worker) whose environment holds
    the value under C3PO_DATABASE_URL."""
    env=['PATH=/usr/local/bin:/usr/bin','C3PO_SERVICE_NAME=r2d2-worker','EODHD_API_TOKEN='+hostemu.SECRET+'-token','C3PO_DATABASE_URL='+value]
    worker=hostemu.container(k3env.WORKER,hostemu.BACKEND,'c3po/backend:production',env,project='c3po',service='r2d2-worker');worker['Id']=k3env.WORKER_ID
    return hostemu.FakeDocker([],{},{},[worker])

def native(value=k3env.VALUE,base=None):
    """An instance of the source's own Native (or of the subclass given) whose run() answers from the emulated engine;
    the sizes asked of every read are recorded (os.read is not substituted by oslevel)."""
    m=k3env.K().m;docker=engine(value)
    class EmulatedDocker(base or m.Native):
        def __init__(self):self.argv=[];self.reads=[]
        def run(self,argv,gate,seconds,capture=True,docker_config=None,stdin=None,variables=None,limit=65536):
            gate();assert argv[0]=='/usr/bin/docker' and stdin is None and not variables and docker_config is None and capture
            self.argv.append(list(argv));return docker.run(list(argv[1:]),None,{})
        def read(self,fd,size):
            self.reads.append(size);return (base or m.Native).read(self,fd,size)
    return EmulatedDocker()

def fields(root):
    import oslevel,family as f
    return {'config_chain':oslevel.rows(root,CONFIG),'worker_container_id':k3env.WORKER_ID,'evidence_boot_id_sha256':f.sha(BOOT.strip())}
