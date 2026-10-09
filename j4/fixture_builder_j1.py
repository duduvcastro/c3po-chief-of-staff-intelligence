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


