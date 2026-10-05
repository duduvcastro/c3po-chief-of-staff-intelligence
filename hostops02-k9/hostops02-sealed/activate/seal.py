"""Seal of K6a (activate). Offline; run by the author when every other file is final.

  seal.py write    writes SHA256SUMS: every file of this directory (build/ included), for `shasum -a 256 -c SHA256SUMS`
  seal.py check    exit 1 unless SHA256SUMS agrees with the files as they are AND build/ is what the frozen core
                   assembles from spec.py and op.py (assemble.py --check), with the core beside this directory as
                   ../core or where HOSTOPS02_CORE_DIRECTORY says
Hashes are computed here, never typed. What the Linux job writes while it runs is not listed.
"""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
CORE=Path(os.environ.get('HOSTOPS02_CORE_DIRECTORY') or HERE.parent/'core').resolve()
SKIP_DIRECTORIES=('__pycache__','.pytest_cache','_tmp')
OUTPUT=re.compile(r'linux_root/SHAPES\..*\.json')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def listed():
    out=[]
    for path in sorted(HERE.rglob('*')):
        relative=path.relative_to(HERE)
        if (path.is_file() and relative.as_posix()!='SHA256SUMS' and not set(relative.parts)&set(SKIP_DIRECTORIES) and path.suffix!='.pyc'
                and not OUTPUT.fullmatch(relative.as_posix())):out.append(relative.as_posix())
    return out
def sums():return ''.join('%s  %s\n'%(sha(HERE/name),name) for name in listed())

def main(mode):
    if mode=='write':
        (HERE/'SHA256SUMS').write_text(sums(),encoding='ascii')
        print('SHA256SUMS:',sha(HERE/'SHA256SUMS'),'(%d files)'%len(listed()));return 0
    if mode=='check':
        same=(HERE/'SHA256SUMS').is_file() and (HERE/'SHA256SUMS').read_text(encoding='ascii')==sums()
        built=subprocess.run([sys.executable,'-B',str(CORE/'assemble.py'),'--check',str(HERE)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        ok=same and built.returncode==0
        print('SEAL_OK' if ok else 'SEAL_BROKEN',built.stdout.decode().strip());return 0 if ok else 1
    print(__doc__);return 2

if __name__=='__main__':raise SystemExit(main(sys.argv[1] if len(sys.argv)==2 else ''))
