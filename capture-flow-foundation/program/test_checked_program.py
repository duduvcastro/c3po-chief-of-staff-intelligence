import copy,datetime as dt,unittest
import checked_program as m
NOW=dt.datetime(2026,10,8,11,45,tzinfo=dt.timezone.utc)
CTX=dict(session='2026-10-08',run_id='37699999999',run_attempt=1,nonce='a'*32)
def auth():return dict(schema='CAPTURE_JOB_DATED_AUTHORITY_V1',status='SIGNED',owner='DUDU',answer='Assino',session=CTX['session'],source_layout_sha256='b'*64,outside_Mac=True,single_job=True,single_use=True,retry=False,election='JOB_ONLY_MAC_CAPTURE_RETIRED_BEFORE_PREPARE',retired_mac_config_sha256=[x*64 for x in ('c','d','e','f')],document_sha256='b'*64,source_owner_record_body_sha256='c'*64,operator_election_record_body_sha256='d'*64,signed_at_utc='2026-10-07T20:00:00Z',election_observed_at_utc='2026-10-08T11:40:00Z')
def approval():return dict(schema='CAPTURE_JOB_PHYSICAL_APPROVAL_V1',verdict='PASS_PHYSICAL_RUNTIME',**CTX,measurement_sha256='c'*64,source_layout_sha256='b'*64,dated_authority_sha256='d'*64,runtime_guard_sha256=m.HELPER,binder_sha256=m.BINDER,accepted_seals_sha256=m.REGISTRY,review_body_sha256='e'*64,measured_at_utc='2026-10-08T11:41:00Z',reviewed_at_utc='2026-10-08T11:43:00Z')
class Proof(unittest.TestCase):
 def bad(self,f,*a):
  with self.assertRaises(m.Refused):f(*a)
 def test_exact_synthetic_dated_scope(self):self.assertEqual(m.authority(auth(),'b'*64,NOW),auth())
 def test_no_unsigned_other_day_retry_or_mac_overlap(self):
  for key,value in [('status','DRAFT'),('answer','sim'),('session','2026-10-09'),('outside_Mac',False),('single_job',False),('retry',True),('election','BOTH'),('source_layout_sha256','a'*64),('retired_mac_config_sha256',['c'*64]*4),('operator_election_record_body_sha256','')]:
   with self.subTest(key=key):self.bad(m.authority,dict(auth(),**{key:value}),'b'*64,NOW)
 def test_no_future_or_before_signature_election(self):
  for value in ['2026-10-09T11:40:00Z','2026-10-07T19:00:00Z']:
   self.bad(m.authority,dict(auth(),election_observed_at_utc=value),'b'*64,NOW)
 def test_exact_synthetic_own_physical_scope(self):self.assertEqual(m.approval(approval(),'c'*64,'b'*64,'d'*64,CTX,NOW),approval())
 def test_old_job_date_or_program_measurement_refused(self):
  for key,value in [('run_id','37699999998'),('run_attempt',True),('nonce','b'*32),('session','2026-10-07'),('measurement_sha256','d'*64),('source_layout_sha256','c'*64),('runtime_guard_sha256','f'*64),('reviewed_at_utc','2026-10-08T11:50:00Z'),('measured_at_utc','2026-10-07T11:40:00Z')]:
   with self.subTest(key=key):self.bad(m.approval,dict(approval(),**{key:value}),'c'*64,'b'*64,'d'*64,CTX,NOW)
 def test_allowlisted_source_layout_only(self):
  x=dict(schema='CAPTURE_JOB_SOURCE_LAYOUT_V1',session='2026-10-08',tools={k:dict(path=v,sha256='b'*64) for k,v in m.PATHS.items()},helpers={'capture_job/checked_program.py':'c'*64});self.assertEqual(m.layout(x),x)
  for path in ['/private/script.py','capture_job/../script.py']:
   v=copy.deepcopy(x);v['helpers'][path]='d'*64;self.bad(m.layout,v)
  v=copy.deepcopy(x);v['tools']['binder']['path']='private/arbitrary.py';self.bad(m.layout,v)
  v=copy.deepcopy(x);v['helpers']['capture_job/live_adapter.py']='d'*64;self.bad(m.layout,v)
if __name__=='__main__':unittest.main()
