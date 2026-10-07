"""Dated SYNTHETIC operator/job exchange. Never an operational control or authority.

Fable executes this worker via the separate rehearsal workflow. Only fixed
harmless fixtures can be decrypted. No SSH, app/core import, owner ask or GO.
"""
import argparse,base64,datetime as dt,hashlib,json,os,pathlib,re,secrets,subprocess,sys,time,types,urllib.request
HOME=pathlib.Path(__file__).resolve().parent
ROOT='https://api.github.com/repos/duduvcastro/c3po-chief-of-staff-intelligence'
AGE='eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c'
KEYGEN='0a0009db842259d6717f7eeb30acb6b90d2a2eb924c6acd0a0db0ca1f1537899'

def load(n):
 p=HOME/(n+'.py');m=types.ModuleType('rehearsal_'+n);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
m=load('capsule_data');f=load('synthetic_fixtures')
def ctx(v):return m.own_context(v,'2026-10-07')
def fixtures(out):
 p=m.output_dir(out);inventory=m.canonical(dict(schema='SYNTHETIC_CAPTURE_INPUTS_V1',operational_authority=False,files=[dict(path='FIXTURE.public.txt',bytes=len(f.MARKER),sha256=m.sha(f.MARKER))]));archive=m.tar_bytes({'FIXTURE.public.txt':f.MARKER});rows={}
 for op in m.OPS:
  part,flags=m.validate_bound_rows(f.rows(op),op,'PRIMARY');rows.update(part)
 manifest=m.canonical(dict(schema='CAPTURE_NIGHT_EVIDENCE_V1',session='2026-10-08',grid='G19',slot='PRIMARY',files=[dict(path=n,bytes=len(b),sha256=m.sha(b)) for n,b in sorted(rows.items())]));night=m.tar_bytes({**rows,'MANIFEST.private.json':manifest})
 for n,b in [('INPUTS.fixture.tar',archive),('INVENTORY.fixture.json',inventory),('NIGHT.fixture.tar',night),('NIGHT_MANIFEST.fixture.json',manifest)]:m.put(p/n,b)
 m.put(p/'FIXTURE_PINS.public.json',m.canonical(dict(schema='SYNTHETIC_FIXTURE_PINS_V1',operational_READY=False,input_sha256=m.sha(archive),inventory_sha256=m.sha(inventory),night_sha256=m.sha(night),night_manifest_sha256=m.sha(manifest))))
 return p

def public_body(kind,context,values):
 return dict(schema='CAPTURE_OPERATOR_REHEARSAL_PUBLIC_V1',kind=kind,**ctx(context),scope='SYNTHETIC_NO_OPERATIONAL_AUTHORITY',**values)
def context_record(a,b,run):
 m.need(a==b,'REHEARSAL_PUBLIC_CHANGED');v=m.bot_comment(a);c=ctx(v);m.need(v.get('schema')=='CAPTURE_OPERATOR_REHEARSAL_PUBLIC_V1' and v.get('kind')=='EPHEMERAL_RECIPIENT' and v.get('scope')=='SYNTHETIC_NO_OPERATIONAL_AUTHORITY','REHEARSAL_PUBLIC_SCHEMA')
 m.need(re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}',v.get('recipient','')) and run.get('id')==int(c['run_id']) and run.get('run_attempt')==1 and run.get('event')=='push' and run.get('head_branch')=='ops/capture-operator2-rehearsal-20261007' and run.get('path')=='.github/workflows/operator2-rehearsal.yml' and run.get('status')=='in_progress' and run.get('repository',{}).get('full_name')=='duduvcastro/c3po-chief-of-staff-intelligence','REHEARSAL_RUN')
 m.need(a['created_at'].startswith('2026-10-07T'),'REHEARSAL_DATE');return dict(schema='CAPTURE_OPERATOR_REHEARSAL_CONTEXT_V1',**c,scope=v['scope'],recipient=v['recipient'],source_comment_id=a['id'],source_body_sha256=m.sha(a['body'].encode()),source_head_sha=run['head_sha'])
def context_file(raw):
 v=m.strict(raw);c=ctx(v);m.need(v.get('schema')=='CAPTURE_OPERATOR_REHEARSAL_CONTEXT_V1' and v.get('scope')=='SYNTHETIC_NO_OPERATIONAL_AUTHORITY' and raw==m.canonical(v),'REHEARSAL_CONTEXT');return v,c

def make_control(context,kind,cipher,blob,manifest,inventory_cipher=None,inventory_blob=None):
 v,c=context_file(context);m.need(kind in ('PRIVATE_INPUTS','NIGHT_GATES'),'REHEARSAL_CONTROL_KIND');b,h=m.blob_readback(cipher,blob);body=dict(schema='CAPTURE_OPERATOR_REHEARSAL_CONTROL_V1',kind=kind,sequence=1,**c,scope='SYNTHETIC_NO_OPERATIONAL_AUTHORITY',blob_sha=b,ciphertext_sha256=h,manifest_sha256=m.sha(manifest))
 if kind=='PRIVATE_INPUTS':mb,mh=m.blob_readback(inventory_cipher,inventory_blob);body.update(manifest_blob_sha=mb,manifest_ciphertext_sha256=mh)
 return body

def accept_control(comment,context,kind):
 v=m.location(comment);u=comment.get('user',{});m.need(u.get('id')==313137248 and u.get('login')=='duduvcastro' and u.get('type')=='User' and comment.get('author_association')=='OWNER' and comment.get('performed_via_github_app') is None,'REHEARSAL_OPERATOR_ACCOUNT')
 c=ctx(context);m.need(v.get('schema')=='CAPTURE_OPERATOR_REHEARSAL_CONTROL_V1' and v.get('scope')=='SYNTHETIC_NO_OPERATIONAL_AUTHORITY' and v.get('kind')==kind and type(v.get('sequence')) is int and v['sequence']==1 and all(v.get(k)==x for k,x in c.items()),'REHEARSAL_CONTROL_CONTEXT')
 fields={'schema','scope','kind','sequence',*c,'blob_sha','ciphertext_sha256','manifest_sha256'}
 if kind=='PRIVATE_INPUTS':fields|={'manifest_blob_sha','manifest_ciphertext_sha256'}
 m.need(set(v)==fields,'REHEARSAL_CONTROL_FIELDS');return v

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise m.Refused('REHEARSAL_REDIRECT')
class API:
 def __init__(self):
  token=os.environ.get('REHEARSAL_GITHUB_TOKEN','');m.need(token and not re.search(r'[\s\x00-\x1f]',token),'REHEARSAL_TOKEN');self.token=token;self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 def call(self,path,body=None):
  allowed=(body is not None and path=='/issues/429/comments' or body is None and (re.fullmatch('/issues/comments/[1-9][0-9]*',path) or re.fullmatch('/git/blobs/[0-9a-f]{40}',path) or re.fullmatch(r'/issues/429/comments\?since=2026-10-07T\d{2}%3A\d{2}%3A\d{2}Z&per_page=100&page=[1-9][0-9]?',path)))
  m.need(allowed,'REHEARSAL_API_PATH');url=ROOT+path;req=urllib.request.Request(url,data=m.canonical(body) if body is not None else None,headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'synthetic-operator-rehearsal'})
  with self.opener.open(req,timeout=20) as r:
   m.need(r.status==(201 if body is not None else 200) and r.geturl()==url,'REHEARSAL_API_RESPONSE');raw=r.read(24*1024*1024+1)
  m.need(len(raw)<=24*1024*1024,'REHEARSAL_API_LIMIT');return m.strict(raw)
 def publish(self,body):
  text=m.canonical(body).decode();p=self.call('/issues/429/comments',{'body':text});a=self.call('/issues/comments/'+str(p['id']));m.need(a==p and a['body']==text,'REHEARSAL_POST_GET');return a
 def wait(self,context,kind,since,deadline):
  while dt.datetime.now(dt.timezone.utc)<=deadline:
   rows=[]
   for page in range(1,21):
    batch=self.call('/issues/429/comments?since='+since.replace(':','%3A')+'&per_page=100&page='+str(page));m.need(type(batch) is list,'REHEARSAL_COLLECTION');rows.extend(batch)
    if len(batch)<100:break
   else:raise m.Refused('REHEARSAL_COLLECTION_INCOMPLETE')
   hits=[]
   for c in rows:
    try:v=accept_control(c,context,kind)
    except (m.Refused,ValueError,KeyError,TypeError):continue
    a=self.call('/issues/comments/'+str(c['id']));b=self.call('/issues/comments/'+str(c['id']));m.need(a==b==c,'REHEARSAL_CONTROL_CHANGED');hits.append(v)
   m.need(len(hits)<=1,'REHEARSAL_DUPLICATE_CONTROL')
   if hits:return hits[0]
   time.sleep(5)
  raise m.Refused('REHEARSAL_DEADLINE_NO_RETRY')
 def blob(self,b,h):
  m.need(re.fullmatch('[0-9a-f]{40}',b),'REHEARSAL_BLOB');v=self.call('/git/blobs/'+b);raw=base64.b64decode(v['content'].replace('\n',''),validate=True);m.need(m.sha(raw)==h,'REHEARSAL_CIPHER_HASH');m.blob_readback(raw,v);return raw

def worker(age,keygen,home):
 now=dt.datetime.now(dt.timezone.utc);m.need(now.date().isoformat()=='2026-10-07' and now<m.instant('2026-10-07T21:30:00Z') and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','REHEARSAL_DATE_ATTEMPT');m.need(m.sha(m.read(age))==AGE and m.sha(m.read(keygen))==KEYGEN,'REHEARSAL_CRYPTO_PIN');p=m.output_dir(home);fixed=fixtures(p/'fixtures');pins=m.strict(m.read(fixed/'FIXTURE_PINS.public.json'));api=API();context=dict(session='2026-10-07',run_id=os.environ.get('GITHUB_RUN_ID',''),run_attempt=1,nonce=secrets.token_hex(16));ctx(context)
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
 def child(args):
  r=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,env=env,check=False);m.need(r.returncode==0,'REHEARSAL_CRYPTO_FAILED_NO_RETRY');return r.stdout
 child([keygen,'-o',str(p/'ephemeral-key')]);recipient=child([keygen,'-y',str(p/'ephemeral-key')]).decode().strip();m.need(re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}',recipient),'REHEARSAL_KEY');posted=api.publish(public_body('EPHEMERAL_RECIPIENT',context,dict(recipient=recipient,status='AWAITING_SYNTHETIC_INPUTS')));since=(m.instant(posted['created_at'])-dt.timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ');deadline=min(now+dt.timedelta(minutes=20),m.instant('2026-10-07T21:30:00Z'))
 def clear(blob,pin,label):
  raw=api.blob(blob,pin);m.put(p/(label+'.age'),raw);dest=p/(label+'.clear');child([age,'-d','-i',str(p/'ephemeral-key'),'-o',str(dest),str(p/(label+'.age'))]);return m.read(dest)
 private=api.wait(context,'PRIVATE_INPUTS',since,deadline);m.need(private['manifest_sha256']==pins['inventory_sha256'],'REHEARSAL_INVENTORY_PIN');m.need(clear(private['blob_sha'],private['ciphertext_sha256'],'inputs')==m.read(fixed/'INPUTS.fixture.tar') and clear(private['manifest_blob_sha'],private['manifest_ciphertext_sha256'],'inventory')==m.read(fixed/'INVENTORY.fixture.json'),'REHEARSAL_PRIVATE_FIXTURE_BYTES')
 night=api.wait(context,'NIGHT_GATES',since,deadline);m.need(night['manifest_sha256']==pins['night_manifest_sha256'] and clear(night['blob_sha'],night['ciphertext_sha256'],'night')==m.read(fixed/'NIGHT.fixture.tar'),'REHEARSAL_NIGHT_FIXTURE_BYTES');report=public_body('RESULT',context,dict(status='PASS_SYNTHETIC_OPERATOR_EXCHANGE_ONLY',cipher_blobs=3,controls=2,host_calls=0,owner_asks=0,operational_READY=False));api.publish(report);m.put(HOME/'CHANNEL_RESULT.public.json',m.canonical(report));print('SYNTHETIC_EXCHANGE_COMPLETE_NO_HOST_NO_GO')

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);sub=ap.add_subparsers(dest='command',required=True)
 s=sub.add_parser('fixtures');s.add_argument('--out',required=True)
 s=sub.add_parser('context')
 for k in ('public-readback1','public-readback2','run-readback','out'):s.add_argument('--'+k,required=True)
 s=sub.add_parser('control');s.add_argument('--kind',choices=('PRIVATE_INPUTS','NIGHT_GATES'),required=True)
 for k in ('context','cipher','blob-readback','manifest','out'):s.add_argument('--'+k,required=True)
 s.add_argument('--inventory-cipher');s.add_argument('--inventory-blob-readback')
 s=sub.add_parser('worker')
 for k in ('age','keygen','home'):s.add_argument('--'+k,required=True)
 a=ap.parse_args();j=lambda p:m.strict(m.read(p,24*1024*1024))
 if a.command=='fixtures':fixtures(a.out)
 elif a.command=='context':m.put(a.out,m.canonical(context_record(j(a.public_readback1),j(a.public_readback2),j(a.run_readback))))
 elif a.command=='control':
  v=make_control(m.read(a.context),a.kind,m.read(a.cipher),j(a.blob_readback),m.read(a.manifest),m.read(a.inventory_cipher) if a.inventory_cipher else None,j(a.inventory_blob_readback) if a.inventory_blob_readback else None);m.put(a.out,m.canonical(dict(body=m.canonical(v).decode())))
 else:return worker(a.age,a.keygen,a.home)
 print('SYNTHETIC_OPERATOR_DATA_ONLY_NOT_OPERATIONAL')
if __name__=='__main__':
 try:main()
 except Exception:print('SYNTHETIC_REHEARSAL_REFUSED_NO_RETRY');raise SystemExit(2)
