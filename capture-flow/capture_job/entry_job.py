"""Fixed staged entry. Runtime approval is external, never generated here."""
import argparse,datetime as dt,hashlib,json,os,pathlib,subprocess,sys,types

def load(p,pin,name):
 raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('ENTRY_SOURCE')
 m=types.ModuleType(name);m.__file__=str(p);sys.modules[name]=m;exec(compile(raw,str(p),'exec'),m.__dict__);return m

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False);ap.add_argument('stage',choices=('challenge-sheet','challenge-execute','prepare-four','sign-four','run'));ap.add_argument('--state',required=True);a=ap.parse_args()
 state=json.loads(pathlib.Path(a.state).read_bytes());root=pathlib.Path(state['root']);home=pathlib.Path(state['private']);layout_raw=pathlib.Path(state['layout']).read_bytes()
 if hashlib.sha256(layout_raw).hexdigest()!=state['layout_sha256']:raise ValueError('ENTRY_LAYOUT')
 layout=json.loads(layout_raw);f=load(root/'capture_job/job_files.py',layout['helpers']['capture_job/job_files.py'],'capture_entry_files');state=f.strict(f.read(a.state));ch=load(root/'capture_job/job_channel.py',layout['helpers']['capture_job/job_channel.py'],'capture_entry_channel');api=ch.API(os.environ.get('CAPTURE_GITHUB_READ_TOKEN',''));ctx=ch.context(state['context'])
 f.need(os.environ.get('GITHUB_RUN_ID')==ctx['run_id'] and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','ENTRY_JOB')
 f.need(not (home/'HALTED.json').exists(),'ENTRY_HALTED');api.assert_no_halt(ctx)
 if a.stage=='challenge-sheet':
  control=api.wait_control(ctx,'RUNTIME_APPROVAL',1,'2026-10-08T11:51:00Z');v=control['document'];f.need(v['schema']=='CAPTURE_JOB_PHYSICAL_APPROVAL_V1' and all(v.get(k)==x for k,x in ctx.items()) and v['measurement_sha256']==state['measurement_sha256'] and v['source_layout_sha256']==state['layout_sha256'] and v['dated_authority_sha256']==state['authority_sha256'] and v['ssh_executable_sha256']==state['ssh_executable_sha256'],'ENTRY_APPROVAL_BINDING')
  # The external review must exist as real unedited #429 bytes, not a future hash.
  q=api.review_by_body_hash(v['review_body_sha256'],lambda:dt.datetime.now(dt.timezone.utc))
  f.need(all(x in q['body'] for x in (state['measurement_sha256'],state['layout_sha256'],ctx['run_id'],ctx['nonce'],'PASS_PHYSICAL_RUNTIME')),'ENTRY_REVIEW_SCOPE')
  f.put(home/'PHYSICAL_APPROVAL.json',f.canonical(v));f.put(home/'PHYSICAL_REVIEW.public.txt',q['body'].encode())
 approval_raw=f.read(home/'PHYSICAL_APPROVAL.json');guard=root/'capture_job/checked_program.py';f.read(guard,layout['helpers']['capture_job/checked_program.py'],False);cache=f.directory(home/('entry-cache-'+a.stage),True)
 argv=[str(root/'venv/bin/python'),'-I','-S','-B','-X','pycache_prefix='+str(cache),str(guard),'--root',str(root),'--layout',state['layout'],'--layout-sha256',state['layout_sha256'],'--measurement',state['measurement'],'--measurement-sha256',state['measurement_sha256'],'--approval',str(home/'PHYSICAL_APPROVAL.json'),'--approval-sha256',f.sha(approval_raw),'--authority',state['authority'],'--authority-sha256',state['authority_sha256'],'--nonce',ctx['nonce'],'--tool','controller','--',a.stage,'--state',a.state]
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','GITHUB_RUN_ID':ctx['run_id'],'GITHUB_RUN_ATTEMPT':'1','CAPTURE_GITHUB_READ_TOKEN':os.environ.get('CAPTURE_GITHUB_READ_TOKEN','')}
 # No plaintext output escapes the job. A timeout is consumed, never retried.
 out=home/('ENTRY-'+a.stage+'.stdout.private');err=home/('ENTRY-'+a.stage+'.stderr.private')
 with os.fdopen(os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as o,os.fdopen(os.open(err,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600),'wb') as e:
  remaining=(dt.datetime.fromisoformat('2026-10-08T14:45:00+00:00')-dt.datetime.now(dt.timezone.utc)).total_seconds();f.need(remaining>0,'ENTRY_JOB_END');r=subprocess.run(argv,stdout=o,stderr=e,env=env,timeout=min(remaining,10800 if a.stage=='run' else 2700),check=False)
 f.need(r.returncode==0,'ENTRY_STAGE_REFUSED_NO_RETRY');print('{"status":"GUARDED_STAGE_COMPLETE","operational_READY":false}')
if __name__=='__main__':
 try:main()
 except Exception:print('{"status":"ENTRY_REFUSED_NO_RETRY","operational_READY":false}');raise SystemExit(2)
