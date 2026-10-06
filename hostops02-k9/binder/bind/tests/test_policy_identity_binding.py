"""Positive and adversarial identity provenance from one exact POLICY receipt; no host."""
from datetime import datetime,timezone
import copy,pytest
import helpers as h
b=h.b
BOOT='b0'*32
ID='c1'*32

def context():
    receipt={'operation':b.K9R_OPERATION,'mode':'POLICY','boot_id_sha256':BOOT,'findings':[],
      'effects':{'mode':'POLICY','evidence_boot_id_sha256':BOOT},
      'items':{'worker':{'status':'COMPLETE','running':True,'state':'running','image_id_equal_signed':True,'container_id':ID},'boot':{'status':'COMPLETE','equal_to_the_evidence':True}},
      'clock':{'utc_start':'2026-10-05T20:00:00+00:00','utc_end':'2026-10-05T20:00:05+00:00'}}
    return {'plan':{'worker_container_id':ID,'evidence_boot_id_sha256':BOOT},
      'entries':[{'role':'R','operation':b.K9R_OPERATION}],'receipts':{'R':receipt},
      'evidence_facts':[{'role':'R','complete':True}],
      'copied':[{'plan_pointer':'/worker_container_id','evidence_role':'R','receipt_pointer':'/items/worker/container_id'},
                {'plan_pointer':'/evidence_boot_id_sha256','evidence_role':'R','receipt_pointer':'/boot_id_sha256'}],
      'window':{'start':datetime(2026,10,5,20,38,tzinfo=timezone.utc)}}

def test_exact_same_policy_identity_positive():
    assert b.policy_worker_identity(context())['evidence_role']=='R'

@pytest.mark.parametrize('change,code',[
 ('absent','POLICY_IDENTITY_NOT_ONE_READ'),('duplicate','POLICY_IDENTITY_NOT_ONE_READ'),
 ('partial','POLICY_IDENTITY_NOT_COMPLETE'),('findings','POLICY_IDENTITY_NOT_COMPLETE'),
 ('worker_unavailable','POLICY_IDENTITY_NOT_COMPLETE'),('boot_unavailable','POLICY_IDENTITY_NOT_COMPLETE'),
 ('boot_false','POLICY_IDENTITY_NOT_COMPLETE'),('effects_mode','POLICY_IDENTITY_NOT_COMPLETE'),
 ('running_false','POLICY_IDENTITY_NOT_COMPLETE'),('state_wrong','POLICY_IDENTITY_NOT_COMPLETE'),('image_false','POLICY_IDENTITY_NOT_COMPLETE'),('findings_missing','POLICY_IDENTITY_NOT_COMPLETE'),
 ('clock_naive','POLICY_IDENTITY_CLOCK_INVALID'),('clock_reversed','POLICY_IDENTITY_CLOCK_INVALID'),
 ('worker_missing','POLICY_IDENTITY_NOT_THE_PLAN'),('boot_missing','POLICY_IDENTITY_NOT_THE_PLAN'),
 ('boot_mismatch','POLICY_IDENTITY_NOT_THE_PLAN'),('effects_boot','POLICY_IDENTITY_NOT_THE_PLAN'),
 ('id_mismatch','POLICY_IDENTITY_NOT_THE_PLAN'),('typed','POLICY_IDENTITY_NOT_EXACT_COPIES'),
 ('split_roles','POLICY_IDENTITY_NOT_EXACT_COPIES'),('wrong_pointer','POLICY_IDENTITY_NOT_EXACT_COPIES'),
 ('duplicate_copy','POLICY_IDENTITY_NOT_EXACT_COPIES'),('late','READER_PREDECESSOR_NOT_FINISHED')])
def test_policy_identity_refuses_unproved_or_rebound_values(change,code):
    c=context();r=c['receipts']['R']
    if change=='absent':c['entries']=[]
    if change=='duplicate':c['entries'].append(dict(c['entries'][0],role='P'));c['receipts']['P']=copy.deepcopy(r)
    if change=='partial':c['evidence_facts'][0]['complete']=False
    if change=='findings':r['findings']=['EVIDENCE_FROM_EARLIER_BOOT']
    if change=='worker_unavailable':r['items']['worker']['status']='UNAVAILABLE'
    if change=='boot_unavailable':r['items']['boot']['status']='UNAVAILABLE'
    if change=='boot_false':r['items']['boot']['equal_to_the_evidence']=False
    if change=='effects_mode':r['effects']['mode']='TREE'
    if change=='worker_missing':del r['items']['worker']['container_id']
    if change=='boot_missing':del r['boot_id_sha256']
    if change=='boot_mismatch':r['boot_id_sha256']='a1'*32
    if change=='effects_boot':r['effects']['evidence_boot_id_sha256']='a1'*32
    if change=='id_mismatch':r['items']['worker']['container_id']='a1'*32
    if change=='typed':c['copied']=[]
    if change=='split_roles':c['copied'][1]['evidence_role']='TREE'
    if change=='wrong_pointer':c['copied'][1]['receipt_pointer']='/effects/evidence_boot_id_sha256'
    if change=='duplicate_copy':c['copied'].append(dict(c['copied'][0]))
    if change=='running_false':r['items']['worker']['running']=False
    if change=='state_wrong':r['items']['worker']['state']='exited'
    if change=='image_false':r['items']['worker']['image_id_equal_signed']=False
    if change=='findings_missing':del r['findings']
    if change=='clock_naive':r['clock']['utc_start']='2026-10-05T20:00:00'
    if change=='clock_reversed':r['clock']['utc_start']='2026-10-05T20:01:00+00:00'
    if change=='late':r['clock']['utc_end']='2026-10-05T21:00:00+00:00'
    with h.refused(code):b.policy_worker_identity(c)
