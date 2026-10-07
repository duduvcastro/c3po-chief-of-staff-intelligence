import copy, datetime as dt, email.message, hashlib, io, json, pathlib, sys, tempfile, unittest, urllib.error
sys.dont_write_bytecode=True
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import github_readback as g
SCENARIOS=0
class Reply:
 def __init__(self,url,raw,status=200,ctype='application/json'):
  self.status=status;self.url=url;self.raw=io.BytesIO(raw);self.headers=email.message.Message();self.headers['Content-Type']=ctype
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def geturl(self):return self.url
 def read(self,n):return self.raw.read(n)
class Opener:
 def __init__(self,response=None,error=None):self.response=response;self.error=error;self.calls=[]
 def open(self,req,timeout):
  self.calls.append((req,timeout))
  if self.error:raise self.error
  return self.response
class Client:
 def __init__(self,replies):self.replies=replies;self.calls=[]
 def comment(self,cid):self.calls.append(cid);return self.replies.pop(0)
def fixture():
 body='public-question-hashes-only';ctx=dict(session='2026-10-08',run_id='37612765727',run_attempt=1,nonce='a'*32,sheet_sha256='b'*64,prepared_at_utc='2026-10-08T11:45:00Z',question_created_at='2026-10-08T11:49:00Z',question_body_sha256=g.sha(body.encode()),asked_question_sha256='c'*64,not_before='2026-10-08T11:50:00Z',not_after='2026-10-08T12:30:00Z')
 issue=g.API.rsplit('/comments/',1)[0]+'/429'
 q=dict(id=100,url=g.API+'100',issue_url=issue,created_at=ctx['question_created_at'],updated_at=ctx['question_created_at'],body=body)
 answer={k:ctx[k] for k in ('session','run_id','run_attempt','nonce','sheet_sha256')};answer.update(schema='CAPTURE_OWNER_ANSWER_V2',answer='Assino',question_body_sha256=ctx['question_body_sha256'],asked_question_sha256=ctx['asked_question_sha256'],asked_at_utc='2026-10-08T11:50:00Z',answered_at_utc='2026-10-08T11:50:00Z',recorded_by='FABLE',source_channel='AskUserQuestion via Fable')
 a=dict(id=101,url=g.API+'101',issue_url=issue,created_at='2026-10-08T11:50:00Z',updated_at='2026-10-08T11:50:00Z',body=json.dumps(answer),user=dict(id=313137248,login='duduvcastro',type='User'),author_association='OWNER',performed_via_github_app=None)
 return body,ctx,Client([q,copy.deepcopy(q),a,copy.deepcopy(a)])
NOW=lambda:dt.datetime(2026,10,8,11,50,1,tzinfo=dt.timezone.utc)
class Tests(unittest.TestCase):
 def case(self):
  global SCENARIOS;SCENARIOS+=1
 def test_get_only_fixed_authenticated_endpoint(self):
  self.case();cid=101;url=g.API+str(cid);op=Opener(Reply(url,json.dumps(dict(id=cid,url=url)).encode()));out=g.GitHubGET('fake-test-token',op).comment(cid)
  self.assertEqual(out['id'],cid);self.assertEqual(len(op.calls),1);req,timeout=op.calls[0]
  self.assertEqual(req.method,'GET');self.assertEqual(req.full_url,url);self.assertEqual(timeout,20);self.assertEqual(req.get_header('Authorization'),'Bearer fake-test-token')
 def test_get_refusals_no_retry(self):
  url=g.API+'101'
  cases=[Reply(url,b'{}',500),Reply(url,b'{}',200,'text/html'),Reply('https://example.invalid',b'{}'),Reply(url,b'x'*(g.LIMIT+1)),Reply(url,b'{"id":101,"id":101}'),Reply(url,b'{}'),Reply(url,json.dumps(dict(id=True,url=url)).encode())]
  for reply in cases:
   self.case();op=Opener(reply)
   with self.assertRaises(g.Refused):g.GitHubGET('fake-test-token',op).comment(101)
   self.assertEqual(len(op.calls),1)
  self.case();op=Opener(error=urllib.error.URLError('test-failure'))
  with self.assertRaises(g.Refused):g.GitHubGET('fake-test-token',op).comment(101)
  self.assertEqual(len(op.calls),1)
 def test_redirect_refused(self):
  self.case()
  with self.assertRaises(g.Refused):g.NoRedirect().redirect_request(None,None,302,'',{},'https://example.invalid')
 def test_exact_four_gets_not_signature(self):
  self.case();body,ctx,c=fixture();raw,result=g.collect(c,100,101,body,ctx,NOW)
  self.assertEqual(c.calls,[100,100,101,101]);self.assertFalse(result['is_operational_authority']);self.assertEqual(json.loads(raw)['observed_at'],'2026-10-08T11:50:01Z')
 def test_changes_and_deadline_refused(self):
  for index,key,value in [(1,'body','changed'),(1,'updated_at','2026-10-08T11:49:01Z'),(3,'body','changed'),(2,'performed_via_github_app',{})]:
   self.case();body,ctx,c=fixture();c.replies[index][key]=value
   with self.assertRaises(g.Refused):g.collect(c,100,101,body,ctx,NOW)
  self.case();body,ctx,c=fixture()
  with self.assertRaises(g.Refused):g.collect(c,100,101,body,ctx,lambda:dt.datetime(2026,10,8,12,30,1,tzinfo=dt.timezone.utc))
 def test_private_input_guards(self):
  self.case()
  with tempfile.TemporaryDirectory(prefix='capture-input-test-',dir=str(pathlib.Path(tempfile.gettempdir()).resolve())) as td:
   p=pathlib.Path(td)/'input.json';p.write_bytes(b'fixture');p.chmod(0o600)
   self.assertEqual(g.private_read(str(p),100),b'fixture')
   self.case();p.chmod(0o644)
   with self.assertRaises(g.Refused):g.private_read(str(p),100)
   self.case();p.chmod(0o600);link=pathlib.Path(td)/'link.json';link.symlink_to(p)
   with self.assertRaises(g.Refused):g.private_read(str(link),100)
   self.case()
   with self.assertRaises(g.Refused):g.private_read(str(p),2)
 def test_output_exclusive_private(self):
  self.case()
  with tempfile.TemporaryDirectory(prefix='capture-readback-test-',dir=str(pathlib.Path(tempfile.gettempdir()).resolve())) as td:
   p=pathlib.Path(td)/'packet.json';result=g.store_packet(str(p),b'test-private-fixture');self.assertEqual(p.stat().st_mode&0o777,0o600);self.assertFalse(result['operational_READY'])
   with self.assertRaises(g.Refused):g.store_packet(str(p),b'changed')
if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):
   denied.append(event);raise RuntimeError('OFFLINE_NO_NETWORK_OR_CHILD')
 sys.addaudithook(audit)
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 root=pathlib.Path(__file__).resolve().parent
 report=dict(schema='CAPTURE_FABLE_API_BRIDGE_COMPONENT_TEST_V2',python=sys.version.split()[0],methods=result.testsRun,scenarios=SCENARIOS,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),source_sha256=g.sha((root/'github_readback.py').read_bytes()),test_sha256=g.sha(pathlib.Path(__file__).read_bytes()),actual_network_calls=0,actual_signatures=0,host_calls=0,operational_READY=False)
 with (root/'BRIDGE_TEST_RESULT.json').open('x') as out:out.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
