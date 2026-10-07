"""Dated staged adapter. All operational children use the grouped guard.

The single job never restarts a stage or a D/R. Inputs and externally recorded
answers are data, never commands. Any failure durably stops this job's sequence.
"""
import argparse,datetime as dt,hashlib,io,json,os,pathlib,re,subprocess,sys,tarfile,time,types
SESSION='2026-10-08'
STAGES=('challenge-sheet','challenge-execute','prepare-four','sign-four','run')
OPERATIONS=('policy_read','capture_launch','capture_result','capture_cleanup')
AGE='eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c'

def load(p,pin,name):
 raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('ADAPTER_SOURCE_PIN')
 m=types.ModuleType(name);m.__file__=str(p);sys.modules[name]=m;exec(compile(raw,str(p),'exec'),m.__dict__);return m

class Live:
 def __init__(self,state_path):
  self.state_path=pathlib.Path(state_path);initial=json.loads(self.state_path.read_bytes());self.root=pathlib.Path(initial['root']);raw=pathlib.Path(initial['layout']).read_bytes()
  if hashlib.sha256(raw).hexdigest()!=initial['layout_sha256']:raise ValueError('ADAPTER_LAYOUT_PIN')
  self.layout=json.loads(raw);self.f=load(self.root/'capture_job/job_files.py',self.layout['helpers']['capture_job/job_files.py'],'capture_live_files');self.s=self.f.strict(self.f.read(self.state_path));self.home=self.f.directory(self.s['private']);self.ctx=self.s['context'];self.ch=load(self.root/'capture_job/job_channel.py',self.layout['helpers']['capture_job/job_channel.py'],'capture_live_channel');self.ch.context(self.ctx)
  self.f.need(os.environ.get('GITHUB_RUN_ID')==self.ctx['run_id'] and os.environ.get('GITHUB_RUN_ATTEMPT')=='1' and sys.platform=='linux' and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and os.geteuid()!=0,'ADAPTER_ACTUAL_PROCESS')
  self.api=self.ch.API(os.environ.get('CAPTURE_GITHUB_READ_TOKEN',''));self.count=len(list((self.home/'calls').glob('*.stdout.private')));self.reviews={};self.night=None
 def now(self):
  value=dt.datetime.now(dt.timezone.utc);self.need(value<dt.datetime.fromisoformat('2026-10-08T14:45:00+00:00'),'ADAPTER_JOB_END');return value
 def identity(self):return dict(self.ctx)
 def need(self,v,code):self.f.need(v,code)
 def put(self,path,value):return self.f.put(path,self.f.canonical(value))
 def get(self,path):return self.f.strict(self.f.read(path))
 def bound(self,op):return self.home/'sheets'/op
 def call(self,role,args,allowed=(0,),timeout=180):
  self.need(not (self.home/'HALTED.json').exists(),'ADAPTER_ALREADY_HALTED');self.count+=1;n=str(self.count).zfill(5);cache=self.f.directory(self.home/('cache-'+n),True)
  guard=self.root/'capture_job/checked_program.py';self.f.read(guard,self.layout['helpers']['capture_job/checked_program.py'],False)
  approval=self.home/'PHYSICAL_APPROVAL.json';argv=[str(self.root/'venv/bin/python'),'-I','-S','-B','-X','pycache_prefix='+str(cache),str(guard)]
  for k in ('root','layout','layout_sha256','measurement','measurement_sha256','authority','authority_sha256'):argv+=['--'+k.replace('_','-'),self.s[k]]
  argv+=['--approval',str(approval),'--approval-sha256',self.f.sha(self.f.read(approval)),'--nonce',self.ctx['nonce'],'--tool',role,'--']+list(map(str,args))
  env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','GITHUB_RUN_ID':self.ctx['run_id'],'GITHUB_RUN_ATTEMPT':'1','CAPTURE_GITHUB_READ_TOKEN':os.environ.get('CAPTURE_GITHUB_READ_TOKEN','')}
  out=self.home/'calls'/(n+'.stdout.private');err=self.home/'calls'/(n+'.stderr.private')
  with os.fdopen(os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as o,os.fdopen(os.open(err,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as e:
   remaining=(dt.datetime.fromisoformat('2026-10-08T14:45:00+00:00')-self.now()).total_seconds();self.need(remaining>0,'ADAPTER_JOB_END');r=subprocess.run(argv,stdout=o,stderr=e,env=env,timeout=min(timeout,remaining),check=False)
  self.need(r.returncode in allowed and self.f.read(err,empty=True)==b'','ADAPTER_CHILD_REFUSED_OR_UNCERTAIN_NO_RETRY')
  return self.get(out)
 def inspect(self,command,bound=None,*extra):return self.call('inspect',[command,'--bound',bound or self.home/'challenge',*extra])
 def verify_authority_runtime(self,current):
  self.need(current==self.ctx and self.now().date().isoformat()==SESSION,'ADAPTER_DATE_JOB');self.api.assert_no_halt(self.ctx);self.inspect('verify')
 def wait_until(self,text):
  end=dt.datetime.fromisoformat(text.replace('Z','+00:00'))
  while self.now()<end:
   self.need(not (self.home/'HALTED.json').exists(),'ADAPTER_HALTED');self.api.assert_no_halt(self.ctx);time.sleep(min(10,max(0,(end-self.now()).total_seconds())))
 def cipher(self,source,name):
  target=self.home/'cipher'/(name+'.age');self.call('export',['--input',source,'--age-binary',self.s['age'],'--age-sha256',AGE,'--out',target]);return self.f.sha(self.f.read(target))
 def archive_cipher(self,files,name):
  # Explicit allowlist supplied by stages. No keys/token/private inventory or arbitrary walk.
  stream=io.BytesIO()
  with tarfile.open(fileobj=stream,mode='w',format=tarfile.USTAR_FORMAT) as t:
   for alias,path in sorted(files.items()):
    self.need(re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+){0,4}',alias),'ADAPTER_EXPORT_ALIAS');raw=self.f.read(path,empty=True);m=tarfile.TarInfo(alias);m.size=len(raw);m.mode=0o600;m.uid=m.gid=0;m.mtime=0;t.addfile(m,io.BytesIO(raw))
  p=self.home/(name+'.tar');self.f.put(p,stream.getvalue());return self.cipher(p,name)
 def question(self,op,public,asked,prepared):
  body=self.ch.owner_public_body(public);v=self.f.strict(body);p=self.home/'questions'/op;self.f.directory(p,True);self.f.put(p/'PUBLIC.json',body.encode());q=self.api.publish_owner(body);self.put(p/'POST.READBACK.json',q)
  context=dict(self.ctx,sheet_sha256=v['sheet_sha256'],question_created_at=q['created_at'],question_body_sha256=self.f.sha(body.encode()),asked_question_sha256=v['asked_question_sha256'],prepared_at_utc=prepared,not_before='2026-10-08T11:50:00Z',not_after='2026-10-08T12:30:00Z');self.put(p/'CONTEXT.json',context)
  return dict(operation=op,question_id=q['id'],sheet_sha256=v['sheet_sha256'],asked_path=str(asked))
 def packet(self,op,sequence,deadline):
  p=self.home/'questions'/op;q=self.get(p/'POST.READBACK.json');v=self.f.strict(q['body']);control=self.api.wait_control(self.ctx,'OWNER_ANSWER_ID',sequence,deadline)
  self.need(control['question_id']==q['id'] and control['sheet_sha256']==v['sheet_sha256'],'ADAPTER_ANSWER_OWN_QUESTION');out=p/'OWNER_API.READBACK.json'
  self.call('response',['--question-id',q['id'],'--answer-id',control['answer_id'],'--question-body',p/'PUBLIC.json','--context',p/'CONTEXT.json','--out',out]);packet=self.get(out)
  self.need(self.f.sha(packet['first']['body'].encode())==control['document_sha256'],'ADAPTER_ACTUAL_ANSWER_BODY_PIN')
  self.need(packet['first']['id']==control['answer_id'] and packet['question_first']['id']==q['id'],'ADAPTER_PACKET_IDS');return out,packet
 def challenge_args(self):
  return ['--parameters',self.home/'CHALLENGE.PARAMETERS.json','--dated-authority',self.home/'CHALLENGE.DATED_AUTHORITY.json','--dated-authority-sha256',self.f.sha(self.f.read(self.home/'CHALLENGE.DATED_AUTHORITY.json')),'--runtime-approval',self.home/'CHALLENGE.PHYSICAL_APPROVAL.json','--runtime-approval-sha256',self.f.sha(self.f.read(self.home/'CHALLENGE.PHYSICAL_APPROVAL.json')),'--out',self.home/'challenge']
 def challenge_sheet(self):
  self.verify_authority_runtime(self.ctx);ctor_path=self.root/'capture_job/bootstrap/constructor.py';raw=self.f.read(ctor_path,self.layout['tools']['constructor']['sha256'],False);ctor=types.ModuleType('capture_constructor_metadata');ctor.__file__=str(ctor_path);sys.modules[ctor.__name__]=ctor;exec(compile(raw,str(ctor_path),'exec'),ctor.__dict__)
  authority=self.get(self.s['authority']);approval=self.get(self.home/'PHYSICAL_APPROVAL.json');measurement=self.get(self.s['measurement']);pins=dict(ctor.PINS,templates=ctor.TEMPLATE_PINS,constructor=self.layout['tools']['constructor']['sha256'],owner_response=ctor.HELPER_PIN)
  dated=dict(schema='CAPTURE_TRANSPORT_DATED_AUTHORITY_V1',status='SIGNED',owner='DUDU',answer='Assino',channel='AskUserQuestion via Fable',operation=ctor.OP,session=SESSION,outside_Mac=True,single_use=True,retry=False,scope='TRANSPORT_CHALLENGE_ONLY_NO_HOST_FILE_ACCESS_NO_BOOT_REPEAT',program_pins=pins,signed_at_utc=authority['signed_at_utc'],source_decision_body_sha256=authority['source_owner_record_body_sha256'],document_sha256=authority['document_sha256'])
  physical=dict(schema='CAPTURE_TRANSPORT_LINUX_RUNTIME_APPROVAL_V1',verdict='PASS_PHYSICAL_RUNTIME',run_id=self.ctx['run_id'],run_attempt=1,platform='linux',program_pins=pins,remote_command='sudo -n /usr/bin/python3 -I -B -',measurement_sha256=self.s['measurement_sha256'],review_body_sha256=approval['review_body_sha256'],python_executable_sha256=measurement['executable_sha256'],ssh_executable_sha256=approval['ssh_executable_sha256'],measured_at_utc=approval['measured_at_utc'],reviewed_at_utc=approval['reviewed_at_utc'])
  params=dict(self.ctx,target=self.s['target'],ssh_key=dict(path=str(self.home/'ssh-key'),sha256=self.f.sha(self.f.read(self.home/'ssh-key'))),known_hosts=dict(path=str(self.home/'known-hosts'),sha256=self.f.sha(self.f.read(self.home/'known-hosts'))),claim_root_identity=self.s['claim_root_identity'],bound_directory=str(self.home/'challenge'))
  self.put(self.home/'CHALLENGE.PARAMETERS.json',params);self.put(self.home/'CHALLENGE.DATED_AUTHORITY.json',dated);self.put(self.home/'CHALLENGE.PHYSICAL_APPROVAL.json',physical);self.f.directory(self.home/'questions',True)
  body=self.call('constructor',['sheet',*self.challenge_args()]);sheet=self.get(self.home/'challenge/PREPARE.json');q=self.question('transport_challenge',self.f.canonical(body).decode(),self.home/'challenge/OWNER_QUESTION.private.txt',sheet['prepared_at_utc']);self.put(self.home/'CHALLENGE.QUESTION.json',q)
  self.archive_cipher({'OWNER_QUESTION.private.txt':self.home/'challenge/OWNER_QUESTION.private.txt','PREPARE.json':self.home/'challenge/PREPARE.json'},'CHALLENGE_QUESTION')
 def challenge_execute(self):
  self.verify_authority_runtime(self.ctx);packet,record=self.packet('transport_challenge',1,'2026-10-08T11:52:00Z');sheet=self.home/'challenge/PREPARE.json';self.call('constructor',['approve',*self.challenge_args(),'--sheet',sheet,'--sheet-sha256',self.f.sha(self.f.read(sheet)),'--packet',packet,'--packet-sha256',self.f.sha(self.f.read(packet))])
  self.wait_until('2026-10-08T11:52:00Z');self.verify_authority_runtime(self.ctx);cfg=self.home/'challenge/DISPATCH_AUTHORIZATION.json';cfg_sha=self.f.sha(self.f.read(cfg));args=['--config',cfg,'--config-sha256',cfg_sha];result=self.call('challenge_dispatch',args+['--phase','prepare'],allowed=(2,));self.need(result.get('status')=='AWAITING_PUBLICATION_NO_SPAWN' and result.get('retry') is False,'ADAPTER_CHALLENGE_INTENT')
  config=self.get(cfg);intent=self.f.read(pathlib.Path(config['attempt_directory'])/'intent.json');self.need(self.f.sha(intent)==result['intent_sha256'],'ADAPTER_CHALLENGE_INTENT_PIN');public=self.api.publish('INTENT',self.ctx,dict(operation='transport_challenge',status='AWAITING_PUBLICATION_NO_SPAWN',config_sha256=cfg_sha,go_sha256=result['go_sha256'],intent_sha256=result['intent_sha256']))
  proof=dict(schema='HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_INTENT_PUBLICATION_V1',status='PUBLISHED',owner='DUDU',publication_ref=str(public['id']),go_sha256=result['go_sha256'],config_sha256=cfg_sha,intent_sha256=result['intent_sha256'],published_at=public['created_at']);proof_path=self.home/'CHALLENGE.PUBLICATION.PROOF.json';proof_sha=self.put(proof_path,proof)
  self.wait_until((dt.datetime.fromisoformat(public['created_at'].replace('Z','+00:00'))+dt.timedelta(seconds=120)).strftime('%Y-%m-%dT%H:%M:%SZ'));self.verify_authority_runtime(self.ctx)
  result=self.call('challenge_dispatch',args+['--phase','resume','--publication-proof',proof_path,'--publication-proof-sha256',proof_sha],timeout=180);self.need(result.get('status')=='KNOWN_COMPLETE','ADAPTER_CHALLENGE_UNCERTAIN')
  verified=self.completed_challenge();self.put(self.home/'CHALLENGE.VERIFIED.json',verified)
 def completed_challenge(self):return self.inspect('challenge',self.home/'challenge','--nonce',self.ctx['nonce'])
 def prepare_four(self):
  self.verify_authority_runtime(self.ctx);self.completed_challenge();self.f.directory(self.home/'sheets',True);inventory=self.get(self.home/'INVENTORY.json');exports={}
  for op in OPERATIONS:
   self.need(self.now()<dt.datetime.fromisoformat('2026-10-08T12:30:00+00:00'),'ADAPTER_PRE_DEADLINE');params=self.home/(op+'.PARAMETERS.json');rows=[r for r in inventory['files'] if r['role']=='BASE_PARAMETERS_NOT_JOB_PARAMETERS' and self.get(self.home/'inputs'/r['bundle_path'])['plan']['k9_operation']==op];self.need(len(rows)==1,'ADAPTER_ONE_BASE')
   base=self.home/'inputs'/rows[0]['bundle_path'];self.call('render',['--base',base,'--inventory',self.home/'INVENTORY.json','--private-root',self.home/'inputs','--family-root',self.root/'families','--operation',op,'--out',params]);v=self.get(params);ctx=self.home/(op+'.CONTEXT.json');self.put(ctx,dict(schema='CAPTURE_GITHUB_CONTEXT_V2',**self.ctx,k9_operation=op));family='k9_phase_read' if op in ('policy_read','capture_result') else 'k9_phase_step'
   self.call('binder',['prepare','--family',self.root/'families'/family,'--operation',v['operation'],'--params',params,'--reference',self.home/'challenge/DISPATCH_AUTHORIZATION.json','--out',self.bound(op),'--mode','real','--github-context',ctx])
   asked=self.home/(op+'.QUESTION.private.txt');q=self.inspect('question',self.bound(op),'--question-out',asked);self.question(op,q['body'],asked,q['prepared_at_utc']);exports[op+'/OWNER_QUESTION.private.txt']=asked;exports[op+'/PREPARE.json']=self.bound(op)/'PREPARE.json'
  self.archive_cipher(exports,'FOUR_PRE_QUESTIONS')
 def sign_four(self):
  self.verify_authority_runtime(self.ctx);exports={}
  for seq,op in enumerate(OPERATIONS,2):
   packet,record=self.packet(op,seq,'2026-10-08T12:30:00Z');sheet=self.bound(op)/'PREPARE.json';answer=self.f.strict(record['first']['body']);self.call('binder',['sign','--bound',self.bound(op),'--sheet-sha256',self.f.sha(self.f.read(sheet)),'--signed-at',answer['answered_at_utc'],'--owner-answer','Assino','--owner-api-proof',packet])
   snapshot=self.inspect('snapshot',self.bound(op));self.put(self.home/(op+'.SIGNED.SNAPSHOT.json'),snapshot)
   for path in self.bound(op).rglob('*'):
    if path.is_file():exports[op+'/'+str(path.relative_to(self.bound(op)))]=path
  self.archive_cipher(exports,'FOUR_SIGNED_BOUND')
 def prepare_sign_review(self,op,current,transport):
  self.need(current==self.ctx and transport==self.completed_challenge(),'ADAPTER_CHALLENGE_FROZEN');self.verify_authority_runtime(current);raw=self.f.read(self.home/(op+'.SIGNED.SNAPSHOT.json'));snapshot=self.f.strict(raw)
  control=self.api.wait_control(current,'BOUND_REVIEW',OPERATIONS.index(op)+1,'2026-10-08T12:30:00Z');doc=control['document'];self.need(all(doc.get(k)==x for k,x in current.items()) and doc['operation']==op and all(doc[k]==snapshot[k] for k in ('sheet_sha256','request_sha256','payload_sha256')),'ADAPTER_BOUND_REVIEW_OWN_BYTES')
  q=self.api.review_by_body_hash(doc['review_body_sha256'],self.now);self.need(all(x in q['body'] for x in (snapshot['request_sha256'],snapshot['payload_sha256'],'SIM_CODEX_REVIEW_OF_THE_BOUND_SET')),'ADAPTER_BOUND_REVIEW_SCOPE')
  review_path=self.home/(op+'.BOUND_REVIEW.public.txt');self.f.put(review_path,q['body'].encode());self.reviews[op]=(review_path,self.f.sha(q['body'].encode()),q);snapshot['bound_review_verified']=True
  self.need(self.snapshot(op)==snapshot,'ADAPTER_SNAPSHOT_REDERIVED');return snapshot
 def snapshot(self,op):
  v=self.inspect('snapshot',self.bound(op));v['bound_review_verified']=False
  if op in self.reviews:
   path,pin,q=self.reviews[op];self.f.read(path,pin);self.need(self.api.comment(q['id'])==q,'ADAPTER_REVIEW_CHANGED');v['bound_review_verified']=True
  return v
 def night_branch(self):
  if self.night is None:
   control=self.api.wait_control(self.ctx,'NIGHT_GATES',1,'2026-10-08T13:58:39Z');self.need(control['document_sha256']==control['manifest_sha256'],'ADAPTER_NIGHT_MANIFEST_BODY_PIN');cipher=self.api.blob(control['blob_sha'],control['ciphertext_sha256']);p=self.home/'NIGHT.tar.age';self.f.put(p,cipher);tar=self.home/'NIGHT.tar';self.call('decrypt',['--age',self.s['age'],'--key',self.home/'age-key','--cipher',p,'--cipher-sha256',control['ciphertext_sha256'],'--out',tar]);out=self.home/'night';result=self.call('night_import',['--tar',tar,'--manifest-sha256',control['manifest_sha256'],'--out',out]);self.night=(result['slot'],out)
  return self.night[0]
 def prerequisite(self,op,slot):
  self.need(self.night is not None and self.night[0]==slot,'ADAPTER_BRANCH_CHANGED');return self.inspect('night',self.night[1]/op/'bound','--slot',slot,'--operation',op)
 def check(self,op,step):
  self.verify_authority_runtime(self.ctx);args=['check','--bound',self.bound(op),'--family',self.root/'families'/('k9_phase_read' if op in ('policy_read','capture_result') else 'k9_phase_step'),'--step',step]
  if op in ('capture_launch','capture_cleanup'):
   p=self.home/(op+'.'+step+'.GATES.json');self.put(p,dict(schema='BIND_ONCE_DISPATCH_GATES_V1',codex_review=dict(document_file=str(self.reviews[op][0]),form='BOUND_SET')));args+=['--gates',p]
  value=self.call('binder',args);self.need(value.get('verdict')==('VALID_WINDOW_OPEN' if step=='prepare' else 'VALID_RESUME_ALLOWED_BY_THE_GATES') and value.get('dispatch_allowed_by_the_gates') is True,'ADAPTER_CHECK_GATES_CLOCK_REFUSED')
 def dispatcher(self,op,phase,proof=None):
  bound=self.bound(op);role='read_dispatch' if op in ('policy_read','capture_result') else 'step_dispatch';self.need(self.f.sha(self.f.read(bound/'dispatch_once.py'))==self.layout['tools'][role]['sha256'],'ADAPTER_DISPATCH_SOURCE_MATCH');cfg=bound/'DISPATCH.BOUND.json';args=['--config',cfg,'--config-sha256',self.f.sha(self.f.read(cfg)),'--phase',phase]
  if proof:args+=['--publication-proof',proof['publication_proof_path'],'--publication-proof-sha256',proof['publication_proof_sha256']]
  return self.call(role,args,allowed=(2,) if phase=='prepare' else (0,),timeout=180)
 def prepare_publish(self,op):
  result=self.dispatcher(op,'prepare');self.need(result.get('status')=='AWAITING_PUBLICATION_NO_SPAWN','ADAPTER_INTENT_NO_SPAWN');intent=self.inspect('intent',self.bound(op));q=self.api.publish('INTENT',self.ctx,dict(operation=op,status='AWAITING_PUBLICATION_NO_SPAWN',intent_sha256=intent['intent_sha256'],config_sha256=intent['config_sha256'],go_sha256=intent['go_sha256'],request_sha256=intent['request_sha256']))
  proof=self.call('binder',['publish-proof','--bound',self.bound(op),'--comment-id',q['id'],'--created-at',q['created_at']]);self.put(self.home/(op+'.PUBLICATION.json'),proof);return dict(comment_id=q['id'],created_at=q['created_at'],readback_exact=True,attempts=1)
 def resume_once(self,op):
  result=self.dispatcher(op,'resume',self.get(self.home/(op+'.PUBLICATION.json')));self.need(result.get('status')=='KNOWN_COMPLETE','ADAPTER_RESUME_UNCERTAIN_NO_RETRY')
 def status(self,op):return self.call('binder',['status','--bound',self.bound(op)])
 def run(self):
  policy=load(self.root/'capture_job/session_policy.py',self.layout['helpers']['capture_job/session_policy.py'],'capture_live_policy');result=policy.run_after_preflight(self);self.put(self.home/'FLOW.RESULT.private.json',result);exports={'FLOW.RESULT.private.json':self.home/'FLOW.RESULT.private.json'}
  for op in OPERATIONS:
   cfg=self.get(self.bound(op)/'DISPATCH.BOUND.json');attempt=pathlib.Path(cfg['attempt_directory'])
   for name in ('exit.json','stdout.private.json','stderr.private'):exports[op+'/'+name]=attempt/name
  digest=self.archive_cipher(exports,'FLOW_RESULTS');self.api.publish('RESULT',self.ctx,dict(status='FLOW_COMPLETE_REQUIRES_REVIEW',ciphertext_sha256=digest,files=len(exports)))
 def stage(self,name):
  self.need(name in STAGES and not (self.home/'HALTED.json').exists(),'ADAPTER_STAGE');i=STAGES.index(name)
  if i>0:
   previous=self.get(self.home/(STAGES[i-1]+'.COMPLETE.json'));self.need(previous.get('stage')==STAGES[i-1] and previous.get('context')==self.ctx,'ADAPTER_STAGE_ORDER')
  self.put(self.home/(name+'.ENTERED.json'),dict(stage=name,context=self.ctx,entered_at=self.now().strftime('%Y-%m-%dT%H:%M:%SZ')))
  getattr(self,name.replace('-','_'))();self.put(self.home/(name+'.COMPLETE.json'),dict(stage=name,context=self.ctx,operational_READY=False))

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('stage',choices=STAGES);ap.add_argument('--state',required=True);a=ap.parse_args();adapter=None
 try:adapter=Live(a.state);adapter.stage(a.stage);print('{"status":"STAGE_COMPLETE","operational_READY":false}');return 0
 except BaseException:
  if adapter is not None:
   try:adapter.put(adapter.home/'HALTED.json',dict(status='HALTED_NO_RETRY',stage=a.stage,context=adapter.ctx,operational_READY=False))
   except Exception:pass
   try:adapter.api.publish('REFUSED',adapter.ctx,dict(status='HALTED_NO_RETRY'))
   except Exception:pass
  print('{"status":"STAGE_REFUSED_OR_UNCERTAIN_NO_RETRY","operational_READY":false}');return 2
if __name__=='__main__':raise SystemExit(main())
