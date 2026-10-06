"""Prova offline SUBSET_REGISTRY25: tres familias/tres nucleos, registry25 real integral.
Somente verify_family/accepted_seal/hostops02_core e assemble --check. Nao chama
prepare, sign, check-bound, sealed-copy, dispatch, transporte, Docker ou host.
"""
import argparse
from collections import Counter
import hashlib,json,os,platform,re,shutil,stat,subprocess,sys,tempfile,time,types
from pathlib import Path
import xml.etree.ElementTree as ET
SOURCE_SHA256='c5730380bae38027be58f1b34c49eca072611d03d1ebc2837f2604a0ee2cf3d2'
REGISTRY_SHA256='78eb4ab25db448d677b5c54bb2f91346c194427fee88028260d1ba2f7be50d72'
OLD_K3K9_SHA256='1eda0e5c483ee11b04f6babfe0de937296e56e6d3ba1f37714816b1bd784d7d7'
SUBSET=(('HOSTOPS02_BOOTSTRAP_IDENTITY','bootstrap_identity','7068c24fb3a771a5250e1070e46b6f98abb244d963809a668c331337493cf149'),
 ('HOSTOPS02_K3K9_SECRETS','k3k9_secrets','cbf694266a657e6c831f79c50171f3ba80349ff832425250c6fa871631517f79'),
 ('HOSTOPS02_K3_SECRET_ENV','k3_secret_env','de961bbf1f4969d1e650a097db3b002c8e784c48d24ed2dbee04a9279721f6f9'))
CASE_NAMES=['registry25_exact_with_three_unique_subset_rows']+['real_family_core_'+r[0] for r in SUBSET]+['selected_python_BUILD_EQUAL_'+r[0] for r in SUBSET]+[
 'refuses_swapped_bootstrap_core','refuses_genuine_superseded_K3K9_seal_metadata','refuses_altered_bootstrap_file','refuses_altered_binder_source','refuses_altered_registry_bytes','refuses_absent_BOOT_registry_row_DTO','refuses_ambiguous_BOOT_registry_row_DTO','input_bytes_and_modes_unchanged_after_all_cases']
class ProofRefused(ValueError):pass

def sha(raw):return hashlib.sha256(raw).hexdigest()
def require(ok,code):
    if not ok:raise ProofRefused(code)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def read_regular(path,limit=8*1024*1024):
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        first=os.fstat(fd);require(stat.S_ISREG(first.st_mode),'INPUT_NOT_REGULAR');blocks=[];size=0
        while True:
            b=os.read(fd,1048576)
            if not b:break
            size+=len(b);require(size<=limit,'INPUT_LIMIT');blocks.append(b)
        last=os.fstat(fd)
        require((first.st_dev,first.st_ino,first.st_size,first.st_mtime_ns,first.st_ctime_ns)==(last.st_dev,last.st_ino,last.st_size,last.st_mtime_ns,last.st_ctime_ns),'INPUT_CHANGED_WHILE_READ')
        return b''.join(blocks)
    finally:os.close(fd)
def pinned(path,pin,code,limit=8*1024*1024):
    raw=read_regular(path,limit);require(sha(raw)==pin,code);return raw

def load_binder(package):
    source_path=package/'selector/bind_once.py';registry_path=package/'selector/ACCEPTED_SEALS.json'
    source=pinned(source_path,SOURCE_SHA256,'BINDER_EXTERNAL_PIN',4*1024*1024)
    registry=pinned(registry_path,REGISTRY_SHA256,'REGISTRY_EXTERNAL_PIN',65536)
    m=types.ModuleType('_subset_registry25_pinned_binder');m.__file__=str(source_path);sys.modules[m.__name__]=m
    exec(compile(source,'PINNED_SUBSET_BINDER_SOURCE','exec'),m.__dict__)
    original=m.read_file
    def read_same_buffer(path,limit,code,**options):
        target=Path(os.path.abspath(str(path)))
        if target.name in ('bind_once.py','ACCEPTED_SEALS.json'):
            m.need(target in (source_path,registry_path),'PINNED_IDENTITY_PATH_CHANGED')
            raw=source if target==source_path else registry;m.need(len(raw)<=limit,code);return raw
        return original(path,limit,code,**options)
    m.read_file=read_same_buffer
    identity,rows=m.binder_identity()
    require(identity=={'binder_sha256':SOURCE_SHA256,'accepted_seals_sha256':REGISTRY_SHA256},'BINDER_SAME_BUFFER_IDENTITY')
    return m,rows

def subset_rows(m,rows):
    require(len(rows)==25,'REGISTRY_NOT_25');out=[];cores={}
    for name,directory,pin in SUBSET:
        row=m.accepted_seal(rows,pin);require(row['family']==name and row.get('core') is not None,'SUBSET_ROW_MISMATCH')
        key=m.core_directory_of(row);require(key not in cores,'SUBSET_CORE_ALIAS_OR_AMBIGUITY');cores[key]=row['core'];out.append((row,directory))
    require(len(out)==len(cores)==3,'SUBSET_CARDINALITY');return out,cores

def inventory(root):
    require(root.is_dir() and not root.is_symlink() and stat.S_IMODE(root.stat().st_mode)==0o700,'INPUT_ROOT_NOT_PRIVATE')
    files={}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(),'INPUT_LINK')
        require(stat.S_IMODE(path.stat().st_mode)==(0o700 if path.is_dir() else 0o600),'INPUT_MODE')
        if path.is_file():files[path.relative_to(root).as_posix()]={'sha256':sha(read_regular(path)),'mode_octal':'0600'}
    return files

def write(path,raw):
    missing=[];p=path.parent
    while not p.exists():missing.append(p);p=p.parent
    for directory in reversed(missing):directory.mkdir(mode=0o700)
    require(stat.S_IMODE(path.parent.stat().st_mode)==0o700,'OUTPUT_PARENT_NOT_PRIVATE')
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        data=memoryview(raw)
        while data:
            n=os.write(fd,data);require(n>0,'OUTPUT_WRITE_ZERO');data=data[n:]
    finally:os.close(fd)

def streams(evidence,label,done):
    stdout=done.stdout or b'';stderr=done.stderr or b'';write(evidence/(label+'.stdout'),stdout);write(evidence/(label+'.stderr'),stderr)
    return {'exit_code':done.returncode,'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),'stdout_bytes':len(stdout),'stderr_bytes':len(stderr)}

def bounded(command,seconds,evidence,label,**options):
    try:done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=seconds,**options)
    except subprocess.TimeoutExpired as error:
        write(evidence/(label+'.timeout.stdout'),error.stdout or b'');write(evidence/(label+'.timeout.stderr'),error.stderr or b'')
        raise ProofRefused('SUBPROCESS_TIMEOUT_PARTIAL_STREAMS_PRESERVED') from None
    return done,streams(evidence,label,done)

def copy_private(source,target):
    target.mkdir(mode=0o700)
    for path in sorted(source.rglob('*')):
        require(not path.is_symlink(),'COPY_INPUT_LINK');rel=path.relative_to(source)
        if path.is_dir():(target/rel).mkdir(mode=0o700)
        else:write(target/rel,read_regular(path))

def real_family(m,root,row,directory):
    family=m.verify_family(root/directory)
    seal=m.accepted_seal(m.binder_identity()[1],family['sums_sha256'])
    require(seal==row,'REAL_SELECTED_ROW_MISMATCH')
    record=json.loads(family['files']['build/ASSEMBLY.json'])
    op=m.select_operation(family,record['operation']);rt=m.load_runtime(op['files'],op['source_name'],op['directory'])
    return family,seal,op,rt

def observed_core(m,arguments,evidence,label,children):
    original=m.subprocess.run;prior=tempfile.tempdir;tempfile.tempdir=str(evidence)
    def observe(command,**options):
        require(type(command) is list and command[-2]=='--check' and Path(command[-3]).name=='assemble.py','UNEXPECTED_CHILD_COMMAND')
        child_label=label+'_system_child_'+str(len(children));slot='SYSTEM_/usr/bin/python3' if command[0]=='/usr/bin/python3' else 'OTHER_CHILD_INTERPRETER'
        try:
            done=original(command,**options);detail=streams(evidence,child_label,done)
            children.append(dict(detail,interpreter_slot=slot,interpreter_path_sha256=sha(command[0].encode()),kind='REAL_BINDER_CORE_ASSEMBLY_CHECK'))
            return done
        except subprocess.TimeoutExpired as error:
            write(evidence/(child_label+'.timeout.stdout'),error.stdout or b'');write(evidence/(child_label+'.timeout.stderr'),error.stderr or b'')
            children.append({'kind':'REAL_BINDER_CORE_ASSEMBLY_CHECK','status':'TIMEOUT','interpreter_slot':slot});raise
    m.subprocess.run=observe
    try:return m.hostops02_core(*arguments)
    finally:m.subprocess.run=original;tempfile.tempdir=prior

def refusal(m,action,code):
    try:action()
    except m.Refused as error:
        require(str(error)==code,'WRONG_BINDER_REFUSAL');return {'refusal':str(error),'scope':'NEGATIVE_LOCAL_ONLY'}
    raise ProofRefused('BINDER_DID_NOT_REFUSE')
def proof_refusal(action,code):
    try:action()
    except ProofRefused as error:
        require(str(error)==code,'WRONG_INPUT_REFUSAL');return {'refusal':str(error),'scope':'NEGATIVE_INPUT_PIN_ONLY'}
    raise ProofRefused('INPUT_DID_NOT_REFUSE')

def main():
    ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('--python',required=True);ap.add_argument('--package',required=True);ap.add_argument('--evidence-out',required=True);args=ap.parse_args()
    package=Path(args.package).absolute();python=Path(args.python).absolute();out=Path(args.evidence_out).absolute()
    require(package.is_dir() and not package.is_symlink(),'PACKAGE_NOT_FOUND')
    require(not out.exists() and out.parent.is_dir(),'OUTPUT_NOT_FRESH')
    normalized=out.parent.resolve()/out.name;require(normalized!=package.resolve() and package.resolve() not in normalized.parents,'OUTPUT_INSIDE_INPUT')
    os.umask(0o077);m,rows=load_binder(package);selected,cores=subset_rows(m,rows);before=inventory(package/'families');require(len(before)==269,'SUBSET_FILE_COUNT')
    require({p.name for p in (package/'families').iterdir()}=={r[1] for r in selected}|set(cores),'SUBSET_EXACT_DIRECTORIES')
    identity_before=inventory(package/'selector');require(set(identity_before)=={'bind_once.py','ACCEPTED_SEALS.json'},'THIN_SELECTOR_FILE_SET')
    out.mkdir(mode=0o700);results=[];children=[]
    suite=ET.Element('testsuite',name='SUBSET_REGISTRY25',tests=str(len(CASE_NAMES)),failures='0',errors='0',skipped='0')
    def case(name,action):
        node=ET.SubElement(suite,'testcase',classname='SUBSET_REGISTRY25',name=name);begun=time.monotonic()
        try:detail=action();results.append({'case':name,'status':'PASS','detail':detail})
        except Exception as error:
            code=str(error) if isinstance(error,(ProofRefused,m.Refused)) else type(error).__name__
            ET.SubElement(node,'failure',message=code).text=code;results.append({'case':name,'status':'FAIL','code':code});suite.set('failures',str(int(suite.get('failures'))+1))
        finally:node.set('time',str(time.monotonic()-begun))
    probe_code="import json,platform;print(json.dumps({'implementation':platform.python_implementation(),'version':platform.python_version()}))"
    def registry_case():
        done,detail=bounded([str(python),'-I','-S','-B','-c',probe_code],30,out,'selected_python_probe');require(done.returncode==0,'SELECTED_PYTHON_PROBE_FAILED')
        selected_version=json.loads(done.stdout);system,system_detail=bounded(['/usr/bin/python3','-I','-B','-c',probe_code],30,out,'system_python_separate_probe')
        system_version=json.loads(system.stdout) if system.returncode==0 else None
        return {'registry_entries':25,'families_observed':3,'cores_observed':3,'selected_python':selected_version,'system_python_separately_observed':system_version,'selected_probe':detail,'system_probe':system_detail,'outer_helper':{'implementation':platform.python_implementation(),'version':platform.python_version()},'same_buffer_source_and_registry':True}
    case(CASE_NAMES[0],registry_case)
    for row,directory in selected:
        def action(row=row,directory=directory):
            values=real_family(m,package/'families',row,directory);core=observed_core(m,values,out,'core_'+directory,children)
            require(core['assembly_check']['answer']=='BUILD_EQUAL','REAL_CORE_NOT_BUILD_EQUAL')
            return {'family':row['family'],'manifest_sha256':row['sha256sums_sha256'],'core':row['core'],'real_APIs':['verify_family','accepted_seal','select_operation','load_runtime','hostops02_core'],'assembly_check':core['assembly_check'],'scope':'THREE_FAMILY_SUBSET_ONLY'}
        case('real_family_core_'+row['family'],action)
    for row,directory in selected:
        def action(row=row,directory=directory):
            cache=Path(tempfile.mkdtemp(prefix='selected-assembly-',dir=out));cache.chmod(0o700)
            core=package/'families'/m.core_directory_of(row)
            done,detail=bounded([str(python),'-I','-S','-B','-X','pycache_prefix='+str(cache),str(core/'assemble.py'),'--check',str(package/'families'/directory)],120,out,'selected_'+directory)
            require(done.returncode==0 and done.stdout==b'BUILD_EQUAL\n' and done.stderr==b'' and not list(cache.iterdir()),'SELECTED_ASSEMBLY_NOT_BUILD_EQUAL')
            return dict(detail,answer='BUILD_EQUAL',interpreter='EXPLICIT_SELECTED_PYTHON_NOT_SYSTEM_CHILD',core_generation=row['core']['generation_sha256'])
        case('selected_python_BUILD_EQUAL_'+row['family'],action)
    boot_row,boot_dir=selected[0]
    def swapped():
        root=out/'wrong-core';root.mkdir(mode=0o700);copy_private(package/'families'/boot_dir,root/boot_dir)
        copy_private(package/'families/core_k3k9',root/'core_bootstrap_identity')
        values=real_family(m,root,boot_row,boot_dir)
        return refusal(m,lambda:m.hostops02_core(*values),'CORE_SEAL_NOT_ACCEPTED')
    case('refuses_swapped_bootstrap_core',swapped)
    case('refuses_genuine_superseded_K3K9_seal_metadata',lambda:dict(refusal(m,lambda:m.accepted_seal(rows,OLD_K3K9_SHA256),'FAMILY_SEAL_NOT_ACCEPTED'),genuine_prior_manifest_sha256=OLD_K3K9_SHA256,scope='REAL_PRIOR_SEAL_LOOKUP_METADATA_ONLY_NOT_OLD_FAMILY_EXECUTION'))
    def altered_file():
        root=out/'bad-file';root.mkdir(mode=0o700);copy_private(package/'families'/boot_dir,root/boot_dir)
        file=root/boot_dir/'op.py';file.write_bytes(file.read_bytes()+b'\n# SYNTHETIC_FILE_HASH_NEGATIVE\n')
        return refusal(m,lambda:m.verify_family(root/boot_dir),'FAMILY_HASH')
    case('refuses_altered_bootstrap_file',altered_file)
    for name,label,code in [('bind_once.py','refuses_altered_binder_source','BINDER_EXTERNAL_PIN'),('ACCEPTED_SEALS.json','refuses_altered_registry_bytes','REGISTRY_EXTERNAL_PIN')]:
        def action(name=name,code=code):
            root=out/('bad-'+name.replace('.','-'));root.mkdir(mode=0o700);copy_private(package/'selector',root/'selector')
            file=root/'selector'/name;file.write_bytes(file.read_bytes()+b'\nSYNTHETIC_PIN_NEGATIVE\n')
            return proof_refusal(lambda:load_binder(root),code)
        case(label,action)
    case('refuses_absent_BOOT_registry_row_DTO',lambda:dict(refusal(m,lambda:m.accepted_seal([r for r in rows if r['family']!=SUBSET[0][0]],SUBSET[0][2]),'FAMILY_SEAL_NOT_ACCEPTED'),scope='IN_MEMORY_NEGATIVE_DTO_NOT_AN_ACCEPTED_REGISTRY'))
    case('refuses_ambiguous_BOOT_registry_row_DTO',lambda:dict(refusal(m,lambda:m.accepted_seal(rows+[next(r for r in rows if r['family']==SUBSET[0][0])],SUBSET[0][2]),'FAMILY_SEAL_NOT_ACCEPTED'),scope='IN_MEMORY_NEGATIVE_DTO_NOT_AN_ACCEPTED_REGISTRY'))
    def integrity():
        require(inventory(package/'families')==before and inventory(package/'selector')==identity_before,'ORIGINAL_INPUTS_CHANGED')
        for path in out.rglob('*'):
            require(not path.is_symlink() and stat.S_IMODE(path.stat().st_mode)==(0o700 if path.is_dir() else 0o600),'OUTPUT_MODE_OR_LINK')
        return {'subset_input_files_before_after':268,'thin_selector_files_before_after':2,'hash_or_mode_divergences':0}
    case(CASE_NAMES[-1],integrity)
    require([r['case'] for r in results]==CASE_NAMES,'CASE_INVENTORY_MISMATCH')
    junit=ET.tostring(suite,encoding='utf-8',xml_declaration=True);write(out/'JUNIT.xml',junit)
    report={'schema':'SUBSET_REGISTRY25_OFFLINE_PROOF_V1','status':'PASS_SUBSET_REGISTRY25_LOCAL_ONLY' if all(r['status']=='PASS' for r in results) else 'FAIL_SUBSET_REGISTRY25','scope':'THREE_FAMILIES_THREE_CORES_ONLY_NOT_FULL25_COPY_NOT_LINUX_HOST_L1_L2','registry_entries':25,'families_observed':3,'cores_observed':3,'source_sha256':SOURCE_SHA256,'registry_sha256':REGISTRY_SHA256,'helper_sha256':sha(read_regular(Path(__file__))), 'cases':len(results),'passed':sum(r['status']=='PASS' for r in results),'failed':sum(r['status']=='FAIL' for r in results),'errors':0,'skipped':0,'expected_cases':CASE_NAMES,'case_inventory_sha256':sha(('\n'.join(sorted(CASE_NAMES))+'\n').encode()),'results':results,'real_binder_system_children_observed':children,'input_inventory_before_sha256':sha(canonical(before)),'input_thin_selector_before_sha256':sha(canonical(identity_before)),'operational_steps':0,'sealed_copy_full25':False,'prepare_sign_dispatch_transport_Docker_host':False,'Linux_acceptance_transfer':False,'junit_sha256':sha(junit)}
    write(out/'RESULT.json',(json.dumps(report,sort_keys=True,indent=2)+'\n').encode());print(json.dumps({k:report[k] for k in ('status','cases','passed','failed','errors','skipped','registry_entries','families_observed','cores_observed','operational_steps')},sort_keys=True));return 0 if report['failed']==0 else 1

if __name__=='__main__':raise SystemExit(main())
