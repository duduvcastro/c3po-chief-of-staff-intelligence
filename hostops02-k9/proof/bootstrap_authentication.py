"""One mandatory external dry-gate authentication case, genuine synthetic documents.
No Native, clocks/effects/transport/real signature/authority. The binder's Untouchable guard remains real.
"""
import argparse,hashlib,importlib.util,json,os,sys,types
from pathlib import Path
import xml.etree.ElementTree as ET
BINDER_SHA='c5730380bae38027be58f1b34c49eca072611d03d1ebc2837f2604a0ee2cf3d2'
FAMILY_SHA='7068c24fb3a771a5250e1070e46b6f98abb244d963809a668c331337493cf149'
CORE_SHA='4e3aecd1826404b3d03425aaf866a0f8fe1152a0d99ba9b5c4a38613f14c110d'
CASE='test_current_binder_authenticate_accepts_morning_family_with_untouchable_dry_gate'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(v,c):
 if not v:raise ValueError(c)
def main():
 p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--output',required=True);a=p.parse_args();root=Path(a.root).absolute();out=Path(a.output).absolute()
 need(root.resolve()==root and out.resolve()==out and root not in out.parents and not out.exists(),'FRESH_EXTERNAL_OUTPUT_REQUIRED');need(os.geteuid()!=0,'ROOT_FORBIDDEN')
 bootstrap_path=Path(__file__).parent/'bootstrap_tests.py';raw=bootstrap_path.read_bytes();h=types.ModuleType('_auth_unit_helpers');h.__file__=str(bootstrap_path);exec(compile(raw,str(bootstrap_path),'exec'),h.__dict__)
 units=[{'dest':'bootstrap_identity','seal_file':'SHA256SUMS','seal_sha256':FAMILY_SHA},{'dest':'core_bootstrap_identity','seal_file':'CORE_SHA256SUMS','seal_sha256':CORE_SHA}]
 before=[h.verify_unit(str(root),u) for u in units];binder_path=root/'binder/bind/bind_once.py';binder_raw=h.read_regular(str(binder_path));need(sha(binder_raw)==BINDER_SHA,'CURRENT_BINDER_SOURCE_PIN')
 rows={}
 for unit,state in zip(units,before):
  for rel,pin in state['entries'].items():rows[str(root/unit['dest']/rel)]=pin
 original_spec=importlib.util.spec_from_file_location
 class Loader:
  def __init__(self,path):self.path=Path(path).absolute()
  def create_module(self,spec):return None
  def exec_module(self,module):
   raw=h.read_regular(str(self.path));need(sha(raw)==rows.get(str(self.path)),'CONSUMED_FAMILY_MODULE_HASH');exec(compile(raw,str(self.path),'exec'),module.__dict__)
 def exact_spec(name,path,*args,**kwargs):
  value=original_spec(name,path,*args,**kwargs);value.loader=Loader(path);return value
 importlib.util.spec_from_file_location=exact_spec
 def load(name,path):
  raw=h.read_regular(str(path));need(sha(raw)==rows.get(str(path)),'CONSUMED_FIXTURE_MODULE_HASH');m=types.ModuleType(name);m.__file__=str(path);sys.modules[name]=m;exec(compile(raw,str(path),'exec'),m.__dict__);return m
 sys.path[:0]=[str(root/'bootstrap_identity/tests'),str(root/'core_bootstrap_identity/tests')]
 load('hostemu',root/'core_bootstrap_identity/tests/hostemu.py');load('family',root/'core_bootstrap_identity/tests/family.py');fx=load('_current_auth_fixtures',root/'bootstrap_identity/tests/fixtures.py')
 b=types.ModuleType('_current_auth_binder');b.__file__=str(binder_path);sys.modules[b.__name__]=b;exec(compile(binder_raw,str(binder_path),'exec'),b.__dict__)
 docs,_=fx.case();rt={'source':docs.k.m,'source_bytes':docs.k.source};need(b.authenticate(rt,'core',docs.raw(),docs.now)=='ACCEPTED','DRY_FIRST_GATE_AUTHENTICATION_NOT_ACCEPTED')
 after=[h.verify_unit(str(root),u) for u in units];need(before==after and h.read_regular(str(binder_path))==binder_raw,'INPUT_BYTES_CHANGED')
 out.mkdir(mode=0o700);j=ET.Element('testsuites');s=ET.SubElement(j,'testsuite',name='current_binder_external_bootstrap_auth',tests='1',failures='0',errors='0',skipped='0');ET.SubElement(s,'testcase',classname='untouchable_dry_gate',name=CASE)
 xml=ET.tostring(j,encoding='utf-8',xml_declaration=True);(out/'TESTS.xml').write_bytes(xml)
 result={'schema':1,'status':'PASS_CURRENT_BINDER_DRY_GATE_AUTHENTICATION','case_names':[CASE],'counts':{'tests':1,'passed':1,'failures':0,'errors':0,'omissions':0},'binder_source_sha256':BINDER_SHA,'family_sha256':FAMILY_SHA,'core_sha256':CORE_SHA,'inputs_unchanged':True,'junit_sha256':sha(xml),'scope':'Genuine synthetic documents and binder authenticate Untouchable only; not prepare, signature, host, Linux, transport or authority.'}
 (out/'RESULT.json').write_text(json.dumps(result,indent=1,sort_keys=True)+'\n');print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as e:print(json.dumps({'status':'REFUSED_CURRENT_BINDER_DRY_GATE_AUTHENTICATION','error_type':type(e).__name__,'code':str(e)},sort_keys=True),file=sys.stderr);raise SystemExit(2)
