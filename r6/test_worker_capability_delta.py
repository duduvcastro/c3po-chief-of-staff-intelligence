"""NEW capability/native clock/hard deadline fixtures; no historical suites."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import fcntl,json,os,signal,tempfile,time,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class CapabilityDelta(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='new-r5-capability-',dir=Path(__file__).parent)
  self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
  (self.root/'attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)),lock_budget_seconds=.04,finish_budget_seconds=1.5)
  self.x=Fixture(self.root);self.batch=c.FiniteBatch(self.x.bundle,self.ledger,self.x.services,clock=self.x.clock)
  self.outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=.8)
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def effects(self):return (self.root/'effects.synthetic').read_bytes() if (self.root/'effects.synthetic').exists() else b''
 def public(self,key):
  before=(self.root/'attempts.ledger').read_bytes();out=self.batch.run_reserved('prove',key,terminal=True)
  self.assertEqual(out['code'],'OUTER_WORKER_CAPABILITY_REQUIRED',out);self.assertEqual(out['effect_calls'],0)
  self.assertEqual((self.root/'attempts.ledger').read_bytes(),before);return out
 def test_new_public_resume_pending_claim_never_effects_or_finalizes(self):
  key=self.batch.reserve('prove');self.public(key);self.public(key);self.assertEqual(self.effects(),b'')
 def test_new_private_entry_requires_typed_permit(self):
  key=self.batch.reserve('prove');out=self.batch._run_reserved('prove',key,permit=None)
  self.assertEqual(out['code'],'OUTER_WORKER_CAPABILITY_REQUIRED');self.assertEqual(self.effects(),b'')
 def test_new_nonce_hash_is_committed_but_nonce_not_on_disk(self):
  nonce=os.urandom(32);key=self.batch.reserve('prove',worker_nonce_sha256=c.sha(nonce))
  data=(self.root/'attempts.ledger').read_bytes();claim=c.strict(data.strip())
  self.assertEqual(claim['data']['worker_nonce_sha256'],c.sha(nonce));self.assertNotIn(nonce.hex().encode(),data)
  self.ledger.check_reserved(c.context(self.batch.q)+('prove',),c.sha(self.batch.bundle.request),c.sha(self.batch.bundle.bound),key,worker_nonce=nonce)
  with self.assertRaisesRegex(c.Hold,'WORKER_NONCE_MISMATCH'):
   self.ledger.check_reserved(c.context(self.batch.q)+('prove',),c.sha(self.batch.bundle.request),c.sha(self.batch.bundle.bound),key,worker_nonce=b'x'*32)
 def test_new_legacy_pending_claim_without_nonce_cannot_dispatch(self):
  key=self.batch.reserve('prove')
  with self.assertRaisesRegex(c.Hold,'WORKER_NONCE_MISMATCH'):
   self.ledger.check_reserved(c.context(self.batch.q)+('prove',),c.sha(self.batch.bundle.request),c.sha(self.batch.bundle.bound),key,worker_nonce=b'x'*32)
  self.public(key);self.assertEqual(self.effects(),b'')
 def test_new_current_outer_executes_once_then_refuses_durable_terminal(self):
  first=self.outer.run(self.batch,'prove');self.assertEqual(first['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',first)
  second=self.outer.run(self.batch,'prove');self.assertEqual(second['status'],'REFUSED_CONSUMED',second)
  self.assertFalse(second['recovery_required']);self.assertEqual(self.effects(),b'1');self.public(first['attempt_key']);self.assertEqual(self.effects(),b'1')
 def test_new_injected_stale_clock_cannot_make_old_veto_current(self):
  stale=o.now()-timedelta(seconds=60)
  self.batch.clock=lambda:stale
  self.batch.monotonic=lambda:0
  self.batch.services=replace(self.x.services,veto_read=lambda q,t,n:c.VetoView(b'SYNTHETIC_STALE',q['veto_authority_sha256'],'ALLOW',stale,stale+timedelta(seconds=5)))
  out=self.outer.run(self.batch,'prove');self.assertEqual(out['inner_result']['code'],'REAL_VETO_NOT_FRESH_ALLOW',out)
  self.assertEqual(out['effect_calls'],0);self.assertEqual(self.effects(),b'')
 def test_new_injected_clock_is_never_called_by_supervised_dispatch(self):
  self.batch.clock=lambda:(_ for _ in ()).throw(AssertionError('injected clock used'))
  self.batch.monotonic=lambda:(_ for _ in ()).throw(AssertionError('injected mono used'))
  out=self.outer.run(self.batch,'prove');self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
 def test_new_invocation_deadlines_are_inside_outer_hard_deadline(self):
  start=o.now();mark=time.monotonic();self.outer.hard_budget=.4
  def execute(call):
   (self.root/'invocation.json').write_bytes(c.canonical({'wall':c.iso(call.deadline_utc),'mono':call.deadline_monotonic}))
   return self.x.execute(call)
  self.batch.services=replace(self.x.services,execute=execute)
  out=self.outer.run(self.batch,'prove');self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
  inv=c.strict((self.root/'invocation.json').read_bytes());self.assertLessEqual(inv['mono'],mark+.42)
  self.assertLessEqual((c.instant(inv['wall'])-start).total_seconds(),.42)
 def test_new_busy_refusal_diagnosis_does_not_claim_retry_authority(self):
  fd=os.open(self.root/'attempts.ledger',os.O_RDWR)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);out=self.outer.run(self.batch,'prove')
   self.assertEqual(out['status'],'REFUSED_NOT_RESERVED');self.assertEqual(out['refusal_class'],'LOCK_BUSY')
   self.assertFalse(out['recovery_required']);self.assertFalse(out['automatic_retry']);self.assertEqual(self.effects(),b'')
  finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
 def test_new_torn_global_hold_remains_unmodified_and_requires_recovery(self):
  (self.root/'attempts.ledger').write_bytes(b'PARTIAL')
  out=self.outer.run(self.batch,'prove');self.assertEqual(out['refusal_class'],'LEDGER_HOLD');self.assertTrue(out['recovery_required'])
  self.assertEqual((self.root/'attempts.ledger').read_bytes(),b'PARTIAL');self.assertEqual(self.effects(),b'')
 def test_new_zero_byte_consume_proof_remains_global_hold(self):
  key=c.sha(c.canonical(list(c.context(self.batch.q)+('prove',))))
  p=self.root/('consume-'+key);p.write_bytes(b'');os.chmod(p,0o600)
  out=self.outer.run(self.batch,'prove');self.assertEqual(out['status'],'UNCERTAIN_CONSUMED');self.assertEqual(out['code'],'LEDGER_PROOF_INCOMPLETE')
  self.assertTrue(out['recovery_required']);self.assertEqual(p.read_bytes(),b'');self.assertEqual(self.effects(),b'')
 def test_new_finish_waits_own_budget_after_worker_cleanup(self):
  marker=self.root/'hold-lock';release=self.root/'lock-held'
  holder=os.fork()
  if holder==0:
   try:
    stop=time.monotonic()+3
    while not marker.exists() and time.monotonic()<stop:time.sleep(.002)
    fd=os.open(self.root/'attempts.ledger',os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX);release.write_bytes(b'1');time.sleep(.65)
    fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
   finally:os._exit(0)
  try:
   def execute(call):
    result=self.x.execute(call);marker.write_bytes(b'1')
    stop=time.monotonic()+.2
    while not release.exists() and time.monotonic()<stop:time.sleep(.002)
    return result
   self.batch.services=replace(self.x.services,execute=execute);out=self.outer.run(self.batch,'prove')
   self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out);self.assertEqual(self.effects(),b'1')
   self.assertEqual([c.strict(x)['kind'] for x in (self.root/'attempts.ledger').read_bytes().splitlines()],['CLAIM','TERMINAL'])
  finally:os.waitpid(holder,0)

if __name__=='__main__':unittest.main(verbosity=2)
