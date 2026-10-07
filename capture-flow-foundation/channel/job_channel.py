"""Fixed #429 metadata/ciphertext exchange; no arbitrary URLs or commands.

Control comments identify data and hashes, not shell commands. The actual dated
authority, physical runtime and own answer checks remain separate gates. A Fable
record authenticated by GitHub is not independent proof of a human signature.
"""
import base64
import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.request

ROOT='https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence'
ISSUE=ROOT+'/issues/429'
OWNER_ID=313137248
CONTROL_KINDS=('PRIVATE_INPUTS','RUNTIME_APPROVAL','OWNER_ANSWER_ID','BOUND_REVIEW','NIGHT_GATES')
PUBLIC_KINDS=('EPHEMERAL_RECIPIENT','RUNTIME_MEASURED','OWNER_REQUEST','INTENT','RESULT','REFUSED')
class Refused(ValueError):pass
def need(ok,code):
    if not ok:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict(raw):
    def pairs(items):
        out={}
        for k,v in items:need(k not in out,'JOB_DUPLICATE_FIELD');out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'JOB_NONFINITE'))
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def pin(v):need(type(v) is str and re.fullmatch('[0-9a-f]{64}',v),'JOB_HASH');return v
def context(v):
    need(set(v)=={'session','run_id','run_attempt','nonce'} and v['session']=='2026-10-08'
         and type(v['run_id']) is str and re.fullmatch('[1-9][0-9]{5,19}',v['run_id'])
         and type(v['run_attempt']) is int and v['run_attempt']==1
         and type(v['nonce']) is str and re.fullmatch('[0-9a-f]{32}',v['nonce']),'JOB_CONTEXT')
    return dict(v)
def public_body(kind,ctx,values):
    """Only fixed labels, hashes, counts, UTC and the public recipient. No free prose."""
    need(kind in PUBLIC_KINDS,'JOB_PUBLIC_KIND');ctx=context(ctx)
    allowed={'sheet_sha256','question_body_sha256','asked_question_sha256','request_sha256','payload_sha256',
             'ciphertext_sha256','manifest_sha256','config_sha256','go_sha256','intent_sha256','receipt_sha256',
             'measurement_sha256','artifact_name','files','bytes','operation','status','recipient','created_at'}
    need(type(values) is dict and set(values)<=allowed,'JOB_PUBLIC_KEYS')
    for k,v in values.items():
        if k.endswith('_sha256'):pin(v)
        elif k in ('files','bytes'):need(type(v) is int and 0<=v<=32*1024*1024,'JOB_PUBLIC_COUNT')
        elif k=='operation':need(v in ('transport_challenge','policy_read','capture_launch','capture_result','capture_cleanup'),'JOB_PUBLIC_OPERATION')
        elif k=='recipient':need(type(v) is str and re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}',v),'JOB_RECIPIENT')
        elif k=='created_at':need(type(v) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',v),'JOB_PUBLIC_TIME')
        else:need(type(v) is str and re.fullmatch('[A-Z0-9_]{1,96}',v),'JOB_PUBLIC_LABEL')
    return canonical(dict(schema='CAPTURE_JOB_PUBLIC_V1',kind=kind,**ctx,**values)).decode()
def control(comment,ctx,kind,sequence):
    """Return a strictly typed record from Fable's own authenticated account."""
    need(type(comment) is dict and comment.get('issue_url')==ISSUE
         and type(comment.get('id')) is int and comment['id']>0
         and comment.get('url')==ROOT+'/issues/comments/'+str(comment['id'])
         and comment.get('created_at')==comment.get('updated_at'),'JOB_CONTROL_LOCATION_OR_EDIT')
    user=comment.get('user',{})
    need(user.get('id')==OWNER_ID and user.get('login')=='duduvcastro' and user.get('type')=='User'
         and comment.get('author_association')=='OWNER' and comment.get('performed_via_github_app') is None,
         'JOB_CONTROL_ACCOUNT')
    body=comment.get('body');need(type(body) is str and len(body.encode())<=8192,'JOB_CONTROL_BODY')
    v=strict(body);need(type(v) is dict and v.get('schema')=='CAPTURE_JOB_CONTROL_V1'
         and kind in CONTROL_KINDS and v.get('kind')==kind and type(v.get('sequence')) is int
         and v['sequence']==sequence and {k:v.get(k) for k in ctx}==context(ctx),'JOB_CONTROL_SCOPE')
    fields={'schema','kind','sequence',*ctx,'document_sha256'}
    if kind=='OWNER_ANSWER_ID':
        fields|={'question_id','answer_id','sheet_sha256'}
        for k in ('question_id','answer_id'):need(type(v.get(k)) is int and v[k]>0,'JOB_ANSWER_ID')
        pin(v.get('sheet_sha256'))
    elif kind in ('PRIVATE_INPUTS','NIGHT_GATES'):
        fields|={'blob_sha','ciphertext_sha256','manifest_sha256'}
        need(type(v.get('blob_sha')) is str and re.fullmatch('[0-9a-f]{40}',v['blob_sha']),'JOB_BLOB_ID')
        pin(v.get('ciphertext_sha256'));pin(v.get('manifest_sha256'))
        if kind=='PRIVATE_INPUTS':
            fields|={'manifest_blob_sha','manifest_ciphertext_sha256'}
            need(type(v.get('manifest_blob_sha')) is str and re.fullmatch('[0-9a-f]{40}',v['manifest_blob_sha']),'JOB_MANIFEST_BLOB_ID')
            pin(v.get('manifest_ciphertext_sha256'))
    else:
        fields|={'document'};document(v.get('document'),kind)
        need(sha(canonical(v['document']))==pin(v.get('document_sha256')),'JOB_CONTROL_DOCUMENT_PIN')
    need(set(v)==fields,'JOB_CONTROL_KEYS');pin(v.get('document_sha256'))
    return v
def document(value,kind):
    need(type(value) is dict,'JOB_CONTROL_DOCUMENT')
    if kind=='RUNTIME_APPROVAL' and value.get('schema')=='CAPTURE_JOB_PHYSICAL_APPROVAL_V1':
        keys={'schema','session','run_id','run_attempt','nonce','verdict','measurement_sha256','source_layout_sha256','dated_authority_sha256','runtime_guard_sha256','binder_sha256','accepted_seals_sha256','review_body_sha256','measured_at_utc','reviewed_at_utc'}
        need(set(value)==keys and value['verdict']=='PASS_PHYSICAL_RUNTIME','JOB_RUNTIME_DOCUMENT_SCOPE')
        context({k:value[k] for k in ('session','run_id','run_attempt','nonce')})
    elif kind=='RUNTIME_APPROVAL':
        keys={'schema','session','run_id','run_attempt','verdict','measurement_sha256',
              'runtime_guard_sha256','binder_sha256','accepted_seals_sha256',
              'review_body_sha256','dated_authority_sha256','measured_at_utc','reviewed_at_utc'}
        need(set(value)==keys and value['schema']=='CAPTURE_LINUX_RUNTIME_APPROVAL_V2'
             and value['verdict']=='PASS_PHYSICAL_RUNTIME','JOB_RUNTIME_DOCUMENT_SCOPE')
    else:
        keys={'schema','verdict','session','run_id','run_attempt','nonce','operation',
              'sheet_sha256','request_sha256','payload_sha256','review_body_sha256'}
        need(set(value)==keys and value['schema']=='CAPTURE_JOB_BOUND_REVIEW_V1'
             and value['verdict']=='SIM_CODEX_REVIEW_OF_THE_BOUND_SET'
             and value['operation'] in ('policy_read','capture_launch','capture_result','capture_cleanup'),
             'JOB_BOUND_DOCUMENT_SCOPE')
        context({k:value[k] for k in ('session','run_id','run_attempt','nonce')})
    need(value['session']=='2026-10-08' and type(value['run_id']) is str
         and re.fullmatch('[1-9][0-9]{5,19}',value['run_id'])
         and type(value['run_attempt']) is int and value['run_attempt']==1,'JOB_DOCUMENT_CONTEXT')
    for key,item in value.items():
        if key.endswith('_sha256'):pin(item)
        elif key.endswith('_utc'):
            need(type(item) is str and re.fullmatch(r'2026-10-08T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',item),
                 'JOB_DOCUMENT_UTC')
    return value
def owner_public_body(raw):
    need(type(raw) is str and len(raw.encode())<=4096,'JOB_OWNER_BODY')
    v=strict(raw);need(type(v) is dict,'JOB_OWNER_BODY')
    base={'schema','session','run_id','run_attempt','nonce','sheet_sha256','request_sha256',
          'owner_question_sha256','asked_question_sha256','owner_deadline_utc','answer_schema','response_channel','recorded_by'}
    need(v.get('answer_schema')=='CAPTURE_OWNER_ANSWER_V2' and v.get('recorded_by')=='FABLE'
         and v.get('response_channel')=='AskUserQuestion via Fable','JOB_OWNER_CHANNEL')
    if v.get('schema')=='CAPTURE_OWNER_REQUEST_V2':
        need(set(v)==base|{'verdict','k9_operation','not_before','not_after'}
             and v['verdict']=='AWAITING_OWNER_SIGNATURE'
             and v['k9_operation'] in ('policy_read','capture_launch','capture_result','capture_cleanup')
             and v['owner_deadline_utc']=='2026-10-08T12:30:00Z','JOB_OWNER_CAPTURE_SCOPE')
        for key in ('not_before','not_after'):
            need(type(v[key]) is str and re.fullmatch(r'2026-10-08T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',v[key]),'JOB_OWNER_TIME')
    else:
        need(set(v)==base and v.get('schema')=='CAPTURE_TRANSPORT_OWNER_REQUEST_V1'
             and v['owner_deadline_utc']=='2026-10-08T11:52:00Z','JOB_OWNER_CHALLENGE_SCOPE')
    context({k:v[k] for k in ('session','run_id','run_attempt','nonce')})
    for key,val in v.items():
        if key.endswith('_sha256'):pin(val)
    need(canonical(v).decode()==raw,'JOB_OWNER_BODY_CANONICAL')
    return raw
def post_body(raw):
    value=strict(raw);need(type(value) is dict and set(value)=={'body'},'JOB_POST_BODY')
    body=value['body'];v=strict(body);need(type(v) is dict,'JOB_POST_BODY')
    if v.get('schema')=='CAPTURE_JOB_PUBLIC_V1':
        ctx={k:v.get(k) for k in ('session','run_id','run_attempt','nonce')};context(ctx)
        values={k:x for k,x in v.items() if k not in {*ctx,'schema','kind'}}
        need(public_body(v['kind'],ctx,values)==body,'JOB_POST_PUBLIC_CANONICAL')
    else:owner_public_body(body)
    return body
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):raise Refused('JOB_REDIRECT')
class API:
    def __init__(self,token,opener=None):
        need(type(token) is str and token and not re.search(r'[\s\x00-\x1f]',token),'JOB_TOKEN')
        self.token=token;self.opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def request(self,path,method='GET',body=None,maximum=1024*1024):
        allowed=(method=='POST' and path=='/issues/429/comments' or method=='GET' and
                 (re.fullmatch('/issues/comments/[1-9][0-9]*',path) or re.fullmatch('/git/blobs/[0-9a-f]{40}',path)
                  or re.fullmatch(r'/issues/429/comments\?since=2026-10-08T[0-9]{2}%3A[0-9]{2}%3A[0-9]{2}Z&per_page=100',path)))
        need(allowed,'JOB_API_PATH')
        if method=='POST':post_body(body)
        url=ROOT+path
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json',
                 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'capture-job-channel'}
        if body is not None:headers['Content-Type']='application/json'
        req=urllib.request.Request(url,method=method,headers=headers,data=body)
        try:
            with self.opener.open(req,timeout=20) as r:
                need(r.status==(201 if method=='POST' else 200) and r.geturl()==url,'JOB_API_STATUS_LOCATION')
                need(r.headers.get_content_type()=='application/json','JOB_API_CONTENT_TYPE');raw=r.read(maximum+1)
        except Refused:raise
        except (urllib.error.URLError,OSError,TimeoutError):raise Refused('JOB_API_FAILED_NO_RETRY') from None
        need(len(raw)<=maximum,'JOB_API_SIZE');return strict(raw)
    def comment(self,cid):
        need(type(cid) is int and cid>0,'JOB_COMMENT_ID');v=self.request('/issues/comments/'+str(cid),maximum=65536)
        need(v.get('id')==cid and v.get('url')==ROOT+'/issues/comments/'+str(cid) and v.get('issue_url')==ISSUE,'JOB_COMMENT_LOCATION');return v
    def publish(self,kind,ctx,values):
        body=public_body(kind,ctx,values);c=self.request('/issues/429/comments','POST',canonical({'body':body}),65536)
        need(type(c.get('id')) is int,'JOB_POST_ID');r=self.comment(c['id'])
        need(r==c and r.get('body')==body and r.get('created_at')==r.get('updated_at'),'JOB_POST_READBACK')
        return r
    def publish_owner(self,body):
        body=owner_public_body(body);c=self.request('/issues/429/comments','POST',canonical({'body':body}),65536)
        need(type(c.get('id')) is int,'JOB_POST_ID');r=self.comment(c['id'])
        need(r==c and r.get('body')==body and r.get('created_at')==r.get('updated_at'),'JOB_POST_READBACK')
        return r
    def control_readback(self,cid,ctx,kind,sequence):
        a,b=self.comment(cid),self.comment(cid);need(a==b,'JOB_CONTROL_CHANGED')
        return control(a,ctx,kind,sequence)
    def wait_control(self,ctx,kind,sequence,deadline,clock=None,sleep=None):
        clock=clock or (lambda:dt.datetime.now(dt.timezone.utc));sleep=sleep or time.sleep
        end=dt.datetime.fromisoformat(deadline.replace('Z','+00:00'))
        cursor='2026-10-08T11:40:00Z';seen={};candidates={}
        while clock()<end:
            rows=self.request('/issues/429/comments?since='+cursor.replace(':','%3A')+'&per_page=100')
            need(type(rows) is list and len(rows)<100,'JOB_COLLECTION_INCOMPLETE')
            for c in rows:
                need(type(c) is dict and type(c.get('id')) is int and type(c.get('body')) is str,'JOB_COLLECTION_SHAPE')
                hashed=sha(c['body'].encode())
                try:v=strict(c['body'])
                except (TypeError,ValueError):continue
                if type(v) is dict and v.get('schema')=='CAPTURE_JOB_CONTROL_V1' and v.get('kind')==kind and v.get('sequence')==sequence and all(v.get(k)==val for k,val in ctx.items()):
                    previous=seen.get(c['id']);need(previous is None or previous==hashed,'JOB_COLLECTION_BODY_CHANGED')
                    seen[c['id']]=hashed;control(c,ctx,kind,sequence);candidates[c['id']]=c
            need(len(candidates)<=1,'JOB_DUPLICATE_CONTROL')
            if candidates:
                cid=next(iter(candidates));record=self.control_readback(cid,ctx,kind,sequence)
                need(clock()<=end,'JOB_CONTROL_DEADLINE_NO_RETRY');return record
            if rows:
                latest=max(dt.datetime.fromisoformat(c['created_at'].replace('Z','+00:00')) for c in rows)
                need(latest.date().isoformat()=='2026-10-08' and latest<=clock(),'JOB_COLLECTION_TIME')
                cursor=(latest-dt.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ')
            sleep(min(10,max(0,(end-clock()).total_seconds())))
        raise Refused('JOB_CONTROL_DEADLINE_NO_RETRY')
    def blob(self,blob_sha,ciphertext_sha):
        need(type(blob_sha) is str and re.fullmatch('[0-9a-f]{40}',blob_sha),'JOB_BLOB_ID');pin(ciphertext_sha)
        v=self.request('/git/blobs/'+blob_sha,maximum=24*1024*1024)
        need(v.get('sha')==blob_sha and v.get('encoding')=='base64' and type(v.get('size')) is int
             and 0<v['size']<=16*1024*1024,'JOB_BLOB_METADATA')
        raw=base64.b64decode(v['content'].replace('\n',''),validate=True)
        need(len(raw)==v['size'] and sha(raw)==ciphertext_sha
             and hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==blob_sha
             and raw.startswith(b'age-encryption.org/v1\n'),'JOB_CIPHERTEXT_PIN')
        return raw
