"""Selo offline da nova familia: write fixa SHA256SUMS; check verifica sem escrever.
Nao mede host, nao gera GO e nao substitui prova Linux. Exige a suite local completa.
"""
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
CORE=HERE.parent/'core_bootstrap_identity'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(ok,code):
    if not ok:raise ValueError(code)
def document(path):return json.loads(path.read_bytes())
def listed():
    rows=[]
    for path in sorted(HERE.rglob('*')):
        require(not path.is_symlink(),'FAMILY_LINK_NOT_ALLOWED')
        if path.is_file() and path.relative_to(HERE).as_posix()!='SHA256SUMS':
            require(path.suffix!='.pyc' and '__pycache__' not in path.parts and '.pytest_cache' not in path.parts,'FAMILY_CACHE_NOT_ALLOWED')
            rows.append(path.relative_to(HERE).as_posix())
    return rows

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module

def check_inputs():
    core_seal=load(CORE/'seal.py','_bootstrap_core_seal_check')
    require(core_seal.main('check')==0,'CORE_SEAL_BROKEN')
    assembler=load(CORE/'assemble.py','_bootstrap_assembler_check')
    files=assembler.build(HERE)
    found={p.name:p.read_bytes() for p in (HERE/'build').iterdir() if p.is_file()}
    require(files==found,'ASSEMBLY_BUILD_MISMATCH')
    report=json.loads(files['ASSEMBLY.json'])
    recorded=document(HERE/'build/ASSEMBLY.json');require(report==recorded,'ASSEMBLY_REPORT_MISMATCH')
    validation=document(HERE/'VALIDATION.json');inventory=document(HERE/'validation/TEST_INVENTORY.json')
    require(validation['status']=='PASS_LOCAL_SYNTHETIC_ONLY','VALIDATION_SCOPE')
    require(validation['source_sha256']==recorded['source_sha256']==sha(HERE/'build/bootstrap_identity.py'),'VALIDATION_SOURCE_PIN')
    require(validation['core_sha256']==recorded['core_sha256']==sha(CORE/'assemble.py'),'VALIDATION_CORE_PIN')
    require(validation['core_manifest_sha256']==sha(CORE/'CORE_SHA256SUMS'),'VALIDATION_CORE_MANIFEST_PIN')
    require(validation['test_inventory_sha256']==sha(HERE/validation['test_inventory']),'VALIDATION_INVENTORY_PIN')
    require(validation['test_files']=={p.relative_to(HERE).as_posix():sha(p) for p in sorted((HERE/'tests').glob('*.py'))},'VALIDATION_TEST_BYTES')
    names=inventory['names'];require(inventory['case_count']==len(names)==151,'INVENTORY_CASE_COUNT')
    require(inventory['multiset_sha256']==hashlib.sha256(('\n'.join(sorted(names))+'\n').encode()).hexdigest(),'INVENTORY_MULTISET_PIN')
    require({run['interpreter']['slot'] for run in validation['runs']}=={'py39','py312'} and len(validation['runs'])==2,'VALIDATION_INTERPRETERS')
    for run in validation['runs']:
        require(run['exit_code']==0 and run['counts']=={'tests':151,'failures':0,'errors':0,'skipped':0},'VALIDATION_COUNTS')
        require(run['scope']=='LOCAL_SYNTHETIC_NOT_LINUX_HOST_L1_L2','VALIDATION_RUN_SCOPE')
        junit=HERE/'validation'/run['junit'];stdout=HERE/'validation'/run['stdout']
        require(sha(junit)==run['junit_sha256'] and sha(stdout)==run['stdout_sha256'],'VALIDATION_STREAM_PIN')
        root=ET.fromstring(junit.read_bytes());suites=list(root.iter('testsuite'));cases=list(root.iter('testcase'))
        actual={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
        require(actual==run['counts'] and len(cases)==151,'JUNIT_COUNTS')
        require(not list(root.iter('failure')) and not list(root.iter('error')) and not list(root.iter('skipped')),'JUNIT_RESULT')
        require(Counter(c.attrib['name'] for c in cases)==Counter(names),'JUNIT_CASE_MULTISET')
        ids=sorted(c.attrib['classname'].split('.tests.',1)[-1]+'::'+c.attrib['name'] for c in cases)
        require(ids==inventory['normalized_cases'],'JUNIT_NORMALIZED_CASE_MULTISET')
    interface=document(HERE/'INTERFACE.json')
    require(interface['source_sha256']==recorded['source_sha256'] and interface['required_item_count']==len(interface['required_items'])==40,'INTERFACE_SOURCE_OR_ITEMS')
    provenance=document(HERE/'PROVENANCE.json')
    require(provenance['source']==recorded['source_sha256'] and provenance['core_generation']==recorded['core_sha256'],'PROVENANCE_SOURCE_OR_CORE')
    return recorded

def main(mode):
    require(mode in ('write','check'),'USE_WRITE_OR_CHECK');report=check_inputs()
    sums=''.join('%s  %s\n'%(sha(HERE/name),name) for name in listed());path=HERE/'SHA256SUMS'
    if mode=='write':path.write_text(sums,encoding='ascii')
    else:require(path.is_file() and path.read_text(encoding='ascii')==sums,'FAMILY_SEAL_BROKEN')
    print(json.dumps({'status':'FAMILY_SEAL_OK_LOCAL_ONLY','manifest_sha256':sha(path),'files':len(listed()),'source_sha256':report['source_sha256'],'core_sha256':report['core_sha256']},sort_keys=True));return 0

if __name__=='__main__':
    try:raise SystemExit(main(sys.argv[1] if len(sys.argv)==2 else ''))
    except (ValueError,KeyError,OSError,ET.ParseError) as error:
        print('FAMILY_SEAL_REFUSED '+str(error));raise SystemExit(1)
