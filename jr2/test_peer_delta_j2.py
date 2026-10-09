"""NEW peer-defect delta only; J R1's twenty methods not rediscovered or repeated."""
import base64
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import sys,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import fixture_builder_j1 as fixture
import j_slot as j
import veto_emitter as v

class PeerDelta(unittest.TestCase):
 def setUp(self):
  self.f=fixture.JFixtures('runTest');self.f.setUp();self.mode='normal';self.receipt=None;self.returned=False
  self.f.image.module.execute=self.execute
 def tearDown(self):self.f.tearDown()
 def execute(self,build,**kwargs):
  ctx=build();self.receipt={'schema':'R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1','session':'2026-10-12','mode':'PUBLISH','status':'REFUSED','code':None}
  if self.mode=='early':
   self.receipt.update(epoch=j.config.EPOCH,status='ALREADY_PUBLISHED_VERIFIED',capacity_config_sha256=self.f.settings.r2d2_v2_capacity_config_sha,binding_sha256='a'*64,manifest_sha256='b'*64)
   return self.receipt,0
  kwargs.pop('prepare_first');code=self.f.writer(ctx,self.receipt,**kwargs)
  observed=self.f.f.now;until=observed+timedelta(seconds=10)
  self.receipt.update(go_mode='INDIVIDUAL',go_sha256='c'*64,template_sha256='d'*64,view={'observed_at':observed.isoformat(),'valid_until':until.isoformat()},window={'not_before':'2026-10-12T12:59:00Z','not_after':'2026-10-12T13:01:00Z'},published_at=observed.isoformat(),file={'uid':0,'mode':'0600','nlink':1},symbol_count=550)
  if self.mode=='full_already':self.receipt['status']='ALREADY_PUBLISHED_VERIFIED'
  if self.mode=='missing_go':self.receipt.pop('go_sha256')
  if self.mode=='changed_view':self.receipt['view']['observed_at']='2026-10-12T13:00:00Z'
  self.returned=True
  return self.receipt,code
 def test_early_already_not_complete_and_original_preserved(self):
  self.mode='early';out=self.f.run_slot();self.assertEqual((out.status,out.code),('UNCERTAIN','J_MANIFEST_UNVERIFIED'))
  self.assertNotIn('prepare',self.f.events);self.assertEqual(json.loads(out.writer_receipt_raw)['status'],'ALREADY_PUBLISHED_VERIFIED')
  self.assertEqual(out.writer_receipt_sha256,v.digest(out.writer_receipt_raw));self.assertEqual(out.writer_exit_code,0)
 def test_full_already_still_refuses_under_narrow_gate(self):
  self.mode='full_already';out=self.f.run_slot();self.assertEqual(out.status,'UNCERTAIN');self.assertEqual(out.code,'J_MANIFEST_UNVERIFIED')
  self.assertIn('view',json.loads(out.writer_receipt_raw))
 def test_malformed_rule_consumes_shared_family_before_parse(self):
  raw=b'NOT-JSON\n';one=self.f.run_slot(rule_raw=raw,rule_sha256=v.digest(raw));self.assertEqual(one.code,'J_RULE_INVALID')
  two=self.f.run_slot();self.assertEqual(two.code,'ATTEMPT_ALREADY_CONSUMED');self.assertEqual(self.f.events,[])
 def test_wrong_rule_hash_consumes_before_hash_check(self):
  one=self.f.run_slot(rule_sha256='f'*64);self.assertEqual(one.code,'J_RULE_HASH')
  self.assertEqual(self.f.run_slot().code,'ATTEMPT_ALREADY_CONSUMED');self.assertEqual(self.f.events,[])
 def test_normal_complete_preserves_full_writer_bytes_and_private_ledger(self):
  out=self.f.run_slot();self.assertEqual(out.status,'COMPLETE');self.assertEqual(out.mode,'FIXTURE');raw=j.writer_bytes(self.receipt);self.assertEqual(out.writer_receipt_raw,raw)
  doc=json.loads(raw);self.assertEqual(doc['go_mode'],'INDIVIDUAL');self.assertEqual(doc['binding_sha256'],'a'*64);self.assertIn('view',doc);self.assertIn('window',doc);self.assertFalse(out.operational_GO)
  private=j.private_result(out);self.assertNotIn('writer_receipt_raw',private);self.assertEqual(base64.b64decode(private['writer_receipt_base64']),raw)
  ledger=(self.f.root/'ledger'/'attempts.ledger').read_bytes();last=json.loads(ledger.splitlines()[-1]);self.assertEqual(base64.b64decode(last['data']['writer_receipt_base64']),raw)
 def test_missing_go_field_refuses_with_complete_original_saved(self):
  self.mode='missing_go';out=self.f.run_slot();self.assertEqual(out.code,'J_WRITER_GO_UNVERIFIED');self.assertIsNotNone(out.writer_receipt_raw)
  self.assertEqual(json.loads(out.writer_receipt_raw)['status'],'PUBLISHED_VERIFIED')
 def test_wrong_actual_observation_field_refuses(self):
  self.mode='changed_view';out=self.f.run_slot();self.assertEqual(out.code,'J_WRITER_VIEW_UNVERIFIED');self.assertEqual(out.status,'UNCERTAIN')
 def test_receipt_mutation_after_return_refuses_without_mutating_original_snapshot(self):
  def mutate(*a):
   self.f.events.append('slot-auth')
   if self.returned:self.receipt['unknown_after_return']='MUTATION'
  self.f.sa=replace(self.f.sa,verify_current=mutate)
  out=self.f.run_slot();self.assertEqual(out.code,'J_WRITER_RECEIPT_CHANGED');self.assertNotIn('unknown_after_return',json.loads(out.writer_receipt_raw))

if __name__=='__main__':unittest.main()
