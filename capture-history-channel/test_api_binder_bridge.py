"""New API packet/binder-channel ABI proof, synthetic API only; no REAL operations."""
import copy,datetime as dt,hashlib,json,pathlib,sys,unittest
sys.dont_write_bytecode=True;sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import github_readback as bridge
from test_capture_channel import NS,fixture
class Client:
 def __init__(self,replies):self.replies=replies;self.calls=[]
 def comment(self,cid):self.calls.append(cid);return self.replies.pop(0)
class Tests(unittest.TestCase):
 def test_live_packet_format_matches_capture_binder(self):
  state,p=fixture();q=p['question_first'];context=json.loads(state['files']['CAPTURE.GITHUB.CONTEXT.json'])
  context={k:context[k] for k in ('session','run_id','run_attempt','nonce')}
  context.update(sheet_sha256=NS['sha'](state['sheet_raw']),question_created_at=q['created_at'],question_body_sha256=NS['sha'](q['body'].encode()),asked_question_sha256=NS['sha'](NS['capture_fable_question'](state)),prepared_at_utc=state['sheet']['prepared_at_utc'],not_before='2026-10-08T11:50:00Z',not_after='2026-10-08T12:30:00Z')
  client=Client([q,copy.deepcopy(q),p['first'],p['readback']]);clock=lambda:dt.datetime(2026,10,8,11,50,1,tzinfo=dt.timezone.utc)
  raw,record=bridge.collect(client,100,101,q['body'],context,clock)
  got,channel=NS['capture_signature_packet'](state,raw)
  self.assertEqual(got,record);self.assertIn(bridge.sha(raw),channel);self.assertEqual(client.calls,[100,100,101,101]);self.assertFalse(got['is_operational_authority'])
  changed=copy.deepcopy(state);changed['sheet_raw']=b'changed-sheet'
  with self.assertRaises(ValueError):NS['capture_signature_packet'](changed,raw)
if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):denied.append(event);raise RuntimeError('NO_NETWORK_OR_CHILD')
 sys.addaudithook(audit)
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));root=pathlib.Path(__file__).resolve().parent
 report=dict(schema='CAPTURE_FABLE_RECORD_API_BINDER_ABI_PROOF_V2',methods=result.testsRun,scenarios=2,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),actual_network_calls=0,real_prepare_sign_dispatch=0,operational_READY=False,binder_source_sha256=bridge.sha((root/'binder/bind/bind_once.py').read_bytes()),bridge_sha256=bridge.sha((root/'github_readback.py').read_bytes()))
 with (root/'API_BINDER_TEST_RESULT.json').open('x') as out:out.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
