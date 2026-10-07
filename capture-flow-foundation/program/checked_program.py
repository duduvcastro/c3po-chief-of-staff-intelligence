"""Compare external physical identity, then execute the pinned tool IN THIS process.

No self-acceptance, arbitrary programs or unguarded child commands. Measurement is
separate and not authority. E5, external review and actual 08/10 identity are needed.
"""
import argparse,datetime as dt,hashlib,json,os,pathlib,re,stat,sys,types
HELPER='796ec07043f628b96bfdab20e5103567a70cc62c15f3ee63ce74ea36f6a0e2d6'
BINDER='9dbff222a3f815573d0cf89686f16a841260831400da40c5055999d7c71af133'
REGISTRY='78eb4ab25db448d677b5c54bb2f91346c194427fee88028260d1ba2f7be50d72'
PATHS={'binder':'binder/bind/bind_once.py','constructor':'capture_job/bootstrap/constructor.py',
 'response':'capture_job/api/github_readback.py','import':'capture_job/private_bundle.py',
 'export':'capture_job/private_export.py','render':'capture_job/parameter_render.py',
 'inspect':'capture_job/inspect_bound.py','controller':'capture_job/live_adapter.py',
 'challenge_dispatch':'capture_job/bootstrap/transport_challenge/dispatch_once.py',
 'read_dispatch':'families/k9_phase_read/build/dispatch_once.py',
 'step_dispatch':'families/k9_phase_step/build/dispatch_once.py'}
class Refused(ValueError):pass
def need(ok,code):
 if not ok:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(v):need(type(v) is str and re.fullmatch('[0-9a-f]{64}',v) and v!='0'*64,'PROGRAM_PIN');return v
def strict(raw):
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'PROGRAM_DUPLICATE');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'PROGRAM_NONFINITE'))
def instant(v):
 need(type(v) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',v),'PROGRAM_TIME');return dt.datetime.fromisoformat(v.replace('Z','+00:00'))
def read(path,expected=None,private=False,limit=32*1024*1024):
 p=pathlib.Path(path);need(p.is_absolute(),'PROGRAM_ABSOLUTE')
 for part in (p,*p.parents):need(not part.is_symlink(),'PROGRAM_LINK')
 fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and not a.st_mode&0o022 and 0<a.st_size<=limit,'PROGRAM_FILE')
  need(not private or a.st_uid==os.getuid() and stat.S_IMODE(a.st_mode)==0o600,'PROGRAM_PRIVATE')
  raw=f.read(limit+1);b=os.fstat(f.fileno())
 def identity(v):return v.st_dev,v.st_ino,v.st_size,v.st_mtime_ns,v.st_ctime_ns
 need(identity(a)==identity(b)==identity(p.lstat()) and len(raw)==a.st_size,'PROGRAM_CHANGED')
 if expected is not None:need(sha(raw)==pin(expected),'PROGRAM_BYTES')
 return raw
def layout(value):
 need(type(value) is dict and set(value)=={'schema','session','tools','helpers'} and value['schema']=='CAPTURE_JOB_SOURCE_LAYOUT_V1' and value['session']=='2026-10-08','PROGRAM_LAYOUT')
 need(type(value['tools']) is dict and set(value['tools'])==set(PATHS),'PROGRAM_TOOL_SET')
 for role,path in PATHS.items():
  item=value['tools'][role];need(set(item)=={'path','sha256'} and item['path']==path,'PROGRAM_TOOL_PATH');pin(item['sha256'])
 need(type(value['helpers']) is dict and not set(value['helpers'])&set(PATHS.values()) and 'capture_job/checked_program.py' in value['helpers'] and all(type(k) is str and re.fullmatch(r'capture_job/[A-Za-z0-9_/.-]+\.py',k) and '..' not in pathlib.PurePosixPath(k).parts for k in value['helpers']),'PROGRAM_HELPER_PATH')
 for item in value['helpers'].values():pin(item)
 return value
def authority(value,layout_sha,now):
 need(value.get('schema')=='CAPTURE_JOB_DATED_AUTHORITY_V1' and value.get('status')=='SIGNED' and value.get('owner')=='DUDU' and value.get('answer')=='Assino'
      and value.get('session')=='2026-10-08' and value.get('source_layout_sha256')==layout_sha
      and value.get('outside_Mac') is True and value.get('single_job') is True and value.get('single_use') is True and value.get('retry') is False
      and value.get('election')=='JOB_ONLY_MAC_CAPTURE_RETIRED_BEFORE_PREPARE','PROGRAM_DATED_AUTHORITY')
 retired=value.get('retired_mac_config_sha256');need(type(retired) is list and len(retired)==len(set(retired))==4,'PROGRAM_MAC_ELECTION')
 for item in retired:pin(item)
 for key in ('document_sha256','source_owner_record_body_sha256','operator_election_record_body_sha256'):pin(value.get(key))
 need(instant(value['signed_at_utc'])<=now and instant(value['election_observed_at_utc'])<=now and instant(value['election_observed_at_utc'])>=instant(value['signed_at_utc']),'PROGRAM_AUTHORITY_ORDER')
 return value
def approval(value,measurement_sha,layout_sha,authority_sha,ctx,now):
 need(value.get('schema')=='CAPTURE_JOB_PHYSICAL_APPROVAL_V1' and value.get('verdict')=='PASS_PHYSICAL_RUNTIME'
      and all(value.get(k)==v for k,v in ctx.items()) and type(value.get('run_attempt')) is int
      and value.get('measurement_sha256')==measurement_sha and value.get('source_layout_sha256')==layout_sha
      and value.get('dated_authority_sha256')==authority_sha and value.get('runtime_guard_sha256')==HELPER
      and value.get('binder_sha256')==BINDER and value.get('accepted_seals_sha256')==REGISTRY,'PROGRAM_APPROVAL')
 pin(value.get('review_body_sha256'));a,b=instant(value['measured_at_utc']),instant(value['reviewed_at_utc'])
 need(a.date().isoformat()=='2026-10-08' and a<=b<=now,'PROGRAM_APPROVAL_ORDER');return value
def sources(root,manifest):
 files={}
 for item in manifest['tools'].values():files[item['path']]=read(root/item['path'],item['sha256'])
 for path,p in manifest['helpers'].items():files[path]=read(root/path,p)
 need(manifest['tools']['binder']['sha256']==BINDER,'PROGRAM_BINDER_PIN');read(root/'binder/bind/ACCEPTED_SEALS.json',REGISTRY)
 return files
def main(argv=None):
 ap=argparse.ArgumentParser(allow_abbrev=False)
 for k in ('root','layout','layout-sha256','measurement','measurement-sha256','approval','approval-sha256','authority','authority-sha256','nonce'):ap.add_argument('--'+k,required=True)
 ap.add_argument('--tool',required=True,choices=tuple(PATHS));ap.add_argument('tool_args',nargs=argparse.REMAINDER);a=ap.parse_args(argv)
 try:
  root=pathlib.Path(a.root);need(root.is_absolute() and sys.platform=='linux' and os.geteuid()!=0 and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','PROGRAM_ACTUAL_LINUX')
  run=os.environ.get('GITHUB_RUN_ID','');need(re.fullmatch('[1-9][0-9]{5,19}',run) and re.fullmatch('[0-9a-f]{32}',a.nonce),'PROGRAM_JOB')
  now=dt.datetime.now(dt.timezone.utc);need(now.date().isoformat()=='2026-10-08','PROGRAM_DATE')
  ctx=dict(session='2026-10-08',run_id=run,run_attempt=1,nonce=a.nonce)
  manifest=layout(strict(read(a.layout,a.layout_sha256)));authority(strict(read(a.authority,a.authority_sha256,True)),a.layout_sha256,now)
  expected=strict(read(a.measurement,a.measurement_sha256,True));approval(strict(read(a.approval,a.approval_sha256,True)),a.measurement_sha256,a.layout_sha256,a.authority_sha256,ctx,now)
  pinned=sources(root,manifest);helper_path=root/'binder/bind/runtime_identity.py';helper=read(helper_path,HELPER)
  mod=types.ModuleType('runtime_identity');mod.__file__=str(helper_path);sys.modules['runtime_identity']=mod;exec(compile(helper,str(helper_path),'exec'),mod.__dict__)
  observed=mod.observe(root,(helper_path,pathlib.Path(__file__).absolute()),expected=expected);mod.compare(expected,observed)
  need(pinned==sources(root,manifest),'PROGRAM_SOURCE_CHANGED_DURING_GUARD')
  need(a.tool_args[:1]==['--'] and len(a.tool_args)>1,'PROGRAM_ARGUMENTS')
  path=root/PATHS[a.tool];source=pinned[PATHS[a.tool]];sys.argv=[str(path)]+a.tool_args[1:]
 except Exception:
  print('{"status":"REFUSED_PHYSICAL_PROGRAM_GUARD","operational_READY":false}');return 2
 exec(compile(source,str(path),'exec'),{'__name__':'__main__','__file__':str(path),'__package__':None,'__builtins__':__builtins__})
 return 0
if __name__=='__main__':raise SystemExit(main())
