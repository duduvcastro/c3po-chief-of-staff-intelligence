"""NEW result-contract delta only; closed 49/26/22 suites are not imported."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import fcntl,os,tempfile,time,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class ReservationResultDelta(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='new-result-contract-',dir=Path(__file__).parent)
  self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
  (self.root/'attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)),lock_budget_seconds=.03)
  self.fixture=Fixture(self.root);self.batch=c.FiniteBatch(self.fixture.bundle,self.ledger,self.fixture.services,clock=self.fixture.clock)
  self.outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=.5)
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def reserve(self):return self.batch.reserve('prove')
 def rows(self):return [c.strict(z) for z in (self.root/'attempts.ledger').read_bytes().splitlines()]
 def terminal(self,key,status='UNCERTAIN_CONSUMED',code='SYNTHETIC_ORIGINAL_UNCERTAIN'):
  result={'status':status,'code':code,'inner_code':None,'operation':'prove','attempt_key':key,
    'effect_calls':0,'original_receipt_sha256':None,'original_receipt_completed_at':None,
    'automatic_retry':False,'operational_GO_granted':False,'physical_host_certified':False,'completed_at':c.iso(o.now())}
  self.ledger.finish(key,result);return self.rows()[-1]
 def second(self,status='REFUSED_CONSUMED',recovery=False):
  before=(self.root/'attempts.ledger').read_bytes()
  with patch.object(o.os,'fork',side_effect=AssertionError('fork on second reservation')):
   result=self.outer.run(self.batch,'prove')
  self.assertEqual(result['status'],status,result);self.assertEqual(result['effect_calls'],0)
  self.assertIs(result['recovery_required'],recovery);self.assertIs(result['automatic_retry'],False)
  self.assertFalse((self.root/'effects.synthetic').exists())
  if status=='REFUSED_CONSUMED':self.assertEqual((self.root/'attempts.ledger').read_bytes(),before)
  return result
 def test_new_exact_uncertain_terminal_is_closed_without_ledger_recovery(self):
  key=self.reserve();terminal=self.terminal(key);r=self.second()
  self.assertTrue(r['reservation_durable']);self.assertEqual(r['consumption_state'],'TERMINAL_DURABLE')
  self.assertEqual(r['previous_terminal_status'],'UNCERTAIN_CONSUMED');self.assertEqual(r['previous_terminal_sha256'],c.sha(c.canonical(terminal)))
 def test_new_refused_terminal_is_closed_and_no_callback_repeated(self):
  self.terminal(self.reserve(),'REFUSED_CONSUMED','REAL_AUTHORITY_ADAPTER_UNAVAILABLE');self.second()
 def test_new_complete_terminal_remains_original_without_second_effect(self):
  terminal=self.terminal(self.reserve(),'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',None);r=self.second()
  self.assertEqual(r['previous_terminal_status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE');self.assertEqual(r['previous_terminal_sha256'],c.sha(c.canonical(terminal)))
 def test_new_pending_claim_is_uncertain_and_never_retried(self):
  self.reserve();r=self.second('UNCERTAIN_CONSUMED',True)
  self.assertTrue(r['reservation_durable']);self.assertEqual(r['consumption_state'],'UNRESOLVED_CONSUMED');self.assertIsNone(r['previous_terminal_status'])
 def test_new_orphan_marker_adopts_uncertain_result_not_complete(self):
  key=self.reserve()
  (self.root/('reserved-'+key)).unlink();(self.root/'attempts.ledger').write_bytes(b'')
  r=self.second('UNCERTAIN_CONSUMED',True);self.assertEqual(r['previous_terminal_status'],'UNCERTAIN_CONSUMED')
  self.assertEqual(self.rows()[-1]['data']['code'],'ORPHAN_MARKER')
 def test_new_lost_commit_of_uncertain_terminal_stays_recovered_uncertain(self):
  key=self.reserve();self.terminal(key);(self.root/('terminal-'+key)).unlink()
  r=self.second('UNCERTAIN_CONSUMED',True);self.assertEqual(r['previous_terminal_status'],'UNCERTAIN_CONSUMED')
  proof=c.strict((self.root/('terminal-'+key)).read_bytes());self.assertIs(proof['recovered'],True)
  self.second('UNCERTAIN_CONSUMED',True)
 def test_new_torn_same_key_history_preserves_consumed_unknown(self):
  self.reserve()
  with (self.root/'attempts.ledger').open('ab') as f:f.write(b'{"torn":')
  r=self.second('UNCERTAIN_CONSUMED',True);self.assertEqual(r['code'],'LEDGER_PARTIAL_OR_FULL');self.assertFalse(r['reservation_durable'])
 def test_new_busy_lock_returns_not_reserved_but_no_retry_permission(self):
  fd=os.open(self.root/'attempts.ledger',os.O_RDWR)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);r=self.second('REFUSED_NOT_RESERVED',False)
   self.assertEqual(r['code'],'LEDGER_LOCK_DEADLINE_NO_RESERVATION');self.assertEqual(self.rows(),[])
  finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
 def test_new_legacy_v1_terminal_proof_is_explicitly_read_only_compatible(self):
  key=self.reserve();terminal=self.terminal(key);proofpath=self.root/('terminal-'+key)
  proof=c.strict(proofpath.read_bytes());proof.pop('recovered');proof['schema']='L12_TERMINAL_COMMIT_CANDIDATE_V1';proofpath.write_bytes(c.canonical(proof))
  r=self.second();self.assertEqual(r['previous_terminal_sha256'],c.sha(c.canonical(terminal)))
 def test_new_direct_run_uses_same_reservation_result_contract(self):
  self.terminal(self.reserve(),'REFUSED_CONSUMED','OUTER_LIMITER_REQUIRED');r=self.batch.run('prove')
  self.assertEqual(r['status'],'REFUSED_CONSUMED');self.assertFalse(r['recovery_required']);self.assertTrue(r['reservation_durable']);self.assertEqual(r['effect_calls'],0)
 def test_new_outer_worker_failure_commits_then_second_is_final_refusal(self):
  with patch.object(self.outer,'_worker',side_effect=lambda *a:os._exit(4)):
   first=self.outer.run(self.batch,'prove')
  self.assertEqual(first['status'],'UNCERTAIN_CONSUMED');r=self.second();self.assertEqual(r['previous_terminal_status'],'UNCERTAIN_CONSUMED')
 def test_new_outer_source_failure_commits_then_second_has_no_fork(self):
  self.outer.core_sha256='f'*64;first=self.outer.run(self.batch,'prove')
  self.assertEqual(first['code'],'OUTER_SOURCE_PIN_CHANGED');self.second()

if __name__=='__main__':unittest.main(verbosity=2)
