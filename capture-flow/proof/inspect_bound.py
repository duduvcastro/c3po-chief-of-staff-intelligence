"""Guarded byte re-derivation only. Output is private to the sealed controller.

No host transport, signatures or claims. Historical BOUNDs are evidence only.
"""
import argparse,hashlib,json,os,pathlib,stat,sys,types
BINDER='9dbff222a3f815573d0cf89686f16a841260831400da40c5055999d7c71af133'
CONSTRUCTOR='c94b823f8f070ad2373d8116f3eb67127f1e146df27f72af1b7f824762b0d42b'
ROOT=pathlib.Path(__file__).resolve().parents[1]
def need(ok,code):
 if not ok:raise ValueError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def read(path,limit=32*1024*1024,allow_empty=False):
 p=pathlib.Path(path);need(p.is_absolute(),'INSPECT_PATH')
 for q in (p,*p.parents):need(not q.is_symlink(),'INSPECT_LINK')
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and not a.st_mode&0o022 and a.st_size<=limit and (a.st_size>0 or allow_empty),'INSPECT_FILE');raw=f.read(limit+1);b=os.fstat(f.fileno())
 def identity(v):return v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns,v.st_ctime_ns
 need(identity(a)==identity(b)==identity(p.lstat()) and len(raw)==a.st_size,'INSPECT_CHANGED');return raw
def module(path,pin,name):
 raw=read(path);need(sha(raw)==pin,'INSPECT_SOURCE_PIN');m=types.ModuleType(name);m.__file__=str(path);sys.modules[name]=m;exec(compile(raw,str(path),'exec'),m.__dict__);return m
def binder():return module(ROOT/'binder/bind/bind_once.py',BINDER,'capture_inspection_binder')
def job(value):
 need(value.get('session')=='2026-10-08' and value.get('run_id')==os.environ.get('GITHUB_RUN_ID') and type(value.get('run_attempt')) is int and value['run_attempt']==1 and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','INSPECT_JOB')
 return {k:value[k] for k in ('session','run_id','run_attempt','nonce')}
def snapshot(m,bound):
 state=m.signed_state(bound);sheet=state['sheet'];params=m.strict_json(state['files']['PARAMETERS.json'],'INSPECT_PARAMETERS');ctx=m.capture_context_value(state['files'][m.CAPTURE_OWNER_CONTEXT_NAME],params);current=job(ctx)
 need(m.claim_identity(bound/m.CLAIM_ROOT)==sheet['claim_root_identity'],'INSPECT_ORIGINAL_ROOT_ONLY')
 packet=state['files'][m.CAPTURE_OWNER_READBACK_NAME];record,_=m.capture_signature_packet(state,packet);p=m.strict_json(packet,'INSPECT_PACKET');op=params['plan']['k9_operation']
 need(params['plan']['day']=='2026-10-08' and params['plan']['slot']=='PRIMARY' and params['signature_model']=='PRE','INSPECT_OWN_PRE')
 return dict(**current,operation=op,signature_model='PRE',slot='PRIMARY',signed=True,own_owner_record_verified=True,
  answered_at_utc=record['answered_at_utc'],observed_at_utc=p['observed_at'],sheet_sha256=sha(state['sheet_raw']),request_sha256=sheet['request_sha256'],payload_sha256=sha(state['payload']),config_sha256=sha(state['config_raw']),owner_packet_sha256=sha(packet),host_binding_sha256=sheet['host_binding_sha256'],not_before=m.zulu(state['window']['gate_start']),not_after=m.zulu(state['window']['gate_end']))
def night(m,bound,slot,operation):
 state=m.signed_state(bound);report=m.attempt_report(state)[0];params=m.strict_json(state['files']['PARAMETERS.json'],'INSPECT_PARAMETERS');request=m.strict_json(state['files']['REQUEST.BOUND.json'],'INSPECT_REQUEST');plan=request['plan']
 need(report['verified'] is True and report['status']=='KNOWN_COMPLETE' and report['outcome']==report['success_criterion'],'INSPECT_REAL_NIGHT_INCOMPLETE')
 need(params['k9_grid']=='G19' and plan['day']=='2026-10-08' and plan['slot']==slot and plan['k9_operation']==operation,'INSPECT_NIGHT_BRANCH')
 return dict(verified=True,status=report['status'],outcome=report['outcome'],success_criterion=report['success_criterion'],day=plan['day'],grid='G19',slot=slot,k9_operation=operation,host_binding_sha256=state['sheet']['host_binding_sha256'],request_sha256=report['request_sha256'],payload_sha256=report['payload_sha256'],receipt_sha256=report['stdout_sha256'],attempt_key=plan['attempt_key'],boot_id_sha256=plan['evidence_boot_id_sha256'])
def challenge(m,bound,nonce):
 ctor=module(ROOT/'capture_job/bootstrap/constructor.py',CONSTRUCTOR,'capture_inspection_constructor');sheet=read(bound/'PREPARE.json');v=ctor.strict(sheet);params=v['parameters'];need(job(params)['nonce']==nonce,'INSPECT_CHALLENGE_CONTEXT')
 packet=read(bound/'OWNER_API.READBACK.json');expected=ctor.approve_sheet(sheet,packet,ctor.canonical(v['dated_authority']),ctor.canonical(v['physical_runtime_approval']))
 # The constructor's originally consumed approval bytes must match their embedded canonical bytes.
 need(v['dated_authority_sha256']==sha(ctor.canonical(v['dated_authority'])) and v['physical_runtime_approval_sha256']==sha(ctor.canonical(v['physical_runtime_approval'])),'INSPECT_CHALLENGE_APPROVAL_BYTES')
 for name,raw in expected.items():need(read(bound/name)==raw,'INSPECT_CHALLENGE_BOUND_CHANGED')
 cfgraw=read(bound/'DISPATCH_AUTHORIZATION.json');cfg=ctor.strict(cfgraw);attempt=pathlib.Path(cfg['attempt_directory']);xraw=read(attempt/'exit.json');x=ctor.strict(xraw);out=read(attempt/'stdout.private.json');err=read(attempt/'stderr.private',allow_empty=True);receipt=ctor.strict(out)
 need(xraw==canonical(x) and x['status']=='KNOWN_COMPLETE' and x['attempts']==1 and x['config_sha256']==sha(cfgraw) and x['command_sha256']==cfg['command_sha256'] and x['stdout_sha256']==sha(out) and x['stderr_sha256']==sha(err) and err==b'','INSPECT_CHALLENGE_TRANSPORT')
 bindings={'request_sha256':sha(expected['REQUEST.BOUND.json']),'authority_sha256':sha(expected['AUTHORITY.SIGNED.json']),'go_sha256':sha(expected['GO.SIGNED.json']),'payload_sha256':cfg['source']['sha256'],'host_binding_sha256':cfg['host_binding_sha256']}
 need(all(receipt.get(k)==val for k,val in bindings.items()),'INSPECT_CHALLENGE_BINDING');body=dict(receipt);metadata=body.pop('metadata_sha256',None);need(sha(canonical(body))==metadata,'INSPECT_CHALLENGE_METADATA')
 need(receipt.get('status')=='METADATA_ONLY_REQUIRES_REVIEW' and receipt.get('outcome')=='AUTHENTICATED_CAPTURE_TRANSPORT_CHALLENGE_RETURNED' and type(receipt.get('executor_uid_verified')) is int and receipt['executor_uid_verified']==0 and all(receipt.get(k)==params[k] for k in ('session','run_id','run_attempt','nonce')),'INSPECT_CHALLENGE_REAL_UID_CONTEXT')
 effects=receipt.get('effects');need(effects==dict(operation=ctor.OP,session=params['session'],run_id=params['run_id'],run_attempt=1,nonce=params['nonce'],host_writes=0,host_file_reads=0,root_source_walks=0,BOOT_claims=0,SQL=0,containers=0,activation=False) and receipt.get('host_reads')==receipt.get('writes')==0 and receipt.get('activation_performed') is False and receipt.get('transport_only') is True and receipt.get('host_readiness') is False,'INSPECT_CHALLENGE_EFFECTS')
 m.load_reference(bound/'DISPATCH_AUTHORIZATION.json',m.REAL,True)
 return dict(**job(params),verified=True,status='KNOWN_COMPLETE',remote_uid=0,attempts=1,retry=False,remote_command=cfg['remote_command'],no_host_file_access=True,config_sha256=sha(cfgraw),receipt_sha256=sha(out))
def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('command',choices=('verify','question','snapshot','intent','night','challenge'));ap.add_argument('--bound',required=True);ap.add_argument('--question-out');ap.add_argument('--slot',choices=('PRIMARY','SPARE'));ap.add_argument('--operation',choices=('commit_result','publish_launch'));ap.add_argument('--nonce');a=ap.parse_args();m=binder();bound=pathlib.Path(a.bound);need(bound.is_absolute(),'INSPECT_BOUND')
 if a.command=='verify':v=dict(status='GROUPED_GUARD_EXECUTED',operational_READY=False)
 elif a.command=='snapshot':v=snapshot(m,bound)
 elif a.command=='night':need(a.slot and a.operation,'INSPECT_NIGHT_ARGS');v=night(m,bound,a.slot,a.operation)
 elif a.command=='challenge':need(a.nonce,'INSPECT_NONCE');v=challenge(m,bound,a.nonce)
 elif a.command=='question':
  state=m.open_bound(bound,signed=False);body=m.capture_question_body(state);asked=m.capture_fable_question(state);need(a.question_out,'INSPECT_QUESTION_OUT');m.put(pathlib.Path(a.question_out).parent,pathlib.Path(a.question_out).name,asked);v=dict(body=body,asked_question_sha256=sha(asked),prepared_at_utc=state['sheet']['prepared_at_utc'])
 else:
  state=m.signed_state(bound);attempt,claim,names,phase=m.attempt_state(state);need(phase=='PREPARED_AWAITING_PUBLICATION','INSPECT_INTENT_PHASE');raw=read(attempt/'intent.json');v=m.strict_json(raw,'INSPECT_INTENT');need(v['config_sha256']==sha(state['config_raw']) and v['request_sha256']==state['sheet']['request_sha256'] and v['go_sha256']==sha(state['raws'][2]),'INSPECT_INTENT_BINDINGS');v=dict(v,intent_sha256=sha(raw))
 print(json.dumps(v,sort_keys=True))
if __name__=='__main__':main()
