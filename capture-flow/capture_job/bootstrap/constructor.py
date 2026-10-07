"""Dated 08/10 transport-sheet constructor, never connects or dispatches.

Only the operator may use the CLI after exact dated authority and separately
reviewed physical Linux runtime. A candidate or a self-described receipt does
not supply either trust anchor. No earlier executed transport/BOOT is accepted.
The pure builders below permit synthetic proofs without operational execution.
"""
import copy,datetime as dt,hashlib,json,os,pathlib,re,stat,sys,types
ROOT=pathlib.Path(__file__).resolve().parent
PINS={
 'capture_transport_challenge.py':'8c07c42459fd0f9f1dcdb7d2701f0c96fbb5246f8148b3b668ff690438b11fca',
 'launcher_stdin.py':'ac4085e49dd1a7fcc0e64e3eaa5cd75b1a5f7f961f587e9eaf76c17d96f73caa',
 'transport_once.py':'5900efbf916d679a6ce176dd71413f304e21e0c9ab65b0ff8ee742cc212f2918',
 'dispatch_once.py':'4a0d3db181df0812d6247ec17d91212cf9c7bf635e48ba534f1c88a3ce2a8e38'}
HELPER_PIN='9a3a6605176215b22be0613f7e0be1f8b0093ca147ca2bf63e0f16e7a962c814'
TEMPLATE_PINS={'REQUEST.UNBOUND.json': '030df2b493d5057953469c9f313df7ecaeaba50cd17f16ca077791ac5b8c67f0', 'AUTHORITY.UNBOUND.json': 'f9a36ff7840413eef2d9f073347b9a65787df34bbf3979f3f210951a00b234a1', 'GO.UNBOUND.json': '5b1a801121b38fc8c21ec1b69e276e53d72eace95d06f004218f3a380e0ab5f7', 'DISPATCH.UNBOUND.json': '6c28be24bd304a1dd1962636730e0a77d6a46c46d24345209484ac822edef417'}
START='2026-10-08T11:52:00+00:00';END='2026-10-08T12:02:00+00:00'
OWNER='DUDU';OP='GO_READONLY_HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_01'
class Refused(ValueError):pass
def need(ok,code):
 if not ok:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def strict(raw):
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'CONSTRUCTOR_DUPLICATE_FIELD');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'CONSTRUCTOR_CONSTANT'))
def utc(t):
 need(type(t) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)',t),'CONSTRUCTOR_TIME')
 return dt.datetime.fromisoformat(t.replace('Z','+00:00'))
def pin(p):need(type(p) is str and re.fullmatch('[0-9a-f]{64}',p) and p!='0'*64,'CONSTRUCTOR_PIN');return p
def path(p):
 need(type(p) is str and p.startswith('/') and str(pathlib.PurePosixPath(p))==p and '..' not in pathlib.PurePosixPath(p).parts,'CONSTRUCTOR_PATH')
 return pathlib.Path(p)
def no_links(p):
 for ancestor in (p,*p.parents):need(not ancestor.is_symlink(),'CONSTRUCTOR_SYMLINK')
def signature(s):return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns
def read(p,expected=None,private=True,limit=65536):
 p=path(str(p));no_links(p)
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and 0<a.st_size<=limit,'CONSTRUCTOR_FILE')
  need(not a.st_mode&0o022 and (not private or a.st_uid==os.getuid() and stat.S_IMODE(a.st_mode)==0o600),'CONSTRUCTOR_PRIVATE')
  raw=f.read(limit+1);b=os.fstat(f.fileno())
 need(signature(a)==signature(b)==signature(p.lstat()) and len(raw)==a.st_size,'CONSTRUCTOR_CHANGED')
 if expected is not None:need(sha(raw)==pin(expected),'CONSTRUCTOR_FILE_PIN')
 return raw
def module(name,raw):
 m=types.ModuleType('_constructor_'+name.replace('.','_'));m.__file__=str(ROOT/name);old=sys.modules.get(m.__name__);sys.modules[m.__name__]=m
 try:exec(compile(raw,m.__file__,'exec'),m.__dict__)
 finally:
  if old is None:sys.modules.pop(m.__name__,None)
  else:sys.modules[m.__name__]=old
 return m
def runtime():
 raws={n:read(ROOT/'transport_challenge'/n,p,False,2*1024*1024) for n,p in PINS.items()}
 helper=read(ROOT/'owner_response.py',HELPER_PIN,False)
 return raws,module('source',raws['capture_transport_challenge.py']),module('launcher',raws['launcher_stdin.py']),module('owner_response',helper)
def argv(fields):
 need(re.fullmatch(r'[a-z_][a-z0-9_-]*@[A-Za-z0-9.-]+',fields['target']) is not None,'CONSTRUCTOR_TARGET')
 return ['/usr/bin/ssh','-F','/dev/null','-T','-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','GlobalKnownHostsFile=/dev/null','-o','UserKnownHostsFile='+fields['known_hosts']['path'],'-o','ConnectTimeout=10','-o','ConnectionAttempts=1','-i',fields['ssh_key']['path'],fields['target'],'sudo -n /usr/bin/python3 -I -B -']
def prerequisites(params,approval,physical,prepared_at):
 need(set(params)=={'session','run_id','run_attempt','nonce','target','ssh_key','known_hosts','claim_root_identity','bound_directory'},'CONSTRUCTOR_PARAMETER_KEYS')
 need(params['session']=='2026-10-08' and type(params['run_attempt']) is int and params['run_attempt']==1,'CONSTRUCTOR_SESSION_ATTEMPT')
 need(type(params['run_id']) is str and re.fullmatch('[1-9][0-9]{5,19}',params['run_id']) and type(params['nonce']) is str and re.fullmatch('[0-9a-f]{32}',params['nonce']),'CONSTRUCTOR_RUN_NONCE')
 need(utc('2026-10-08T11:45:00Z')<=utc(prepared_at)<utc('2026-10-08T11:52:00Z'),'CONSTRUCTOR_PREPARE_BAND')
 for k in ('ssh_key','known_hosts'):
  need(type(params[k]) is dict and set(params[k])=={'path','sha256'},'CONSTRUCTOR_CREDENTIAL');path(params[k]['path']);pin(params[k]['sha256'])
 root=params['claim_root_identity'];need(type(root) is dict and set(root)=={'path','device','inode'} and type(root['device']) is int and root['device']>=0 and type(root['inode']) is int and root['inode']>0,'CONSTRUCTOR_ROOT');path(root['path']);path(params['bound_directory'])
 need(type(approval) is dict and approval.get('schema')=='CAPTURE_TRANSPORT_DATED_AUTHORITY_V1' and approval.get('status')=='SIGNED'
      and approval.get('owner')==OWNER and approval.get('answer')=='Assino' and approval.get('channel')=='AskUserQuestion via Fable'
      and approval.get('operation')==OP and approval.get('session')=='2026-10-08' and approval.get('outside_Mac') is True
      and approval.get('single_use') is True and approval.get('retry') is False
      and approval.get('scope')=='TRANSPORT_CHALLENGE_ONLY_NO_HOST_FILE_ACCESS_NO_BOOT_REPEAT'
      and approval.get('program_pins')==dict(PINS,templates=TEMPLATE_PINS,constructor=sha(read(ROOT/'constructor.py',private=False,limit=1024*1024)),owner_response=HELPER_PIN), 'CONSTRUCTOR_DATED_AUTHORITY')
 need(utc(approval['signed_at_utc'])<=utc(prepared_at),'CONSTRUCTOR_AUTHORITY_ORDER')
 pin(approval['source_decision_body_sha256']);pin(approval['document_sha256'])
 need(type(physical) is dict and physical.get('schema')=='CAPTURE_TRANSPORT_LINUX_RUNTIME_APPROVAL_V1' and physical.get('verdict')=='PASS_PHYSICAL_RUNTIME'
      and physical.get('run_id')==params['run_id'] and type(physical.get('run_attempt')) is int and physical['run_attempt']==1
      and physical.get('platform')=='linux' and physical.get('program_pins')==approval['program_pins']
      and physical.get('remote_command')=='sudo -n /usr/bin/python3 -I -B -','CONSTRUCTOR_PHYSICAL_RUNTIME')
 pin(physical['measurement_sha256']);pin(physical['review_body_sha256']);pin(physical['python_executable_sha256']);pin(physical['ssh_executable_sha256'])
 need(utc(physical['measured_at_utc'])<=utc(physical['reviewed_at_utc'])<=utc(prepared_at),'CONSTRUCTOR_RUNTIME_ORDER')
def make_sheet(params,approval_raw,physical_raw,prepared_at):
 """Pure unsigned sheet; pinned approval bytes must come from a trusted external record."""
 approval,physical=strict(approval_raw),strict(physical_raw);prerequisites(params,approval,physical,prepared_at)
 raws,m,launcher,helper=runtime()
 templates={key:strict(read(ROOT/'transport_challenge'/(key+'.UNBOUND.json'),TEMPLATE_PINS[key+'.UNBOUND.json'],private=False)) for key in ('REQUEST','AUTHORITY','GO','DISPATCH')}
 fields={k:copy.deepcopy(params[k]) for k in ('target','ssh_key','known_hosts')}
 host=sha(canonical({'known_hosts_sha256':fields['known_hosts']['sha256'],'target':fields['target']}))
 command=sha(canonical(argv(fields)));request=templates['REQUEST'];request.update(status='BOUND',date='2026-10-08',not_before=START,not_after=END,host_binding_sha256=host)
 request['plan'].update(status='BOUND',session=params['session'],run_id=params['run_id'],run_attempt=1,nonce=params['nonce'],host_binding_sha256=host,window={'not_before':START,'expires_at':END})
 m.validate_plan(request['plan']);rr=canonical(request)
 return dict(schema='CAPTURE_TRANSPORT_PREPARE_V1',status='UNSIGNED_AWAITING_OWN_OWNER_RESPONSE',prepared_at_utc=prepared_at,
  parameters=copy.deepcopy(params),request=request,request_sha256=sha(rr),fields=fields,command_sha256=command,host_binding_sha256=host,
  program_pins=approval['program_pins'],dated_authority_sha256=sha(approval_raw),physical_runtime_approval_sha256=sha(physical_raw),
  dated_authority=approval,physical_runtime_approval=physical,templates=templates,operational_READY=False)
def question(sheet_raw):
 s=strict(sheet_raw);c=s['parameters']
 private=('Desafio de transporte próprio de 08/10. Uma tentativa, sem retry; UID remoto 0; nenhuma leitura/escrita de arquivo host, SQL, Docker, importação app ou repetição de BOOT. Janela 08:52–09:02 BRT; aguardar publicação e 120 segundos antes do envio. Isso observa somente o transporte. Não dá prontidão K9. Folha sha256:'+sha(sheet_raw)+'; REQUEST:'+s['request_sha256']+'; autoridade datada:'+s['dated_authority_sha256']+'; runtime físico aprovado:'+s['physical_runtime_approval_sha256']+'. Destino privado:'+c['target']+'. Responda exatamente Assino.').encode()
 fields=dict(schema='CAPTURE_TRANSPORT_OWNER_REQUEST_V1',session=c['session'],run_id=c['run_id'],run_attempt=1,nonce=c['nonce'],sheet_sha256=sha(sheet_raw),request_sha256=s['request_sha256'],owner_question_sha256=sha(private),owner_deadline_utc='2026-10-08T11:52:00Z',answer_schema='CAPTURE_OWNER_ANSWER_V2',recorded_by='FABLE',response_channel='AskUserQuestion via Fable')
 asked=private+b'\nCONTEXTO DESTA UNICA FOLHA:\n'+canonical(fields)
 public=dict(fields,asked_question_sha256=sha(asked))
 return canonical(public),asked
def approve_sheet(sheet_raw,packet_raw,approval_raw,physical_raw):
 """Pure byte assembly after exact own response; never writes, prepares or sends."""
 s=strict(sheet_raw);need(s.get('schema')=='CAPTURE_TRANSPORT_PREPARE_V1' and s.get('status')=='UNSIGNED_AWAITING_OWN_OWNER_RESPONSE','CONSTRUCTOR_SHEET')
 expected=make_sheet(s['parameters'],approval_raw,physical_raw,s['prepared_at_utc']);need(canonical(expected)==sheet_raw,'CONSTRUCTOR_FROZEN_SHEET_CHANGED')
 body,asked=question(sheet_raw);packet=strict(packet_raw);need(type(packet) is dict and set(packet)=={'question_first','question_readback','first','readback','observed_at'},'CONSTRUCTOR_PACKET')
 q=packet['question_first'];need(q==packet['question_readback'] and q.get('body')==body.decode() and q.get('created_at')==q.get('updated_at') and type(q.get('id')) is int and q['id']>0,'CONSTRUCTOR_QUESTION_READBACK')
 raws,m,launcher,helper=runtime();need(q.get('issue_url')==helper.ISSUE_URL and q.get('url')==helper.ISSUE_URL.rsplit('/issues/',1)[0]+'/issues/comments/'+str(q['id']),'CONSTRUCTOR_QUESTION_LOCATION')
 c=s['parameters'];context={k:c[k] for k in ('session','run_id','run_attempt','nonce')};context.update(sheet_sha256=sha(sheet_raw),question_created_at=q['created_at'],question_body_sha256=sha(body),asked_question_sha256=sha(asked),prepared_at_utc=s['prepared_at_utc'],not_before='2026-10-08T11:50:00Z',not_after='2026-10-08T12:30:00Z')
 record=helper.validate_owner_response(packet['first'],packet['readback'],context,packet['observed_at'])
 need(utc(record['answered_at_utc'])<=utc('2026-10-08T11:52:00Z') and utc(packet['observed_at'])<=utc('2026-10-08T11:52:00Z'),'CONSTRUCTOR_OWN_SIGNATURE_DEADLINE')
 request_raw=canonical(s['request']);auth=copy.deepcopy(s['templates']['AUTHORITY']);auth.update(status='SIGNED',decision='APPROVED',execution_authorized=True,owner=OWNER,owner_evidence='DUDU answered Assino (REGISTRO_PELA_FABLE AskUserQuestion via Fable) at '+record['answered_at_utc']+'; sheet:'+sha(sheet_raw)+'; packet:'+sha(packet_raw)+'; dated authority:'+sha(approval_raw),effects=m.effects_of(s['request']['plan']),request_sha256=sha(request_raw),host_binding_sha256=s['host_binding_sha256'],not_before=START,not_after=END)
 ar=canonical(auth);go=copy.deepcopy(s['templates']['GO']);binding=dict(target=c['target'],remote_command='sudo -n /usr/bin/python3 -I -B -',command_sha256=s['command_sha256'],runtime_sha256=PINS)
 go.update(status='SIGNED',action='GO',execution_authorized=True,owner=OWNER,effects=auth['effects'],request_sha256=sha(request_raw),authority_sha256=sha(ar),claim_root_identity=c['claim_root_identity'],transport_binding=binding,host_binding_sha256=s['host_binding_sha256'],not_before=START,not_after=END);gr=canonical(go)
 payload=launcher.build(raws['capture_transport_challenge.py'],request_raw,ar,gr,expected_payload_sha256=PINS['capture_transport_challenge.py'],expected_request_sha256=sha(request_raw),expected_authority_sha256=sha(ar),expected_go_sha256=sha(gr))
 cfg=copy.deepcopy(s['templates']['DISPATCH']);cfg.update(status='BOUND',decision='GO',owner=OWNER,authorization_ref='CAPTURE_DATED_AUTHORITY:'+sha(approval_raw)+':OWNER_PACKET:'+sha(packet_raw),target=c['target'],ssh_key=c['ssh_key'],known_hosts=c['known_hosts'],host_binding_sha256=s['host_binding_sha256'],command_sha256=s['command_sha256'],local_root_identity=c['claim_root_identity'],attempt_directory=str(path(c['claim_root_identity']['path'])/'challenge-once'),not_before=START,not_after=END,latest_start='2026-10-08T12:00:40+00:00',runtime_sha256=PINS)
 files={'REQUEST.BOUND.json':request_raw,'AUTHORITY.SIGNED.json':ar,'GO.SIGNED.json':gr,'FINAL_PAYLOAD.BOUND.py':payload,'OWNER_API.READBACK.json':packet_raw}
 for key,name in [('source','capture_transport_challenge.py'),('request','REQUEST.BOUND.json'),('authority','AUTHORITY.SIGNED.json'),('go','GO.SIGNED.json'),('payload','FINAL_PAYLOAD.BOUND.py')]:
  raw=raws['capture_transport_challenge.py'] if key=='source' else files[name];cfg[key]=dict(path=str(path(c['bound_directory'])/name),sha256=sha(raw))
 files['capture_transport_challenge.py']=raws['capture_transport_challenge.py'];files['DISPATCH_AUTHORIZATION.json']=canonical(cfg)
 # Inner authentication is later performed by the actual dispatcher/remote actor.
 # No synthetic UID or source.run call is a substitute for that real gate.
 return files
def anchors(params,physical):
 need(os.geteuid()!=0 and sys.platform=='linux' and sys.flags.isolated and sys.dont_write_bytecode,'CONSTRUCTOR_PHYSICAL_LINUX_PROCESS')
 need(os.environ.get('GITHUB_RUN_ID')==params['run_id'] and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','CONSTRUCTOR_PHYSICAL_JOB')
 read(str(pathlib.Path(sys.executable).resolve()),physical['python_executable_sha256'],False,64*1024*1024)
 read('/usr/bin/ssh',physical['ssh_executable_sha256'],False,16*1024*1024)
 for k in ('ssh_key','known_hosts'):read(params[k]['path'],params[k]['sha256'])
 root=path(params['claim_root_identity']['path']);no_links(root);s=root.lstat()
 need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700 and (s.st_dev,s.st_ino)==(params['claim_root_identity']['device'],params['claim_root_identity']['inode']) and not list(root.iterdir()),'CONSTRUCTOR_CLAIM_ROOT_NOT_OWN_EMPTY')
def write_all(out,files):
 out=path(out);no_links(out);s=out.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'CONSTRUCTOR_OUTPUT_PRIVATE')
 for name,raw in files.items():
  need('/' not in name and name not in ('','.','..'),'CONSTRUCTOR_OUTPUT_NAME')
  fd=os.open(str(out/name),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
def main(argv_in=None):
 import argparse
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('command',choices=('sheet','approve'));ap.add_argument('--parameters',required=True);ap.add_argument('--dated-authority',required=True);ap.add_argument('--dated-authority-sha256',required=True);ap.add_argument('--runtime-approval',required=True);ap.add_argument('--runtime-approval-sha256',required=True);ap.add_argument('--out',required=True);ap.add_argument('--sheet');ap.add_argument('--sheet-sha256');ap.add_argument('--packet');ap.add_argument('--packet-sha256');a=ap.parse_args(argv_in)
 try:
  params=strict(read(a.parameters));need(a.out==params['bound_directory'],'CONSTRUCTOR_BOUND_DIRECTORY')
  authority=read(a.dated_authority,a.dated_authority_sha256);physical=read(a.runtime_approval,a.runtime_approval_sha256)
  anchors(params,strict(physical))
  if a.command=='sheet':
   prepared_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z');sheet=canonical(make_sheet(params,authority,physical,prepared_at));body,asked=question(sheet)
   write_all(a.out,{'PREPARE.json':sheet,'OWNER_QUESTION.private.txt':asked,'OWNER_REQUEST.public.json':body});print(body.decode())
  else:
   need(a.sheet and a.sheet_sha256 and a.packet and a.packet_sha256,'CONSTRUCTOR_OWN_PACKET_REQUIRED');sheet=read(a.sheet,a.sheet_sha256);need(strict(sheet)['parameters']==params,'CONSTRUCTOR_PARAMETER_CHANGED')
   packet=read(a.packet,a.packet_sha256);files=approve_sheet(sheet,packet,authority,physical);write_all(a.out,files)
   print(json.dumps(dict(status='SIGNED_BYTES_STORED_NOT_DISPATCHED',config_sha256=sha(files['DISPATCH_AUTHORIZATION.json']),operational_READY=False)))
  return 0
 except (Refused,OSError,ValueError,KeyError,TypeError):print('{"status":"CONSTRUCTOR_REFUSED_NO_RETRY","operational_READY":false}');return 2
if __name__=='__main__':raise SystemExit(main())
