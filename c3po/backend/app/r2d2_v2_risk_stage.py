"""Private, bounded, one-attempt risk input staging. No provider/DB/worker calls."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

MAX_FILE=16*1024*1024
MAX_TOTAL=2*1024*1024*1024
MAX_FILES=12000
HEX=re.compile(r'(?!0{64}\Z)[0-9a-f]{64}\Z')

def need(value,code):
    if not value:raise ValueError(code)

def sha(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()

def unique(pairs):
    out={}
    for key,value in pairs:
        need(key not in out,'STAGE_DUPLICATE_JSON_KEY');out[key]=value
    return out

def document(raw):
    def reject(value):raise ValueError('STAGE_NONFINITE_JSON')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)

def relative(value):
    need(isinstance(value,str) and len(value)<=512,'STAGE_PATH_INVALID')
    p=PurePosixPath(value)
    need(not p.is_absolute() and p.as_posix()==value and 0<len(p.parts)<=8
         and all(part not in ('','..','.') and re.fullmatch(r'[A-Za-z0-9_.-]+',part) for part in p.parts),
         'STAGE_PATH_INVALID')
    return p

def read_private(path):
    path=Path(path)
    need(path.is_absolute() and '..' not in path.parts,'STAGE_PATH_INVALID')
    for p in (path,*path.parents):need(not p.is_symlink(),'STAGE_SYMLINK')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as h:
        s=os.fstat(h.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.geteuid() and s.st_nlink==1 and s.st_mode&0o077==0
             and s.st_size<=MAX_FILE,'STAGE_FILE_INVALID')
        raw=h.read(MAX_FILE+1);need(len(raw)<=MAX_FILE,'STAGE_FILE_LIMIT')
        return raw

def directory(path):
    path=Path(path)
    for parent in (path,*path.parents):need(not parent.is_symlink(),'STAGE_SYMLINK')
    s=path.stat()
    need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid() and s.st_mode&0o077==0,'STAGE_DIRECTORY_INVALID')

def references(value):
    out={}
    def walk(item,depth=0):
        need(depth<=32,'STAGE_JSON_DEPTH')
        if isinstance(item,dict):
            if 'path' in item or 'sha256' in item:
                need(set(item)=={'path','sha256'},'STAGE_REFERENCE_INVALID')
                key=str(relative(item['path']));digest=item['sha256']
                need(isinstance(digest,str) and HEX.fullmatch(digest),'STAGE_HASH_INVALID')
                need(key not in out or out[key]==digest,'STAGE_REFERENCE_CONFLICT');out[key]=digest
            else:
                for v in item.values():walk(v,depth+1)
        elif isinstance(item,list):
            for v in item:walk(v,depth+1)
    walk(value);need(0<len(out)<=MAX_FILES,'STAGE_FILE_COUNT');return out

def build_bundle(manifest_path,manifest_sha256):
    manifest_path=Path(manifest_path).absolute();directory(manifest_path.parent)
    need(HEX.fullmatch(manifest_sha256),'STAGE_HASH_INVALID')
    raw=read_private(manifest_path);need(sha(raw)==manifest_sha256,'STAGE_MANIFEST_CHANGED')
    doc=document(raw);refs=references(doc)
    need(manifest_path.name=='manifest.json' and 'manifest.json' not in refs,'STAGE_MANIFEST_NAME')
    files={'manifest.json':base64.b64encode(raw).decode()};total=len(raw)
    for name,digest in refs.items():
        body=read_private(manifest_path.parent/name);need(sha(body)==digest,'STAGE_INPUT_CHANGED')
        total+=len(body);need(total<=MAX_TOTAL,'STAGE_TOTAL_LIMIT')
        files[name]=base64.b64encode(body).decode()
    return {'schema':'CERTIFIED_RISK_INPUT_BUNDLE_V1','manifest_sha256':manifest_sha256,'files':files}

def validate_bundle(bundle,*,namespace,session,symbols,admission_sha256):
    need(isinstance(bundle,dict) and set(bundle)=={'schema','manifest_sha256','files'}
         and bundle['schema']=='CERTIFIED_RISK_INPUT_BUNDLE_V1','STAGE_BUNDLE_INVALID')
    encoded=bundle['files'];need(isinstance(encoded,dict) and 1<len(encoded)<=MAX_FILES+1,'STAGE_FILE_COUNT')
    need(HEX.fullmatch(bundle['manifest_sha256']),'STAGE_HASH_INVALID')
    rawfiles={};total=0
    for name,body in encoded.items():
        relative(name);need(isinstance(body,str) and len(body)<=((MAX_FILE+2)//3)*4,'STAGE_FILE_LIMIT')
        raw=base64.b64decode(body,validate=True);need(len(raw)<=MAX_FILE,'STAGE_FILE_LIMIT')
        total+=len(raw);need(total<=MAX_TOTAL,'STAGE_TOTAL_LIMIT');rawfiles[name]=raw
    raw=rawfiles['manifest.json'];need(sha(raw)==bundle['manifest_sha256'],'STAGE_MANIFEST_CHANGED')
    doc=document(raw);refs=references(doc)
    need(set(rawfiles)==set(refs)|{'manifest.json'},'STAGE_FILE_SET')
    for name,digest in refs.items():need(sha(rawfiles[name])==digest,'STAGE_INPUT_CHANGED')
    need(doc.get('schema')=='V2_RISK_REPLAY_MANIFEST_V1' and doc.get('namespace')==namespace
         and doc.get('session_date')==session and doc.get('mode')=='OFFLINE_REPLAY'
         and type(doc.get('phase_pending')) is int and doc['phase_pending']==0,'STAGE_SCOPE')
    need(doc.get('admission',{}).get('sha256')==admission_sha256,'STAGE_ADMISSION')
    names=[row['symbol'] for row in doc.get('symbols',[])]
    need(names==symbols and 0<len(names)<=550 and len(set(names))==len(names),'STAGE_LIST')
    return rawfiles

def write_new(path,raw):
    directory(path.parent)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
    sync(path.parent)

def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def stage(bundle,*,root,namespace,session,symbols,admission_sha256,order_sha256,pins_sha256,
          before_sha256,check_after,executor_binding):
    """Caller proves authority/preflight/time. check_after repeats baseline/time.

    Any interruption leaves .started and no acceptance; never replay automatically.
    Receipt and binding become usable only after both readback and post-check.
    """
    root=Path(root);directory(root);directory(root/'control')
    need(all(HEX.fullmatch(x) for x in (admission_sha256,order_sha256,pins_sha256,before_sha256)), 'STAGE_BINDINGS')
    rawfiles=validate_bundle(bundle,namespace=namespace,session=session,symbols=symbols,admission_sha256=admission_sha256)
    need(not (root/'risk-inputs').exists() and not (root/'risk-inputs').is_symlink(),'STAGE_PRIOR_ATTEMPT')
    marker={'schema':'CERTIFIED_RISK_STAGE_START_V1','namespace':namespace,'session':session,
            'owner_order_sha256':order_sha256,'pins_sha256':pins_sha256,'baseline_sha256':before_sha256,
            'manifest_sha256':bundle['manifest_sha256'],'admission_sha256':admission_sha256,
            'symbols_sha256':sha(('\n'.join(symbols)+'\n').encode('ascii')),
            'executor_binding':executor_binding}
    write_new(root/'control/risk-stage.started.json',encode(marker))
    tmp=Path(tempfile.mkdtemp(prefix='.risk-stage-',dir=root));os.chmod(tmp,0o700)
    for name,body in rawfiles.items():
        target=tmp/name
        for parent in reversed(target.parent.relative_to(tmp).parents):
            if str(parent)!='.':(tmp/parent).mkdir(mode=0o700,exist_ok=True)
        target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        write_new(target,body)
    # Temp cannot be reused as authority: verify every byte before final rename.
    for name,body in rawfiles.items():need(read_private(tmp/name)==body,'STAGE_READBACK')
    check_after()
    os.rename(tmp,root/'risk-inputs');sync(root)
    for name,body in rawfiles.items():need(read_private(root/'risk-inputs'/name)==body,'STAGE_READBACK')
    check_after()
    binding={**marker,'schema':'CERTIFIED_RISK_INPUT_BINDING_V1','status':'ACCEPTED',
             'files':{name:sha(body) for name,body in rawfiles.items()},'post_state_unchanged':True,
             'automatic_retry':False}
    raw=encode(binding);write_new(root/'control/risk-input-binding.json',raw)
    write_new(root/'control/risk-stage.accepted.json',encode({'schema':'CERTIFIED_RISK_STAGE_ACCEPTANCE_V1',
             'namespace':namespace,'session':session,'binding_sha256':sha(raw),'manifest_sha256':bundle['manifest_sha256']}))
    return {'binding_sha256':sha(raw),'file_count':len(rawfiles),'total_bytes':sum(map(len,rawfiles.values()))}


def causal_inventory(symbols_raw, *, namespace, session, markets):
    """Preserve the causal ADV20 order exactly; never alphabetize the handoff."""
    from app.r2d2_v2_risk_normalization import canonical_symbol
    try:names=symbols_raw.decode('ascii').splitlines()
    except UnicodeError:raise ValueError('SYMBOL_INVALID') from None
    need(0<len(names)<=550 and len(set(names))==len(names),'STAGE_LIST')
    need(symbols_raw==('\n'.join(names)+'\n').encode('ascii'),'STAGE_LIST_BYTES')
    need(all(canonical_symbol(name)==name for name in names),'SYMBOL_INVALID')
    need(set(markets)==set(names) and all(v in ('US','B3') for v in markets.values()),'STAGE_MARKETS')
    return {'namespace':namespace,'session_date':session,
            'symbols':[{'symbol':name,'market':markets[name]} for name in names]}


def stage_risk_input_bundle(bundle, *, root, namespace, session, order_sha256, pins_sha256,
                            before_sha256, scoped_counts, check_after,
                            execute_receipt_path, execute_receipt_sha256,
                            host_manifest_sha256, host_go_sha256):
    """Repository-owned successor entry point. Caller pins these hashes in its GO.

    Checks all five accepted predecessors, causal bytes, and the approved host
    execution before allowing the private staging write. No provider or DB calls.
    """
    root=Path(root)
    need(tuple(scoped_counts)==(1,1,2),'SCOPED_COUNTS_BEFORE_INVALID')
    need(not any(os.path.lexists(root/'control'/name) for name in
        ('risk.started.json','risk.accepted.json','capture.started.json','capture.invoked.json')),'PRIOR_ATTEMPT')
    admission_raw=b'';admission={}
    for phase in ('collect','build','publish','components','admission'):
        raw=read_private(root/'receipts'/f'{phase}.result.json')
        start=read_private(root/'control'/f'{phase}.started.json')
        doc=document(raw);ack=document(read_private(root/'control'/f'{phase}.accepted.json'))
        scope={'phase':phase,'namespace':namespace,'session':session,
               'order_sha256':order_sha256,'pins_sha256':pins_sha256}
        need(doc.get('schema')=='CODEX_CERTIFIED_PHASE_RECEIPT_V1'
             and doc.get('status')=='PASSED' and doc.get('start_sha256')==sha(start)
             and all(doc.get(k)==v for k,v in scope.items()),'RISK_STAGE_PHASE_CHAIN')
        need(ack.get('schema')=='CODEX_CERTIFIED_PHASE_ACCEPTANCE_V1'
             and all(ack.get(k)==v for k,v in scope.items())
             and ack.get('receipt_sha256')==sha(raw) and type(ack.get('driver_exit_code')) is int
             and ack['driver_exit_code']==0 and ack.get('driver_status')=='PASSED'
             and ack.get('post_state_unchanged') is True,'RISK_STAGE_PHASE_CHAIN')
        if phase=='admission':admission_raw,admission=raw,doc
    names_raw=read_private(root/'control/symbols.txt')
    manifest=document(base64.b64decode(bundle['files']['manifest.json'],validate=True))
    inventory=causal_inventory(names_raw,namespace=namespace,session=session,
        markets={row['symbol']:row['market'] for row in manifest['symbols']})
    symbols=[row['symbol'] for row in inventory['symbols']]
    causal=admission['native_result']['causal_readback']
    need(causal.get('epoch')==namespace and causal.get('session')==session
         and causal.get('status')=='AVAILABLE' and causal.get('diagnostics')==[]
         and causal.get('symbols_file_sha256')==sha(names_raw)
         and type(causal.get('selected_count')) is int and causal['selected_count']==len(symbols),'RISK_STAGE_LIST')
    raw=read_private(execute_receipt_path)
    need(all(isinstance(x,str) and HEX.fullmatch(x) for x in
        (execute_receipt_sha256,host_manifest_sha256,host_go_sha256)),'STAGE_EXECUTOR_BINDING')
    need(sha(raw)==execute_receipt_sha256,'STAGE_EXECUTOR_RECEIPT_CHANGED')
    receipt=document(raw)
    need(receipt.get('schema')=='R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1'
         and receipt.get('phase')=='execute' and receipt.get('status')=='COMPLETE'
         and receipt.get('namespace')==namespace and receipt.get('session_date')==session
         and receipt.get('manifest_sha256')==host_manifest_sha256
         and receipt.get('go_sha256')==host_go_sha256,'STAGE_EXECUTOR_BINDING')
    outputs=receipt['outputs']
    need(outputs['assessment_manifest']['sha256']==bundle['manifest_sha256'],'STAGE_EXECUTOR_ASSESSMENT_MISMATCH')
    need(outputs.get('admission_sha256')==sha(admission_raw),'STAGE_EXECUTOR_ADMISSION_MISMATCH')
    need(isinstance(outputs.get('risk_sha256'),str) and HEX.fullmatch(outputs['risk_sha256']),'STAGE_EXECUTOR_RISK_HASH')
    authority={'execute_receipt_sha256':execute_receipt_sha256,'host_manifest_sha256':host_manifest_sha256,
               'host_go_sha256':host_go_sha256,'risk_sha256':outputs['risk_sha256']}
    return stage(bundle,root=root,namespace=namespace,session=session,symbols=symbols,
        admission_sha256=sha(admission_raw),order_sha256=order_sha256,pins_sha256=pins_sha256,
        before_sha256=before_sha256,check_after=check_after,executor_binding=authority)


def execute_staged_risk(*, root, binding_sha256, namespace, session, output_path, execution_at):
    """Replay locally and accept only the exact risk bytes produced by the host."""
    from datetime import date
    from app.r2d2_v2_risk_executor import execute_private_risk
    root=Path(root)
    raw=read_private(root/'control/risk-input-binding.json')
    need(sha(raw)==binding_sha256,'STAGE_BINDING_CHANGED')
    binding=document(raw)
    acceptance=document(read_private(root/'control/risk-stage.accepted.json'))
    need(acceptance.get('binding_sha256')==binding_sha256 and binding.get('status')=='ACCEPTED'
         and binding.get('namespace')==namespace and binding.get('session')==session,'STAGE_BINDING_SCOPE')
    authority=binding['executor_binding']
    for name,digest in binding['files'].items():
        relative(name);need(sha(read_private(root/'risk-inputs'/name))==digest,'STAGE_INPUT_CHANGED')
    result=execute_private_risk(manifest_path=root/'risk-inputs/manifest.json',
        manifest_sha256=binding['manifest_sha256'],expected_namespace=namespace,
        expected_session_date=date.fromisoformat(session),output_path=Path(output_path),execution_at=execution_at)
    need(result['risk_sha256']==authority['risk_sha256'],'STAGE_EXECUTOR_RISK_MISMATCH')
    return result
