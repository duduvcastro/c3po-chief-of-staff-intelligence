"""Mutation check of the HOSTOPS01 candidate. Offline. Never touches the candidate: every mutant is applied to a
private copy under <candidate>/../notes/mut-<record name>/ and the copy's own test files are run against it.

A mutant is one literal replacement in one shared part (applied to every assembled source that carries the part),
in one operation's own part, in the four dispatchers (or the two of the write operations) or in the four launchers.
A mutant is KILLED only by a behavioural test: the tests named "static" (byte pins, syntax-tree allow-lists) are
deselected, so a mutant cannot be killed merely because a hash changed. Zero survivors and zero anchor errors are
required. check also requires one mutant per member of every operation's effects (what the signed GO shows).

A mutant listed in REDUNDANT (mutants.py) removes a check that another check implies: alone it cannot change any
result. It is run alone and recorded under redundant_survivors, never counted as killed and never as a survivor of
the list; check requires it to be a member of a combined mutant, and that combined mutant must die like any other.
A redundant mutant that does die alone is recorded under redundant_killed_alone (the entry in REDUNDANT is then stale).

No path of the machine a run is made on enters a record or a log: the location of the private copy is written as
<copy>, any other absolute path of the workstation as <path>.

usage: mutate.py check | run [name-prefix ...]   (python and worker count from HOSTOPS_MUTATION_PYTHON / _WORKERS;
       the record of a complete run goes to mutation/<HOSTOPS_MUTATION_RECORD>, default MUTATION_RUN.json;
       variables named HOSTOPS_TEST_* are handed to the tests, see tests/test_family.py)
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

CAND=Path(__file__).resolve().parent.parent
WORK=CAND.parent/'notes'/('mut-'+os.path.basename(os.environ.get('HOSTOPS_MUTATION_RECORD','MUTATION_RUN.json')))
PYTHON=os.environ.get('HOSTOPS_MUTATION_PYTHON','/usr/bin/python3')
WORKERS=int(os.environ.get('HOSTOPS_MUTATION_WORKERS','6'))
RECORD=os.path.basename(os.environ.get('HOSTOPS_MUTATION_RECORD','MUTATION_RUN.json'))
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME','')}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS_TEST_')})
SOURCE={'provision':'provision/provision_dirs.py','install_units':'install_units/install_units.py',
        'readback':'readback/readback_readonly.py','precheck':'precheck/precheck_readonly.py'}
CARRIES={'core':['provision','install_units','readback','precheck'],'runner':['provision','readback','precheck'],
         'layout':['provision','precheck'],'listing':['provision','precheck'],'scan':['install_units','readback','precheck'],
         'render':['install_units','readback'],'op_provision':['provision'],'op_install_units':['install_units'],
         'op_readback':['readback'],'op_precheck':['precheck']}
ALL=['test_family.py','test_render.py','test_provision.py','test_install_units.py','test_readback.py','test_precheck.py','test_native.py']
TESTS={'core':ALL,'runner':['test_provision.py','test_readback.py','test_precheck.py','test_native.py','test_family.py'],
       'layout':['test_provision.py','test_precheck.py','test_native.py','test_family.py'],
       'listing':['test_provision.py','test_precheck.py'],'scan':['test_install_units.py','test_readback.py','test_precheck.py'],
       'render':['test_render.py','test_install_units.py','test_readback.py'],
       'op_provision':['test_provision.py','test_native.py','test_precheck.py','test_family.py'],
       'op_install_units':['test_install_units.py','test_native.py','test_precheck.py','test_family.py'],
       'op_readback':['test_readback.py','test_native.py','test_precheck.py','test_family.py'],
       'op_precheck':['test_precheck.py','test_native.py','test_family.py'],
       'dispatcher':['test_family.py'],'dispatcher_write':['test_family.py'],'launcher':['test_family.py']}
TESTS['scan']=TESTS['scan']+['test_native.py']
WRITE_OPS=('provision','install_units')

def files_of(target):
    if target=='dispatcher':return [op+'/dispatch_once.py' for op in SOURCE]
    if target=='dispatcher_write':return [op+'/dispatch_once.py' for op in WRITE_OPS]
    if target=='launcher':return [op+'/launcher_stdin.py' for op in SOURCE]
    return [SOURCE[op] for op in CARRIES[target]]

from mutants import MUTANTS,COMBOS,EFFECTS,REDUNDANT

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
        for relative in files_of(target):
            count=(CAND/relative).read_text().count(old)
            if count!=1:errors.append('%s: anchor occurs %d times in %s'%(name,count,relative))
        if old==new:errors.append(name+': no change')
    names=[mutant[0] for mutant in MUTANTS]
    if len(set(names))!=len(names):errors.append('duplicate mutant names')
    for name,members in COMBOS.items():
        for member in members:
            if member not in names:errors.append('%s: unknown member %s'%(name,member))
    for name in REDUNDANT:
        if name not in names:errors.append('%s: redundant mutant is not in the list'%name)
        if not any(name in members and len(members)>1 for members in COMBOS.values()):errors.append('%s: redundant mutant without a combined mutant'%name)
    return errors+effects_coverage()

def effects_coverage():
    """Every member of the effects each source computes for its fixture has its own mutant (EFFECTS in mutants.py)
    and no mutant names a member that does not exist. Read from the candidate's own fixtures, offline."""
    sys.path.insert(0,str(CAND/'tests'))
    try:import family
    finally:sys.path.remove(str(CAND/'tests'))
    errors=[]
    for op in SOURCE:
        # placement B: the fixture in which every member is present (under placement A the data volume members are null)
        docs,_=family.default_docs(op,placement='B');effects=docs.go['effects'];spec=EFFECTS.get(op,{'top':[],'nested':{}})
        if sorted(effects)!=sorted(spec['top']):errors.append('%s: effects members %s have no mutant or do not exist'%(op,sorted(set(effects)^set(spec['top']))))
        for key,value in effects.items():
            item=value[0] if type(value) is list and value and type(value[0]) is dict else value if type(value) is dict else None
            if key in spec['nested']:
                if item is None or sorted(item)!=sorted(spec['nested'][key]):errors.append('%s.%s: nested members differ from the mutant list'%(op,key))
            elif item is not None and key not in spec.get('opaque',[]):errors.append('%s.%s: a nested member list or an opaque mark is missing'%(op,key))
    return errors

def prepare(name):
    work=WORK/name
    if work.exists():shutil.rmtree(work)
    shutil.copytree(CAND,work,ignore=shutil.ignore_patterns('mutation','__pycache__','*.pyc','TESTS*.xml'))
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
        try:
            for relative in set(relative for target,_,_ in changes for relative in files_of(target)):
                compile((work/relative).read_text(),relative,'exec')
        except SyntaxError as error:return {'mutant':name,'error':'SYNTAX %s'%error}
        command=[PYTHON,'-B','-m','pytest','-p','no:cacheprovider','--basetemp',str(work/'_tmp'),'-q','-x','-k','not static',
                 '--tb=line']+[str(work/'tests'/item) for item in tests]
        done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=ENV,cwd=str(work),timeout=900)
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
    pins={relative:sha(CAND/relative) for relative in sorted(set(SOURCE.values())|{op+'/dispatch_once.py' for op in SOURCE}|{op+'/launcher_stdin.py' for op in SOURCE})}
    pins.update({'tests/'+item:sha(CAND/'tests'/item) for item in ALL+['family.py','hostemu.py','native_child.py','oslevel.py']})
    pins['mutation/mutants.py']=sha(CAND/'mutation'/'mutants.py')
    record={'python':subprocess.run([PYTHON,'-V'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.decode().strip(),
            'candidate_sha256':pins,'counts':{'single':len([name for name in names if name not in COMBOS]),'combined':len([name for name in names if name in COMBOS]),
            'killed':len([row for row in results if row.get('killed')]),'survivors':len(survivors),'errors':len(failures),
            'redundant_survivors':len(redundant_survivors)},
            'survivors':survivors,'errors':failures,'results':results,'complete_run':len(sys.argv)<=2,
            'redundant':{name:{'why':REDUNDANT[name],'combined_mutants':sorted(combo for combo,members in COMBOS.items() if name in members)}
                         for name in sorted(REDUNDANT) if name in names},
            'redundant_survivors':redundant_survivors,'redundant_killed_alone':redundant_killed}
    if len(sys.argv)<=2:(CAND/'mutation'/RECORD).write_text(json.dumps(record,indent=1,sort_keys=True)+'\n')
    print('MUTANTS',len(results));print('SURVIVORS',survivors);print('REDUNDANT_SURVIVORS',redundant_survivors);print('ERRORS',failures)
    return 1 if survivors or failures else 0

if __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parent));raise SystemExit(main())
