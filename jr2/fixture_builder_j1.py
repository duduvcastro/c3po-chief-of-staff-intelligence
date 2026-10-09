"""NEW synthetic J-slot paths; temporary fixtures only, never live image/DB/host."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import j_slot as j
import folder_veto as folder
import veto_emitter as v
import config_finalizer as cf
import finite_batch as batch
from fixture_builder_r3 import FixtureBuilder

class JFixtures(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.events=[]
  for name in ('veto','docs','config','payload','go','ledger','manifest'):
   p=self.root/name;p.mkdir();p.chmod(0o700)
  (self.root/'ledger'/'attempts.ledger').write_bytes(b'');(self.root/'ledger'/'attempts.ledger').chmod(0o600)
  self.ledger=batch.DurableLedger(str(self.root/'ledger'),batch.measure_local_ledger(str(self.root/'ledger')))
  self.clock=lambda:self.f.now;self.mono=lambda:0.0
  self.f=FixtureBuilder('runTest');self.f.setUp()
  self.f.now=datetime(2026,10,12,13,0,0,456789,tzinfo=timezone.utc)
  self.decision=(HERE/'originals'/'DECISAO_D1_CAMINHO_RAPIDO.md').read_bytes();self.owner=(HERE/'originals'/'DUDU_D1_SIGNATURE.json').read_bytes()
  for name in ('documents','payload','go'):
   self.f.template['roots'][name]['path']=str(self.root/('docs'if name=='documents'else name))
  self.template=v.canonical(self.f.template)+b'\n';self.f.template_raw=self.template
  self.base=dict(self.f.spec);self.base.pop('veto_spec_sha256');self.base.pop('required_pins')
  self.base['settings_file']=str(self.root/'config'/'capacity.json');self.base['template_sha256']=v.digest(self.template)
  program=(HERE/'folder_verifier_fixture.py').resolve();anc=folder.measure_folder(str(program.parent));self.program={'identity':'folder-verifier-fixture','implementation_sha256':v.digest(program.read_bytes()),'path':str(program),'ancestors':anc}
  self.authpin=v.digest(b'SYNTHETIC_SLOT_AUTHORITY_PROGRAM');self.fauthpin=v.digest(b'SYNTHETIC_FOLDER_AUTHORITY_PROGRAM')
  impl={n:j.module_pin(n)for n in ('folder_veto','veto_emitter','config_finalizer','finite_batch','j_slot')}
  required=set(self.f.vspec['required_pins'])|{v.digest(self.template),v.digest(self.owner),folder.D1_SHA,self.program['implementation_sha256'],self.authpin,self.fauthpin,*impl.values()}
  self.base['required_pins']=sorted(required)
  self.source={'schema':folder.SCHEMA,'mode':'FIXTURE','context':{'epoch':cf.EPOCH,'first_session':cf.FIRST,'day':cf.FIRST,'order_sha':self.f.machine_sha},'root':{'path':str(self.root/'veto'),'ancestors':folder.measure_folder(str(self.root/'veto')),'owner_uid':os.getuid()},'source_identity':'folder-fixture','source_implementation_sha256':impl['folder_veto'],'authority_sha256':v.digest(self.f.va),'authority_verifier':{'identity':'folder-authority-fixture','implementation_sha256':self.fauthpin},'veto_verifier':self.program,'owner_record_sha256':v.digest(self.owner),'decision_document_sha256':folder.D1_SHA,'valid_from':'2026-10-12T12:59:00Z','valid_until':'2026-10-12T13:01:00Z','observe_not_before':'2026-10-12T13:00:00Z','observe_not_after':'2026-10-12T13:00:30Z','ttl_seconds':10,'required_pins':sorted(required)}
  self.source_raw=v.canonical(self.source)+b'\n'
  self.vbase={'schema':v.SPEC_SCHEMA,'mode':'FIXTURE','context':self.source['context'],'source':{'identity':self.source['source_identity'],'implementation_sha256':impl['folder_veto'],'observation_format':folder.OBSERVATION},'verifier':{k:self.program[k]for k in ('identity','implementation_sha256')},'authority_sha256':v.digest(self.f.va),'maximum_age_seconds':10,'required_pins':sorted(required),'consumer_config_template_sha256':v.digest(self.template),'consumer_document_pins':sorted({x['sha256']for x in self.f.template['document_pins'].values()})}
  self.base_raw=v.canonical(self.base)+b'\n';self.vbase_raw=v.canonical(self.vbase)+b'\n'
  self.rule={'schema':j.SCHEMA,'mode':'FIXTURE','epoch':cf.EPOCH,'day':cf.FIRST,'folder_spec_sha256':v.digest(self.source_raw),'config_base_sha256':v.digest(self.base_raw),'template_sha256':v.digest(self.template),'veto_base_sha256':v.digest(self.vbase_raw),'manifest_writer_sha256':j.MANIFEST_SHA,'implementations':impl,'authority_verifier':{'identity':'slot-authority-fixture','implementation_sha256':self.authpin},'manifest_directory':str(self.root/'manifest'),'output_roots':{'documents':folder.measure_folder(str(self.root/'docs')),'config_run':folder.measure_folder(str(self.root/'config'))},'observe_not_before':self.source['observe_not_before'],'observe_not_after':self.source['observe_not_after'],'process_settings':{'r2d2_v2_shadow_enabled':True,'r2d2_v2_capacity_required':True}}
  self.sa=j.SlotAuthority('slot-authority-fixture',self.authpin,'FIXTURE',self.slot_auth)
  self.fa=folder.AuthorityBinding('folder-authority-fixture',self.fauthpin,'FIXTURE',self.folder_auth)
  self.cv=self.f.cb;self.image=j.ImageBinding('FIXTURE',SimpleNamespace(context=self.context,run=self.writer),j.MANIFEST_SHA)
  self.before_prepare=None;self.after_prepare=None;self.delay=False
 def tearDown(self):self.ledger.close();self.temp.cleanup()
 def slot_auth(self,*a):self.events.append('slot-auth')
 def folder_auth(self,*a):
  self.events.append('folder-auth')
  self.assertTrue(any(x.name.startswith('consume-')for x in(self.root/'ledger').iterdir()))
 def context(self,settings,**kw):
  self.events.append('context');self.settings=settings
  self.assertTrue(kw['prepare_first']);self.assertIs(kw['clock'],self.clock)
  if self.delay:self.f.now+=timedelta(seconds=11)
  return SimpleNamespace(prepare=self.prepare,verify_go=self.verify_go)
 def prepare(self,day):
  self.events.append('prepare')
  if self.after_prepare:self.after_prepare()
  return {'status':'COMMITTED'}
 def verify_go(self,*a):self.events.append('go');return True
 def writer(self,ctx,receipt,**kw):
  self.events.append('run');self.assertEqual(kw['day'],cf.FIRST);self.assertEqual(kw['max_wait'],0)
  self.assertEqual(kw['require_go_mode'],'INDIVIDUAL')
  if self.before_prepare:self.before_prepare()
  ctx.verify_go({},{});ctx.prepare(cf.FIRST);ctx.verify_go({},{});self.events.append('publish-fixture')
  receipt.update(epoch=cf.EPOCH,status='PUBLISHED_VERIFIED',capacity_config_sha256=self.settings.r2d2_v2_capacity_config_sha,binding_sha256='a'*64,manifest_sha256='b'*64)
  return 0
 def run_slot(self,**changes):
  raw=v.canonical(self.rule)+b'\n'
  args=dict(rule_raw=raw,rule_sha256=v.digest(raw),ledger=self.ledger,authority=self.sa,folder_spec_raw=self.source_raw,folder_authority_raw=self.f.va,decision_raw=self.decision,owner_raw=self.owner,folder_binding=self.fa,config_base_raw=self.base_raw,template_raw=self.template,veto_base_raw=self.vbase_raw,config_authority_raw=self.f.ca,act_b_raw=self.f.act_raw,machine_order_raw=self.f.order_raw,config_verifier=self.cv,image=self.image,base_settings=SimpleNamespace(),clock=self.clock,monotonic=self.mono)
  args.update(changes);return j.run_slot(**args)
 def test_one_same_process_fixture_dynamic_outputs_complete(self):
  out=self.run_slot();self.assertEqual((out.status,out.code),('COMPLETE','J_IMAGE_MANIFEST_COMPLETE'))
  self.assertFalse(out.operational_GO)
  raw=(self.root/'docs'/'veto.md').read_bytes();self.assertIn(b'13:00:00.456789+00:00',raw);self.assertIn(b'"state":"DRAFT"',raw)
  config=json.loads((self.root/'config'/'capacity.json').read_bytes());self.assertEqual(config['veto_views'][cf.FIRST]['sha256'],v.digest(raw));self.assertIsNone(config['restore_revocation'])
  self.assertEqual(config['identity']['runtime_order_sha'],self.f.runtime_sha)
  self.assertIn('prepare',self.events);self.assertGreater(self.events.count('folder-auth'),5)
 def test_j2_new_rule_hash_cannot_repeat_day(self):
  one=self.run_slot();self.assertEqual(one.status,'COMPLETE');calls=len(self.events)
  self.rule['manifest_directory']=str(self.root/'another-manifest')
  self.assertEqual(self.run_slot().code,'ATTEMPT_ALREADY_CONSUMED')
  self.assertEqual(len(self.events),calls)
 def test_invalid_input_consumed_before_any_observation(self):
  out=self.run_slot(template_raw=self.template+b'bad');self.assertEqual(out.code,'J_INPUT_PIN');self.assertEqual(self.events,[])
  self.assertEqual(self.run_slot().code,'ATTEMPT_ALREADY_CONSUMED')
 def test_veto_before_observation_refuses_without_image_or_stage(self):
  (self.root/'veto'/'STOP').write_bytes(b'ANY ENTRY')
  out=self.run_slot();self.assertEqual(out.code,'FOLDER_VETO_PRESENT');self.assertNotIn('context',self.events)
  self.assertEqual(list((self.root/'docs').iterdir()),[])
 def test_veto_added_before_prepare_blocks_image_commit(self):
  self.before_prepare=lambda:(self.root/'veto'/'STOP').write_bytes(b'veto')
  out=self.run_slot();self.assertEqual(out.status,'UNCERTAIN');self.assertEqual(out.code,'FOLDER_VETO_PRESENT');self.assertNotIn('prepare',self.events);self.assertNotIn('publish-fixture',self.events)
 def test_veto_added_after_prepare_blocks_publication(self):
  self.after_prepare=lambda:(self.root/'veto'/'STOP').write_bytes(b'veto')
  out=self.run_slot();self.assertEqual(out.status,'UNCERTAIN');self.assertIn('prepare',self.events);self.assertNotIn('publish-fixture',self.events)
 def test_context_delay_does_not_renew_or_reach_prepare(self):
  self.delay=True;out=self.run_slot();self.assertEqual(out.code,'J_VETO_BUDGET_EXHAUSTED');self.assertNotIn('prepare',self.events)
 def test_slot_lambda_true_is_not_authority(self):
  out=self.run_slot(authority=replace(self.sa,verify_current=lambda *a:True));self.assertEqual(out.code,'J_AUTHORITY_BOOLEAN_IS_NOT_ATTESTATION');self.assertNotIn('context',self.events)
 def test_folder_lambda_true_is_not_authority(self):
  out=self.run_slot(folder_binding=replace(self.fa,verify_current=lambda *a:True));self.assertEqual(out.code,'FOLDER_AUTHORITY_BOOLEAN_IS_NOT_ATTESTATION');self.assertNotIn('context',self.events)
 def test_real_clock_injected_refuses_before_callback(self):
  self.rule['mode']='REAL';out=self.run_slot();self.assertEqual(out.code,'J_OUTER_RESERVATION_REQUIRED');self.assertEqual(self.events,[])
 def test_real_supplied_reservation_still_rejects_injected_clock(self):
  scope=(cf.EPOCH,cf.FIRST,'L12_JSLOT_1');key=self.ledger.claim(scope,'c'*64,'d'*64,None)
  outer=j.OuterReservation(scope,'c'*64,'d'*64,key);self.rule['mode']='REAL'
  out=self.run_slot(outer_reservation=outer);self.assertEqual(out.code,'J_REAL_CLOCK_REQUIRED');self.assertEqual(self.events,[])
 def test_outer_pending_and_inner_family_have_separate_claims(self):
  scope=(cf.EPOCH,cf.FIRST,'L12_JSLOT_1');key=self.ledger.claim(scope,'c'*64,'d'*64,None)
  out=self.run_slot(outer_reservation=j.OuterReservation(scope,'c'*64,'d'*64,key));self.assertEqual(out.status,'COMPLETE')
  self.assertNotEqual(out.attempt_key,key);self.ledger.check_reserved(scope,'c'*64,'d'*64,key)
 def test_dynamic_original_never_uses_scheduled_time(self):
  source=folder.FolderSource(self.source_raw,self.f.va,self.decision,self.owner,spec_sha256=v.digest(self.source_raw),binding=folder.AuthorityBinding('folder-authority-fixture',self.fauthpin,'FIXTURE',lambda *a:None),clock=self.clock)
  try:
   obs=source.observe();cr,vr=j.runtime_specs(self.base_raw,self.template,self.vbase_raw,source,obs)
   vs=json.loads(vr);self.assertEqual(vs['view_opens_at'],self.f.now.isoformat());self.assertNotEqual(vs['view_opens_at'],self.rule['observe_not_before'])
   first=json.loads(obs);self.f.now+=timedelta(seconds=3);source.current();self.assertEqual(json.loads(source.original),first)
  finally:source.close()
 def test_wrong_consumer_machine_order_refuses_before_stage(self):
  base=dict(self.base,act_b_order_sha=self.f.runtime_sha);raw=v.canonical(base)+b'\n';self.rule['config_base_sha256']=v.digest(raw)
  out=self.run_slot(config_base_raw=raw);self.assertEqual(out.code,'CONFIG_VETO_MACHINE_ORDER_CONTEXT');self.assertEqual(list((self.root/'docs').iterdir()),[])
 def test_config_callback_not_verified_cannot_stage(self):
  out=self.run_slot(config_verifier=replace(self.cv,verify_current=lambda *a:True));self.assertEqual(out.code,'CONFIG_AUTHORITY_RESULT');self.assertEqual(list((self.root/'docs').iterdir()),[])
 def test_staged_output_conflict_never_overwrites(self):
  path=self.root/'docs'/'veto.md';path.write_bytes(b'PREEXISTING');path.chmod(0o600)
  out=self.run_slot();self.assertEqual(out.status,'UNCERTAIN');self.assertEqual(path.read_bytes(),b'PREEXISTING');self.assertNotIn('context',self.events)
 def test_changed_folder_inode_refuses(self):
  (self.root/'veto').rename(self.root/'veto-original');(self.root/'veto').mkdir();(self.root/'veto').chmod(0o700)
  out=self.run_slot();self.assertEqual(out.code,'FOLDER_IDENTITY_CHANGED');self.assertNotIn('context',self.events)
 def test_sunday_cannot_masquerade_as_monday_image_view(self):
  self.f.now=datetime(2026,10,11,17,0,tzinfo=timezone.utc);out=self.run_slot();self.assertEqual(out.code,'FOLDER_AUTHORITY_EXPIRED');self.assertNotIn('context',self.events)
 def test_clock_rollback_or_nonfinite_mono_refuses(self):
  out=self.run_slot(monotonic=lambda:float('nan'));self.assertEqual(out.code,'J_MONOTONIC');self.assertNotIn('context',self.events)
 def test_exact_image_context_and_run_abi_read_only_ast(self):
  raw=(HERE/'originals'/'manifest_writer.py').read_bytes();self.assertEqual(v.digest(raw),j.MANIFEST_SHA)
  tree=ast.parse(raw);func={x.name:x for x in tree.body if isinstance(x,ast.FunctionDef)}
  self.assertEqual([a.arg for a in func['context'].args.kwonlyargs],['now','prepare_first','clock'])
  self.assertIn('view_opens_at',[a.arg for a in func['run'].args.kwonlyargs]);self.assertIn('require_go_mode',[a.arg for a in func['run'].args.kwonlyargs])


