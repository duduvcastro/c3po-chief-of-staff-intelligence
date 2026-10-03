"""Every seal this branch carries, verified by command. Reads and hashes; changes nothing except its own report.

  /usr/bin/python3 -I -B proof/seals.py        (from anywhere; it works on the directory above its own)

For the frozen core, for each of the four tier 0 operations (catalog_init, install_release, epoch_readback,
activate), for C3 (tls_probe) and for the token placement (token_from_env), in this order:
  - the seal file (CORE_SHA256SUMS or SHA256SUMS) has the SHA-256 that SEALS.expected.json records (written by
    command when this branch was made; it is what the verification of each operation named);
  - every file the seal lists is present with the listed hash, or is one of the files WITHHELD.json names for that
    directory with that same hash (a file that could not be made public; the seal file itself is unchanged);
  - no file is present that the seal does not list, except the seal file and what the Linux job writes;
  - for an operation: build/ is what the frozen core assembles (assemble.py --check: BUILD_EQUAL), ASSEMBLY.json
    names this core generation, and the payload hashes are the recorded ones;
  - the directory's own seal.py check, where it has one and nothing of it is withheld.
Then the files of proof/ against PROOF_SHA256SUMS, and the workflow file against proof/WORKFLOW.yml.txt.
Prints one line per check and writes proof/out/SEALS.json. Exit 0 only when every check holds; 3 when the only checks
that fail say a file is present that a seal does not list (every sealed byte is still the sealed one); 1 otherwise.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
FAMILY=os.path.dirname(HERE)
REPOSITORY=os.path.dirname(FAMILY)
WORKFLOW=os.path.join(REPOSITORY,'.github','workflows','hostops02-linux-root.yml')
ORDER=('core','catalog_init','install_release','epoch_readback','activate','tls_probe','token_from_env')
# what the Linux job writes into the sealed directories while it runs
OUTPUT=re.compile(r'linux_root/(TESTS\..*\.xml|SHAPES\..*\.json|CATALOG_SHAPE\..*\.json)')
SKIPPED_PARTS=('__pycache__','.pytest_cache','_tmp')
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
UNLISTED='no file is present that the seal does not list'

def sha(path):
    with open(path,'rb') as handle:return hashlib.sha256(handle.read()).hexdigest()
def load(name):
    with open(os.path.join(HERE,name),'rb') as handle:return json.loads(handle.read())
def listing(path):
    """{name: digest} of a `shasum -a 256` file; None when a line is not of that form or a name is listed twice."""
    out={}
    with open(path,encoding='ascii') as handle:
        for line in handle.read().splitlines():
            digest,separator,name=line.partition('  ')
            if not (re.fullmatch('[0-9a-f]{64}',digest) and separator and name and name not in out and not name.startswith('/') and '..' not in name.split('/')):return None
            out[name]=digest
    return out
def present(directory,seal_name):
    found=[]
    for folder,names,files in os.walk(directory):
        names[:]=[name for name in names if name not in SKIPPED_PARTS]
        for name in files:
            relative=os.path.relpath(os.path.join(folder,name),directory).replace(os.sep,'/')
            if relative!=seal_name and not name.endswith('.pyc') and not OUTPUT.fullmatch(relative):found.append(relative)
    return sorted(found)
def command(arguments,cwd):
    done=subprocess.run(arguments,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=ENV,cwd=cwd,timeout=300)
    return done.returncode,done.stdout.decode('utf-8','replace').strip()

def directory_checks(name,expected,withheld):
    """[(check, True or False, detail)] of one sealed directory."""
    directory=os.path.join(FAMILY,name);seal_name=expected['seal_file'];seal=os.path.join(directory,seal_name);rows=[]
    def check(label,ok,detail=''):rows.append((name+': '+label,bool(ok),detail))
    if not os.path.isfile(seal):
        check('the seal file is present',False,seal_name);return rows
    check('the seal file is the recorded one',sha(seal)==expected['seal_sha256'],sha(seal))
    listed=listing(seal)
    if listed is None:
        check('the seal file is a list of hashes and names',False);return rows
    check('the seal lists the recorded number of files',len(listed)==expected['files'],str(len(listed)))
    absent=sorted(item for item in listed if not os.path.isfile(os.path.join(directory,item)))
    check('every listed file is present, or is withheld with the listed hash',
          sorted(withheld)==absent and all(withheld[item]['sha256']==listed[item] for item in absent),'withheld: '+(', '.join(absent) or 'none'))
    differing=sorted(item for item in listed if item not in absent and sha(os.path.join(directory,item))!=listed[item])
    check('every present file has the listed hash',not differing,', '.join(differing[:6]))
    extra=sorted(item for item in present(directory,seal_name) if item not in listed)
    check(UNLISTED,not extra,', '.join(extra[:6]))
    if name=='core':
        code,out=command(['/usr/bin/python3','-B','assemble.py','--core'],directory)
        check('the core generation is the recorded one',code==0 and out==expected['generation_sha256']==sha(os.path.join(directory,'assemble.py')),out[:80])
    else:
        code,out=command(['/usr/bin/python3','-B',os.path.join(FAMILY,'core','assemble.py'),'--check',directory],directory)
        check('build/ is what the frozen core assembles',code==0 and out=='BUILD_EQUAL',out[:120])
        with open(os.path.join(directory,'build','ASSEMBLY.json'),'rb') as handle:assembly=json.loads(handle.read())
        source=os.path.join(directory,'build',assembly['module']+'.py');final=os.path.join(directory,'build','FINAL_PAYLOAD.UNBOUND.py')
        check('the assembly names this core generation',assembly['core_sha256']==sha(os.path.join(FAMILY,'core','assemble.py')))
        check('the payload source is the recorded one',sha(source)==assembly['source_sha256']==expected['payload_source_sha256'],sha(source))
        check('the unbound final payload is the recorded one',sha(final)==assembly['final_payload_sha256']==expected['final_payload_unbound_sha256'],sha(final))
    if os.path.isfile(os.path.join(directory,'seal.py')) and not withheld:
        code,out=command(['/usr/bin/python3','-B','seal.py','check'],directory)
        check('its own seal.py check',code==0 and 'SEAL_OK' in out and 'SEAL_BROKEN' not in out,out.splitlines()[-1][:120] if out else '')
    return rows

def proof_checks():
    rows=[];seal=os.path.join(HERE,'PROOF_SHA256SUMS')
    def check(label,ok,detail=''):rows.append(('proof: '+label,bool(ok),detail))
    listed=listing(seal) if os.path.isfile(seal) else None
    if listed is None:
        check('PROOF_SHA256SUMS is present and a list of hashes and names',False);return rows
    differing=sorted(item for item in listed if not os.path.isfile(os.path.join(HERE,item)) or sha(os.path.join(HERE,item))!=listed[item])
    check('every file of proof/ has the listed hash',not differing,', '.join(differing[:6]))
    found=sorted(item for item in present(HERE,'PROOF_SHA256SUMS') if not item.startswith('out/'))
    check('every file of proof/ is listed, and nothing else',found==sorted(listed),', '.join(sorted(set(found)^set(listed))[:6]))
    check('the workflow file is proof/WORKFLOW.yml.txt, byte for byte',os.path.isfile(WORKFLOW) and sha(WORKFLOW)==sha(os.path.join(HERE,'WORKFLOW.yml.txt')),
          sha(WORKFLOW) if os.path.isfile(WORKFLOW) else 'absent')
    others=sorted(name for name in os.listdir(os.path.dirname(WORKFLOW)) if name!=os.path.basename(WORKFLOW)) if os.path.isdir(os.path.dirname(WORKFLOW)) else ['no workflow directory']
    check('the branch carries no other workflow',not others,', '.join(others[:6]))
    return rows

def main():
    expected=load('SEALS.expected.json');withheld=load('WITHHELD.json');rows=[]
    for name in ORDER:rows+=directory_checks(name,expected[name],withheld.get(name,{}))
    rows+=proof_checks()
    for label,ok,detail in rows:print('%s  %s%s'%('ok  ' if ok else 'FAIL',label,' ['+detail+']' if detail else ''))
    result={'schema':'HOSTOPS02_PROOF_SEALS_V1','seals':{name:{'seal_sha256':sha(os.path.join(FAMILY,name,expected[name]['seal_file'])),'files':expected[name]['files'],
                                                               'withheld':sorted(withheld.get(name,{}))} for name in ORDER if os.path.isfile(os.path.join(FAMILY,name,expected[name]['seal_file']))},
            'proof_seal_sha256':sha(os.path.join(HERE,'PROOF_SHA256SUMS')) if os.path.isfile(os.path.join(HERE,'PROOF_SHA256SUMS')) else None,
            'workflow_sha256':sha(WORKFLOW) if os.path.isfile(WORKFLOW) else None,
            'checks':[{'check':label,'holds':ok} for label,ok,_ in rows],'every_check_holds':all(ok for _,ok,_ in rows)}
    os.makedirs(os.path.join(HERE,'out'),exist_ok=True)
    with open(os.path.join(HERE,'out','SEALS.json'),'w',encoding='ascii') as handle:handle.write(json.dumps(result,indent=1,sort_keys=True)+'\n')
    broken=[label for label,ok,_ in rows if not ok];only_unlisted=bool(broken) and all(label.endswith(UNLISTED) for label in broken)
    print('SEALS_OK' if not broken else 'SEALS_HOLD_BUT_UNLISTED_FILES_ARE_PRESENT' if only_unlisted else 'SEALS_BROKEN',len(rows),'checks')
    return 0 if not broken else 3 if only_unlisted else 1

if __name__=='__main__':raise SystemExit(main())
