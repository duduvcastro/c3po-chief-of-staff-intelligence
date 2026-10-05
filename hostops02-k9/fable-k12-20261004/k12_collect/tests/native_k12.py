"""Real system calls for the K12 families (a byte-identical copy in each family's tests): a private temporary tree that
stands in for '/', with the capacity tree, the reader's configuration, the manifests and receipts directories, the
journal catalog, and the data volume on a device of its own (bound read-only at /app/day-d-data, the
named exception) with the release directory M1 installs (tests/native_support.py, install_release's file), and the
source's own Native with ONE method replaced: NativeRunner.run, which would start the docker CLI. There is no docker
on the workstation; the replacement answers from the emulated engine of tests/k12emu.py. Every filesystem call is the
unmodified source's, recorded by tests/oslevel.py of the frozen core. No host, no docker, no network."""
import os
from pathlib import Path

import family as f
import hostemu
import k12emu as e
import native_support

def write(path,content,mode=0o600):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content);os.chmod(path,mode)

def build_tree(base):
    root=native_support.build_tree(base)
    for path in ('var/lib/c3po-capacity/config','var/lib/c3po-capacity/documents','var/lib/c3po-capacity/payload','var/lib/c3po-capacity/go',
                 'etc/c3po-reader/docker-cli','etc/c3po-bar/manifests','var/lib/c3po-bar/journal','var/lib/c3po-reader/capacity-receipts','mnt/day-d-data/r2d2-v2-release-20261005'):
        (root/path).mkdir(parents=True,exist_ok=True)
    for path in ('var','var/lib','etc'):os.chmod(root/path,0o755)
    for path in ('var/lib/c3po-capacity','var/lib/c3po-capacity/config','var/lib/c3po-capacity/documents','var/lib/c3po-capacity/payload',
                 'var/lib/c3po-capacity/go','etc/c3po-reader','etc/c3po-reader/docker-cli','etc/c3po-bar','etc/c3po-bar/manifests','var/lib/c3po-bar',
                 'var/lib/c3po-bar/journal','var/lib/c3po-reader','var/lib/c3po-reader/capacity-receipts','mnt/day-d-data/r2d2-v2-release-20261005'):os.chmod(root/path,0o700)
    write(root/'mnt/day-d-data/r2d2-v2-release-20261005/release.CERTIFIED.json',e.RELEASE_BYTES)
    write(root/'etc/c3po-reader/secret.env',e.SECRET_ENV);write(root/'etc/c3po-reader/pins.env',e.PINS)
    write(root/('var/lib/c3po-capacity/config/manifest_writer-%s.py'%e.sha(e.WRITER)),e.WRITER)
    for index in (1,2,3):write(root/('var/lib/c3po-capacity/config/session=%s.%s.capacity.json'%(e.DAY,e.WINDOWS[index])),e.config_bytes(e.DAY,e.WINDOWS[index]))
    for name in ('epoch.json','maintenance.lock'):write(root/('var/lib/c3po-bar/journal/'+name),b'{}')
    binary_present(root)
    return root

def rows(root,path):return native_support.rows(root,path)
def chains(root,names):
    paths={'config':e.CONFIG,'manifests':e.MANIFESTS,'reader_config':e.READER,'docker_cli':e.DOCKER_CLI,'journal':e.JOURNAL,'data':e.RELEASE,'receipts':e.RECEIPTS}
    return {name:rows(root,paths[name]) for name in names}

def engine(k):
    """The emulated engine, alone: hostemu's world for its images and containers, the paths it checks for binds present."""
    host=e.world(k);return host

def with_engine(native,host):
    """The source's own Native class with the process runner answered by the emulated engine (argv, limits and the
    two variables still recorded by the emulated host)."""
    class Answered(native):
        def run(self,argv,gate,seconds,capture=True,docker_config=None,stdin=None,variables=None,limit=65536):
            return host.run(['/usr/bin/docker']+list(argv[1:]),gate,seconds,capture,docker_config,stdin,variables,limit)
    return Answered()

def binary_present(root):
    """A root-owned, closed docker file in the tree, so that the runner's trusted_executable accepts the path; it is never
    executed (run is answered by the emulated engine)."""
    path=root/'usr'/'bin'/'docker';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'ELF');os.chmod(path,0o755)
    for parent in (root/'usr',root/'usr'/'bin'):os.chmod(parent,0o755)
    return path
