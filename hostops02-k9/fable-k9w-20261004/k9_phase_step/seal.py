"""Seal of K9W (k9_phase_step). Offline; run by the author when every other file is final. (K4-E0's seal.py with its
own tables: one own mutation list run on two interpreters.)

  seal.py write    checks the core's seal and that build/ is the assembly, runs the suite with each interpreter,
                   reads the mutation records, writes VALIDATION.json and then SHA256SUMS
  seal.py check    exit 1 unless the core is the sealed one, build/ is the assembly and SHA256SUMS agrees with the files

Nothing is typed: every hash and every count in VALIDATION.json is computed here from the files and from the runs.
Interpreters: /usr/bin/python3 and, when HOSTOPS_SEAL_PYTHON_2 names one, a second (only its version enters the file).
A mutation record counts only while its pins equal the files as they are (VALIDATION.json says so per record).

Scratch (the junit file, the suites' temporary trees, the mutation copies) goes to ../k9_phase_step.work, OUTSIDE this
directory. A directory named work/ inside it is refused by both modes (WORK_INSIDE), so nothing can sit unsealed here.
What is sealed: every file of this directory except SHA256SUMS itself, work/ (scratch) and any directory whose name
begins with "review-" (where reviewers of these bytes write; nothing in them is read by a test, a tool or a run).
The two suites of VALIDATION.json are run without any other operation named, so their number of tests is the one the
Linux job (set 3, not run by the author) should show. When HOSTOPS_SEAL_OTHER_OPERATIONS names sibling
operations and earlier families (and HOSTOPS_SEAL_BOUND_POSTDEPLOY the bound post-deploy set), one more run with
them is recorded apart, with the hash of each one's unbound request: information about that instant, not a seal."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ElementTree

HERE=Path(__file__).resolve().parent
CORE=HERE.parent/'core'
SKIP_DIRECTORIES=('__pycache__','.pytest_cache','_tmp','work')
SKIP_PREFIX='review-'                     # reviewers' scratch inside the operation directory
CLEAN=('MUTATION_RUN.json','MUTATION_RUN.py312.json')       # zero survivors required
RECORDS=CLEAN
PRIVATE=('HOSTOPS02_TEST_OTHER_OPERATIONS','HOSTOPS02_TEST_BOUND_POSTDEPLOY')        # never given to the two sealed suites
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME','')}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_') and name not in PRIVATE})
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def listed():
    out=[]
    for path in sorted(HERE.rglob('*')):
        relative=path.relative_to(HERE)
        if (path.is_file() and relative.as_posix()!='SHA256SUMS' and not set(relative.parts)&set(SKIP_DIRECTORIES) and path.suffix!='.pyc'
                and not any(part.startswith(SKIP_PREFIX) for part in relative.parts[:-1])):out.append(relative.as_posix())
    return out
def sums():return ''.join('%s  %s\n'%(sha(HERE/name),name) for name in listed())

def core_ok():
    done=subprocess.run(['/usr/bin/python3','-B',str(CORE/'seal.py'),'check'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV)
    return done.returncode==0 and done.stdout.strip()==b'SEAL_OK'
def build_ok():
    done=subprocess.run(['/usr/bin/python3','-B',str(CORE/'assemble.py'),'--check',str(HERE)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV)
    return done.returncode==0 and done.stdout.strip()==b'BUILD_EQUAL'

def suite(python,extra=None):
    """One run of tests/ with one interpreter: counts read from the junit file pytest writes, never from its text."""
    env=dict(ENV,**(extra or {}))
    work=HERE.parent/(HERE.name+'.work');work.mkdir(exist_ok=True);report=work/'seal-junit.xml'     # scratch OUTSIDE the sealed directory
    if report.exists():report.unlink()
    done=subprocess.run([python,'-B','-W','error::SyntaxWarning','-m','pytest','-p','no:cacheprovider','-q','--basetemp',str(work/'_seal_tmp'),'--junitxml',str(report),
                         '-o','junit_family=xunit2','tests'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,cwd=str(HERE))
    node=ElementTree.parse(str(report)).getroot();node=node if node.tag=='testsuite' else node.find('testsuite')
    counts={key:int(node.get(key)) for key in ('tests','failures','errors','skipped')}
    files={};skips=[]
    for case in node.iter('testcase'):
        name=case.get('classname','').split('.')[1] if '.' in case.get('classname','') else case.get('classname','');files[name]=files.get(name,0)+1
        if case.find('skipped') is not None:skips.append(case.get('name'))
    version=subprocess.run([python,'-V'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.decode().strip()
    return {'python':version,'returncode':done.returncode,'passed':counts['tests']-counts['failures']-counts['errors']-counts['skipped'],'per_file':dict(sorted(files.items())),
            'release_repository_given':'HOSTOPS02_TEST_RELEASE_REPOSITORY' in ENV,'skipped_tests':sorted(skips),**counts}

def record(name):
    """One record of mutation/mutate.py (K9R's harness): its pins are paths of this directory, or core/<path> for the core."""
    path=HERE/'mutation'/name
    if not path.is_file():return {'present':False}
    data=json.loads(path.read_bytes());pins=data.get('pins_sha256',{})
    def current(relative):
        if relative.startswith('core/'):return sha(CORE/relative[len('core/'):]) if (CORE/relative[len('core/'):]).is_file() else None
        return sha(HERE/relative) if (HERE/relative).is_file() else None
    stale=sorted(relative for relative,value in pins.items() if current(relative)!=value)
    timed_out=[row['mutant'] for row in data['results'] if str(row.get('summary','')).startswith('TIME_LIMIT')]
    return {'present':True,'sha256':sha(path),'python':data['python'],'complete_run':data['complete_run'],'counts':data['counts'],'survivors':data['survivors'],
            'errors':data['errors'],'killed_by_the_time_limit':timed_out,'pins_equal_the_files':not stale and bool(pins),'stale_pins':stale}

def others():
    """The run with the sibling operations and the earlier families named by the caller, or None. Information only."""
    named=[item for item in os.environ.get('HOSTOPS_SEAL_OTHER_OPERATIONS','').split(os.pathsep) if item]
    if not named or not os.environ.get('HOSTOPS_SEAL_PYTHON_2'):return None
    extra={'HOSTOPS02_TEST_OTHER_OPERATIONS':os.pathsep.join(named)}
    if os.environ.get('HOSTOPS_SEAL_BOUND_POSTDEPLOY'):extra['HOSTOPS02_TEST_BOUND_POSTDEPLOY']=os.environ['HOSTOPS_SEAL_BOUND_POSTDEPLOY']
    rows=[]
    for item in named:
        path=Path(item).resolve();template=path/'build'/'REQUEST.UNBOUND.json' if (path/'build'/'ASSEMBLY.json').is_file() else path/'REQUEST.UNBOUND.json'
        rows.append({'name':'/'.join(path.parts[-2:]),'unbound_request_sha256':sha(template) if template.is_file() else None,
                     'sealed':(path/'SHA256SUMS').is_file(),'sha256sums_sha256':sha(path/'SHA256SUMS') if (path/'SHA256SUMS').is_file() else None})
    return {'named':rows,'bound_postdeploy_given':'HOSTOPS02_TEST_BOUND_POSTDEPLOY' in extra,'run':suite(os.environ['HOSTOPS_SEAL_PYTHON_2'],extra),
            'meaning':'what these directories were when this was sealed; they are sealed on their own and may change afterwards'}

def main(mode):
    if (HERE/'work').exists():
        print('WORK_INSIDE: move',HERE/'work','aside; scratch belongs in',HERE.parent/(HERE.name+'.work'));return 1
    if mode=='check':
        ok=core_ok() and build_ok() and (HERE/'SHA256SUMS').is_file() and (HERE/'SHA256SUMS').read_text(encoding='ascii')==sums()
        print('SEAL_OK' if ok else 'SEAL_BROKEN');return 0 if ok else 1
    if mode!='write':
        print(__doc__);return 2
    if not core_ok():raise SystemExit('the core is not the sealed one')
    if not build_ok():raise SystemExit('build/ is not what assemble.py writes')
    assembly=json.loads((HERE/'build'/'ASSEMBLY.json').read_bytes())
    suites=[suite('/usr/bin/python3')]+([suite(os.environ['HOSTOPS_SEAL_PYTHON_2'])] if os.environ.get('HOSTOPS_SEAL_PYTHON_2') else [])
    validation={'schema':'HOSTOPS02_K9_PHASE_STEP_VALIDATION_V1','revision':4,'operation':assembly['operation'],
                'core':{'generation_sha256_of_assemble_py':sha(CORE/'assemble.py'),'core_sha256sums':sha(CORE/'CORE_SHA256SUMS'),'seal':'SEAL_OK'},
                'assembly':{key:assembly[key] for key in ('parts','core_sha256','source_sha256','source_bytes','scope_sha256','operation_part_sha256','spec_sha256',
                            'dispatcher_sha256','launcher_sha256','transport_sha256','final_payload_sha256','final_payload_bytes','unbound_request_bytes','date_class','dates',
                            'writes_allowed','activation_allowed')},
                'build_equals_assembly':True,
                'unbound_documents':{name:sha(HERE/'build'/name) for name in ('REQUEST.UNBOUND.json','AUTHORITY.UNBOUND.json','GO.UNBOUND.json','DISPATCH.UNBOUND.json',
                                                                                'PUBLICATION_PROOF.UNBOUND.json','FINAL_PAYLOAD.UNBOUND.py')},
                'fixture':{'module_sha256':sha(HERE/'tests'/'k9w.py'),'runner_bytes':'SYNTHETIC test bytes only (tests/k9w.py RUNNER); the runner is judged by hash on the host (TREE), not here'},
                'contracts':{'k9r_build':'../k9_phase_read/build/k9_phase_read.py','k9r_build_sha256':sha(HERE.parent/'k9_phase_read'/'build'/'k9_phase_read.py') if (HERE.parent/'k9_phase_read'/'build'/'k9_phase_read.py').is_file() else None,
                             'runner_source':'W/fable-k9runner-20261004/src/k9_runner.readable.py','runner_source_sha256':sha(HERE.parent.parent/'fable-k9runner-20261004'/'src'/'k9_runner.readable.py') if (HERE.parent.parent/'fable-k9runner-20261004'/'src'/'k9_runner.readable.py').is_file() else None,
                             'meaning':'the files the step plan, launch record and receipt checks were matched to when this was sealed; both are in progress'},
                'suites':suites,'suites_with_other_operations':others(),'mutation':{name:record(name) for name in RECORDS},
                'placement':{'status':'DECIDED_BY_CODEX_2026_10_04','decision_file':'W/codex-n8-placement-20261004.txt',
                             'decision_sha256':'d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53',
                             'amended_by':'Codex decision 6, #429 comment 5985748037: source_root /var/lib/c3po/r2d2-v2-source-20261005, root-only chain, on the filesystem of days/',
                             'revision':4,'previous_revision':'../k9_phase_step.rev1-165330a6',
                             'note':'a location decision, not a GO of these bytes or a host authorization'},
                'linux_root_job':{'status':'NOT_RUN','required_before_any_binding':True,'entry_point':'linux_root/run.sh (after core/linux_root/run.sh ../k9_phase_step)',
                                  'gate':'set 3: the core linux_root job run with this directory as its argument, suite passing as real root, then linux_root/run.sh exit 0'},
                'host':'NOTHING_OF_THIS_DIRECTORY_WAS_RUN_ON_THE_HOST','bound':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,indent=1,sort_keys=True)+'\n',encoding='ascii')
    (HERE/'SHA256SUMS').write_text(sums(),encoding='ascii')
    print('VALIDATION.json',sha(HERE/'VALIDATION.json'));print('SHA256SUMS',sha(HERE/'SHA256SUMS'),'(%d files)'%len(listed()))
    bad=[item for item in suites if item['returncode']!=0 or item['failures'] or item['errors']]
    own=[validation['mutation'][name] for name in CLEAN]
    weak=[item for item in own if not (item.get('present') and item['pins_equal_the_files'] and item['complete_run'] and not item['survivors'] and not item['counts']['errors']
                                       and not item['killed_by_the_time_limit'])]
    if bad or weak:print('NOT_CLEAN: suites failing %d, mutation records missing, stale or with survivors %d'%(len(bad),len(weak)));return 1
    print('CLEAN');return 0

if __name__=='__main__':raise SystemExit(main(sys.argv[1] if len(sys.argv)==2 else ''))
