"""NEW final-parent terminal failure classification; one synthetic effect only."""
from pathlib import Path
from unittest.mock import patch
import os,tempfile,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class TerminalRecoveryDelta(unittest.TestCase):
 def test_new_finish_failure_retains_claim_effect_once_and_requires_recovery(self):
  with tempfile.TemporaryDirectory(prefix='new-terminal-recovery-',dir=Path(__file__).parent) as directory:
   root=Path(directory);os.chmod(root,0o700)
   (root/'attempts.ledger').write_bytes(b'');os.chmod(root/'attempts.ledger',0o600)
   ledger=c.DurableLedger(str(root),c.measure_local_ledger(str(root)),lock_budget_seconds=.04,finish_budget_seconds=1)
   try:
    x=Fixture(root);batch=c.FiniteBatch(x.bundle,ledger,x.services,clock=x.clock)
    outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=.8)
    with patch.object(ledger,'finish',side_effect=c.Hold('SYNTHETIC_FINISH_FAILURE')):
     first=outer.run(batch,'prove')
    self.assertEqual(first['status'],'UNCERTAIN_CONSUMED',first)
    self.assertEqual(first['code'],'TERMINAL_LEDGER_UNCERTAIN',first)
    self.assertTrue(first['recovery_required']);self.assertTrue(first['reservation_durable'])
    self.assertFalse(first['automatic_retry'])
    self.assertEqual(first['inner_result']['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE')
    self.assertEqual((root/'effects.synthetic').read_bytes(),b'1')
    self.assertFalse((root/('terminal-'+first['attempt_key'])).exists())
    rows=[c.strict(line) for line in (root/'attempts.ledger').read_bytes().splitlines()]
    self.assertEqual([row['kind'] for row in rows],['CLAIM'])
    second=outer.run(batch,'prove')
    self.assertEqual(second['status'],'UNCERTAIN_CONSUMED',second)
    self.assertTrue(second['recovery_required']);self.assertFalse(second['automatic_retry'])
    self.assertEqual((root/'effects.synthetic').read_bytes(),b'1')
   finally:ledger.close()

if __name__=='__main__':unittest.main(verbosity=2)
