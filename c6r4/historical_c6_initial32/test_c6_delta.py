"""NEW C6 delta fixtures; no closed suite or app imports/runs."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import copy,json,os,tempfile,unittest
import finite_batch as c
import image_path_adapter as a
import image_capacity_gate as g
import k9_receipt_adapter as k
from synthetic_capacity_fixture import fixture,OPEN,CAPTURE_OPEN,CAPTURE_CLOSE
CLOSE=OPEN+timedelta(hours=6,minutes=30)

class DownFixture:
 def __init__(self):
  self.authority=c.canonical({'fixture':'SYNTHETIC_NOT_AUTHORITY'});self.runtime=c.canonical({'fixture':'SYNTHETIC_NOT_RUNTIME'})
  self.at=datetime(2026,10,12,7,tzinfo=timezone.utc);prepared=datetime(2026,10,11,18,tzinfo=timezone.utc);ctx=(c.EPOCH,c.DAY,c.PREVIOUS,'P');self.receipts={}
  for role in ('commit_result','publish_launch'):
   raw=c.canonical({'fixture':'SYNTHETIC_NOT_OPERATIONAL_RECEIPT','role':role});self.receipts[role]=c.Receipt(raw,role,ctx,'COMPLETE',prepared-timedelta(hours=1))
  windows={'reader_bound':(OPEN-timedelta(minutes=30),OPEN-timedelta(minutes=2)),
   'reader_cycle':(OPEN-timedelta(seconds=90),OPEN+timedelta(minutes=2)),
   'policy_read':(OPEN+timedelta(minutes=10),OPEN+timedelta(minutes=11)),
   'capture_launch':(OPEN+timedelta(minutes=20),CAPTURE_CLOSE+timedelta(minutes=2)),
   'capture_result':(CAPTURE_CLOSE+timedelta(minutes=24),CAPTURE_CLOSE+timedelta(minutes=29))}
  self.q={'schema':'L12_FINITE_BATCH_REQUEST_CANDIDATE_V1','lane':'DOWNSTREAM_AFTER_E6','epoch':c.EPOCH,'session':c.DAY,'previous_session':c.PREVIOUS,'track':'P',
   'prepared_at':c.iso(prepared),'owner_deadline':c.iso(prepared+timedelta(hours=1)),'authority_sha256':c.sha(self.authority),'runtime_sha256':c.sha(self.runtime),
   'veto_authority_sha256':c.sha(b'SYNTHETIC_VETO_AUTH'),'initial_receipts':{r:c.sha(x.raw) for r,x in self.receipts.items()},'tasks':[]}
  for i,op in enumerate(c.DOWNSTREAM):
   start,end=windows.get(op,(self.at+timedelta(minutes=i*2),self.at+timedelta(minutes=i*2+1)))
   self.q['tasks'].append({'operation':op,'not_before':c.iso(start),'not_after':c.iso(end),'budget_seconds':1,'requires':list(c.MINIMUM_DEPENDENCIES[op])})
  request=c.canonical(self.q);owner=c.canonical({'schema':'L12_OWNER_RECORD_CANDIDATE_V1','answer':'Assino','channel':'REGISTRO_PELA_FABLE','request_sha256':c.sha(request),
   'question_sha256':c.sha(b'SYNTHETIC_QUESTION'),'question_published_at':c.iso(prepared+timedelta(seconds=1)),'signed_at':c.iso(prepared+timedelta(seconds=2))})
  docs=(('authority',self.authority),('owner',owner),('runtime',self.runtime));bound=c.canonical({'schema':'L12_BOUND_CANDIDATE_V1','request_sha256':c.sha(request),
   'documents_sha256':{n:c.sha(x) for n,x in docs},'bound_at':c.iso(prepared+timedelta(seconds=3))});self.bundle=c.Bundle(request,bound,docs)
 def task(self,op):return next(t for t in self.q['tasks'] if t['operation']==op)

class BridgeFixture:
 def __init__(self):
  self.scope,self.receipt,self.row,self.records,self.manifest,self.ready,self.catalog,self.session=fixture();self.down=DownFixture()
  self.scope=replace(self.scope,finite_authority_sha256=self.down.q['authority_sha256']);self.at=OPEN-timedelta(minutes=29);self.journal=a.DirectoryPin(1,99,0)
  self.epoch=a.FileEvidence(a.canonical({'schema':'MASSIVE_SESSION_ROOT_V1','epoch':a.EPOCH,'device':1,'inode':99}),1,5,0,0,0o600,1)
 def snapshot(self):return g.Snapshot(a.canonical(self.receipt),a.canonical(self.row),a.canonical(self.records),self.manifest,self.at,self.epoch,self.journal,
   '/synthetic-private-journal',self.ready,self.catalog,self.session,CLOSE,self.scope.calendar_pin_sha256)
 def gate(self,reader=None,verifier=None):return g.ImageCapacityGate(self.scope,reader or (lambda *args:self.snapshot()),verifier or (lambda *args:None),
   journal_directory='/synthetic-private-journal',clock=lambda:self.at)
 def call(self,phase,op):return self.gate()(self.down.q,phase,self.at,self.down.task(op))
 def copy(self):
  self.row['state']['sessions'][self.scope.day]={'capacity_binding':copy.deepcopy(self.row['state']['daily_capacity'][self.scope.day])};self.row['state_sha']=a.digest(self.row['state'])

class NewC6Bridge(unittest.TestCase):
 def setUp(self):self.x=BridgeFixture()
 def test_new_preopen_epoch_root_without_ready_or_copy(self):
  x=self.x;out=replace(x.snapshot(),ready=None,session_manifest=None,session_root=None,session_close=None)
  self.assertIsNone(x.gate(reader=lambda *a:out)(x.down.q,'BEFORE_READER_PROCESS_LAUNCH',x.at,x.down.task('reader_bound')))
 def test_new_first_session_at_old_deadline(self):
  x=self.x;x.at=OPEN-timedelta(seconds=10);self.assertIsNone(x.call('BEFORE_FIRST_READER','reader_cycle'))
 def test_new_post_open_ready_with_separate_window(self):
  x=self.x;x.at=OPEN+timedelta(seconds=32);self.assertIsNone(x.call('BEFORE_FIRST_READER','reader_cycle'))
 def test_new_first_session_needs_ready(self):
  x=self.x;x.at=OPEN;out=replace(x.snapshot(),ready=None)
  with self.assertRaisesRegex(c.Hold,'IMAGE_SESSION_EVIDENCE_MISSING'):x.gate(reader=lambda *a:out)(x.down.q,'BEFORE_FIRST_READER',x.at,x.down.task('reader_cycle'))
 def test_new_calendar_close_pin_mandatory(self):
  x=self.x;x.at=OPEN
  for out in (replace(x.snapshot(),session_close=None),replace(x.snapshot(),calendar_pin_sha256='b'*64)):
   with self.assertRaisesRegex(c.Hold,'IMAGE_CALENDAR_CLOSE_UNBOUND'):x.gate(reader=lambda *a:out)(x.down.q,'BEFORE_FIRST_READER',x.at,x.down.task('reader_cycle'))
 def test_new_first_cycle_case_b_without_copy(self):
  x=self.x;x.at=OPEN+timedelta(seconds=1);self.assertIsNone(x.call('AFTER_FIRST_CYCLE','reader_cycle'))
 def test_new_capture_launch_case_b_without_copy(self):
  x=self.x;x.at=OPEN+timedelta(minutes=22);self.assertIsNone(x.call('BEFORE_CAPTURE_LAUNCH','capture_launch'))
 def test_new_cleanup_budget_does_not_extend_launch(self):
  x=self.x;x.at=CAPTURE_CLOSE
  with self.assertRaisesRegex(c.Hold,'CAPTURE_LAUNCH_WINDOW_CLOSED'):x.call('BEFORE_CAPTURE_LAUNCH','capture_launch')
 def test_new_after_capture_needs_matching_copy(self):
  x=self.x;x.at=CAPTURE_CLOSE
  with self.assertRaisesRegex(c.Hold,'DB_SESSION_BINDING_MISSING_OR_CHANGED'):x.call('AFTER_CAPTURE','capture_launch')
  x.copy();self.assertIsNone(x.call('AFTER_CAPTURE','capture_launch'))
 def test_new_mismatched_optional_copy_refuses_precapture(self):
  x=self.x;x.copy();x.row['state']['sessions'][x.scope.day]['capacity_binding']['sha']='c'*64;x.row['state_sha']=a.digest(x.row['state']);x.at=OPEN+timedelta(minutes=22)
  with self.assertRaisesRegex(c.Hold,'DB_SESSION_BINDING_MISSING_OR_CHANGED'):x.call('BEFORE_CAPTURE_LAUNCH','capture_launch')
 def test_new_epoch_catalog_is_not_session_catalog(self):
  x=self.x;out=replace(x.snapshot(),epoch_catalog=x.catalog,journal_root=x.session)
  with self.assertRaisesRegex(c.Hold,'JOURNAL_EPOCH_ROOT_MISMATCH'):x.gate(reader=lambda *a:out)(x.down.q,'BEFORE_READER_PROCESS_LAUNCH',x.at,x.down.task('reader_bound'))
 def test_new_settings_root_mismatch_before_process(self):
  x=self.x;out=replace(x.snapshot(),settings_journal_directory='/synthetic-other-root')
  with self.assertRaisesRegex(c.Hold,'JOURNAL_SETTINGS_ROOT_MISMATCH'):x.gate(reader=lambda *a:out)(x.down.q,'BEFORE_READER_PROCESS_LAUNCH',x.at,x.down.task('reader_bound'))
 def test_new_snapshot_verifier_delay_cannot_cross_window(self):
  x=self.x;original=x.at
  def delayed(*args):x.at=original+timedelta(minutes=40)
  with self.assertRaisesRegex(c.Hold,'IMAGE_SNAPSHOT_NOT_FRESH'):x.gate(verifier=delayed)(x.down.q,'BEFORE_READER_PROCESS_LAUNCH',original,x.down.task('reader_bound'))
 def test_new_phase_cannot_use_other_task(self):
  x=self.x
  with self.assertRaisesRegex(c.Hold,'IMAGE_GATE_TASK_UNBOUND'):x.gate()(x.down.q,'BEFORE_CAPTURE_LAUNCH',x.at,x.down.task('reader_bound'))
 def test_new_session_window_independent_of_writer_window(self):
  x=self.x;x.at=OPEN+timedelta(seconds=30);self.assertGreater(x.at,x.scope.not_after);self.assertIsNone(x.call('BEFORE_FIRST_READER','reader_cycle'))
 def test_new_false_verifier_not_evidence(self):
  x=self.x
  with self.assertRaisesRegex(c.Hold,'ADAPTER_DID_NOT_ATTEST'):x.gate(verifier=lambda *a:False)(x.down.q,'BEFORE_READER_PROCESS_LAUNCH',x.at,x.down.task('reader_bound'))

class NewC6Core(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='new-c6-core-',dir=Path(__file__).parent);self.root=Path(self.temp.name);os.chmod(self.root,0o700)
  self.root.joinpath('attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)));self.x=DownFixture();self.at=self.x.at;self.phases=[];self.effects=[]
  def execute(inv):
   self.effects.append(inv.operation);raw=c.canonical({'fixture':'SYNTHETIC_COMPLETE_ONLY','operation':inv.operation,'completed_at':c.iso(self.at)})
   item=c.Receipt(raw,inv.operation,inv.context,'COMPLETE',self.at);self.x.receipts[inv.operation]=item;return item
  def capacity(q,phase,n,task):self.phases.append((phase,task['operation']))
  self.services=c.Services(authority=lambda *a:None,identity=lambda *a:None,receipt_read=lambda role,*a:self.x.receipts.get(role),receipt_verify=lambda *a:None,
   operation_gate=lambda *a:None,veto_read=lambda q,t,n:c.VetoView(b'SYNTHETIC_CURRENT',q['veto_authority_sha256'],'ALLOW',n,n+timedelta(seconds=5)),
   veto_verify=lambda *a:None,execute=execute,capacity_path=capacity)
  self.batch=c.FiniteBatch(self.x.bundle,self.ledger,self.services,clock=lambda:self.at,monotonic=lambda:0)
 def tearDown(self):self.ledger.close();self.temp.cleanup()
 def seed(self,op):
  self.at=c.instant(self.x.task(op)['not_before']);key=self.batch.reserve(op);out=self.batch.run_reserved(op,key,terminal=True)
  self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out);return out
 def test_new_post_publish_without_admission(self):
  self.seed('e6');self.seed('post');self.assertEqual(self.effects,['e6','post']);self.assertNotIn('admission_manifest',self.x.receipts)
 def test_new_process_session_and_first_cycle_have_distinct_phases(self):
  for op in ('e6','admission_manifest','post','reader_bound','reader_cycle'):self.seed(op)
  self.assertEqual(self.phases,[('BEFORE_READER_PROCESS_LAUNCH','reader_bound'),('BEFORE_FIRST_READER','reader_cycle'),('AFTER_FIRST_CYCLE','reader_cycle')])
 def test_new_capture_copy_gate_follows_complete_effect(self):
  for op in ('e6','admission_manifest','post','reader_bound','reader_cycle','policy_read','capture_launch'):self.seed(op)
  self.assertEqual(self.phases[-2:],[('BEFORE_CAPTURE_LAUNCH','capture_launch'),('AFTER_CAPTURE','capture_launch')])
 def test_new_capture_missing_copy_uncertain_and_consumed_after_one_effect(self):
  for op in ('e6','admission_manifest','post','reader_bound','reader_cycle','policy_read'):self.seed(op)
  def gate(q,phase,n,task):
   if phase=='AFTER_CAPTURE':raise c.Hold('DB_SESSION_BINDING_MISSING_OR_CHANGED')
  self.batch.services=replace(self.services,capacity_path=gate);self.at=c.instant(self.x.task('capture_launch')['not_before']);key=self.batch.reserve('capture_launch')
  out=self.batch.run_reserved('capture_launch',key,terminal=True);self.assertEqual(out['status'],'UNCERTAIN_CONSUMED');self.assertEqual(out['effect_calls'],1)
  with self.assertRaisesRegex(c.ReservationFailure,'ATTEMPT_ALREADY_CONSUMED'):self.batch.reserve('capture_launch')

def runner_fixture(role='capture_launch'):
 ops={'collect_launch':('causal_list','PROVIDER',None),'commit_launch':('causal_list','DATABASE',None),'publish_launch':('causal_list','DATABASE',None),'capture_launch':('capture','PROVIDER',None)}
 constants={'EPOCH':c.EPOCH,'DAYS':(c.DAY,),'PACKAGE':'d'*64,'REVISION':'e'*40,'OPS':ops,'RECEIPT_KEYS':k.RECEIPT_KEYS,'PLAN_KEYS':k.PLAN_KEYS,
  'CONST_KEYS':k.CONST_KEYS,'LIMITS':{'synthetic':True},'FLOOR':1,'DB':{'synthetic':True}}
 source=('"""SYNTHETIC_METADATA_ONLY_NOT_REAL_RUNNER"""\n'+''.join(n+'='+repr(v)+'\n' for n,v in constants.items())).encode();op=k.ALIASES[role];phase,network,_=ops[op]
 key=c.sha(json.dumps([c.EPOCH,c.DAY,phase,op],separators=(',',':')).encode())
 plan={'schema':'K9_STEP_PLAN_V1','epoch':c.EPOCH,'day':c.DAY,'k9_phase':phase,'k9_operation':op,'slot':'SYNTHETIC_ONLY','attempt_key':key,
  'request_sha256':'1'*64,'go_sha256':'2'*64,'run_not_after':'2026-10-12T14:03:00+00:00',
  'constants':{'package_sha256':constants['PACKAGE'],'code_revision':constants['REVISION'],'act_b_sha256':'3'*64,'release_sha256':'4'*64,
   'policy_sha256':'5'*64,'runner_sha256':c.sha(source),'risk_source_pins_sha256':'6'*64,'risk_limits':constants['LIMITS'],'disk_floor_bytes':constants['FLOOR']},
  'network_class':network,'database':constants['DB'] if op in ('commit_launch','publish_launch') else None,'risk':None,'step_row':{}}
 raw=c.canonical(plan);binding=k.Binding(role,raw,source,c.sha(source),'7'*64)
 doc={'schema':'K9_STEP_RECEIPT_V1','status':'COMPLETE','code':None,'epoch':c.EPOCH,'day':c.DAY,'phase':phase,'operation':op,'attempt_key':key,
  'step_plan_sha256':c.sha(raw),'started_at':'2026-10-12T13:52:00+00:00','completed_at':'2026-10-12T14:01:00+00:00',
  'package_sha256':constants['PACKAGE'],'build_sha':constants['REVISION'],
  'outputs':{'source/snapshot.json':'8'*64,'source/tape/'+c.DAY+'.us-quote.ndjson':'9'*64} if op=='capture_launch' else {},
  'aggregates':{},'counts':{'capture_complete':1,'consumer_failed':0} if op=='capture_launch' else {}}
 now=CAPTURE_CLOSE+timedelta(seconds=1);inv=c.Invocation(role,(c.EPOCH,c.DAY,c.PREVIOUS,'P'),'a'*64,'b'*64,now+timedelta(seconds=30),10,())
 return binding,doc,inv,now

class NewK9ABI(unittest.TestCase):
 def setUp(self):self.binding,self.doc,self.inv,self.now=runner_fixture()
 def decode(self,doc=None,verifier=None,raw=None):return k.K9ReceiptAdapter(self.binding,verifier if verifier is not None else (lambda *a:None)).decode(
   raw if raw is not None else c.canonical(self.doc if doc is None else doc),self.inv,now=self.now)
 def test_new_abi_plus00_times_preserve_original_bytes(self):
  raw=c.canonical(self.doc)+b'\n';out=self.decode(raw=raw);self.assertEqual(out.raw,raw);self.assertEqual(out.completed_at,CAPTURE_CLOSE);self.assertEqual(out.role,'capture_launch')
 def test_new_actual_historical_epoch03_source_refused_without_import(self):
  source=Path('../fable-k9runner-20261004/k9_runner.py').read_bytes();self.assertEqual(c.sha(source),'563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690')
  with self.assertRaisesRegex(c.Hold,'K9_RUNNER_EPOCH04_ORIGINAL_REQUIRED'):k.K9ReceiptAdapter(replace(self.binding,runner_source_raw=source,runner_source_sha256=c.sha(source)),lambda *a:None)
 def test_new_started_failed_deadline_refused_not_complete(self):
  for status in ('STARTED','FAILED','DEADLINE','REFUSED'):
   with self.assertRaisesRegex(c.Hold,'K9_ORIGINAL_NOT_EXACT_COMPLETE'):self.decode({**self.doc,'status':status})
 def test_new_step_plan_attempt_package_build_pins_exact(self):
  for name in ('step_plan_sha256','attempt_key','package_sha256','build_sha'):
   with self.assertRaisesRegex(c.Hold,'K9_ORIGINAL_NOT_EXACT_COMPLETE'):self.decode({**self.doc,name:'c'*len(self.doc[name])})
 def test_new_capture_success_and_consumer_failure_counts(self):
  for counts in ({'capture_complete':0,'consumer_failed':0},{'capture_complete':1,'consumer_failed':1},{'capture_complete':True,'consumer_failed':0}):
   with self.assertRaises(c.Hold):self.decode({**self.doc,'counts':counts})
 def test_new_capture_outputs_snapshot_and_tape_required(self):
  with self.assertRaisesRegex(c.Hold,'K9_CAPTURE_ACTUAL_COMPLETE_REQUIRED'):self.decode({**self.doc,'outputs':{'source/snapshot.json':'8'*64}})
 def test_new_future_deadline_and_nonutc_clocks_refuse(self):
  for value in ('2026-10-12T14:04:00+00:00','2026-10-12T14:00:00-04:00'):
   with self.assertRaises(c.Hold):self.decode({**self.doc,'completed_at':value})
 def test_new_original_verifier_required_and_bool_refused(self):
  with self.assertRaisesRegex(c.Hold,'REAL_ADAPTER_UNAVAILABLE'):k.K9ReceiptAdapter(self.binding,None).decode(c.canonical(self.doc),self.inv,now=self.now)
  with self.assertRaisesRegex(c.Hold,'ADAPTER_DID_NOT_ATTEST'):self.decode(verifier=lambda *a:True)
 def test_new_verifier_cannot_change_decoded_original(self):
  def mutate(raw,binding,inv,n,doc,*args):doc['counts']['consumer_failed']=1
  with self.assertRaisesRegex(c.Hold,'K9_VERIFIER_CHANGED_ORIGINALS'):self.decode(verifier=mutate)
 def test_new_duplicate_keys_and_extra_fields_refused(self):
  with self.assertRaises(c.Hold):self.decode(raw=b'{"schema":"x","schema":"y"}')
  with self.assertRaisesRegex(c.Hold,'K9_ORIGINAL_NOT_EXACT_COMPLETE'):self.decode({**self.doc,'extra':'NOT_ABI'})
 def test_new_stdout_summary_is_not_actual_runner_receipt(self):
  with self.assertRaisesRegex(c.Hold,'K9_ORIGINAL_NOT_EXACT_COMPLETE'):self.decode({'status':'CAPTURED','symbols':2})
 def test_new_alias_cannot_promote_collect_to_capture_or_risk(self):
  binding,doc,inv,now=runner_fixture('collect')
  for role in ('capture_launch','post'):
   with self.assertRaisesRegex(c.Hold,'K9_CORE_OPERATION_UNBOUND'):k.K9ReceiptAdapter(replace(binding,core_operation=role),lambda *a:None)

if __name__=='__main__':unittest.main(verbosity=2)
