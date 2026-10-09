"""New R5/J3 reservation and explicit protocol-boundary fixtures only."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest
import fixture_support_j3 as support
import j_slot as j
import veto_emitter as v

class ReservationDelta(unittest.TestCase):
 def setUp(self):
  self.helper=support.PeerDelta('runTest');self.helper.setUp();self.f=self.helper.f
  self.scope=(j.config.EPOCH,j.config.FIRST,'L12_JSLOT_1')
  self.req='c'*64;self.bound='d'*64
  self.key=self.f.ledger.claim(self.scope,self.req,self.bound,None,worker_nonce_sha256=v.digest(b'PRIVATE-WORKER-CAPABILITY'))
  self.outer=j.OuterReservation(self.scope,self.req,self.bound,self.key)
 def tearDown(self):self.helper.tearDown()
 def run(self,result=None):
  if result is not None:return super().run(result)
  return self.f.run_slot(outer_reservation=self.outer)
 def test_historical_fixture_completes_by_read_only_observation_without_dispatch(self):
  seen=[];original=self.f.ledger.observe_reservation
  def observed(*a):
   seen.append(a);return original(*a)
  self.f.ledger.observe_reservation=observed
  def forbidden(*a,**kw):raise AssertionError('J must not consume core worker dispatch')
  self.f.ledger.check_reserved=forbidden
  proof=self.f.root/'ledger'/('reserved-'+self.key);raw=proof.read_bytes()
  out=self.run()
  self.assertEqual(out.status,'COMPLETE');self.assertGreater(len(seen),20)
  self.assertEqual(proof.read_bytes(),raw);self.assertFalse(any(x.name.startswith('dispatch-')for x in proof.parent.iterdir()))
  self.assertFalse(out.operational_GO);self.assertNotEqual(out.attempt_key,self.key)
  self.assertIn('view',json.loads(out.writer_receipt_raw))
 def test_external_wrong_pin_refuses_and_shared_family_is_consumed(self):
  self.outer=replace(self.outer,request_sha256='e'*64)
  first=self.run();self.assertEqual(first.code,'RESERVATION_PIN_CHANGED');self.assertEqual(self.f.events,[])
  self.assertEqual(self.run().code,'ATTEMPT_ALREADY_CONSUMED')
 def test_boolean_reservation_observation_is_not_a_permit(self):
  self.f.ledger.observe_reservation=lambda *a:True
  out=self.run();self.assertEqual(out.code,'J_RESERVATION_OBSERVATION_RESULT');self.assertEqual(self.f.events,[])
  self.assertFalse(out.operational_GO)
 def test_outer_closed_inside_authority_callback_blocks_before_observation(self):
  def closed(*a):
   self.f.events.append('authority-fixture')
   self.f.ledger.finish(self.key,{'status':'REFUSED','code':'SYNTHETIC_OUTER_CLOSED'})
  self.f.sa=replace(self.f.sa,verify_current=closed)
  out=self.run();self.assertEqual(out.code,'RESERVATION_NOT_PENDING')
  self.assertEqual(self.f.events,['authority-fixture']);self.assertEqual(list((self.f.root/'docs').iterdir()),[])
 def test_outer_closed_during_context_blocks_prepare_after_staging(self):
  context=self.f.image.module.context
  def closed(*a,**kw):
   value=context(*a,**kw);self.f.ledger.finish(self.key,{'status':'REFUSED','code':'SYNTHETIC_OUTER_CLOSED'})
   return value
  self.f.image.module.context=closed
  out=self.run();self.assertEqual((out.status,out.code),('UNCERTAIN','RESERVATION_NOT_PENDING'))
  self.assertNotIn('prepare',self.f.events);self.assertIsNone(out.writer_receipt_raw)
  self.assertTrue((self.f.root/'docs'/'veto.md').exists())
 def test_real_with_valid_outer_and_mutable_callbacks_is_explicit_hold(self):
  self.f.rule['mode']='REAL'
  self.f.sa=replace(self.f.sa,mode='REAL',verify_current=lambda *a:None)
  self.f.clock=lambda:self.f.f.now
  out=self.run();self.assertEqual(out.code,'J_REAL_PROCESS_AUTHORITY_UNAVAILABLE');self.assertEqual(self.f.events,[])
  self.assertEqual(self.run().code,'ATTEMPT_ALREADY_CONSUMED')
  self.assertFalse(any(x.name.startswith('dispatch-')for x in (self.f.root/'ledger').iterdir()))
 def test_isolated_five_second_candidate_cannot_replace_historical_rule(self):
  self.f.rule['veto_protocol']=j.PROCESS_PROTOCOL
  out=self.run();self.assertEqual(out.code,'J_PROCESS_PROTOCOL_NOT_OPERATIONAL');self.assertEqual(self.f.events,[])
  self.assertEqual(self.run().code,'ATTEMPT_ALREADY_CONSUMED')
 def test_missing_protocol_is_not_implicitly_chosen(self):
  self.f.rule.pop('veto_protocol')
  out=self.run();self.assertEqual(out.code,'J_RULE_FIELDS');self.assertEqual(self.f.events,[])
 def test_wrong_candidate_program_pin_cannot_run_fixture_as_real(self):
  self.f.rule['process_candidate_pins']['veto_emitter.py']='f'*64
  out=self.run();self.assertEqual(out.code,'J_PROCESS_CANDIDATE_PINS');self.assertEqual(self.f.events,[])
 def test_core_and_process_namespaces_are_exact_and_distinct(self):
  self.assertEqual(j.module_pin('finite_batch'),j.CORE_SHA)
  j.check_candidate_protocol(dict(j.PROCESS_PINS))
  self.assertNotEqual(j.PROCESS_PINS['finite_batch.py'],j.CORE_SHA)
  self.assertNotEqual(j.PROCESS_PINS['veto_emitter.py'],j.module_pin('veto_emitter'))

if __name__=='__main__':unittest.main()
