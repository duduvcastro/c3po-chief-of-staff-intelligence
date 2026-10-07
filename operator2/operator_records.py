"""Operator data builder only: no network, SSH, app import, sign or dispatch.

Actual owner decisions and GitHub readbacks are inputs. Generated JSON is a
record to publish, never a human answer or runtime PASS manufactured here.
"""
import argparse,datetime as dt,hashlib,json,pathlib,re,os
E5='6eecb45632f8679d74dd4d14d8309476cbe7d6953fff52a042c8e473a74c68df'
SIGNATURE='2d5fd0f7c04ea5f23d3cd4df62cd7431575898fe862bcdd110cb1cb81408377f'
LAYOUT='b106708d7e72d3c6b529021a1a35fa85d1076a52eb01883cd7b28597334eeac0'
ROOT='https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence'
SETS={'policy_read':('3cbba6513c8a5910cc0cc08b804e05cff0cbd79b3eb8b501f5ff4b27b48e5d28','00485fcc66681afc6b1ed8f3da62ff69f13103dbb9d03bad77671576cb605a22'),'capture_launch':('d18fa79b8180d03eeb78245f80bb7a4235fadcb17800ecf76c21a3c64f6181d5','3995f8a6483c702ec142d9da5f44acfb5b45a35346ad51effa73cca1f114bd40'),'capture_result':('e0c70fabf828ae95bcdc932943a3e5067a594fb2665152ec632cb4cf0ea52621','9e2a55ca3aa8a9d99a6d602e5ec6a240546e5a31d660d3ee91ce2b3fbfdd2254'),'capture_cleanup':('9947af8b8dfae26d15adab3e89eaf5b2779ded1af68a7426e66da0886d19298c','38f90d6ed8f79855a0de12cff42927290c953b3be76fa278489d09fc5d179e64')}
class Refused(ValueError):pass
def need(v,code):
 if not v:raise Refused(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def strict(b):
 def pairs(rows):
  out={}
  for k,v in rows:need(k not in out,'DUPLICATE_FIELD');out[k]=v
  return out
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'NONFINITE'))
def utc(v):
 need(type(v) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',v),'UTC');return dt.datetime.fromisoformat(v.replace('Z','+00:00'))
def pin(v):need(type(v) is str and re.fullmatch('[0-9a-f]{64}',v),'HASH');return v
def read(p):
 p=pathlib.Path(p);need(p.is_file() and not p.is_symlink() and p.stat().st_size<=16*1024*1024,'INPUT');a=p.stat();raw=p.read_bytes();b=p.stat();need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns,b.st_ctime_ns),'INPUT_CHANGED');return raw
def put(p,b):
 p=pathlib.Path(p);need(p.parent.is_dir() and not p.parent.is_symlink(),'OUTPUT_PARENT');fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
def request(body):return canonical({'body':canonical(body).decode()})
def record_signature(raw,doc,retirements):
 need(sha(raw)==SIGNATURE and sha(doc)==E5,'SIGNED_E5_BYTES');s=strict(raw);need(s['document_sha256']==E5 and s['answer']=='Assino a emenda5 rev3 da A2','SIGNED_E5_ANSWER');signed=s['signed_at_utc'];utc(signed);need(set(retirements)==set(SETS),'RETIREMENT_SET');times=[];proofs={}
 for op,(sheet,config) in SETS.items():
  b=retirements[op];v=strict(b);need(v['status']=='RETIRED_NEVER_DISPATCH' and v['prepare_json_sha256']==sheet and v['owner_signature_record_sha256']==SIGNATURE and v['authority']=='A2_EMENDA_05 rev3 '+E5,'RETIREMENT_EXACT');need(utc(v['retired_at_utc'])>=utc(signed),'RETIREMENT_ORDER');times.append(v['retired_at_utc']);proofs[op]=sha(b)
 common=dict(document_sha256=E5,source_layout_sha256=LAYOUT,retired_mac_config_sha256=[x[1] for x in SETS.values()])
 owner=dict(schema='CAPTURE_JOB_DATED_AUTHORITY_RECORD_V1',**common,owner='DUDU',answer='Assino',signed_at_utc=signed,source_signature_record_sha256=SIGNATURE)
 retirement=dict(schema='CAPTURE_JOB_MAC_RETIREMENT_RECORD_V1',**common,election='JOB_ONLY_MAC_CAPTURE_RETIRED_BEFORE_PREPARE',observed_at_utc=max(times),retirement_record_sha256=proofs)
 return owner,retirement

def comment(v,owner=True,parse=True):
 need(type(v.get('id')) is int and v['id']>0 and v.get('url')==ROOT+'/issues/comments/'+str(v['id']) and v.get('issue_url')==ROOT+'/issues/429' and v.get('created_at')==v.get('updated_at'),'COMMENT_LOCATION_OR_EDIT');utc(v['created_at'])
 if owner:
  u=v.get('user',{});need(u.get('id')==313137248 and u.get('login')=='duduvcastro' and u.get('type')=='User' and v.get('author_association')=='OWNER' and v.get('performed_via_github_app') is None,'COMMENT_ACCOUNT')
 need(type(v.get('body')) is str,'COMMENT_BODY');return strict(v['body']) if parse else v['body']
def dated(owner,retired):
 a,b=comment(owner),comment(retired);need(a.get('schema')=='CAPTURE_JOB_DATED_AUTHORITY_RECORD_V1' and b.get('schema')=='CAPTURE_JOB_MAC_RETIREMENT_RECORD_V1','AUTHORITY_RECORD_SCHEMAS');configs=[x[1] for x in SETS.values()]
 for v in (a,b):need(v.get('document_sha256')==E5 and v.get('source_layout_sha256')==LAYOUT and v.get('retired_mac_config_sha256')==configs,'AUTHORITY_RECORD_PINS')
 need(a.get('owner')=='DUDU' and a.get('answer')=='Assino' and a.get('source_signature_record_sha256')==SIGNATURE,'OWNER_RECORD_ANSWER');need(b.get('election')=='JOB_ONLY_MAC_CAPTURE_RETIRED_BEFORE_PREPARE','ELECTION');need(utc(a['signed_at_utc'])<=utc(b['observed_at_utc'])<=utc(retired['created_at']) and utc(a['signed_at_utc'])<=utc(owner['created_at']),'AUTHORITY_RECORD_ORDER')
 return dict(schema='CAPTURE_JOB_DATED_AUTHORITY_V1',status='SIGNED',owner='DUDU',answer='Assino',session='2026-10-08',source_layout_sha256=LAYOUT,outside_Mac=True,single_job=True,single_use=True,retry=False,election=b['election'],retired_mac_config_sha256=configs,document_sha256=E5,source_owner_record_comment_id=owner['id'],source_owner_record_body_sha256=sha(owner['body'].encode()),operator_election_record_comment_id=retired['id'],operator_election_record_body_sha256=sha(retired['body'].encode()),signed_at_utc=a['signed_at_utc'],election_observed_at_utc=b['observed_at_utc'])
def own_context(v):
 need(v.get('session')=='2026-10-08' and type(v.get('run_id')) is str and re.fullmatch('[1-9][0-9]{5,19}',v['run_id']) and type(v.get('run_attempt')) is int and v['run_attempt']==1 and type(v.get('nonce')) is str and re.fullmatch('[0-9a-f]{32}',v['nonce']),'OWN_CONTEXT');return {k:v[k] for k in ('session','run_id','run_attempt','nonce')}
def answer(question,asked,answered,human,asked_question_bytes):
 q=comment(question,False);ctx=own_context(q);need(sha(asked_question_bytes)==q['asked_question_sha256'],'ASKED_PRIVATE_QUESTION_BYTES');need(human=='Assino','HUMAN_ANSWER_NOT_LITERAL');need(q.get('schema') in ('CAPTURE_TRANSPORT_OWNER_REQUEST_V1','CAPTURE_OWNER_REQUEST_V2') and q.get('recorded_by')=='FABLE' and q.get('answer_schema')=='CAPTURE_OWNER_ANSWER_V2','QUESTION_SCHEMA');need(utc(question['created_at'])<=utc(asked)<=utc(answered)<=utc(q['owner_deadline_utc']),'ANSWER_ORDER_OR_DEADLINE')
 return dict(schema='CAPTURE_OWNER_ANSWER_V2',**ctx,sheet_sha256=pin(q['sheet_sha256']),question_body_sha256=sha(question['body'].encode()),asked_question_sha256=pin(q['asked_question_sha256']),asked_at_utc=asked,answered_at_utc=answered,answer=human,recorded_by='FABLE',source_channel='AskUserQuestion via Fable')
def control_answer(question,record):
 q=comment(question,False);v=comment(record);ctx=own_context(q);need(v.get('schema')=='CAPTURE_OWNER_ANSWER_V2' and v.get('answer')=='Assino' and v.get('recorded_by')=='FABLE' and v.get('source_channel')=='AskUserQuestion via Fable','ANSWER_RECORD');need(all(v.get(k)==x for k,x in ctx.items()) and v.get('sheet_sha256')==q['sheet_sha256'] and v.get('question_body_sha256')==sha(question['body'].encode()) and v.get('asked_question_sha256')==q['asked_question_sha256'],'ANSWER_OWN_BYTES');need(utc(question['created_at'])<=utc(v['asked_at_utc'])<=utc(v['answered_at_utc'])<=utc(record['created_at'])<=utc(q['owner_deadline_utc']) and utc(record['created_at'])-utc(v['answered_at_utc'])<=dt.timedelta(seconds=60),'ANSWER_RECORD_ORDER');seq=1 if q['schema']=='CAPTURE_TRANSPORT_OWNER_REQUEST_V1' else 2+tuple(SETS).index(q['k9_operation'])
 return dict(schema='CAPTURE_JOB_CONTROL_V1',kind='OWNER_ANSWER_ID',sequence=seq,**ctx,document_sha256=sha(record['body'].encode()),question_id=question['id'],answer_id=record['id'],sheet_sha256=q['sheet_sha256'])
def capsule_command():
 import sys,types
 source=pathlib.Path(__file__).parent/'capsule_data.py';raw=source.read_bytes();need(sha(raw)=='6b5709772a19011090052fb4cfe643d666d92003e140358038b690921a47fb49','CAPSULE_HELPER_PIN');m=types.ModuleType('pinned_capsule_data');m.__file__=str(source);exec(compile(raw,str(source),'exec'),m.__dict__);m.main(sys.argv[1:])

def main():
 import sys
 if len(sys.argv)>1 and sys.argv[1] in ('ephemeral-context', 'blob-requests', 'private-inputs', 'night-capsule', 'night-gates'):return capsule_command()
 ap=argparse.ArgumentParser(allow_abbrev=False);sub=ap.add_subparsers(dest='command',required=True)
 s=sub.add_parser('authority-records');s.add_argument('--signature',required=True);s.add_argument('--e5',required=True);s.add_argument('--retirement-root',required=True);s.add_argument('--out',required=True)
 s=sub.add_parser('dated-authority');s.add_argument('--owner-readback',required=True);s.add_argument('--retirement-readback',required=True);s.add_argument('--out',required=True)
 s=sub.add_parser('answer-record');s.add_argument('--question-readback',required=True);s.add_argument('--asked-question-file',required=True);s.add_argument('--asked-at',required=True);s.add_argument('--answered-at',required=True);s.add_argument('--human-answer',required=True);s.add_argument('--out',required=True)
 s=sub.add_parser('answer-control');s.add_argument('--question-readback',required=True);s.add_argument('--answer-readback',required=True);s.add_argument('--out',required=True)
 a=ap.parse_args()
 if a.command=='authority-records':
  retire={op:read(pathlib.Path(a.retirement_root)/('k9-g19-'+op.replace('_','-')+'-p-20261008')/'RETIRED_BY_EMENDA5.json') for op in SETS};owner,retired=record_signature(read(a.signature),read(a.e5),retire);out=pathlib.Path(a.out);out.mkdir(mode=0o700);put(out/'OWNER_RECORD.request.json',request(owner));put(out/'RETIREMENT_RECORD.request.json',request(retired))
 elif a.command=='dated-authority':put(a.out,canonical(dated(strict(read(a.owner_readback)),strict(read(a.retirement_readback)))))
 elif a.command=='answer-record':put(a.out,request(answer(strict(read(a.question_readback)),a.asked_at,a.answered_at,a.human_answer,read(a.asked_question_file))))
 else:put(a.out,request(control_answer(strict(read(a.question_readback)),strict(read(a.answer_readback)))))
 print('{"status":"OPERATOR_DATA_ONLY_NOT_SIGNATURE_RUNTIME_PASS_OR_GO"}')
if __name__=='__main__':
 try:main()
 except Exception:print('{"status":"OPERATOR_RECORD_REFUSED"}');raise SystemExit(2)
