"""Exact byte and scalar provenance for reader installation; synthetic receipts only."""
from datetime import datetime,timezone
from pathlib import Path
import base64,types,copy
import pytest
import helpers as h
b=h.b
BOOT='b0'*32

def ctx(operation,plan,predecessor,pointer,value):
 receipt={'operation':predecessor,'boot_id_sha256':BOOT,'clock':{'utc_end':'2026-10-05T20:00:00+00:00'},'effects':{'value':value}}
 return {'operation':operation,'plan':dict(plan,evidence_boot_id_sha256=BOOT),'receipts':{'R':receipt},
 'copied':[{'plan_pointer':pointer,'evidence_role':'R','receipt_pointer':'/effects/value'}],
 'evidence_facts':[{'role':'R','complete':True}],'window':{'start':datetime(2026,10,5,20,38,tzinfo=timezone.utc)}}

@pytest.mark.parametrize('change',['missing','partial','wrong_boot','wrong_value','wrong_operation','late'])
def test_secret_worker_id_is_not_invented_or_taken_from_unproved_receipt(change):
 op='GO_WRITE_HOSTOPS02_K3_SECRET_ENV_01'
 from test_policy_identity_binding import context as policy_context
 c=policy_context();c['operation']=op
 assert b.reader_install_rules(c)['copies'][0]['evidence_role']=='R'
 if change=='missing':c['copied']=[]
 if change=='partial':c['evidence_facts'][0]['complete']=False
 if change=='wrong_boot':c['receipts']['R']['boot_id_sha256']='a1'*32
 if change=='wrong_value':c['receipts']['R']['items']['worker']['container_id']='a1'*32
 if change=='wrong_operation':c['receipts']['R']['operation']='OTHER'
 if change=='late':c['receipts']['R']['clock']['utc_end']='2026-10-05T21:00:00+00:00'
 with h.refused('READER_PREDECESSOR_NOT_FINISHED' if change=='late' else ('POLICY_IDENTITY_NOT_COMPLETE' if change in ('wrong_operation','partial') else 'POLICY_IDENTITY_NOT_EXACT_COPIES' if change=='missing' else 'POLICY_IDENTITY_NOT_THE_PLAN')):b.reader_install_rules(c)

def test_liveness_image_and_fixed_readonly_source_target():
 op='GO_READONLY_HOSTOPS02_K13R_READER_LIVENESS_01'
 c=ctx(op,{'image_id':'sha256:'+'c1'*32,'source_target':'/c3po-source'},'GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01','/image_id','sha256:'+'c1'*32)
 assert b.reader_install_rules(c)['copies']
 c['plan']['source_target']='/different'
 with h.refused('READER_SOURCE_TARGET_NOT_APPROVED'):b.reader_install_rules(c)

def test_k4_input_member_map_exposes_exact_bytes_hash_size():
 op='GO_WRITE_HOSTOPS02_K4_FILES_01'
 for mode,kind in [('CHAIN_STATIC','static_config'),('LAUNCHER','launcher')]:
  mapping=b.input_members(op,{'mode':mode})
  assert set(mapping)=={'/delivery/'+kind+'/'+name for name in ('content_b64','sha256','bytes')}
  assert {value[0] for value in mapping.values()}=={'k4_'+kind}
 assert b.input_members(op,{'mode':'WRITER'})=={}

def test_k4_launcher_bytes_are_the_named_input():
 op='GO_WRITE_HOSTOPS02_K4_FILES_01';raw=b'fixed launcher\n'
 c={'operation':op,'plan':{'mode':'LAUNCHER','delivery':{'launcher':{'content_b64':base64.b64encode(raw).decode(),'sha256':b.sha(raw),'bytes':len(raw)}}},
 'inputs':{'k4_launcher':raw},'rt':{'source':types.SimpleNamespace(signed_bytes=lambda item,limit,code:base64.b64decode(item['content_b64']))}}
 assert b.reader_install_rules(c)['file_inputs']==['launcher']
 c['inputs']['k4_launcher']=b'other'
 with h.refused('K4_INPUT_NOT_THE_BINDER_BYTES'):b.reader_install_rules(c)

def test_switch_requires_every_file_hash_and_release_image_origin():
 op='GO_WRITE_HOSTOPS02_K13_READER_SWITCH_01'
 c=ctx(op,{'mode':'ACTIVATE','image_id':'sha256:'+'c1'*32,'release':{'sha256':'d1'*32},'files':{'launcher':'e1'*32}},b.ACTIVATE_OPERATION,'/image_id','sha256:'+'c1'*32)
 for role,operation,pointer,value in [('REL',b.RELEASE_OPERATION,'/release/sha256','d1'*32),('FILE','GO_WRITE_HOSTOPS02_K4_FILES_01','/files/launcher','e1'*32)]:
  c['receipts'][role]={'operation':operation,'boot_id_sha256':BOOT,'clock':{'utc_end':'2026-10-05T20:00:00+00:00'},'effects':{'value':value}}
  c['copied'].append({'plan_pointer':pointer,'evidence_role':role,'receipt_pointer':'/effects/value'});c['evidence_facts'].append({'role':role,'complete':True})
 assert len(b.reader_install_rules(c)['copies'])==3
 c['plan']['files']={}
 with h.refused('READER_FILES_NOT_PROVED'):b.reader_install_rules(c)
 c['plan']['files']={'launcher':'f1'*32}
 with h.refused('READER_MEMBER_NOT_PROVED'):b.reader_install_rules(c)

def test_pins_require_actual_config_launcher_and_both_unit_deliveries():
 op='GO_WRITE_HOSTOPS02_K4_FILES_01';unit_op='GO_WRITE_HOSTOPS02_READER_UNITS_01'
 plan={'mode':'PINS','delivery':{'producer_unit_sha256':'a1'*32,'reader_unit_sha256':'b1'*32,
 'values':{'C3PO_R2D2_V2_SHADOW_SOURCE_DIR':'/c3po-source','C3PO_R2D2_V2_CAPACITY_CONFIG_SHA':'c1'*32,
 'C3PO_READER_LAUNCHER_SHA256':'d1'*32}}}
 c=ctx(op,plan,unit_op,'/delivery/producer_unit_sha256','a1'*32)
 for role,operation,pointer,value in [('UNIT',unit_op,'/delivery/reader_unit_sha256','b1'*32),
 ('CONFIG',op,'/delivery/values/C3PO_R2D2_V2_CAPACITY_CONFIG_SHA','c1'*32),
 ('LAUNCHER',op,'/delivery/values/C3PO_READER_LAUNCHER_SHA256','d1'*32)]:
  c['receipts'][role]={'operation':operation,'boot_id_sha256':BOOT,'clock':{'utc_end':'2026-10-05T20:00:00+00:00'},'effects':{'value':value}}
  c['copied'].append({'plan_pointer':pointer,'evidence_role':role,'receipt_pointer':'/effects/value'});c['evidence_facts'].append({'role':role,'complete':True})
 assert len(b.reader_install_rules(c)['copies'])==4
 c['receipts']['CONFIG']['effects']['value']='e1'*32
 with h.refused('READER_MEMBER_NOT_PROVED'):b.reader_install_rules(c)
 c['receipts']['CONFIG']['effects']['value']='c1'*32
 c['plan']['delivery']['values']['C3PO_R2D2_V2_SHADOW_SOURCE_DIR']='/other'
 with h.refused('READER_SOURCE_TARGET_NOT_APPROVED'):b.reader_install_rules(c)


def reader_units_context(expectations=None,leftovers=()):
 op='GO_WRITE_HOSTOPS02_READER_UNITS_01';value=copy.deepcopy(list(leftovers))
 expectations=expectations or ['ABSENT']*3
 names=(('READER_SERVICE','c3po-reader.service'),('READER_TIMER','c3po-reader.timer'),('READER_ALERT','c3po-reader-alert.service'))
 units=[{'key':key,'destination_name':name,'expect':copy.deepcopy(expect)}
        for (key,name),expect in zip(names,expectations)]
 return ctx(op,{'units':units,'acknowledged_leftovers':value},b.PRECHECK_OPERATION,'/acknowledged_leftovers',copy.deepcopy(value))

LEFTOVER={'name':'.hostops-'+'e'*16+'-0.partial','device':1,'inode':23}
PRESENT_ONE_LINK={'device':1,'inode':17,'links':1}

@pytest.mark.parametrize('present_index',[None,0,1,2])
@pytest.mark.parametrize('with_leftover',[False,True])
def test_reader_units_accept_absent_and_present_with_one_link(present_index,with_leftover):
 expectations=['ABSENT']*3
 if present_index is not None:expectations[present_index]=PRESENT_ONE_LINK
 c=reader_units_context(expectations,[LEFTOVER] if with_leftover else [])
 before=copy.deepcopy(c)
 result=b.reader_install_rules(c)
 assert result==({'copies':[{'plan_pointer':'/acknowledged_leftovers','evidence_role':'R'}]} if with_leftover else {'mode':None})
 assert c==before

@pytest.mark.parametrize('present_index',[0,1,2])
@pytest.mark.parametrize('with_leftover',[False,True])
def test_reader_units_refuse_two_links_before_accepting_any_leftovers(present_index,with_leftover,monkeypatch):
 expectations=[PRESENT_ONE_LINK,'ABSENT',PRESENT_ONE_LINK]
 expectations[present_index]=dict(PRESENT_ONE_LINK,links=2)
 leftover=dict(LEFTOVER,name='.hostops-'+'e'*16+'-%d.partial'%present_index,inode=PRESENT_ONE_LINK['inode'])
 c=reader_units_context(expectations,[leftover] if with_leftover else [])
 before=copy.deepcopy(c)
 monkeypatch.setattr(b,'scalar_receipt_copy',h.never)
 with h.refused('READER_UNIT_PRESENT_LINKS_NOT_ONE'):b.reader_install_rules(c)
 assert c==before

@pytest.mark.parametrize('expect',[None,'PRESENT',False,{},
 dict(PRESENT_ONE_LINK,links=True),dict(PRESENT_ONE_LINK,links='1'),dict(PRESENT_ONE_LINK,links=1.0),
 dict(PRESENT_ONE_LINK,links=0),dict(PRESENT_ONE_LINK,links=3)])
def test_reader_units_require_absent_or_an_integer_one_link_expectation(expect):
 c=reader_units_context([expect,'ABSENT','ABSENT'])
 with h.refused('READER_UNIT_PRESENT_LINKS_NOT_ONE'):b.reader_install_rules(c)

def test_acknowledged_leftovers_are_copied_from_precheck_not_a_write():
 c=reader_units_context(leftovers=[LEFTOVER])
 assert b.reader_install_rules(c)['copies']
 c['receipts']['R']['operation']='GO_WRITE_SUPERVISOR_READER_PROVISION_01'
 with h.refused('READER_MEMBER_NOT_PROVED'):b.reader_install_rules(c)

@pytest.mark.parametrize('change',['missing','partial','wrong_boot','wrong_name','wrong_device','wrong_inode','late'])
def test_reader_units_leftovers_keep_exact_identity_and_complete_same_boot_provenance(change):
 c=reader_units_context([PRESENT_ONE_LINK,'ABSENT','ABSENT'],[LEFTOVER])
 assert b.reader_install_rules(c)['copies']
 if change=='missing':c['copied']=[]
 if change=='partial':c['evidence_facts'][0]['complete']=False
 if change=='wrong_boot':c['receipts']['R']['boot_id_sha256']='a1'*32
 if change=='wrong_name':c['receipts']['R']['effects']['value'][0]['name']='.hostops-'+'f'*16+'-0.partial'
 if change=='wrong_device':c['receipts']['R']['effects']['value'][0]['device']+=1
 if change=='wrong_inode':c['receipts']['R']['effects']['value'][0]['inode']+=1
 if change=='late':c['receipts']['R']['clock']['utc_end']='2026-10-05T21:00:00+00:00'
 with h.refused('READER_PREDECESSOR_NOT_FINISHED' if change=='late' else 'READER_MEMBER_NOT_PROVED'):b.reader_install_rules(c)

def test_reader_units_one_link_refusal_is_recognised_and_exercised_by_the_existing_coverage_table():
 from test_bind_once import refusal_codes_of_the_source
 code='READER_UNIT_PRESENT_LINKS_NOT_ONE'
 c=reader_units_context(['ABSENT',dict(PRESENT_ONE_LINK,links=2),'ABSENT'],[LEFTOVER])
 with h.refused(code):b.reader_install_rules(c)
 codes,_=refusal_codes_of_the_source()
 assert code in codes and code in h.COVERED

def test_reader_units_default_common_rule_fixture_supplies_absent_unit_expectations():
 from test_programs import ctx_of
 op='GO_WRITE_HOSTOPS02_READER_UNITS_01'
 names=(('READER_SERVICE','c3po-reader.service'),('READER_TIMER','c3po-reader.timer'),('READER_ALERT','c3po-reader-alert.service'))
 source=types.SimpleNamespace(OPERATION=op,PLAN_KEYS=('units','evidence_boot_id_sha256'),UNIT_ORDER=names,EVIDENCE_OPERATIONS=(b.PRECHECK_OPERATION,),WRITES_ALLOWED=True)
 programs=types.SimpleNamespace(modules={op:(None,None,{'source':source})})
 c=ctx_of(programs,op)
 assert [unit['expect'] for unit in c['plan']['units']]==['ABSENT']*3
 assert b.sealed_program_rules(c)['sealed_program']['extra']=={'mode':None}
