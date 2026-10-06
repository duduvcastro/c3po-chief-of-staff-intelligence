"""Candidate CI orchestrator. Never dispatches an operational request. NOT_RUN by its author."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

PACKAGE=Path(__file__).resolve().parents[1]
INPUTS_RAW=(PACKAGE/'proof/INPUTS.json').read_bytes()
PINS=json.loads(INPUTS_RAW)
PRODUCTION=('/etc/c3po-bar','/var/lib/c3po-bar','/etc/c3po-reader','/var/lib/c3po-reader','/opt/chief-of-staff-digital','/mnt/day-d-data','/run/c3po-security','/var/lib/c3po','/var/lib/c3po-capacity')

def digest(raw):return hashlib.sha256(raw).hexdigest()
def raw(path):
    path=Path(path)
    if path.is_symlink():raise ValueError('SYMLINK_INPUT')
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise ValueError('NOT_SINGLE_REGULAR')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd);data=b''
        while True:
            block=os.read(fd,1048576)
            if not block:break
            data+=block
        after=os.fstat(fd)
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('INPUT_CHANGED_DURING_READ')
        return data
    finally:os.close(fd)
def pin_unit(root,manifest,pin):
    data=raw(root/manifest)
    if digest(data)!=pin:raise ValueError('MANIFEST_PIN')
    rows={}
    for line in data.decode('ascii').splitlines():
        if not re.fullmatch(r'[0-9a-f]{64}  [^\r\n]+',line):raise ValueError('MANIFEST_GRAMMAR')
        sha,name=line.split('  ',1);p=Path(name)
        if p.is_absolute() or any(x in ('','..','.') for x in name.split('/')) or name in rows:raise ValueError('MANIFEST_PATH')
        rows[name]=sha
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual!=set(rows)|{manifest}:raise ValueError('UNIT_FILE_SET')
    for name,pin in rows.items():
        if digest(raw(root/name))!=pin:raise ValueError('UNIT_BUFFER_PIN')
    return {'manifest_sha256':digest(data),'members':len(rows),'file_hashes':rows}
def snapshot():
    if digest(raw(PACKAGE/'proof/INPUTS.json'))!=digest(INPUTS_RAW):raise ValueError('INPUTS_CONFIG_CHANGED')
    out={'inputs_sha256':digest(INPUTS_RAW)}
    for name,unit in PINS['units'].items():out[name]=pin_unit(PACKAGE/unit['path'],unit['manifest'],unit['sha256'])
    for name,pin in PINS['proof_files'].items():
        if digest(raw(PACKAGE/name))!=pin:raise ValueError('PROOF_FILE_PIN')
    return out

def guard():
    if sys.platform!='linux' or os.getuid()==0 or os.getuid()!=os.geteuid():raise ValueError('NONROOT_LINUX_REQUIRED')
    if any(os.environ.get(k)!=v for k,v in [('GITHUB_ACTIONS','true'),('RUNNER_ENVIRONMENT','github-hosted'),('HOSTOPS_THROWAWAY_RUNNER','yes')]):raise ValueError('THROWAWAY_GITHUB_REQUIRED')
    if any(os.path.lexists(p) for p in PRODUCTION):raise ValueError('PRODUCTION_PATH_PRESENT')

def write(path,data):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        view=memoryview(data)
        while view:view=view[os.write(fd,view):]
        os.fsync(fd)
    finally:os.close(fd)

def junit(path,component,identity,collected=None,original_system=False):
    data=raw(path);root=ET.fromstring(data)
    if root.tag!='testsuites' or any(x.tag!='testsuite' for x in root):raise ValueError('JUNIT_ROOT_STRUCTURE')
    cases=[]
    for suite in root:
        if any(x.tag not in ('properties','testcase') for x in suite):raise ValueError('JUNIT_SUITE_STRUCTURE')
        for props in [x for x in suite if x.tag=='properties']:
            if any(x.tag!='property' or list(x) for x in props):raise ValueError('JUNIT_PROPERTIES_STRUCTURE')
        direct=[x for x in suite if x.tag=='testcase']
        if list(suite.iter('testcase'))!=direct or list(suite.iter('testsuite'))!=[suite]:raise ValueError('JUNIT_HIDDEN_CASE_OR_SUITE')
        counts={'tests':len(direct),'failures':0,'errors':0,'skipped':0}
        for case in direct:
            if any(x.tag not in ('properties','failure','error','skipped','system-out','system-err') for x in case):raise ValueError('JUNIT_CASE_STRUCTURE')
            for props in [x for x in case if x.tag=='properties']:
                if any(x.tag!='property' or list(x) for x in props):raise ValueError('JUNIT_PROPERTIES_STRUCTURE')
            status=[x for x in case if x.tag in ('failure','error','skipped')]
            if len(status)>1:raise ValueError('JUNIT_AMBIGUOUS_STATUS')
            for x in case.iter():
                if x is not case and x not in list(case) and x.tag in ('testcase','testsuite','failure','error','skipped'):raise ValueError('JUNIT_HIDDEN_STATUS')
            if status:counts[status[0].tag+'s' if status[0].tag!='skipped' else 'skipped']+=1
        for tag in ('failure','error','skipped'):
            if list(suite.iter(tag))!=[node for case in direct for node in case if node.tag==tag]:raise ValueError('JUNIT_HIDDEN_SUITE_STATUS')
        for field,total in counts.items():
            literal=suite.attrib.get(field)
            if literal is None or not re.fullmatch(r'[0-9]+',literal) or int(literal)!=total:raise ValueError('JUNIT_AGGREGATE_MISMATCH')
        cases+=direct
    if len(cases)!=PINS['suite_case_counts'][component]:raise ValueError('JUNIT_CASE_COUNT')
    if any(x.find('failure') is not None or x.find('error') is not None for x in cases):raise ValueError('JUNIT_FAILURE_OR_ERROR')
    skipped=[x for x in cases if x.find('skipped') is not None]
    allowed=Counter(tuple(x) for x in PINS['expected_skips'][component][identity])
    if original_system and component=='core' and identity=='root':
        allowed[('tests.test_assembly','test_static_run_prefix_is_the_readme_argv_at_the_release','HOSTOPS02_TEST_RELEASE_REPOSITORY (a checkout that holds dd4ec4bb) is not set')]+=1
    observed=Counter((x.attrib.get('classname'),x.attrib.get('name'),x.find('skipped').attrib.get('message')) for x in skipped)
    if observed!=allowed:raise ValueError('UNEXPECTED_OR_MISSING_PLATFORM_OMISSION')
    names=Counter((x.attrib.get('classname'),x.attrib.get('name')) for x in cases)
    if component=='core' and names!=Counter(tuple(x) for x in PINS['core_case_names']):raise ValueError('CORE_JUNIT_CASE_COLLECTION')
    if collected is not None:
        receipt=json.loads(raw(collected))
        if receipt.get('pytest_returncode')!=0 or names!=Counter(tuple(x) for x in receipt.get('cases',[])):raise ValueError('JUNIT_COLLECTED_CASE_COLLECTION')
    if component=='family' and not original_system and collected is None:raise ValueError('FAMILY_COLLECTION_MISSING')
    if any(not a or not b or n!=1 for (a,b),n in names.items()):raise ValueError('JUNIT_EMPTY_OR_DUPLICATE_CASE_NAME')
    return {'sha256':digest(data),'cases':len(cases),'passed':len(cases)-len(skipped),'omissions':len(skipped),'omitted_cases':[{'classname':x.attrib.get('classname'),'name':x.attrib.get('name'),'reason':x.find('skipped').attrib.get('message')} for x in skipped],'case_name_sha256':sorted(digest((a+'\0'+b).encode()) for a,b in names)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--part',choices=['core','family','mutations','secret-config','original-linux-root'],required=True);ap.add_argument('--python',required=True);ap.add_argument('--label',choices=['py39','py312'],required=True);ap.add_argument('--repo',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    guard();before=snapshot();out=Path(a.out)
    if out.exists() or out.is_symlink():raise ValueError('OUTPUT_EXISTS')
    out.parent.mkdir(parents=True,exist_ok=True);out.mkdir(mode=0o700)
    result={'schema':'CURRENT_K3K9_CI_PROOF_V1','status':'HOLD','part':a.part,'label':a.label,'candidate_run':True,'operational_dispatch':False,'records':[],'source_pins':PINS['units'],'core_engine_shapes':'PENDING_ORIGINAL_LINUX_ROOT_PART' if a.part=='original-linux-root' else 'NOT_RUN_IN_THIS_SELECTED_PART','original_engine_inner_streams':'original mutation engine merges stdout/stderr and retains normalized summaries; wrapper streams remain raw'}
    work=None
    def run(name,argv,env=None,timeout=1800,cwd=None,retain_nonzero=False):
        row={'name':name,'argv':argv,'returncode':'NOT_STARTED'};result['records'].append(row)
        try:
            done=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,cwd=cwd,timeout=timeout);stdout,stderr=done.stdout,done.stderr;row['returncode']=done.returncode
        except subprocess.TimeoutExpired as error:
            stdout=error.stdout or b'';stderr=error.stderr or b'';row['returncode']='TIMEOUT'
        except OSError as error:
            stdout=b'';stderr=(type(error).__name__+': '+str(error)).encode();row['returncode']='OSERROR'
        write(out/(name+'.stdout'),stdout);write(out/(name+'.stderr'),stderr)
        row.update({'stdout_sha256':digest(stdout),'stderr_sha256':digest(stderr),'stdout_bytes':len(stdout),'stderr_bytes':len(stderr)})
        if row['returncode']!=0 and not retain_nonzero:raise ValueError('COMMAND_FAILED '+name)
        return stdout
    try:
        executable=Path(a.python).resolve()
        if not re.fullmatch(r'/opt/hostedtoolcache/Python/3\.(9|12)\.[0-9]+/x64/bin/python[0-9.]*',str(executable)):raise ValueError('NOT_SELECTED_ACTION_EXECUTABLE')
        est=executable.stat()
        observation={'realpath':str(executable),'file_type_bits':stat.S_IFMT(est.st_mode),
                     'regular':stat.S_ISREG(est.st_mode),'mode_octal':format(stat.S_IMODE(est.st_mode),'04o'),
                     'uid':est.st_uid,'gid':est.st_gid,'nlink':est.st_nlink,'device':est.st_dev,'inode':est.st_ino,
                     'size':est.st_size,'mtime_ns':est.st_mtime_ns,'ctime_ns':est.st_ctime_ns,
                     'buffer_sha256':None,'buffer_read_error':None}
        result['selected_executable_observation']=observation
        if stat.S_ISREG(est.st_mode):
            try:observation['buffer_sha256']=digest(executable.read_bytes())
            except OSError as error:observation['buffer_read_error']=type(error).__name__+': '+str(error)
        if not stat.S_ISREG(est.st_mode) or est.st_mode&0o022:raise ValueError('UNSAFE_SELECTED_EXECUTABLE')
        executable_before=digest(executable.read_bytes())
        version=json.loads(run('python-version',[a.python,'-I','-B','-c','import json,platform,sys;print(json.dumps({"python":platform.python_version(),"executable":sys.executable}))']))
        if not version['python'].startswith('3.9.' if a.label=='py39' else '3.12.'):raise ValueError('SELECTED_PYTHON_VERSION')
        result['python']=version
        result['python']['executable_sha256']=executable_before
        work=Path(tempfile.mkdtemp(prefix='current-k3k9-',dir=os.environ['RUNNER_TEMP']))
        core=work/'core';family=work/'k3k9_secrets'
        shutil.copytree(PACKAGE/'units/core',core);shutil.copytree(PACKAGE/'units/k3k9_secrets',family)
        baseline=PACKAGE/'baseline/hostops01'
        repo=Path(a.repo).resolve();release=work/'release';release.mkdir(mode=0o700)
        archive=work/'release.tar'
        # Source input is written directly to private scratch, never to proof logs or artifacts.
        run('release-archive',['/usr/bin/git','-C',str(repo),'archive','--format=tar','--output='+str(archive),PINS['release_commit'],*PINS['release_files']])
        run('release-extract',['/usr/bin/tar','-xf',str(archive),'-C',str(release)])
        for name,pin in PINS['release_files'].items():
            if digest(raw(release/name))!=pin:raise ValueError('CERTIFIED_RELEASE_FILE_PIN')
        env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','HOME':str(work),'HOSTOPS02_TEST_CORE':str(core),'HOSTOPS02_TEST_RELEASE_TREE':str(release),'HOSTOPS02_TEST_RELEASE_REPOSITORY':str(repo),'HOSTOPS02_TEST_HOSTOPS01_DIR':str(baseline)}
        if a.part in ('core','family'):
            component=a.part;directory=core if component=='core' else family
            run('author-seal-'+component,[a.python,'-I','-B',str(directory/'seal.py'),'check'],env)
            if component=='family':
                assembled=run('assembly',[a.python,'-I','-B',str(core/'assemble.py'),'--check',str(family)],env)
                if assembled.strip()!=b'BUILD_EQUAL':raise ValueError('ASSEMBLY_NOT_EQUAL')
            for identity in ('user','root'):
                target=out/('TESTS.'+identity+'.xml');temp=work/('pytest-'+component+'-'+identity)
                collection=out/('COLLECTION.'+identity+'.json')
                argv=[a.python,'-B',str(PACKAGE/'proof/pytest_collection_driver.py'),str(collection),'-p','no:cacheprovider','--basetemp',str(temp),'--junitxml',str(target),'--rootdir',str(directory),'-q',str(directory/'tests')]
                if identity=='root':argv=['sudo','-n','env']+[k+'='+v for k,v in sorted(env.items())]+argv
                run('suite-'+identity,argv,env,timeout=7200,cwd=str(directory))
                result['records'][-1]['junit']=junit(target,component,identity,collected=collection)
        elif a.part=='mutations':
            for component,directory in [('core',core),('family',family)]:
                record='CURRENT.'+a.label+'.json';menv=dict(env,HOSTOPS_MUTATION_PYTHON=a.python,HOSTOPS_MUTATION_WORKERS='8',HOSTOPS_MUTATION_RECORD=record)
                run('anchors-'+component,[a.python,'-B',str(directory/'mutation/mutate.py'),'check'],menv)
                run('mutations-'+component,[a.python,'-B',str(directory/'mutation/mutate.py'),'run'],menv,timeout=14400,retain_nonzero=True)
                data=raw(directory/'mutation'/record);write(out/('MUTATION.'+component+'.json'),data)
                row=json.loads(data);expected=PINS['mutation_names'][component]
                manifest=PINS['units'][component]['manifest'];source=PACKAGE/PINS['units'][component]['path']
                source_rows=dict(line.split('  ',1)[::-1] for line in raw(source/manifest).decode().splitlines())
                record_pins=row.get('core_sha256' if component=='core' else 'operation_sha256')
                if not isinstance(record_pins,dict) or not record_pins or any(source_rows.get(n)!=v for n,v in record_pins.items()):raise ValueError('MUTATION_CONSUMED_SOURCE_PINS')
                if component=='family' and (row.get('core_seal_sha256')!=PINS['units']['core']['sha256'] or row.get('core_generation_sha256')!=digest(raw(PACKAGE/'units/core/assemble.py'))):raise ValueError('MUTATION_CORE_PIN')
                mutation_suite=ET.Element('testsuites');suite=ET.SubElement(mutation_suite,'testsuite',name='original-'+component+'-mutants',tests=str(len(row.get('results',[]))),failures=str(sum(x.get('killed') is not True for x in row.get('results',[]))),errors='0',skipped='0')
                for item in row.get('results',[]):
                    case=ET.SubElement(suite,'testcase',classname='original_mutation.'+component,name=str(item.get('mutant')),time=str(item.get('seconds',0)))
                    if item.get('killed') is not True:ET.SubElement(case,'failure',message='Original mutation engine did not kill this mutant').text=json.dumps(item,sort_keys=True)
                    ET.SubElement(case,'system-out').text=json.dumps(item,sort_keys=True)
                write(out/('MUTATION.'+component+'.xml'),ET.tostring(mutation_suite,encoding='utf-8',xml_declaration=True))
                if result['records'][-1]['returncode']!=0:raise ValueError('MUTATION_ENGINE_EXIT')
                if row.get('complete_run') is not True or Counter(x.get('mutant') for x in row.get('results',[]))!=Counter(expected):raise ValueError('MUTATION_COLLECTION')
                if row['counts']['survivors']!=0 or row['counts']['errors']!=0 or row['counts']['killed']!=len(expected) or row.get('survivors') or row.get('errors'):raise ValueError('MUTATION_SURVIVORS_OR_ERRORS')
                if any(x.get('killed') is not True or x.get('error') for x in row['results']):raise ValueError('MUTATION_CASE_FAILED')
                bounded=[x['mutant'] for x in row['results'] if x.get('returncode') is None]
                result['records'][-1]['mutation']={'sha256':digest(data),'total':len(expected),'killed':len(expected),'bounded_nontermination_original_engine_semantics':bounded,'survivors':0,'errors':0}
        elif a.part=='original-linux-root':
            # New compatible scratch layout allows the original root delta test to find its baseline.
            layout=work/'suite';layout.mkdir();original_core=layout/'core';original_family=layout/'k3k9_secrets'
            shutil.copytree(PACKAGE/'units/core',original_core);shutil.copytree(PACKAGE/'units/k3k9_secrets',original_family)
            shutil.copytree(baseline,work/'hostops01/candidate')
            shutil.copytree(release,original_family/'work/release')
            original_env=dict(env,HOSTOPS_THROWAWAY_RUNNER='yes',RUNNER_ENVIRONMENT='github-hosted',GITHUB_ACTIONS='true')
            run('original-linux-root',['/bin/sh',str(original_core/'linux_root/run.sh'),'../k3k9_secrets'],original_env,timeout=14400,cwd=str(original_core),retain_nonzero=True)
            original_exit=result['records'][-1]['returncode']
            outputs=original_core/'linux_root'
            # Keep literal NOT_RUN/error outputs too, before any parse or verdict.
            for original in sorted(outputs.glob('TESTS.*.xml'))+sorted(outputs.glob('SHAPES.*.json')):
                write(out/('RAW.'+original.name),raw(original))
            if original_exit!=0:raise ValueError('ORIGINAL_LINUX_ROOT_EXIT')
            system=run('original-system-python-version',['/usr/bin/python3','-I','-B','-c','import json,platform,sys;print(json.dumps({"python":platform.python_version(),"executable":sys.executable}))'],original_env)
            result['original_system_python']=json.loads(system)
            if not result['original_system_python']['python'].startswith('3.12.'):raise ValueError('ORIGINAL_SYSTEM_PYTHON_VERSION')
            outputs=original_core/'linux_root'
            original_cases={}
            for component,prefix in [('core',''),('family','k3k9_secrets.')]:
                for identity in ('root','user'):
                    original=outputs/('TESTS.'+prefix+'linux-'+identity+'.xml')
                    target=out/('ORIGINAL.'+component+'.'+identity+'.xml');write(target,raw(original))
                    info=junit(target,component,identity,original_system=True);original_cases[component+'.'+identity]=info
                    if component=='family':
                        names=Counter((x.attrib['classname'],x.attrib['name']) for x in ET.fromstring(raw(target)).findall('.//testcase'))
                        if 'family_names' in locals() and names!=family_names:raise ValueError('ORIGINAL_FAMILY_ROOT_USER_COLLECTION')
                        family_names=names
            shape_raw=raw(outputs/'SHAPES.linux-root.json');shape=json.loads(shape_raw)
            if shape.get('all_shapes_ran') is not True or shape.get('all_expectations_met') is not True or len(shape.get('shapes',{}))!=7 or len(shape.get('expectations',{}))!=25 or any(v is not True for v in shape['expectations'].values()):raise ValueError('ORIGINAL_CORE_ENGINE_SHAPES')
            write(out/'ORIGINAL.SHAPES.json',shape_raw)
            result['core_engine_shapes']='ORIGINAL_U1_TO_U7_COMPLETED';result['original_junit']=original_cases
        else:
            marker={'HOSTOPS_THROWAWAY_RUNNER':'yes','RUNNER_ENVIRONMENT':'github-hosted','GITHUB_ACTIONS':'true','PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1'}
            # Only the family's original proof touches Docker; production dispatcher is never called.
            run('fixture-image',['/usr/bin/docker','pull','python:3.12-slim'],marker,timeout=1200)
            body=json.loads(run('original-secret-config-proof',['sudo','-n','env']+[k+'='+v for k,v in sorted(marker.items())]+[a.python,'-I','-B',str(family/'linux_root/secret_config_proof.py')],marker,timeout=1200))
            if body.get('all_expectations_met') is not True or len(body.get('results',[]))!=7:raise ValueError('SECRET_CONFIG_PROOF')
            result['secret_config']=body
        result['status']='PASS_CURRENT_SCOPED_CI'
    except Exception as error:result['failure']=type(error).__name__+': '+str(error)
    finally:
        try:result['origin_before_after_equal']=before==snapshot()
        except Exception as error:result['origin_before_after_equal']=False;result['integrity_error']=type(error).__name__+': '+str(error)
        if not result['origin_before_after_equal']:result['status']='HOLD'
        # Scratch inputs, including the certified config, are never uploaded.
        if work is not None:
            try:
                if work.is_symlink() or work.parent.resolve()!=Path(os.environ['RUNNER_TEMP']).resolve() or not work.name.startswith('current-k3k9-'):raise ValueError('SCRATCH_CLEANUP_BOUNDARY')
                cleanup=['sudo','-n','/usr/bin/python3','-I','-B','-c','import shutil,sys;shutil.rmtree(sys.argv[1])',str(work)]
                run('scratch-cleanup',cleanup,timeout=300)
            except Exception as error:
                result['status']='HOLD';result['cleanup_error']=type(error).__name__+': '+str(error)
        if 'executable_before' in locals():
            result['executable_before_after_equal']=executable_before==digest(executable.read_bytes())
            if not result['executable_before_after_equal']:result['status']='HOLD'
    write(out/'RESULT.json',(json.dumps(result,indent=1,sort_keys=True)+'\n').encode())
    print(json.dumps({'status':result['status'],'part':a.part,'label':a.label,'records':len(result['records'])},sort_keys=True))
    return 0 if result['status']=='PASS_CURRENT_SCOPED_CI' else 1

if __name__=='__main__':raise SystemExit(main())
