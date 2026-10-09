"""NEW R6 terminal owner/schema/foreign-bound/umask fixtures only."""
from pathlib import Path
from dataclasses import replace
import os,signal,stat,tempfile,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class TerminalOwnerDelta(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='new-r6-terminal-',dir=Path(__file__).parent)
  self.root=Path(self.tmp.name);os.chmod(self.root,0o700)
  (self.root/'attempts.ledger').write_bytes(b'');os.chmod(self.root/'attempts.ledger',0o600)
  self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)),lock_budget_seconds=.04,finish_budget_seconds=1)
  self.x=Fixture(self.root);self.batch=c.FiniteBatch(self.x.bundle,self.ledger,self.x.services,clock=self.x.clock)
  self.outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=.8)
 def tearDown(self):self.ledger.close();self.tmp.cleanup()
 def pending(self,mode='LOCAL_REFUSAL'):
  permit=c._TerminalPermit(os.urandom(32),mode)
  key=self.batch.reserve('prove',worker_nonce_sha256=c.sha(os.urandom(32)),terminal_permit=permit)
  return key,permit
 def refused(self,key):
  return {'schema':'L12_LOCAL_ATTEMPT_CANDIDATE_V1','status':'REFUSED_CONSUMED','code':'OUTER_LIMITER_REQUIRED',
          'inner_code':None,'operation':'prove','attempt_key':key,'effect_calls':0,'original_receipt_sha256':None,
          'original_receipt_completed_at':None,'automatic_retry':False,'operational_GO_granted':False,
          'physical_host_certified':False,'completed_at':c.iso(o.now())}
 def test_new_public_finish_without_owner_cannot_forge_complete_or_append(self):
  key,_=self.pending();before=(self.root/'attempts.ledger').read_bytes()
  with self.assertRaisesRegex(c.Hold,'TERMINAL_PARENT_CAPABILITY_REQUIRED'):
   self.ledger.finish(key,{'schema':'anything','status':'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE'})
  self.assertEqual((self.root/'attempts.ledger').read_bytes(),before)
  self.assertFalse((self.root/('terminal-'+key)).exists())
 def test_new_current_outer_parent_commits_only_own_complete_once(self):
  first=self.outer.run(self.batch,'prove');self.assertEqual(first['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',first)
  second=self.outer.run(self.batch,'prove');self.assertEqual(second['status'],'REFUSED_CONSUMED',second)
  self.assertEqual(second['previous_effect_calls'],1);self.assertIsNone(second['previous_terminal_code'])
  self.assertFalse(second['recovery_required']);self.assertEqual((self.root/'effects.synthetic').read_bytes(),b'1')
 def test_new_wrong_private_parent_nonce_cannot_close_existing_claim(self):
  key,_=self.pending();other=c._TerminalPermit(os.urandom(32),'LOCAL_REFUSAL');before=(self.root/'attempts.ledger').read_bytes()
  with self.assertRaisesRegex(c.Hold,'TERMINAL_OWNER_MISMATCH'):
   self.ledger.finish(key,self.refused(key),terminal_permit=other)
  self.assertEqual((self.root/'attempts.ledger').read_bytes(),before)
 def test_new_owner_does_not_accept_wrong_terminal_schema_or_status(self):
  key,permit=self.pending();row=self.refused(key);row['schema']='anything';before=(self.root/'attempts.ledger').read_bytes()
  with self.assertRaisesRegex(c.Hold,'TERMINAL_RESULT_SCHEMA_INVALID'):
   self.ledger.finish(key,row,terminal_permit=permit)
  self.assertEqual((self.root/'attempts.ledger').read_bytes(),before)
  row=self.refused(key);row['status']='ORIGINAL_COMPLETE_OBSERVED_CANDIDATE'
  with self.assertRaisesRegex(c.Hold,'TERMINAL_RESULT_SCHEMA_INVALID'):
   self.ledger.finish(key,row,terminal_permit=permit)
 def test_new_parent_terminal_permit_cannot_be_used_in_fork_child(self):
  key,permit=self.pending();pid=os.fork()
  if pid==0:
   try:
    try:self.ledger.finish(key,self.refused(key),terminal_permit=permit)
    except c.Hold as e:(self.root/'child-failure').write_text(str(e));os._exit(0)
    os._exit(2)
   except BaseException:os._exit(3)
  _,status=os.waitpid(pid,0);self.assertEqual(status,0)
  self.assertEqual((self.root/'child-failure').read_text(),'TERMINAL_OWNER_SCOPE_INVALID')
  self.assertFalse((self.root/('terminal-'+key)).exists())
 def test_new_terminal_permit_is_one_use_even_for_same_refusal(self):
  key,permit=self.pending();self.ledger.finish(key,self.refused(key),terminal_permit=permit)
  before=(self.root/'attempts.ledger').read_bytes()
  with self.assertRaisesRegex(c.Hold,'TERMINAL_OWNER_SCOPE_INVALID'):
   self.ledger.finish(key,self.refused(key),terminal_permit=permit)
  self.assertEqual((self.root/'attempts.ledger').read_bytes(),before)
 def test_new_legacy_claim_without_terminal_owner_cannot_be_promoted(self):
  key=self.batch.reserve('prove');permit=c._TerminalPermit(os.urandom(32),'LOCAL_REFUSAL')
  with self.assertRaisesRegex(c.Hold,'TERMINAL_OWNER_MISMATCH'):
   self.ledger.finish(key,self.refused(key),terminal_permit=permit)
  self.assertFalse((self.root/('terminal-'+key)).exists())
 def test_new_j_family_terminal_has_no_core_complete_dependency_authority(self):
  scope=(c.EPOCH,c.DAY,'J_ADMISSION_FAMILY_V1');permit=c._TerminalPermit(os.urandom(32),'J_FAMILY')
  req,bound=c.sha(b'SYNTHETIC_J_REQUEST'),c.sha(b'SYNTHETIC_J_BOUND')
  key=self.ledger.claim(scope,req,bound,None,terminal_permit=permit)
  row={'schema':'L12_J_FAMILY_TERMINAL_CANDIDATE_V1','family':'J_ADMISSION_FAMILY_V1','status':'COMPLETE',
       'code':'J_IMAGE_MANIFEST_COMPLETE','attempt_key':key,'completed_at':c.iso(o.now()),'automatic_retry':False,
       'result':{'status':'COMPLETE','code':'J_IMAGE_MANIFEST_COMPLETE','attempt_key':key,'operational_GO':False}}
  self.ledger.finish_family(key,row,terminal_permit=permit)
  with self.assertRaisesRegex(c.Hold,'DEPENDENCY_TERMINAL_NOT_OWNED'):
   self.ledger.dependency(scope,req,bound,self.x.receipt('prove'))
 def test_new_foreign_request_or_bound_is_consumed_unresolved_not_exact_closed(self):
  first=self.outer.run(self.batch,'prove');self.assertEqual(first['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',first)
  for req,bound in ((c.sha(b'FOREIGN_REQUEST'),c.sha(self.batch.bundle.bound)),
                    (c.sha(self.batch.bundle.request),c.sha(b'FOREIGN_BOUND'))):
   with self.assertRaises(c.ReservationFailure) as caught:
    self.ledger.claim(c.context(self.batch.q)+('prove',),req,bound,None)
   err=caught.exception;self.assertEqual(str(err),'ATTEMPT_CONSUMED_BY_OTHER_BOUND');self.assertTrue(err.recovery_required)
   self.assertFalse(err.closed);self.assertEqual(err.previous_terminal_status,'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE')
  self.assertEqual((self.root/'effects.synthetic').read_bytes(),b'1')
 def test_new_proof_permissions_are_exact_0600_under_umask_0277(self):
  previous=os.umask(0o277)
  try:out=self.outer.run(self.batch,'prove')
  finally:os.umask(previous)
  self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
  for name in ('consume-','reserved-','dispatch-','terminal-'):
   self.assertEqual(stat.S_IMODE((self.root/(name+out['attempt_key'])).stat().st_mode),0o600)

 def test_new_durable_uncertain_after_worker_loss_remains_uncertain_on_second_call(self):
  def execute(call):
   self.x.execute(call)
   os.kill(os.getpid(),signal.SIGKILL)
  self.batch.services=replace(self.x.services,execute=execute)
  first=self.outer.run(self.batch,'prove')
  self.assertEqual(first['status'],'UNCERTAIN_CONSUMED',first)
  self.assertEqual(first['code'],'OUTER_WORKER_LOST',first)
  second=self.outer.run(self.batch,'prove')
  self.assertEqual(second['status'],'UNCERTAIN_CONSUMED',second)
  self.assertTrue(second['recovery_required']);self.assertTrue(second['reservation_durable'])
  self.assertEqual(second['previous_terminal_code'],'OUTER_WORKER_LOST')
  self.assertIsNone(second['previous_effect_calls'])
  self.assertFalse(second['automatic_retry']);self.assertEqual((self.root/'effects.synthetic').read_bytes(),b'1')

 def test_new_legacy_forged_complete_is_consumed_readonly_but_not_dependency(self):
  key=self.batch.reserve('prove');receipt=self.x.receipt('prove',o.now())
  fake={'schema':'anything','status':'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',
        'original_receipt_sha256':c.sha(receipt.raw),'original_receipt_completed_at':c.iso(receipt.completed_at)}
  # TEST ONLY: reproduces an old public finish by creating its retained rows.
  with self.ledger._lock():
   rows,previous=self.ledger._rows();terminal=self.ledger._append(rows,previous,key,'TERMINAL',fake)
   self.ledger._commit_terminal(key,terminal,fake['status'])
  before=(self.root/'attempts.ledger').read_bytes()
  with self.assertRaisesRegex(c.Hold,'DEPENDENCY_TERMINAL_NOT_OWNED'):
   self.ledger.dependency(c.context(self.batch.q)+('prove',),c.sha(self.batch.bundle.request),c.sha(self.batch.bundle.bound),receipt)
  self.assertEqual((self.root/'attempts.ledger').read_bytes(),before)
  again=self.outer.run(self.batch,'prove');self.assertEqual(again['status'],'REFUSED_CONSUMED',again)
  self.assertFalse((self.root/'effects.synthetic').exists())
 def test_new_current_owned_outer_complete_is_dependency_with_exact_original(self):
  out=self.outer.run(self.batch,'prove');self.assertEqual(out['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',out)
  receipt=self.x.receipt('prove',c.instant(out['original_receipt_completed_at']))
  self.assertEqual(c.sha(receipt.raw),out['original_receipt_sha256'])
  self.assertIsNone(self.ledger.dependency(c.context(self.batch.q)+('prove',),c.sha(self.batch.bundle.request),c.sha(self.batch.bundle.bound),receipt))
  self.assertEqual((self.root/'effects.synthetic').read_bytes(),b'1')

if __name__=='__main__':unittest.main(verbosity=2)
