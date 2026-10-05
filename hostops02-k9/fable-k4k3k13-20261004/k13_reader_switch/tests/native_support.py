"""Real system calls for K13: the core's os-level substitution (tests/oslevel.py of the frozen core, unchanged), the data
volume on a device of its own (Volume, the class of install_release's and K4-E0's native_support.py), a real tree
standing in for '/' with everything the reader launch reads, and the source's own Native with two things replaced:

  run        the docker CLI and systemctl are answered by the emulated engine of tests/k13.py (ReaderHost). No binary is
             started. The emulated systemd is shown the real activation.env (its ExecCondition) by a read of the real
             tree made with the builtin open, which is not a call of the source.
  fstatvfs   the real call is made on the held descriptor; f_bavail is then reported as 100 GiB, because the journal
             floor the source requires (at least 53,687,091,200 bytes) is a figure of the host, not of a workstation.

Every other call of the run (the walks, lstat, open, read, fstat, the creation of activation.env by an exclusive
temporary, link, unlink, fsync, umask) is the unmodified Native's and reaches the kernel. No host, no docker, no ssh."""
import os
from pathlib import Path
import types

import family as f
import hostemu
import k13
import oslevel

VOLUME='/mnt/day-d-data'
OFFSET=1
BOOT=hostemu.BOOT
FREE_BYTES=100*1024**3

class Moved:
    """A stat result of the data volume: the same values, another device."""
    def __init__(self,info):self._info=info
    def __getattr__(self,name):
        value=getattr(self._info,name);return value+OFFSET if name=='st_dev' else value

def inside(path):return path==VOLUME or path.startswith(VOLUME+'/')

class Volume:
    """with Volume(root) as record: <one run with the module's own Native()>"""
    def __init__(self,root):self.substitute=oslevel.Substitute(root)
    def __enter__(self):
        record=self.record=self.substitute.__enter__();self.patched={name:getattr(os,name) for name in ('stat','lstat','fstat')};patched=self.patched
        def stat_(path,*,dir_fd=None,follow_symlinks=True):
            info=patched['stat'](path,dir_fd=dir_fd,follow_symlinks=follow_symlinks);return Moved(info) if inside(record.name(path,dir_fd)) else info
        def lstat_(path,*,dir_fd=None):return stat_(path,dir_fd=dir_fd,follow_symlinks=False)
        def fstat_(fd):
            info=patched['fstat'](fd);return Moved(info) if inside(record.paths.get(fd,'?')) else info
        os.stat,os.lstat,os.fstat=stat_,lstat_,fstat_
        return record
    def __exit__(self,*exception):
        for name,function in self.patched.items():setattr(os,name,function)
        return self.substitute.__exit__(*exception)

def rows(root,path):
    """Six-key rows read from the real tree as the source will read them: the test user as root, the volume on its own device."""
    out=oslevel.rows(root,path)
    for row in out:
        if inside(row['path']):row['device']+=OFFSET
    return out

def build_tree(base):
    """A private tree that stands in for '/', holding what the weekend operations leave for the reader launch."""
    root=Path(str(base)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('proc/sys/kernel/random','usr/bin','etc/systemd/system','etc/c3po-reader/docker-cli','etc/c3po-reader/launcher',
                 'var/lib/c3po-bar/journal','mnt/day-d-data/r2d2-v2-release-20261005','var/lib/c3po/r2d2-v2-source-20261005','var/lib/c3po-capacity'):(root/path).mkdir(parents=True,exist_ok=True)
    for path in [root]+sorted(root.rglob('*')):os.chmod(path,0o755)
    for path in ('etc/c3po-reader','etc/c3po-reader/docker-cli','etc/c3po-reader/launcher','var/lib/c3po-bar','var/lib/c3po-bar/journal',
                 'mnt/day-d-data/r2d2-v2-release-20261005','var/lib/c3po','var/lib/c3po/r2d2-v2-source-20261005','var/lib/c3po-capacity'):os.chmod(root/path,0o700)
    def put(path,raw,mode):
        target=root/path.lstrip('/');target.write_bytes(raw);os.chmod(target,mode)
    put('/proc/sys/kernel/random/boot_id',BOOT,0o444)
    for name in ('docker','systemctl'):put('/usr/bin/'+name,b'not a binary: never started',0o755)
    for name,raw in k13.UNIT_BYTES.items():put(k13.UNITS+'/'+name,raw,0o644)
    put(k13.LAUNCHER_DIRECTORY+'/reader_launcher.py',k13.LAUNCHER,0o600)
    put(k13.CONFIG+'/secret.env',k13.SECRET_LINE,0o600)
    put(k13.CONFIG+'/pins.env',k13.PINS,0o600)
    put(k13.JOURNAL+'/maintenance.lock',b'',0o600)
    journal=os.stat(root/k13.JOURNAL.lstrip('/'))
    put(k13.JOURNAL+'/epoch.json',f.canonical({'schema':'MASSIVE_SESSION_ROOT_V1','epoch':k13.EPOCH,'device':journal.st_dev,'inode':journal.st_ino}),0o600)
    put(k13.RELEASE_DIRECTORY+'/'+k13.RELEASE_NAME,k13.RELEASE,0o600)
    return root

def fields(root,mode='ACTIVATE'):
    def digest(path):return f.sha((root/path.lstrip('/')).read_bytes())
    out={'mode':mode,'evidence_boot_id_sha256':f.sha(BOOT.strip()),'unit_rows':rows(root,k13.UNITS),'config_rows':rows(root,k13.CONFIG),
         'launcher_rows':rows(root,k13.LAUNCHER_DIRECTORY),'journal_rows':rows(root,k13.JOURNAL),'release_rows':rows(root,k13.RELEASE_DIRECTORY),
         'release':{'name':k13.RELEASE_NAME,'sha256':f.sha(k13.RELEASE)},
         'files':{'reader_service':digest(k13.UNITS+'/'+k13.SERVICE),'reader_timer':digest(k13.UNITS+'/'+k13.TIMER),'reader_alert':digest(k13.UNITS+'/'+k13.ALERT),
                  'producer_service':digest(k13.UNITS+'/'+k13.PRODUCER),'launcher':digest(k13.LAUNCHER_DIRECTORY+'/reader_launcher.py'),
                  'pins':digest(k13.CONFIG+'/pins.env')},
         'image_id':hostemu.BACKEND,'journal_free_floor_bytes':56706990080,'source_rows':rows(root,k13.SOURCE_ROOT),'capacity_rows':rows(root,k13.CAPACITY)}
    if mode=='DEACTIVATE':
        for key in ('unit_rows','config_rows','launcher_rows','journal_rows','release_rows','release','files','image_id','journal_free_floor_bytes','source_rows','capacity_rows'):out[key]=None
    return out

def engine(k,root,setup=None,die=None):
    """An instance of a subclass of the source's Native that replaces run and fstatvfs only, and the emulated engine.
    die: a callable(argv) that may end the process after an emulated command took effect (os._exit)."""
    emulated=k13.world(k);root=str(root)
    if setup is not None:setup(emulated)
    real_fstatvfs=os.fstatvfs
    class Engine(k.m.Native):
        def run(self,argv,gate,seconds,capture=True,docker_config=None,stdin=None,variables=None,limit=65536):
            path=k13.CONFIG+'/activation.env'
            try:
                with open(root+path,'rb') as stream:raw=stream.read()          # the builtin open: not a call of the source
                if emulated.tree.get(path) is None:emulated.tree.add(path,kind='file',mode=0o600,content=raw)
            except FileNotFoundError:pass
            result=emulated.run(argv,gate,seconds,capture,docker_config,stdin,variables,limit)
            if die is not None:die(argv)
            return result
        def fstatvfs(self,fd):
            numbers=real_fstatvfs(fd)
            return types.SimpleNamespace(f_frsize=numbers.f_frsize,f_bavail=FREE_BYTES//numbers.f_frsize,f_blocks=numbers.f_blocks,f_bfree=numbers.f_bfree)
    return Engine(),emulated
