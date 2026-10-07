"""Synthetic authenticated-input proof. No REAL prepare/sign/transport or host."""
import copy,datetime as dt,hashlib,json,pathlib,sys,types,unittest
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parent;BUILD=ROOT/'transport_challenge/build'
RAW=(BUILD/'capture_transport_challenge.py').read_bytes()
m=types.ModuleType('capture_transport_challenge_offline_test');m.__file__=str(BUILD/'capture_transport_challenge.py');sys.modules[m.__name__]=m
exec(compile(RAW,m.__file__,'exec'),m.__dict__)
NOW=lambda:dt.datetime(2026,10,8,11,55,tzinfo=dt.timezone.utc)
SCENARIOS=0
class NoHost:
 def __getattr__(self,name):raise AssertionError('HOST_METHOD_FORBIDDEN_'+name)
def fixture():
 request=json.loads((BUILD/'REQUEST.UNBOUND.json').read_bytes());auth=json.loads((BUILD/'AUTHORITY.UNBOUND.json').read_bytes());go=json.loads((BUILD/'GO.UNBOUND.json').read_bytes())
 start='2026-10-08T11:52:00+00:00';end='2026-10-08T12:02:00+00:00';host='a'*64
 for o in (request,auth,go):o.update(not_before=start,not_after=end,host_binding_sha256=host)
 request.update(status='BOUND',date='2026-10-08');request['plan'].update(status='BOUND',session='2026-10-08',run_id='37612765727',run_attempt=1,nonce='b'*32,host_binding_sha256=host,window=dict(not_before=start,expires_at=end))
 auth.update(status='SIGNED',decision='APPROVED',execution_authorized=True,owner='SYNTHETIC_TEST_NOT_DUDU',owner_evidence='SYNTHETIC_TEST_NO_HUMAN_SIGNATURE',effects=m.effects_of(request['plan']))
 go.update(status='SIGNED',action='GO',execution_authorized=True,owner=auth['owner'],effects=auth['effects'],claim_root_identity=dict(path='/synthetic-not-real-claim-root',device=1,inode=2));go['transport_binding'].update(target='fixture@fixture.invalid',command_sha256='c'*64)
 return request,auth,go

def invoke(request,auth,go,clock=NOW,uid=lambda:0,wrong_pin=False):
 global SCENARIOS;SCENARIOS+=1
 rr=m.canonical(request);auth=dict(auth,request_sha256=m.sha(rr));ar=m.canonical(auth);go=dict(go,request_sha256=m.sha(rr),authority_sha256=m.sha(ar));gr=m.canonical(go)
 pins=m.Pins(request=m.sha(rr),authority=m.sha(ar),go=m.sha(gr),payload=m.sha(RAW))
 if wrong_pin:pins=m.Pins(request='d'*64,authority=m.sha(ar),go=m.sha(gr),payload=m.sha(RAW))
 return m.run(rr,ar,gr,pins=pins,payload_bytes=RAW,clock=clock,monotonic=lambda:1.,executor_uid=uid,host=NoHost())
class Tests(unittest.TestCase):
 def test_complete_echo_no_host_method(self):
  r,a,g=fixture();got=invoke(r,a,g)
  self.assertEqual(got['status'],m.COMPLETE_STATUS);self.assertEqual(got['outcome'],m.COMPLETE_OUTCOME)
  self.assertEqual(got['nonce'],r['plan']['nonce']);self.assertEqual(got['writes'],0);self.assertEqual(got['host_reads'],0);self.assertFalse(got['host_readiness'])
 def test_scope_date_and_context_refusals(self):
  for key,val in [('session','2026-10-09'),('run_id','001234'),('run_attempt',2),('run_attempt',True),('nonce','short')]:
   with self.subTest(key=key):
    r,a,g=fixture();r['plan'][key]=val
    self.assertEqual(invoke(r,a,g)['status'],m.REFUSED_STATUS)
  r,a,g=fixture();r['plan']['window']['not_before']='2026-10-08T11:53:00+00:00';r['not_before']=a['not_before']=g['not_before']=r['plan']['window']['not_before']
  self.assertEqual(invoke(r,a,g)['status'],m.REFUSED_STATUS)
 def test_unsigned_authority_refused(self):
  r,a,g=fixture();a['execution_authorized']=False;self.assertEqual(invoke(r,a,g)['status'],m.REFUSED_STATUS)
 def test_wrong_pin_refused(self):
  self.assertEqual(invoke(*fixture(),wrong_pin=True)['status'],m.REFUSED_STATUS)
 def test_uid_mismatch_refused(self):
  self.assertEqual(invoke(*fixture(),uid=lambda:1000)['status'],m.REFUSED_STATUS)
 def test_expired_refused(self):
  self.assertEqual(invoke(*fixture(),clock=lambda:dt.datetime(2026,10,8,12,2,1,tzinfo=dt.timezone.utc))['status'],m.REFUSED_STATUS)
 def test_changed_signed_effects_refused(self):
  r,a,g=fixture();g['effects']['host_writes']=1;self.assertEqual(invoke(r,a,g)['status'],m.REFUSED_STATUS)
if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):
   denied.append(event);raise RuntimeError('NO_NETWORK_CHILD_OR_HOST')
 sys.addaudithook(audit)
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 report=dict(schema='CAPTURE_TRANSPORT_CHALLENGE_SYNTHETIC_PROOF_V1',methods=result.testsRun,scenarios=SCENARIOS,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),source_sha256=m.sha(RAW),test_sha256=m.sha(pathlib.Path(__file__).read_bytes()),synthetic_UID_only=True,real_prepare_sign_transport=0,host_calls=0,operational_READY=False)
 with (ROOT/'TRANSPORT_TEST_RESULT.json').open('x') as out:out.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
