"""Validate exact portable offline proof units; never operational or host proof."""
import hashlib, importlib.util, json, os, re, stat, sys
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

PROFILE_FILE='OFFLINE_CONFORMANCE_EXPECTATIONS.json'
PROOF_FILES=('offline_conformance_tests.py','bootstrap_tests.py',PROFILE_FILE,'binder_tests.py','run_group.py')
COUNT_KEYS=('tests','passed','failures','errors','skipped')
CHILD_LOADER=r'''import hashlib,os,stat,sys
path,pin=sys.argv[1:3]
os.umask(0o077)
if os.path.realpath(path)!=os.path.abspath(path):raise ValueError('HELPER_LINK')
fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
try:
 a=os.fstat(fd)
 if not stat.S_ISREG(a.st_mode):raise ValueError('HELPER_NOT_REGULAR')
 blocks=[]
 while True:
  raw=os.read(fd,1048576)
  if not raw:break
  blocks.append(raw)
 z=os.fstat(fd)
 if (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)!=(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns):raise ValueError('HELPER_CHANGED_WHILE_READ')
finally:os.close(fd)
consumed=b''.join(blocks)
if hashlib.sha256(consumed).hexdigest()!=pin:raise ValueError('HELPER_EXTERNAL_PIN')
sys.argv=[path]+sys.argv[3:]
__file__=path
exec(compile(consumed,path,'exec'),globals())
'''

def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(value,code):
    if not value:raise ValueError(code)
def exact(a,b):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(b,sort_keys=True,separators=(',',':'),allow_nan=False)
def json_buffer(raw):
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'JSON_DUPLICATE_KEY');result[key]=value
        return result
    def constant(value):raise ValueError('JSON_NONFINITE')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)
def field(value,path):
    for key in path.split('.'):
        need(type(value) is dict and key in value,'RESULT_FIELD_MISSING:'+path);value=value[key]
    return value

def relative(name):
    need(type(name) is str and name and not name.startswith('/') and all(p not in ('','.','..') for p in name.split('/')),'INVALID_RELATIVE_PATH');return name

def load_profile(consumed,directory):
    expectations=json_buffer(consumed)
    need(type(expectations) is dict and expectations.get('schema')==1 and type(expectations.get('schema')) is int,'PROFILE_SCHEMA')
    profiles=expectations.get('profiles');need(type(profiles) is dict and directory in profiles,'PROFILE_ABSENT')
    p=profiles[directory];need(type(p) is dict,'PROFILE_INVALID')
    required={'unit_sha256','helper_file','helper_sha256','result_schema','status','case_names','count','result_exact','stdout_fields','result_count_fields','result_case_names_field','junit_file','evidence_dir_mode'}
    need(required.issubset(p),'PROFILE_FIELDS')
    for key in ('unit_sha256','helper_sha256'):need(type(p[key]) is str and re.fullmatch('[0-9a-f]{64}',p[key]),'PROFILE_PIN')
    relative(p['helper_file']);relative(p['junit_file'])
    need(type(p['count']) is int and p['count']>0,'PROFILE_COUNT')
    need(type(p['case_names']) is list and len(p['case_names'])==p['count'] and len(set(p['case_names']))==p['count'] and all(type(v) is str and v for v in p['case_names']),'PROFILE_CASE_NAMES')
    need(type(p['result_exact']) is dict and p['result_exact'],'PROFILE_RESULT_EXACT')
    need(type(p['result_count_fields']) is dict and set(p['result_count_fields'])==set(COUNT_KEYS) and all(type(v) is str and v for v in p['result_count_fields'].values()),'PROFILE_COUNT_FIELDS')
    need(type(p['result_case_names_field']) is str and p['result_case_names_field'],'PROFILE_NAMES_FIELD')
    need(type(p['stdout_fields']) is list and len(set(p['stdout_fields']))==len(p['stdout_fields']) and all(type(v) is str and v for v in p['stdout_fields']),'PROFILE_STDOUT_FIELDS')
    need(p['evidence_dir_mode'] in ('FRESH_PATH','EMPTY_DIRECTORY'),'PROFILE_OUTPUT_MODE')
    extra=p.get('helper_extra_args',[]);need(type(extra) is list and extra in ([],['--worker']),'PROFILE_EXTRA_ARGS')
    need((p['evidence_dir_mode']=='EMPTY_DIRECTORY')==(extra==['--worker']),'PROFILE_WORKER_OUTPUT_CONTRACT')
    need(type(p['status']) is str and p['status'],'PROFILE_STATUS')
    return p

def stable_unit(bootstrap,root,unit):
    # verify_unit is the same full-unit verifier used by the bootstrap step.
    # These additional consumed reads reject links/FIFOs and check every sealed buffer.
    need(not unit.get('withheld'),'UNIT_WITHHELD');dest=relative(unit['dest']);seal=relative(unit['seal_file'])
    base=Path(root)/dest;need(os.path.realpath(base)==os.path.abspath(base),'UNIT_LINK_OR_ESCAPE')
    need(os.path.commonpath((str(Path(root).absolute()),str(base.absolute())))==str(Path(root).absolute()),'UNIT_ESCAPE')
    manifest=bootstrap.read_regular(str(base/seal));need(sha(manifest)==unit['seal_sha256'],'UNIT_EXTERNAL_PIN')
    rows={}
    for line in manifest.decode('utf-8').splitlines():
        pin,sep,name=line.partition('  ');need(sep and re.fullmatch('[0-9a-f]{64}',pin) and name not in rows,'UNIT_MANIFEST_INVALID');relative(name);rows[name]=pin
    found=set();files={};directories={}
    for folder,dirs,names in os.walk(base,followlinks=False):
        directories[os.path.relpath(folder,base)]=stat.S_IMODE(os.lstat(folder).st_mode)
        for name in dirs:need(stat.S_ISDIR(os.lstat(os.path.join(folder,name)).st_mode),'UNIT_DIRECTORY_LINK')
        for name in names:
            path=Path(folder)/name;need(stat.S_ISREG(os.lstat(path).st_mode),'UNIT_NONREGULAR');rel=path.relative_to(base).as_posix();found.add(rel)
            data=bootstrap.read_regular(str(path));files[rel]={'sha256':sha(data),'mode':stat.S_IMODE(os.lstat(path).st_mode)}
    need(found==set(rows)|{seal},'UNIT_FILE_SET')
    need(files[seal]['sha256']==unit['seal_sha256'] and all(files[n]['sha256']==pin for n,pin in rows.items()),'UNIT_BUFFER_HASH')
    verified=bootstrap.verify_unit(str(Path(root).absolute()),unit)
    need(verified['entries']==rows and verified['manifest_sha256']==sha(manifest),'UNIT_VERIFIER_DISAGREES')
    return {'unit':dest,'manifest_sha256':sha(manifest),'files':files,'directories':directories}

def required_equal(actual,required,path=''):
    if type(required) is dict:
        need(type(actual) is dict,'RESULT_EXACT_MISMATCH:'+path)
        for key,value in required.items():
            need(key in actual,'RESULT_EXACT_MISSING:'+path+key);required_equal(actual[key],value,path+key+'.')
    else:need(exact(actual,required),'RESULT_EXACT_MISMATCH:'+path)

def same_bytes(source,copy):
    return source['manifest_sha256']==copy['manifest_sha256'] and {k:v['sha256'] for k,v in source['files'].items()}=={k:v['sha256'] for k,v in copy['files'].items()} and set(source['directories'])==set(copy['directories'])

def private_copy(bootstrap,root,unit,before,target):
    need(not os.path.lexists(target),'PRIVATE_INPUT_NOT_FRESH')
    need(target.parent.is_dir() and os.path.realpath(target.parent)==os.path.abspath(target.parent),'PRIVATE_INPUT_PARENT_LINK')
    need(os.path.commonpath((str(Path(root).resolve()),str(target)))!=str(Path(root).resolve()),'PRIVATE_INPUT_UNDER_ORIGIN')
    target.mkdir(mode=0o700)
    for name in sorted(before['directories'],key=lambda n:(len(Path(n).parts),n)):
        if name!='.':(target/name).mkdir(mode=0o700)
    for name,expected in sorted(before['files'].items()):
        consumed=bootstrap.read_regular(str(Path(root)/unit['dest']/name));need(sha(consumed)==expected['sha256'],'ORIGIN_CHANGED_DURING_COPY')
        fd=os.open(str(target/name),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            data=memoryview(consumed)
            while data:
                n=os.write(fd,data);need(n>0,'PRIVATE_COPY_WRITE_ZERO');data=data[n:]
        finally:os.close(fd)
    copied_unit=dict(unit,dest=target.name)
    copied=stable_unit(bootstrap,str(target.parent),copied_unit)
    need(same_bytes(before,copied),'PRIVATE_COPY_BYTES_DIFFER')
    need(all(v['mode']==0o600 for v in copied['files'].values()) and all(v==0o700 for v in copied['directories'].values()),'PRIVATE_COPY_MODES')
    need(stable_unit(bootstrap,root,unit)==before,'ORIGIN_CHANGED_AFTER_COPY')
    return copied_unit,copied

def capture_case_receipts(bootstrap,evidence,out,report,profile,prefix):
    """Preserve each genuine emulated TREE producer buffer, not just its aggregate report."""
    if not profile.get('case_receipt_artifacts_required',False):return []
    rows=report.get('cases');need(type(rows) is list and len(rows)==profile['count'],'CASE_RECEIPT_ROWS_MISSING')
    need([r.get('name') for r in rows]==profile['case_names'],'CASE_RECEIPT_NAMES_DIFFER')
    artifacts=[];names=[]
    for row in rows:
        name=relative(row.get('receipt_file'));need('/' not in name and name=='TREE.'+row['name']+'.json','CASE_RECEIPT_FILE_NAME')
        pin=row.get('receipt_sha256');need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin),'CASE_RECEIPT_HASH')
        raw=bootstrap.read_regular(str(evidence/name));need(sha(raw)==pin,'CASE_RECEIPT_HASH_DIFFERS')
        receipt=json_buffer(raw);need(type(receipt) is dict and receipt.get('status')==row.get('producer_status') and receipt.get('outcome')==row.get('producer_outcome') and receipt.get('findings')==row.get('producer_findings') and receipt.get('items_not_complete')==row.get('producer_items_not_complete'),'CASE_RECEIPT_METADATA_DIFFERS')
        target=prefix+'.'+name;fd=os.open(str(out/target),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            data=memoryview(raw)
            while data:
                n=os.write(fd,data);need(n>0,'CASE_RECEIPT_WRITE_ZERO');data=data[n:]
        finally:os.close(fd)
        need(bootstrap.read_regular(str(evidence/name))==raw,'CASE_RECEIPT_CHANGED_AFTER_PARSE')
        artifacts.append({'case_name':row['name'],'file':target,'sha256':pin,'scope':'Genuine sealed K9R FakeHost producer buffer; synthetic context, not a real BOUND/host receipt.'});names.append(name)
    need({p.name for p in evidence.iterdir()}==set(names)|{'RESULT.json',profile['junit_file']},'CASE_RECEIPT_ARTIFACT_SET')
    return artifacts

def inspect_results(result_raw,junit_raw,stdout,p):
    report=json_buffer(result_raw);need(type(report) is dict,'RESULT_NOT_OBJECT')
    need(exact(report.get('schema'),p['result_schema']) and report.get('status')==p['status'],'RESULT_SCHEMA_OR_STATUS')
    required_equal(report,p['result_exact'])
    counts={k:field(report,v) for k,v in p['result_count_fields'].items()}
    need(all(type(v) is int for v in counts.values()),'RESULT_COUNT_NOT_INTEGER')
    need(counts=={'tests':p['count'],'passed':p['count'],'failures':0,'errors':0,'skipped':0},'RESULT_INCOMPLETE_COUNTS')
    names=field(report,p['result_case_names_field']);need(type(names) is list and all(type(v) is str for v in names) and Counter(names)==Counter(p['case_names']),'RESULT_CASE_INVENTORY')
    need(b'<!DOCTYPE' not in junit_raw.upper() and b'<!ENTITY' not in junit_raw.upper(),'JUNIT_DECLARATION')
    node=ET.fromstring(junit_raw);suites=[node] if node.tag=='testsuite' else list(node) if node.tag=='testsuites' else []
    need(suites and all(s.tag=='testsuite' and not s.findall('testsuite') for s in suites),'JUNIT_SUITES')
    cases=[];jcounts={k:0 for k in ('tests','failures','errors','skipped')}
    for suite in suites:
        for key in jcounts:
            text=suite.get(key);need(type(text) is str and re.fullmatch('[0-9]+',text),'JUNIT_COUNT');jcounts[key]+=int(text)
        cases.extend(suite.findall('testcase'))
    need(jcounts=={'tests':p['count'],'failures':0,'errors':0,'skipped':0} and len(cases)==p['count'],'JUNIT_INCOMPLETE_COUNTS')
    need(len(list(node.iter('testcase')))==len(cases),'JUNIT_NESTED_CASE')
    need(not any(list(node.iter(tag)) for tag in ('failure','error','skipped')),'JUNIT_HIDDEN_FAILURE_OR_OMISSION')
    need(Counter(c.get('name') for c in cases)==Counter(p['case_names']),'JUNIT_CASE_INVENTORY')
    need(report.get('junit_sha256')==sha(junit_raw),'JUNIT_REPORTED_HASH')
    summary=json_buffer(stdout);need(type(summary) is dict,'STDOUT_NOT_OBJECT')
    if not p['stdout_fields']:need(exact(summary,report),'STDOUT_FULL_REPORT_DIFFERS')
    else:
        for key in p['stdout_fields']:need(exact(field(summary,key),field(report,key)),'STDOUT_FIELD_DIFFERS:'+key)
    return {'complete':True,'counts':counts,'case_names':names,'result_sha256':sha(result_raw),'junit_sha256':sha(junit_raw),'stdout_json_sha256':sha(stdout.encode()),'result':report}

def run_step(group,directory,root,here,binder,run_probe):
    """Both existing pinned venv layers; every refusal remains in OFFLINE.<unit>.json."""
    need(type(directory) is str and re.fullmatch('[A-Za-z0-9_-]+',directory),'INVALID_UNIT_DESTINATION')
    out=Path(group.out);detail={'schema':'HOSTOPS02_OFFLINE_CONFORMANCE_CI_V1','unit':directory,'scope':'Exact portable offline unit only; no host, GO, Docker, operational receipt or full registry copy proof','layers':{},'complete':False}
    bootstrap=None;unit=None;before=None;proof_before=None;profile=None
    def write(path,data):
        fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            view=memoryview(data)
            while view:
                n=os.write(fd,view);need(n>0,'LOG_WRITE_ZERO');view=view[n:]
        finally:os.close(fd)
    def probe(argv,label,row,env,timeout):
        try:status,stdout,stderr,elapsed=run_probe(argv,cwd=str(root),env=env,timeout=timeout)
        except Exception as error:
            status='TIMEOUT' if type(error).__name__=='TimeoutExpired' else 'NOT_STARTED:'+type(error).__name__
            stdout=getattr(error,'stdout',None) or getattr(error,'output',None) or '';stderr=getattr(error,'stderr',None) or str(error);elapsed=0
        stdout=stdout.decode('utf-8','replace') if isinstance(stdout,bytes) else stdout or '';stderr=stderr.decode('utf-8','replace') if isinstance(stderr,bytes) else stderr or ''
        for stream,value in (('stdout',stdout),('stderr',stderr)):
            path=out/('OFFLINE.%s.%s.%s.txt'%(directory,label,stream));data=value.encode();write(path,data)
        row.setdefault('commands',[]).append({'kind':label,'status':status,'elapsed_seconds':elapsed,'stdout_sha256':sha(stdout.encode()),'stderr_sha256':sha(stderr.encode()),'stdout_file':'OFFLINE.%s.%s.stdout.txt'%(directory,label),'stderr_file':'OFFLINE.%s.%s.stderr.txt'%(directory,label),'interpreter':argv[0]})
        return status,stdout,stderr
    try:
        need(os.geteuid()!=0,'OFFLINE_REQUIRES_NONROOT')
        need(type(group.name) is str and re.fullmatch('[A-Za-z0-9_-]+',group.name),'GROUP_NAME_INVALID')
        spec=importlib.util.spec_from_file_location('_offline_bootstrap_unit_verifier',Path(here)/'bootstrap_tests.py');bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
        proof_before={name:sha(bootstrap.read_regular(str(Path(here)/name))) for name in PROOF_FILES};detail['proof_files_before']=proof_before
        need(globals().get('_CONSUMED_MODULE_SHA256')==proof_before['offline_conformance_tests.py'],'EXECUTED_MODULE_BUFFER_DIFFERS')
        profile=load_profile(bootstrap.read_regular(str(Path(here)/PROFILE_FILE)),directory)
        need(proof_before[PROFILE_FILE]==sha(bootstrap.read_regular(str(Path(here)/PROFILE_FILE))),'PROFILE_CHANGED_WHILE_CONSUMED')
        selected=[u for u in group.units['units'] if u.get('dest')==directory];need(len(selected)==1,'UNIT_ABSENT_OR_AMBIGUOUS');unit=selected[0]
        need(unit.get('seal_sha256')==profile['unit_sha256'],'PROFILE_UNIT_PIN')
        before=stable_unit(bootstrap,root,unit);detail['before']=before
        helper=Path(root)/directory/profile['helper_file'];helper_raw=bootstrap.read_regular(str(helper))
        need(sha(helper_raw)==profile['helper_sha256'] and before['files'].get(profile['helper_file'],{}).get('sha256')==profile['helper_sha256'],'HELPER_PIN')
        detail['helper_before_sha256']=sha(helper_raw);detail['profile']=profile
        for version,label in [([3,9],'py39'),([3,12],'py312')]:
            row={'complete':False,'required_version':version,'private_input_unchanged':False};detail['layers'][label]=row
            copy_path=None;copy_unit=None;copy_before=None
            try:
                need(stable_unit(bootstrap,root,unit)==before,'UNIT_CHANGED_BEFORE_LAYER')
                python=Path(group.temp)/('hostops02-binder-%s-%s'%(group.name,label))/'bin/python';need(python.is_file(),'EXACT_LAYER_VENV_MISSING_NO_FALLBACK')
                env={k:v for k,v in os.environ.items() if not k.startswith(('BIND_','PYTEST_','PYTHON')) and k!='VIRTUAL_ENV'};env.update(PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
                status,text,stderr=probe([str(python),'-I','-B','-c',binder.VERSION_PROBE],label+'.version',row,env,60)
                need(type(status) is int and status==0 and not stderr,'INTERPRETER_PROBE_FAILED_OR_STDERR')
                observed=json_buffer(text);need(observed.get('version')==version and type(observed.get('euid')) is int and observed.get('euid')==os.geteuid() and observed['euid']!=0 and type(observed.get('uid')) is int and observed['uid']==os.getuid(),'INTERPRETER_VERSION_OR_NONROOT')
                row['observed_interpreter']=observed
                copy_path=Path(group.temp)/('offline-input-%s-%s-%s'%(group.name,directory,label))
                copy_unit,copy_before=private_copy(bootstrap,root,unit,before,copy_path)
                row['private_input_before']=copy_before;row['private_input_matches_authenticated_origin']=same_bytes(before,copy_before)
                helper=copy_path/profile['helper_file']
                need(sha(bootstrap.read_regular(str(helper)))==profile['helper_sha256'],'PRIVATE_HELPER_PIN')
                evidence=Path(group.temp)/('offline-%s-%s-%s'%(group.name,directory,label));need(not os.path.lexists(evidence),'EVIDENCE_NOT_FRESH')
                need(evidence.parent.is_dir() and os.path.realpath(evidence.parent)==os.path.abspath(evidence.parent),'EVIDENCE_PARENT_LINK')
                need(os.path.commonpath((str(Path(root).resolve()),str(evidence)))!=str(Path(root).resolve()),'EVIDENCE_UNDER_INPUT')
                if profile['evidence_dir_mode']=='EMPTY_DIRECTORY':evidence.mkdir(mode=0o700)
                argv=[str(python),'-I','-B','-c',CHILD_LOADER,str(helper),profile['helper_sha256']]+profile.get('helper_extra_args',[])+['--python',str(python),'--package',str(copy_path),'--evidence-out',str(evidence)]
                status,text,stderr=probe(argv,label+'.proof',row,env,600)
                row['proof_exit']=status
                captured={};row['artifact_capture_errors']={}
                for artifact,source_path in [('RESULT',evidence/'RESULT.json'),('JUNIT',evidence/profile['junit_file'])]:
                    try:
                        consumed=bootstrap.read_regular(str(source_path));target='OFFLINE.%s.%s.%s.%s'%(directory,label,artifact,'json' if artifact=='RESULT' else 'xml')
                        write(out/target,consumed);captured[artifact]=consumed;row[artifact.lower()+'_artifact']={'file':target,'sha256':sha(consumed),'consumed_buffer_preserved':True}
                    except Exception as error:row['artifact_capture_errors'][artifact]=str(error)
                need(type(status) is int and status==0,'OFFLINE_HELPER_FAILED');need(not stderr,'OFFLINE_HELPER_UNEXPECTED_STDERR')
                need(evidence.is_dir() and not evidence.is_symlink() and stat.S_IMODE(evidence.stat().st_mode)==0o700,'EVIDENCE_NOT_PRIVATE')
                result_path=evidence/'RESULT.json';junit_path=evidence/profile['junit_file']
                need(set(captured)=={'RESULT','JUNIT'},'RESULT_OR_JUNIT_UNAVAILABLE_OR_UNSAFE')
                result_raw=captured['RESULT'];junit_raw=captured['JUNIT']
                for folder,dirs,names in os.walk(evidence,followlinks=False):
                    need(stat.S_ISDIR(os.lstat(folder).st_mode) and stat.S_IMODE(os.lstat(folder).st_mode)==0o700,'EVIDENCE_DIRECTORY_NOT_PRIVATE')
                    for name in dirs:need(stat.S_ISDIR(os.lstat(os.path.join(folder,name)).st_mode) and stat.S_IMODE(os.lstat(os.path.join(folder,name)).st_mode)==0o700,'EVIDENCE_DIRECTORY_LINK_OR_MODE')
                    for name in names:need(stat.S_ISREG(os.lstat(os.path.join(folder,name)).st_mode) and stat.S_IMODE(os.lstat(os.path.join(folder,name)).st_mode)==0o600,'EVIDENCE_FILE_LINK_OR_MODE')
                row.update(inspect_results(result_raw,junit_raw,text,profile))
                row['individual_case_receipts']=capture_case_receipts(bootstrap,evidence,out,row['result'],profile,'OFFLINE.%s.%s'%(directory,label))
                need(bootstrap.read_regular(str(result_path))==result_raw and bootstrap.read_regular(str(junit_path))==junit_raw,'ARTIFACT_CHANGED_AFTER_CONSUMED_PARSE')
                row['helper_after_sha256']=sha(bootstrap.read_regular(str(helper)));need(row['helper_after_sha256']==sha(helper_raw),'HELPER_CHANGED_AFTER_LAYER')
                need(stable_unit(bootstrap,root,unit)==before,'UNIT_CHANGED_AFTER_LAYER')
            except Exception as error:
                row['complete']=False;row['refusal']=str(error);row['error_type']=type(error).__name__
            finally:
                try:
                    row['private_input_after']=stable_unit(bootstrap,str(copy_path.parent),copy_unit) if copy_path is not None and copy_unit is not None and copy_before is not None else None
                    row['private_input_unchanged']=copy_before is not None and row['private_input_after']==copy_before
                except Exception as error:row['private_input_unchanged']=False;row['private_input_integrity_refusal']=str(error)
                row['complete']=row['complete'] and row['private_input_unchanged']
        detail['complete']=len(detail['layers'])==2 and all(row['complete'] for row in detail['layers'].values())
    except Exception as error:detail['refusal']=str(error);detail['error_type']=type(error).__name__
    finally:
        try:
            detail['after']=stable_unit(bootstrap,root,unit) if bootstrap is not None and unit is not None and before is not None else None
            detail['unit_unchanged']=before is not None and detail['after']==before
        except Exception as error:detail['unit_unchanged']=False;detail['integrity_refusal']=str(error)
        try:
            detail['proof_files_after']={name:sha(bootstrap.read_regular(str(Path(here)/name))) for name in PROOF_FILES} if bootstrap is not None else None
            detail['proof_files_unchanged']=proof_before is not None and detail['proof_files_after']==proof_before
        except Exception as error:detail['proof_files_unchanged']=False;detail['proof_integrity_refusal']=str(error)
        detail['complete']=detail['complete'] and detail['unit_unchanged'] and detail['proof_files_unchanged']
        write(out/('OFFLINE.%s.json'%directory),(json.dumps(detail,sort_keys=True,indent=2)+'\n').encode())
        group.record('offline-conformance %s: exact cases in both layers and unchanged bytes'%directory,0 if detail['complete'] else 1,'OFFLINE.%s.json'%directory)
    return detail['complete']
