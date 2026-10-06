"""Real candidate helpers with frozen fixture functions; all receipts here are synthetic.
No Native, commands, subprocess, network, host binding or operational authority.
"""
import argparse,ast,copy,hashlib,json,stat,sys,types,unittest
import xml.etree.ElementTree as ET
from datetime import datetime,timedelta,timezone
from functools import lru_cache
from pathlib import Path

SHA=lambda raw:hashlib.sha256(raw).hexdigest()
INPUTS={}
def read(path):
    raw=Path(path).read_bytes();INPUTS[str(path)]=SHA(raw);return raw
def stamp(text):return datetime.fromisoformat('2026-10-06T'+text+'+00:00')
def window(text,minutes=5):
    start=stamp(text);end=start+timedelta(minutes=minutes)
    return dict(start=start,end=end,gate_start=start,gate_end=end)
def clock(a,z):return dict(utc_start=stamp(a).isoformat(),utc_end=stamp(z).isoformat())
def pre_context():
    c=fx['context']();c['window']=window('12:26:00')
    c['receipts']['TREE_PRE']['clock']=clock('12:20:00','12:21:00')
    for role in ('E0','POST'):c['receipts'][role]['clock']=clock('11:40:00','11:41:00')
    return c
def k3_context():
    c=fx['k3_context']();c['window']=window('12:38:00')
    c['receipts']['TREE_PRE']['clock']=clock('12:20:00','12:21:00')
    for role in ('E0','POST'):c['receipts'][role]['clock']=clock('11:40:00','11:41:00')
    c['receipts']['BOOTSTRAP']['clock']=clock('12:26:00','12:26:15')
    return c
def env_context():
    c=fx['env_context']();c['window']=window('22:20:00')
    c['receipts']['BOOTSTRAP']['clock']=clock('12:26:00','12:26:15')
    k=c['receipts']['K3'];k['clock']=clock('12:31:05','12:31:15')
    request=b.strict_json(c['blobs']['K3']['request'],'TEST_REQUEST')
    request['not_before']=stamp('12:31:00').isoformat();request['not_after']=stamp('12:36:00').isoformat()
    raw=b.canonical(request);c['blobs']['K3']['request']=raw;k['request_sha256']=b.sha(raw)
    return c

def e0_context(at):
    raw=read(RUNTIME/'test-inputs/k9_runner.rev2-563a4797/k9_runner.py')
    boot=fx['BOOT'];return {'operation':b.K4E0_OPERATION,'plan':{'parent':fx['chain']('/var/lib'),'runner':{'path':b.K9_RUNNER_PATH%b.K9_RUNNER_SHA256,'sha256':b.K9_RUNNER_SHA256,'bytes':len(raw)},'evidence_boot_id_sha256':boot},'rt':{'source':mods['k4_e0']},'entries':[{'role':'PRE','operation':b.PRECHECK_OPERATION}],'receipts':{'PRE':{'operation':b.PRECHECK_OPERATION,'effects':{'evidence_boot_id_sha256':boot}}},'evidence_facts':[{'role':'PRE','complete':True}],'window':window(at),'watchdog':80,'inputs':{'runner':raw}}
def policy_context():
    worker='d2'*32;boot=fx['BOOT'];operation='GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01';m=mods['k3_secret_env'];rows=fx['chain']('/etc/c3po-reader')
    c={'operation':operation,'plan':{'worker_container_id':worker,'evidence_boot_id_sha256':boot,'config_chain':rows},'entries':[],'receipts':{},'evidence_facts':[],'copied':[],'rt':{'source':m},'window':window('22:26:00'),'watchdog':80,'mode':b.REHEARSAL,'params':{},'request':{'writes_allowed':True}}
    def add(role,op,r):c['entries'].append({'role':role,'operation':op});c['receipts'][role]=r;c['evidence_facts'].append({'role':role,'complete':True})
    add('PROVISION',m.PROVISION_OPERATION,{'operation':m.PROVISION_OPERATION,'effects':{'evidence_boot_id_sha256':boot},'items':{'config_chain':copy.deepcopy(rows)}})
    add('POST',m.EPOCH_READBACK_OPERATION,{'operation':m.EPOCH_READBACK_OPERATION,'effects':{'evidence_boot_id_sha256':boot}})
    add('POLICY_NEW',b.K9R_OPERATION,{'operation':b.K9R_OPERATION,'mode':'POLICY','boot_id_sha256':boot,'findings':[],'effects':{'mode':'POLICY','evidence_boot_id_sha256':boot},'items':{'worker':{'status':'COMPLETE','running':True,'state':'running','image_id_equal_signed':True,'container_id':worker},'boot':{'status':'COMPLETE','equal_to_the_evidence':True}},'clock':clock('22:10:00','22:10:05')})
    c['copied']=[{'plan_pointer':'/config_chain','evidence_role':'PROVISION','receipt_pointer':'/items/config_chain'},{'plan_pointer':'/worker_container_id','evidence_role':'POLICY_NEW','receipt_pointer':'/items/worker/container_id'},{'plan_pointer':'/evidence_boot_id_sha256','evidence_role':'POLICY_NEW','receipt_pointer':'/boot_id_sha256'}];return c

def a7_boot_context():
    c=policy_context();c['entries']=[r for r in c['entries'] if r['role']!='POLICY_NEW'];c['evidence_facts']=[r for r in c['evidence_facts'] if r['role']!='POLICY_NEW'];del c['receipts']['POLICY_NEW']
    e=env_context();c['window']=window('12:46:00');c['plan']['worker_container_id']=fx['WORKER'];c['blobs']={}
    for role in ('BOOTSTRAP','K3'):
        c['entries']+=copy.deepcopy([r for r in e['entries'] if r['role']==role]);c['evidence_facts']+=copy.deepcopy([r for r in e['evidence_facts'] if r['role']==role]);c['receipts'][role]=copy.deepcopy(e['receipts'][role]);c['blobs'][role]=copy.deepcopy(e['blobs'][role])
    c['copied']=[r for r in c['copied'] if r['plan_pointer']=='/config_chain']+copy.deepcopy(e['copied']);return c

class Controls(unittest.TestCase):
    def refuse(self,call,code):
        with self.assertRaises(b.Refused) as caught:call()
        self.assertEqual(str(caught.exception),code)
    def test_boot_exact_morning_window(self):b.bootstrap_first_night({'window':window('12:26:00')},True)
    def test_boot_current_RULES_positive_no_future_boot(self):
        c=pre_context();before=copy.deepcopy(c);result=b.RULES_OF[b.BOOTSTRAP_OPERATION](c)
        self.assertFalse(result['bootstrap_identity']['tree_complete']);self.assertEqual(c,before)
    def test_boot_future_boot_citation_refused(self):
        c=pre_context();fx['add_receipt'](c,'BOOTSTRAP',b.BOOTSTRAP_OPERATION,fx['bootstrap_receipt']())
        self.refuse(lambda:b.RULES_OF[b.BOOTSTRAP_OPERATION](c),'BOOTSTRAP_PREPARE_CANNOT_CITE_BOOTSTRAP')
    def test_boot_morning_sendable_floor(self):
        w=window('12:26:00');self.assertGreaterEqual(b.k9_sendable_seconds(w['start'],w['end']-timedelta(seconds=80),False),180)
    def test_boot_complete_morning_observation(self):
        c=k3_context();before=copy.deepcopy(c);answer=b.bootstrap_complete_identity(c)
        self.assertEqual(answer['container_id'],fx['WORKER']);self.assertEqual(c,before)
    def test_boot_previous_night_receipt_refused(self):
        c=k3_context();c['receipts']['BOOTSTRAP']['clock']=clock('21:53:00','21:53:15')
        self.refuse(lambda:b.bootstrap_complete_identity(c),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    def test_boot_missing_absence_refused(self):
        c=k3_context();c['receipts']['BOOTSTRAP']['items']['directory:EMITTER']['absence_confirmed']=False
        self.refuse(lambda:b.bootstrap_complete_identity(c),'BOOTSTRAP_ABSENCE_NOT_POSITIVELY_CONFIRMED')
    def test_boot_claim_not_durable_refused(self):
        c=k3_context();c['receipts']['BOOTSTRAP']['claim']['file_fsync']=False
        self.refuse(lambda:b.bootstrap_complete_identity(c),'BOOTSTRAP_CLAIM_NOT_DURABLE_COMPLETE')
    def test_boot_signed_effects_do_not_substitute_observation(self):
        c=k3_context();c['receipts']['BOOTSTRAP']['items']['worker']['container_id']='d2'*32
        self.refuse(lambda:b.bootstrap_complete_identity(c),'BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT')
    def test_boot_nonempty_stderr_refused(self):
        c=k3_context();c['evidence_facts'][-1]['bound_set']['stderr_empty']=False
        self.refuse(lambda:b.bootstrap_complete_identity(c),'BOOTSTRAP_EVIDENCE_NOT_BOUND')
    def test_k3_full_current_RULES_morning_positive(self):
        c=k3_context();before=copy.deepcopy(c);result=b.RULES_OF[b.K3K9_OPERATION](c)
        self.assertEqual(result['k9_prerequisite']['identity_source'],'BOOTSTRAP_IDENTITY_OBSERVED');self.assertEqual(c,before)
    def test_k3_before_boot_end_refused(self):
        c=k3_context();c['window']=window('12:30:59')
        self.refuse(lambda:b.RULES_OF[b.K3K9_OPERATION](c),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    def test_k3_after_morning_band_refused(self):
        c=k3_context();c['window']=window('15:30:00')
        self.refuse(lambda:b.RULES_OF[b.K3K9_OPERATION](c),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    def test_k3_boot_prior_provenance_refused(self):
        c=k3_context();c['copied']=[x for x in c['copied'] if x['plan_pointer']!='/worker_container_id']
        self.refuse(lambda:b.RULES_OF[b.K3K9_OPERATION](c),'BOOTSTRAP_IDENTITY_NOT_EXACT_COPIES')
    def test_a7_same_worker_chain_helper_accepts_evening(self):
        c=env_context();before=copy.deepcopy(c);answer=b.reader_install_rules(c)
        self.assertEqual(answer['identity_observed_role'],'BOOTSTRAP');self.assertFalse(answer['k3_effects_are_independent_observation']);self.assertEqual(c,before)
    def test_a7_recreated_plan_worker_refused(self):
        c=env_context();c['plan']['worker_container_id']='d2'*32
        self.refuse(lambda:b.reader_install_rules(c),'BOOTSTRAP_IDENTITY_NOT_EXACT_COPIES')
    def test_a7_new_worker_signed_k3_effect_is_not_observation(self):
        c=env_context();c['receipts']['K3']['effects']['values']['provider_env']['container_id']='d2'*32
        self.refuse(lambda:b.reader_install_rules(c),'BOOTSTRAP_K3_CHAIN_NOT_SAME_IDENTITY')
    def test_a7_different_boot_refused(self):
        c=env_context();c['plan']['evidence_boot_id_sha256']='d2'*32
        self.refuse(lambda:b.reader_install_rules(c),'BOOTSTRAP_IDENTITY_NOT_OBSERVED_SAME_BOOT')
    def test_a7_unlinked_k3_receipt_refused(self):
        c=env_context();r=b.strict_json(c['blobs']['K3']['request'],'TEST_REQUEST');r['evidence'][0]['receipt_sha256']='a1'*32
        raw=b.canonical(r);c['blobs']['K3']['request']=raw;c['receipts']['K3']['request_sha256']=b.sha(raw)
        self.refuse(lambda:b.reader_install_rules(c),'BOOTSTRAP_K3_CHAIN_NOT_LINKED')
    def test_prerequisite_earliest_proposed_band(self):
        c={'window':window('11:26:00'),'watchdog':80};self.assertGreaterEqual(b.k9_prerequisite_window(c,(b.BOOTSTRAP_DAY,),b.BOOTSTRAP_MORNING_BAND),180)
    def test_prerequisite_late_window_below_sendable_refused(self):
        c={'window':window('15:25:00'),'watchdog':80};self.refuse(lambda:b.k9_prerequisite_window(c,(b.BOOTSTRAP_DAY,),b.BOOTSTRAP_MORNING_BAND),'K9_SENDABLE_SECONDS_BELOW_180')
    def test_prerequisite_before_proposed_band_refused(self):
        c={'window':window('11:25:59'),'watchdog':80};self.refuse(lambda:b.k9_prerequisite_window(c,(b.BOOTSTRAP_DAY,),b.BOOTSTRAP_MORNING_BAND),'K9_PREREQUISITE_WINDOW_NOT_IN_ITS_BAND')
    def test_prerequisite_wrong_utc_day_refused(self):
        c={'window':window('11:26:00'),'watchdog':80};c['window']={k:v+timedelta(days=1) for k,v in c['window'].items()}
        self.refuse(lambda:b.k9_prerequisite_window(c,(b.BOOTSTRAP_DAY,),b.BOOTSTRAP_MORNING_BAND),'K9_PREREQUISITE_WINDOW_NOT_IN_ITS_BAND')

    def test_k3_immediate_postboot_window_below_sendable_refused(self):
        c=k3_context();c['window']=window('12:31:00')
        self.refuse(lambda:b.RULES_OF[b.K3K9_OPERATION](c),'K9_SENDABLE_SECONDS_BELOW_180')
    def test_e0_morning_band_current_rule_accepts(self):
        c=e0_context('11:26:00');self.assertEqual(b.RULES_OF[b.K4E0_OPERATION](c)['k9_prerequisite']['program'],'K4E0')
    def test_e0_previous_evening_day06_preserved(self):
        c=e0_context('21:53:00');self.assertEqual(b.RULES_OF[b.K4E0_OPERATION](c)['k9_prerequisite']['program'],'K4E0')
    def test_e0_other_utc_day_retains_old_band(self):
        c=e0_context('21:53:00');c['window']={k:v-timedelta(days=1) for k,v in c['window'].items()}
        self.assertEqual(b.RULES_OF[b.K4E0_OPERATION](c)['k9_prerequisite']['program'],'K4E0')
    def test_a7_POLICY_branch_new_observed_worker_accepts_full_binding_rules(self):
        c=policy_context();before=copy.deepcopy(c['receipts']);answer=b.RULES_OF[c['operation']](c)
        self.assertEqual(answer['sealed_program']['extra']['copies'][0]['evidence_role'],'POLICY_NEW');self.assertEqual(c['receipts'],before)
    def test_a7_POLICY_typed_worker_copy_refused(self):
        c=policy_context();c['copied']=[r for r in c['copied'] if r['plan_pointer']!='/worker_container_id']
        self.refuse(lambda:b.RULES_OF[c['operation']](c),'POLICY_IDENTITY_NOT_EXACT_COPIES')
    def test_a7_POLICY_observation_wrong_boot_refused(self):
        c=policy_context();c['receipts']['POLICY_NEW']['boot_id_sha256']='d2'*32;c['receipts']['POLICY_NEW']['effects']['evidence_boot_id_sha256']='d2'*32
        self.refuse(lambda:b.RULES_OF[c['operation']](c),'EVIDENCE_NOT_OF_THE_SAME_BOOT')
    def test_a7_POLICY_observation_not_running_refused(self):
        c=policy_context();c['receipts']['POLICY_NEW']['items']['worker']['running']=False
        self.refuse(lambda:b.RULES_OF[c['operation']](c),'POLICY_IDENTITY_NOT_COMPLETE')
    def test_policy_D06_evening_refused_by_real_K9_day_window(self):
        self.refuse(lambda:b.k9_day_window('2026-10-06','POLICY',stamp('22:10:00'),stamp('22:15:00'),None),'K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    def test_policy_D07_before_midnight_refused_by_real_K9_day_window(self):
        self.refuse(lambda:b.k9_day_window('2026-10-07','POLICY',stamp('22:10:00'),stamp('22:15:00'),None),'K9_WINDOW_NOT_IN_THE_EVE_OR_MORNING_OF_THE_DAY')
    def test_policy_D06_morning_allowed_by_real_K9_day_window(self):
        b.k9_day_window('2026-10-06','POLICY',stamp('12:38:00'),stamp('12:43:00'),None)

    def test_a7_full_RULES_morning_after_k3_same_worker(self):
        c=a7_boot_context();before=copy.deepcopy(c['receipts']);mods['k3_secret_env'].validate_plan(c['plan']);answer=b.RULES_OF[c['operation']](c)
        self.assertEqual(answer['sealed_program']['extra']['identity_observed_role'],'BOOTSTRAP');self.assertEqual(c['receipts'],before)
    def test_a7_full_RULES_recreated_worker_still_refused(self):
        c=a7_boot_context();c['plan']['worker_container_id']='d2'*32
        self.refuse(lambda:b.RULES_OF[c['operation']](c),'BOOTSTRAP_IDENTITY_NOT_EXACT_COPIES')
    def test_e0_corridor_between_bands_refused(self):
        c=e0_context('16:26:00');self.refuse(lambda:b.RULES_OF[b.K4E0_OPERATION](c),'K9_PREREQUISITE_WINDOW_NOT_IN_ITS_BAND')
    def test_e0_other_day_morning_not_added(self):
        c=e0_context('11:26:00');c['window']={k:v+timedelta(days=1) for k,v in c['window'].items()}
        self.refuse(lambda:b.RULES_OF[b.K4E0_OPERATION](c),'K9_PREREQUISITE_WINDOW_NOT_IN_ITS_BAND')
    def test_k3_corridor_between_bands_refused(self):
        c=k3_context();c['window']=window('16:26:00');self.refuse(lambda:b.RULES_OF[b.K3K9_OPERATION](c),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    def test_a7_corridor_between_bands_refused(self):
        c=a7_boot_context();c['window']=window('16:26:00');self.refuse(lambda:b.RULES_OF[c['operation']](c),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    def test_k3_old_night_band_preserved_with_morning_boot(self):
        c=k3_context();c['window']=window('21:53:00');self.assertEqual(b.RULES_OF[b.K3K9_OPERATION](c)['k9_prerequisite']['program'],'K3K9')
    def test_k3_after_morning_end_before_night_refused(self):
        c=k3_context();c['window']=window('15:29:59');self.refuse(lambda:b.RULES_OF[b.K3K9_OPERATION](c),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    def test_generic_boot_dependent_other_day_refused(self):
        c={'window':window('12:38:00')};c['window']={k:v+timedelta(days=1) for k,v in c['window'].items()};self.refuse(lambda:b.bootstrap_first_night(c),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    def test_old_boot_exact_night_request_refused(self):
        self.refuse(lambda:b.bootstrap_first_night({'window':window('21:53:00')},True),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')

for field,delta in [('start',-1),('end',1),('gate_start',1),('gate_end',-1)]:
    def bad(self,field=field,delta=delta):
        c={'window':window('12:26:00')};c['window'][field]+=timedelta(seconds=delta)
        self.refuse(lambda:b.bootstrap_first_night(c,True),'BOOTSTRAP_WINDOW_NOT_FIRST_NIGHT')
    setattr(Controls,'test_boot_exact_'+field+'_mismatch_refused',bad)

class RecordResult(unittest.TestResult):
    def __init__(self):super().__init__();self.rows=[]
    def addSuccess(self,test):super().addSuccess(test);self.rows.append((test.id(),'PASS',''))
    def addFailure(self,test,err):super().addFailure(test,err);self.rows.append((test.id(),'FAIL',self._exc_info_to_string(err,test)))
    def addError(self,test,err):super().addError(test,err);self.rows.append((test.id(),'ERROR',self._exc_info_to_string(err,test)))
    def addSkip(self,test,reason):super().addSkip(test,reason);self.rows.append((test.id(),'SKIP',reason))


# Portable test integration of the exact48 public controls; own synthetic contexts only.
import helpers as _portable_helpers
import test_bootstrap_identity_binding as _portable_fixture
b=_portable_helpers.b
fx={name:getattr(_portable_fixture,name) for name in ('context','k3_context','env_context','BOOT','WORKER','chain','add_receipt','bootstrap_receipt')}
RUNTIME=Path(__file__).resolve().parents[2]
mods={}
for _family,_path in [('k4_e0',RUNTIME/'test-inputs/k4_e0.sealed-63c75348/build/k4_e0.py'),('k3_secret_env',RUNTIME/'test-inputs/programs-final-candidate/k3_secret_env/build/k3_secret_env.py')]:
    _buf=_path.read_bytes()
    _mod=types.ModuleType('portable_actual_'+_family);_mod.__file__=str(_path);sys.modules[_mod.__name__]=_mod
    exec(compile(_buf,str(_path),'exec'),_mod.__dict__);mods[_family]=_mod
