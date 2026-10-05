"""Mutation check of K6a (activate). The core's mutation/mutate.py with three tables changed (SOURCE, CARRIES, TESTS),
the private copy made of THIS operation directory, and the frozen core left where it is. Offline. Never touches the
operation or the core: every mutant is applied to a private copy of this directory under
<hostops02>/work/mut-activate-<record name>/ and the copy's own test files are run against it, with the core's test
helpers taken from the sealed core (HOSTOPS02_TEST_CORE_TESTS).

A mutant is one literal replacement in the operation's own part as it stands in the built source (target 'op'), in a
shared part as it stands there (the core's own list, target named after the part), or in the generated dispatcher
or launcher.
A mutant is KILLED only by a behavioural test: the tests named "static" (byte pins, the seal, syntax-tree
allow-lists) are deselected, so a mutant cannot be killed merely because a hash changed. A run that does not end
within the time limit is a kill as well (a mutant that makes a wait endless is found by the wait). Zero survivors and
zero anchor errors are required.

A mutant listed in REDUNDANT (mutants.py) removes a check that another check implies: alone it cannot change any
result. It is run alone and recorded under redundant_survivors, never counted as killed and never as a survivor of
the list; check requires it to be a member of a combined mutant, and that combined mutant must die like any other.

No path of the machine a run is made on enters a record or a log: the location of the private copy is written as
<copy>, any other absolute path of the workstation as <path>.

usage: mutate.py check | run [name-prefix ...]   (python and worker count from HOSTOPS_MUTATION_PYTHON / _WORKERS;
       the record of a complete run goes to mutation/<HOSTOPS_MUTATION_RECORD>, default MUTATION_RUN.json)

An operation built on the core reuses this file by copying it next to its own mutants.py and changing three tables:
SOURCE (its build/<module>.py), CARRIES (which parts it carries, plus its own 'op') and TESTS (its test files).
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

CORE=Path(__file__).resolve().parent.parent                      # the operation directory (the name is the core harness's)
FROZEN=Path(os.environ.get('HOSTOPS02_CORE_DIRECTORY') or CORE.parent/'core').resolve()      # the sealed core, read only
RECORD=os.path.basename(os.environ.get('HOSTOPS_MUTATION_RECORD','MUTATION_RUN.json'))
WORK=CORE.parent/'work'/('mut-activate-'+RECORD)
PYTHON=os.environ.get('HOSTOPS_MUTATION_PYTHON','/usr/bin/python3')
WORKERS=int(os.environ.get('HOSTOPS_MUTATION_WORKERS','8'))
TIME_LIMIT=900          # the workstation is shared: a survivor must never be taken for a kill because its run was slow
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME','')}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
ENV['HOSTOPS02_TEST_CORE_TESTS']=str(FROZEN/'tests')
SOURCE={'op':'build/activate.py'}
PARTS=('core','runner','docker','parents','files','lock')
CARRIES={name:['op'] for name in ('op',)+PARTS}
# fastest and most specific first: the run stops at the first failing test
ORDER=['test_activate.py','test_plan.py','test_precheck.py','test_effects.py','test_budget.py','test_crash_points.py','test_native_calls.py','test_conformance.py']
TESTS={name:list(ORDER) for name in ('op',)+PARTS}
TESTS.update({'dispatcher':['test_conformance.py'],'launcher':['test_conformance.py']})

def files_of(target):
    if target=='dispatcher':return ['build/dispatch_once.py']
    if target=='launcher':return ['build/launcher_stdin.py']
    return [SOURCE[name] for name in CARRIES[target]]

from mutants import MUTANTS,COMBOS,REDUNDANT,ORIGIN

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
    """Every anchor must occur exactly once in every file it is applied to."""
    errors=[]
    for name,target,old,new in MUTANTS:
        if target not in TESTS:
            errors.append('%s: unknown target %s'%(name,target));continue
        for relative in files_of(target):
            count=(CORE/relative).read_text().count(old)
            if count!=1:errors.append('%s: anchor occurs %d times in %s'%(name,count,relative))
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
        if not (CORE/'tests'/item).is_file():errors.append('test file missing: '+item)
    return errors

def prepare(name):
    work=WORK/name
    if work.exists():shutil.rmtree(work)
    shutil.copytree(CORE,work,ignore=shutil.ignore_patterns('mutation','linux_root','__pycache__','*.pyc','.pytest_cache','_tmp'))
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
    finally:shutil.rmtree(work,ignore_errors=True)

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
    relatives=sorted({relative for target in TESTS for relative in files_of(target)})
    pins={relative:sha(CORE/relative) for relative in relatives}
    pins.update({'tests/'+item:sha(CORE/'tests'/item) for item in ORDER+['k6a.py','native_engine.py','native_child.py','conftest.py']})
    pins.update({'op.py':sha(CORE/'op.py'),'spec.py':sha(CORE/'spec.py'),'mutation/mutants.py':sha(CORE/'mutation'/'mutants.py'),'mutation/mutate.py':sha(Path(__file__))})
    pins['core/CORE_SHA256SUMS']=sha(FROZEN/'CORE_SHA256SUMS');pins['core/assemble.py']=sha(FROZEN/'assemble.py')
    record={'python':subprocess.run([PYTHON,'-V'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.decode().strip(),
            'pins':pins,'origin':{origin:len([name for name in names if ORIGIN.get(name)==origin]) for origin in sorted(set(ORIGIN.values()))},
            'survivors_by_origin':{origin:[name for name in survivors if ORIGIN.get(name)==origin] for origin in sorted(set(ORIGIN.values()))},'counts':{'single':len([name for name in names if name not in COMBOS]),'combined':len([name for name in names if name in COMBOS]),
            'killed':len([row for row in results if row.get('killed')]),'survivors':len(survivors),'errors':len(failures),
            'redundant_survivors':len(redundant_survivors)},
            'survivors':survivors,'errors':failures,'results':results,'complete_run':len(sys.argv)<=2,'prefixes':sys.argv[2:],
            'redundant':{name:{'why':REDUNDANT[name],'combined_mutants':sorted(combo for combo,members in COMBOS.items() if name in members)}
                         for name in sorted(REDUNDANT) if name in names},
            'redundant_survivors':redundant_survivors,'redundant_killed_alone':redundant_killed}
    if len(sys.argv)<=2 or os.environ.get('HOSTOPS_MUTATION_WRITE')=='yes':(CORE/'mutation'/RECORD).write_text(json.dumps(record,indent=1,sort_keys=True)+'\n')
    print('MUTANTS',len(results));print('SURVIVORS',survivors);print('REDUNDANT_SURVIVORS',redundant_survivors);print('ERRORS',failures)
    return 1 if survivors or failures else 0

if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent));raise SystemExit(main())
