"""Dated bootstrap before runtime acceptance. Fixed local crypto/measure only.

No SSH, signatures, dispatch or self-issued PASS. The signed E5 must explicitly
permit local credentials, ephemeral age key, measurement and ciphertext exchange.
"""
import argparse,datetime as dt,hashlib,json,os,pathlib,re,secrets,subprocess,sys,types
AGE='eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c'
KEYGEN='0a0009db842259d6717f7eeb30acb6b90d2a2eb924c6acd0a0db0ca1f1537899'
INVENTORY='8671e15a46627734dbcc133d59b42b574ffea134548d0cec408bec2177bb5e69'

def module(p,pin,name):
 raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('BOOTSTRAP_SOURCE_PIN')
 m=types.ModuleType(name);m.__file__=str(p);sys.modules[name]=m;exec(compile(raw,str(p),'exec'),m.__dict__);return m

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False)
 for k in ('root','layout','layout-sha256','authority','authority-sha256','private','age','keygen'):ap.add_argument('--'+k,required=True)
 a=ap.parse_args();root=pathlib.Path(a.root);layout_raw=pathlib.Path(a.layout).read_bytes();layout=json.loads(layout_raw)
 if hashlib.sha256(layout_raw).hexdigest()!=a.layout_sha256:raise ValueError('BOOTSTRAP_LAYOUT')
 f=module(root/'capture_job/job_files.py',layout['helpers']['capture_job/job_files.py'],'capture_bootstrap_files')
 ch=module(root/'capture_job/job_channel.py',layout['helpers']['capture_job/job_channel.py'],'capture_bootstrap_channel')
 guard=module(root/'capture_job/checked_program.py',layout['helpers']['capture_job/checked_program.py'],'capture_bootstrap_guard')
 f.need(sys.platform=='linux' and os.geteuid()!=0 and sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','BOOTSTRAP_PROCESS')
 now=dt.datetime.now(dt.timezone.utc);f.need(now.date().isoformat()=='2026-10-08' and dt.datetime.fromisoformat('2026-10-08T11:45:00+00:00')<=now<dt.datetime.fromisoformat('2026-10-08T11:50:00+00:00'),'BOOTSTRAP_BAND')
 guard.layout(layout);guard.sources(root,layout);authority_raw=f.read(a.authority,a.authority_sha256);authority=f.strict(authority_raw);guard.authority(authority,a.layout_sha256,now)
 api=ch.API(os.environ.get('CAPTURE_GITHUB_READ_TOKEN',''))
 for kind,key,pin_key in [('CAPTURE_JOB_DATED_AUTHORITY_RECORD_V1','source_owner_record_comment_id','source_owner_record_body_sha256'),('CAPTURE_JOB_MAC_RETIREMENT_RECORD_V1','operator_election_record_comment_id','operator_election_record_body_sha256')]:
  cid=authority.get(key);q,r=api.comment(cid),api.comment(cid);f.need(q==r and ch.sha(q['body'].encode())==authority[pin_key] and q['created_at']==q['updated_at'],'BOOTSTRAP_AUTHORITY_READBACK')
  u=q.get('user',{});f.need(u.get('id')==ch.OWNER_ID and u.get('login')=='duduvcastro' and u.get('type')=='User' and q.get('author_association')=='OWNER' and q.get('performed_via_github_app') is None,'BOOTSTRAP_AUTHORITY_ACCOUNT')
  v=f.strict(q['body']);f.need(v.get('schema')==kind and v.get('document_sha256')==authority['document_sha256'] and v.get('source_layout_sha256')==a.layout_sha256 and v.get('retired_mac_config_sha256')==authority['retired_mac_config_sha256'],'BOOTSTRAP_AUTHORITY_SCOPE')
  if kind=='CAPTURE_JOB_DATED_AUTHORITY_RECORD_V1':f.need(v.get('owner')=='DUDU' and v.get('answer')=='Assino' and v.get('signed_at_utc')==authority['signed_at_utc'],'BOOTSTRAP_OWNER_RECORD')
  else:f.need(v.get('election')==authority['election'] and v.get('observed_at_utc')==authority['election_observed_at_utc'],'BOOTSTRAP_ELECTION_RECORD')
 home=f.directory(a.private,True);output=f.directory(home/'cipher',True);f.directory(home/'calls',True);claims=f.directory(home/'challenge-claims',True);f.directory(home/'challenge',True)
 f.put(home/'DATED_AUTHORITY.json',authority_raw);f.put(home/'LAYOUT.json',layout_raw)
 target=os.environ.get('C3PO_AWS_USER','')+'@'+os.environ.get('C3PO_AWS_HOST','');f.need(re.fullmatch(r'[a-z_][a-z0-9_-]*@[A-Za-z0-9.-]+',target),'BOOTSTRAP_TARGET')
 key=os.environ.get('C3PO_AWS_SSH_KEY','').encode();known=os.environ.get('C3PO_AWS_KNOWN_HOSTS','').encode();f.need(0<len(key)<=65536 and 0<len(known)<=65536,'BOOTSTRAP_CREDENTIALS')
 f.put(home/'ssh-key',key);f.put(home/'known-hosts',known)
 f.read(a.age,AGE,False);f.read(a.keygen,KEYGEN,False)
 env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','GITHUB_RUN_ID':os.environ.get('GITHUB_RUN_ID',''),'GITHUB_RUN_ATTEMPT':'1'}
 ctx=ch.context(dict(session='2026-10-08',run_id=env['GITHUB_RUN_ID'],run_attempt=1,nonce=secrets.token_hex(16)))
 def child(argv,timeout=60,stdin=None):
  r=subprocess.run(argv,input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=timeout,check=False)
  f.need(r.returncode==0,'BOOTSTRAP_CHILD_REFUSED_NO_RETRY');return r.stdout,r.stderr
 child([a.keygen,'-o',str(home/'age-key')]);f.read(home/'age-key')
 recipient,err=child([a.keygen,'-y',str(home/'age-key')]);recipient=recipient.decode().strip();f.need(not err and re.fullmatch('age1[023456789acdefghjklmnpqrstuvwxyz]{58}',recipient),'BOOTSTRAP_EPHEMERAL_RECIPIENT')
 api.publish('EPHEMERAL_RECIPIENT',ctx,dict(recipient=recipient,manifest_sha256=INVENTORY,status='AWAITING_PRIVATE_INPUTS'))
 control=api.wait_control(ctx,'PRIVATE_INPUTS',1,'2026-10-08T11:50:00Z');f.need(control['manifest_sha256']==control['document_sha256']==INVENTORY,'BOOTSTRAP_INVENTORY')
 def decrypt(blob,pin,name):
  cipher=api.blob(blob,pin);f.put(home/(name+'.age'),cipher);out=home/name
  child([a.age,'-d','-i',str(home/'age-key'),'-o',str(out),str(home/(name+'.age'))]);f.read(out,limit=16*1024*1024);return out
 archive=decrypt(control['blob_sha'],control['ciphertext_sha256'],'INPUTS.tar');inventory=decrypt(control['manifest_blob_sha'],control['manifest_ciphertext_sha256'],'INVENTORY.json');f.read(inventory,INVENTORY)
 importer=root/'capture_job/private_bundle.py';f.read(importer,layout['tools']['import']['sha256'],False)
 out,err=child([str(root/'venv/bin/python'),'-I','-S','-B',str(importer),'--decrypted-tar',str(archive),'--manifest',str(inventory),'--manifest-sha256',INVENTORY,'--out',str(home/'inputs')]);f.need(not err and f.strict(out)['status']=='PRIVATE_DATA_STORED_NOT_OPERATION_AUTHORITY','BOOTSTRAP_INPUT_IMPORT')
 measurement=home/'RUNTIME_IDENTITY.private.json';cache=f.directory(home/'measure-cache',True);program=root/'capture_job/measure_job.py';f.read(program,layout['helpers']['capture_job/measure_job.py'],False)
 out,err=child([str(root/'venv/bin/python'),'-I','-S','-B','-X','pycache_prefix='+str(cache),str(program),'--root',str(root),'--layout',str(home/'LAYOUT.json'),'--layout-sha256',a.layout_sha256,'--authority',str(home/'DATED_AUTHORITY.json'),'--authority-sha256',a.authority_sha256,'--nonce',ctx['nonce'],'--out',str(measurement)],timeout=180)
 f.need(not err,'BOOTSTRAP_MEASURE_OUTPUT');measured=f.strict(out);f.need(measured['status']=='MEASURED_NOT_ACCEPTED' and measured['measurement_sha256']==f.sha(f.read(measurement)),'BOOTSTRAP_MEASURE_BINDING')
 export=root/'capture_job/private_export.py';f.read(export,layout['tools']['export']['sha256'],False)
 out,err=child([str(root/'venv/bin/python'),'-I','-S','-B',str(export),'--input',str(measurement),'--age-binary',a.age,'--age-sha256',AGE,'--out',str(output/'RUNTIME_IDENTITY.json.age')]);f.need(not err,'BOOTSTRAP_CIPHER_OUTPUT')
 st=claims.stat();state=dict(schema='CAPTURE_JOB_STATE_V1',context=ctx,root=str(root),private=str(home),layout=str(home/'LAYOUT.json'),layout_sha256=a.layout_sha256,authority=str(home/'DATED_AUTHORITY.json'),authority_sha256=a.authority_sha256,measurement=str(measurement),measurement_sha256=measured['measurement_sha256'],ssh_executable_sha256=measured['ssh_executable_sha256'],age=a.age,keygen=a.keygen,target=target,claim_root_identity=dict(path=str(claims),device=st.st_dev,inode=st.st_ino))
 f.put(home/'STATE.json',f.canonical(state));f.put(home/'BOOTSTRAP.COMPLETE.json',f.canonical(dict(status='BOOTSTRAP_MEASURED_NOT_ACCEPTED',**ctx)))
 api.publish('RUNTIME_MEASURED',ctx,dict(measurement_sha256=measured['measurement_sha256'],manifest_sha256=a.layout_sha256,ciphertext_sha256=f.sha(f.read(output/'RUNTIME_IDENTITY.json.age')),artifact_name='RUNTIME_IDENTITY',status='MEASURED_NOT_ACCEPTED'))
 print('{"status":"BOOTSTRAP_MEASURED_NOT_ACCEPTED","operational_READY":false}')
if __name__=='__main__':
 try:main()
 except Exception:print('{"status":"BOOTSTRAP_REFUSED_NO_RETRY","operational_READY":false}');raise SystemExit(2)
