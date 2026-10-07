"""Focused new producer/receiver proofs; all job/owner/receipt records are fixtures."""
import copy,datetime as dt,hashlib,json,os,pathlib,sys,tempfile,types,unittest
HOME=pathlib.Path(__file__).resolve().parent

def load(name,p=None):
 p=p or HOME/(name+'.py');m=types.ModuleType('proof_'+name);m.__file__=str(p);sys.modules[m.__name__]=m;exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
m=load('capsule_data');f=load('synthetic_fixtures');night=load('night',HOME/'reference/night_bundle.py');channel=load('channel',HOME/'reference/job_channel.py')
NOW=m.instant('2026-10-08T11:47:00Z')
class Tests(unittest.TestCase):
 def ep(self):return f.ephemeral_fixtures()
 def test_real_bot_format_source_tree_and_context(self):
  c,r,cm,t,a=self.ep();v=m.ephemeral(c,copy.deepcopy(c),r,cm,t,a,NOW);self.assertEqual(v['run_id'],f.CTX['run_id']);self.assertEqual(v['source_layout_sha256'],m.LAYOUT)
 def test_commit_and_tree_must_be_real_linked_api_records(self):
  c,r,cm,t,a=self.ep();self.assertNotEqual(cm['sha'],t['sha']);m.ephemeral(c,c,r,cm,t,a,NOW)
  for record,key,val in [('commit','sha','f'*40),('commit','url',m.ROOT+'/git/commits/'+('f'*40)),('tree','sha',r['head_sha']),('tree','truncated',True)]:
   c,r,cm,t,a=self.ep();target=cm if record=='commit' else t;target[key]=val
   with self.assertRaises(m.Refused):m.ephemeral(c,c,r,cm,t,a,NOW)
 def test_bot_spoof_and_app_refused(self):
  for login,uid,app in [('duduvcastro',313137248,None),('github-actions[bot]',m.BOT_ID,{'slug':'evil'})]:
   c,r,cm,t,a=self.ep();c['user']['login']=login;c['user']['id']=uid;c['performed_via_github_app']=app
   with self.assertRaises(m.Refused):m.ephemeral(c,c,r,cm,t,a,NOW)
 def test_edited_and_changed_ephemeral_refused(self):
  c,r,cm,t,a=self.ep();d=copy.deepcopy(c);d['body']+=' '
  with self.assertRaises(m.Refused):m.ephemeral(c,d,r,cm,t,a,NOW)
  c['updated_at']='2026-10-08T11:47:00Z'
  with self.assertRaises(m.Refused):m.ephemeral(c,c,r,cm,t,a,NOW)
 def test_second_attempt_wrong_run_and_other_branch_refused(self):
  for key,val in [('run_attempt',2),('id',2),('head_branch','main'),('path','.github/workflows/other.yml'),('status','completed')]:
   c,r,cm,t,a=self.ep();r[key]=val
   with self.assertRaises(m.Refused):m.ephemeral(c,c,r,cm,t,a,NOW)
 def test_altered_source_or_authority_refused_before_private_input(self):
  c,r,cm,t,a=self.ep();t['tree'][0]['sha']='f'*40
  with self.assertRaises(m.Refused):m.ephemeral(c,c,r,cm,t,a,NOW)
  c,r,cm,t,a=self.ep()
  with self.assertRaises(m.Refused):m.ephemeral(c,c,r,cm,t,a+b' ',NOW)
 def test_multiple_active_workflows_refused(self):
  c,r,cm,t,a=self.ep();t['tree'].append(dict(type='blob',path='.github/workflows/other.yml',sha='f'*40))
  with self.assertRaises(m.Refused):m.ephemeral(c,c,r,cm,t,a,NOW)
 def test_late_ephemeral_refused(self):
  c,r,cm,t,a=self.ep()
  with self.assertRaises(m.Refused):m.ephemeral(c,c,r,cm,t,a,m.instant('2026-10-08T11:50:01Z'))
 def test_plaintext_cannot_be_blob_request(self):
  with self.assertRaises(m.Refused):m.blob_request(b'PRIVATE PLAINTEXT')
 def test_blob_request_and_exact_git_readback(self):
  raw=f.fake_cipher();req=m.strict(m.blob_request(raw));self.assertEqual(req['encoding'],'base64');self.assertEqual(m.blob_readback(raw,f.blob(raw)),(m.gitsha(raw),m.sha(raw)))
 def test_wrong_blob_digest_or_bytes_refused(self):
  raw=f.fake_cipher();b=f.blob(raw);b['sha']='f'*40
  with self.assertRaises(m.Refused):m.blob_readback(raw,b)
  b=f.blob(raw);b['content']='eA=='
  with self.assertRaises(m.Refused):m.blob_readback(raw,b)
 def private(self,archive=b'SYNTHETIC INPUT TAR',inventory=b'SYNTHETIC INVENTORY',now=NOW):
  old=(m.INPUT_TAR,m.INVENTORY);m.INPUT_TAR=m.sha(b'SYNTHETIC INPUT TAR');m.INVENTORY=m.sha(b'SYNTHETIC INVENTORY');a=f.fake_cipher(b'tar');b=f.fake_cipher(b'inventory')
  try:return m.private_inputs(f.context(),archive,inventory,a,b,f.blob(a),f.blob(b),now)
  finally:m.INPUT_TAR,m.INVENTORY=old
 def owner_comment(self,body):
  c=f.comment(body);c.update(user=dict(id=313137248,login='duduvcastro',type='User'),author_association='OWNER',performed_via_github_app=None);return c
 def test_private_inputs_exact_control_accepted_by_frozen_receiver(self):
  v=self.private();got=channel.control(self.owner_comment(v),f.CTX,'PRIVATE_INPUTS',1);self.assertEqual(got['sequence'],1);self.assertIn('manifest_blob_sha',got)
 def test_private_changed_inputs_and_deadline_refused(self):
  with self.assertRaises(m.Refused):self.private(archive=b'changed')
  with self.assertRaises(m.Refused):self.private(now=m.instant('2026-10-08T11:50:01Z'))
 def test_cross_job_invalid_nonce_context_refused(self):
  v=m.strict(f.context());v['nonce']='bad'
  with self.assertRaises(m.Refused):m.context_file(m.canonical(v))
 def capsule(self,slot='PRIMARY',mutate=None):
  with tempfile.TemporaryDirectory(dir=pathlib.Path(tempfile.gettempdir()).resolve()) as home:
   p=pathlib.Path(home);a=f.rows('commit_result',slot);b=f.rows('publish_launch',slot)
   if mutate:mutate(a,b)
   f.write_bound(p/'commit',a);f.write_bound(p/'publish',b);return m.night_capsule(p/'commit',p/'publish',slot,m.instant('2026-10-08T00:00:00Z'))
 def test_primary_and_spare_builder_to_frozen_importer(self):
  for slot in ('PRIMARY','SPARE'):
   raw,manifest,report=self.capsule(slot);v,rows=night.inspect(raw,m.sha(manifest));self.assertEqual(v['slot'],slot);self.assertEqual(len(rows),report['files']);self.assertFalse(report['operational_READY'])
 def test_finished_original_bytes_preserved_without_rewrite(self):
  raw,manifest,_=self.capsule();_,rows=night.inspect(raw,m.sha(manifest))
  for op in m.OPS:
   self.assertEqual({n[len(op+'/bound/'):]:b for n,b in rows.items() if n.startswith(op+'/bound/')},f.rows(op))
 def test_mixed_branch_host_boot_refused(self):
  for change in ['slot','host','boot']:
   a=f.rows('commit_result');b=f.rows('publish_launch',slot='SPARE' if change=='slot' else 'PRIMARY',host='f'*64 if change=='host' else 'a'*64,boot='f'*64 if change=='boot' else 'b'*64)
   with self.assertRaises(m.Refused):
    with tempfile.TemporaryDirectory(dir=pathlib.Path(tempfile.gettempdir()).resolve()) as home:m.night_capsule(f.write_bound(pathlib.Path(home)/'a',a),f.write_bound(pathlib.Path(home)/'b',b),'PRIMARY',m.instant('2026-10-08T00:00:00Z'))
 def test_partial_result_refused(self):
  def change(a,b):
   key=next(n for n in a if n.endswith('/exit.json'));v=m.strict(a[key]);v['status']='KNOWN_PARTIAL';a[key]=m.canonical(v)
  with self.assertRaises(m.Refused):self.capsule(mutate=change)
 def test_unsigned_modified_document_and_extra_file_refused(self):
  for change in [lambda a,b:a.__setitem__('REQUEST.BOUND.json',b'{}'),lambda a,b:a.__setitem__('SECRET.pem',b'NO')]:
   with self.assertRaises(m.Refused):self.capsule(mutate=change)
 def test_missing_spawn_claim_refused(self):
  with self.assertRaises(m.Refused):self.capsule(mutate=lambda a,b:a.pop(next(n for n in a if n.endswith('/spawn.claim'))))
 def test_changed_receipt_or_nonempty_stderr_refused(self):
  for suffix,val in [('stdout.private.json',b'{}'),('stderr.private',b'warning')]:
   def change(a,b):a[next(n for n in a if n.endswith('/'+suffix))]=val
   with self.assertRaises(m.Refused):self.capsule(mutate=change)
 def test_canonical_manifest_and_deterministic_ustar(self):
  a,ma,_=self.capsule();b,mb,_=self.capsule();self.assertEqual((a,ma),(b,mb));self.assertEqual(ma,m.canonical(m.strict(ma)));m.inspect_night_tar(a,ma,NOW)
 def test_night_control_accepted_by_frozen_receiver(self):
  a,ma,_=self.capsule();c=f.fake_cipher(b'night');v=m.night_gates(f.context(),a,ma,c,f.blob(c),NOW);channel.control(self.owner_comment(v),f.CTX,'NIGHT_GATES',1);self.assertEqual(v['document_sha256'],m.sha(ma))
 def test_night_wrong_manifest_archive_cipher_and_deadline_refused(self):
  a,ma,_=self.capsule();c=f.fake_cipher()
  for ar,man,cipher,now in [(a,ma+b' ',c,NOW),(a+b'x'*512,ma,c,NOW),(a,ma,b'plaintext',NOW),(a,ma,c,m.instant('2026-10-08T13:58:40Z'))]:
   with self.assertRaises(m.Refused):m.night_gates(f.context(),ar,man,cipher,f.blob(c),now)
 def test_real_dispatch_timestamp_and_no_future_receipt(self):
  self.assertEqual(m.receipt_instant('2026-10-07T23:20:00.123456+00:00').microsecond,123456)
  with self.assertRaises(m.Refused):m.receipt_instant('2026-10-07T23:20:00')
  raw,manifest,_=self.capsule()
  with self.assertRaises(m.Refused):m.inspect_night_tar(raw,manifest,m.instant('2026-10-07T23:19:59Z'))
 def test_symlink_hardlink_and_special_file_refused(self):
  with tempfile.TemporaryDirectory(dir=pathlib.Path(tempfile.gettempdir()).resolve()) as home:
   p=pathlib.Path(home);m.put(p/'a',b'A');os.symlink(p/'a',p/'link')
   with self.assertRaises(m.Refused):m.read(p/'link')
   os.link(p/'a',p/'hard')
   with self.assertRaises(m.Refused):m.read(p/'a')
   os.mkfifo(p/'pipe')
   with self.assertRaises(m.Refused):m.read(p/'pipe')
 def test_outputs_exclusive_and_private(self):
  with tempfile.TemporaryDirectory(dir=pathlib.Path(tempfile.gettempdir()).resolve()) as home:
   p=pathlib.Path(home)/'output';m.put(p,b'A');self.assertEqual(p.stat().st_mode&0o777,0o600)
   with self.assertRaises(FileExistsError):m.put(p,b'B')
if __name__=='__main__':
 def audit(e,args):
  if e.startswith(('socket.','subprocess.')) or e in ('os.system','os.exec','os.fork','os.posix_spawn'):raise RuntimeError('PROOF_NO_NETWORK_CHILD_HOST')
 sys.addaudithook(audit);r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests));v=dict(schema='OPERATOR2_NEW_DATA_PROOF_V1',methods=r.testsRun,failures=len(r.failures),errors=len(r.errors),actual_network=0,children=0,host=0,actual_asks=0,actual_signatures=0,operational_READY=False,source_sha256=m.sha((HOME/'capsule_data.py').read_bytes()),test_sha256=m.sha(pathlib.Path(__file__).read_bytes()));(HOME/'RESULT.public.json').write_bytes(m.canonical(v));raise SystemExit(0 if r.wasSuccessful() else 1)
