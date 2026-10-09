"""NEW native-clock/FD/process/J-family delta fixtures only; never production."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import hot_runtime as hot
import hot_worker as worker
import fixture_support_j3 as support
import fixture_builder_r3 as config_fixture

def record(path):
    names=['/']+[str(Path(*path.parent.parts[:i]))for i in range(2,len(path.parent.parts)+1)]
    return {'path':str(path),'sha256':hot.sha(path.read_bytes()),'ancestors':[[name,list(hot.directory(os.lstat(name)))]for name in names]}

class HotFixture:
    def __init__(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        programs={}
        for name in ('hot_runtime','hot_worker','hot_watchdog','finite_batch','folder_veto','veto_emitter','config_finalizer','consumer_codec','j_slot'):
            p=self.root/(name+'.py');p.write_bytes((HERE/(name+'.py')).read_bytes());p.chmod(0o444);programs[name]=record(p)
        p=self.root/'bridge.py';p.write_bytes((HERE/'hot_bridge_fixture.py').read_bytes());p.chmod(0o444);programs['authority_bridge']=record(p)
        originals={}
        for name in ('request','bound','owner','authority','runtime','rule','folder_spec','folder_authority','decision','folder_owner','config_base','template','veto_base','config_authority','act_b','machine_order'):
            p=self.root/(name+'.original');p.write_bytes(b'SYNTHETIC '+name.encode());p.chmod(0o600);originals[name]=record(p)
        now=hot.utc_now();self.registry={'schema':hot.SCHEMA,'mode':'FIXTURE','protocol':hot.PROTOCOL,'epoch':'R2D2-V2-SHADOW-2026-10-12','day':'2026-10-12',
          'programs':programs,'originals':originals,'bridge':{'bootstrap':'bootstrap_hot','authorize':'authorize_hot','general_read':'general_read','general_verify':'general_verify'},
          'ledger':{},'outer_scope':[],'authority_sha256':hot.sha(b'SYNTHETIC-HOT-AUTH'),'general_authority_sha256':hot.sha(b'SYNTHETIC-GENERAL-AUTH'),
          'general_source_identity':'synthetic-folder-only','not_before':hot.iso(now-timedelta(seconds=10)),'not_after':hot.iso(now+timedelta(seconds=30))}
        self.raw=hot.canonical(self.registry);self.loaded=hot.LoadedSet(self.raw);self.session=None
    def session_new(self):self.session=hot.HotSession(self.loaded,fixture_scope=True);return self.session
    def close(self):
        if self.session:self.session.close()
        self.loaded.close();self.tmp.cleanup()

class ProcessDelta(unittest.TestCase):
    def setUp(self):self.f=HotFixture()
    def tearDown(self):self.f.close()
    def fail(self,case,code):
        self.f.loaded.modules['authority_bridge'].GENERAL_CASE=case
        with self.assertRaisesRegex(hot.Refused,code):self.f.session_new().warm()
    def test_preload_and_general_observation_use_native_distinct_instant(self):
        s=self.f.session_new();s.warm();general_time=hot.instant(s.general['observed_at']);self.assertGreaterEqual(general_time,s.warm_at)
        at=hot.utc_now();until=at+timedelta(seconds=10);s.start_image(at,until)
        before=s.image_at;s.refresh_general();s.before_effect();self.assertEqual(s.image_at,before);self.assertEqual(s.image_until,until)
        self.assertFalse(s.general.get('actual_installation_certified',False))
    def test_source_file_change_is_refused_before_authority_callback(self):
        p=self.f.root/'bridge.py';p.chmod(0o600);p.write_bytes(p.read_bytes()+b'\n')
        with self.assertRaisesRegex(hot.Refused,'HOT_FILE_CHANGED'):self.f.session_new()
    def test_runtime_loaded_function_code_change_is_detected(self):
        self.f.loaded.modules['authority_bridge'].authorize_hot.__code__=(lambda *a:None).__code__
        with self.assertRaisesRegex(hot.Refused,'HOT_FUNCTION_CHANGED'):self.f.session_new()
    def test_boolean_authority_is_not_attestation(self):self.fail('authority_boolean','HOT_AUTHORITY_NOT_ATTESTED')
    def test_general_expired_refused(self):self.fail('expired','HOT_GENERAL_STALE_OR_FUTURE')
    def test_general_old_refused(self):self.fail('old','HOT_GENERAL_STALE_OR_FUTURE')
    def test_general_future_refused(self):self.fail('future','HOT_GENERAL_STALE_OR_FUTURE')
    def test_general_owner_veto_refused(self):self.fail('veto','HOT_GENERAL_CONTEXT')
    def test_general_revoked_required_pin_refused(self):self.fail('revoked','HOT_GENERAL_REVOKED')
    def test_general_missing_critical_pin_refused(self):self.fail('missing_pin','HOT_GENERAL_REVOCATION_SCOPE')
    def test_general_wrong_target_day_refused(self):self.fail('wrong_day','HOT_GENERAL_CONTEXT')
    def test_general_boolean_verifier_refused(self):self.fail('verify_boolean','HOT_GENERAL_NOT_ATTESTED')
    def test_image_instant_cannot_be_observed_before_warmup(self):
        s=self.f.session_new()
        with self.assertRaisesRegex(hot.Refused,'HOT_IMAGE_ONCE'):s.start_image(hot.utc_now(),hot.utc_now()+timedelta(seconds=10))
    def test_image_ten_seconds_cannot_be_renewed(self):
        s=self.f.session_new();s.warm();now=hot.utc_now();s.start_image(now,now+timedelta(seconds=10))
        with self.assertRaisesRegex(hot.Refused,'HOT_IMAGE_ONCE'):s.start_image(hot.utc_now(),hot.utc_now()+timedelta(seconds=10))
    def test_expired_image_cannot_be_saved_by_fresh_general_fact(self):
        s=self.f.session_new();s.warm();now=hot.utc_now();s.start_image(now,now+timedelta(seconds=10));s.image_until=now-timedelta(seconds=1)
        with self.assertRaisesRegex(hot.Refused,'HOT_IMAGE10_EXPIRED'):s.refresh_general()
    def test_parent_cannot_supply_python_callback_via_transport(self):
        self.assertEqual(worker.main(['--callback','lambda:True','--mode','REAL']),3)
    def test_entrypoint_running_code_matches_the_actual_program(self):worker.verify_running_code((HERE/'hot_worker.py').read_bytes())
    def test_entrypoint_changed_running_code_is_not_a_source_pin(self):
        original=worker.identity.__code__
        try:
            worker.identity.__code__=(lambda *a:()).__code__
            with self.assertRaisesRegex(ValueError,'HOT_RUNNING_SOURCE_CHANGED'):worker.verify_running_code((HERE/'hot_worker.py').read_bytes())
        finally:worker.identity.__code__=original
    def test_real_emitter_without_private_child_session_refused(self):
        v=self.f.loaded.modules['veto_emitter'];cf=self.f.loaded.modules['config_finalizer']
        # Pure builder produces only synthetic vectors; no real folder/app/DB.
        config_fixture.f=cf;config_fixture.v=v;fixture=config_fixture.FixtureBuilder('runTest');fixture.setUp()
        spec=dict(fixture.vspec,mode='REAL');raw=v.canonical(spec)+b'\n'
        with self.assertRaisesRegex(hot.Refused,'HOT_PROCESS_REQUIRED'):
            v.emit_view(raw,fixture.observation,fixture.va,v.digest(fixture.observation),spec_sha256=v.digest(raw),verifier=object(),clock=v.real_clock,consumer_template_raw=fixture.template_raw)
    def test_fixture_session_cannot_authorize_real_emitter(self):
        session=self.f.session_new();session.warm()
        with self.assertRaisesRegex(hot.Refused,'HOT_REAL_SESSION_REQUIRED'):
            hot.require_session(session,'veto_emitter')
    def test_fixed_isolated_subprocess_loads_only_registry_files_and_refuses_invalid_original(self):
        p=self.f.root/'registry.json';p.write_bytes(self.f.raw);p.chmod(0o600)
        encoded=base64.b64encode(hot.canonical(record(p))).decode('ascii')
        out=subprocess.run([sys.executable,'-I','-B','-','--registry-record-base64',encoded,'--mode','FIXTURE'],
          input=(HERE/'hot_worker.py').read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5,
          env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'})
        self.assertEqual(out.returncode,3);body=json.loads(out.stdout);self.assertEqual(body['status'],'HOLD')
        self.assertEqual(body['code'],'DOCUMENT_INVALID');self.assertFalse(body['operational_GO']);self.assertEqual(out.stderr,b'')
    def test_finalizer_permits_only_exact_veto_entry(self):
        cf=self.f.loaded.modules['config_finalizer'];v=self.f.loaded.modules['veto_emitter'];config_fixture.f=cf;config_fixture.v=v
        f=config_fixture.FixtureBuilder('runTest');f.setUp();final=dict(f.template,veto_views={cf.FIRST:{'file':'actual-veto.md','sha256':'a'*64}})
        cf.verify_final_delta(f.template_raw,v.canonical(final)+b'\n',day=cf.FIRST,veto_file='actual-veto.md',veto_sha256='a'*64)
    def test_finalizer_document_pin_change_refused(self):
        cf=self.f.loaded.modules['config_finalizer'];v=self.f.loaded.modules['veto_emitter'];config_fixture.f=cf;config_fixture.v=v
        f=config_fixture.FixtureBuilder('runTest');f.setUp();final=json.loads(json.dumps(f.template));final['veto_views']={cf.FIRST:{'file':'actual-veto.md','sha256':'a'*64}};final['document_pins']['DUDU']['sha256']='b'*64
        with self.assertRaisesRegex(cf.Refused,'CONFIG_UNAUTHORIZED_DELTA'):cf.verify_final_delta(f.template_raw,v.canonical(final)+b'\n',day=cf.FIRST,veto_file='actual-veto.md',veto_sha256='a'*64)

class FamilyDelta(unittest.TestCase):
    def setUp(self):
        # Source helpers contain fixture constructors, no old test methods.
        import j_slot,finite_batch,veto_emitter,config_finalizer,folder_veto,fixture_builder_j1,fixture_builder_r3
        # Restore the normal package modules after temporary loader fixtures.
        for name in ('finite_batch','veto_emitter','consumer_codec','config_finalizer','folder_veto','j_slot'):
            sys.modules.pop(name,None)
        import importlib
        self.batch=importlib.import_module('finite_batch');self.j=importlib.import_module('j_slot')
        tmp=tempfile.TemporaryDirectory();self.tmp=tmp;self.root=Path(tmp.name).resolve();self.root.chmod(0o700)
        p=self.root/'attempts.ledger';p.write_bytes(b'');p.chmod(0o600)
        self.ledger=self.batch.DurableLedger(str(self.root),self.batch.measure_local_ledger(str(self.root)))
        self.family=self.j.claim_family(self.ledger,'a'*64,'b'*64)
    def tearDown(self):self.ledger.close();self.tmp.cleanup()
    def test_last_folder_recheck_refuses_veto_added_after_authority_before_file_creation(self):
        import folder_veto as folder,fixture_builder_j1 as jf,fixture_builder_r3 as cf
        import veto_emitter as v,config_finalizer as config
        jf.j,jf.v,jf.cf,jf.batch,jf.folder=self.j,v,config,self.batch,folder
        cf.f,cf.v=config,v
        fixture=jf.JFixtures('runTest');fixture.setUp();source=None
        try:
            fixture.ledger.claim((self.j.config.EPOCH,self.j.config.FIRST,'FIXTURE_LAST_GATE'),'a'*64,'b'*64,None)
            source=folder.FolderSource(fixture.source_raw,fixture.f.va,fixture.decision,fixture.owner,
                spec_sha256=v.digest(fixture.source_raw),binding=fixture.fa,clock=fixture.clock)
            original=source.observe();source.current()
            # Simulates an owner adding the veto during a later slow verifier;
            # no callback is allowed after the physical final recheck.
            (fixture.root/'veto'/'OWNER_VETO').write_bytes(b'SYNTHETIC-VETO')
            output=fixture.root/'docs'/'must-not-exist'
            with self.assertRaisesRegex(folder.Refused,'FOLDER_VETO_PRESENT'):
                self.j.stage_file(str(output),b'SYNTHETIC',folder.measure_folder(str(output.parent)),
                    owner_uid=os.geteuid(),effect_guard=lambda:self.j.immediate_effect_gate(source,None))
            self.assertFalse(output.exists());self.assertEqual(source.original,original)
        finally:
            if source is not None:source.close()
            fixture.tearDown()
    def test_family_terminal_requires_private_owner_and_exact_schema(self):
        with self.assertRaisesRegex(self.batch.Hold,'TERMINAL_PARENT_CAPABILITY_REQUIRED'):
            self.ledger.finish_family(self.family.key,{'status':'COMPLETE'})
        self.j.finish_family(self.family,self.j.SlotResult('REFUSED','NEW_FIXTURE_REFUSAL',self.family.key))
        rows,_=self.ledger._rows();terminal=[r for r in rows if r['kind']=='TERMINAL'][0]
        self.assertEqual(terminal['data']['schema'],'L12_J_FAMILY_TERMINAL_CANDIDATE_V1');self.assertFalse(terminal['data']['result']['operational_GO'])
        self.assertNotIn('nonce',self.batch.canonical(terminal['data']).decode())
    def test_family_cannot_issue_core_original_complete(self):
        with self.assertRaisesRegex(self.batch.Hold,'TERMINAL_RESULT_INVALID'):
            self.ledger.finish(self.family.key,{'status':'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE'},terminal_permit=self.family.permit)
    def test_private_terminal_owner_cannot_be_reused(self):
        out=self.j.SlotResult('REFUSED','NEW_FIXTURE_REFUSAL',self.family.key);self.j.finish_family(self.family,out)
        with self.assertRaisesRegex(self.j.Refused,'J_FAMILY_RESERVATION_UNBOUND'):self.j.finish_family(self.family,out)
    def test_another_bound_cannot_reset_the_consumed_shared_family(self):
        self.j.finish_family(self.family,self.j.SlotResult('REFUSED','NEW_FIXTURE_REFUSAL',self.family.key))
        with self.assertRaisesRegex(self.batch.ReservationFailure,'ATTEMPT_CONSUMED_BY_OTHER_BOUND'):self.j.claim_family(self.ledger,'c'*64,'d'*64)

class J4ReceiptDelta(unittest.TestCase):
    def test_full_writer_original_survives_private_family_terminal(self):
        # One new compatibility path for the changed terminal API. This is a
        # synthetic writer, no image import/DB/production effect or old suite.
        import importlib,fixture_builder_j1 as jf
        for name in ('finite_batch','veto_emitter','consumer_codec','config_finalizer','folder_veto','j_slot'):sys.modules.pop(name,None)
        j=importlib.import_module('j_slot');v=importlib.import_module('veto_emitter');cf=importlib.import_module('config_finalizer');batch=importlib.import_module('finite_batch');folder=importlib.import_module('folder_veto')
        jf.j,jf.v,jf.cf,jf.batch,jf.folder=j,v,cf,batch,folder
        config_fixture.f,config_fixture.v=cf,v
        support.j,support.v=j,v
        helper=support.PeerDelta('runTest');helper.setUp();f=helper.f
        try:
            f.rule['process_candidate_pins']={}
            result=f.run_slot();self.assertEqual(result.status,'COMPLETE');self.assertEqual(result.mode,'FIXTURE')
            self.assertIsNotNone(result.writer_receipt_raw);self.assertEqual(v.digest(result.writer_receipt_raw),result.writer_receipt_sha256)
            rows,_=f.ledger._rows();terminal=[r for r in rows if r['kind']=='TERMINAL'][0]['data']
            self.assertEqual(terminal['schema'],'L12_J_FAMILY_TERMINAL_CANDIDATE_V1')
            self.assertEqual(base64.b64decode(terminal['result']['writer_receipt_base64']),result.writer_receipt_raw)
            self.assertFalse(result.operational_GO)
        finally:helper.tearDown()

class WatchdogAndBudgetDelta(unittest.TestCase):
    def test_post_observation_work_is_included_in_projected_mark(self):
        fixture=HotFixture()
        try:
            s=fixture.session_new();s.warm();observed=hot.utc_now();time.sleep(.30)
            s.start_image(observed,observed+timedelta(seconds=10));now,tick=hot.utc_now(),time.monotonic()
            self.assertGreater(tick-s.image_mark,.29)
            self.assertLess(abs((now-observed).total_seconds()-(tick-s.image_mark)),.025)
        finally:fixture.close()
    def test_general_age_checked_at_each_file_effect_without_callback(self):
        fixture=HotFixture()
        try:
            s=fixture.session_new();s.warm();observed=hot.utc_now();s.start_image(observed,observed+timedelta(seconds=10))
            j=fixture.loaded.modules['j_slot'];folder=fixture.loaded.modules['folder_veto']
            output=fixture.root/'new-output';expected=folder.measure_folder(str(fixture.root));s.general['observed_at']=hot.iso(hot.utc_now()-timedelta(seconds=6))
            with self.assertRaisesRegex(hot.Refused,'HOT_GENERAL_STALE_OR_FUTURE'):
                j.stage_file(str(output),b'SYNTHETIC',expected,owner_uid=os.geteuid(),effect_guard=s.effect_time_only)
            self.assertFalse(output.exists())
        finally:fixture.close()
    def test_independent_watchdog_kills_own_fixture_group_while_parent_blocked_in_native_code(self):
        # The test process creates its OWN session; Codex/user/production group
        # is never targeted. No app or authority module is imported in it.
        raw=(HERE/'hot_watchdog.py').read_bytes()
        driver="""import os,sys,time,ctypes\nfrom datetime import timedelta\nos.setsid()\nfrom types import ModuleType\nm=ModuleType('fixture_dog')\nsys.modules[m.__name__]=m\nexec(%r,m.__dict__)\ndog=m.ImageWatchdog(m.utc_now()+timedelta(seconds=3),fixture_own_group=True)\nnow=m.utc_now();dog.start(now,now+timedelta(seconds=.25))\nprint('FIXTURE_DOG_READY',flush=True)\nctypes.CDLL(None).sleep(3)\nprint('BAD_NATIVE_CALLBACK_RETURNED',flush=True)\n"""%raw
        begin=time.monotonic();out=subprocess.run([sys.executable,'-I','-B','-'],input=driver.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=4)
        self.assertEqual(out.returncode,-9);self.assertEqual(out.stdout,b'FIXTURE_DOG_READY\n');self.assertEqual(out.stderr,b'');self.assertLess(time.monotonic()-begin,1.5)
    def test_outer_operation_other_than_admission_cannot_supply_the_reservation(self):
        fixture=HotFixture()
        try:
            fixture.loaded.close();r=fixture.registry;records=r['originals']
            def put(name,raw):
                p=Path(records[name]['path']);p.write_bytes(raw);records[name]=record(p)
            authority,runtime=(b'SYNTHETIC-AUTHORITY',b'SYNTHETIC-RUNTIME');r['authority_sha256']=hot.sha(authority)
            for name,raw in [('authority',authority),('runtime',runtime)]:put(name,raw)
            q={'schema':'L12_FINITE_BATCH_REQUEST_CANDIDATE_V1','lane':'DOWNSTREAM_AFTER_E6','epoch':r['epoch'],'session':r['day'],'previous_session':'2026-10-09','track':'P',
                'prepared_at':'2026-10-11T20:00:00Z','owner_deadline':'2026-10-12T00:45:00Z','authority_sha256':r['authority_sha256'],'runtime_sha256':hot.sha(runtime),
                'veto_authority_sha256':r['general_authority_sha256'],'initial_receipts':{'commit_result':'a'*64,'publish_launch':'b'*64},
                'tasks':[{'operation':'e6','not_before':'2026-10-12T10:20:00Z','not_after':'2026-10-12T10:25:00Z','budget_seconds':60,'requires':['commit_result','publish_launch']},
                         {'operation':'admission_manifest','not_before':'2026-10-12T10:38:00Z','not_after':'2026-10-12T10:39:00Z','budget_seconds':20,'requires':['e6']}]}
            request=hot.canonical(q)
            # Synthetic owner-vector solely to reach the pure wrong-scope
            # guard. FIXTURE bridge, no authority callback/effect is called.
            owner=hot.canonical({'schema':'L12_OWNER_RECORD_CANDIDATE_V1','answer':'Assino','channel':'REGISTRO_PELA_FABLE',
                'request_sha256':hot.sha(request),'question_sha256':'c'*64,'question_published_at':'2026-10-11T20:00:10Z','signed_at':'2026-10-11T20:00:20Z'})
            put('owner',owner);put('request',request);put('bound',hot.canonical({'schema':'L12_BOUND_CANDIDATE_V1','request_sha256':hot.sha(request),
                'documents_sha256':{'owner':hot.sha(owner),'authority':hot.sha(authority),'runtime':hot.sha(runtime)},'bound_at':'2026-10-11T20:01:00Z'}))
            r['not_before'],r['not_after']='2026-10-12T10:38:00Z','2026-10-12T10:39:00Z';r['outer_scope']=[r['epoch'],r['day'],'2026-10-09','P','capture_launch']
            fixture.loaded=hot.LoadedSet(hot.canonical(r))
            with self.assertRaisesRegex(ValueError,'HOT_OUTER_OPERATION_SCOPE'):worker.run_loaded(fixture.loaded)
            self.assertEqual(fixture.loaded.modules['authority_bridge'].CALLS,[])
        finally:fixture.close()


if __name__=='__main__':unittest.main()
