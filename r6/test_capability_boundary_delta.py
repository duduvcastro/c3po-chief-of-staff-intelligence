"""NEW root-peer boundaries: threads, public classification and commit reread."""
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import os,tempfile,threading,time,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class PeerBoundary(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='new-r5-peer-',dir=Path(__file__).parent);self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
  (self.root/'attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)))
  self.x=Fixture(self.root);self.batch=c.FiniteBatch(self.x.bundle,self.ledger,self.x.services)
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def test_new_public_unknown_key_does_not_claim_consumed_or_durable(self):
  out=self.batch.run_reserved('prove','invalid')
  self.assertEqual(out['status'],'REFUSED_NO_EFFECT');self.assertIsNone(out['attempt_key']);self.assertFalse(out['reservation_durable'])
  self.assertFalse(out['recovery_required']);self.assertEqual(out['consumption_state'],'UNIDENTIFIED');self.assertFalse((self.root/'effects.synthetic').exists())
 def test_new_public_pending_key_is_unverified_not_closed(self):
  key=self.batch.reserve('prove');out=self.batch.run_reserved('prove',key)
  self.assertEqual(out['status'],'REFUSED_NO_EFFECT');self.assertTrue(out['recovery_required']);self.assertFalse(out['reservation_durable'])
  self.assertEqual(out['consumption_state'],'UNVERIFIED');self.assertEqual(len((self.root/'attempts.ledger').read_bytes().splitlines()),1)
 def test_new_worker_thread_reentry_is_refused_before_any_callback(self):
  nonce=os.urandom(32);key=self.batch.reserve('prove',worker_nonce_sha256=c.sha(nonce));pid=os.fork()
  if pid==0:
   try:
    os.setsid();permit=c._WorkerPermit(nonce,os.getppid(),o.now()+timedelta(seconds=1),time.monotonic()+1)
    outputs=[];t=threading.Thread(target=lambda:outputs.append(self.batch._run_reserved('prove',key,permit=permit)));t.start();t.join()
    (self.root/'thread.json').write_bytes(c.canonical(outputs[0]))
   finally:os._exit(0)
  os.waitpid(pid,0);out=c.strict((self.root/'thread.json').read_bytes())
  self.assertEqual(out['code'],'OUTER_WORKER_THREAD_INVALID');self.assertEqual(out['effect_calls'],0);self.assertFalse((self.root/'effects.synthetic').exists())
 def test_new_reserved_commit_reread_must_match_exact_claim(self):
  nonce=os.urandom(32);key=self.batch.reserve('prove',worker_nonce_sha256=c.sha(nonce));original=self.ledger._file;seen=0
  def changed(name):
   nonlocal seen
   value,digest=original(name)
   if name=='reserved-'+key:
    seen+=1
    if seen==2:value=dict(value,claim_sha256='a'*64)
   return value,digest
  with patch.object(self.ledger,'_file',side_effect=changed):
   with self.assertRaisesRegex(c.Hold,'RESERVATION_COMMIT_CHANGED'):
    self.ledger.check_reserved(c.context(self.batch.q)+('prove',),c.sha(self.batch.bundle.request),c.sha(self.batch.bundle.bound),key,worker_nonce=nonce)
  self.assertFalse((self.root/'effects.synthetic').exists())

if __name__=='__main__':unittest.main(verbosity=2)
