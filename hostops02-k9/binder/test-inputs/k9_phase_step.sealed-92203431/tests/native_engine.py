"""K9W's own Native on a real temporary tree, with the one thing a workstation has no real counterpart for replaced:
the docker CLI. Every file call (the walks, the lstat and reads of the receipts and records, the claim, the
directories, the step plan, the launch record) is the unmodified Native's and reaches the kernel; `run` alone is
answered by the emulated engine of k9w.py (its container side never writes into the real tree). fstatvfs is the
kernel's unless the workstation has less than the floor free, when the emulated host's figures stand in (said in the
result); no docker binary is started, no host is contacted."""
import os
from pathlib import Path

import k9w

def build(root,emulated):
    """The emulated tree written as real directories and files under root (which stands for '/')."""
    root=Path(str(root));modes=[]
    for path in emulated.tree.paths():
        node=emulated.tree.get(path);target=root/path[1:]
        if node.kind=='dir':target.mkdir();modes.append((target,node.mode))
        elif node.kind=='file':target.write_bytes(bytes(node.content));modes.append((target,node.mode))
        elif node.kind=='symlink':os.symlink('/nonexistent-target',str(target))
    os.chmod(str(root),0o755)
    for target,mode in sorted(modes,key=lambda item:-len(item[0].parts)):os.chmod(str(target),mode)
    return root

def engine(k,emulated):
    """An instance of a subclass of the source's Native that overrides `run` (and fstatvfs only below the floor)."""
    emulated.docker.check_mounts=False
    class Engine(k.m.Native):
        def run(self,argv,gate,seconds,capture=True,docker_config=None,stdin=None,variables=None,limit=65536):
            return emulated.run(argv,gate,seconds,capture,docker_config,stdin,variables,limit)
        def fstatvfs(self,fd):
            real=os.fstatvfs(fd)
            if real.f_bavail*real.f_frsize>=k.m.K9W_DISK_FLOOR_BYTES:return real
            return emulated.vfs[k9w.hostemu.ROOT_DEVICE]
    return Engine()
