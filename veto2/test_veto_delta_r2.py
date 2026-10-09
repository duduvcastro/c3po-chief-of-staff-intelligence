"""NEW defect-delta vectors only; no real authority or future clock attestation."""
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
HERE=Path(__file__).resolve().parent
loader=importlib.util.spec_from_file_location('veto_emitter',HERE/'veto_emitter.py')
v=importlib.util.module_from_spec(loader);sys.modules[loader.name]=v;loader.loader.exec_module(v)

class Delta(unittest.TestCase):
 def setUp(self):
  self.now=datetime(2026,10,12,13,0,0,234567,tzinfo=timezone.utc)
  self.original=b'SYNTHETIC-original-not-real';self.authority=b'SYNTHETIC-authority'
  self.template=v.canonical({'document_pins':{'ACT_B':{'file':'act_b.md','sha256':'4'*64},'REVOCATIONS':{'file':'rev.md','sha256':'5'*64}}})+b'\n'
  self.spec={'schema':v.SPEC_SCHEMA,'mode':'FIXTURE','context':{'epoch':'R2D2-V2-SHADOW-2026-10-12','first_session':'2026-10-12','day':'2026-10-12','order_sha':'1'*64},'source':{'identity':'synthetic-source','implementation_sha256':'2'*64,'observation_format':'SYNTHETIC'},'verifier':{'identity':'synthetic-verifier','implementation_sha256':'3'*64},'authority_sha256':v.digest(self.authority),'view_opens_at':self.now.isoformat(),'maximum_age_seconds':10,'consumer_config_template_sha256':v.digest(self.template),'consumer_document_pins':['4'*64,'5'*64]}
  self.spec['required_pins']=sorted({'1'*64,'2'*64,'3'*64,'4'*64,'5'*64,v.digest(self.authority),v.digest(self.template)})
  self.row=v.VerifiedObservation('FIXTURE','synthetic-source','2'*64,'SYNTHETIC',v.digest(self.original),v.digest(self.authority),'2026-10-12T12:00:00Z','2026-10-12T14:00:00Z',tuple(self.spec['required_pins']),'FABLE',True,True,True,self.spec['context']['epoch'],'2026-10-12','2026-10-12','1'*64,self.now.isoformat(),'VERIFIED',self.now.isoformat(),(self.now+timedelta(seconds=10)).isoformat(),False,())
  self.verifier=v.VerifierBinding('synthetic-verifier','3'*64,'FIXTURE',lambda *a:self.row)
 def emit(self,spec=None,verifier=None,clock=None,template=None):
  raw=v.canonical(spec or self.spec)+b'\n'
  return v.emit_view(raw,self.original,self.authority,v.digest(self.original),spec_sha256=v.digest(raw),verifier=verifier or self.verifier,clock=clock or(lambda:self.now),consumer_template_raw=self.template if template is None else template)
 def source(self,tmp,raw):
  path=Path(tmp).resolve()/'approved.py';path.write_bytes(raw);path.chmod(0o600)
  parent=str(path.parent);names=['/']+[str(Path(*Path(parent).parts[:i]))for i in range(2,len(Path(parent).parts)+1)]
  pins=tuple((x,v._directory_identity(os.lstat(x)))for x in names)
  return path,pins
 def test_real_callable_metadata_does_not_execute(self):
  calls=[];binding=v.VerifierBinding('synthetic-verifier','3'*64,'REAL',lambda *a:calls.append(a))
  with self.assertRaisesRegex(v.Refused,'VETO_REAL_VERIFIER_NOT_LOADED'):
   self.emit(spec=dict(self.spec,mode='REAL'),verifier=binding,clock=v.real_clock)
  self.assertEqual(calls,[])
 def test_real_injected_clock_refuses_before_source(self):
  with self.assertRaisesRegex(v.Refused,'VETO_REAL_CLOCK_REQUIRED'):
   self.emit(spec=dict(self.spec,mode='REAL'),verifier=replace(self.verifier,mode='REAL'))
 def test_loader_wrong_hash_never_executes_marker(self):
  with tempfile.TemporaryDirectory()as tmp:
   marker=Path(tmp)/'executed';path,pins=self.source(tmp,(f"open({str(marker)!r},'w').write('BAD')\nVERIFIER_MODE='FIXTURE'\ndef verify_original(*a):return None\n").encode())
   with self.assertRaisesRegex(v.Refused,'VETO_VERIFIER_IMPLEMENTATION_HASH'):
    v.load_verifier(str(path),ancestors=pins,identity='approved',implementation_sha256='a'*64,mode='FIXTURE')
   self.assertFalse(marker.exists())
 def test_loaded_pin_and_post_load_change(self):
  with tempfile.TemporaryDirectory()as tmp:
   raw=b"VERIFIER_MODE='FIXTURE'\ndef verify_original(*a):return a[0]\n";path,pins=self.source(tmp,raw)
   loaded=v.load_verifier(str(path),ancestors=pins,identity='approved',implementation_sha256=v.digest(raw),mode='FIXTURE')
   v._check_loaded(loaded);self.assertEqual(loaded.verify_original(b'ORIGINAL'),b'ORIGINAL')
   path.write_bytes(raw+b'#changed\n')
   with self.assertRaisesRegex(v.Refused,'VETO_VERIFIER_IMPLEMENTATION_CHANGED'):v._check_loaded(loaded)
 def test_metadata_cannot_forge_loaded_registry(self):
  with tempfile.TemporaryDirectory()as tmp:
   raw=b"VERIFIER_MODE='FIXTURE'\ndef verify_original(*a):return None\n";path,pins=self.source(tmp,raw)
   module=types.ModuleType('fake');exec(raw,module.__dict__)
   fake=v.LoadedVerifier('approved',v.digest(raw),'FIXTURE',module.verify_original,str(path),pins,v._file_identity(path.stat()),module)
   with self.assertRaisesRegex(v.Refused,'VETO_REAL_VERIFIER_NOT_LOADED'):v._check_loaded(fake)
 def test_loaded_actual_mode_cannot_be_changed_by_metadata(self):
  with tempfile.TemporaryDirectory()as tmp:
   raw=b"VERIFIER_MODE='REAL'\ndef verify_original(*a):return None\n";path,pins=self.source(tmp,raw)
   with self.assertRaisesRegex(v.Refused,'VETO_VERIFIER_LOADED_MODE'):
    v.load_verifier(str(path),ancestors=pins,identity='approved',implementation_sha256=v.digest(raw),mode='FIXTURE')
 def test_loaded_function_replacement_refuses(self):
  with tempfile.TemporaryDirectory()as tmp:
   raw=b"VERIFIER_MODE='FIXTURE'\ndef verify_original(*a):return None\n";path,pins=self.source(tmp,raw)
   loaded=v.load_verifier(str(path),ancestors=pins,identity='approved',implementation_sha256=v.digest(raw),mode='FIXTURE')
   loaded.module.verify_original=lambda *a:True
   with self.assertRaisesRegex(v.Refused,'VETO_REAL_VERIFIER_NOT_LOADED'):v._check_loaded(loaded)
 def test_symlink_leaf_and_changed_ancestor_refuse(self):
  with tempfile.TemporaryDirectory()as tmp:
   raw=b"VERIFIER_MODE='FIXTURE'\ndef verify_original(*a):return None\n";path,pins=self.source(tmp,raw)
   link=Path(tmp).resolve()/'link.py';link.symlink_to(path)
   with self.assertRaisesRegex(v.Refused,'VETO_VERIFIER_FILE_UNAVAILABLE'):v.load_verifier(str(link),ancestors=pins,identity='approved',implementation_sha256=v.digest(raw),mode='FIXTURE')
   changed=pins[:-1]+((pins[-1][0],(0,0,0,0,0)),)
   with self.assertRaisesRegex(v.Refused,'VETO_VERIFIER_ROOT_CHANGED'):v.load_verifier(str(path),ancestors=changed,identity='approved',implementation_sha256=v.digest(raw),mode='FIXTURE')
 def test_actual_template_pin_and_all_document_scope_required(self):
  with self.assertRaisesRegex(v.Refused,'VETO_CONSUMER_TEMPLATE_HASH'):self.emit(template=self.template+b' ')
  spec=dict(self.spec,required_pins=[p for p in self.spec['required_pins']if p!='5'*64])
  with self.assertRaisesRegex(v.Refused,'VETO_CONSUMER_REVOCATION_SCOPE'):self.emit(spec=spec)
  spec=dict(self.spec,consumer_document_pins=['4'*64])
  with self.assertRaisesRegex(v.Refused,'VETO_CONSUMER_REVOCATION_SCOPE'):self.emit(spec=spec)
 def test_revoked_actual_revocations_document_refuses(self):
  self.row=replace(self.row,revoked_shas=('5'*64,))
  with self.assertRaisesRegex(v.Refused,'VETO_AUTHORITY_REVOKED'):self.emit()
 def test_actual_fractional_timestamp_preserved_and_no_renewal(self):
  one=self.emit();self.now+=timedelta(seconds=2);two=self.emit()
  self.assertEqual(one.view_raw,two.view_raw);self.assertIn(b'13:00:00.234567+00:00',one.view_raw)
  self.assertIn(b'"state":"DRAFT"',one.view_raw);self.assertFalse(one.operational_GO)
 def test_epoch03_real_literal_refuses(self):
  spec=dict(self.spec,context=dict(self.spec['context'],epoch='R2D2-V2-SHADOW-2026-10-05'))
  with self.assertRaisesRegex(v.Refused,'VETO_EPOCH'):self.emit(spec=spec)

if __name__=='__main__':unittest.main()
