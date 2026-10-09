"""NEW public/private reentry and parent-lifeline fixtures; local POSIX only."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import os,signal,tempfile,time,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class SupervisionDelta(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='new-r5-supervision-',dir=Path(__file__).parent);self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
  (self.root/'attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)))
  self.x=Fixture(self.root);self.batch=c.FiniteBatch(self.x.bundle,self.ledger,self.x.services,clock=self.x.clock)
  self.outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=.8)
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def wait(self,name,timeout=2):
  stop=time.monotonic()+timeout
  while not (self.root/name).exists() and time.monotonic()<stop:time.sleep(.002)
  self.assertTrue((self.root/name).exists(),name)
 def effect_bytes(self):return (self.root/'effects.synthetic').read_bytes() if (self.root/'effects.synthetic').exists() else b''
 def fork_outer(self):
  pid=os.fork()
  if pid==0:
   try:
    out=self.outer.run(self.batch,'prove');(self.root/'outer.json').write_bytes(c.canonical(out))
   finally:os._exit(0)
  return pid
 def test_new_public_resume_parallel_with_outer_cannot_duplicate_effect(self):
  def execute(call):
   (self.root/'entered').write_bytes(b'1');time.sleep(.15);return self.x.execute(call)
  self.batch.services=replace(self.x.services,execute=execute);pid=self.fork_outer()
  try:
   self.wait('entered');key=c.sha(c.canonical(list(c.context(self.batch.q)+('prove',))))
   out=self.batch.run_reserved('prove',key);self.assertEqual(out['effect_calls'],0)
  finally:os.waitpid(pid,0)
  out=c.strict((self.root/'outer.json').read_bytes());self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out);self.assertEqual(self.effect_bytes(),b'1')
 def test_new_parent_loss_lifeline_kills_before_remaining_budget_effect(self):
  def execute(call):
   (self.root/'entered').write_bytes(b'1');time.sleep(.3);return self.x.execute(call)
  self.batch.services=replace(self.x.services,execute=execute);pid=self.fork_outer();self.wait('entered')
  os.kill(pid,signal.SIGKILL);os.waitpid(pid,0);time.sleep(.4)
  self.assertEqual(self.effect_bytes(),b'');self.assertFalse((self.root/'outer.json').exists())
  key=c.sha(c.canonical(list(c.context(self.batch.q)+('prove',))))
  out=self.batch.run_reserved('prove',key);self.assertEqual(out['effect_calls'],0)
  out=self.outer.run(self.batch,'prove');self.assertEqual(out['status'],'UNCERTAIN_CONSUMED');self.assertEqual(out['effect_calls'],0);self.assertTrue(out['recovery_required'])
 def test_new_parent_loss_after_effect_never_allows_public_second_effect(self):
  def execute(call):
   result=self.x.execute(call);(self.root/'entered').write_bytes(b'1');time.sleep(.3);return result
  self.batch.services=replace(self.x.services,execute=execute);pid=self.fork_outer();self.wait('entered')
  os.kill(pid,signal.SIGKILL);os.waitpid(pid,0);time.sleep(.06)
  key=c.sha(c.canonical(list(c.context(self.batch.q)+('prove',))))
  for _ in range(2):self.assertEqual(self.batch.run_reserved('prove',key)['effect_calls'],0)
  out=self.outer.run(self.batch,'prove');self.assertEqual(out['status'],'UNCERTAIN_CONSUMED');self.assertEqual(self.effect_bytes(),b'1')
 def test_new_one_use_permit_refuses_second_entry_inside_worker(self):
  nonce=os.urandom(32);key=self.batch.reserve('prove',worker_nonce_sha256=c.sha(nonce));pid=os.fork()
  if pid==0:
   try:
    os.setsid();permit=c._WorkerPermit(nonce,os.getppid(),o.now()+timedelta(seconds=1),time.monotonic()+1)
    first=self.batch._run_reserved('prove',key,permit=permit);second=self.batch._run_reserved('prove',key,permit=permit)
    (self.root/'private.json').write_bytes(c.canonical({'first':first,'second':second}))
   finally:os._exit(0)
  os.waitpid(pid,0);out=c.strict((self.root/'private.json').read_bytes())
  self.assertEqual(out['first']['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
  self.assertEqual(out['second']['code'],'OUTER_WORKER_CAPABILITY_REQUIRED');self.assertEqual(self.effect_bytes(),b'1')
 def test_new_descendant_cannot_use_leader_permit(self):
  nonce=os.urandom(32);key=self.batch.reserve('prove',worker_nonce_sha256=c.sha(nonce));pid=os.fork()
  if pid==0:
   try:
    os.setsid();permit=c._WorkerPermit(nonce,os.getppid(),o.now()+timedelta(seconds=1),time.monotonic()+1);child=os.fork()
    if child==0:
     try:(self.root/'descendant.json').write_bytes(c.canonical(self.batch._run_reserved('prove',key,permit=permit)))
     finally:os._exit(0)
    os.waitpid(child,0)
   finally:os._exit(0)
  os.waitpid(pid,0);out=c.strict((self.root/'descendant.json').read_bytes());self.assertEqual(out['code'],'OUTER_WORKER_SCOPE_INVALID');self.assertEqual(self.effect_bytes(),b'')
 def test_new_inherited_inner_child_is_not_a_core_dispatcher(self):
  import bounded_runner as inner
  self.assertEqual(inner.Registry.__dataclass_fields__['containment'].default,'OWN_SESSION')
  source=Path(inner.__file__).read_text();self.assertNotIn('run_reserved(',source);self.assertIn('INHERITED_OUTER_GROUP',source)

if __name__=='__main__':unittest.main(verbosity=2)
