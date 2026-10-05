"""Author's check of K6a, offline: runs what CONTRACT.txt section 11 lists and writes VALIDATION.json from what the
commands printed (nothing in that file is typed). No host, no network, no docker.

  validate.py <python 3.9> <python 3.12>      (the core beside this directory as ../core)

It runs: the seal of the core, assemble.py --check, the suite with each interpreter (with whatever HOSTOPS02_TEST_*
locations the environment gives, and once without them), mutate.py check, the self-test of the Linux shapes; it reads
both mutation records and says whether their pins are the bytes of this directory. It does not run the mutation.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
CORE=Path(os.environ.get('HOSTOPS02_CORE_DIRECTORY') or HERE.parent/'core').resolve()
BARE={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ.get('HOME','')}
GIVEN=dict(BARE,**{name:value for name,value in os.environ.items() if name.startswith('HOSTOPS02_TEST_')})

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(argv,env=BARE,cwd=HERE):
    done=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,env=env,cwd=str(cwd))
    return done.returncode,done.stdout.decode(errors='replace').strip()
def counts(line):
    return {key:int(number) for number,key in re.findall(r'(\d+) (passed|failed|skipped|errors?|deselected)',line)}

def suite(python,env):
    files=sorted(path.name for path in (HERE/'tests').glob('test_*.py'));per={}
    for name in files:
        code,out=run([python,'-B','-m','pytest','-p','no:cacheprovider','-q','tests/'+name],env);per[name]=dict(counts(out.splitlines()[-1]),returncode=code)
    code,out=run([python,'-B','-m','pytest','-p','no:cacheprovider','-q','tests'],env)
    return {'version':run([python,'-V'])[1],'returncode':code,'total':counts(out.splitlines()[-1]),'by_file':per}

def record(name):
    path=HERE/'mutation'/name
    if not path.is_file():return {'present':False}
    data=json.loads(path.read_bytes());pins=data.get('pins',{})
    def current(relative):
        if relative.startswith('core/'):return sha(CORE/relative[5:])
        if relative=='mutation/mutate.py':return sha(HERE/'mutation'/'mutate.py')
        return sha(HERE/relative)
    stale=sorted(relative for relative,value in pins.items() if current(relative)!=value)
    slow=[row['mutant'] for row in data['results'] if str(row.get('summary','')).startswith('TIME_LIMIT')]
    return {'present':True,'sha256':sha(path),'python':data['python'],'counts':data['counts'],'origin':data.get('origin'),'survivors':data['survivors'],'errors':data['errors'],
            'complete_run':data['complete_run'],'killed_by_the_time_limit':slow,'pins_are_the_bytes_of_this_directory':not stale,'pins_that_differ':stale}

def inherited():
    """The core's own mutants run against THIS operation's suite (information: their kill by the core's suite is the
    core's record). Survivors by the part they mutate."""
    base=record('MUTATION_INHERITED.json')
    if not base.get('present'):return base
    os.environ['HOSTOPS_MUTATION_INHERITED']='yes';sys.path.insert(0,str(HERE/'mutation'))
    try:
        import mutants
    finally:sys.path.remove(str(HERE/'mutation'))
    own=mutants.BUILT.index('# ==== BEGIN OP_ACTIVATE')
    # a row of the core's list is applied wherever its anchor occurs once in the built source: some anchors of the core's
    # demonstration operation occur in this operation's own part instead of a shared part, and are counted apart
    target={name:('this_operation_part' if part not in ('dispatcher','launcher') and mutants.BUILT.index(old)>=own else part) for name,part,old,_ in mutants.MUTANTS}
    data=json.loads((HERE/'mutation'/'MUTATION_INHERITED.json').read_bytes());parts={}
    for row in data['results']:
        part=parts.setdefault(target.get(row['mutant'],'?'),{'run':0,'killed':0,'survivors':[]});part['run']+=1
        if row.get('killed'):part['killed']+=1
        else:part['survivors'].append(row['mutant'])
    base.update(by_part=parts,not_applicable_to_this_build=len(mutants.INHERITED_SKIPPED),
                meaning='a survivor here is a guarantee of the core that this operation\'s own tests do not exercise; the core\'s own record kills it');return base

def main(arguments):
    if len(arguments)!=2:
        print(__doc__);return 2
    old,new=arguments;assembly=json.loads((HERE/'build'/'ASSEMBLY.json').read_bytes())
    check=run(['/usr/bin/python3','-B',str(CORE/'assemble.py'),'--check',str(HERE)])
    seal=run(['/usr/bin/python3','-B',str(CORE/'seal.py'),'check'],cwd=CORE)
    anchors=run(['/usr/bin/python3','-B','mutation/mutate.py','check'])
    shapes=run(['/usr/bin/python3','-B','linux_root/shapes.py','--self-test'])
    result={'schema':'HOSTOPS02_ACTIVATE_VALIDATION_V1','operation':assembly['operation'],
            'taken_at_utc':run(['/bin/date','-u','+%Y-%m-%dT%H:%M:%SZ'])[1],
            'core':{'generation':run(['/usr/bin/python3','-B',str(CORE/'assemble.py'),'--core'])[1],'seal':seal[1],'CORE_SHA256SUMS':sha(CORE/'CORE_SHA256SUMS')},
            'assembly':{'check':check[1],'source_sha256':assembly['source_sha256'],'source_bytes':assembly['source_bytes'],'scope_sha256':assembly['scope_sha256'],
                        'final_payload_unbound_sha256':assembly['final_payload_sha256'],'final_payload_unbound_bytes':assembly['final_payload_bytes'],
                        'dispatcher_sha256':assembly['dispatcher_sha256'],'launcher_sha256':assembly['launcher_sha256'],'transport_sha256':assembly['transport_sha256'],
                        'operation_part_sha256':assembly['operation_part_sha256'],'spec_sha256':assembly['spec_sha256'],'unbound_request_bytes':assembly['unbound_request_bytes'],
                        'dates':assembly['dates'],'writes_allowed':assembly['writes_allowed'],'activation_allowed':assembly['activation_allowed']},
            'tests':{'with_the_locations_given':{'locations':sorted(name for name in GIVEN if name.startswith('HOSTOPS02_TEST_')),'python_a':suite(old,GIVEN),'python_b':suite(new,GIVEN)},
                     'without_them':{'python_a':suite(old,BARE)['total'],'python_b':suite(new,BARE)['total']}},
            'mutation':{'anchors':anchors[1],'MUTATION_RUN.json':record('MUTATION_RUN.json'),'MUTATION_RUN.py312.json':record('MUTATION_RUN.py312.json'),
                        'MUTATION_INHERITED.json':inherited()},
            'linux_job':{'run':False,'why':'no Linux and no docker offline','shapes_self_test_on_the_emulation':{'returncode':shapes[0]}},
            'host':{'contacted':False},'reviewed_by_anyone_but_the_author':False}
    (HERE/'VALIDATION.json').write_text(json.dumps(result,indent=1,sort_keys=True)+'\n')
    ok=(check[0]==0 and seal[0]==0 and anchors[0]==0 and shapes[0]==0 and all(result['tests']['with_the_locations_given'][key]['returncode']==0 for key in ('python_a','python_b')))
    print('VALIDATION_WRITTEN' if ok else 'VALIDATION_WRITTEN_WITH_FAILURES');return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
