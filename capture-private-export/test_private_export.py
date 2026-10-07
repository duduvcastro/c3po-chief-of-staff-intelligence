"""Offline confidentiality interface guards; fake age process, no crypto/child/host."""
import hashlib,json,os,pathlib,subprocess,sys,tempfile,types,unittest
sys.dont_write_bytecode=True
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import private_export as m
COUNT=0
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=str(pathlib.Path(tempfile.gettempdir()).resolve()))
  self.root=pathlib.Path(self.tmp.name);self.root.chmod(0o700)
  self.inp=self.root/'input';self.inp.write_bytes(b'private fixture');self.inp.chmod(0o600)
  self.exe=self.root/'age';self.exe.write_bytes(b'fake executable never run');self.exe.chmod(0o700)
  self.pin=m.sha(self.exe.read_bytes());self.out=self.root/'output';self.calls=[]
 def tearDown(self):self.tmp.cleanup()
 def fake(self,argv,**kw):
  self.calls.append((argv,kw));kw['stdout'].write(b'age-encryption.org/v1\nsynthetic ciphertext only')
  return types.SimpleNamespace(returncode=0)
 def call(self,runner=None):
  global COUNT;COUNT+=1
  return m.encrypt(str(self.inp),str(self.exe),self.pin,str(self.out),runner or self.fake)
 def refused(self):
  with self.assertRaises((m.Refused,OSError)):self.call()
  self.assertEqual(self.calls,[])
 def test_fixed_recipient_private_output_no_secret_argv(self):
  got=self.call();argv,kw=self.calls[0]
  self.assertEqual(argv,[str(self.exe),'--encrypt','--recipient',m.RECIPIENT])
  self.assertEqual(kw['input'],b'private fixture');self.assertIs(kw['stderr'],subprocess.DEVNULL)
  self.assertEqual(kw['timeout'],30);self.assertFalse(kw['check']);self.assertEqual(self.out.stat().st_mode&0o777,0o600)
  self.assertEqual(got['ciphertext_sha256'],m.sha(self.out.read_bytes()));self.assertFalse(got['operational_READY'])
  self.assertNotIn('private fixture',json.dumps(got))
 def test_input_world_readable_refused(self):self.inp.chmod(0o644);self.refused()
 def test_input_symlink_refused(self):
  original=self.inp;self.inp=self.root/'link';self.inp.symlink_to(original);self.refused()
 def test_input_hardlink_refused(self):os.link(self.inp,self.root/'other');self.refused()
 def test_wrong_executable_pin_refused(self):self.pin='a'*64;self.refused()
 def test_writable_executable_refused(self):self.exe.chmod(0o777);self.refused()
 def test_output_existing_refused(self):self.out.write_bytes(b'preserved');self.refused();self.assertEqual(self.out.read_bytes(),b'preserved')
 def test_output_parent_public_refused(self):self.root.chmod(0o755);self.refused()
 def test_cipher_failure_no_retry(self):
  def bad(argv,**kw):self.calls.append(argv);return types.SimpleNamespace(returncode=1)
  with self.assertRaises(m.Refused):self.call(bad)
  self.assertEqual(len(self.calls),1);self.assertTrue(self.out.exists())
  with self.assertRaises(m.Refused):self.call(bad)
  self.assertEqual(len(self.calls),1)
 def test_replaced_output_refused(self):
  def replace(argv,**kw):
   result=self.fake(argv,**kw);self.out.unlink();self.out.write_bytes(b'age-encryption.org/v1\nreplacement');return result
  with self.assertRaises(m.Refused):self.call(replace)
 def test_bad_cipher_format_refused(self):
  def wrong(argv,**kw):self.calls.append(argv);kw['stdout'].write(b'not age');return types.SimpleNamespace(returncode=0)
  with self.assertRaises(m.Refused):self.call(wrong)
 def test_changed_executable_refused(self):
  def changed(argv,**kw):result=self.fake(argv,**kw);self.exe.write_bytes(b'changed');return result
  with self.assertRaises(m.Refused):self.call(changed)
if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):
   denied.append(event);raise RuntimeError('OFFLINE_NO_NETWORK_OR_CHILD')
 sys.addaudithook(audit)
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 root=pathlib.Path(__file__).resolve().parent
 report=dict(schema='CAPTURE_PRIVATE_EXPORT_SYNTHETIC_TEST_V1',methods=result.testsRun,scenarios=COUNT,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),source_sha256=m.sha((root/'private_export.py').read_bytes()),test_sha256=m.sha(pathlib.Path(__file__).read_bytes()),actual_crypto_processes=0,actual_network_calls=0,actual_private_exports=0,host_calls=0,operational_READY=False)
 with (root/'EXPORT_TEST_RESULT.json').open('x') as out:out.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
