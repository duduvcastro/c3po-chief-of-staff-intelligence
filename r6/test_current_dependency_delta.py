"""NEW final-byte dependency coherence and nonce-supervisor smoke."""
from pathlib import Path
import ast,hashlib,inspect,unittest
import finite_batch as c
import outer_limiter as o
import image_path_adapter as a
import image_capacity_gate as g

class FinalDependency(unittest.TestCase):
 def test_new_r5b_gate_dependency_is_exact_and_phase_task_api_unchanged(self):
  pins={'image_path_adapter.py':'78282c7e932f8082f7108eb5d22413c7580a4393ea9e3171f465d5b48ba35096','image_capacity_gate.py':'58a6104e8d1efcab2199d388ffe17e602abf315304449dd1be5178f57f7c12ec'}
  for name,digest in pins.items():self.assertEqual(hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest(),digest)
  self.assertEqual(tuple(inspect.signature(g.ImageCapacityGate.__call__).parameters),('self','plan','phase','now','task'))
  self.assertEqual(set(('deadline_utc','deadline_monotonic','original_receipts'))&set(c.Invocation.__dataclass_fields__),{'deadline_utc','deadline_monotonic','original_receipts'})
  self.assertIs(g.Hold,c.Hold);self.assertIs(g.accepted,c.accepted);self.assertIs(g.image,a);self.assertIs(o.c,c)
 def test_new_no_public_reserved_dispatch_path_remains_in_supervisor(self):
  source=Path(o.__file__).read_text();tree=ast.parse(source)
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
  self.assertFalse(any(n.func.attr=='run_reserved' for n in calls));self.assertTrue(any(n.func.attr=='_run_reserved' for n in calls))
  self.assertIn('worker_nonce_sha256=c.sha(nonce)',source);self.assertIn('os.close(lifeline_write)',source)

 def test_new_r5b_bridge_refuses_operational_injected_clock_before_callbacks(self):
  calls=[]
  with self.assertRaisesRegex(c.Hold,'IMAGE_CLOCK_INJECTION_FORBIDDEN'):
   g.ImageCapacityGate(None,lambda *args:calls.append('read'),lambda *args:calls.append('verify'),
                       journal_directory='/synthetic-not-a-real-root',clock=lambda:None)
  self.assertEqual(calls,[])

 def test_new_crosslane_ready_and_decoder_share_current_core_and_external_verifier(self):
  import capacity_monday_gate as m,ready_wait_gate as w,k9_receipt_adapter as k,verification_binding as v
  pins={'capacity_monday_gate.py':'ebe04ca62c8b75ba0b2ed3444a14503e9f44c4b6937de3cf544d55f76142fc53',
        'ready_wait_gate.py':'5bbef9a6db2e9e714bcee3cc72ee1836e66bb303a3a67c5ff3aea8274c93262b',
        'verification_binding.py':'78f4309d9713ea1c718d5635e5eed0dc71335c9b7cb7c82149185e868fc23c86',
        'k9_receipt_adapter.py':'ed89a0718b40dadc154af5d2eb268815dcd580de8e3daa8457e1ac662d977509'}
  for name,digest in pins.items():self.assertEqual(hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest(),digest)
  for module in (m,w,k,v):self.assertIs(module.c,c)
  for module in (m,w,k):self.assertIs(module.Verifier,v.Verifier)
  for gate in (m.CapacityMondayGate,w.ReadyWaitGate):
   self.assertEqual(tuple(inspect.signature(gate.__call__).parameters),('self','bundle','q','task','now'))
  self.assertIn('CAPACITY_MONDAY',c.LANES);self.assertEqual(c.LANES['CAPACITY_MONDAY'],('capacity_activate',))
  self.assertIn('ready_wait',c.Services.__dataclass_fields__);self.assertIn('capacity_dependencies',c.Services.__dataclass_fields__)

if __name__=='__main__':unittest.main(verbosity=2)
