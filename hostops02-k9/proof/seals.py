"""Every seal the K9 proof branch carries, verified by command. Reads and hashes; changes nothing but its own report.

  /usr/bin/python3 -I -B proof/seals.py [--after] [--out <file>]      (from anywhere: it works on the directory above its own)

proof/UNITS.json (written by stage_branch.sh when the branch was made) names every sealed directory copied into
hostops02-k9/, its seal file (SHA256SUMS or CORE_SHA256SUMS), the SHA-256 of that seal file, the files WITHHELD from
publication (each with its sealed hash and why), and the links between the directories. For each directory:
  - the seal file has the recorded SHA-256;
  - every file it lists is present with the listed hash, or is withheld (then it must be ABSENT);
  - no file is present that the seal does not list. Before the run (default) nothing else is allowed; with --after,
    what the Linux job writes is allowed and listed: linux_root/TESTS.*.xml, linux_root/SHAPES*.json, tests/.work/,
    __pycache__/ and .pytest_cache/;
  - before the run only, and only where nothing of the directory is withheld: the directory's own `seal.py check`
    (the build is the assembly of its core, the core is the sealed one, the mutation records hold), exit 0;
then every link is the recorded one, the files of proof/ hold PROOF_SHA256SUMS, and the workflow file is
proof/WORKFLOW.yml.txt byte for byte. Exit 0 only when every check holds; 1 otherwise. Writes the checks as JSON to
proof/out/SEALS[.after].json (or --out).
"""
import fnmatch
import hashlib
import json
import os
import subprocess
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)                                   # hostops02-k9/
REPOSITORY=os.path.dirname(ROOT)
WORKFLOW=os.path.join(REPOSITORY,'.github','workflows','hostops02-k9-proof.yml')
SEAL_FILES=('SHA256SUMS','CORE_SHA256SUMS')
OUTPUT_PATTERNS=('linux_root/TESTS.*.xml','linux_root/SHAPES*.json')
OUTPUT_DIRECTORIES=('__pycache__','.pytest_cache')
OUTPUT_PREFIXES=('tests/.work/',)

def sha_file(path):
    digest=hashlib.sha256()
    with open(path,'rb') as handle:
        for block in iter(lambda:handle.read(1<<20),b''):digest.update(block)
    return digest.hexdigest()

def listing(path):
    out={}
    with open(path,'r',encoding='utf-8') as handle:
        for line in handle.read().splitlines():
            if not line.strip():continue
            digest,separator,name=line.partition('  ')
            if not separator or len(digest)!=64:raise ValueError('a line of %s is not "<sha256>  <path>"'%os.path.basename(path))
            out[name]=digest
    return out

def present(directory):
    """Every regular file under directory, relative, links not followed (a link inside a unit is reported)."""
    files=[];links=[]
    for folder,names,found in os.walk(directory):
        for name in list(names):
            if os.path.islink(os.path.join(folder,name)):links.append(os.path.relpath(os.path.join(folder,name),directory));names.remove(name)
        for name in found:
            path=os.path.join(folder,name);relative=os.path.relpath(path,directory)
            (links if os.path.islink(path) else files).append(relative)
    return sorted(files),sorted(links)

def is_output(relative):
    parts=relative.split('/')
    if any(part in OUTPUT_DIRECTORIES for part in parts) or relative.endswith('.pyc'):return True
    if any(relative.startswith(prefix) for prefix in OUTPUT_PREFIXES):return True
    return any(fnmatch.fnmatchcase(relative,pattern) for pattern in OUTPUT_PATTERNS)

def check_unit(unit,after):
    checks=[];directory=os.path.join(ROOT,unit['dest'])
    def add(name,ok,detail=None):checks.append({'unit':unit['dest'],'check':name,'ok':bool(ok),'detail':detail})
    seal=os.path.join(directory,unit['seal_file'])
    if not os.path.isfile(seal):
        add('seal file present',False,unit['seal_file']);return checks
    add('seal file has the recorded sha256',sha_file(seal)==unit['seal_sha256'],sha_file(seal))
    try:listed=listing(seal)
    except ValueError as error:
        add('seal file readable',False,str(error));return checks
    withheld=unit.get('withheld',{})
    add('withheld files are listed by the seal with the recorded hash',all(listed.get(name)==row['sha256'] for name,row in withheld.items()),sorted(withheld))
    missing=[];differ=[];shown=[]
    for name,digest in sorted(listed.items()):
        path=os.path.join(directory,name)
        if name in withheld:
            if os.path.lexists(path):shown.append(name)
            continue
        if not os.path.isfile(path) or os.path.islink(path):missing.append(name)
        elif sha_file(path)!=digest:differ.append(name)
    add('every listed file present with its hash (%d listed, %d withheld)'%(len(listed),len(withheld)),not missing and not differ,{'missing':missing,'hash_differs':differ})
    add('no withheld file is present',not shown,shown)
    files,links=present(directory)
    unlisted=[name for name in files if name not in listed and name!=unit['seal_file']]
    outputs=[name for name in unlisted if is_output(name)]
    stray=[name for name in unlisted if not is_output(name)] if after else unlisted
    add('no file the seal does not list'+(' (outputs of the job allowed)' if after else ''),not stray,{'unlisted':stray,'job_outputs':outputs if after else []})
    add('no link inside the directory',not links,links)
    if not after and unit.get('seal_py') and not withheld and os.path.isfile(os.path.join(directory,'seal.py')):
        env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME','/nonexistent'),'LC_ALL':'C.UTF-8'}
        try:
            done=subprocess.run(['/usr/bin/python3','-B','seal.py','check'],cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,timeout=600)
            text=done.stdout.decode('utf-8','replace').strip().splitlines()
            add('its own seal.py check',done.returncode==0,(text[-1] if text else '')[:200])
        except subprocess.TimeoutExpired:
            add('its own seal.py check',False,'TIMEOUT 600 s')
    elif not after and unit.get('seal_py'):
        add('its own seal.py check',True,'NOT_RUN: a file of this directory is withheld (the check needs every sealed file)')
    return checks

def main(arguments):
    after='--after' in arguments
    out=None
    if '--out' in arguments:out=arguments[arguments.index('--out')+1]
    with open(os.path.join(HERE,'UNITS.json'),'rb') as handle:units=json.load(handle)
    checks=[]
    for unit in units['units']:checks+=check_unit(unit,after)
    for link in units['links']:
        path=os.path.join(ROOT,link['path'])
        target=os.readlink(path) if os.path.islink(path) else None
        resolved=os.path.realpath(path)
        checks.append({'unit':link['path'],'check':'link to %s'%link['target'],'ok':target==link['target'] and resolved.startswith(ROOT+os.sep) and os.path.isdir(resolved),
                       'detail':target})
    proof=listing(os.path.join(HERE,'PROOF_SHA256SUMS'))
    files,links=present(HERE)
    files=[name for name in files if not name.startswith('out/') and name!='PROOF_SHA256SUMS' and not is_output(name)]
    checks.append({'unit':'proof','check':'PROOF_SHA256SUMS holds and lists every file of proof/','ok':sorted(proof)==sorted(files) and not links
                   and all(sha_file(os.path.join(HERE,name))==digest for name,digest in proof.items()),'detail':{'listed':len(proof),'present':len(files)}})
    workflow_ok=os.path.isfile(WORKFLOW) and sha_file(WORKFLOW)==sha_file(os.path.join(HERE,'WORKFLOW.yml.txt'))
    checks.append({'unit':'workflow','check':'.github/workflows/hostops02-k9-proof.yml is proof/WORKFLOW.yml.txt','ok':workflow_ok,'detail':sha_file(WORKFLOW) if os.path.isfile(WORKFLOW) else None})
    others=sorted(name for name in os.listdir(os.path.dirname(WORKFLOW)) if name!=os.path.basename(WORKFLOW)) if os.path.isdir(os.path.dirname(WORKFLOW)) else []
    checks.append({'unit':'workflow','check':'no other workflow on the branch','ok':not others,'detail':others})
    for row in checks:
        print('%s %s: %s%s'%('OK  ' if row['ok'] else 'FAIL',row['unit'],row['check'],'' if row['ok'] else '  '+json.dumps(row['detail'],sort_keys=True)[:400]))
    failed=[row for row in checks if not row['ok']]
    result={'schema':'HOSTOPS02_K9_PROOF_SEALS_V1','mode':'after' if after else 'before','units':len(units['units']),'checks':checks,'failed':len(failed),
            'seal_sha256':{unit['dest']:unit['seal_sha256'] for unit in units['units']}}
    target=out or os.path.join(HERE,'out','SEALS.after.json' if after else 'SEALS.json')
    os.makedirs(os.path.dirname(target),exist_ok=True)
    with open(target,'w',encoding='utf-8') as handle:handle.write(json.dumps(result,indent=1,sort_keys=True)+'\n')
    print('SEALS_%s units %d checks %d failed %d'%('OK' if not failed else 'BROKEN',len(units['units']),len(checks),len(failed)))
    return 0 if not failed else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
