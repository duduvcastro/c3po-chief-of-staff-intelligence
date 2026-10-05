"""The private tree that stands in for "/" in the native tests of K3-K9, and the one thing of the host they cannot have:
the docker CLI. The source's own Native makes every file system call for real (the core's tests/oslevel.py substitutes
"/" and reports the test user as root); only NativeRunner.run is replaced, by a subclass that answers the three fixed
docker reads from the core's emulated engine (tests/hostemu.py) instead of starting a process. No docker binary is ever
started by these tests, on the workstation or anywhere."""
import os
from pathlib import Path

import hostemu
import k3
import oslevel

BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
VOLUME_DEVICE_SHIFT=1<<20

class VolumeInfo(oslevel.Info):
    """An lstat or fstat as oslevel reports it, and for an object of the data volume's subtree a device number of its
    own: the temporary tree is one filesystem, and the source requires the data volume to be a mount point (the device
    of /mnt/day-d-data differs from that of /mnt). Everything else is the real answer of the system call."""
    def __init__(self,info,uids,gids,volume):oslevel.Info.__init__(self,info,uids,gids);self._volume=volume
    def __getattr__(self,name):
        value=oslevel.Info.__getattr__(self,name)
        if name=='st_dev' and (self._info.st_dev,self._info.st_ino) in self._volume:return value+VOLUME_DEVICE_SHIFT
        return value

class Substitute(oslevel.Substitute):
    """oslevel.Substitute with the data volume's subtree on a device of its own (VolumeInfo)."""
    def __init__(self,root,real_prctl=False):
        oslevel.Substitute.__init__(self,root,real_prctl);volume=Path(self.root)/k3.DATA.lstrip('/');found=set()
        for path in [volume]+list(volume.rglob('*')):
            info=os.lstat(str(path));found.add((info.st_dev,info.st_ino))
        self.volume=found
    def info(self,info):return VolumeInfo(info,self.uids,self.gids,self.volume)

def rows_of(root,paths):
    mapper=Substitute(root);out=[]
    for path in paths:
        info=mapper.info(os.lstat(str(Path(str(root))/path.lstrip('/'))))
        out.append({'path':path,'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':info.st_mode&0o7777,
                    'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns})
    return out

def build(root,tokens=None,url_file=None,password_file=None):
    """The tree: boot_id, /usr/bin/docker (a plain file, never executed), the data volume with the K9 root and its empty
    secrets directory (0700), and the two directories of September (0700) with their files (0600)."""
    m=k3.K().m;root=Path(str(root))
    for path in ('proc/sys/kernel/random','usr/bin','etc','var/lib'):(root/path).mkdir(parents=True,mode=0o755)
    data=root/m.SOURCE_OPEN_ROOT.lstrip('/');data.mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(str(path),0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    docker=root/'usr/bin/docker';docker.write_bytes(b'NOT A BINARY: never executed\n');os.chmod(str(docker),0o755)
    for path in ('/var/lib/c3po',m.K9_ROOT,m.K9_SECRETS_DIRECTORY,m.RISK_URL_DIRECTORY,k3.DATA+'/.c3po-role-executor-20260908-r2',m.EMITTER_SOURCE_DIRECTORY):
        (root/path.lstrip('/')).mkdir(mode=0o700);os.chmod(str(root/path.lstrip('/')),0o700)
    for name in ('tools','days','claims'):(root/m.K9_ROOT.lstrip('/')/name).mkdir(mode=0o700)
    url=root/(m.RISK_URL_DIRECTORY+'/'+m.RISK_URL_NAME).lstrip('/');url.write_bytes((k3.url()+'\n').encode() if url_file is None else url_file);os.chmod(str(url),0o600)
    password=root/(m.EMITTER_SOURCE_DIRECTORY+'/'+m.EMITTER_SOURCE_NAME).lstrip('/')
    password.write_bytes(k3.PASSWORD.encode() if password_file is None else password_file);os.chmod(str(password),0o600)
    return root

def engine(tokens=None):
    """The emulated engine with one running worker whose environment holds the tokens under their plain names."""
    m=k3.K().m;values=dict(k3.TOKENS if tokens is None else tokens)
    env=['PATH=/usr/local/bin:/usr/bin','C3PO_DATABASE_URL=postgresql://c3po:'+hostemu.SECRET+'@db:5432/c3po']+['%s=%s'%(plain,values[prefixed]) for prefixed,plain in m.PROVIDER_TOKEN_NAMES]
    worker=hostemu.container(k3.WORKER,hostemu.BACKEND,'c3po/backend:production',env,project='c3po',service='r2d2-worker');worker['Id']=k3.WORKER_ID
    return hostemu.FakeDocker([],{},{},[worker])

def native(tokens=None,base=None):
    """An instance of the source's own Native (or of the subclass given) whose run() answers from the emulated engine."""
    m=k3.K().m;docker=engine(tokens)
    class EmulatedDocker(base or m.Native):
        argv=[]
        def run(self,argv,gate,seconds,capture=True,docker_config=None,stdin=None,variables=None,limit=65536):
            gate();assert argv[0]=='/usr/bin/docker' and stdin is None and not variables and docker_config is None and capture
            self.argv.append(list(argv));return docker.run(list(argv[1:]),None,{})
    return EmulatedDocker()

def source_rows(root):
    """The rows of the five paths below the data volume, read from the real tree (the test user reported as root)."""
    return rows_of(root,k3.K().m.SOURCE_PATHS)

def fields(root):
    import oslevel,family as f
    m=k3.K().m
    volume=[{key:row[key] for key in ('path','device','inode','uid','gid','mode')} for row in rows_of(root,['/','/mnt',m.SOURCE_OPEN_ROOT])]
    return {'source_rows':source_rows(root),'secrets_chain':oslevel.rows(root,m.K9_SECRETS_DIRECTORY),'data_volume_chain':volume,'worker_container_id':k3.WORKER_ID,'evidence_boot_id_sha256':f.sha(BOOT.strip())}
