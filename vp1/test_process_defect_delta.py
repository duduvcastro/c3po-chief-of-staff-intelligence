"""NEW B1r/S1/S2/X1 vectors. Isolated fixture child only."""
import base64
from dataclasses import asdict,replace
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest
import fixture_builder_r3 as fixture
import veto_emitter as v
import config_finalizer as c
import process_receipt as r

class ProcessDefectDelta(unittest.TestCase):
 def setUp(self):self.f=fixture.FixtureBuilder('runTest');self.f.setUp()
 def emit(self,**changes):
  args=dict(spec_raw=self.f.vspec_raw,observation_raw=self.f.observation,authority_raw=self.f.va,
      observation_sha256=v.digest(self.f.observation),spec_sha256=v.digest(self.f.vspec_raw),verifier=self.f.vbinding,
      clock=lambda:self.f.now,consumer_template_raw=self.f.template_raw,
      derivation_rule_raw=self.f.rule_raw,derivation_rule_sha=self.f.rule_sha)
  args.update(changes);return v.emit_view(**args)
 def l12(self,raw=None,**changes):
  args=dict(spec_raw=self.f.vspec_raw,rule_raw=self.f.rule_raw,rule_sha256=self.f.rule_sha,
      worker_sha256=self.f.spec['process_worker_sha256'],nonce=self.f.spec['process_nonce'],now=self.f.now)
  args.update(changes);return r.l12_view(raw or self.f.receipt_raw,**args)
 def bundle(self):
  fields={'veto_spec':self.f.vspec_raw,'derivation_rule':self.f.rule_raw,'template':self.f.template_raw,
      'observation':self.f.observation,'veto_authority':self.f.va,'config_spec':self.f.spec_raw,'config_authority':self.f.ca,
      'act_b':self.f.act_raw,'machine_order':self.f.order_raw,'fixture_verified_observation':v.canonical(asdict(self.f.vrow))+b'\n'}
  return {'schema':'R2D2_ISOLATED_VETO_WORKER_REQUEST_CANDIDATE_V1','mode':'FIXTURE','nonce':self.f.spec['process_nonce'],
      'fixture_now':self.f.now.isoformat(),'originals':{k:base64.b64encode(raw).decode()for k,raw in fields.items()}}
 def child(self,row):
  out=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).parent/'veto_worker.py')],input=v.canonical(row)+b'\n',
      capture_output=True,timeout=4,check=False)
  self.assertEqual(out.stderr,b'');return out.returncode,json.loads(out.stdout)

 def test_new_finalizer_preserves_all_template_fields_and_pins(self):
  final=self.f.finalize();body=json.loads(final.config_raw)
  self.assertEqual(body['document_pins'],self.f.template['document_pins']);expected=dict(self.f.template)
  expected['veto_views']={c.FIRST:{'file':'veto.md','sha256':self.f.emission.view_sha256}}
  self.assertEqual(body,expected);self.assertFalse(final.operational_GO)
 def test_final_config_added_revoked_document_pin_cannot_pass(self):
  final=self.f.finalize();body=json.loads(final.config_raw);body['document_pins']['GO:bar_manifest']={'file':'go.md','sha256':'a'*64}
  with self.assertRaisesRegex(c.Refused,'CONFIG_FINAL_DOCUMENT_PINS_CHANGED'):
   c.verify_final_delta(self.f.template_raw,v.canonical(body)+b'\n',day=c.FIRST,veto_file='veto.md',veto_sha256=self.f.emission.view_sha256)
 def test_final_config_nonview_mutation_refuses(self):
  final=self.f.finalize();body=json.loads(final.config_raw);body['release_sha']='a'*64
  with self.assertRaisesRegex(c.Refused,'CONFIG_FINAL_STATIC_FIELDS_CHANGED'):
   c.verify_final_delta(self.f.template_raw,v.canonical(body)+b'\n',day=c.FIRST,veto_file='veto.md',veto_sha256=self.f.emission.view_sha256)
 def test_direct_real_forged_loaded_object_never_calls_verifier(self):
  spec=dict(self.f.vspec,mode='REAL');raw=v.canonical(spec)+b'\n';calls=[]
  binding=replace(self.f.vbinding,mode='REAL',verify_original=lambda *a:calls.append(1))
  with self.assertRaisesRegex(v.Refused,'VETO_REAL_PROCESS_AUTHORITY_UNAVAILABLE'):
   self.emit(spec_raw=raw,spec_sha256=v.digest(raw),verifier=binding,clock=v.real_clock)
  self.assertEqual(calls,[])
 def test_monkeypatched_real_clock_cannot_enable_real_api(self):
  original=v.real_clock;v.real_clock=lambda:self.f.now
  try:
   spec=dict(self.f.vspec,mode='REAL');raw=v.canonical(spec)+b'\n'
   with self.assertRaisesRegex(v.Refused,'VETO_REAL_PROCESS_AUTHORITY_UNAVAILABLE'):
    self.emit(spec_raw=raw,spec_sha256=v.digest(raw),clock=v.real_clock)
  finally:v.real_clock=original
 def test_derivation_caller_changes_static_authority_refuses(self):
  spec=dict(self.f.vspec,authority_sha256='a'*64,required_pins=sorted(set(self.f.vspec['required_pins'])|{'a'*64}));raw=v.canonical(spec)+b'\n'
  with self.assertRaisesRegex(v.Refused,'VETO_DERIVATION_STATIC_MISMATCH'):
   self.emit(spec_raw=raw,spec_sha256=v.digest(raw))
 def test_derivation_observation_outside_signed_candidate_window_refuses(self):
  spec=dict(self.f.vspec,view_opens_at='2026-10-12T13:02:00Z');raw=v.canonical(spec)+b'\n'
  with self.assertRaisesRegex(v.Refused,'VETO_DERIVATION_OBSERVATION_WINDOW'):
   self.emit(spec_raw=raw,spec_sha256=v.digest(raw))

 def test_noncapacity_template_refuses_even_if_document_dict_present(self):
  raw=v.canonical({'document_pins':self.f.template['document_pins']})+b'\n'
  spec=dict(self.f.vspec,consumer_config_template_sha256=v.digest(raw),required_pins=sorted(set(self.f.vspec['required_pins'])|{v.digest(raw)}))
  rule=dict(self.f.rule,spec_base={k:x for k,x in spec.items()if k!='view_opens_at'});rr=v.canonical(rule)+b'\n'
  sr=v.canonical(spec)+b'\n'
  with self.assertRaisesRegex(v.Refused,'VETO_CONSUMER_DOCUMENT_FIELDS'):
   self.emit(spec_raw=sr,spec_sha256=v.digest(sr),consumer_template_raw=raw,derivation_rule_raw=rr,derivation_rule_sha=v.digest(rr))
 def test_ten_second_image_view_is_refused_not_clamped(self):
  binding=replace(self.f.vbinding,verify_original=lambda *a:replace(self.f.vrow,valid_until='2026-10-12T13:00:10Z'))
  with self.assertRaisesRegex(v.Refused,'VETO_UNIFIED_VALIDITY_INTERVAL'):self.emit(verifier=binding)
 def test_x1_exact_same_five_second_bounds_and_authority(self):
  view=self.l12();self.assertEqual(view.raw,self.f.emission.view_raw);self.assertEqual(view.authority_sha256,v.digest(self.f.va))
  self.assertEqual(view.verdict,'ALLOW');self.assertEqual((view.valid_until-view.observed_at).total_seconds(),5)
 def test_x1_expired_original_cannot_renew(self):
  with self.assertRaisesRegex(r.Refused,'PROCESS_VIEW_UNIFIED_TTL'):self.l12(now=self.f.now+timedelta(seconds=1))
 def test_draft_to_issued_edit_is_detected_by_original_receipt(self):
  mutated=replace(self.f.emission,view_raw=self.f.emission.view_raw.replace(b'DRAFT',b'ISSUED'))
  with self.assertRaisesRegex(r.Refused,'PROCESS_RECEIPT_BINDING'):
   r.validate(self.f.receipt_raw,mutated,spec=self.f.vspec,rule_sha256=self.f.rule_sha,
       worker_sha256=self.f.spec['process_worker_sha256'],nonce=self.f.spec['process_nonce'])
 def test_bare_emission_without_own_receipt_cannot_finalize(self):
  with self.assertRaises(r.Refused):self.f.finalize(emission_receipt_raw=b'{}\n')

 def test_isolated_worker_fixture_pipe_returns_bound_outputs(self):
  code,row=self.child(self.bundle());self.assertEqual(code,0);self.assertEqual(row['status'],'FIXTURE_COMPLETE')
  self.assertFalse(row['actual_process_attestation']);self.assertFalse(row['operational_GO'])
  self.assertIn(b'"state":"DRAFT"',base64.b64decode(row['view_base64']))
  body=json.loads(base64.b64decode(row['config_base64']));self.assertEqual(body['document_pins'],self.f.template['document_pins'])
  receipt,_=r.parse(base64.b64decode(row['emission_receipt_base64']));self.assertEqual(receipt['worker_pid'],row['worker_pid'])
 def test_isolated_worker_does_not_inherit_hostile_parent_globals(self):
  original=v.emit_view;v.emit_view=lambda *a,**k:(_ for _ in()).throw(RuntimeError('PARENT_MUTATION'))
  try:code,row=self.child(self.bundle());self.assertEqual(code,0);self.assertEqual(row['mode'],'FIXTURE')
  finally:v.emit_view=original
 def test_isolated_worker_real_input_never_promotes_fixture(self):
  row=self.bundle();row['mode']='REAL';code,out=self.child(row)
  self.assertEqual(code,3);self.assertEqual(out['code'],'PROCESS_AUTHORITY_UNAVAILABLE');self.assertNotIn('view_base64',out)

 def test_sunday_spec_cannot_be_relabelled_as_monday_image_authority(self):
  context=dict(self.f.vspec['context'],first_session='2026-10-11',day='2026-10-11')
  spec=dict(self.f.vspec,context=context,view_opens_at='2026-10-11T13:00:00Z')
  rule=dict(self.f.rule,spec_base={k:x for k,x in spec.items()if k!='view_opens_at'},
      observe_not_before='2026-10-11T12:59:00Z',observe_not_after='2026-10-11T13:01:00Z')
  rr=v.canonical(rule)+b'\n';sr=v.canonical(spec)+b'\n'
  with self.assertRaisesRegex(v.Refused,'VETO_DERIVATION_MONDAY_CONTEXT'):
   self.emit(spec_raw=sr,spec_sha256=v.digest(sr),derivation_rule_raw=rr,derivation_rule_sha=v.digest(rr))
 def test_x1_direct_ten_second_transcript_cannot_shorten_interval(self):
  raw=self.f.emission.view_raw.replace(b'13:00:05Z',b'13:00:10Z')
  emission=replace(self.f.emission,view_raw=raw,view_sha256=v.digest(raw))
  receipt=r.make(emission,nonce=self.f.spec['process_nonce'],worker_sha256=self.f.spec['process_worker_sha256'],
      worker_pid=1,rule_sha256=self.f.rule_sha,template_sha256=v.digest(self.f.template_raw))
  with self.assertRaisesRegex(r.Refused,'PROCESS_VIEW_UNIFIED_TTL'):self.l12(raw=receipt)
 def test_x1_forged_issued_transcript_never_promotes_fixture_origin(self):
  raw=self.f.emission.view_raw.replace(b'DRAFT',b'ISSUED')
  emission=replace(self.f.emission,view_raw=raw,view_sha256=v.digest(raw))
  receipt=r.make(emission,nonce=self.f.spec['process_nonce'],worker_sha256=self.f.spec['process_worker_sha256'],
      worker_pid=1,rule_sha256=self.f.rule_sha,template_sha256=v.digest(self.f.template_raw))
  with self.assertRaisesRegex(r.Refused,'PROCESS_VIEW_NOT_FIXTURE'):self.l12(raw=receipt)

if __name__=='__main__':unittest.main()
