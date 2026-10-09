"""Fixture construction support only; no previous test methods are present."""
import base64
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import sys,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import fixture_builder_j1 as fixture
import j_slot as j
import veto_emitter as v

class PeerDelta(unittest.TestCase):
 def setUp(self):
  self.f=fixture.JFixtures('runTest');self.f.setUp();self.mode='normal';self.receipt=None;self.returned=False
  self.f.rule.update(veto_protocol=j.HISTORICAL_PROTOCOL,process_candidate_pins=dict(j.PROCESS_PINS))
  self.f.image.module.execute=self.execute
 def tearDown(self):self.f.tearDown()
 def execute(self,build,**kwargs):
  ctx=build();self.receipt={'schema':'R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1','session':'2026-10-12','mode':'PUBLISH','status':'REFUSED','code':None}
  if self.mode=='early':
   self.receipt.update(epoch=j.config.EPOCH,status='ALREADY_PUBLISHED_VERIFIED',capacity_config_sha256=self.f.settings.r2d2_v2_capacity_config_sha,binding_sha256='a'*64,manifest_sha256='b'*64)
   return self.receipt,0
  kwargs.pop('prepare_first');code=self.f.writer(ctx,self.receipt,**kwargs)
  observed=self.f.f.now;until=observed+timedelta(seconds=10)
  self.receipt.update(go_mode='INDIVIDUAL',go_sha256='c'*64,template_sha256='d'*64,view={'observed_at':observed.isoformat(),'valid_until':until.isoformat()},window={'not_before':'2026-10-12T12:59:00Z','not_after':'2026-10-12T13:01:00Z'},published_at=observed.isoformat(),file={'uid':0,'mode':'0600','nlink':1},symbol_count=550)
  if self.mode=='full_already':self.receipt['status']='ALREADY_PUBLISHED_VERIFIED'
  if self.mode=='missing_go':self.receipt.pop('go_sha256')
  if self.mode=='changed_view':self.receipt['view']['observed_at']='2026-10-12T13:00:00Z'
  self.returned=True
  return self.receipt,code


