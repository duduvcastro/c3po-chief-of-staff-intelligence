"""Mandatory current-source PROBE Linux tests; never called on an operational host.
Private copies alone receive mutation outputs. All inherited omissions remain history.
"""
import hashlib, importlib.util, json, os, stat, sys, math, types, re
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

VERSION_FULL_PROBE="import json,os,sys; print(json.dumps({'version':list(sys.version_info[:2]),'full_version':sys.version.split()[0],'uid':os.getuid(),'euid':os.geteuid()}))"
PROOF_FILES=('probe_tests.py','PROBE_TEST_EXPECTATIONS.json','bootstrap_tests.py','offline_conformance_tests.py','run_group.py')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(value,code):
    if not value:raise ValueError(code)
def exact_count(value,expected):return type(value) is int and value==expected
def inspect_suite(raw,bootstrap,expect):
    counts,cases=bootstrap._junit_layout(raw)
    need(counts=={'tests':618,'failures':0,'errors':0,'skipped':0},'PROBE_FULL_SUITE_FAILED_OR_OMITTED')
    names=[sha(c.get('name').encode()) for c in cases]
    need(Counter(names)==Counter(expect['full_case_name_sha256']),'PROBE_COMPLETE_COLLECTION_DIFFERS')
    need(len(expect['morning_case_name_sha256'])==28 and set(expect['morning_case_name_sha256'])<=set(names),'PROBE_MORNING_CASES_MISSING')
    return {'counts':counts,'passed':618,'omissions':0,'sha256':sha(raw),'collection_sha256':sha(json.dumps(sorted(names),separators=(',',':')).encode())}
def inspect_mutation(raw,expect):
    def pairs(values):
        result={}
        for key,value in values:
            need(key not in result,'MUTATION_DUPLICATE_FIELD');result[key]=value
        return result
    x=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('MUTATION_NONFINITE_JSON')))
    need(type(x) is dict and x.get('complete_run') is True,'MUTATION_NOT_FULL_CURRENT_SOURCE')
    wanted={'single':324,'combined':0,'killed':324,'survivors':0,'errors':0,'redundant_survivors':0}
    need(type(x.get('counts')) is dict and set(x['counts'])==set(wanted) and all(exact_count(x['counts'][k],v) for k,v in wanted.items()),'MUTATION_COUNTS_INCOMPLETE')
    need(x.get('errors')==[] and x.get('survivors')==[] and x.get('redundant_survivors')==[] and x.get('redundant')=={},'MUTATION_FAILURE_OR_REDUNDANT')
    rows=x.get('results');need(type(rows) is list and len(rows)==324,'MUTATION_ROWS_MISSING')
    need(Counter(r.get('mutant') for r in rows)==Counter(expect['mutants']),'MUTATION_COMPLETE_COLLECTION_DIFFERS')
    need(all(r.get('killed') is True and exact_count(r.get('returncode'),1) and not r.get('error') and not str(r.get('summary','')).startswith('TIME_LIMIT') for r in rows),'MUTATION_ERROR_TIMEOUT_OR_SURVIVOR')
    need(all(type(r.get('seconds')) in (int,float) and math.isfinite(r['seconds']) and r['seconds']>=0 for r in rows),'MUTATION_TIMING_INVALID')
    need(x.get('operation_sha256')==expect['operation_sha256'] and x.get('core_seal_sha256')==expect['core_sha256'] and x.get('core_generation_sha256')==expect['core_generation_sha256'],'MUTATION_CONSUMED_INPUT_PINS')
    return x

def mutation_junit(record):
    root=ET.Element('testsuites');suite=ET.SubElement(root,'testsuite',name='current_source_mutation_record',tests='324',failures='0',errors='0',skipped='0',time=str(sum(float(r['seconds']) for r in record['results'])))
    for r in record['results']:ET.SubElement(suite,'testcase',classname='literal_mutation_record',name=r['mutant'],time=str(r['seconds']))
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)

def run_step(group,family_directory,core_directory,documents_directory,root,here,binder,run_probe):
    """Only Group's guarded GitHub runner calls this. Local controls inspect buffers."""
    loaded={}
    def consumed_module(name):
        path=os.path.join(here,name+'.py');raw=binder.read_regular(path)
        module=types.ModuleType('_current_probe_'+name);module.__file__=path;loaded[name+'.py']=sha(raw)
        exec(compile(raw,path,'exec'),module.__dict__);return module
    bootstrap=consumed_module('bootstrap_tests');copyhelper=consumed_module('offline_conformance_tests')
    out=Path(group.out);detail={'schema':'HOSTOPS02_CURRENT_PROBE_CI_V1','scope':'Actual offline Linux PROBE suite and current-source mutation campaign, including test-only primitives; no actual Docker/systemd/operational host/GO proof','layers':{},'complete':False}
    before=None;proof_before=None;selected=[]
    def write(name,raw):
        (out/name).write_bytes(raw);return {'file':name,'sha256':sha(raw)}
    def call(argv,row,label,env,cwd,timeout):
        status,stdout,stderr,seconds=run_probe(argv,cwd=str(cwd),env=env,timeout=timeout)
        stdout=stdout or '';stderr=stderr or ''
        row.setdefault('commands',[]).append({'stage':label,'status':status,'elapsed_seconds':seconds,'stdout':write('PROBE.'+label+'.stdout.txt',stdout.encode()),'stderr':write('PROBE.'+label+'.stderr.txt',stderr.encode())})
        group.record('probe-tests '+label,status,None,seconds)
        return status,stdout,stderr
    try:
        need(sys.platform.startswith('linux') and os.geteuid()!=0 and os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes','PROBE_REQUIRES_NONROOT_THROWAWAY_GITHUB_LINUX')
        need(group.app_python and group.release_tree,'PROBE_REAL_APP_OR_RELEASE_UNAVAILABLE')
        expect_raw=bootstrap.read_regular(os.path.join(here,'PROBE_TEST_EXPECTATIONS.json'));expect=json.loads(expect_raw)
        need(exact_count(expect.get('full_count'),618) and exact_count(expect.get('mutation_count'),324) and len(expect.get('full_case_name_sha256',[]))==618 and len(expect.get('mutants',[]))==324 and len(set(expect['mutants']))==324,'PROBE_EXPECTATIONS_INCOMPLETE')
        for directory in (family_directory,core_directory,documents_directory):
            unit=next((u for u in group.units['units'] if u['dest']==directory),None);need(unit is not None,'PROBE_UNIT_ABSENT');selected.append(unit)
        before=[copyhelper.stable_unit(bootstrap,root,u) for u in selected];detail['units_before']=before
        need([x['manifest_sha256'] for x in before]==[expect[k] for k in ('family_sha256','core_sha256','documents_sha256')],'PROBE_UNIT_PINS_DIFFER')
        need(before[0]['files']['build/capacity_probe.py']['sha256']==expect['source_sha256'],'PROBE_CURRENT_SOURCE_PIN')
        need(all(before[0]['files'].get(name,{}).get('sha256')==pin for name,pin in expect['operation_sha256'].items()) and before[1]['files'].get('assemble.py',{}).get('sha256')==expect['core_generation_sha256'],'PROBE_MUTATION_EXPECTATIONS_NOT_CURRENT_LISTED_INPUTS')
        proof_before={n:sha(bootstrap.read_regular(os.path.join(here,n))) for n in PROOF_FILES};detail['proof_before']=proof_before
        need(all(proof_before[name]==pin for name,pin in loaded.items()) and globals().get('_CONSUMED_MODULE_SHA256')==proof_before['probe_tests.py'],'PROBE_COMPILED_HELPER_BUFFER_DIFFERS')
        for version,label in [([3,9],'py39'),([3,12],'py312')]:
            row={'complete':False};detail['layers'][label]=row;copies=[]
            try:
                py=Path(group.temp)/('hostops02-binder-%s-%s'%(group.name,label))/'bin/python';need(py.is_file(),'PROBE_REQUESTED_PYTHON_UNAVAILABLE_NO_FALLBACK')
                env={k:v for k,v in os.environ.items() if not k.startswith(('PYTHON','PYTEST','BIND_')) and k!='VIRTUAL_ENV'}
                env.update(PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
                status,stdout,stderr=call([str(py),'-I','-B','-c',VERSION_FULL_PROBE],row,label+'.version',env,root,60)
                observed=json.loads(stdout);need(status==0 and not stderr and observed.get('version')==version and observed.get('uid')==os.getuid() and observed.get('euid')==os.geteuid() and type(observed.get('full_version')) is str and re.fullmatch(r'%s\.%s\.[0-9]+'%tuple(version),observed['full_version']),'PROBE_INTERPRETER_IDENTITY')
                row['outer_interpreter']=observed
                status,stdout,stderr=call([group.app_python,'-I','-B','-c',binder.PROBE],row,label+'.app-version',env,root,60)
                need(status==0,'PROBE_APP_VERSION_UNAVAILABLE');row['app_interpreter_separate']=json.loads(stdout)
                base=Path(group.temp)/('probe-input-%s-%s'%(group.name,label));need(not os.path.lexists(base),'PROBE_PRIVATE_INPUT_EXISTS');base.mkdir(mode=0o700)
                for destination,unit,original in zip(('capacity_probe','core','documents'),selected,before):
                    target=base/destination;cu,cb=copyhelper.private_copy(bootstrap,root,unit,original,target);copies.append((cu,cb));need(copyhelper.same_bytes(original,cb),'PROBE_PRIVATE_COPY_DIFFERENT')
                operation=base/'capacity_probe';env.update(HOSTOPS02_TEST_CORE=str(base/'core'),HOSTOPS02_TEST_OPSART_TREE=str(base/'documents'),HOSTOPS02_TEST_RELEASE_TREE=group.release_tree,HOSTOPS02_TEST_APP_PYTHON=group.app_python)
                report=out/('TESTS.probe.%s.xml'%label)
                status,stdout,stderr=call([str(py),'-B','-m','pytest','-p','no:cacheprovider',str(operation/'tests'),'-q','-rfEs','--tb=short','--junitxml',str(report),'--basetemp',str(base/'pytest-work')],row,label+'.suite',env,base,7200)
                suite_raw=bootstrap.read_regular(str(report));row['junit']=inspect_suite(suite_raw,bootstrap,expect);need(status==0,'PROBE_FULL_SUITE_EXIT_NONZERO')
                record_name='MUTATION_CI.%s.json'%label;record_path=operation/'mutation'/record_name;need(not os.path.lexists(record_path),'PROBE_MUTATION_OUTPUT_EXISTS')
                env.update(HOSTOPS_MUTATION_PYTHON=str(py),HOSTOPS_MUTATION_RECORD=record_name,HOSTOPS_MUTATION_WORKERS='6')
                status,stdout,stderr=call([str(py),'-B',str(operation/'mutation/mutate.py'),'run'],row,label+'.mutation',env,operation,16800)
                raw=bootstrap.read_regular(str(record_path));parsed=inspect_mutation(raw,expect);need(status==0,'PROBE_MUTATION_EXIT_NONZERO')
                need(parsed.get('python')=='Python '+observed['full_version'],'PROBE_MUTATION_INTERPRETER_DIFFERS')
                row['mutation_raw']=write('MUTATION.probe.%s.json'%label,raw)
                row['mutation_record_derived_junit']=write('TESTS.probe.%s.mutation-record.xml'%label,mutation_junit(parsed))
                row['mutation_counts']=parsed['counts'];row['mutation_python_observed']=parsed['python'];row['derived_junit_scope']='One row per consumed literal current-source mutation outcome; not a pytest execution report.'
                need(bootstrap.read_regular(str(record_path))==raw,'PROBE_MUTATION_RECORD_CHANGED')
                expected_files=set(copies[0][1]['files'])|{'mutation/'+record_name}
                actual_files={p.relative_to(operation).as_posix() for p in operation.rglob('*') if p.is_file() or p.is_symlink()}
                need(actual_files==expected_files,'PROBE_UNEXPECTED_PRIVATE_FILE')
                row['complete']=True
            except Exception as e:row['refusal']=str(e);row['error_type']=type(e).__name__;row['complete']=False
            finally:
                row['private_inputs_unchanged']=True
                try:
                    for cu,cb in copies:
                        # The mutation output and pytest/work trees are new external evidence; listed input bytes and modes must remain exact.
                        directory=base/cu['dest']
                        for rel,expected in cb['files'].items():
                            p=directory/rel;need(sha(bootstrap.read_regular(str(p)))==expected['sha256'] and stat.S_IMODE(p.stat().st_mode)==expected['mode'],'PROBE_PRIVATE_LISTED_INPUT_CHANGED')
                except Exception as e:row['private_inputs_unchanged']=False;row['private_integrity_refusal']=str(e)
                row['complete']=row['complete'] and row['private_inputs_unchanged']
        detail['complete']=len(detail['layers'])==2 and all(r['complete'] for r in detail['layers'].values())
    except Exception as e:detail['refusal']=str(e);detail['error_type']=type(e).__name__
    finally:
        try:
            detail['units_after']=[copyhelper.stable_unit(bootstrap,root,u) for u in selected];detail['units_unchanged']=before is not None and detail['units_after']==before
            detail['proof_after']={n:sha(bootstrap.read_regular(os.path.join(here,n))) for n in PROOF_FILES};detail['proof_unchanged']=proof_before is not None and detail['proof_after']==proof_before
        except Exception as e:detail['units_unchanged']=False;detail['proof_unchanged']=False;detail['integrity_refusal']=str(e)
        detail['complete']=detail['complete'] and detail.get('units_unchanged',False) and detail.get('proof_unchanged',False)
        write('PROBE.json',(json.dumps(detail,indent=1,sort_keys=True)+'\n').encode());group.record('probe-tests: current-source full collection, mutations and unchanged inputs',0 if detail['complete'] else 1,'PROBE.json')
    return detail['complete']
