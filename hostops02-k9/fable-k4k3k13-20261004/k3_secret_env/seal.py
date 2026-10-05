"""Seal of K3 (k3_secret_env). Offline; run by the author when every other file is final. (K4-E0's seal.py with the
record format of K3-K9's mutation harness, and with the core named core_k3.)

  seal.py write    checks the core (below) and that build/ is the assembly, runs the suite with each interpreter, reads
                   the two mutation records, writes VALIDATION.json and then SHA256SUMS
  seal.py check    exit 0 and SEAL_OK only when the core is the expected generation with its parts as pinned, build/ is
                   the assembly, SHA256SUMS lists exactly the files present and every hash holds, and both mutation
                   records were made against these bytes with zero survivors and zero errors

The core (../core_k3) has a new complete candidate manifest. Its runtime generation is unchanged.
No file is exempt from verification. The original inconsistent manifest is preserved outside the
operation; the complete new manifest and its evidence require independent review before approval.

Nothing is typed: every hash and count in VALIDATION.json is computed here from the files and from the runs.
Interpreters: /usr/bin/python3 and, when HOSTOPS_SEAL_PYTHON_2 names one, a second (only its version enters the file).
Not sealed: SHA256SUMS itself, work/, caches, and any top-level directory whose name begins with "review-"."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree

HERE=Path(__file__).resolve().parent
CORE=HERE.parent/'core_k3'
SCRATCH=HERE.parent/'work'/'k3'
GENERATION='232f4180a940186e86d7599c10c4fac143fcfe3950baa8e853a3910f84f5c1e6'
CORE_UNSEALED=()  # no exceptions, including metadata and mutation evidence
SKIPPED_DIRECTORIES=('work','__pycache__','.pytest_cache','_tmp')
REVIEW_PREFIX='review-'
RECORDS=('MUTATION_RUN.json','MUTATION_RUN.py312.json')
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME',''),'TMPDIR':tempfile.gettempdir()}
ENV.update({name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def listed():
    out=[]
    for path in sorted(HERE.rglob('*')):
        relative=path.relative_to(HERE)
        if not path.is_file() or relative.as_posix()=='SHA256SUMS' or set(relative.parts)&set(SKIPPED_DIRECTORIES) or path.suffix=='.pyc':continue
        if len(relative.parts)>1 and relative.parts[0].startswith(REVIEW_PREFIX):continue
        out.append(relative.as_posix())
    return out
def sums():return ''.join('%s  %s\n'%(sha(HERE/name),name) for name in listed())

def core_problems():
    out=[]
    done=subprocess.run(['/usr/bin/python3','-B',str(CORE/'assemble.py'),'--core'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=ENV)
    if done.returncode!=0 or done.stdout.strip().decode(errors='replace')!=GENERATION:out.append('assemble.py --core: '+done.stdout.decode(errors='replace').strip()[:200])
    if sha(CORE/'assemble.py')!=GENERATION:out.append('core_k3/assemble.py is not the generation '+GENERATION)
    checked=subprocess.run(['/usr/bin/python3','-B',str(CORE/'seal.py'),'check'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=ENV)
    if checked.returncode!=0 or checked.stdout.strip()!=b'SEAL_OK':out.append('complete core seal is broken')
    for line in (CORE/'CORE_SHA256SUMS').read_text().splitlines():
        digest,_,name=line.partition('  ')
        if not (CORE/name).is_file() or sha(CORE/name)!=digest:out.append('core_k3/%s differs from CORE_SHA256SUMS'%name)
    return out
def build_ok():
    done=subprocess.run(['/usr/bin/python3','-B',str(CORE/'assemble.py'),'--check',str(HERE)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV)
    return done.returncode==0 and done.stdout.strip()==b'BUILD_EQUAL'

def record_problems(name):
    path=HERE/'mutation'/name
    if not path.is_file():return ['mutation/%s is missing'%name]
    row=json.loads(path.read_bytes());out=[]
    stale=[relative for relative,pin in row['operation_sha256'].items() if not (HERE/relative).is_file() or sha(HERE/relative)!=pin]
    if stale:out.append('mutation/%s was made against other bytes: %s'%(name,', '.join(stale[:6])))
    if row['core_generation_sha256']!=GENERATION or row['core_seal_sha256']!=sha(CORE/'CORE_SHA256SUMS'):out.append('mutation/%s was made against another core'%name)
    if not row['complete_run'] or row['counts']['survivors'] or row['counts']['errors']:out.append('mutation/%s is not a complete run with zero survivors and zero errors'%name)
    return out

def problems():
    out=core_problems()
    if not build_ok():out.append('build/ is not what core_k3/assemble.py writes')
    path=HERE/'SHA256SUMS'
    if not path.is_file():return out+['SHA256SUMS is missing']
    if path.read_text(encoding='ascii')!=sums():out.append('SHA256SUMS does not list exactly the files present with their hashes')
    for name in RECORDS:out+=record_problems(name)
    return out

def suite(python):
    """One run of tests/ with one interpreter: counts read from the junit file pytest writes, never from its text."""
    SCRATCH.mkdir(parents=True,exist_ok=True);report=SCRATCH/('seal-junit-%s.xml'%hashlib.sha256(python.encode()).hexdigest()[:8])
    done=subprocess.run([python,'-B','-m','pytest','-p','no:cacheprovider','-q','--basetemp',str(SCRATCH/('seal_tmp_'+report.stem[-8:])),'--junitxml',str(report),
                         '-o','junit_family=xunit2','tests'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=ENV,cwd=str(HERE))
    node=ElementTree.parse(str(report)).getroot();node=node if node.tag=='testsuite' else node.find('testsuite')
    counts={key:int(node.get(key)) for key in ('tests','failures','errors','skipped')}
    files={};skips=[]
    for case in node.iter('testcase'):
        name=case.get('classname','').split('.')[1] if '.' in case.get('classname','') else case.get('classname','');files[name]=files.get(name,0)+1
        if case.find('skipped') is not None:skips.append(case.get('name'))
    version=subprocess.run([python,'-V'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.decode().strip()
    return {'python':version,'returncode':done.returncode,'passed':counts['tests']-counts['failures']-counts['errors']-counts['skipped'],
            'per_file':dict(sorted(files.items())),'skipped_tests':sorted(skips),**counts}

def record(name):
    path=HERE/'mutation'/name
    if not path.is_file():return {'present':False}
    data=json.loads(path.read_bytes())
    timed_out=[row['mutant'] for row in data['results'] if str(row.get('summary','')).startswith('TIME_LIMIT')]
    return {'present':True,'sha256':sha(path),'python':data['python'],'complete_run':data['complete_run'],'counts':data['counts'],'survivors':data['survivors'],
            'errors':data['errors'],'killed_by_the_time_limit':timed_out,'problems':record_problems(name)}

def main(mode):
    if mode=='check':
        found=problems()
        if found:
            print('\n'.join(found));print('SEAL_BROKEN',len(found));return 1
        print('SEAL_OK',len(listed()),'files',sha(HERE/'SHA256SUMS'));return 0
    if mode!='write':
        print(__doc__);return 2
    found=core_problems()
    if found:raise SystemExit('the core is not the expected one: '+'; '.join(found))
    if not build_ok():raise SystemExit('build/ is not what assemble.py writes')
    assembly=json.loads((HERE/'build'/'ASSEMBLY.json').read_bytes())
    suites=[suite('/usr/bin/python3')]+([suite(os.environ['HOSTOPS_SEAL_PYTHON_2'])] if os.environ.get('HOSTOPS_SEAL_PYTHON_2') else [])
    validation={'schema':'HOSTOPS02_K3_SECRET_ENV_VALIDATION_V1','operation':assembly['operation'],
                'core':{'directory':'../core_k3 (byte copy of the secrets family\'s revision, made 2026-10-04 21:15Z; never written)',
                        'generation_sha256_of_assemble_py':sha(CORE/'assemble.py'),'core_sha256sums':sha(CORE/'CORE_SHA256SUMS'),
                        'assemble_core':'GENERATION_OK','files_listed_and_equal':'every file of CORE_SHA256SUMS but '+', '.join(CORE_UNSEALED),
                        'unsealed_at_the_copy':{name:sha(CORE/name) for name in CORE_UNSEALED},
                        'note':'the core\'s own seal.py check answers SEAL_BROKEN on the copy because of the two files above (upstream was mid-run)'},
                'assembly':{key:assembly[key] for key in ('parts','core_sha256','source_sha256','source_bytes','scope_sha256','operation_part_sha256','spec_sha256',
                            'dispatcher_sha256','launcher_sha256','transport_sha256','final_payload_sha256','final_payload_bytes','unbound_request_bytes','date_class','dates',
                            'writes_allowed','activation_allowed')},
                'build_equals_assembly':True,
                'unbound_documents':{name:sha(HERE/'build'/name) for name in ('REQUEST.UNBOUND.json','AUTHORITY.UNBOUND.json','GO.UNBOUND.json','DISPATCH.UNBOUND.json',
                                                                                'PUBLICATION_PROOF.UNBOUND.json','FINAL_PAYLOAD.UNBOUND.py')},
                'suites':suites,'mutation':{name:record(name) for name in RECORDS},
                'owner_sentence':{'status':'PROPOSED_NOT_SIGNED','where':'DESIGN.md section 11'},
                'review':{'status':'NOT_REVIEWED'},
                'linux_root_job':{'status':'NOT_RUN','required_before_any_binding':True,
                                  'gate':'the core_k3 linux_root job run with this directory as its argument, suite passing as real root'},
                'host':'NOTHING_OF_THIS_DIRECTORY_WAS_RUN_ON_THE_HOST','bound':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(validation,indent=1,sort_keys=True)+'\n',encoding='ascii')
    (HERE/'SHA256SUMS').write_text(sums(),encoding='ascii')
    print('VALIDATION.json',sha(HERE/'VALIDATION.json'));print('SHA256SUMS',sha(HERE/'SHA256SUMS'),'(%d files)'%len(listed()))
    bad=[item for item in suites if item['returncode']!=0 or item['failures'] or item['errors']]
    weak=[name for name in RECORDS if validation['mutation'][name].get('problems',['missing']) or validation['mutation'][name]['killed_by_the_time_limit']]
    if bad or weak:print('NOT_CLEAN: suites failing %d, mutation records missing, stale or with survivors: %s'%(len(bad),weak));return 1
    print('CLEAN');return 0

if __name__=='__main__':raise SystemExit(main(sys.argv[1] if len(sys.argv)==2 else ''))
