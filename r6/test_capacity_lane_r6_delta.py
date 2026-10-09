"""NEW core lane/callback chronology fixtures. All documents/receipts SYNTHETIC.
Native clock monkeypatch is TEST ONLY; it is never an operational clock adapter.
"""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import os,tempfile,time,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class LaneFixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='new-r6-lane-',dir=Path(__file__).parent)
  self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
  (self.root/'attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)),lock_budget_seconds=.04,finish_budget_seconds=1)
  self.x=Fixture(self.root);self.base=datetime(2026,10,12,4,1,tzinfo=timezone.utc);self.mark=time.monotonic()
  self.x.base=self.base;self.x.mark=self.mark
  self.outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=.8)
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def clock(self):return self.base+timedelta(seconds=time.monotonic()-self.mark)
 def bundle(self,lane,ops,initial=None):
  prepared=datetime(2026,10,11,20,tzinfo=timezone.utc)
  authority=c.canonical({'fixture':'SYNTHETIC_NOT_AUTHORITY'});runtime=c.canonical({'fixture':'SYNTHETIC_NOT_RUNTIME'})
  q={'schema':'L12_FINITE_BATCH_REQUEST_CANDIDATE_V1','lane':lane,'epoch':c.EPOCH,'session':c.DAY,'previous_session':c.PREVIOUS,'track':'P',
     'prepared_at':c.iso(prepared),'owner_deadline':'2026-10-12T00:45:00Z','authority_sha256':c.sha(authority),'runtime_sha256':c.sha(runtime),
     'veto_authority_sha256':c.sha(b'SYNTHETIC_VETO'),'initial_receipts':initial or {},
     'tasks':[{'operation':op,'not_before':c.iso(self.base-timedelta(seconds=1)),'not_after':c.iso(self.base+timedelta(seconds=60)),
               'budget_seconds':.7,'requires':list(c.MINIMUM_DEPENDENCIES[op])} for op in ops]}
  raw=c.canonical(q)
  owner=c.canonical({'schema':'L12_OWNER_RECORD_CANDIDATE_V1','answer':'Assino','channel':'REGISTRO_PELA_FABLE',
       'request_sha256':c.sha(raw),'question_sha256':c.sha(b'SYNTHETIC_QUESTION'),'question_published_at':c.iso(prepared+timedelta(seconds=1)),
       'signed_at':c.iso(prepared+timedelta(seconds=2))})
  docs=(('authority',authority),('owner',owner),('runtime',runtime))
  bound=c.canonical({'schema':'L12_BOUND_CANDIDATE_V1','request_sha256':c.sha(raw),'documents_sha256':{k:c.sha(v) for k,v in docs},'bound_at':c.iso(prepared+timedelta(seconds=3))})
  return c.Bundle(raw,bound,docs)
 def invoke(self,batch,op):
  with patch.object(c,'native_utc_now',self.clock),patch.object(o,'now',self.clock):return self.outer.run(batch,op)
 def effects(self):return (self.root/'effects.synthetic').read_bytes() if (self.root/'effects.synthetic').exists() else b''

class CapacityLaneDelta(LaneFixture):
 def test_new_capacity_monday_lane_allows_only_actual_cross_bound_gate_not_initial_future_hash(self):
  bundle=self.bundle('CAPACITY_MONDAY',c.CAPACITY);q=c.validate_plan(bundle.request)
  m3_bound,j_bound=c.sha(b'SYNTHETIC_M3_OTHER_BOUND'),c.sha(b'SYNTHETIC_J_OTHER_BOUND')
  def proof(actual_bundle,actual_q,task,now):
   c.need(actual_bundle==bundle and actual_q==q,'SYNTHETIC_BUNDLE_UNBOUND')
   c.need(m3_bound!=c.sha(bundle.bound) and j_bound!=c.sha(bundle.bound),'SYNTHETIC_CROSS_BOUND_NOT_DISTINCT')
   c.need(task['operation']=='capacity_activate' and q['initial_receipts']=={},'SYNTHETIC_DYNAMIC_ORIGINALS_UNBOUND')
   with (self.root/'proof-calls').open('ab') as fd:fd.write(b'1')
  services=replace(self.x.services,capacity_dependencies=proof)
  batch=c.FiniteBatch(bundle,self.ledger,services);out=self.invoke(batch,'capacity_activate')
  self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
  self.assertEqual((self.root/'proof-calls').read_bytes(),b'11');self.assertEqual(self.effects(),b'1')
  changed=dict(q);changed['initial_receipts']={'activate':c.sha(b'FUTURE_SHA')}
  with self.assertRaisesRegex(c.Hold,'CAPACITY_DYNAMIC_ORIGINALS_REQUIRED'):c.validate_plan(c.canonical(changed))
 def test_new_capacity_monday_missing_actual_proof_callback_refuses_without_effect(self):
  batch=c.FiniteBatch(self.bundle('CAPACITY_MONDAY',c.CAPACITY),self.ledger,self.x.services)
  out=self.invoke(batch,'capacity_activate');self.assertEqual(out['inner_result']['code'],'REAL_ADAPTER_UNAVAILABLE',out)
  self.assertEqual(out['effect_calls'],0);self.assertEqual(self.effects(),b'')
 def test_new_capacity_cross_proof_future_cannot_reach_effect(self):
  def proof(bundle,q,task,now):c.need(now+timedelta(seconds=1)<=now,'CAPACITY_ORIGINAL_FUTURE')
  batch=c.FiniteBatch(self.bundle('CAPACITY_MONDAY',c.CAPACITY),self.ledger,replace(self.x.services,capacity_dependencies=proof))
  out=self.invoke(batch,'capacity_activate');self.assertEqual(out['inner_result']['code'],'CAPACITY_ORIGINAL_FUTURE',out)
  self.assertEqual(self.effects(),b'')
 def test_new_capacity_cross_proof_wrong_context_cannot_reach_effect(self):
  def proof(bundle,q,task,now):c.need((c.EPOCH,'2026-10-13','P')==(c.EPOCH,c.DAY,'P'),'CAPACITY_ORIGINAL_CONTEXT')
  batch=c.FiniteBatch(self.bundle('CAPACITY_MONDAY',c.CAPACITY),self.ledger,replace(self.x.services,capacity_dependencies=proof))
  out=self.invoke(batch,'capacity_activate');self.assertEqual(out['inner_result']['code'],'CAPACITY_ORIGINAL_CONTEXT',out)
  self.assertEqual(self.effects(),b'')

class ReadySequenceDelta(LaneFixture):
 def downstream(self,ready_callback):
  initial={}
  for role in ('commit_result','publish_launch'):
   receipt=self.x.receipt(role,datetime(2026,10,11,19,tzinfo=timezone.utc));self.x.receipts[role]=receipt;initial[role]=c.sha(receipt.raw)
  bundle=self.bundle('DOWNSTREAM_AFTER_E6',c.DOWNSTREAM,initial)
  def event(text):
   with (self.root/'sequence').open('a') as fd:fd.write(text+'\n')
  def read(role,ctx):
   event('receipt:'+role)
   if role in initial:return self.x.receipts[role]
   p=self.root/(role+'.receipt')
   if not p.exists():return None
   raw=p.read_bytes();row=c.strict(raw);return c.Receipt(raw,role,ctx,'COMPLETE',c.instant(row['at']))
  def execute(call):
   event('effect:'+call.operation);receipt=self.x.receipt(call.operation,self.clock())
   (self.root/(call.operation+'.receipt')).write_bytes(receipt.raw)
   return receipt
  def veto(q,t,n):event('veto:'+t['operation']);return self.x.veto(q,t,n)
  def ready(*args):event('ready_wait');time.sleep(.01)
  services=replace(self.x.services,receipt_read=read,execute=execute,veto_read=veto,
                   capacity_dependencies=lambda *a:None,capacity_path=lambda *a:None,ready_wait=ready if ready_callback else None)
  return c.FiniteBatch(bundle,self.ledger,services)
 def test_new_ready_wait_occurs_under_same_claim_before_fresh_dependencies_and_veto(self):
  batch=self.downstream(True)
  for op in ('e6','admission_manifest','post','reader_bound','reader_cycle'):
   out=self.invoke(batch,op);self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
  sequence=(self.root/'sequence').read_text().splitlines();at=sequence.index('ready_wait');veto=sequence.index('veto:reader_cycle')
  self.assertLess(at,veto);self.assertTrue(any(s.startswith('receipt:') for s in sequence[at+1:veto]))
  self.assertLess(veto,sequence.index('effect:reader_cycle'));self.assertEqual(sequence.count('ready_wait'),1)
 def test_new_missing_ready_wait_callback_prevents_first_session_effect(self):
  batch=self.downstream(False)
  for op in ('e6','admission_manifest','post','reader_bound'):
   out=self.invoke(batch,op);self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
  out=self.invoke(batch,'reader_cycle');self.assertEqual(out['effect_calls'],0,out)
  self.assertEqual(out['inner_result']['code'],'REAL_ADAPTER_UNAVAILABLE',out)
  self.assertNotIn('effect:reader_cycle',(self.root/'sequence').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
