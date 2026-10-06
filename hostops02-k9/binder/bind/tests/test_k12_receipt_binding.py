"""K12 binder rules on synthetic documents rebuilt by the pinned real tool; no host/gate approval."""
from datetime import datetime,timezone
from pathlib import Path
import base64,json,copy
import pytest
import helpers as h
from calendar_fixture_selection import fixture_root
from test_programs import programs,program_seals
b=h.b
ROOT=h.BIND.parent/'test-inputs/k12-documents'
BOOT='b0'*32

def context(programs, root=ROOT):
 ROOT=root
 docs=b.k8_listed_bytes(ROOT/'out-primary');summary=json.loads(docs['SUMMARY.json']);roles=summary['roles']
 raw=docs[roles['request']];request=json.loads(raw)
 files=[]
 for role in ('template','go_admission_record','go_bar_manifest_record','publication_bar_manifest','go_admission','go_bar_manifest','capacity_config','veto_view'):
  body=docs[roles[role]];key=role+':primary' if role in ('capacity_config','veto_view') else role
  files.append({'key':key,'sha256':b.sha(body),'bytes':len(body)})
 delivery={'operation':b.K8_DELIVERY,'outcome':'EVE_DAY_DOCUMENTS_AND_PAYLOAD_DELIVERED_READ_BACK','boot_id_sha256':BOOT,
  'clock':{'utc_end':'2026-10-05T23:55:00+00:00'},'effects':{'day':'2026-10-06','files':files,'contract':{'sha256':b.sha(docs[roles['contract']])}}}
 tree={'operation':b.K12_C,'mode':'TREE','outcome':'K12_OBSERVED_AS_REQUIRED','boot_id_sha256':BOOT,
  'observed_rows':{'config':[{'path':'/var/lib/c3po-capacity/config','device':1,'inode':2}]},'clock':{'utc_end':'2026-10-06T10:00:00+00:00'}}
 return {'operation':b.K12_W,'plan':{'mode':'LAUNCH','capacity_request':{'b64':base64.b64encode(raw).decode(),'sha256':b.sha(raw)},
  'parent_rows':copy.deepcopy(tree['observed_rows']),'evidence_boot_id_sha256':BOOT},'inputs':{'k12_request':raw},
  'rt':{'source':programs.modules[b.K12_W][2]['source']},'params':{'k12_document_set':{'directory':str((ROOT/'out-primary').resolve()),'chain_directory':str((ROOT/'chain').resolve())}},
  'base':ROOT,'window':{'start':datetime(2026,10,6,10,38,tzinfo=timezone.utc)},
  'receipts':{'TREE':tree,'E6':delivery},'entries':[{'role':'TREE','operation':b.K12_C},{'role':'E6','operation':b.K8_DELIVERY}],
  'evidence_facts':[{'role':'TREE','complete':True},{'role':'E6','complete':True}]}

def checker(bundle,documents,chain):
 s=json.loads(documents['SUMMARY.json'])
 return {'status':'VERIFIED','kind':'CAPACITY_DAY','summary':'REBUILT_EQUAL','documentary_authority':'VERIFIED','day':s['day'],'window':s['window'],'sha256sums_sha256':b.sha(documents['SHA256SUMS'])}

def test_actual_k12_parser_accepts_tool_generated_request(programs):
 ctx=context(programs);raw,request,derived=ctx['rt']['source'].k12_capacity_request(ctx['plan']['capacity_request'])
 assert raw==ctx['inputs']['k12_request'] and derived['sha256']==b.sha(raw)

def test_window_ties_document_bytes_to_complete_tree_and_k8_delivery(programs,monkeypatch):
 monkeypatch.setattr(b,'k8_run_verifier',checker)
 result=b.k12_rules(context(programs));assert result['tree_role']=='TREE' and result['documents']['delivery_role']=='E6'

@pytest.mark.parametrize('change,code',[
 ('missing_tree','K12_TREE_NOT_ONE_COMPLETE_READ'),('partial_tree','K12_TREE_NOT_ONE_COMPLETE_READ'),
 ('wrong_tree_row','K12_PARENTS_NOT_FROM_TREE'),('wrong_input','K12_REQUEST_NOT_THE_BINDER_INPUT_BYTES'),
 ('missing_documents','K12_DOCUMENT_SET_REQUIRED'),('no_delivery','K12_K8_DELIVERY_NOT_CITED'),
 ('partial_delivery','K12_K8_DELIVERY_NOT_COMPLETE'),('wrong_contract','K12_DOCUMENTS_NOT_THE_K8_DELIVERY'),
 ('wrong_config','K12_DOCUMENTS_NOT_THE_K8_DELIVERY'),('late_delivery','K12_K8_DELIVERY_NOT_FINISHED')])
def test_k12_holds_unproved_or_mismatched_predecessors(programs,monkeypatch,change,code):
 ctx=context(programs);monkeypatch.setattr(b,'k8_run_verifier',checker)
 if change=='missing_tree':ctx['entries']=ctx['entries'][1:]
 if change=='partial_tree':ctx['evidence_facts'][0]['complete']=False
 if change=='wrong_tree_row':ctx['plan']['parent_rows']['config'][0]['inode']=3
 if change=='wrong_input':ctx['inputs']['k12_request']=b'changed'
 if change=='missing_documents':ctx['params']={}
 if change=='no_delivery':ctx['entries']=ctx['entries'][:1]
 if change=='partial_delivery':ctx['evidence_facts'][1]['complete']=False
 if change=='wrong_contract':ctx['receipts']['E6']['effects']['contract']['sha256']='d1'*32
 if change=='wrong_config':ctx['receipts']['E6']['effects']['files'][-2]['sha256']='d1'*32
 if change=='late_delivery':ctx['receipts']['E6']['clock']['utc_end']='2026-10-06T10:39:00+00:00'
 with h.refused(code):b.k12_rules(ctx)

def test_actual_pinned_tool_reverifies_k12_document_bytes(programs):
 ctx=context(programs,fixture_root()/'k12-documents')
 result=b.k12_rules(ctx);assert result['documents']['request_sha256']==b.sha(ctx['inputs']['k12_request'])

def test_actual_pinned_tool_refuses_k12_documents_from_other_calendar(programs):
 with h.refused('K8_DOCUMENTS_NOT_VERIFIED'):
  b.k12_rules(context(programs,fixture_root(other=True)/'k12-documents'))

@pytest.mark.parametrize('mode',['PERSIST','STOP','COLLECT'])
def test_dependent_requires_exact_launch_receipt(programs,monkeypatch,mode):
 ctx=context(programs);monkeypatch.setattr(b,'k8_run_verifier',checker);ctx['plan'].update(mode=mode,launch_request_sha256='d1'*32)
 if mode=='COLLECT':ctx['operation']=b.K12_C
 with h.refused('K12_LAUNCH_REQUEST_NOT_CITED'):b.k12_rules(ctx)
 launch={'operation':b.K12_W,'mode':'LAUNCH','request_sha256':'d1'*32,'outcome':'K12_WINDOW_STEP_COMPLETE_READ_BACK','boot_id_sha256':BOOT,
 'effects':{'capacity_request_sha256':ctx['plan']['capacity_request']['sha256']},'clock':{'utc_end':'2026-10-06T10:37:00+00:00'}}
 ctx['receipts']['LAUNCH']=launch;ctx['entries'].append({'role':'LAUNCH','operation':b.K12_W});ctx['evidence_facts'].append({'role':'LAUNCH','complete':True})
 assert b.k12_rules(ctx)['documents']['launch_role']=='LAUNCH'
 launch['effects']['capacity_request_sha256']='d2'*32
 with h.refused('K12_LAUNCH_NOT_THE_CITED_WINDOW'):b.k12_rules(ctx)


def removal_context(programs):
 ctx=context(programs);ctx['plan'].update(mode='REMOVE',capacity_request=None,launch_request_sha256=None,
 removals=[{'day':'2026-10-06','window_slot':0,'container_id':'c1'*32,'image_id':'sha256:'+'a1'*32,
 'launch_request_sha256':'d1'*32,'capacity_request_sha256':'d2'*32}])
 row=ctx['plan']['removals'][0]
 collect={'operation':b.K12_C,'mode':'COLLECT','outcome':'K12_OBSERVED_AS_REQUIRED','boot_id_sha256':BOOT,
 'clock':{'utc_end':'2026-10-06T10:00:00+00:00'},'effects':{'day':row['day'],'window_slot':0,
 'launch_request_sha256':row['launch_request_sha256'],'capacity_request_sha256':row['capacity_request_sha256']},
 'items':{'container':{'id':row['container_id'],'ours':True,'running':False}}}
 launch={'operation':b.K12_W,'mode':'LAUNCH','request_sha256':row['launch_request_sha256'],
 'outcome':'K12_WINDOW_STEP_COMPLETE_READ_BACK','boot_id_sha256':BOOT,'clock':{'utc_end':'2026-10-06T09:00:00+00:00'},
 'effects':{'day':row['day'],'window_slot':0,'capacity_request_sha256':row['capacity_request_sha256'],'create':['create',row['image_id']]}}
 for role,r in [('COLLECT',collect),('LAUNCH',launch)]:
  ctx['receipts'][role]=r;ctx['entries'].append({'role':role,'operation':r['operation']});ctx['evidence_facts'].append({'role':role,'complete':True})
 return ctx

def test_remove_requires_proven_stopped_container_and_exact_launch_image(programs):
 ctx=removal_context(programs);assert b.k12_rules(ctx)['container_roles']==['COLLECT']

@pytest.mark.parametrize('change,code',[
 ('missing_collect','K12_REMOVE_CONTAINER_NOT_CITED'),('partial_collect','K12_REMOVE_NOT_THE_CITED_CONTAINER'),
 ('running','K12_REMOVE_NOT_THE_CITED_CONTAINER'),('foreign','K12_REMOVE_NOT_THE_CITED_CONTAINER'),
 ('wrong_capacity','K12_REMOVE_NOT_THE_CITED_CONTAINER'),('missing_launch','K12_REMOVE_LAUNCH_NOT_CITED'),
 ('partial_launch','K12_REMOVE_IMAGE_NOT_THE_LAUNCH'),('wrong_image','K12_REMOVE_IMAGE_NOT_THE_LAUNCH'),
 ('wrong_day','K12_REMOVE_IMAGE_NOT_THE_LAUNCH')])
def test_remove_refuses_unproved_members(programs,change,code):
 ctx=removal_context(programs)
 if change=='missing_collect':ctx['entries']=[e for e in ctx['entries'] if e['role']!='COLLECT']
 if change=='partial_collect':next(f for f in ctx['evidence_facts'] if f['role']=='COLLECT')['complete']=False
 if change=='running':ctx['receipts']['COLLECT']['items']['container']['running']=True
 if change=='foreign':ctx['receipts']['COLLECT']['items']['container']['ours']=False
 if change=='wrong_capacity':ctx['plan']['removals'][0]['capacity_request_sha256']='e1'*32
 if change=='missing_launch':ctx['entries']=[e for e in ctx['entries'] if e['role']!='LAUNCH']
 if change=='partial_launch':next(f for f in ctx['evidence_facts'] if f['role']=='LAUNCH')['complete']=False
 if change=='wrong_image':ctx['plan']['removals'][0]['image_id']='sha256:'+'b1'*32
 if change=='wrong_day':ctx['receipts']['LAUNCH']['effects']['day']='2026-10-07'
 with h.refused(code):b.k12_rules(ctx)

@pytest.mark.parametrize('change,code',[
 ('bad_member','K12_CAPACITY_REQUEST_INVALID'),('bad_summary','K12_DOCUMENTS_INVALID'),
 ('request_changed','K12_REQUEST_NOT_THE_VERIFIED_DOCUMENT_BYTES'),('chain_changed','K12_DOCUMENT_CHAIN_INVALID'),
 ('verifier_refuses','K12_DOCUMENTS_NOT_VERIFIED')])
def test_k12_document_parser_chain_and_real_verifier_cannot_be_bypassed(programs,monkeypatch,change,code):
 ctx=context(programs);original=b.k8_listed_bytes
 def files(path,*args):
  found=original(path,*args)
  if str(path)==str((ROOT/'out-primary').resolve()):
   roles=json.loads(found['SUMMARY.json'])['roles']
   if change=='bad_summary':found['SUMMARY.json']=b'not-json'
   if change=='request_changed':found[roles['request']]=b'other'
   if change=='chain_changed':
    config=json.loads(found[roles['capacity_config']]);config['document_pins']['CODEX']['sha256']='a1'*32
    found[roles['capacity_config']]=json.dumps(config).encode()
  return found
 monkeypatch.setattr(b,'k8_listed_bytes',files);monkeypatch.setattr(b,'k8_run_verifier',lambda *a: {} if change=='verifier_refuses' else checker(*a))
 if change=='bad_member':ctx['plan']['capacity_request']={}
 with h.refused(code):b.k12_rules(ctx)
