import copy,json,pathlib,unittest
import parameter_render as m
class Proof(unittest.TestCase):
 def setUp(self):
  self.original_pin=m.INVENTORY;self.data={};rows=[]
  for op in m.OPERATIONS:
   label='k9-g19-'+op.replace('_','-')+'-p-20261008'
   base=dict(schema='BIND_ONCE_PARAMETERS_V1',signature_model='PRE',k9_grid='G19',label=label,operation='GO_READONLY_HOSTOPS02_K9_PHASE_READ_01' if op in ('policy_read','capture_result') else 'GO_WRITE_HOSTOPS02_K9_PHASE_STEP_01',not_before='2026-10-08T13:50:00Z',not_after='2026-10-08T13:59:59Z',plan=dict(day='2026-10-08',slot='PRIMARY',k9_operation=op,attempt_key='a'*64,host_directory='/var/lib/synthetic-example'),purpose_pt='synthetic only',evidence=[dict(role='TREE_POST',bound='/synthetic/evidence/tree/bound',family='/synthetic/families/k9_phase_read')],linux_job=dict(kind='LINUX_JOB_PASSED',document_file='/synthetic/docs/linux.json'),review=dict(kind='CODEX_REVIEWED',document_file='/synthetic/docs/review.json'))
   raw=m.canonical(base);source='/synthetic/base/'+label+'/PARAMETERS.json';self.data[source]=raw;rows.append(dict(source_path=source,bundle_path='base-parameters/'+label+'/PARAMETERS.json',role='BASE_PARAMETERS_NOT_JOB_PARAMETERS',bytes=len(raw),sha256=m.sha(raw)))
  for source,alias in [('/synthetic/evidence/tree/bound/PREPARE.json','historical/TREE_POST/bound/PREPARE.json'),('/synthetic/docs/linux.json','documents/linux.json'),('/synthetic/docs/review.json','documents/review.json')]:rows.append(dict(source_path=source,bundle_path=alias,role='EVIDENCE',bytes=1,sha256='b'*64))
  self.inventory=dict(schema='CAPTURE_PRIVATE_INPUT_INVENTORY_V1',session='2026-10-08',files=rows,source_families=['k9_phase_read'])
  self.raw=m.canonical(self.inventory);m.INVENTORY=m.sha(self.raw);self.rows=rows[:4]
 def tearDown(self):m.INVENTORY=self.original_pin
 def bad(self,*args):
  with self.assertRaises(m.Refused):m.render(*args)
 def test_four_synthetic_unsigned_inputs_keep_all_host_plan_bytes(self):
  for r in self.rows:
   with self.subTest(role=r['bundle_path']):
    raw=self.data[r['source_path']];before=json.loads(raw);op=before['plan']['k9_operation'];out=json.loads(m.render(raw,self.raw,'/tmp/job/private','/tmp/job/runtime/families',op))
    self.assertEqual(out['plan'],before['plan']);self.assertEqual(out['label'],before['label']);self.assertEqual(out['not_before'],before['not_before']);self.assertEqual(out['not_after'],before['not_after']);self.assertTrue(all(e['bound'].startswith('/tmp/job/private/') for e in out['evidence']));self.assertTrue(out['review']['document_file'].startswith('/tmp/job/private/'))
 def test_tampered_inventory_and_base_refused(self):
  r=self.rows[0];raw=self.data[r['source_path']];before=json.loads(raw)
  self.bad(raw,self.raw+b' ', '/tmp/p','/tmp/f','policy_read')
  before['purpose_pt']='altered';self.bad(m.canonical(before),self.raw,'/tmp/p','/tmp/f','policy_read')
 def test_non_primary_wrong_day_signature_and_operation(self):
  raw=self.data[self.rows[0]['source_path']]
  for field,value in [('slot','SPARE'),('day','2026-10-09'),('k9_operation','collect_launch')]:
   with self.subTest(field=field):p=json.loads(raw);p['plan'][field]=value;self.bad(m.canonical(p),self.raw,'/tmp/p','/tmp/f','policy_read')
  p=json.loads(raw);p['signature_model']='EVE';self.bad(m.canonical(p),self.raw,'/tmp/p','/tmp/f','policy_read')
 def test_private_local_roots_only(self):
  raw=self.data[self.rows[0]['source_path']]
  for p in ('relative','/tmp/../private','/tmp//private'):
   with self.subTest(p=p):self.bad(raw,self.raw,p,'/tmp/f','policy_read')
if __name__=='__main__':unittest.main()
