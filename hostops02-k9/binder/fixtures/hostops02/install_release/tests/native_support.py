"""Real system calls for K10: the core's os-level substitution (tests/oslevel.py of the frozen core, unchanged) plus the
one thing a temporary tree cannot have, a data volume on a filesystem of its own.

oslevel.Substitute redirects the single absolute open ("/") to a private temporary tree, reports the test user as root
and records every system call with its arguments. K10 also requires the signed rows to show that the data volume root
is a mount point (its device differs from its parent's), and a temporary tree is one filesystem. Volume adds that and
nothing else: every stat result of a path at or below /mnt/day-d-data reports the real device number plus one. The
calls themselves (mkdir, open, write, fsync, link, unlink, lstat, fstat, scandir) reach the kernel unchanged, with the
flags the source's own unmodified Native gave them. No host, no docker, no ssh, no credential."""
import os
from pathlib import Path

import oslevel

VOLUME='/mnt/day-d-data'
OFFSET=1
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'

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
    """A private tree that stands in for "/": /mnt/day-d-data with the maintenance pin, the boot identifier."""
    root=Path(str(base)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('mnt/day-d-data/provider=synthetic','proc/sys/kernel/random','etc'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(path,0o755)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    pin=root/'mnt/day-d-data/.r2d2-v2-pinned';pin.write_bytes(b'');os.chmod(pin,0o600)
    return root
