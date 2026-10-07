"""Synthetic constructor and delayed once dispatcher proof. No API, SSH or host."""
import copy,datetime as dt,json,os,pathlib,sys,tempfile,types,unittest
sys.dont_write_bytecode=True;sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import constructor as c
COUNT=0
def fixture(base='/synthetic'):
 p=dict(session='2026-10-08',run_id='37612765727',run_attempt=1,nonce='b'*32,target='fixture@fixture.invalid',ssh_key=dict(path=base+'/key',sha256=c.sha(b'fixture-key')),known_hosts=dict(path=base+'/hosts',sha256=c.sha(b'fixture-known-hosts')),claim_root_identity=dict(path=base+'/claims',device=1,inode=2),bound_directory=base+'/bound')
 pins=dict(c.PINS,templates=c.TEMPLATE_PINS,constructor=c.sha((c.ROOT/'constructor.py').read_bytes()),owner_response=c.HELPER_PIN)
 a=dict(schema='CAPTURE_TRANSPORT_DATED_AUTHORITY_V1',status='SIGNED',owner='DUDU',answer='Assino',channel='AskUserQuestion via Fable',operation=c.OP,session='2026-10-08',outside_Mac=True,single_use=True,retry=False,scope='TRANSPORT_CHALLENGE_ONLY_NO_HOST_FILE_ACCESS_NO_BOOT_REPEAT',program_pins=pins,signed_at_utc='2026-10-07T14:00:00Z',source_decision_body_sha256='c'*64,document_sha256='d'*64)
 r=dict(schema='CAPTURE_TRANSPORT_LINUX_RUNTIME_APPROVAL_V1',verdict='PASS_PHYSICAL_RUNTIME',run_id=p['run_id'],run_attempt=1,platform='linux',program_pins=pins,remote_command='sudo -n /usr/bin/python3 -I -B -',measurement_sha256='e'*64,review_body_sha256='f'*64,python_executable_sha256='a'*64,ssh_executable_sha256='b'*64,measured_at_utc='2026-10-08T11:45:00Z',reviewed_at_utc='2026-10-08T11:46:00Z')
 return p,c.canonical(a),c.canonical(r)
def sheet(args):
 global COUNT;COUNT+=1
 return c.canonical(c.make_sheet(*args,'2026-10-08T11:47:00Z'))
def packet(raw):
 s=c.strict(raw);body,asked=c.question(raw);url='https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence'
 q=dict(id=100,url=url+'/issues/comments/100',issue_url=url+'/issues/429',created_at='2026-10-08T11:49:00Z',updated_at='2026-10-08T11:49:00Z',body=body.decode())
 a={k:s['parameters'][k] for k in ('session','run_id','run_attempt','nonce')};a.update(schema='CAPTURE_OWNER_ANSWER_V2',answer='Assino',sheet_sha256=c.sha(raw),question_body_sha256=c.sha(body),asked_question_sha256=c.sha(asked),asked_at_utc='2026-10-08T11:50:00Z',answered_at_utc='2026-10-08T11:50:30Z',recorded_by='FABLE',source_channel='AskUserQuestion via Fable')
 comment=dict(id=101,url=url+'/issues/comments/101',issue_url=url+'/issues/429',created_at='2026-10-08T11:50:40Z',updated_at='2026-10-08T11:50:40Z',body=json.dumps(a),user=dict(id=313137248,login='duduvcastro',type='User'),author_association='OWNER',performed_via_github_app=None)
 return dict(question_first=q,question_readback=copy.deepcopy(q),first=comment,readback=copy.deepcopy(comment),observed_at='2026-10-08T11:50:41Z')
def approve(raw,p,a,r):
 global COUNT;COUNT+=1
 return c.approve_sheet(raw,c.canonical(p),a,r)
class Tests(unittest.TestCase):
 def test_unsigned_own_sheet_has_no_go(self):
  raw=sheet(fixture());s=c.strict(raw);self.assertFalse(s['operational_READY']);self.assertNotIn('owner_evidence',s['request']);body,asked=c.question(raw)
  self.assertNotIn('fixture.invalid',body.decode());self.assertIn(b'fixture.invalid',asked);self.assertEqual(s['request']['not_before'],c.START)
 def test_exact_fable_record_assembles_inner_authenticated_bytes_only(self):
  p,a,r=fixture();raw=sheet((p,a,r));files=approve(raw,packet(raw),a,r);self.assertEqual(set(files),{'REQUEST.BOUND.json','AUTHORITY.SIGNED.json','GO.SIGNED.json','FINAL_PAYLOAD.BOUND.py','OWNER_API.READBACK.json','capture_transport_challenge.py','DISPATCH_AUTHORIZATION.json'})
  sources,m,l,h=c.runtime();pins=m.Pins(payload=c.PINS['capture_transport_challenge.py'],request=c.sha(files['REQUEST.BOUND.json']),authority=c.sha(files['AUTHORITY.SIGNED.json']),go=c.sha(files['GO.SIGNED.json']))
  plan,gate=m.authenticate(files['REQUEST.BOUND.json'],files['AUTHORITY.SIGNED.json'],files['GO.SIGNED.json'],pins=pins,payload_bytes=sources['capture_transport_challenge.py'],clock=lambda:dt.datetime(2026,10,8,11,55,tzinfo=dt.timezone.utc),monotonic=lambda:1.,executor_uid=lambda:0)
  self.assertEqual(plan['nonce'],p['nonce']);self.assertIn('REGISTRO_PELA_FABLE',c.strict(files['AUTHORITY.SIGNED.json'])['owner_evidence'])
 def test_wrong_date_retry_and_nonce_refused(self):
  for key,val in [('session','2026-10-09'),('run_attempt',2),('run_attempt',True),('nonce','short')]:
   p,a,r=fixture();p[key]=val
   with self.assertRaises(ValueError):sheet((p,a,r))
 def test_missing_outside_mac_authority_or_wrong_program_refused(self):
  for key,val in [('outside_Mac',False),('scope','BOOT_REPEAT'),('status','DRAFT'),('program_pins',{})]:
   p,a,r=fixture();v=c.strict(a);v[key]=val
   with self.assertRaises(ValueError):sheet((p,c.canonical(v),r))
 def test_different_job_or_unreviewed_runtime_refused(self):
  for key,val in [('run_id','37612765728'),('verdict','MEASURED_NOT_REVIEWED'),('platform','darwin'),('run_attempt',2)]:
   p,a,r=fixture();v=c.strict(r);v[key]=val
   with self.assertRaises(ValueError):sheet((p,a,c.canonical(v)))
 def test_sheet_changed_after_question_refused(self):
  p,a,r=fixture();raw=sheet((p,a,r));v=c.strict(raw);v['command_sha256']='a'*64
  with self.assertRaises(ValueError):approve(c.canonical(v),packet(raw),a,r)
 def test_wrong_answer_context_and_question_refused(self):
  p,a,r=fixture();raw=sheet((p,a,r))
  for key,val in [('nonce','d'*32),('sheet_sha256','e'*64),('answer','Sim')]:
   pk=packet(raw);ans=json.loads(pk['first']['body']);ans[key]=val;pk['first']['body']=pk['readback']['body']=json.dumps(ans)
   with self.assertRaises(ValueError):approve(raw,pk,a,r)
  pk=packet(raw);pk['question_readback']['body']='changed'
  with self.assertRaises(ValueError):approve(raw,pk,a,r)
 def test_late_challenge_response_refused(self):
  p,a,r=fixture();raw=sheet((p,a,r));pk=packet(raw);ans=json.loads(pk['first']['body']);ans['answered_at_utc']='2026-10-08T11:52:01Z'
  pk['first']['body']=pk['readback']['body']=json.dumps(ans);pk['first']['created_at']=pk['first']['updated_at']=pk['readback']['created_at']=pk['readback']['updated_at']='2026-10-08T11:52:02Z';pk['observed_at']='2026-10-08T11:52:03Z'
  with self.assertRaises(ValueError):approve(raw,pk,a,r)
 def test_actual_process_guard_refuses_synthetic_context(self):
  p,a,r=fixture()
  with self.assertRaises((ValueError,OSError)):c.anchors(p,c.strict(r))
 def test_dispatch_publication_delay_and_single_spawn(self):
  global COUNT
  with tempfile.TemporaryDirectory(dir=str(pathlib.Path(tempfile.gettempdir()).resolve())) as td:
   base=pathlib.Path(td);(base/'bound').mkdir(mode=0o700);(base/'claims').mkdir(mode=0o700)
   for name,blob in [('key',b'fixture-key'),('hosts',b'fixture-known-hosts')]:q=base/name;q.write_bytes(blob);q.chmod(0o600)
   p,a,r=fixture(str(base));st=(base/'claims').stat();p['claim_root_identity'].update(device=st.st_dev,inode=st.st_ino);raw=sheet((p,a,r));files=approve(raw,packet(raw),a,r)
   c.write_all(str(base/'bound'),files);cfg=files['DISPATCH_AUTHORIZATION.json'];config=c.strict(cfg)
   saved={};mods={}
   try:
    for name in ('capture_transport_challenge','launcher_stdin','transport_once','dispatch_once'):
     saved[name]=sys.modules.get(name);m=types.ModuleType(name);m.__file__=str(c.ROOT/'transport_challenge'/(name+'.py'));sys.modules[name]=m;exec(compile((c.ROOT/'transport_challenge'/(name+'.py')).read_bytes(),m.__file__,'exec'),m.__dict__);mods[name]=m
    d=mods['dispatch_once'];calls=[];now=[dt.datetime(2026,10,8,11,52,tzinfo=dt.timezone.utc)]
    def fake(payload,**kw):
     calls.append(payload);kw['authorize'](kw['payload_sha256'],kw['command_sha256']);return dict(status='KNOWN_PARTIAL',attempts=1,command_sha256=kw['command_sha256']),c.canonical(dict(schema='READONLY_HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_RECEIPT_V1',request_sha256=config['request']['sha256'],go_sha256=config['go']['sha256'],payload_sha256=config['source']['sha256'])),b''
    COUNT+=1;result=d.execute(str(base/'bound/DISPATCH_AUTHORIZATION.json'),c.sha(cfg),clock=lambda:now[0],monotonic=lambda:0.,transport=fake);self.assertEqual(result['status'],'AWAITING_PUBLICATION_NO_SPAWN');self.assertEqual(calls,[])
    intent=(base/'claims/challenge-once/intent.json').read_bytes();proof=dict(schema='HOSTOPS02_CAPTURE_TRANSPORT_CHALLENGE_INTENT_PUBLICATION_V1',status='PUBLISHED',owner='DUDU',publication_ref='SYNTHETIC_NO_ACTUAL_ISSUE_COMMENT',published_at='2026-10-08T11:52:10+00:00',intent_sha256=c.sha(intent),go_sha256=config['go']['sha256'],config_sha256=c.sha(cfg));pr=c.canonical(proof);pf=base/'proof';pf.write_bytes(pr);pf.chmod(0o600)
    now[0]=dt.datetime(2026,10,8,11,54,9,tzinfo=dt.timezone.utc);COUNT+=1
    with self.assertRaises(ValueError):d.execute(str(base/'bound/DISPATCH_AUTHORIZATION.json'),c.sha(cfg),phase='resume',publication_path=str(pf),publication_sha256=c.sha(pr),clock=lambda:now[0],monotonic=lambda:0.,transport=fake)
    self.assertFalse((base/'claims/challenge-once/spawn.claim').exists());self.assertEqual(calls,[])
    now[0]=dt.datetime(2026,10,8,11,54,10,tzinfo=dt.timezone.utc);COUNT+=1
    got=d.execute(str(base/'bound/DISPATCH_AUTHORIZATION.json'),c.sha(cfg),phase='resume',publication_path=str(pf),publication_sha256=c.sha(pr),clock=lambda:now[0],monotonic=lambda:0.,transport=fake);self.assertEqual(got['attempts'],1);self.assertEqual(len(calls),1)
    COUNT+=1
    with self.assertRaises(OSError):d.execute(str(base/'bound/DISPATCH_AUTHORIZATION.json'),c.sha(cfg),phase='resume',publication_path=str(pf),publication_sha256=c.sha(pr),clock=lambda:now[0],monotonic=lambda:0.,transport=fake)
    self.assertEqual(len(calls),1)
   finally:
    for name,old in saved.items():
     if old is None:sys.modules.pop(name,None)
     else:sys.modules[name]=old
if __name__=='__main__':
 denied=[]
 def audit(event,args):
  if event.startswith(('socket.','subprocess.')) or event in ('os.system','os.exec','os.posix_spawn','os.fork'):denied.append(event);raise RuntimeError('OFFLINE_NO_NETWORK_CHILD_OR_HOST')
 sys.addaudithook(audit);result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 report=dict(schema='CAPTURE_TRANSPORT_CONSTRUCTOR_SYNTHETIC_PROOF_V1',python=sys.version.split()[0],methods=result.testsRun,scenarios=COUNT,failures=len(result.failures),errors=len(result.errors),audit_denials=len(denied),constructor_sha256=c.sha((c.ROOT/'constructor.py').read_bytes()),dispatcher_sha256=c.PINS['dispatch_once.py'],test_sha256=c.sha(pathlib.Path(__file__).read_bytes()),actual_owner_API_calls=0,actual_SSH_spawns=0,host_calls=0,synthetic_inner_UID_only=True,operational_READY=False)
 with (c.ROOT/'CONSTRUCTOR_TEST_RESULT.json').open('x') as out:out.write(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
