"""Seal of the frozen core. Offline; run by the author of the core, once, when every other file is final.

  seal.py write    pins every part and every reviewed base file in assemble.py (PINS), then writes CORE_SHA256SUMS
  seal.py check    exit 1 unless PINS and CORE_SHA256SUMS agree with the files as they are

Two levels, and why:
  PINS (in assemble.py)  the files that determine payload bytes: parts/*.py and reviewed_base/*.py. assemble.py refuses
                         to build from a file that differs from its pin, and the hash of assemble.py itself is the
                         generation every source and every receipt names (CORE_SHA256).
  CORE_SHA256SUMS        every file of this directory, for a reviewer: `shasum -a 256 -c CORE_SHA256SUMS`.
Hashes are computed here, never typed.
"""
import hashlib
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
BEGIN='# ---- PINS BEGIN (written by seal.py: every file that determines payload bytes) ----\n'
END='# ---- PINS END ----\n'
SKIP_DIRECTORIES=('__pycache__','.pytest_cache','_tmp')
OUTPUT=re.compile(r'linux_root/(TESTS\..*\.xml|SHAPES\.linux-root\.json)')      # what the Linux job writes while it runs
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def pinned():
    return sorted(path.relative_to(HERE).as_posix() for folder in ('parts','reviewed_base') for path in (HERE/folder).glob('*.py'))
def pins_block():
    lines=['PINS={']+["      %r:%r,"%(name,sha(HERE/name)) for name in pinned()]+['}']
    return BEGIN+'\n'.join(lines)+'\n'+END
def listed():
    out=[]
    for path in sorted(HERE.rglob('*')):
        relative=path.relative_to(HERE)
        if (path.is_file() and relative.as_posix()!='CORE_SHA256SUMS' and not set(relative.parts)&set(SKIP_DIRECTORIES) and path.suffix!='.pyc'
                and not OUTPUT.fullmatch(relative.as_posix())):
            out.append(relative.as_posix())
    return out
def sums():return ''.join('%s  %s\n'%(sha(HERE/name),name) for name in listed())

def main(mode):
    assembler=HERE/'assemble.py';text=assembler.read_text(encoding='ascii')
    match=re.search(re.escape(BEGIN)+'.*?'+re.escape(END),text,re.S)
    if match is None:raise SystemExit('PINS block not found in assemble.py')
    if mode=='write':
        assembler.write_text(text[:match.start()]+pins_block()+text[match.end():],encoding='ascii')
        (HERE/'CORE_SHA256SUMS').write_text(sums(),encoding='ascii')
        print('core generation (sha256 of assemble.py):',sha(assembler));print('CORE_SHA256SUMS:',sha(HERE/'CORE_SHA256SUMS'),'(%d files)'%len(listed()));return 0
    if mode=='check':
        ok=match.group(0)==pins_block() and (HERE/'CORE_SHA256SUMS').is_file() and (HERE/'CORE_SHA256SUMS').read_text(encoding='ascii')==sums()
        print('SEAL_OK' if ok else 'SEAL_BROKEN');return 0 if ok else 1
    print(__doc__);return 2

if __name__=='__main__':raise SystemExit(main(sys.argv[1] if len(sys.argv)==2 else ''))
