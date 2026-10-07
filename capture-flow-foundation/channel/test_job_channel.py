import copy,datetime as dt,hashlib,json,unittest
import job_channel as m
CTX={'session':'2026-10-08','run_id':'37699999999','run_attempt':1,'nonce':'a'*32}
def record(kind='OWNER_ANSWER_ID',**extra):
 v=dict(schema='CAPTURE_JOB_CONTROL_V1',kind=kind,sequence=1,**CTX,document_sha256='b'*64,question_id=1,answer_id=2,sheet_sha256='c'*64)
 if extra:v.update(extra)
 body=m.canonical(v).decode()
 return dict(id=10,url=m.ROOT+'/issues/comments/10',issue_url=m.ISSUE,created_at='2026-10-08T11:50:00Z',updated_at='2026-10-08T11:50:00Z',user=dict(id=m.OWNER_ID,login='duduvcastro',type='User'),author_association='OWNER',performed_via_github_app=None,body=body)
class Fake(m.API):
 def __init__(self,rows,now=None):self.rows=rows;self.calls=[];self.time=now or dt.datetime(2026,10,8,11,50,tzinfo=dt.timezone.utc)
 def request(self,path,*a,**k):self.calls.append(path);return self.rows
 def comment(self,cid):return next(c for c in self.rows if c['id']==cid)
 def sleep(self,s):self.time+=dt.timedelta(seconds=s)
class Proof(unittest.TestCase):
 def bad(self,f,*a):
  with self.assertRaises((m.Refused,ValueError,TypeError)):f(*a)
 def test_own_exact_control_and_replay_scope(self):
  r=record();self.assertEqual(m.control(r,CTX,'OWNER_ANSWER_ID',1)['answer_id'],2)
  for field,val in [('session','2026-10-09'),('run_id','37699999998'),('run_attempt',2),('nonce','d'*32),('sequence',2),('sheet_sha256','bad')]:
   with self.subTest(field=field):
    self.bad(m.control,record(**{field:val}),CTX,'OWNER_ANSWER_ID',1)
 def test_account_location_edit_app_refusal(self):
  for key,value in [('issue_url',m.ROOT+'/issues/430'),('updated_at','2026-10-08T11:51:00Z'),('performed_via_github_app',{'id':4}),('author_association','MEMBER'),('user',dict(id=4,login='duduvcastro',type='User')),('url',m.ROOT+'/issues/comments/11')]:
   with self.subTest(key=key):r=record();r[key]=value;self.bad(m.control,r,CTX,'OWNER_ANSWER_ID',1)
 def test_public_secrets_and_free_text_refused(self):
  self.assertIn('OWNER_REQUEST',m.public_body('OWNER_REQUEST',CTX,dict(sheet_sha256='c'*64,operation='capture_launch')))
  for values in [dict(token='private'),dict(status='/private/path'),dict(artifact_name='SECRET key'),dict(bytes=True),dict(recipient='age-secret-key'),dict(created_at='bad'),dict(sheet_sha256='bad')]:
   with self.subTest(values=list(values)):self.bad(m.public_body,'RESULT',CTX,values)
 def test_duplicate_fields_nonfinite_and_unexpected_control(self):
  for raw in ['{"a":1,"a":2}','{"a":NaN}']:self.bad(m.strict,raw)
  self.bad(m.control,record(free_text='private'),CTX,'OWNER_ANSWER_ID',1)
 def test_runtime_and_bound_documents_exact_hashes_only(self):
  a=dict(schema='CAPTURE_LINUX_RUNTIME_APPROVAL_V2',session=CTX['session'],run_id=CTX['run_id'],run_attempt=1,verdict='PASS_PHYSICAL_RUNTIME',measured_at_utc='2026-10-08T11:45:00Z',reviewed_at_utc='2026-10-08T11:47:00Z')
  for key in ('measurement_sha256','runtime_guard_sha256','binder_sha256','accepted_seals_sha256','review_body_sha256','dated_authority_sha256'):a[key]='b'*64
  self.assertEqual(m.document(a,'RUNTIME_APPROVAL'),a)
  self.bad(m.document,dict(a,path='/private/host'),'RUNTIME_APPROVAL')
  self.bad(m.document,dict(a,review_body_sha256='/private/host'),'RUNTIME_APPROVAL')
  b=dict(schema='CAPTURE_JOB_BOUND_REVIEW_V1',verdict='SIM_CODEX_REVIEW_OF_THE_BOUND_SET',**CTX,operation='capture_launch',sheet_sha256='b'*64,request_sha256='c'*64,payload_sha256='d'*64,review_body_sha256='e'*64)
  self.assertEqual(m.document(b,'BOUND_REVIEW'),b)
  self.bad(m.document,dict(b,operation='collect_launch'),'BOUND_REVIEW')
 def test_api_allowlist_before_network(self):
  class Never:
   def open(self,*a,**k):raise AssertionError('network must not happen')
  a=m.API('synthetic',Never())
  for path,method in [('/issues/430/comments','POST'),('/issues/comments/1','DELETE'),('/git/blobs/'+'a'*40,'POST'),('/issues/429/comments?since=2026-10-09T11%3A40%3A00Z&per_page=100','GET'),('https://evil.invalid','GET')]:self.bad(a.request,path,method)
 def test_one_control_duplicate_and_truncated_collection(self):
  a=Fake([record()]);v=a.wait_control(CTX,'OWNER_ANSWER_ID',1,'2026-10-08T11:52:00Z',lambda:a.time,a.sleep);self.assertEqual(v['answer_id'],2)
  b=record();b['id']=11;b['url']=m.ROOT+'/issues/comments/11'
  for rows in [[record(),b],[record()]*100]:
   a=Fake(rows);self.bad(a.wait_control,CTX,'OWNER_ANSWER_ID',1,'2026-10-08T11:52:00Z',lambda:a.time,a.sleep)
 def test_deadline_no_zero_sleep_or_late_readback(self):
  a=Fake([]);self.bad(a.wait_control,CTX,'OWNER_ANSWER_ID',1,'2026-10-08T11:50:01Z',lambda:a.time,a.sleep);self.assertEqual(len(a.calls),1)
  a=Fake([record()]);original=a.control_readback
  def late(*args):a.time+=dt.timedelta(minutes=3);return original(*args)
  a.control_readback=late;self.bad(a.wait_control,CTX,'OWNER_ANSWER_ID',1,'2026-10-08T11:52:00Z',lambda:a.time,a.sleep)
 def test_cipher_blob_hash_and_metadata_no_plaintext(self):
  raw=b'age-encryption.org/v1\nsynthetic ciphertext';blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  import base64
  value=dict(sha=blob,encoding='base64',size=len(raw),content=base64.b64encode(raw).decode())
  a=Fake([]);a.request=lambda *args,**kwargs:value
  self.assertEqual(a.blob(blob,m.sha(raw)),raw)
  self.bad(a.blob,blob,'f'*64)
  value['content']=base64.b64encode(b'plaintext').decode();self.bad(a.blob,blob,m.sha(raw))
 def test_post_bodies_cannot_bypass_redaction(self):
  body=m.public_body('RESULT',CTX,dict(receipt_sha256='c'*64,status='KNOWN_COMPLETE'))
  self.assertEqual(m.post_body(m.canonical({'body':body})),body)
  for value in [{'body':'private path /secret'},{'body':body,'token':'private'},{'body':'{"schema":"CAPTURE_JOB_PUBLIC_V1","kind":"RESULT","private":"secret"}'}]:
   self.bad(m.post_body,m.canonical(value))
 def test_two_exact_owner_question_schemas_only(self):
  base=dict(schema='CAPTURE_TRANSPORT_OWNER_REQUEST_V1',**CTX,sheet_sha256='b'*64,request_sha256='c'*64,owner_question_sha256='d'*64,asked_question_sha256='e'*64,owner_deadline_utc='2026-10-08T11:52:00Z',answer_schema='CAPTURE_OWNER_ANSWER_V2',response_channel='AskUserQuestion via Fable',recorded_by='FABLE')
  body=m.canonical(base).decode();self.assertEqual(m.owner_public_body(body),body)
  capture=dict(base,schema='CAPTURE_OWNER_REQUEST_V2',verdict='AWAITING_OWNER_SIGNATURE',k9_operation='capture_launch',not_before='2026-10-08T13:50:00Z',not_after='2026-10-08T13:59:59Z',owner_deadline_utc='2026-10-08T12:30:00Z')
  self.assertEqual(m.owner_public_body(m.canonical(capture).decode()),m.canonical(capture).decode())
  for value in [dict(base,question='private'),dict(capture,k9_operation='collect_launch'),dict(base,sheet_sha256='invalid'),dict(base,response_channel='email')]:self.bad(m.owner_public_body,m.canonical(value).decode())
 def test_full_source_physical_approval_is_metadata_only(self):
  value=dict(schema='CAPTURE_JOB_PHYSICAL_APPROVAL_V1',**CTX,verdict='PASS_PHYSICAL_RUNTIME',measured_at_utc='2026-10-08T11:45:00Z',reviewed_at_utc='2026-10-08T11:46:00Z')
  for key in ('measurement_sha256','source_layout_sha256','dated_authority_sha256','runtime_guard_sha256','binder_sha256','accepted_seals_sha256','review_body_sha256'):value[key]='b'*64
  self.assertEqual(m.document(value,'RUNTIME_APPROVAL'),value);self.bad(m.document,dict(value,measurement_plaintext='private'),'RUNTIME_APPROVAL')
if __name__=='__main__':unittest.main()
