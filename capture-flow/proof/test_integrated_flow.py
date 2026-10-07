"""New staged integration/refusal proofs. Synthetic only: no host/network/children."""
import ast,copy,datetime as dt,hashlib,io,json,os,pathlib,sys,tarfile,tempfile,types,unittest
sys.dont_write_bytecode=True
HOME=pathlib.Path(__file__).resolve().parent

def load(name):
 p=HOME/(name+'.py');m=types.ModuleType('proof_'+name);m.__file__=str(p);sys.modules[m.__name__]=m;exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
policy=load('session_policy');night=load('night_bundle');guard=load('checked_program');files=load('job_files');live=load('live_adapter');channel=load('job_channel')
CTX=dict(session='2026-10-08',run_id='12345678901',run_attempt=1,nonce='b'*32)
PIN='a'*64
class Adapter:
 def __init__(self):self.clock=policy.instant('2026-10-08T12:20:00Z');self.calls=[];self.bad=None;self.snapshots={op:self.make(op) for op in policy.OPERATIONS}
 def make(self,op):return dict(**CTX,operation=op,signature_model='PRE',slot='PRIMARY',signed=True,own_owner_record_verified=True,bound_review_verified=True,answered_at_utc='2026-10-08T12:19:00Z',observed_at_utc='2026-10-08T12:20:00Z',sheet_sha256=PIN,request_sha256=PIN,payload_sha256=PIN,config_sha256=PIN,owner_packet_sha256=PIN,host_binding_sha256=PIN,not_before=policy.WINDOWS[op][0],not_after=policy.WINDOWS[op][1])
 def identity(self):return dict(CTX)
 def now(self):return self.clock
 def wait_until(self,t):self.clock=max(self.clock,policy.instant(t));self.calls.append(('wait',t))
 def verify_authority_runtime(self,c):self.calls.append(('guard',dict(c)))
 def completed_challenge(self):return dict(**CTX,verified=self.bad!='challenge',status='KNOWN_COMPLETE',remote_uid=0,attempts=1,retry=False,remote_command='sudo -n /usr/bin/python3 -I -B -',no_host_file_access=True,config_sha256=PIN,receipt_sha256=PIN)
 def prepare_sign_review(self,op,*a):return copy.deepcopy(self.snapshots[op])
 def snapshot(self,op):
  v=copy.deepcopy(self.snapshots[op])
  if self.bad=='snapshot' and op=='capture_launch':v['request_sha256']='c'*64
  return v
 def night_branch(self):return 'SPARE' if self.bad!='branch' else None
 def prerequisite(self,op,slot):
  value=dict(verified=True,status='KNOWN_COMPLETE',outcome='DONE',success_criterion='DONE',day='2026-10-08',grid='G19',k9_operation=op,slot=slot,host_binding_sha256=PIN,request_sha256=PIN,payload_sha256=PIN,receipt_sha256=PIN,boot_id_sha256=PIN)
  if self.bad=='partial' and op=='commit_result':value['status']='KNOWN_PARTIAL'
  if self.bad=='wrong_host':value['host_binding_sha256']='c'*64
  if self.bad=='boot' and op=='publish_launch':value['boot_id_sha256']='c'*64
  if self.bad=='day':value['day']='2026-10-07'
  return value
 def check(self,op,step):self.calls.append(('check',op,step))
 def prepare_publish(self,op):
  self.calls.append(('D',op));return dict(comment_id=42,created_at=self.clock.strftime('%Y-%m-%dT%H:%M:%SZ'),readback_exact=self.bad!='readback',attempts=1)
 def resume_once(self,op):self.calls.append(('R',op,self.clock))
 def status(self,op):return dict(verified=True,status='UNCERTAIN' if self.bad=='uncertain' else 'KNOWN_COMPLETE',outcome='DONE',success_criterion='DONE',config_sha256=PIN)
class Tests(unittest.TestCase):
 def test_staged_flow_order_and_real_publication_delay(self):
  a=Adapter();v=policy.run_after_preflight(a);self.assertEqual(v['completed'],list(policy.OPERATIONS));self.assertFalse(v['operational_READY']);self.assertEqual([x[1] for x in a.calls if x[0]=='D'],list(policy.OPERATIONS))
  for x in [x for x in a.calls if x[0]=='R']:self.assertGreaterEqual(x[2],policy.instant(policy.WINDOWS[x[1]][0])+dt.timedelta(seconds=120))
 def refusal(self,bad):
  a=Adapter();a.bad=bad
  with self.assertRaises(policy.Refused):policy.run_after_preflight(a)
  return a
 def test_no_staged_flow_without_own_complete_challenge(self):self.assertFalse(any(x[0]=='D' for x in self.refusal('challenge').calls))
 def test_incomplete_commit_holds_launch(self):self.assertNotIn(('D','capture_launch'),self.refusal('partial').calls)
 def test_night_same_host_required(self):self.refusal('wrong_host')
 def test_night_same_boot_required(self):self.refusal('boot')
 def test_night_same_session_required(self):self.refusal('day')
 def test_no_branch_inferred(self):self.refusal('branch')
 def test_immutable_signed_request_before_D(self):self.assertNotIn(('D','capture_launch'),self.refusal('snapshot').calls)
 def test_unverified_publication_never_R(self):self.assertFalse(any(x[0]=='R' for x in self.refusal('readback').calls))
 def test_uncertainty_stops_future_operation(self):self.assertEqual([x for x in self.refusal('uncertain').calls if x[0]=='D'],[('D','policy_read')])
 def test_owner_band_no_late_REVIEW_promotion(self):
  a=Adapter();a.snapshots['policy_read']['observed_at_utc']='2026-10-08T12:30:01Z'
  with self.assertRaises(policy.Refused):policy.run_after_preflight(a)
 def test_late_policy_never_claimed(self):
  a=Adapter();a.clock=policy.instant('2026-10-08T12:35:00Z')
  with self.assertRaises(policy.Refused):policy.run_after_preflight(a)
  self.assertFalse(any(x[0]=='D' for x in a.calls))
 def make_tar(self,changed=None):
  names=('PREPARE.json','PARAMETERS.json','REQUEST.BOUND.json','DISPATCH.BOUND.json','CLAIM_ROOT_IDENTITY.json','GO_SCOPE.txt','FINAL_PAYLOAD.BOUND.py','SHA256SUMS','OWNER_QUESTION.txt')
  rows={op+'/bound/'+n:b'SYNTHETIC' for op in ('commit_result','publish_launch') for n in names}
  rows.update({op+'/bound/.dispatch-root/synthetic-once/exit.json':b'{}' for op in ('commit_result','publish_launch')})
  m=dict(schema='CAPTURE_NIGHT_EVIDENCE_V1',session='2026-10-08',grid='G19',slot='SPARE',files=[dict(path=n,bytes=len(b),sha256=night.sha(b)) for n,b in sorted(rows.items())]);raw=json.dumps(m,sort_keys=True,separators=(',',':')).encode();rows['MANIFEST.private.json']=raw
  if changed=='tampered':rows['commit_result/bound/PREPARE.json']=b'CHANGED'
  if changed=='extra':rows['arbitrary/credential']=b'FORBIDDEN'
  output=io.BytesIO()
  with tarfile.open(fileobj=output,mode='w',format=tarfile.USTAR_FORMAT) as t:
   for n,b in sorted(rows.items()):
    x=tarfile.TarInfo(n);x.size=len(b);x.mode=0o600;t.addfile(x,io.BytesIO(b))
  return output.getvalue(),night.sha(raw)
 def test_two_night_byte_sets_are_import_only(self):
  raw,p=self.make_tar();v,rows=night.inspect(raw,p);self.assertEqual(v['slot'],'SPARE');self.assertEqual(len(rows),20)
 def test_night_tampered_bytes_refuse(self):
  with self.assertRaises(night.Refused):night.inspect(*self.make_tar('tampered'))
 def test_night_unlisted_path_refuse(self):
  with self.assertRaises(night.Refused):night.inspect(*self.make_tar('extra'))
 def test_night_nonzero_trailing_refuse(self):
  raw,p=self.make_tar()
  with self.assertRaises(night.Refused):night.inspect(raw+b'x'*512,p)
 def test_exclusive_stage_claim_and_identity(self):
  with tempfile.TemporaryDirectory() as d:
   home=pathlib.Path(d).resolve();home.chmod(0o700);a=object.__new__(live.Live);a.home=home;a.f=files;a.ctx=CTX;a.now=lambda:policy.instant('2026-10-08T11:50:00Z');seen=[];a.challenge_sheet=lambda:seen.append('sheet');a.challenge_execute=lambda:seen.append('execute')
   a.stage('challenge-sheet');self.assertEqual(seen,['sheet'])
   with self.assertRaises(FileExistsError):a.stage('challenge-sheet')
   a.stage('challenge-execute');self.assertEqual(seen,['sheet','execute'])
 def test_stage_cannot_start_out_of_order(self):
  with tempfile.TemporaryDirectory() as d:
   a=object.__new__(live.Live);a.home=pathlib.Path(d).resolve();a.home.chmod(0o700);a.f=files;a.ctx=CTX
   with self.assertRaises(FileNotFoundError):a.stage('prepare-four')
 def test_durable_halt_blocks_every_stage(self):
  with tempfile.TemporaryDirectory() as d:
   a=object.__new__(live.Live);a.home=pathlib.Path(d).resolve();a.home.chmod(0o700);a.f=files;a.ctx=CTX;files.put(a.home/'HALTED.json',b'{}')
   with self.assertRaises(files.Refused):a.stage('challenge-sheet')
 def test_changed_dispatcher_refuses_before_child(self):
  with tempfile.TemporaryDirectory() as d:
   a=object.__new__(live.Live);a.home=pathlib.Path(d).resolve();a.home.chmod(0o700);a.f=files;a.layout=dict(tools=dict(read_dispatch=dict(sha256=PIN)));a.need=lambda v,c:files.need(v,c);b=files.directory(a.home/'bound',True);files.put(b/'dispatch_once.py',b'TAMPERED');a.bound=lambda op:b;a.call=lambda *x:(_ for _ in ()).throw(AssertionError('NO_CHILD'))
   with self.assertRaises(files.Refused):a.dispatcher('policy_read','prepare')
 def test_dispatcher_preload_uses_pinned_sibling_modules(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);home=root/pathlib.PurePosixPath(guard.PATHS['challenge_dispatch']).parent;home.mkdir(parents=True);pinned={};p={}
   for name in guard.DISPATCH_MODULES['challenge_dispatch']:
    raw=b'SYNTHETIC_VALUE=1\n';relative=str((home/(name+'.py')).relative_to(root));pinned[relative]=raw;p[name]=guard.sha(raw)
   try:
    guard.load_dispatch_modules('challenge_dispatch',root,dict(dispatch_runtime=dict(challenge_dispatch=p)),pinned)
    for name in p:self.assertEqual(sys.modules[name].SYNTHETIC_VALUE,1)
    with self.assertRaises(guard.Refused):guard.load_dispatch_modules('challenge_dispatch',root,dict(dispatch_runtime=dict(challenge_dispatch=p)),pinned)
   finally:
    for name in p:sys.modules.pop(name,None)
 def test_source_layout_requires_decrypt_night_import_and_fixed_tools(self):
  self.assertEqual(guard.PATHS['decrypt'],'capture_job/crypto_input.py');self.assertEqual(guard.PATHS['night_import'],'capture_job/night_bundle.py');self.assertEqual(guard.PATHS['controller'],'capture_job/live_adapter.py')
 def test_paginated_collection_uses_real_created_not_post_cursor(self):
  a=object.__new__(channel.API);calls=[];clock=lambda:policy.instant('2026-10-08T12:00:00Z')
  def request(p):
   calls.append(p);page=int(p.rsplit('=',1)[1]);return [dict(id=i+1+(page-1)*100,body='{}',created_at='2026-10-08T11:59:00Z') for i in range(100 if page==1 else 1)]
  a.request=request;rows=a.collect(clock);self.assertEqual(len(rows),101);self.assertEqual(len(calls),2);self.assertEqual(a.cursor,'2026-10-08T11:54:00Z')
 def test_matching_halt_never_ignored(self):
  a=object.__new__(channel.API);a.control_readback=lambda *x:{};q=dict(id=1,body=json.dumps(dict(schema='CAPTURE_JOB_CONTROL_V1',kind='HALT',sequence=1,**CTX)))
  with self.assertRaises(channel.Refused):a.halt_in([q],CTX)
 def test_previous_job_halt_not_new_authority(self):
  a=object.__new__(channel.API);q=dict(id=1,body=json.dumps(dict(schema='CAPTURE_JOB_CONTROL_V1',kind='HALT',sequence=1,**dict(CTX,nonce='c'*32))));a.halt_in([q],CTX)
 def test_actual_measurement_is_bound_to_job_nonce_source_authority_time(self):
  value=dict(**CTX,source_layout_sha256=PIN,dated_authority_sha256=PIN,measured_at_utc='2026-10-08T11:48:00Z');approval=dict(measured_at_utc=value['measured_at_utc']);guard.measurement_binding(value,CTX,PIN,PIN,approval)
  for k,replacement in [('run_id','12345678902'),('nonce','c'*32),('run_attempt',2),('source_layout_sha256','c'*64),('dated_authority_sha256','c'*64),('measured_at_utc','2026-10-07T11:48:00Z')]:
   bad=dict(value,**{k:replacement})
   with self.assertRaises(guard.Refused):guard.measurement_binding(bad,CTX,PIN,PIN,approval)
 def test_actual_answer_body_hash_is_checked_after_bridge(self):
  with tempfile.TemporaryDirectory() as d:
   a=object.__new__(live.Live);a.home=pathlib.Path(d).resolve();a.home.chmod(0o700);a.f=files;a.ctx=CTX;p=files.directory(a.home/'questions',True);p=files.directory(p/'policy_read',True);body=json.dumps(dict(sheet_sha256=PIN));files.put(p/'POST.READBACK.json',files.canonical(dict(id=3,body=body)));answer='{"answered_at_utc":"2026-10-08T12:00:00Z"}';control=dict(question_id=3,answer_id=4,sheet_sha256=PIN,document_sha256='c'*64)
   a.api=types.SimpleNamespace(wait_control=lambda *args:control)
   a.call=lambda *args:files.put(p/'OWNER_API.READBACK.json',files.canonical(dict(first=dict(id=4,body=answer),question_first=dict(id=3))))
   with self.assertRaises(files.Refused):a.packet('policy_read',2,'2026-10-08T12:30:00Z')
 def test_absolute_job_end_refuses_even_local_followup(self):
  real=live.dt.datetime
  class Clock(real):
   @classmethod
   def now(cls,*args):return policy.instant('2026-10-08T14:45:00Z')
  a=object.__new__(live.Live);a.f=files
  try:
   live.dt.datetime=Clock
   with self.assertRaises(files.Refused):a.now()
  finally:live.dt.datetime=real
 def test_exact_four_mac_sets_required(self):
  now=policy.instant('2026-10-08T11:50:00Z');value=dict(schema='CAPTURE_JOB_DATED_AUTHORITY_V1',status='SIGNED',owner='DUDU',answer='Assino',session='2026-10-08',source_layout_sha256=PIN,outside_Mac=True,single_job=True,single_use=True,retry=False,election='JOB_ONLY_MAC_CAPTURE_RETIRED_BEFORE_PREPARE',retired_mac_config_sha256=[x['config_sha256'] for x in guard.RETIRED_MAC_SETS.values()],document_sha256=PIN,source_owner_record_body_sha256=PIN,operator_election_record_body_sha256=PIN,signed_at_utc='2026-10-07T20:00:00Z',election_observed_at_utc='2026-10-07T20:01:00Z')
  guard.authority(value,PIN,now);value['retired_mac_config_sha256'][0]='c'*64
  with self.assertRaises(guard.Refused):guard.authority(value,PIN,now)
 def test_control_collection_incomplete_refuses(self):
  a=object.__new__(channel.API)
  def request(p):
   page=int(p.rsplit('=',1)[1]);return [dict(id=i+1+(page-1)*100,body='{}',created_at='2026-10-08T11:59:00Z') for i in range(100)]
  a.request=request
  with self.assertRaises(channel.Refused):a.collect(lambda:policy.instant('2026-10-08T12:00:00Z'))
 def test_review_survives_created_cursor_overlap_without_recollection(self):
  a=object.__new__(channel.API);q=dict(id=1,body='EXACT_REVIEW',created_at='2026-10-08T11:50:00Z',updated_at='2026-10-08T11:50:00Z');later=dict(id=2,body='LATER',created_at='2026-10-08T12:15:00Z',updated_at='2026-10-08T12:15:00Z');groups=iter([[q],[later],[]]);calls=[]
  a.request=lambda path:(calls.append(path) or next(groups));a.comment=lambda cid:q
  clock=lambda:policy.instant('2026-10-08T12:20:00Z');a.collect(clock);a.collect(clock);self.assertEqual(a.cursor,'2026-10-08T12:10:00Z');self.assertEqual(a.review_by_body_hash(channel.sha(q['body'].encode()),clock),q);self.assertIn('12%3A10%3A00Z',calls[-1])
 def test_review_after_collection_must_retain_exact_unedited_bytes(self):
  a=object.__new__(channel.API);q=dict(id=1,body='EXACT_REVIEW',created_at='2026-10-08T11:50:00Z',updated_at='2026-10-08T11:50:00Z');a.request=lambda path:[q];a.comment=lambda cid:dict(q,body='ALTERED_REVIEW')
  with self.assertRaises(channel.Refused):a.review_by_body_hash(channel.sha(q['body'].encode()),lambda:policy.instant('2026-10-08T12:20:00Z'))
 def test_operational_children_always_grouped_guard_no_shell(self):
  t=ast.parse((HOME/'live_adapter.py').read_bytes());calls=[n for n in ast.walk(t) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and ast.unparse(n.func)=='subprocess.run'];self.assertEqual(len(calls),1);self.assertTrue(all(not any(k.arg=='shell' for k in n.keywords) for n in calls));self.assertIn("'--tool',role,'--'",(HOME/'live_adapter.py').read_text())
 def test_challenge_receipt_literal_matches_sealed_source(self):
  source=(HOME.parent/'codex-capture-single-runner-20261007-candidate7/transport_challenge/capture_transport_challenge.py').read_text() if (HOME.parent/'codex-capture-single-runner-20261007-candidate7').exists() else "COMPLETE_STATUS='METADATA_ONLY_REQUIRES_REVIEW'"
  self.assertIn("COMPLETE_STATUS='METADATA_ONLY_REQUIRES_REVIEW'",source);self.assertIn("receipt.get('status')=='METADATA_ONLY_REQUIRES_REVIEW'",(HOME/'inspect_bound.py').read_text())
if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):denied.append(event);raise RuntimeError('SYNTHETIC_PROOF_NO_NETWORK_CHILD_HOST')
 sys.addaudithook(audit);result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));report=dict(schema='CAPTURE_STAGED_FLOW_SYNTHETIC_PROOF_V1',methods=result.testsRun,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),host_calls=0,actual_prepare_sign_dispatch=0,full_physical_job_proof=False,operational_READY=False,source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(HOME.glob('*.py'))})
 out=HOME/'INTEGRATION_RESULT.public.json'
 with out.open('x') as f:f.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report,sort_keys=True));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
