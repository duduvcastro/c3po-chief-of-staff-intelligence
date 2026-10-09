"""NEW Sunday-purpose vectors. Fixtures only; no signed L12 or physical server."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import json
import os
from pathlib import Path
import sys,tempfile,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import upstream_veto as u
import veto_emitter as v
import finite_batch as b

class Sunday(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
  self.now=datetime(2026,10,11,19,0,0,123456,tzinfo=timezone.utc);self.clock=lambda:self.now
  self.auth=b'SYNTHETIC_SOURCE_AUTHORITY';self.owner=(HERE/'originals'/'DUDU_D1_SIGNATURE.json').read_bytes();self.d1=(HERE/'originals'/'DECISAO_D1_CAMINHO_RAPIDO.md').read_bytes();self.impl=v.digest((HERE/'upstream_veto.py').read_bytes());self.fp=v.digest(b'SYNTHETIC_CALLBACK')
  self.spec={'schema':u.SCHEMA,'mode':'FIXTURE','context':{'epoch':b.EPOCH,'first_session':'2026-10-12','target_session':'2026-10-12','factual_day':'2026-10-11','purpose':'UPSTREAM_P'},'root':{'path':str(self.root),'ancestors':u.measure_folder(str(self.root)),'owner_uid':os.getuid()},'source_identity':'sunday-fixture','source_implementation_sha256':self.impl,'authority_sha256':v.digest(self.auth),'authority_verifier':{'identity':'fixture-external-authority','implementation_sha256':self.fp},'owner_record_sha256':v.digest(self.owner),'decision_document_sha256':u.D1_SHA,'valid_from':'2026-10-11T18:00:00Z','valid_until':'2026-10-12T03:59:59Z','observe_not_before':'2026-10-11T18:00:00Z','observe_not_after':'2026-10-12T03:59:59Z','ttl_seconds':5,'l12_authority_sha256':'a'*64,'runtime_sha256':'b'*64,'l12_scope':{'lane':'UPSTREAM_P','track':'P','previous_session':'2026-10-09','permitted_operations':list(b.UPSTREAM)}}
  self.spec['dependencies']={'finite_batch':v.digest(Path(b.__file__).read_bytes()),'veto_emitter':v.digest(Path(v.__file__).read_bytes())}
  self.spec['required_pins']=sorted({self.impl,v.digest(self.auth),v.digest(self.owner),u.D1_SHA,self.fp,'a'*64,'b'*64,*self.spec['dependencies'].values()})
  self.q={'schema':'L12_FINITE_BATCH_REQUEST_CANDIDATE_V1','lane':'UPSTREAM_P','epoch':b.EPOCH,'session':'2026-10-12','previous_session':'2026-10-09','track':'P','prepared_at':'2026-10-11T17:00:00Z','owner_deadline':'2026-10-11T17:45:00Z','authority_sha256':'a'*64,'runtime_sha256':'b'*64,'veto_authority_sha256':v.digest(self.auth),'initial_receipts':{},'tasks':[]}
  roles=[]
  for op in b.UPSTREAM:
   self.q['tasks'].append({'operation':op,'not_before':'2026-10-11T18:00:00Z','not_after':'2026-10-12T03:59:59Z','budget_seconds':120,'requires':list(b.MINIMUM_DEPENDENCIES[op])})
   roles.append(op)
  self.task=self.q['tasks'][0];self.source=None
 def tearDown(self):
  if self.source:self.source.close()
  self.tmp.cleanup()
 def make(self,**kwargs):
  raw=v.canonical(self.spec)+b'\n';args=dict(spec_raw=raw,authority_raw=self.auth,decision_raw=self.d1,owner_raw=self.owner,spec_sha256=v.digest(raw),binding=u.AuthorityBinding('fixture-external-authority',self.fp,'FIXTURE',lambda *a:None),clock=self.clock);args.update(kwargs)
  self.source=u.FolderSource(**args);return self.source
 def read(self):return self.source.veto_read(self.q,self.task,datetime(2030,1,1,tzinfo=timezone.utc))
 def test_sunday_actual_clock_target_monday_distinct_allow_codec(self):
  self.make();view=self.read();body=json.loads(view.raw)
  self.assertEqual(type(view),b.VetoView);self.assertEqual(view.verdict,'ALLOW');self.assertEqual(body['context']['factual_day'],'2026-10-11');self.assertEqual(body['context']['target_session'],'2026-10-12');self.assertEqual(body['context']['purpose'],'UPSTREAM_P')
  self.assertEqual(view.observed_at,self.now);self.assertEqual((view.valid_until-view.observed_at).total_seconds(),5)
  self.assertNotIn(b'VETO_VIEW',view.raw);self.assertNotIn(b'ISSUED',view.raw);self.assertIsNone(self.source.veto_verify(view,self.q,self.task,self.now))
 def test_same_operation_cannot_renew(self):
  self.make();self.read();self.now+=timedelta(seconds=1)
  with self.assertRaisesRegex(u.Refused,'L12_VETO_OPERATION_ALREADY_OBSERVED'):self.read()
 def test_distinct_finite_operation_observes_new_original(self):
  self.make();one=self.read();self.task=self.q['tasks'][1];self.now+=timedelta(seconds=2);two=self.read()
  self.assertNotEqual(one.raw,two.raw);self.assertEqual(two.observed_at,self.now)
  with self.assertRaisesRegex(u.Refused,'L12_VETO_ORIGINAL'):self.source.veto_verify(one,self.q,self.task,self.now)
 def test_ttl_expiry_is_not_renewed(self):
  self.make();view=self.read();old=view.raw;self.now+=timedelta(seconds=5)
  with self.assertRaisesRegex(u.Refused,'FOLDER_OBSERVATION_STALE'):self.source.veto_verify(view,self.q,self.task,self.now)
  self.assertEqual(view.raw,old)
 def test_veto_added_at_last_hook_blocks_effect(self):
  self.make();self.read();(self.root/'VETO').write_bytes(b'stop')
  with self.assertRaisesRegex(u.Refused,'FOLDER_VETO_PRESENT'):self.source.before_effect(self.q,self.task)
 def test_any_entry_is_veto_before_observation(self):
  self.make();(self.root/'directory-veto').mkdir()
  with self.assertRaisesRegex(u.Refused,'FOLDER_VETO_PRESENT'):self.read()
 def test_monday_clock_is_not_sunday_observation(self):
  self.make();self.now=datetime(2026,10,12,13,0,tzinfo=timezone.utc)
  with self.assertRaisesRegex(u.Refused,'L12_VETO_FACTUAL_DAY'):self.read()
 def test_ten_second_image_ttl_is_refused(self):
  self.spec['ttl_seconds']=10
  with self.assertRaisesRegex(u.Refused,'FOLDER_CLOCK_POLICY'):self.make()
 def test_actual_bootstrap_monday_lane_cannot_use_sunday_scope(self):
  self.make();self.q['lane']='BOOTSTRAP_MONDAY'
  with self.assertRaises((u.Refused,b.Hold)):self.read()
 def test_raw_view_dictionary_or_clone_not_provenance(self):
  self.make();view=self.read()
  with self.assertRaisesRegex(u.Refused,'L12_VETO_ORIGINAL'):self.source.veto_verify(replace(view),self.q,self.task,self.now)
 def test_lambda_true_does_not_attest_authority(self):
  with self.assertRaisesRegex(u.Refused,'FOLDER_AUTHORITY_BOOLEAN_IS_NOT_ATTESTATION'):
   self.make(binding=u.AuthorityBinding('fixture-external-authority',self.fp,'FIXTURE',lambda *a:True))
 def test_real_scope_does_not_accept_injected_clock(self):
  self.spec['mode']='REAL';self.spec['root']['owner_uid']=0;self.spec['root']['ancestors'][-1][1][2]=0
  with self.assertRaisesRegex(u.Refused,'FOLDER_REAL_CLOCK_REQUIRED'):
   self.make(binding=u.AuthorityBinding('fixture-external-authority',self.fp,'REAL',lambda *a:None))
 def test_separate_e6_sunday_scope_requires_complete_result_roles_in_plan(self):
  self.spec['context']['purpose']='E6_SUNDAY';self.spec['l12_scope']['lane']='DOWNSTREAM_AFTER_E6';self.spec['l12_scope']['permitted_operations']=['e6']
  self.q['lane']='DOWNSTREAM_AFTER_E6';self.q['initial_receipts']={'commit_result':'c'*64,'publish_launch':'d'*64}
  self.q['tasks']=[{'operation':'e6','not_before':'2026-10-11T18:00:00Z','not_after':'2026-10-12T03:59:59Z','budget_seconds':120,'requires':list(b.MINIMUM_DEPENDENCIES['e6'])}];self.task=self.q['tasks'][0]
  self.make();view=self.read();self.assertEqual(json.loads(view.raw)['context']['purpose'],'E6_SUNDAY')
  self.assertIsNone(self.source.before_effect(self.q,self.task))
 def test_actual_task_changed_after_read_refuses(self):
  self.make();view=self.read();self.task['budget_seconds']=119
  with self.assertRaisesRegex(u.Refused,'L12_VETO_ORIGINAL'):self.source.veto_verify(view,self.q,self.task,self.now)


