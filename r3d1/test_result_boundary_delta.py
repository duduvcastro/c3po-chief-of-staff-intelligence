"""NEW R3d1 ambiguous legacy proof and busy consumed boundary fixtures only."""
from pathlib import Path
from unittest.mock import patch
import fcntl,os,tempfile,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class BoundaryDelta(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='new-contract-boundary-',dir=Path(__file__).parent);self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
  (self.root/'attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)),lock_budget_seconds=.03)
  self.x=Fixture(self.root);self.batch=c.FiniteBatch(self.x.bundle,self.ledger,self.x.services,clock=self.x.clock)
  self.outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=.5)
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def claim(self):return self.batch.reserve('prove')
 def terminal(self,key,status):
  self.ledger.finish(key,{'status':status,'code':None,'operation':'prove','attempt_key':key,'effect_calls':0,'automatic_retry':False})
 def legacy(self,key):
  path=self.root/('terminal-'+key);proof=c.strict(path.read_bytes());proof.pop('recovered');proof['schema']='L12_TERMINAL_COMMIT_CANDIDATE_V1';path.write_bytes(c.canonical(proof))
 def second(self,expected,recovery):
  before=(self.root/'attempts.ledger').read_bytes()
  with patch.object(o.os,'fork',side_effect=AssertionError('second invocation fork')):r=self.outer.run(self.batch,'prove')
  self.assertEqual(r['status'],expected,r);self.assertIs(r['recovery_required'],recovery);self.assertEqual(r['effect_calls'],0);self.assertIs(r['automatic_retry'],False)
  self.assertEqual((self.root/'attempts.ledger').read_bytes(),before);self.assertFalse((self.root/'effects.synthetic').exists());return r
 def test_new_v1_uncertain_proof_cannot_claim_closed_ledger_history(self):
  key=self.claim();self.terminal(key,'UNCERTAIN_CONSUMED');self.legacy(key);r=self.second('UNCERTAIN_CONSUMED',True)
  self.assertEqual(r['consumption_state'],'UNRESOLVED_CONSUMED');self.assertEqual(r['previous_terminal_status'],'UNCERTAIN_CONSUMED')
 def test_new_v1_nonuncertain_exact_terminal_is_read_only_closed(self):
  key=self.claim();self.terminal(key,'REFUSED_CONSUMED');self.legacy(key);r=self.second('REFUSED_CONSUMED',False)
  self.assertTrue(r['reservation_durable']);self.assertEqual(r['previous_terminal_status'],'REFUSED_CONSUMED')
 def test_new_busy_existing_pending_marker_requires_recovery_without_proof_read(self):
  self.claim();fd=os.open(self.root/'attempts.ledger',os.O_RDWR)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);r=self.second('UNCERTAIN_CONSUMED',True)
   self.assertEqual(r['code'],'LEDGER_LOCK_DEADLINE_NO_RESERVATION');self.assertFalse(r['reservation_durable']);self.assertIsNone(r['previous_terminal_status'])
  finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
 def test_new_busy_existing_terminal_does_not_infer_closed_without_lock(self):
  key=self.claim();self.terminal(key,'REFUSED_CONSUMED');fd=os.open(self.root/'attempts.ledger',os.O_RDWR)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);r=self.second('UNCERTAIN_CONSUMED',True)
   self.assertFalse(r['reservation_durable']);self.assertIsNone(r['previous_terminal_status'])
  finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
  self.second('REFUSED_CONSUMED',False)

if __name__=='__main__':unittest.main(verbosity=2)
