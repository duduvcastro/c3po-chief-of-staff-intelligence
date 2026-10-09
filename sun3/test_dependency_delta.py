"""NEW dependency-only vectors; no old fourteen or task-window-four suite."""
from dataclasses import replace
from pathlib import Path
import unittest
import fixture_builder as fixture
import upstream_veto as u
import veto_emitter as v
import finite_batch as b

class DependencyDelta(unittest.TestCase):
 def setUp(self):self.f=fixture.Sunday('runTest');self.f.setUp()
 def tearDown(self):self.f.tearDown()
 def test_final_r3d1_dependency_and_exact_allow_consumer_class(self):
  self.assertEqual(self.f.spec['dependencies']['finite_batch'],'311c2eaa47a223697324f7386b027b2e83c00926c00e7269fd4cfb9fe1c4fa25')
  self.f.make();view=self.f.read();self.assertIs(type(view),b.VetoView)
  self.assertIsNone(self.f.source.before_effect(self.f.q,self.f.task))
  self.assertEqual(view.observed_at,self.f.now);self.assertLessEqual((view.valid_until-view.observed_at).total_seconds(),5)
 def test_previous_no_go_r3c_dependency_cannot_load_or_observe(self):
  old='1cf1cbf150836d11675c13421cc5a334b4cade6afc452fc70829cca55422e25e'
  self.f.spec['dependencies']['finite_batch']=old
  self.f.spec['required_pins']=sorted(set(self.f.spec['required_pins'])|{old})
  with self.assertRaisesRegex(u.Refused,'FOLDER_DEPENDENCY_PIN'):self.f.make()
  self.assertIsNone(self.f.source)
 def test_every_dependency_is_in_current_revocation_scope(self):
  pin=self.f.spec['dependencies']['veto_emitter'];self.f.spec['required_pins'].remove(pin)
  with self.assertRaisesRegex(u.Refused,'FOLDER_REVOCATION_SCOPE'):self.f.make()
 def test_dependency_change_in_authority_callback_refuses_before_observation(self):
  self.f.make();p=Path(b.__file__);original=p.read_bytes()
  def mutate(*args):p.write_bytes(original+b'\n# Synthetic dependency mutation.\n')
  self.f.source.binding=replace(self.f.source.binding,verify_current=mutate)
  try:
   with self.assertRaisesRegex(u.Refused,'FOLDER_DEPENDENCY_PIN'):self.f.read()
   self.assertIsNone(self.f.source.original)
  finally:p.write_bytes(original)

if __name__=='__main__':unittest.main()
