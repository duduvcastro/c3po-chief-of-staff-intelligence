"""Mutation check of K4-E0 (k4_e0). Offline. Never touches the operation directory or the frozen core: every
mutant is applied to a private copy under <operation>/work/mut-<record name>/<mutant>/k4_e0, beside a link
to the sealed core, and the copy's own test files are run against it. (install_release's mutate.py with the tables
changed and two of its five lists kept: own and carried. The sweep, review and tools lists of install_release came
out of its review; no review of K4-E0 has happened yet.)

This is the core's mutation/mutate.py with three tables changed (SOURCE, CARRIES, TESTS) and the copy step adapted
to an operation directory, as CORE.md section 9 prescribes. A mutant is one literal replacement in the built source
(build/k4_e0.py: target 'op' for the operation's own part), in the generated dispatcher or in the launcher.
A mutant is KILLED only by a behavioural test: the tests named "static" (byte pins, the assembly) are deselected, so
a mutant cannot be killed merely because a hash changed. A run that exceeds the time limit is a kill. Zero survivors
and zero anchor errors are required of the list "own".

Two lists (HOSTOPS_MUTATION_LIST):
  own      (default; record MUTATION_RUN.json) the mutants of this operation: one per member of effects_of(), one per
           refusal of validate_plan and of the precheck, the constants, the order and the effects (mutants.py), and the
           rows of the core's list for the dispatcher and the launcher, applied to the files generated for this operation.
  carried  (record MUTATION_CARRIED.json) INFORMATION ONLY: the core's own rows for the parts this source carries
           (core, parents, files), applied to this source and run against this operation's tests. The parts are the
           sealed bytes and the core's suite kills every one of these rows; a survivor here says that this operation's
           tests do not reach that line, not that the line is unguarded. Survivors are recorded, not required to be zero.

usage: mutate.py check | run [name-prefix ...]   (python and worker count from HOSTOPS_MUTATION_PYTHON / _WORKERS;
       the record of a complete run goes to mutation/<HOSTOPS_MUTATION_RECORD>)
No path of the machine a run is made on enters a record: the copy is written as <copy>, any other path as <path>."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent.parent
CORE=HERE.parent/'core'
NAME=HERE.name
LIST=os.environ.get('HOSTOPS_MUTATION_LIST','own')
RECORD=os.path.basename(os.environ.get('HOSTOPS_MUTATION_RECORD',{'own':'MUTATION_RUN.json','carried':'MUTATION_CARRIED.json'}.get(LIST,'MUTATION_UNKNOWN.json')))
WORK=HERE.parent/(HERE.name+'.work')/('mut-'+RECORD)       # scratch OUTSIDE the sealed directory
PYTHON=os.environ.get('HOSTOPS_MUTATION_PYTHON','/usr/bin/python3')
WORKERS=int(os.environ.get('HOSTOPS_MUTATION_WORKERS','8'))
TIME_LIMIT=600
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME','')}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
SOURCE={'op':'build/k4_e0.py'}
CARRIES={'op':['op'],'core':['op'],'parents':['op'],'files':['op']}
# fastest and most specific first: the run stops at the first failing test
ORDER=['test_k4_e0.py','test_native.py','test_conformance.py']
ONCE=['test_conformance.py']          # what exercises the generated dispatcher and the launcher
TESTS={'op':ORDER,'core':ORDER,'parents':ORDER,'files':ORDER,'dispatcher':ONCE,'dispatcher_write':ONCE,'launcher':ONCE}
TOOLS=()
SUPPORT=['conftest.py','k4e0.py','native_child.py','native_support.py']

def files_of(target):
    if target in ('dispatcher','dispatcher_write'):return ['build/dispatch_once.py']
    if target=='launcher':return ['build/launcher_stdin.py']
    if target in TOOLS:return ['binding/%s.py'%target]
    return [SOURCE[name] for name in CARRIES[target]]

def core_list():
    """The mutants of the frozen core, read from its own files (never copied here)."""
    sys.path.insert(0,str(CORE/'mutation'))
    try:
        spec=importlib.util.spec_from_file_location('_hostops02_core_mutants',CORE/'mutation'/'mutants.py');module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module);return module
    finally:sys.path.remove(str(CORE/'mutation'))

sys.path.insert(0,str(Path(__file__).resolve().parent))
import mutants as own
_core=core_list()
MULTI={}                                  # name -> [(target, anchor, replacement), ...]: one mutant made of several replacements
if LIST=='own':
    MUTANTS=list(own.MUTANTS)+[row for row in _core.MUTANTS if row[1] in ('dispatcher','dispatcher_write','launcher') and row[0] not in own.CORE_ROWS_REPLACED]
    COMBOS=dict(own.COMBOS);REDUNDANT=dict(own.REDUNDANT)
elif LIST=='carried':
    MUTANTS=[row for row in _core.MUTANTS if row[1] in ('core','parents','files')];COMBOS={};REDUNDANT={}
else:raise SystemExit('HOSTOPS_MUTATION_LIST is own or carried')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

ELSEWHERE=re.compile(r'(?:/private)?/(?:Users|home|tmp|var/folders|var/tmp|root)/[^\s\'"]*')
def public(text,work):
    """A line of pytest output without any path of this machine."""
    if text is None:return None
    for prefix in sorted({str(work),os.path.realpath(str(work))},key=len,reverse=True):text=text.replace(prefix,'<copy>')
    return ELSEWHERE.sub('<path>',text)

def changes_of(name):
    if name in MULTI:return list(MULTI[name])
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
            count=(HERE/relative).read_text().count(old)
            if count!=1:errors.append('%s: anchor occurs %d times in %s'%(name,count,relative))
        if old==new:errors.append(name+': no change')
    for name,changes in MULTI.items():
        for target,old,new in changes:
            if target not in TESTS:
                errors.append('%s: unknown target %s'%(name,target));continue
            for relative in files_of(target):
                count=(HERE/relative).read_text().count(old)
                if count!=1:errors.append('%s: anchor occurs %d times in %s'%(name,count,relative))
            if old==new:errors.append(name+': no change')
    names=[mutant[0] for mutant in MUTANTS]+list(MULTI)
    if len(set(names))!=len(names):errors.append('duplicate mutant names: %s'%sorted({name for name in names if names.count(name)>1}))
    for name,members in COMBOS.items():
        for member in members:
            if member not in names:errors.append('%s: unknown member %s'%(name,member))
    for name in REDUNDANT:
        if name not in names:errors.append('%s: redundant mutant is not in the list'%name)
        if not any(name in members and len(members)>1 for members in COMBOS.values()):errors.append('%s: redundant mutant without a combined mutant'%name)
    for item in ORDER:
        if not (HERE/'tests'/item).is_file():errors.append('test file missing: '+item)
    if LIST=='own':errors+=own.coverage(HERE)
    return errors

def prepare(name):
    """<work>/<mutant>/k4_e0 is a copy of this directory; <work>/<mutant>/core is a link to the sealed core
    (the tests of the copy find the core's test modules beside it, as they do in place)."""
    work=WORK/name
    if work.exists():shutil.rmtree(work)
    work.mkdir(parents=True)
    shutil.copytree(HERE,work/NAME,ignore=shutil.ignore_patterns('mutation','work','review-*','__pycache__','*.pyc','.pytest_cache','_tmp'))
    os.symlink(str(CORE),str(work/'core'))
    return work

def run(name):
    started=time.time();changes=changes_of(name);work=prepare(name);copy=work/NAME;tests=[]
    try:
        for target,old,new in changes:
            for relative in files_of(target):
                path=copy/relative;text=path.read_text()
                if text.count(old)!=1:return {'mutant':name,'error':'ANCHOR_COUNT_%d in %s'%(text.count(old),relative)}
                path.write_text(text.replace(old,new))
            tests+=[item for item in TESTS[target] if item not in tests]
        tests=[item for item in ORDER if item in tests]
        try:
            for relative in set(relative for target,_,_ in changes for relative in files_of(target)):
                compile((copy/relative).read_text(),relative,'exec')
        except SyntaxError as error:return {'mutant':name,'error':'SYNTAX %s'%error}
        command=[PYTHON,'-B','-m','pytest','-p','no:cacheprovider','--basetemp',str(work/'_tmp'),'-q','-x','-k','not static',
                 '--tb=line']+[str(copy/'tests'/item) for item in tests]
        try:done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=ENV,cwd=str(copy),timeout=TIME_LIMIT)
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

def pins():
    """What a record was run against: every file of the operation that the tests read, and the seal of the core."""
    relatives=['op.py','spec.py','mutation/mutants.py']+sorted('build/'+path.name for path in (HERE/'build').iterdir() if path.is_file())
    relatives+=['tests/'+item for item in ORDER+SUPPORT]
    found={relative:sha(HERE/relative) for relative in relatives}
    found['<core>/CORE_SHA256SUMS']=sha(CORE/'CORE_SHA256SUMS');found['<core>/mutation/mutants.py']=sha(CORE/'mutation'/'mutants.py')
    found['<core>/mutation/mutants_ported.py']=sha(CORE/'mutation'/'mutants_ported.py');return found

def main():
    mode=sys.argv[1] if len(sys.argv)>1 else 'check'
    errors=check()
    if errors:
        print('\n'.join(errors));print('ANCHOR_ERRORS',len(errors));return 1
    if mode=='check':
        print('LIST',LIST,'MUTANTS',len(MUTANTS)+len(MULTI),'COMBOS',len(COMBOS),'ANCHORS_OK');return 0
    names=[mutant[0] for mutant in MUTANTS]+list(MULTI)+list(COMBOS)
    if len(sys.argv)>2:names=[name for name in names if any(name.startswith(prefix) for prefix in sys.argv[2:])]
    WORK.mkdir(parents=True,exist_ok=True);results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for result in pool.map(run,names):
            results.append(result);print(json.dumps(result),flush=True)
    alive=[row['mutant'] for row in results if not row.get('error') and not row['killed']]
    not_applicable=[]
    survivors=[name for name in alive if name not in REDUNDANT]
    redundant_survivors=[name for name in alive if name in REDUNDANT]
    redundant_killed=[row['mutant'] for row in results if row.get('killed') and row['mutant'] in REDUNDANT]
    failures=[row['mutant'] for row in results if row.get('error')]
    by_target={}
    for mutant in MUTANTS:by_target[mutant[1]]=by_target.get(mutant[1],0)+1
    for changes in MULTI.values():by_target[changes[0][0]]=by_target.get(changes[0][0],0)+1
    record={'python':subprocess.run([PYTHON,'-V'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.decode().strip(),'list':LIST,
            'required_zero_survivors':LIST=='own','pins':pins(),'by_target':by_target,
            'counts':{'single':len([name for name in names if name not in COMBOS]),'combined':len([name for name in names if name in COMBOS]),
            'killed':len([row for row in results if row.get('killed')]),'survivors':len(survivors),'errors':len(failures),
            'redundant_survivors':len(redundant_survivors)},
            'survivors':survivors,'errors':failures,'results':results,'complete_run':len(sys.argv)<=2,
            'redundant':{name:{'why':REDUNDANT[name],'combined_mutants':sorted(combo for combo,members in COMBOS.items() if name in members)}
                         for name in sorted(REDUNDANT) if name in names},
            'not_applicable_does_not_compile':not_applicable,'changes':None,
            'redundant_survivors':redundant_survivors,'redundant_killed_alone':redundant_killed}
    if len(sys.argv)<=2:(HERE/'mutation'/RECORD).write_text(json.dumps(record,indent=1,sort_keys=True)+'\n')
    print('MUTANTS',len(results));print('SURVIVORS',survivors);print('REDUNDANT_SURVIVORS',redundant_survivors);print('ERRORS',failures)
    return 1 if failures or (survivors and LIST=='own') else 0

if __name__=='__main__':raise SystemExit(main())
