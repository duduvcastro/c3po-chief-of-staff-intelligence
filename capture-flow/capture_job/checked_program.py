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
 'decrypt':'capture_job/crypto_input.py','night_import':'capture_job/night_bundle.py','inspect':'capture_job/inspect_bound.py','controller':'capture_job/live_adapter.py',
 'challenge_dispatch':'capture_job/bootstrap/transport_challenge/dispatch_once.py',
 'read_dispatch':'families/k9_phase_read/build/dispatch_once.py',
 'step_dispatch':'families/k9_phase_step/build/dispatch_once.py'}
RETIRED_MAC_SETS={'policy_read': {'sheet_sha256': '3cbba6513c8a5910cc0cc08b804e05cff0cbd79b3eb8b501f5ff4b27b48e5d28', 'config_sha256': '00485fcc66681afc6b1ed8f3da62ff69f13103dbb9d03bad77671576cb605a22', 'go_sha256': '20fc20045746494a99359b6636fbc1266fca5ce51a64312b99db6217bb661dcb'}, 'capture_launch': {'sheet_sha256': 'd18fa79b8180d03eeb78245f80bb7a4235fadcb17800ecf76c21a3c64f6181d5', 'config_sha256': '3995f8a6483c702ec142d9da5f44acfb5b45a35346ad51effa73cca1f114bd40', 'go_sha256': 'a24425ba3faf7454dce0c5e472c2db61ec194dbd784d443190d76091eaaf7b12'}, 'capture_result': {'sheet_sha256': 'e0c70fabf828ae95bcdc932943a3e5067a594fb2665152ec632cb4cf0ea52621', 'config_sha256': '9e2a55ca3aa8a9d99a6d602e5ec6a240546e5a31d660d3ee91ce2b3fbfdd2254', 'go_sha256': '79517c124f10e33e6ec84f58c85ca68d998ba723bc3963eb32a5b2940c5eb6b5'}, 'capture_cleanup': {'sheet_sha256': '9947af8b8dfae26d15adab3e89eaf5b2779ded1af68a7426e66da0886d19298c', 'config_sha256': '38f90d6ed8f79855a0de12cff42927290c953b3be76fa278489d09fc5d179e64', 'go_sha256': '0143a4eb96618aff71c5d97fb7595369c2df49b9478c9a9589f41c218a8403dd'}}
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
 need(type(value) is dict and set(value)=={'schema','session','tools','helpers','dispatch_runtime'} and value['schema']=='CAPTURE_JOB_SOURCE_LAYOUT_V1' and value['session']=='2026-10-08','PROGRAM_LAYOUT')
 need(type(value['tools']) is dict and set(value['tools'])==set(PATHS),'PROGRAM_TOOL_SET')
 for role,path in PATHS.items():
  item=value['tools'][role];need(set(item)=={'path','sha256'} and item['path']==path,'PROGRAM_TOOL_PATH');pin(item['sha256'])
 need(type(value['helpers']) is dict and not set(value['helpers'])&set(PATHS.values()) and 'capture_job/checked_program.py' in value['helpers'] and all(type(k) is str and re.fullmatch(r'capture_job/[A-Za-z0-9_/.-]+\.py',k) and '..' not in pathlib.PurePosixPath(k).parts for k in value['helpers']),'PROGRAM_HELPER_PATH')
 for item in value['helpers'].values():pin(item)
 dispatcher_layout(value)
 return value
def authority(value,layout_sha,now):
 need(value.get('schema')=='CAPTURE_JOB_DATED_AUTHORITY_V1' and value.get('status')=='SIGNED' and value.get('owner')=='DUDU' and value.get('answer')=='Assino'
      and value.get('session')=='2026-10-08' and value.get('source_layout_sha256')==layout_sha
      and value.get('outside_Mac') is True and value.get('single_job') is True and value.get('single_use') is True and value.get('retry') is False
      and value.get('election')=='JOB_ONLY_MAC_CAPTURE_RETIRED_BEFORE_PREPARE','PROGRAM_DATED_AUTHORITY')
 retired=value.get('retired_mac_config_sha256');need(type(retired) is list and len(retired)==len(set(retired))==4,'PROGRAM_MAC_ELECTION')
 for item in retired:pin(item)
 need(set(retired)=={x['config_sha256'] for x in RETIRED_MAC_SETS.values()},'PROGRAM_EXACT_MAC_SETS')
 for key in ('document_sha256','source_owner_record_body_sha256','operator_election_record_body_sha256'):pin(value.get(key))
 need(instant(value['signed_at_utc'])<=now and instant(value['election_observed_at_utc'])<=now and instant(value['election_observed_at_utc'])>=instant(value['signed_at_utc']),'PROGRAM_AUTHORITY_ORDER')
 return value
def approval(value,measurement_sha,layout_sha,authority_sha,ctx,now):
 need(value.get('schema')=='CAPTURE_JOB_PHYSICAL_APPROVAL_V1' and value.get('verdict')=='PASS_PHYSICAL_RUNTIME'
      and all(value.get(k)==v for k,v in ctx.items()) and type(value.get('run_attempt')) is int
      and value.get('measurement_sha256')==measurement_sha and value.get('source_layout_sha256')==layout_sha
      and value.get('dated_authority_sha256')==authority_sha and value.get('runtime_guard_sha256')==HELPER
      and value.get('binder_sha256')==BINDER and value.get('accepted_seals_sha256')==REGISTRY,'PROGRAM_APPROVAL')
 pin(value.get('review_body_sha256'));pin(value.get('ssh_executable_sha256'));a,b=instant(value['measured_at_utc']),instant(value['reviewed_at_utc'])
 need(a.date().isoformat()=='2026-10-08' and a<=b<=now,'PROGRAM_APPROVAL_ORDER');return value
def measurement_binding(value,ctx,layout_sha,authority_sha,accepted):
 need(all(value.get(k)==v for k,v in ctx.items()) and type(value.get('run_attempt')) is int,'PROGRAM_MEASUREMENT_OWN_CONTEXT')
 need(value.get('source_layout_sha256')==layout_sha and value.get('dated_authority_sha256')==authority_sha,'PROGRAM_MEASUREMENT_SOURCE_AUTHORITY')
 need(value.get('measured_at_utc')==accepted['measured_at_utc'],'PROGRAM_MEASUREMENT_TIME')
 return value
DISPATCH_MODULES={'challenge_dispatch':('launcher_stdin','transport_once','capture_transport_challenge'),
 'read_dispatch':('launcher_stdin','transport_once','k9_phase_read'),
 'step_dispatch':('launcher_stdin','transport_once','k9_phase_step')}
def dispatcher_layout(manifest):
 d=manifest['dispatch_runtime'];need(type(d) is dict and set(d)==set(DISPATCH_MODULES),'PROGRAM_DISPATCH_SET')
 for role,names in DISPATCH_MODULES.items():
  need(type(d[role]) is dict and set(d[role])==set(names),'PROGRAM_DISPATCH_MODULES')
  for pin_value in d[role].values():pin(pin_value)
 return d
def load_dispatch_modules(role,root,manifest,pinned):
 if role not in DISPATCH_MODULES:return
 home=(root/PATHS[role]).parent
 for name in DISPATCH_MODULES[role]:
  need(name not in sys.modules,'PROGRAM_DISPATCH_MODULE_PRELOADED')
  path=home/(name+'.py');relative=str(path.relative_to(root));raw=pinned[relative]
  need(sha(raw)==manifest['dispatch_runtime'][role][name],'PROGRAM_DISPATCH_MODULE_PIN')
  module=types.ModuleType(name);module.__file__=str(path)
  module.__spec__=__import__('importlib.machinery',fromlist=['ModuleSpec']).ModuleSpec(name,loader=None,origin=str(path))
  sys.modules[name]=module;exec(compile(raw,str(path),'exec'),module.__dict__)
def sources(root,manifest):
 files={}
 for item in manifest['tools'].values():files[item['path']]=read(root/item['path'],item['sha256'])
 for path,p in manifest['helpers'].items():files[path]=read(root/path,p)
 for role,modules in dispatcher_layout(manifest).items():
  home=pathlib.PurePosixPath(PATHS[role]).parent
  for name,p in modules.items():
   path=str(home/(name+'.py'));files[path]=read(root/path,p)
 need(manifest['tools']['binder']['sha256']==BINDER,'PROGRAM_BINDER_PIN');read(root/'binder/bind/ACCEPTED_SEALS.json',REGISTRY)
 return files
def main(argv=None):
 ap=argparse.ArgumentParser(allow_abbrev=False)
 for k in ('root','layout','layout-sha256','measurement','measurement-sha256','approval','approval-sha256','authority','authority-sha256','nonce'):ap.add_argument('--'+k,required=True)
 ap.add_argument('--tool',required=True,choices=tuple(PATHS));ap.add_argument('tool_args',nargs=argparse.REMAINDER);a=ap.parse_args(argv)
 try:
  root=pathlib.Path(a.root);need(root.is_absolute() and sys.platform=='linux' and os.geteuid()!=0 and os.environ.get('GITHUB_RUN_ATTEMPT')=='1','PROGRAM_ACTUAL_LINUX')
  run=os.environ.get('GITHUB_RUN_ID','');need(re.fullmatch('[1-9][0-9]{5,19}',run) and re.fullmatch('[0-9a-f]{32}',a.nonce),'PROGRAM_JOB')
  now=dt.datetime.now(dt.timezone.utc);need(now.date().isoformat()=='2026-10-08' and instant('2026-10-08T11:45:00Z')<=now<instant('2026-10-08T14:45:00Z'),'PROGRAM_DATE_OR_JOB_BAND')
  ctx=dict(session='2026-10-08',run_id=run,run_attempt=1,nonce=a.nonce)
  manifest=layout(strict(read(a.layout,a.layout_sha256)));authority(strict(read(a.authority,a.authority_sha256,True)),a.layout_sha256,now)
  expected=strict(read(a.measurement,a.measurement_sha256,True));accepted=approval(strict(read(a.approval,a.approval_sha256,True)),a.measurement_sha256,a.layout_sha256,a.authority_sha256,ctx,now)
  measurement_binding(expected,ctx,a.layout_sha256,a.authority_sha256,accepted)
  need(sha(read('/usr/bin/ssh',limit=16*1024*1024))==accepted['ssh_executable_sha256'],'PROGRAM_SSH_PIN')
  pinned=sources(root,manifest);helper_path=root/'binder/bind/runtime_identity.py';helper=read(helper_path,HELPER)
  mod=types.ModuleType('runtime_identity');mod.__file__=str(helper_path);sys.modules['runtime_identity']=mod;exec(compile(helper,str(helper_path),'exec'),mod.__dict__)
  observed=mod.observe(root,(helper_path,pathlib.Path(__file__).absolute()),expected=expected);mod.compare(expected,observed)
  need(pinned==sources(root,manifest),'PROGRAM_SOURCE_CHANGED_DURING_GUARD')
  need(a.tool_args[:1]==['--'] and len(a.tool_args)>1,'PROGRAM_ARGUMENTS')
  path=root/PATHS[a.tool];source=pinned[PATHS[a.tool]];sys.argv=[str(path)]+a.tool_args[1:]
 except Exception:
  print('{"status":"REFUSED_PHYSICAL_PROGRAM_GUARD","operational_READY":false}');return 2
 load_dispatch_modules(a.tool,root,manifest,pinned)
 exec(compile(source,str(path),'exec'),{'__name__':'__main__','__file__':str(path),'__package__':None,'__builtins__':__builtins__})
 return 0
if __name__=='__main__':raise SystemExit(main())
