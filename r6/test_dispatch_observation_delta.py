"""NEW durable-token replay and external-J read-only observation fixtures."""
from datetime import timedelta
from pathlib import Path
import os,tempfile,time,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class DispatchObservation(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='new-r5-dispatch-',dir=Path(__file__).parent);self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
  (self.root/'attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)))
  self.x=Fixture(self.root);self.batch=c.FiniteBatch(self.x.bundle,self.ledger,self.x.services);self.scope=c.context(self.batch.q)+('prove',)
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def claim(self,nonce=None):return self.batch.reserve('prove',worker_nonce_sha256=c.sha(nonce) if nonce else None)
 def observe(self,key):return self.ledger.observe_reservation(self.scope,c.sha(self.batch.bundle.request),c.sha(self.batch.bundle.bound),key)
 def effects(self):return (self.root/'effects.synthetic').read_bytes() if (self.root/'effects.synthetic').exists() else b''
 def test_new_external_observation_is_read_only_and_cannot_authorize_core_effect(self):
  key=self.claim();before={p.name:p.read_bytes() for p in self.root.iterdir()};self.assertIsNone(self.observe(key));self.assertIsNone(self.observe(key))
  self.assertEqual(before,{p.name:p.read_bytes() for p in self.root.iterdir()});self.assertEqual(self.batch.run_reserved('prove',key)['effect_calls'],0);self.assertEqual(self.effects(),b'')
 def test_new_external_observation_rejects_changed_request_or_bound(self):
  key=self.claim()
  with self.assertRaisesRegex(c.Hold,'RESERVATION_PIN_CHANGED'):self.ledger.observe_reservation(self.scope,'a'*64,c.sha(self.batch.bundle.bound),key)
  with self.assertRaisesRegex(c.Hold,'RESERVATION_PIN_CHANGED'):self.ledger.observe_reservation(self.scope,c.sha(self.batch.bundle.request),'a'*64,key)
 def test_new_external_observation_requires_commit_and_complete_chain(self):
  key=self.claim();p=self.root/('reserved-'+key);p.write_bytes(b'')
  with self.assertRaisesRegex(c.Hold,'LEDGER_PROOF_INCOMPLETE'):self.observe(key)
  self.assertEqual(p.read_bytes(),b'');self.assertEqual(self.effects(),b'')
 def test_new_new_permit_with_same_nonce_cannot_dispatch_twice(self):
  nonce=os.urandom(32);key=self.claim(nonce);pid=os.fork()
  if pid==0:
   try:
    os.setsid();parent=os.getppid();end=o.now()+timedelta(seconds=1);mono=time.monotonic()+1
    first=self.batch._run_reserved('prove',key,permit=c._WorkerPermit(nonce,parent,end,mono))
    second=self.batch._run_reserved('prove',key,permit=c._WorkerPermit(nonce,parent,end,mono))
    (self.root/'replay.json').write_bytes(c.canonical({'first':first,'second':second}))
   finally:os._exit(0)
  os.waitpid(pid,0);out=c.strict((self.root/'replay.json').read_bytes());self.assertEqual(out['first']['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
  self.assertEqual(out['second']['code'],'WORKER_DISPATCH_ALREADY_CONSUMED');self.assertEqual(self.effects(),b'1')
 def test_new_parallel_workers_with_same_nonce_are_durably_single_dispatch(self):
  nonce=os.urandom(32);key=self.claim(nonce);pids=[]
  for i in range(2):
   pid=os.fork()
   if pid==0:
    try:
     os.setsid();out=self.batch._run_reserved('prove',key,permit=c._WorkerPermit(nonce,os.getppid(),o.now()+timedelta(seconds=1),time.monotonic()+1))
     (self.root/('worker%d.json'%i)).write_bytes(c.canonical(out))
    finally:os._exit(0)
   pids.append(pid)
  for pid in pids:os.waitpid(pid,0)
  out=[c.strict((self.root/('worker%d.json'%i)).read_bytes()) for i in range(2)]
  self.assertEqual(sum(x['effect_calls'] for x in out),1,out);self.assertEqual(self.effects(),b'1');self.assertIn('WORKER_DISPATCH_ALREADY_CONSUMED',[x['code'] for x in out])
 def test_new_zero_byte_dispatch_proof_remains_hold_without_effect_or_repair(self):
  nonce=os.urandom(32);key=self.claim(nonce);p=self.root/('dispatch-'+key);p.write_bytes(b'');os.chmod(p,0o600)
  with self.assertRaisesRegex(c.Hold,'LEDGER_PROOF_INCOMPLETE'):self.observe(key)
  self.assertEqual(p.read_bytes(),b'');self.assertEqual(self.effects(),b'')

if __name__=='__main__':unittest.main(verbosity=2)
