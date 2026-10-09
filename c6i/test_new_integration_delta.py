"""NEW source integration fixtures only. No apps, host, SQL or operational GO."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import copy,json,time,unittest
from unittest.mock import patch
import finite_batch as c
import image_path_adapter as a
import ready_wait_gate as w
import capacity_monday_gate as m
import k9_receipt_adapter as k
from verification_binding import Verifier
from synthetic_bridge_plan import DownFixture
from synthetic_gate_fixture import fixture,OPEN

def verifier(identity='fixture_verify',callback=None,mode='FIXTURE'):
    return Verifier(mode,identity,'a'*64,callback or(lambda *a:None))
def vpin(identity='fixture_verify'):return {'identity':identity,'source_sha256':'a'*64}
def bundle(q):return c.Bundle(c.canonical(q),c.canonical({'fixture':'SYNTHETIC_BOUND'}),())

class ReadyDelta(unittest.TestCase):
 def setUp(self):
  self.d=DownFixture();self.q=self.d.q;self.task=self.d.task('reader_cycle');self.task['budget_seconds']=60
  self.bundle=bundle(self.q);self.now=OPEN-timedelta(seconds=10);self.mono=100.;self.calls=0
  self.rule={'schema':'L12_READY_WAIT_RULE_CANDIDATE_V1','mode':'FIXTURE','epoch':c.EPOCH,'day':c.DAY,
   'request_sha256':c.sha(self.bundle.request),'bound_sha256':c.sha(self.bundle.bound),'calendar_sha256':'c'*64,
   'not_before':self.task['not_before'],'not_after':self.task['not_after'],'max_wait_seconds':60,'poll_seconds':1,
   'verifiers':{'rule':vpin(),'ready':vpin()}}
  self.ready=fixture()[5]
 def gate(self,reader=None,verify=None):
  raw=c.canonical(self.rule);return w.ReadyWaitGate(raw,rule_sha256=c.sha(raw),read_ready=reader or(lambda *a:self.ready),
      verify_rule=verifier(),verify_ready=verify or verifier())
 def call(self,g):
  def sleep(seconds):self.now+=timedelta(seconds=seconds);self.mono+=seconds
  with patch.object(w,'native_utc',lambda:self.now),patch.object(w.time,'monotonic',lambda:self.mono),patch.object(w.time,'sleep',sleep):
   return g(self.bundle,self.q,self.task,OPEN-timedelta(seconds=60))
 def test_absent_then_ready_after_open32_inside_same_finite_call(self):
  def reader(*args):
   self.calls+=1
   return None if self.now<OPEN+timedelta(seconds=32)else self.ready
  self.assertIsNone(self.call(self.gate(reader)));self.assertEqual(self.calls,43)
 def test_absence_hits_finite_limit_and_never_creates_effect(self):
  self.rule['max_wait_seconds']=2
  with self.assertRaisesRegex(c.Hold,'READY_WAIT_DEADLINE'):self.call(self.gate(lambda *a:None))
  self.assertEqual(self.mono,102.)
 def test_present_wrong_day_is_fatal_without_wait_retry(self):
  self.ready=replace(self.ready,raw=a.canonical({'epoch':c.EPOCH,'session':'2026-10-09'}))
  with self.assertRaisesRegex(c.Hold,'READY_WAIT_ORIGINAL_DIVERGENT'):self.call(self.gate())
  self.assertEqual(self.mono,100.)
 def test_rule_and_bound_actual_original_are_not_self_reported(self):
  self.bundle=replace(self.bundle,bound=b'SYNTHETIC_CHANGED')
  with self.assertRaisesRegex(c.Hold,'READY_WAIT_INVOCATION_UNBOUND'):self.call(self.gate())
 def test_late_namespace_verifier_cannot_freeze_utc(self):
  def late(*args):self.mono+=61
  with self.assertRaisesRegex(c.Hold,'READY_WAIT_DEADLINE'):self.call(self.gate(verify=verifier(callback=late)))
 def test_real_bare_callback_without_loaded_approved_module_refuses(self):
  self.rule['mode']='REAL';raw=c.canonical(self.rule)
  with self.assertRaisesRegex(c.Hold,'REAL_VERIFIER_LOADED_MODULE_REQUIRED'):
   w.ReadyWaitGate(raw,rule_sha256=c.sha(raw),read_ready=lambda *a:None,
     verify_rule=verifier(mode='REAL'),verify_ready=verifier(mode='REAL'))

class CapacityDelta(unittest.TestCase):
 def setUp(self):
  self.d=DownFixture();self.q=self.d.q;self.task=self.d.task('reader_bound');self.task['budget_seconds']=60
  self.bundle=bundle(self.q);self.now=OPEN-timedelta(minutes=29);self.mono=100.
  self.config=c.canonical({'fixture':'SYNTHETIC_NOT_CONFIGURATION'});configsha=c.sha(self.config)
  self.source_req=c.canonical({'fixture':'SYNTHETIC_SOURCE_REQUEST'});self.source_bound=c.canonical({'fixture':'SYNTHETIC_SOURCE_BOUND'})
  def linked(role,at,track,raw=None):return m.LinkedReceipt(raw or c.canonical({'fixture':'SYNTHETIC_NOT_RECEIPT'}),'b'*64,role,
       (c.EPOCH,c.DAY,c.PREVIOUS,track),'COMPLETE',at,self.source_req,self.source_bound)
  m3=linked('activate',self.now-timedelta(minutes=3),'BOOTSTRAP');j_at=self.now-timedelta(minutes=2)
  jraw=c.canonical({'schema':'R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1','status':'PUBLISHED_VERIFIED','mode':'PUBLISH',
   'code':None,'epoch':c.EPOCH,'session':c.DAY,'capacity_config_sha256':configsha,'massive_bars_enabled':True,'published_at':c.iso(j_at)})
  j=linked('admission_manifest',j_at,'P',jraw);act=linked('capacity_activate',self.now-timedelta(minutes=1),'P')
  self.proof=m.CapacityMondayProof('FIXTURE',m3,j,self.config,configsha,act)
  self.rule={'schema':'CAPACITY_MONDAY_RULE_CANDIDATE_V1','mode':'FIXTURE','epoch':c.EPOCH,'day':c.DAY,
   'authority_sha256':self.q['authority_sha256'],'selectors':{},'consumers':{},'verifiers':{n:vpin()for n in ('rule','original','config')}}
  for n,item in [('m3',m3),('j',j),('activation',act)]:
   self.rule['selectors'][n]={'source_sha256':item.source_sha256,'request_sha256':c.sha(item.request_raw),
    'bound_sha256':c.sha(item.bound_raw),'role':item.role,'context':list(item.context)}
  self.rule['consumers']={'CAPACITY_MONDAY':{**{k:self.rule['selectors']['activation'][k]for k in ('request_sha256','bound_sha256')},'authority_sha256':'9'*64},
   'DOWNSTREAM_AFTER_E6':{'request_sha256':c.sha(self.bundle.request),'bound_sha256':c.sha(self.bundle.bound),'authority_sha256':self.q['authority_sha256']}}
 def gate(self,verify=None):
  raw=c.canonical(self.rule);return m.CapacityMondayGate(raw,rule_sha256=c.sha(raw),read_proof=lambda *a:self.proof,
   verify_rule=verifier(),verify_original=verify or verifier(),verify_config=verifier())
 def call(self,g):
  with patch.object(m,'native_utc',lambda:self.now),patch.object(m.time,'monotonic',lambda:self.mono):
   return g(self.bundle,self.q,self.task,self.now-timedelta(seconds=10))
 def test_cross_bound_m3_j_and_activation_actual_read_with_rule_not_future_receipt_pin(self):
  self.assertIsNone(self.call(self.gate()))
  self.assertNotIn('receipt_sha256',str(self.rule))
 def test_downstream_capacity_never_activated_refuses_before_capture_effect(self):
  self.proof=replace(self.proof,activation=None)
  with self.assertRaisesRegex(c.Hold,'CAPACITY_NOT_ACTIVATED'):self.call(self.gate())
 def test_foreign_source_request_or_bound_is_not_same_dependency(self):
  self.proof=replace(self.proof,m3=replace(self.proof.m3,bound_raw=b'OTHER_SYNTHETIC_BOUND'))
  with self.assertRaisesRegex(c.Hold,'CAPACITY_MONDAY_SOURCE_OR_BOUND_CHANGED'):self.call(self.gate())
 def test_m3_must_be_complete_before_j(self):
  self.proof=replace(self.proof,m3=replace(self.proof.m3,completed_at=self.now))
  with self.assertRaisesRegex(c.Hold,'CAPACITY_MONDAY_M3_J_ORDER'):self.call(self.gate())
 def test_activation_before_j_cannot_be_after_j_proof(self):
  self.proof=replace(self.proof,activation=replace(self.proof.activation,completed_at=self.proof.m3.completed_at))
  with self.assertRaisesRegex(c.Hold,'CAPACITY_MONDAY_AFTER_J_REQUIRED'):self.call(self.gate())
 def test_worker_final_config_must_be_same_exact_j_original_hash(self):
  self.proof=replace(self.proof,config_raw=b'SYNTHETIC_OTHER_CONFIG')
  with self.assertRaisesRegex(c.Hold,'CAPACITY_MONDAY_CONFIG_PIN'):self.call(self.gate())
 def test_boolean_checkers_are_never_attestations(self):
  with self.assertRaisesRegex(c.Hold,'EXTERNAL_VERIFIER_BOOLEAN_IS_NOT_ATTESTATION'):
   self.call(self.gate(verifier(callback=lambda *a:True)))
 def test_distinct_rule_and_consumer_authorities_are_preserved(self):
  self.rule['authority_sha256']='8'*64
  self.assertNotEqual(self.rule['authority_sha256'],self.q['authority_sha256'])
  self.assertIsNone(self.call(self.gate()))
 def test_rule_authority_cannot_replace_other_consumer_authority(self):
  self.rule['consumers']['DOWNSTREAM_AFTER_E6']['authority_sha256']='8'*64
  with self.assertRaisesRegex(c.Hold,'CAPACITY_MONDAY_INVOCATION_UNBOUND'):self.call(self.gate())
 def test_native_clock_after_original_verifier_cannot_run_past_window(self):
  def late(*args):self.now=c.instant(self.task['not_after'])
  with self.assertRaisesRegex(c.Hold,'CAPACITY_MONDAY_DEADLINE'):self.call(self.gate(verifier(callback=late)))

class DecoderDelta(unittest.TestCase):
 def setUp(self):
  self.at=datetime(2026,10,12,14,1,2,tzinfo=timezone.utc);self.mono=100.
  self.req=c.canonical({'fixture':'SYNTHETIC_K9_REQUEST'});self.go=c.canonical({'fixture':'SYNTHETIC_K9_GO'})
  self.compiled={'EPOCH':c.EPOCH,'DAYS':[c.DAY],'PACKAGE':'b'*64,'REVISION':'c'*40,'OPS':{'capture_launch':['S','SOURCE','x']},
   'RECEIPT_KEYS':k.RECEIPT_KEYS,'PLAN_KEYS':k.PLAN_KEYS,'CONST_KEYS':k.CONST_KEYS,'LIMITS':{'fixture':1},'FLOOR':100,'DB':None}
  self.source='\n'.join(name+' = '+repr(value)for name,value in self.compiled.items()).encode()+b'\n'
  self.constants={'package_sha256':self.compiled['PACKAGE'],'code_revision':self.compiled['REVISION'],'act_b_sha256':'a'*64,
   'release_sha256':'a'*64,'policy_sha256':'a'*64,'runner_sha256':c.sha(self.source),'risk_source_pins_sha256':'a'*64,
   'risk_limits':self.compiled['LIMITS'],'disk_floor_bytes':100}
  key=c.sha(json.dumps([c.EPOCH,c.DAY,'S','capture_launch'],separators=(',',':'),ensure_ascii=True).encode())
  self.plan={'schema':'K9_STEP_PLAN_V1','epoch':c.EPOCH,'day':c.DAY,'k9_phase':'S','k9_operation':'capture_launch','slot':'SYNTHETIC',
   'attempt_key':key,'request_sha256':c.sha(self.req),'go_sha256':c.sha(self.go),'run_not_after':c.iso(self.at+timedelta(minutes=9)),
   'constants':self.constants,'network_class':'SOURCE','database':None,'risk':{},'step_row':{}}
  self.rawplan=c.canonical(self.plan)
  self.binding=k.Binding('capture_launch',self.rawplan,self.source,c.sha(self.source),'d'*64)
  self.inv=c.Invocation('capture_launch',(c.EPOCH,c.DAY,c.PREVIOUS,'P'),'e'*64,'f'*64,self.at+timedelta(minutes=10),120.,())
  self.rule={'schema':'K9_APPROVED_DECODER_RULE_CANDIDATE_V1','mode':'FIXTURE','epoch':c.EPOCH,'day':c.DAY,
   'runner_source_sha256':c.sha(self.source),'step_plan_sha256':c.sha(self.rawplan),'provenance_binding_sha256':'d'*64,
   'invocation_request_sha256':self.inv.request_sha256,'invocation_bound_sha256':self.inv.bound_sha256,
   'k9_request_sha256':c.sha(self.req),'k9_go_sha256':c.sha(self.go),
   'phase_not_before':'2026-10-12T13:52:00Z','phase_not_after':'2026-10-12T14:10:00Z','verifiers':{'approval':vpin(),'original':vpin()}}
  self.doc={'schema':'K9_STEP_RECEIPT_V1','status':'COMPLETE','code':None,'epoch':c.EPOCH,'day':c.DAY,'phase':'S',
   'operation':'capture_launch','attempt_key':key,'step_plan_sha256':c.sha(self.rawplan),'started_at':'2026-10-12T14:00:00Z',
   'completed_at':'2026-10-12T14:01:00Z','package_sha256':'b'*64,'build_sha':'c'*40,
   'outputs':{'source/snapshot.json':'a'*64,'source/tape/'+c.DAY+'.us-quote.ndjson':'a'*64},'aggregates':{},
   'counts':{'capture_complete':1,'consumer_failed':0}}
 def adapter(self,original=None):
  raw=c.canonical(self.rule);approval=k.Approval(raw,c.sha(raw),self.req,self.go)
  return k.K9ReceiptAdapter(self.binding,original or verifier(),approval=approval,verify_approval=verifier())
 def decode(self,adapter,**kwargs):
  with patch.object(k,'native_utc',lambda:self.at),patch.object(k.time,'monotonic',lambda:self.mono):
   return adapter.decode(c.canonical(self.doc),self.inv,**kwargs)
 def test_explicit_external_rule_and_four_original_pin_mapping_preserve_raw_receipt(self):
  receipt=self.decode(self.adapter());self.assertEqual(receipt.raw,c.canonical(self.doc))
 def test_two_edits_to_historical_runner_do_not_self_approve_source(self):
  source=self.source+b'UNAPPROVED_EDIT = 1\n';self.binding=replace(self.binding,runner_source_raw=source,runner_source_sha256=c.sha(source))
  with self.assertRaisesRegex(c.Hold,'K9_NOT_APPROVED_EXTERNAL_SOURCE'):self.adapter()
 def test_invocation_request_and_bound_must_match_independent_rule(self):
  self.inv=replace(self.inv,bound_sha256='0'*64)
  with self.assertRaisesRegex(c.Hold,'K9_INVOCATION_CONTEXT_CHANGED'):self.decode(self.adapter())
 def test_k9_original_go_mapping_cannot_be_caller_only(self):
  self.go=b'SYNTHETIC_WRONG_GO'
  with self.assertRaisesRegex(c.Hold,'K9_APPROVAL_ORIGINALS_CHANGED'):self.adapter()
 def test_supplied_clock_is_refused(self):
  with self.assertRaisesRegex(c.Hold,'K9_CLOCK_INJECTION_FORBIDDEN'):self.decode(self.adapter(),now=self.at)
 def test_native_now_cannot_decode_future_monday_receipt_on_sunday(self):
  self.at-=timedelta(days=1)
  with self.assertRaisesRegex(c.Hold,'K9_ORIGINAL_AFTER_DEADLINE'):self.decode(self.adapter())
 def test_monotonic_deadline_rechecked_after_provenance_callback(self):
  def late(*a):self.mono=121.
  with self.assertRaisesRegex(c.Hold,'K9_ORIGINAL_AFTER_DEADLINE'):self.decode(self.adapter(verifier(callback=late)))
 def test_ast_annassign_if_subscript_augassign_and_update_refuse(self):
  variants=("EPOCH: str = 'OTHER'", "if True:\n EPOCH = 'OTHER'", "OPS['x'] = []", "DAYS += ['OTHER']", "OPS.update({'x':[]})")
  for variant in variants:
   with self.subTest(variant=variant),self.assertRaises(c.Hold):k.compiled_literals(self.source+variant.encode()+b'\n')
 def test_original_outside_pinned_phase_window_is_not_relabelled(self):
  self.doc['started_at']='2026-10-12T13:51:59Z'
  with self.assertRaisesRegex(c.Hold,'K9_ORIGINAL_OUTSIDE_APPROVED_PHASE'):self.decode(self.adapter())
 def test_capture_complete_flag_before_actual_monday_close_cannot_be_complete(self):
  self.doc['completed_at']='2026-10-12T14:00:59Z'
  with self.assertRaisesRegex(c.Hold,'K9_CAPTURE_MONDAY_CLOSE_REQUIRED'):self.decode(self.adapter())
 def test_real_bare_checker_cannot_impersonate_loaded_approved_provenance(self):
  self.rule['mode']='REAL';raw=c.canonical(self.rule);approval=k.Approval(raw,c.sha(raw),self.req,self.go)
  with self.assertRaisesRegex(c.Hold,'REAL_VERIFIER_LOADED_MODULE_REQUIRED'):
   k.K9ReceiptAdapter(self.binding,verifier(mode='REAL'),approval=approval,verify_approval=verifier(mode='REAL'))

if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__)))
 p=Path(__file__).parent
 (p/'NEW_RESULT.json').write_bytes(c.canonical({'schema':'CODEX_C6_NEW_INTEGRATION_DELTA_RESULT_V1','new_methods':result.testsRun,
  'failures':len(result.failures),'errors':len(result.errors),'closed_methods_repeated':0,'mode':'SYNTHETIC_ONLY',
  'source':{n:c.sha((p/n).read_bytes())for n in ('ready_wait_gate.py','capacity_monday_gate.py','k9_receipt_adapter.py','verification_binding.py')},
  'operational_GO':False,'actual_producers_or_receipts':0,'linux_proof':'PENDING'})+b'\n')
 raise SystemExit(0 if result.wasSuccessful()else 1)
