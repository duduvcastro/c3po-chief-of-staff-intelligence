"""New historical-evidence scope regression, AST-only, no real signatures/host."""
import ast,copy,hashlib,json,pathlib,re,sys,unittest
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parent;SOURCE=ROOT/'binder/bind/bind_once.py';raw=SOURCE.read_bytes();tree=ast.parse(raw)
class Refused(ValueError):pass
def need(ok,code):
 if not ok:raise Refused(code)
legacy={'c5730380bae38027be58f1b34c49eca072611d03d1ebc2837f2604a0ee2cf3d2','600475be7a4a0438dc8e54327b538ca5a274a260f478845791f341e4eccb7da0','bf9cd86cc176e2bfe0ef80470a930741b00bf9333989d0b6cc7b8c296cf77a33'}
NS=dict(REAL='REAL',CAPTURE_OWNER_CONTEXT_NAME='CAPTURE.GITHUB.CONTEXT.json',HISTORICAL_EVIDENCE_BINDERS=frozenset(legacy))
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='capture_packet_required'],type_ignores=[]),str(SOURCE),'exec'),NS)
SCENARIOS=0
class Tests(unittest.TestCase):
 def check(self,sheet,wanted):
  global SCENARIOS;SCENARIOS+=1;self.assertIs(NS['capture_packet_required'](sheet),wanted)
 def test_only_three_exact_historical_fingerprints_without_context(self):
  for p in legacy:self.check(dict(mode='REAL',binder=dict(binder_sha256=p),files_sha256={}),False)
 def test_new_unknown_or_missing_fingerprint_requires_api(self):
  for p in ('a'*64,None,''):
   self.check(dict(mode='REAL',binder=dict(binder_sha256=p),files_sha256={}),True)
  self.check(dict(mode='REAL',files_sha256={}),True)
 def test_context_always_requires_api_even_historical_fingerprint(self):
  for p in legacy:self.check(dict(mode='REAL',binder=dict(binder_sha256=p),files_sha256={'CAPTURE.GITHUB.CONTEXT.json':'a'*64}),True)
 def test_rehearsal_not_promoted(self):self.check(dict(mode='REHEARSAL',files_sha256={}),False)
 def test_new_sign_cannot_use_historical_reader_to_bypass_api(self):
  global SCENARIOS;SCENARIOS+=1
  funcs={n.name:ast.unparse(n) for n in tree.body if isinstance(n,ast.FunctionDef)}
  sign=funcs['sign'];self.assertLess(sign.index('BINDER_CHANGED_SINCE_PREPARE'),sign.index('CAPTURE_OWNER_API_PROOF_REQUIRED'))
  self.assertIn("if sheet['mode'] == REAL:",sign);self.assertNotIn('capture_packet_required',sign)
  self.assertIn('capture_context_file(github_context_path, params)',funcs['prepare'])
  self.assertIn('BOUND_SET_RELOCATED_OR_CLAIM_ROOT_CHANGED',funcs['claim_root_state']);self.assertIn('BINDER_CHANGED_SINCE_PREPARE',funcs['check'])
 def test_historical_signed_state_keeps_original_channel_and_new_state_packet(self):
  global SCENARIOS;SCENARIOS+=1
  funcs={n.name:ast.unparse(n) for n in tree.body if isinstance(n,ast.FunctionDef)}
  self.assertIn('capture_packet_required(sheet)',funcs['signed_state']);self.assertIn('HISTORICAL_EVIDENCE_BINDER_NOT_PINNED',funcs['signed_state'])
  self.assertIn('REAL_OWNER, REAL_ANSWER, REAL_CHANNEL',funcs['signed_state']);self.assertIn('capture_signature_packet',funcs['signed_state'])
if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):denied.append(event);raise RuntimeError('OFFLINE_NO_NETWORK_CHILD_HOST')
 sys.addaudithook(audit);result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 report=dict(schema='CAPTURE_HISTORICAL_CHANNEL_SCOPE_REGRESSION_V1',methods=result.testsRun,scenarios=SCENARIOS,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),source_sha256=hashlib.sha256(raw).hexdigest(),test_sha256=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),real_prepare_sign_dispatch=0,host_calls=0,operational_READY=False)
 with (ROOT/'HISTORY_SCOPE_TEST_RESULT.json').open('x') as f:f.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
