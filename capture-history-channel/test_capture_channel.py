"""Focused new-channel tests. AST extraction: no binder/app imports or REAL calls."""
import ast, copy, hashlib, json, pathlib, re, sys, unittest
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parent
SOURCE=ROOT/'binder/bind/bind_once.py'
TREE=ast.parse(SOURCE.read_bytes())
NAMES={'capture_context_value','capture_request_fields','capture_fable_question','capture_question_body','capture_signature_packet'}
class Refused(ValueError):pass
def need(ok,code):
 if not ok:raise Refused(code)
def strict(raw,code):
 def pairs(items):
  out={}
  for k,v in items:
   need(k not in out,code);out[k]=v
  return out
 try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(Refused(code)))
 except (ValueError,TypeError):raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def read_file(path,maximum,code,**kw):
 raw=path.read_bytes();need(len(raw)<=maximum,code);return raw
NS=dict(need=need,strict_json=strict,Refused=Refused,sha=sha,read_file=read_file,Path=pathlib.Path,re=re,
 canonical=lambda obj:json.dumps(obj,sort_keys=True,separators=(',',':')).encode(),REAL='REAL',
 REAL_CHANNEL='AskUserQuestion via Fable',CAPTURE_REAL_CHANNEL='REGISTRO_PELA_FABLE AskUserQuestion capture/policy candidate',__file__=str(SOURCE),
 CAPTURE_OWNER_CONTEXT_NAME='CAPTURE.GITHUB.CONTEXT.json',CAPTURE_OPS=('policy_read','capture_launch','capture_result','capture_cleanup'),
 CAPTURE_OWNER_RESPONSE_SHA256=sha((SOURCE.parent/'capture_owner_response.py').read_bytes()))
exec(compile(ast.Module(body=[n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in NAMES],type_ignores=[]),str(SOURCE),'exec'),NS)
ISSUE='https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence/issues/429'
URL=ISSUE.rsplit('/issues/',1)[0]+'/issues/comments/'
SCENARIOS=0

def fixture():
 ctx=dict(schema='CAPTURE_GITHUB_CONTEXT_V2',session='2026-10-08',run_id='37612765727',run_attempt=1,nonce='a'*32,k9_operation='capture_launch')
 params=dict(signature_model='PRE',plan=dict(day=ctx['session'],k9_operation=ctx['k9_operation'],slot='PRIMARY'))
 sheet=dict(mode='REAL',signature_model='PRE',request_sha256='b'*64,prepared_at_utc='2026-10-08T11:45:00Z',window=dict(gate_not_before='2026-10-08T13:50:00Z',gate_not_after='2026-10-08T13:59:59Z'))
 state=dict(sheet=sheet,sheet_raw=json.dumps(sheet).encode(),files={'CAPTURE.GITHUB.CONTEXT.json':json.dumps(ctx).encode(),'PARAMETERS.json':json.dumps(params).encode(),'OWNER_QUESTION.txt':b'Pergunta privada exata: Assino somente esta folha.'})
 q=dict(id=100,url=URL+'100',issue_url=ISSUE,created_at='2026-10-08T11:49:00Z',updated_at='2026-10-08T11:49:00Z',body=NS['capture_question_body'](state))
 answer=dict(schema='CAPTURE_OWNER_ANSWER_V2',answer='Assino',session=ctx['session'],run_id=ctx['run_id'],run_attempt=1,nonce=ctx['nonce'],sheet_sha256=sha(state['sheet_raw']),question_body_sha256=sha(q['body'].encode()),asked_question_sha256=sha(NS['capture_fable_question'](state)),asked_at_utc='2026-10-08T11:50:00Z',answered_at_utc='2026-10-08T11:50:00Z',recorded_by='FABLE',source_channel='AskUserQuestion via Fable')
 c=dict(id=101,url=URL+'101',issue_url=ISSUE,created_at='2026-10-08T11:50:00Z',updated_at='2026-10-08T11:50:00Z',body=json.dumps(answer),user=dict(id=313137248,login='duduvcastro',type='User'),author_association='OWNER',performed_via_github_app=None)
 return state,dict(question_first=q,question_readback=copy.deepcopy(q),first=c,readback=copy.deepcopy(c),observed_at='2026-10-08T11:50:01Z')

class Tests(unittest.TestCase):
 def run_packet(self,state,packet):
  global SCENARIOS
  SCENARIOS+=1
  return NS['capture_signature_packet'](state,json.dumps(packet).encode())
 def test_exact_four_scopes(self):
  for op in NS['CAPTURE_OPS']:
   with self.subTest(op=op):
    state,packet=fixture();c=json.loads(state['files']['CAPTURE.GITHUB.CONTEXT.json']);p=json.loads(state['files']['PARAMETERS.json']);c['k9_operation']=p['plan']['k9_operation']=op
    state['files']['CAPTURE.GITHUB.CONTEXT.json']=json.dumps(c).encode();state['files']['PARAMETERS.json']=json.dumps(p).encode()
    for key in ('question_first','question_readback'):packet[key]['body']=NS['capture_question_body'](state)
    answer=json.loads(packet['first']['body']);answer.update(question_body_sha256=sha(packet['question_first']['body'].encode()),asked_question_sha256=sha(NS['capture_fable_question'](state)))
    for key in ('first','readback'):packet[key]['body']=json.dumps(answer)
    result,channel=self.run_packet(state,packet)
    self.assertEqual(result['status'],'MATCHED_FABLE_RECORD_NOT_SIGNED');self.assertFalse(result['is_operational_authority']);self.assertIn('packet-sha256:',channel)
 def test_context_scope_refusals(self):
  for field,value in [('session','2026-10-09'),('k9_operation','commit_launch'),('run_attempt',2),('run_attempt',True),('nonce','short'),('run_id','00123'),('schema','OTHER')]:
   with self.subTest(field=field):
    state,packet=fixture();c=json.loads(state['files']['CAPTURE.GITHUB.CONTEXT.json']);c[field]=value;state['files']['CAPTURE.GITHUB.CONTEXT.json']=json.dumps(c).encode()
    with self.assertRaises(Refused):self.run_packet(state,packet)
  for field,value in [('slot','SPARE'),('day','2026-10-09')]:
   state,packet=fixture();p=json.loads(state['files']['PARAMETERS.json']);p['plan'][field]=value;state['files']['PARAMETERS.json']=json.dumps(p).encode()
   with self.assertRaises(Refused):self.run_packet(state,packet)
 def test_question_refusals(self):
  for field,value in [('id',True),('url',URL+'999'),('issue_url',ISSUE[:-3]+'428'),('body','changed'),('updated_at','2026-10-08T11:49:01Z')]:
   with self.subTest(field=field):
    state,p=fixture()
    for k in ('question_first','question_readback'):p[k][field]=value
    with self.assertRaises(Refused):self.run_packet(state,p)
  state,p=fixture();p['question_readback']['body']='changed'
  with self.assertRaises(Refused):self.run_packet(state,p)
 def test_owner_packet_refusals(self):
  for field,value in [('issue_url',ISSUE[:-3]+'428'),('performed_via_github_app',{}),('author_association','CONTRIBUTOR'),('updated_at','2026-10-08T11:50:02Z'),('user',dict(id=99,login='duduvcastro',type='User'))]:
   with self.subTest(field=field):
    state,p=fixture()
    for k in ('first','readback'):p[k][field]=value
    with self.assertRaises(Refused):self.run_packet(state,p)
  for field,value in [('nonce','c'*32),('sheet_sha256','d'*64),('run_attempt',2),('answer','Sim'),('recorded_by','DUDU_DIRECT'),('source_channel','GitHub direct'),('asked_question_sha256','0'*64),('question_body_sha256','0'*64),('asked_at_utc','2026-10-08T11:51:00Z'),('answered_at_utc','2026-10-08T11:51:00Z'),('schema','CAPTURE_OWNER_ANSWER_V1')]:
   state,p=fixture();body=json.loads(p['first']['body']);body[field]=value
   for k in ('first','readback'):p[k]['body']=json.dumps(body)
   with self.assertRaises(Refused):self.run_packet(state,p)
  state,p=fixture();p['observed_at']='2026-10-08T12:30:01Z'
  with self.assertRaises(Refused):self.run_packet(state,p)
 def test_source_integration_order(self):
  global SCENARIOS
  SCENARIOS+=1
  functions={n.name:n for n in TREE.body if isinstance(n,ast.FunctionDef)}
  sign=ast.unparse(functions['sign']);prepare=ast.unparse(functions['prepare']);signed=ast.unparse(functions['signed_state']);opened=ast.unparse(functions['open_bound'])
  self.assertLess(sign.index('capture_signature_packet('),sign.index("put(state['bound'],"))
  self.assertLess(prepare.index('capture_context_file('),prepare.index("put(out,"))
  self.assertIn('capture_signature_packet(',signed);self.assertIn('CAPTURE_OWNER_CONTEXT_NAME in expected',opened);self.assertIn('signed_names.add(CAPTURE_OWNER_READBACK_NAME)',opened)

if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):
   denied.append(event);raise RuntimeError('OFFLINE_NO_CHILD_OR_NETWORK')
 sys.addaudithook(audit)
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 report=dict(schema='CAPTURE_BINDER_FABLE_RECORD_COMPONENT_TEST_V2',python=sys.version.split()[0],methods=result.testsRun,scenarios=SCENARIOS,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),source_sha256=sha(SOURCE.read_bytes()),test_sha256=sha(pathlib.Path(__file__).read_bytes()),binder_imports=0,real_prepare_calls=0,real_sign_calls=0,host_calls=0,operational_READY=False)
 with (ROOT/'CHANNEL_TEST_RESULT.json').open('x') as out:out.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
