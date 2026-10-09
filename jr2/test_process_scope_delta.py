"""NEW local process flags/ledger boundary vectors, no app import or worker write."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import test_peer_delta_j2 as peer
import j_slot as j
import veto_emitter as v

class ProcessScopeDelta(unittest.TestCase):
 def setUp(self):
  self.fixture=peer.PeerDelta('runTest');self.fixture.setUp();self.f=self.fixture.f
 def tearDown(self):self.fixture.tearDown()
 def test_local_flags_preserve_inactive_worker_settings(self):
  base=SimpleNamespace(r2d2_v2_shadow_enabled=False,r2d2_v2_capacity_required=False,database_url='')
  out=self.f.run_slot(base_settings=base)
  self.assertEqual(out.status,'COMPLETE');self.assertIs(self.f.settings.r2d2_v2_shadow_enabled,True)
  self.assertIs(self.f.settings.r2d2_v2_capacity_required,True)
  self.assertIs(base.r2d2_v2_shadow_enabled,False);self.assertIs(base.r2d2_v2_capacity_required,False)
  # Exact original context guard, isolated AST: DB unavailable stops before app import.
  original=(Path(j.__file__).parent/'originals'/'manifest_writer.py').read_bytes()
  context=next(n for n in ast.parse(original).body if isinstance(n,ast.FunctionDef)and n.name=='context')
  context.returns=None
  for a in context.args.args+context.args.kwonlyargs:a.annotation=None
  isolated=ast.Module(body=[context],type_ignores=[]);namespace={'need':j.need}
  exec(compile(ast.fix_missing_locations(isolated),'<original-context-guard-fixture>','exec'),namespace)
  with self.assertRaisesRegex(j.Refused,'PERSISTENT_DATABASE_REQUIRED'):
   namespace['context'](self.f.settings,now=self.f.clock(),prepare_first=True,clock=self.f.clock)
 def test_inexact_process_settings_refuse_before_observation_and_consume(self):
  self.f.rule['process_settings']['r2d2_v2_capacity_required']=False
  out=self.f.run_slot();self.assertEqual(out.code,'J_PROCESS_SETTINGS');self.assertEqual(self.f.events,[])
  self.assertEqual(self.f.run_slot().code,'ATTEMPT_ALREADY_CONSUMED')
 def test_missing_or_extra_process_flags_never_implicitly_authorized(self):
  self.f.rule.pop('process_settings')
  out=self.f.run_slot();self.assertEqual(out.code,'J_RULE_FIELDS');self.assertEqual(self.f.events,[])
 def test_r3d1_dependency_exact_and_recovery_without_consumption_is_uncertain(self):
  self.assertEqual(j.module_pin('finite_batch'),'311c2eaa47a223697324f7386b027b2e83c00926c00e7269fd4cfb9fe1c4fa25')
  def unavailable(*args):raise j.batch.ReservationFailure('LEDGER_UNVERIFIED','a'*64,False,recovery_required=True)
  self.f.ledger.claim=unavailable
  out=self.f.run_slot();self.assertEqual((out.status,out.code),('UNCERTAIN','LEDGER_UNVERIFIED'))
  self.assertEqual(self.f.events,[]);self.assertIsNone(out.writer_receipt_raw)

if __name__=='__main__':unittest.main()
