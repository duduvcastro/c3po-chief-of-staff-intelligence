"""Actual dated instance measurement; never self-accepts the instance."""
import argparse,hashlib,json,os,pathlib,sys,types

def main():
 ap=argparse.ArgumentParser(allow_abbrev=False)
 for k in ('root','layout','layout-sha256','authority','authority-sha256','nonce','out'):ap.add_argument('--'+k,required=True)
 a=ap.parse_args();root=pathlib.Path(a.root);layout_raw=pathlib.Path(a.layout).read_bytes();v=json.loads(layout_raw)
 if hashlib.sha256(layout_raw).hexdigest()!=a.layout_sha256:raise ValueError('MEASURE_LAYOUT')
 p=root/'capture_job/checked_program.py';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=v['helpers'].get('capture_job/checked_program.py'):raise ValueError('MEASURE_GUARD')
 guard=types.ModuleType('capture_measured_guard');guard.__file__=str(p);sys.modules[guard.__name__]=guard;exec(compile(raw,str(p),'exec'),guard.__dict__)
 guard.need(sys.platform=='linux' and os.geteuid()!=0 and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','MEASURE_ACTUAL_JOB')
 now=guard.dt.datetime.now(guard.dt.timezone.utc);guard.need(now.date().isoformat()=='2026-10-08','MEASURE_DATE')
 manifest=guard.layout(guard.strict(layout_raw));guard.authority(guard.strict(guard.read(a.authority,a.authority_sha256,True)),a.layout_sha256,now);sources=guard.sources(root,manifest)
 helper_path=root/'binder/bind/runtime_identity.py';helper=guard.read(helper_path,guard.HELPER);m=types.ModuleType('runtime_identity');m.__file__=str(helper_path);sys.modules[m.__name__]=m;exec(compile(helper,str(helper_path),'exec'),m.__dict__)
 observed=m.observe(root,(helper_path,p,pathlib.Path(__file__).absolute()));guard.need(sources==guard.sources(root,manifest),'MEASURE_SOURCE_CHANGED')
 guard.need(guard.re.fullmatch('[0-9a-f]{32}',a.nonce) and guard.re.fullmatch('[1-9][0-9]{5,19}',os.environ.get('GITHUB_RUN_ID','')),'MEASURE_OWN_CONTEXT')
 observed.update(source_layout_sha256=a.layout_sha256,dated_authority_sha256=a.authority_sha256,runtime_guard_sha256=guard.HELPER,measurement_is_not_acceptance=True,session='2026-10-08',run_id=os.environ['GITHUB_RUN_ID'],run_attempt=1,nonce=a.nonce,measured_at_utc=guard.dt.datetime.now(guard.dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
 raw=(json.dumps(observed,sort_keys=True,indent=2)+'\n').encode();fd=os.open(a.out,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 print(json.dumps(dict(status='MEASURED_NOT_ACCEPTED',measurement_sha256=guard.sha(raw),source_layout_sha256=a.layout_sha256,ssh_executable_sha256=guard.sha(guard.read('/usr/bin/ssh',limit=16*1024*1024)),actual_host_calls=0,operational_READY=False)))
if __name__=='__main__':main()
