"""Mutation check of K5 (supervisor activation, B11). Offline. Copied from K2a's mutate.py with the tables below changed. The core's mutation/mutate.py with three tables changed
(SOURCE, CARRIES, TESTS), as CORE.md section 9 prescribes, and with the operation directory in the place of the core:
every mutant is applied to a private copy of THIS operation directory under <hostops02>/work/mut-k2a-<record name>/ and
the copy's own test files are run against it. The frozen core is never copied and never touched: the copy's tests find
it above them (tests/conftest.py).

A mutant is one literal replacement in the operation's own part as it stands in the built source
(build/catalog_init.py; the anchor must occur exactly once in the whole source). A mutant is KILLED only by a
behavioural test: the tests named "static" (byte pins, text pins against the release) are deselected, so a mutant
cannot be killed merely because a pinned text changed. A run that does not end within the time limit is a kill as
well. Zero survivors and zero anchor errors are required. The mutants of the carried parts are the core's own list
(core/mutation), run against the core's demonstration operations; they are not repeated here.

No path of the machine a run is made on enters a record or a log.

usage: mutate.py check | run [name-prefix ...]   (python and worker count from HOSTOPS_MUTATION_PYTHON / _WORKERS;
       the record of a complete run goes to mutation/<HOSTOPS_MUTATION_RECORD>, default MUTATION_RUN.json)
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

OPERATION=Path(__file__).resolve().parent.parent
CORE=OPERATION.parent/'core'
RECORD=os.path.basename(os.environ.get('HOSTOPS_MUTATION_RECORD','MUTATION_RUN.json'))
WORK=OPERATION.parent/'work'/('mut-k5-'+RECORD)
PYTHON=os.environ.get('HOSTOPS_MUTATION_PYTHON','/usr/bin/python3')
WORKERS=int(os.environ.get('HOSTOPS_MUTATION_WORKERS','8'))
TIME_LIMIT=240
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME',''),'HOSTOPS02_TEST_CORE':str(CORE)}
if (OPERATION/'work'/'release').is_dir():ENV['HOSTOPS02_TEST_RELEASE_TREE']=str(OPERATION/'work'/'release')       # the copy does not carry work/
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
SOURCE={'op':'build/supervisor_activate.py'}
CARRIES={'op':['op']}
# fastest and most specific first: the run stops at the first failing test
ORDER=['test_k5.py','test_native.py','test_conformance.py']
TESTS={'op':ORDER}

def files_of(target):return [SOURCE[name] for name in CARRIES[target]]

from mutants import MUTANTS,COMBOS,REDUNDANT

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

ELSEWHERE=re.compile(r'(?:/private)?/(?:Users|home|tmp|var/folders|var/tmp|root)/[^\s\'"]*')
def public(text,work):
    """A line of pytest output without any path of this machine."""
    if text is None:return None
    for prefix in sorted({str(work),os.path.realpath(str(work))},key=len,reverse=True):text=text.replace(prefix,'<copy>')
    return ELSEWHERE.sub('<path>',text)

def changes_of(name):
    if name in COMBOS:
        by={mutant[0]:mutant for mutant in MUTANTS};return [by[member][1:4] for member in COMBOS[name]]
    return [mutant[1:4] for mutant in MUTANTS if mutant[0]==name]

def check():
    """Every anchor must occur exactly once in the built source, inside the operation's own part."""
    errors=[]
    built=(OPERATION/SOURCE['op']).read_text();own=(OPERATION/'op.py').read_text()
    if built.count(own.rstrip('\n'))!=1:errors.append('build/ does not carry op.py as it is: assemble first')
    for name,target,old,new in MUTANTS:
        if target not in TESTS:
            errors.append('%s: unknown target %s'%(name,target));continue
        for relative in files_of(target):
            count=(OPERATION/relative).read_text().count(old)
            if count!=1:errors.append('%s: anchor occurs %d times in %s'%(name,count,relative))
        if own.count(old)!=1:errors.append('%s: anchor is not a text of the operation part'%name)
        if old==new:errors.append(name+': no change')
    names=[mutant[0] for mutant in MUTANTS]
    if len(set(names))!=len(names):errors.append('duplicate mutant names: %s'%sorted({name for name in names if names.count(name)>1}))
    for name,members in COMBOS.items():
        for member in members:
            if member not in names:errors.append('%s: unknown member %s'%(name,member))
    for name in REDUNDANT:
        if name not in names:errors.append('%s: redundant mutant is not in the list'%name)
        if not any(name in members and len(members)>1 for members in COMBOS.values()):errors.append('%s: redundant mutant without a combined mutant'%name)
    for item in ORDER:
        if not (OPERATION/'tests'/item).is_file():errors.append('test file missing: '+item)
    return errors

def prepare(name):
    work=WORK/name/OPERATION.name
    if work.parent.exists():shutil.rmtree(work.parent)
    shutil.copytree(OPERATION,work,ignore=shutil.ignore_patterns('mutation','work','linux_root','__pycache__','*.pyc','.pytest_cache','_tmp'))
    return work

def run(name):
    started=time.time();changes=changes_of(name);work=prepare(name);tests=[]
    try:
        for target,old,new in changes:
            for relative in files_of(target):
                path=work/relative;text=path.read_text()
                if text.count(old)!=1:return {'mutant':name,'error':'ANCHOR_COUNT_%d in %s'%(text.count(old),relative)}
                path.write_text(text.replace(old,new))
            tests+=[item for item in TESTS[target] if item not in tests]
        tests=[item for item in ORDER if item in tests]
        try:
            for relative in set(relative for target,_,_ in changes for relative in files_of(target)):
                compile((work/relative).read_text(),relative,'exec')
        except SyntaxError as error:return {'mutant':name,'error':'SYNTAX %s'%error}
        command=[PYTHON,'-B','-m','pytest','-p','no:cacheprovider','--basetemp',str(work/'_tmp'),'-q','-x','-k','not static',
                 '--tb=line']+[str(work/'tests'/item) for item in tests]
        try:done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=ENV,cwd=str(work),timeout=TIME_LIMIT)
        except subprocess.TimeoutExpired:
            return {'mutant':name,'returncode':None,'killed':True,'summary':'TIME_LIMIT_%d_SECONDS'%TIME_LIMIT,'first_failure':None,'tests':tests,
                    'seconds':round(time.time()-started,1)}
        lines=done.stdout.decode(errors='replace').strip().splitlines()
        failed=[line for line in lines if line.startswith('FAILED ') or ' Error' in line or 'Error:' in line][:1]
        result={'mutant':name,'returncode':done.returncode,'killed':done.returncode==1,'summary':public(lines[-1],work) if lines else '',
                'first_failure':public(failed[0],work)[:300] if failed else None,'tests':tests,'seconds':round(time.time()-started,1)}
        if name in REDUNDANT:result['redundant']=True
        if done.returncode not in (0,1):result['error']='PYTEST_RETURNCODE_%d'%done.returncode
        return result
    finally:shutil.rmtree(work.parent,ignore_errors=True)

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'check'
    errors=check()
    if errors:
        print('\n'.join(errors));print('ANCHOR_ERRORS',len(errors));return 1
    if mode=='check':
        print('MUTANTS',len(MUTANTS),'COMBOS',len(COMBOS),'ANCHORS_OK');return 0
    names=[mutant[0] for mutant in MUTANTS]+list(COMBOS)
    if len(sys.argv)>2:names=[name for name in names if any(name.startswith(prefix) for prefix in sys.argv[2:])]
    WORK.mkdir(parents=True,exist_ok=True);results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for result in pool.map(run,names):
            results.append(result);print(json.dumps(result),flush=True)
    alive=[row['mutant'] for row in results if not row.get('error') and not row['killed']]
    survivors=[name for name in alive if name not in REDUNDANT]
    redundant_survivors=[name for name in alive if name in REDUNDANT]
    redundant_killed=[row['mutant'] for row in results if row.get('killed') and row['mutant'] in REDUNDANT]
    failures=[row['mutant'] for row in results if row.get('error')]
    pins={relative:sha(OPERATION/relative) for relative in ['op.py','spec.py']+sorted('build/'+path.name for path in (OPERATION/'build').iterdir() if path.is_file())}
    pins.update({'tests/'+path.name:sha(path) for path in sorted((OPERATION/'tests').iterdir()) if path.suffix=='.py'})
    pins['mutation/mutants.py']=sha(OPERATION/'mutation'/'mutants.py');pins['mutation/mutate.py']=sha(OPERATION/'mutation'/'mutate.py')
    record={'python':subprocess.run([PYTHON,'-V'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.decode().strip(),
            'operation_sha256':pins,'core_seal_sha256':sha(CORE/'CORE_SHA256SUMS'),'core_generation_sha256':sha(CORE/'assemble.py'),
            'release_tree_at_hand':'HOSTOPS02_TEST_RELEASE_TREE' in ENV,
            'counts':{'single':len([name for name in names if name not in COMBOS]),'combined':len([name for name in names if name in COMBOS]),
            'killed':len([row for row in results if row.get('killed')]),'survivors':len(survivors),'errors':len(failures),
            'redundant_survivors':len(redundant_survivors)},
            'survivors':survivors,'errors':failures,'results':results,'complete_run':len(sys.argv)<=2,
            'redundant':{name:{'why':REDUNDANT[name],'combined_mutants':sorted(combo for combo,members in COMBOS.items() if name in members)}
                         for name in sorted(REDUNDANT) if name in names},
            'redundant_survivors':redundant_survivors,'redundant_killed_alone':redundant_killed}
    if len(sys.argv)<=2:(OPERATION/'mutation'/RECORD).write_text(json.dumps(record,indent=1,sort_keys=True)+'\n')
    print('MUTANTS',len(results));print('SURVIVORS',survivors);print('REDUNDANT_SURVIVORS',redundant_survivors);print('ERRORS',failures)
    return 1 if survivors or failures else 0

if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent));raise SystemExit(main())
