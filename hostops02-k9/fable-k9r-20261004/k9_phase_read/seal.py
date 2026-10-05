"""Seal of the K9R operation directory. Offline; reads and hashes files, runs nothing of the operation.

  seal.py write    (author only) writes SHA256SUMS: one line per file of this directory, sorted, `shasum -a 256` format
  seal.py check    exit 0 and SEAL_OK only when SHA256SUMS lists exactly the files present and every hash holds, the
                   build is what the frozen core assembles (ASSEMBLY.json names that core), and both mutation records
                   were complete runs with zero survivors and zero errors made against the sealed bytes

catalog_init's seal.py with the mutation record of K11's format (pins_sha256: the build, op.py, spec.py, the test
files, mutants.py, and the core's assemble.py, CORE_SHA256SUMS and test modules). Not sealed: SHA256SUMS itself,
work/ (private copies of a mutation run), caches, and the directories review-* at the top of this directory: what a
reviewer writes beside the candidate is the reviewer's, and never breaks its seal.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
CORE=HERE.parent/'core'
SKIPPED_DIRECTORIES=('work','__pycache__','.pytest_cache','_tmp')
SKIPPED_FILES=('SHA256SUMS',)
REVIEW_PREFIX='review-'
RECORDS=('MUTATION_RUN.json','MUTATION_RUN.py312.json')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def files():
    found=[]
    for path in sorted(HERE.rglob('*')):
        relative=path.relative_to(HERE)
        if not path.is_file() or any(part in SKIPPED_DIRECTORIES for part in relative.parts) or str(relative) in SKIPPED_FILES or path.suffix=='.pyc':continue
        if len(relative.parts)>1 and relative.parts[0].startswith(REVIEW_PREFIX):continue
        found.append(str(relative))
    return found
def lines():return ''.join('%s  %s\n'%(sha((HERE/name).read_bytes()),name) for name in files())

def problems():
    out=[];path=HERE/'SHA256SUMS'
    if not path.is_file():return ['SHA256SUMS is missing']
    listed={}
    for line in path.read_text().splitlines():
        digest,_,name=line.partition('  ');listed[name]=digest
    present=files()
    out+=['not listed: '+name for name in present if name not in listed]+['listed and absent: '+name for name in listed if name not in present]
    out+=['hash differs: '+name for name in present if name in listed and listed[name]!=sha((HERE/name).read_bytes())]
    report=json.loads((HERE/'build'/'ASSEMBLY.json').read_bytes())
    if report['core_sha256']!=sha((CORE/'assemble.py').read_bytes()):out.append('build/ASSEMBLY.json names another core generation than ../core')
    if report['operation_part_sha256']!=sha((HERE/'op.py').read_bytes()) or report['spec_sha256']!=sha((HERE/'spec.py').read_bytes()):out.append('build/ was not assembled from op.py and spec.py as they are')
    if report['source_sha256']!=sha((HERE/'build'/(report['module']+'.py')).read_bytes()):out.append('build/ASSEMBLY.json does not name the source in build/')
    done=subprocess.run([sys.executable,'-B',str(CORE/'assemble.py'),'--check',str(HERE)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if done.returncode!=0 or done.stdout.strip()!=b'BUILD_EQUAL':out.append('assemble.py --check: '+done.stdout.decode(errors='replace').strip()[:200])
    for name in RECORDS:
        record=HERE/'mutation'/name
        if not record.is_file():
            out.append('mutation/%s is missing'%name);continue
        row=json.loads(record.read_bytes())
        stale=[relative for relative,pin in row['pins_sha256'].items()
               if not ((CORE/relative[5:]) if relative.startswith('core/') else (HERE/relative)).is_file()
               or sha(((CORE/relative[5:]) if relative.startswith('core/') else (HERE/relative)).read_bytes())!=pin]
        if stale:out.append('mutation/%s was made against other bytes: %s'%(name,', '.join(stale[:6])))
        if not row['complete_run'] or row['counts']['survivors'] or row['counts']['errors']:out.append('mutation/%s is not a complete run with zero survivors and zero errors'%name)
    return out

def main(arguments):
    if arguments==['write']:
        (HERE/'SHA256SUMS').write_text(lines());print('SHA256SUMS',len(files()),'files',sha((HERE/'SHA256SUMS').read_bytes()));return 0
    if arguments==['check']:
        found=problems()
        if found:
            print('\n'.join(found));print('SEAL_BROKEN',len(found));return 1
        print('SEAL_OK',len(files()),'files',sha((HERE/'SHA256SUMS').read_bytes()));return 0
    print(__doc__);return 2

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
