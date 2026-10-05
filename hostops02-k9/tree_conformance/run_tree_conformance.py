#!/usr/bin/env python3
"""Eight actual sealed K9R TREE cases on its genuine memory host; no Native/host action."""
import argparse,copy,errno,hashlib,importlib.util,json,os,re,subprocess,sys,time,types
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET
FAMILY_SHA='248c2ae45d096ec3dfa8a845ecff8d1032f8d02bb71ec6cdfc019d70c7710c66'
CORE_SHA='73fb546b9758718924b73200b48b7c0582a156a60da200ff83f4ca66e9e5c9b1'
SOURCE_SHA='42521f6c17fe1a96ad07200b24c5786036b63ef4091753514f41e80ad3169d7f'
BINDER_SHA='bb255f8693d2213e5fad33c440bc4a6802f8122310c5384b192922f58fa49fc5'
CASE_NAMES=('actual_tree_before_first_k3_schema_and_source_rows','unexpected_secret_entry','provider_already_exists','emitter_permission_denied_is_not_absence','emitter_io_error_is_not_absence','below_floor','source_group_writable','runner_hash_wrong')
STATUS='PASS_REAL_K9R_EMULATED_TREE_SCHEMA_CONFORMANCE'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(value,code):
 if not value:raise ValueError(code)
def no_links(path):
 for p in (path,*path.parents):require(not p.is_symlink(),'PATH_SYMLINK')
def files_of(root):return sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink())
def verify_manifest(root,name,pin=None):
 path=root/name;no_links(path);raw=path.read_bytes()
 if pin:require(sha(raw)==pin,'MANIFEST_PIN')
 rows={}
 for line in raw.decode('ascii').splitlines():
  digest,rel=line.split('  ',1);require(re.fullmatch('[0-9a-f]{64}',digest) and rel and not rel.startswith('/') and all(x not in ('','..','.') for x in rel.split('/')) and rel not in rows,'MANIFEST_ROW_INVALID')
  p=root/rel;no_links(p);require(p.is_file() and sha(p.read_bytes())==digest,'MANIFEST_FILE_HASH');rows[rel]=digest
 require(set(files_of(root))==set(rows)|{name},'MANIFEST_FILE_SET')
 return rows,sha(raw)
def package_snapshot(root):
 rows,pin=verify_manifest(root,'SHA256SUMS');require(rows.get('k9_phase_read/SHA256SUMS')==FAMILY_SHA and rows.get('core/CORE_SHA256SUMS')==CORE_SHA and rows.get('k9_phase_read/build/k9_phase_read.py')==SOURCE_SHA and rows.get('binder/bind_once.py')==BINDER_SHA,'PACKAGE_INPUT_PINS')
 verify_manifest(root/'k9_phase_read','SHA256SUMS',FAMILY_SHA);verify_manifest(root/'core','CORE_SHA256SUMS',CORE_SHA)
 return {'manifest_sha256':pin,'files':rows}
def encoded(value):return json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True).encode()+b'\n'
def write_json(path,value):path.write_bytes(encoded(value))
def load_pinned(name,path,root,rows):
 no_links(path);raw=path.read_bytes();rel=path.relative_to(root).as_posix();require(sha(raw)==rows.get(rel),'CONSUMED_MODULE_HASH')
 module=types.ModuleType(name);module.__file__=str(path);module.__package__='';sys.modules[name]=module;exec(compile(raw,str(path),'exec'),module.__dict__);return module

def worker(root,out):
 require(os.getuid()!=0,'ROOT_FORBIDDEN');no_links(root);no_links(out);require(root.is_dir() and out.is_dir() and not any(out.iterdir()) and out!=root and root not in out.parents,'EVIDENCE_OUT_NOT_FRESH_EXTERNAL')
 before=package_snapshot(root);rows=before['files'];start=time.monotonic()
 def forbidden(*a,**kw):raise AssertionError('OPERATIONAL_OR_SUBPROCESS_ACTION_FORBIDDEN')
 subprocess.run=forbidden;subprocess.Popen=forbidden;subprocess.call=forbidden;subprocess.check_call=forbidden;subprocess.check_output=forbidden;os.system=forbidden
 # Genuine modules and f.load() remain unchanged; every build module gets the same-buffer pin loader.
 original_spec=importlib.util.spec_from_file_location
 class Loader:
  def __init__(self,path):self.path=Path(path)
  def create_module(self,spec):return None
  def exec_module(self,module):
   no_links(self.path);raw=self.path.read_bytes();rel=self.path.relative_to(root).as_posix();require(sha(raw)==rows.get(rel),'CONSUMED_BUILD_MODULE_HASH');exec(compile(raw,str(self.path),'exec'),module.__dict__)
 def spec(name,location,*args,**kwargs):
  path=Path(location).absolute();require(path==root or root in path.parents,'BUILD_MODULE_OUTSIDE_PACKAGE')
  value=original_spec(name,path,*args,**kwargs);value.loader=Loader(path);return value
 importlib.util.spec_from_file_location=spec
 sys.path[:0]=[str(root/'k9_phase_read/tests'),str(root/'core/tests')]
 hostemu=load_pinned('hostemu',root/'core/tests/hostemu.py',root,rows)
 f=load_pinned('family',root/'core/tests/family.py',root,rows)
 k9r=load_pinned('k9r',root/'k9_phase_read/tests/k9r.py',root,rows);k9r.ProbeContainer=lambda:forbidden
 b=load_pinned('_pinned_binder',root/'binder/bind_once.py',root,rows)
 def context(receipt):
  return {'operation':b.BOOTSTRAP_OPERATION,'entries':[{'role':'TREE_PRE','operation':b.K9R_OPERATION}],
   'receipts':{'TREE_PRE':copy.deepcopy(receipt)},'plan':{'evidence_boot_id_sha256':receipt['boot_id_sha256']},
   'window':{'start':datetime.fromisoformat('2026-10-06T20:43:00+00:00')},'blobs':{'TREE_PRE':{'source':'bound'}},
   'evidence_facts':[{'role':'TREE_PRE','complete':False,'not_complete_accepted_by_parameter':True,'source':'BOUND_SET','receipt_host_binding_is_the_one_of_this_set':True,'receipt_payload_is_the_sealed_source_of_that_operation':True,'exit_json_binds_these_bytes':True,'bound_set':{'stderr_empty':True,'exit_json_binds_config_request_go_and_output':True}}]}
 def produce(damage):
  docs,host=k9r.case('TREE',now=k9r.at('2026-10-06T20:40:00+00:00'));require(isinstance(host,hostemu.FakeHost),'HOST_NOT_GENUINE_FAKE');docs.k.m.Native=forbidden
  require(sha(docs.k.source)==SOURCE_SHA,'CONSUMED_PRODUCER_HASH')
  for name in ('provider_env_file','risk_db_env_file','emitter'):host.tree.remove(k9r.PLACEMENT[name])
  if damage:damage(docs,host)
  snapshot=host.tree.snapshot();receipt=docs.run(host);require(snapshot==host.tree.snapshot(),'MEMORY_HOST_MUTATED');require(not host.mutating() and not host.commands and not host.fds,'HOST_EFFECT_OR_DESCRIPTOR_LEAK');require(f.sealed(receipt),'RECEIPT_SEAL_INVALID')
  secrets=set(k9r.SEPTEMBER[1::3])|{k9r.PLACEMENT[x] for x in ('provider_env_file','risk_db_env_file','emitter_password')};require(not any(e[0]=='read' and e[1] in secrets for e in host.log),'SECRET_SOURCE_VALUE_READ')
  return receipt,host
 def extra(docs,host):host.tree.add(k9r.PLACEMENT['secrets']+'/extra',kind='file',mode=0o600,content=b'synthetic')
 def secret(docs,host):host.tree.add(k9r.PLACEMENT['provider_env_file'],kind='file',mode=0o600,content=b'synthetic')
 def error(number):
  def apply(docs,host):
   def hook(h,name,detail,calls):
    if name=='lstat' and detail[0]==k9r.PLACEMENT['emitter']:raise OSError(number,'synthetic error')
   host.hook=hook
  return apply
 def floor(docs,host):host.vfs[hostemu.ROOT_DEVICE].f_bavail=0
 def permissions(docs,host):host.tree.get(k9r.SEPTEMBER[0]).mode=0o770
 def runner(docs,host):host.tree.get(k9r.PLACEMENT['tools']+'/k9_runner-'+sha(k9r.RUNNER)+'.py').content=bytearray(b'changed synthetic runner')
 damages=(None,extra,secret,error(errno.EACCES),error(errno.EIO),floor,permissions,runner);results=[]
 for index,(name,damage) in enumerate(zip(CASE_NAMES,damages)):
  t=time.monotonic();record={'name':name,'passed':False}
  try:
   receipt,host=produce(damage)
   if index==0:
    role,tree=b.bootstrap_tree_pre(context(receipt));require(role=='TREE_PRE' and tree==receipt,'POSITIVE_TREE_MISMATCH')
    projected=b.bootstrap_source_rows(receipt['items']['september_sources']['components']);require(len(projected)==5 and all(set(r)=={'path','device','inode','uid','gid','mtime_ns','ctime_ns','mode'} for r in projected),'SOURCE_PROJECTION_SCHEMA');require([r['mode'] for r in projected]==[0o700,0o600,0o700,0o700,0o600],'SOURCE_PROJECTION_MODES')
    require([r['type'] for r in receipt['items']['september_sources']['components']]==['dir','file','dir','dir','file'],'REAL_PRODUCER_COMPONENT_TYPES');code='ACCEPTED_PARTIAL_TREE_SCHEMA'
   else:
    try:b.bootstrap_tree_pre(context(receipt))
    except b.Refused as e:code=str(e)
    else:raise AssertionError('GENUINE_BAD_TREE_ACCEPTED')
    expected='BOOTSTRAP_TREE_PRE_GAPS_NOT_EXACT' if index in (1,2) else 'BOOTSTRAP_TREE_PRE_NOT_ONE_PARTIAL_READ';require(code==expected,'REFUSAL_CODE_NOT_EXACT')
   rel='TREE.'+name+'.json';raw=encoded(receipt);(out/rel).write_bytes(raw)
   record.update(passed=True,receipt_file=rel,receipt_sha256=sha(raw),producer_status=receipt['status'],producer_outcome=receipt['outcome'],producer_findings=receipt['findings'],producer_items_not_complete=receipt['items_not_complete'],binder_result=code,host_commands=0,host_mutations=0,unclosed_descriptors=0,model_snapshot_unchanged=True)
  except Exception as exc:record.update(error_type=type(exc).__name__,error_code=str(exc).replace(str(root),'S/').replace(str(out),'W/'))
  record['seconds']=round(time.monotonic()-t,6);results.append(record)
 after=package_snapshot(root);require(before==after,'PACKAGE_CHANGED_AFTER')
 failed=sum(not r['passed'] for r in results);junit=ET.Element('testsuites');suite=ET.SubElement(junit,'testsuite',name='real_k9r_tree_conformance',tests='8',failures=str(failed),errors='0',skipped='0',time=str(round(time.monotonic()-start,6)))
 for r in results:
  node=ET.SubElement(suite,'testcase',classname='real_k9r_tree_conformance',name=r['name'],time=str(r['seconds']))
  if not r['passed']:ET.SubElement(node,'failure',message=r['error_code']).text=r['error_type']+': '+r['error_code']
 xml=ET.tostring(junit,encoding='utf-8',xml_declaration=True);(out/'TESTS.xml').write_bytes(xml)
 result={'schema':1,'status':STATUS if failed==0 else 'FAIL_REAL_K9R_EMULATED_TREE_SCHEMA_CONFORMANCE','python':{'version':sys.version,'executable_name':Path(sys.executable).name,'non_root':True},'family_sha256':FAMILY_SHA,'core_sha256':CORE_SHA,'source_sha256':SOURCE_SHA,'binder_source_sha256':BINDER_SHA,'scope':'Actual sealed K9R TREE executes only its genuine in-memory FakeHost. Binder context/BOUND facts are synthetic; no real BOUND verification, Linux/Docker/host/authority/GO proof. No Native, subprocess, host command or model mutation.','counts':{'tests':8,'passed':8-failed,'failures':failed,'errors':0,'omissions':0},'case_names':list(CASE_NAMES),'cases':results,'integrity':{'before':before,'after':after,'files_changed':0},'junit_sha256':sha(xml)}
 write_json(out/'RESULT.json',result);print(json.dumps(result,sort_keys=True));return 0 if failed==0 else 1

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--python');parser.add_argument('--package',required=True);parser.add_argument('--evidence-out',required=True);parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS);args=parser.parse_args()
 root=Path(args.package).absolute();out=Path(args.evidence_out).absolute();no_links(root);no_links(out);require(root.resolve()==root and out.resolve()==out,'PATH_NOT_CANONICAL')
 if args.worker:return worker(root,out)
 require(args.python and Path(args.python).is_absolute(),'EXPLICIT_PYTHON_REQUIRED');py=Path(args.python);require(py.is_file() and os.access(py,os.X_OK),'PYTHON_UNAVAILABLE');require(os.getuid()!=0,'ROOT_FORBIDDEN');require(not out.exists(),'EVIDENCE_OUT_ALREADY_EXISTS');require(out!=root and root not in out.parents,'EVIDENCE_UNDER_PACKAGE');package_snapshot(root);out.mkdir(mode=0o700)
 raw=(root/'run_tree_conformance.py').read_bytes();source=sha(raw);require(source==sha(Path(__file__).read_bytes()),'RUNNER_NOT_THE_PACKAGE_SOURCE')
 argv=[str(py),'-I','-B',str(root/'run_tree_conformance.py'),'--worker','--package',str(root),'--evidence-out',str(out)];proc=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
 sys.stdout.buffer.write(proc.stdout);sys.stderr.buffer.write(proc.stderr);return proc.returncode
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as exc:print(json.dumps({'schema':1,'status':'REFUSED_REAL_TREE_PROOF','code':str(exc),'error_type':type(exc).__name__},sort_keys=True),file=sys.stderr);raise SystemExit(2)
