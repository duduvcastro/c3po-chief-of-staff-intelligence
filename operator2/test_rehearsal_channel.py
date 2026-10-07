"""New rehearsal isolation and operator CLI proofs. No API, encryption or job launch."""
import copy,hashlib,json,os,pathlib,sys,tempfile,types,unittest
HOME=pathlib.Path(__file__).resolve().parent

def load(n):
 p=HOME/(n+'.py');m=types.ModuleType('test_'+n);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
r=load('rehearsal_channel');m=r.m;f=r.f
CTX=dict(session='2026-10-07',run_id='12345678901',run_attempt=1,nonce='e'*32)
def public():
 v=r.public_body('EPHEMERAL_RECIPIENT',CTX,dict(recipient='age1'+'q'*58,status='AWAITING_SYNTHETIC_INPUTS'));c=f.comment(v);c['created_at']=c['updated_at']='2026-10-07T17:20:00Z';run=dict(id=int(CTX['run_id']),run_attempt=1,event='push',head_branch='ops/capture-operator2-rehearsal-20261007',path='.github/workflows/operator2-rehearsal.yml',status='in_progress',repository=dict(full_name='duduvcastro/c3po-chief-of-staff-intelligence'),head_sha='f'*40);return c,run
class Tests(unittest.TestCase):
 def context(self):
  c,run=public();return m.canonical(r.context_record(c,copy.deepcopy(c),run))
 def comment(self,v):
  c=f.comment(v);c.update(user=dict(id=313137248,login='duduvcastro',type='User'),author_association='OWNER',performed_via_github_app=None);return c
 def test_namespace_cannot_be_operational_context(self):
  with self.assertRaises(m.Refused):m.context_file(self.context())
 def test_synthetic_context_requires_own_bot_and_run(self):
  c,run=public();c['user']['id']=1
  with self.assertRaises(m.Refused):r.context_record(c,c,run)
  c,run=public();run['run_attempt']=2
  with self.assertRaises(m.Refused):r.context_record(c,c,run)
 def test_two_typed_controls_roundtrip_without_operational_schema(self):
  b=f.fake_cipher();blob=f.blob(b)
  for kind in ('PRIVATE_INPUTS','NIGHT_GATES'):
   v=r.make_control(self.context(),kind,b,blob,b'SYNTHETIC_MANIFEST',b,blob);got=r.accept_control(self.comment(v),CTX,kind);self.assertEqual(got['sequence'],1);self.assertNotEqual(got['schema'],'CAPTURE_JOB_CONTROL_V1')
 def test_cross_job_edited_duplicate_or_nonowner_control_refused(self):
  b=f.fake_cipher();v=r.make_control(self.context(),'NIGHT_GATES',b,f.blob(b),b'MANIFEST')
  for change in ('nonce','edit','account','extra'):
   q=self.comment(v)
   if change=='nonce':x=m.strict(q['body']);x['nonce']='d'*32;q['body']=m.canonical(x).decode()
   elif change=='edit':q['updated_at']='2026-10-07T17:30:00Z'
   elif change=='account':q['user']['id']=1
   else:x=m.strict(q['body']);x['extra']='bad';q['body']=m.canonical(x).decode()
   with self.assertRaises(m.Refused):r.accept_control(q,CTX,'NIGHT_GATES')
 def test_fixed_harmless_fixture_builder_deterministic(self):
  with tempfile.TemporaryDirectory(dir=pathlib.Path(tempfile.gettempdir()).resolve()) as home:
   p=pathlib.Path(home);a=r.fixtures(p/'a');b=r.fixtures(p/'b')
   for x in a.iterdir():self.assertEqual(x.read_bytes(),(b/x.name).read_bytes())
   pins=m.strict((a/'FIXTURE_PINS.public.json').read_bytes());self.assertFalse(pins['operational_READY']);self.assertEqual(pins['input_sha256'],m.sha((a/'INPUTS.fixture.tar').read_bytes()))
 def test_production_operator_cli_new_command_dispatch_and_exclusive_outputs(self):
  op=load('operator_records');old=sys.argv
  with tempfile.TemporaryDirectory(dir=pathlib.Path(tempfile.gettempdir()).resolve()) as home:
   p=pathlib.Path(home);m.put(p/'cipher.age',f.fake_cipher());sys.argv=['operator_records.py','blob-requests','--cipher',str(p/'cipher.age'),'--out',str(p/'output')]
   try:op.main()
   finally:sys.argv=old
   self.assertEqual(m.strict((p/'output/BLOB1.request.json').read_bytes())['encoding'],'base64')
 def test_rehearsal_cli_context_and_control(self):
  old=sys.argv
  with tempfile.TemporaryDirectory(dir=pathlib.Path(tempfile.gettempdir()).resolve()) as home:
   p=pathlib.Path(home);c,run=public()
   for n,v in [('c1',c),('c2',c),('run',run)]:m.put(p/n,m.canonical(v))
   sys.argv=['rehearsal_channel.py','context','--public-readback1',str(p/'c1'),'--public-readback2',str(p/'c2'),'--run-readback',str(p/'run'),'--out',str(p/'context')]
   try:r.main()
   finally:sys.argv=old
   b=f.fake_cipher();m.put(p/'cipher',b);m.put(p/'blob',m.canonical(f.blob(b)));m.put(p/'manifest',b'SYNTHETIC_MANIFEST');sys.argv=['rehearsal_channel.py','control','--kind','NIGHT_GATES','--context',str(p/'context'),'--cipher',str(p/'cipher'),'--blob-readback',str(p/'blob'),'--manifest',str(p/'manifest'),'--out',str(p/'control')]
   try:r.main()
   finally:sys.argv=old
   v=m.strict(m.strict((p/'control').read_bytes())['body']);self.assertEqual(v['kind'],'NIGHT_GATES');self.assertEqual(v['session'],'2026-10-07')
if __name__=='__main__':
 def audit(e,args):
  if e.startswith(('socket.','subprocess.')) or e in ('os.system','os.exec','os.fork','os.posix_spawn'):raise RuntimeError('LOCAL_REHEARSAL_PROOF_NO_NETWORK_CHILD_HOST')
 sys.addaudithook(audit);result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));v=dict(schema='OPERATOR2_REHEARSAL_LOCAL_PROOF_V1',methods=result.testsRun,failures=len(result.failures),errors=len(result.errors),network=0,children=0,host=0,operational_READY=False,source_sha256=m.sha((HOME/'rehearsal_channel.py').read_bytes()),test_sha256=m.sha(pathlib.Path(__file__).read_bytes()));(HOME/'REHEARSAL_RESULT.public.json').write_bytes(m.canonical(v));raise SystemExit(0 if result.wasSuccessful() else 1)
