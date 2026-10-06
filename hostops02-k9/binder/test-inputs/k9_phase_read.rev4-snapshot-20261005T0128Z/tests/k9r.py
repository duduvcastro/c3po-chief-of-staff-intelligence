"""Fixtures of the K9R tests: request plans built from the emulated host as a binder would copy them from the TREE
receipt, the K9 tree as K4-E0 and K3-K9 would leave it, the files a K9W launch and the K9 runner (or the packaged risk
CLI) would leave for a RESULT, and the emulated probe container.

The emulated probe container does not stand in for the snippet: it EXECUTES the exact bytes the run put on standard
input with a real interpreter in isolated mode, with the command words the run gave (after `timeout -s KILL 36`),
the environment the docker CLI would give it (the env file of the emulated tree and the one --env word), against a
stand-in of the application package written to a temporary directory (FAKE below). Three things are put in front of
those bytes, for the test only: the stand-in on the import path, a fixed wall clock (the epoch's evening, not the
workstation's), and nothing else. tests/test_snippet.py runs the same bytes against the release's own modules.

hostemu is extended here by subclassing, never edited: K9Docker knows the probe's prefix (--network bridge,
--env-file, --env) and renders this source's own inspect format with State.OOMKilled. Everything here is synthetic:
no value, identity or byte of the real host, release or provider."""
import atexit
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
EPOCH='R2D2-V2-SHADOW-2026-10-05'
DAY='2026-10-06'
REVISION=hostemu.REVISION
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
NOTE='ab5159bea34b3239379e87c2500d383f0777cc6186618435ba0ea9f61e3d596c'
DATA=hostemu.DATA
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'
PLACEMENT={'k9_root':K9_ROOT,'source_root':SOURCE_ROOT,'days':K9_ROOT+'/days','tools':K9_ROOT+'/tools','claims':K9_ROOT+'/claims',
           'secrets':K9_ROOT+'/secrets','emitter':K9_ROOT+'/secrets/emitter','provider_env_file':K9_ROOT+'/secrets/provider.env',
           'risk_db_env_file':K9_ROOT+'/secrets/risk-db.env','emitter_password':K9_ROOT+'/secrets/emitter/password','source_open_root':None,'k9_open_root':None,'september_open_root':DATA,
           'decision':'d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53','decision_6':'#429 comment 5985748037'}
SEPTEMBER=(DATA+'/.r2d2-v2-risk-secrets',DATA+'/.r2d2-v2-risk-secrets/risk-database-url',DATA+'/.c3po-role-executor-20260908-r2',
           DATA+'/.c3po-role-executor-20260908-r2/secret',DATA+'/.c3po-role-executor-20260908-r2/secret/password')
def open_root(name):return None
def device(path):return hostemu.DATA_DEVICE if path.startswith(DATA+'/') else hostemu.ROOT_DEVICE
CHAINS=('days','source_root','secrets','tools','claims')
CANARY='never-emit-provider-token-canary'
RUNNER=b'"""synthetic stand-in of k9_runner.py: never executed by these tests"""\n'
RELEASE=f.canonical({'schema':'R2D2_V2_RELEASE_V3','mode':'CERTIFIED','epoch':EPOCH,'synthetic':True})
POLICY=f.canonical({'schema':'R2D2_V2_LIVE_POLICY_V1','mode':'LIVE','epoch':EPOCH,'valid_from':'2026-10-02T00:00:00+00:00','valid_until':'2026-10-10T00:00:00+00:00'})
POLICY_DIRECTORY=DATA+'/r2d2-v2-live/2026-10-05'
RELEASE_DIRECTORY=DATA+'/r2d2-v2-release-20261005'
DATA_TARGET='/app/day-d-data'
REQUEST_OF_THE_LAUNCH='5e'*32
STEP_PLAN='9a'*32

def sha(raw):return hashlib.sha256(raw).hexdigest()
def attempt_key(epoch,day,phase,operation):
    """actb03_lib.attempt_key, written out again."""
    return sha(json.dumps([epoch,day,phase,operation],separators=(',',':'),ensure_ascii=True).encode('ascii'))

READ={'readiness_probe':('causal_list','PROBE',None),'readiness_recheck':('causal_list','PROBE',None),
      'collect_result':('causal_list','RESULT','collect_launch'),'commit_result':('causal_list','RESULT','commit_launch'),
      'publish_result':('causal_list','RESULT','publish_launch'),'components_result':('components','RESULT','components_launch'),
      'sources_result':('sources','RESULT','sources_launch'),'acquire_result':('risk','RESULT','acquire_launch'),
      'execute_result':('risk','RESULT','execute_launch'),'capture_result':('capture','RESULT','capture_launch'),
      'policy_read':('policy_readonly','POLICY',None)}
# G18 of K9_INTERFACE_NOTE.md section 5.3 and 5.5 for D=2026-10-06: (first instant of the window, run_not_after of the launch)
GRID={'readiness_probe':('2026-10-05T21:26:00+00:00',None),'readiness_recheck':('2026-10-05T22:26:00+00:00',None),
      'collect_result':('2026-10-05T21:50:00+00:00','2026-10-05T21:49:59+00:00'),'commit_result':('2026-10-05T22:08:00+00:00','2026-10-05T22:07:59+00:00'),
      'publish_result':('2026-10-05T22:42:00+00:00','2026-10-05T22:41:59+00:00'),'components_result':('2026-10-06T00:46:00+00:00','2026-10-06T00:45:59+00:00'),
      'sources_result':('2026-10-06T02:26:00+00:00','2026-10-06T02:08:59+00:00'),'acquire_result':('2026-10-06T03:47:00+00:00','2026-10-06T03:46:59+00:00'),
      'execute_result':('2026-10-06T04:26:00+00:00','2026-10-06T04:15:59+00:00'),'capture_result':('2026-10-06T14:26:00+00:00','2026-10-06T14:03:00+00:00'),
      'policy_read':('2026-10-06T12:26:00+00:00',None)}
TREE_MOMENT='2026-10-05T20:40:00+00:00'
from datetime import datetime,timedelta
def at(text):return datetime.fromisoformat(text)

# ---------------------------------------------------------------- the emulated engine, extended by subclassing
STATE9=dict(hostemu.STATE,OOMKilled=('scalar','OOMKilled'))
CONTAINER9=dict(hostemu.CONTAINER,State=('ptr','State',STATE9))
FLAGS9=('--rm','-i','--init','--read-only')
VALUES9=('--pull','--user','--network','--cap-drop','--security-opt','--mount','--name','--env-file','--env','--memory','--pids-limit')

class K9RunCall(hostemu.RunCall):
    """One attached `docker run` with the options of the probe's prefix as well."""
    def __init__(self,docker,arguments,stdin,environment):
        self.docker,self.stdin,self.environment=docker,stdin,dict(environment or {})
        self.flags=[];self.options={};self.mounts=[];index=0
        while index<len(arguments) and arguments[index].startswith('-'):
            word=arguments[index]
            if word in FLAGS9:self.flags.append(word);index+=1
            elif word in VALUES9:
                value=arguments[index+1];index+=2
                if word=='--mount':self.mounts.append(hostemu.parse_mount(value))
                else:self.options.setdefault(word,[]).append(value)
            else:raise AssertionError('docker run option outside the emulated set: %r'%word)
        assert index<len(arguments),'docker run without an image'
        self.image=arguments[index];self.command=list(arguments[index+1:]);self.name=(self.options.get('--name') or [None])[0]
        self.network=(self.options.get('--network') or ['bridge'])[0];self.read_only_root='--read-only' in self.flags
        self.container_environment={}

def parse_env_file(raw):
    """What the docker CLI makes of an env file: NAME=VALUE lines, comments and blank lines skipped."""
    out={}
    for line in raw.decode().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        name,_,value=line.partition('=');out[name]=value
    return out

class K9Docker(hostemu.FakeDocker):
    def run(self,args,stdin=None,environment=None):
        if args[:3]==['container','inspect','--format'] and len(args)==5 and 'OOMKilled' in args[3]:
            self.environments.append(dict(environment or {}))
            if self.inspect_returncode:return self.inspect_returncode,b''
            item=self.container(args[4])
            return (1,b'') if item is None else self.render(args[3],CONTAINER9,item,True)
        if args[:1]==['run'] and '--env-file' in args:
            self.environments.append(dict(environment or {}))
            call=K9RunCall(self,args[1:],stdin,environment);self.runs.append(call)
            assert '--rm' in call.flags and call.options.get('--pull')==['never'],'this family never runs a container that stays or pulls'
            if self.find(call.image) is None or self.find(call.image)['Id']!=call.image:return 125,b''
            for path in call.options.get('--env-file',[]):
                node=self.host.tree.get(path)
                if node is None or node.kind!='file':return 125,b''          # the CLI cannot read its env file
                call.container_environment.update(parse_env_file(bytes(node.content)))
            for word in call.options.get('--env',[]):
                name,_,value=word.partition('=');call.container_environment[name]=value
            if call.name is not None and self.container(call.name) is not None:return 125,b''
            assert self.on_run is not None,'the test gave no behaviour for the container (docker.on_run)'
            code,out=self.on_run(call);assert type(code) is int and type(out) is bytes
            return code,out
        return hostemu.FakeDocker.run(self,args,stdin,environment)


# ---------------------------------------------------------------- the stand-in for the application package
FAKE={'__init__.py':'',
'_knobs.py':'''import json,os
def knobs():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'knobs.json')) as stream:return json.load(stream)
    except OSError:return {}
''',
'config.py':'''import os
from ._knobs import knobs
class Settings:
    eodhd_base_url='https://provider.invalid'
    def __init__(self):self.eodhd_api_token=os.environ.get('C3PO_EODHD_API_TOKEN','')
def get_settings():
    if knobs().get('settings_error'):raise RuntimeError('a message that is not a code: /some/path '+os.environ.get('C3PO_EODHD_API_TOKEN',''))
    return Settings()
''',
'r2d2_v2_earnings_package.py':'''from ._knobs import knobs
def implementation_package_sha():return knobs().get('package','%s')
'''%PACKAGE,
'r2d2_v2_producer_daily.py':'''import hashlib,json,time
from dataclasses import dataclass
from datetime import date,datetime,timedelta,timezone
from ._knobs import knobs
if knobs().get('import_error'):raise ImportError('the producer cannot be imported')
class ProducerError(RuntimeError):
    """Controlled message only."""
DAILY_ELIGIBLE_TYPES=("COMMON_STOCK","COMMON_STOCK_ADR")
TYPE_MAP={"Common Stock":"COMMON_STOCK","ETF":"ETF"}
@dataclass(frozen=True)
class Response:
    payload:bytes
    received_at:datetime
    url_path:str
    @property
    def sha256(self):return hashlib.sha256(self.payload).hexdigest()
    def json(self):
        try:return json.loads(self.payload.decode("utf-8"))
        except (UnicodeDecodeError,ValueError) as exc:raise ProducerError("PROVIDER_JSON_INVALID:"+self.url_path) from exc
class EodhdFetcher:
    """The packaged fetcher's interface; the stand-in refuses settings other than the probe's and answers from the knobs."""
    def __init__(self,base_url,token,*,timeout=60.0,retries=2,sleep=time.sleep):
        if not token.strip():raise ProducerError("PROVIDER_TOKEN_MISSING")
        if token!=knobs().get('token',token):raise ProducerError("TOKEN_NOT_THE_ENV_FILE_ONE")
        if timeout!=15.0 or retries!=0:raise ProducerError("FETCHER_SETTINGS_NOT_THE_PROBE_ONES")
        self.calls=0
    def __call__(self,path,params):
        self.calls+=1
        if knobs().get('fail_path')==path:raise ProducerError("PROVIDER_REQUEST_FAILED:"+path+":ConnectTimeout")
        if knobs().get('hang_path')==path:time.sleep(120)
        if path=="/api/exchange-symbol-list/US" and params=={}:body=knobs()['registry']
        elif path=="/api/eod-bulk-last-day/US" and set(params)=={"date"}:
            if params["date"]!=knobs().get('expect_date',params["date"]):raise ProducerError("BULK_DATE_NOT_THE_PREVIOUS_SESSION")
            body=knobs()['bulk']
        else:raise ProducerError("UNEXPECTED_CALL")
        raw=body.encode() if isinstance(body,str) else json.dumps(body).encode()
        return Response(raw,datetime.now(timezone.utc)+timedelta(seconds=self.calls),path)
def previous_session(day):
    value=day-timedelta(days=1)
    while value.weekday()>=5:value-=timedelta(days=1)
    return value
def session_close(day):return datetime(day.year,day.month,day.day,20,0,tzinfo=timezone.utc)
def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()
def build_registry(response,*,previous_close):
    rows=response.json()
    if not isinstance(rows,list) or not rows:raise ProducerError("REGISTRY_EMPTY")
    if response.received_at<=previous_close:raise ProducerError("REGISTRY_CAPTURED_BEFORE_CLOSE")
    instruments=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get("Exchange") not in ("NYSE","NASDAQ"):continue
        code=row.get("Code")
        if not isinstance(code,str) or code in seen:continue
        seen.add(code);instruments.append({"symbol":code,"market":row["Exchange"],"security_type":TYPE_MAP.get(row.get("Type"),"OTHER"),"classification_verified":True})
    instruments.sort(key=lambda item:item["symbol"])
    return {"instruments":instruments},{"counts":{"duplicates":0}}
def _distinct(rows):
    unique={}
    for row in rows:unique.setdefault(canonical(row),row)
    return list(unique.values())
def _bar(item,session,received_at):
    values=[item.get(key) for key in ("open","high","low","close","volume")]
    if any(not isinstance(value,(int,float)) or isinstance(value,bool) for value in values):return None
    return {"session_date":session.isoformat()}
'''}

_ROOT=Path(tempfile.mkdtemp(prefix='k9r-fake-app-'))
atexit.register(lambda:shutil.rmtree(str(_ROOT),ignore_errors=True))
def fake_tree(**knobs):
    raw=json.dumps(knobs,sort_keys=True).encode();root=_ROOT/hashlib.sha256(raw).hexdigest()[:16]
    if not root.is_dir():
        staging=Path(tempfile.mkdtemp(dir=str(_ROOT)));(staging/'app').mkdir()
        for name,body in FAKE.items():(staging/'app'/name).write_text(body)
        (staging/'app'/'knobs.json').write_bytes(raw)
        try:os.rename(str(staging),str(root))
        except OSError:shutil.rmtree(str(staging),ignore_errors=True)
    return str(root)

def provider_rows(eligible=4000,present=3840,conflicts=0,day='2026-10-05',other=5,stale=0,unusable=0):
    """(registry rows, bulk rows): eligible common stocks on NYSE, ETFs that are not eligible, and bulk rows for the
    first present of the eligible names (the first conflicts with two different rows; the last unusable have no volume),
    and stale rows of another date for the names that are not present."""
    names=['S%03d'%index for index in range(eligible)]
    registry=[{'Code':name,'Exchange':'NYSE','Type':'Common Stock'} for name in names]+[{'Code':'E%02d'%index,'Exchange':'NASDAQ','Type':'ETF'} for index in range(other)]
    bulk=[]
    for index,name in enumerate(names[:present]):
        bulk.append({'code':name,'date':day,'open':10,'high':11,'low':9,'close':10.5,'volume':1000 if index<present-unusable else None})
        if index<conflicts:bulk.append({'code':name,'date':day,'open':12,'high':13,'low':11,'close':12.5,'volume':1})
    bulk.append({'code':'E00','date':day,'open':1,'high':1,'low':1,'close':1,'volume':1})
    for name in names[present:present+stale]:bulk.append({'code':name,'date':'2026-10-02','open':1,'high':1,'low':1,'close':1,'volume':1})
    return registry,bulk

SHIM='''import sys,datetime as _k9_dt
sys.path.append(%r)
_k9_now=%r
class _K9Fixed(_k9_dt.datetime):
    @classmethod
    def now(cls,tz=None):
        value=cls.fromisoformat(_k9_now);return value if tz is None else value.astimezone(tz)
_k9_dt.datetime=_K9Fixed
'''
_CACHE={}
class ProbeContainer:
    """docker.on_run for the probe: runs the exact standard input with a real interpreter, as the container would."""
    def __init__(self,tree=None,now='2026-10-05T21:26:30+00:00',python=None):
        if tree is None:
            registry,bulk=provider_rows();tree=fake_tree(registry=registry,bulk=bulk,token=CANARY,expect_date='2026-10-05')
        self.tree,self.now,self.python=tree,now,python or sys.executable;self.calls=[];self.stderr=[]
    def __call__(self,call):
        assert call.command[:5]==['timeout','-s','KILL','36','python'] and call.command[5:8]==['-I','-B','-'] and len(call.command)==10
        assert call.network=='bridge' and call.read_only_root and call.mounts==[] and call.stdin and not os.path.exists('/app')
        self.calls.append(call)
        environment={'PATH':'/usr/bin:/bin'};environment.update(call.container_environment)
        key=(self.tree,self.now,self.python,call.stdin,tuple(call.command),tuple(sorted(environment.items())))
        if key not in _CACHE:
            shim=(SHIM%(self.tree,self.now)).encode()
            done=subprocess.run([self.python]+call.command[5:],input=shim+call.stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment,timeout=120)
            _CACHE[key]=(done.returncode if done.returncode>=0 else 128-done.returncode,done.stdout,done.stderr)
        code,out,err=_CACHE[key];self.stderr.append(err);return code,out


# ---------------------------------------------------------------- the host: the K9 tree as E0 and K3-K9 leave it
def world(k):
    host=f.world(k);host.docker.__class__=K9Docker;tree=host.tree;dev=hostemu.ROOT_DEVICE
    tree.add('/var/lib/c3po',mode=0o755)                      # the parent E0 does not create (N-8: never presumed)
    for path in (K9_ROOT,PLACEMENT['days'],PLACEMENT['tools'],PLACEMENT['claims'],PLACEMENT['secrets'],PLACEMENT['emitter'],SOURCE_ROOT):
        tree.add(path,mode=0o700,dev=device(path))
    tree.add(PLACEMENT['provider_env_file'],kind='file',mode=0o600,dev=dev,
             content=('C3PO_EODHD_API_TOKEN=%s\nC3PO_FINNHUB_API_TOKEN=%s-finnhub\nC3PO_FMP_API_TOKEN=%s-fmp\n'%(CANARY,CANARY,CANARY)).encode())
    tree.add(PLACEMENT['risk_db_env_file'],kind='file',mode=0o600,dev=dev,content=('C3PO_R2D2_RISK_DATABASE_URL=postgresql://reader:%s@db:5432/c3po\n'%CANARY).encode())
    tree.add(PLACEMENT['emitter_password'],kind='file',mode=0o600,dev=dev,content=(CANARY+'-emitter\n').encode())
    tree.add(PLACEMENT['tools']+'/k9_runner-'+sha(RUNNER)+'.py',kind='file',mode=0o600,dev=dev,content=RUNNER)
    for path,mode in ((SEPTEMBER[0],0o700),(SEPTEMBER[2],0o700),(SEPTEMBER[3],0o700)):tree.add(path,mode=mode,dev=hostemu.DATA_DEVICE)
    tree.add(SEPTEMBER[1],kind='file',mode=0o600,dev=hostemu.DATA_DEVICE,content=('postgresql://reader:%s@db/c3po\n'%CANARY).encode())
    tree.add(SEPTEMBER[4],kind='file',mode=0o600,dev=hostemu.DATA_DEVICE,content=(CANARY+'-september-password\n').encode())
    host.docker.on_run=ProbeContainer()
    return host

def constants(**changes):
    values={'k9_interface_note_sha256':NOTE,'act_b_sha256':'a1'*32,'package_sha256':PACKAGE,'code_revision':REVISION,'release_sha256':sha(RELEASE),
            'policy_sha256':sha(POLICY),'image_id':hostemu.BACKEND,'runner_sha256':sha(RUNNER),'probe_snippet_sha256':f.load(DIRECTORY).m.K9_PROBE_SNIPPET_SHA256,
            'networks':{'PROVIDER':'bridge','DATABASE':'c3po_c3po_internal','DATABASE_AND_PROVIDER':'c3po_db_loopback'},'step_table_sha256':'b2'*32,
            'risk_source_pins_sha256':'c3'*32,'risk_limits':{'max_symbols':550,'max_total_requests':2200,'max_body_bytes':16777216,
            'max_total_bytes':1073741824,'max_elapsed_seconds':3600},'readiness_rule':{'numerator':95,'denominator':100,'minimum_eligible':4000},'disk_floor_bytes':214748364800,
            'placement':dict(PLACEMENT)}
    values.update(changes);return values

def chains(host):
    return {name:{'path':PLACEMENT[name],'rows':hostemu.rows(host,PLACEMENT[name]),'open_root':open_root(name)} for name in CHAINS}

def fields(host,operation,*,day=DAY,slot='PRIMARY',run_not_after=None,constant=None,policy_read=None):
    phase,mode,_=READ[operation]
    plan={'mode':mode,'epoch':EPOCH,'day':day,'k9_phase':phase,'k9_operation':operation,'slot':slot,'attempt_key':attempt_key(EPOCH,day,phase,operation),
          'run_not_after':run_not_after if run_not_after is not None else GRID[operation][1],'constants':constant or constants(),'parent_rows':chains(host),
          'evidence_boot_id_sha256':f.BOOT_SHA,'policy_read':None}
    if mode=='POLICY':
        plan['policy_read']=policy_read or {'policy':{'directory':{'path':POLICY_DIRECTORY,'rows':hostemu.rows(host,POLICY_DIRECTORY),'open_root':DATA},'file_name':'policy.json'},
                                            'release':{'directory':{'path':RELEASE_DIRECTORY,'rows':hostemu.rows(host,RELEASE_DIRECTORY),'open_root':DATA},
                                                       'file_name':'release.CERTIFIED.json'},
                                            'worker':{'container':hostemu.WORKER,'data_source':DATA,'data_target':DATA_TARGET}}
    return plan

def tree_fields(constant=None):
    return {'mode':'TREE','epoch':EPOCH,'day':None,'k9_phase':None,'k9_operation':None,'slot':None,'attempt_key':None,'run_not_after':None,
            'constants':constant or constants(),'parent_rows':None,'evidence_boot_id_sha256':None,'policy_read':None}


# ---------------------------------------------------------------- what a launch and its step leave for RESULT
def day_path(*parts):return '/'.join((PLACEMENT['days'],DAY)+parts)
OUTPUTS={'collect_launch':{'day/inputs/registry.json':b'{"registry":"synthetic"}','day/inputs/daily_contract.json':b'{"daily":"synthetic"}'*50,
                           'day/inputs/registry.receipt.json':b'{"r":1}','day/inputs/daily_contract.receipt.json':b'{"r":2}'},
         'commit_launch':{'day/causal/commitment.private.json':b'{"commitment":"synthetic"}'},
         'publish_launch':{'source/causal_list/R2D2-V2-SHADOW-2026-10-05/2026-10-06.json':b'{"envelope":"synthetic"}',
                           'day/relay/R2D2-V2-SHADOW-2026-10-05/2026-10-06.json':b'{"relay":"synthetic"}','day/control/symbols.txt':b'S000\nS001\n'},
         'components_launch':{'source/components/2026-10-06/registry.json':b'{"registry":"synthetic"}','source/components/2026-10-06/earnings.json':b'{"earnings":1}'},
         'sources_launch':{'day/risk/plan/replay.private.json':b'{"replay":1}','day/risk/plan/risk-input-names.private.json':b'{"names":1}'},
         'capture_launch':{'source/snapshot.json':b'{"snapshot":1}','source/tape/2026-10-06.us-quote.ndjson':b'{"q":1}\n'}}
AGGREGATES={'components_launch':{'source/components/2026-10-06/daily_61':[b'{"c":%d}'%index for index in range(3)]}}
COUNTS={'collect_launch':{'registry_symbols':105,'complete_bars':2000,'bar_conflicts':0,'logical_fetch_calls':41},
        'components_launch':{'daily_61':{'symbol_count':3,'incomplete_count':0},'logical_fetch_calls':12}}

def add_file(host,path,content,mode=0o600):host.tree.add(path,kind='file',mode=mode,dev=device(path),content=content)
def add_dir(host,path,mode=0o700):
    if host.tree.get(path) is None:host.tree.add(path,mode=mode,dev=device(path))
def put(host,key,content):
    root,_,rest=key.partition('/');path=(day_path() if root=='day' else SOURCE_ROOT)+'/'+rest
    parts=path.split('/')
    for index in range(len(K9_ROOT.split('/'))+1 if root=='day' else len(SOURCE_ROOT.split('/'))+1,len(parts)):add_dir(host,'/'.join(parts[:index]))
    add_file(host,path,content)

def launched(host,launch,*,exit_code=0,state='exited',oom=False,labels=None):
    phase=[row[0] for row in READ.values() if row[2]==launch][0]
    item=hostemu.container('c3po-k9-20261006-'+launch,hostemu.BACKEND,hostemu.BACKEND,[],running=state=='running')
    item['State'].update(Status=state,Running=state=='running',ExitCode=exit_code,OOMKilled=oom,StartedAt='2026-10-05T21:29:11.500000000Z',
                         FinishedAt='2026-10-06T14:20:00.123456789Z')
    item['Config']['Labels']=labels if labels is not None else {'c3po.k9.attempt_key':attempt_key(EPOCH,DAY,phase,launch),'c3po.k9.request_sha256':REQUEST_OF_THE_LAUNCH}
    host.docker.containers.append(item);return item

def record(host,launch,container,**changes):
    phase=[row[0] for row in READ.values() if row[2]==launch][0]
    body={'schema':'K9_LAUNCH_RECORD_V1','epoch':EPOCH,'day':DAY,'operation':launch,'slot':'PRIMARY','attempt_key':attempt_key(EPOCH,DAY,phase,launch),
          'request_sha256':REQUEST_OF_THE_LAUNCH,'step_plan_sha256':STEP_PLAN,'container_id':container['Id'],'container_name':'c3po-k9-20261006-'+launch,
          'created_at':'2026-10-05T21:29:10+00:00','started_at':'2026-10-05T21:29:11+00:00','timeout_seconds':1235}
    body.update(changes);add_dir(host,day_path());add_dir(host,day_path('launches'))
    add_file(host,day_path('launches',launch+'.json'),f.canonical(body));return body

def step(host,launch,*,started=True,receipt=True,failed=None,changes=None,started_changes=None):
    """The K9 runner's files: the start marker, then exactly one of RECEIPT (COMPLETE) or FAILED (failed=status)."""
    phase=[row[0] for row in READ.values() if row[2]==launch][0];add_dir(host,day_path('receipts'))
    identity={'epoch':EPOCH,'day':DAY,'phase':phase,'operation':launch,'attempt_key':attempt_key(EPOCH,DAY,phase,launch),'step_plan_sha256':STEP_PLAN}
    if started:
        marker=dict(identity,schema='K9_STEP_STARTED_V1',started_at='2026-10-05T21:29:12+00:00');marker.update(started_changes or {})
        add_file(host,day_path('receipts',launch+'.STARTED.json'),f.canonical(marker))
    outputs={};aggregates={}
    for key,content in OUTPUTS.get(launch,{}).items():put(host,key,content);outputs[key]=sha(content)
    for key,files in AGGREGATES.get(launch,{}).items():
        for index,content in enumerate(files):put(host,key+'/F%03d.json'%index,content)
        aggregates[key]={'files':len(files),'sha256':sha(f.canonical(sorted(sha(item) for item in files)))}
    body=dict(identity,schema='K9_STEP_RECEIPT_V1',status='COMPLETE',code=None,started_at='2026-10-05T21:29:12+00:00',completed_at='2026-10-05T21:40:00+00:00',
              package_sha256=PACKAGE,build_sha=REVISION,outputs=outputs,aggregates=aggregates,counts=COUNTS.get(launch,{'logical_fetch_calls':1}))
    if receipt:
        complete=dict(body);complete.update(changes or {});add_file(host,day_path('receipts',launch+'.RECEIPT.json'),f.canonical(complete))
    if failed:
        failure=dict(body,status=failed,code='STEP_'+failed,outputs={},aggregates={});failure.update(changes or {})
        add_file(host,day_path('receipts',launch+'.FAILED.json'),f.canonical(failure))
    return body

HOST_PLAN=b'{"schema":"R2D2_V2_RISK_HOST_PLAN_V1","synthetic":true}'
HOST_GO=b'{"schema":"R2D2_V2_RISK_HOST_GO_V1","synthetic":true}'
def spool(*parts):return day_path('risk','spool',sha(HOST_PLAN),*parts)
def packaged(host,launch,*,started=True,receipt=True,failed=None,changes=None,namespace='R2D2-V2-DIAG-R4-2026-10-06'):
    phase={'acquire_launch':'acquire','execute_launch':'execute'}[launch]
    for path in (day_path('risk'),day_path('risk','plan'),day_path('risk','spool'),spool()):add_dir(host,path)
    if host.tree.get(day_path('risk','plan','HOST_PLAN.json')) is None:
        add_file(host,day_path('risk','plan','HOST_PLAN.json'),HOST_PLAN);add_file(host,day_path('risk','plan','GO.json'),HOST_GO)
    bound={'phase':phase,'manifest_sha256':sha(HOST_PLAN),'go_sha256':sha(HOST_GO)}
    prior={'acquire':'preflight','execute':'acquire'}[phase]
    if host.tree.get(spool(prior+'.RECEIPT.json')) is None:add_file(host,spool(prior+'.RECEIPT.json'),b'{"prior":"%s"}'%prior.encode())
    previous=sha(bytes(host.tree.get(spool(prior+'.RECEIPT.json')).content))
    if started:add_file(host,spool(phase+'.STARTED.json'),f.canonical(dict(bound,started_at='2026-10-06T02:41:10+00:00')))
    if phase=='acquire':
        acquired=b'{"acquired":"synthetic"}';add_dir(host,spool('acquired'));add_file(host,spool('acquired','acquired.json'),acquired)
        outputs={'batch_manifest_sha256':'d4'*32,'acquired_manifest':{'path':'acquired.json','sha256':sha(acquired)},'counts':{'symbols':3,'http_attempts':9}}
    else:
        assessment,manifest,risk=b'{"assessment":1}',b'{"manifest":1}',b'{"risk":1}'
        for name in ('assessment','risk-output'):add_dir(host,spool(name))
        add_file(host,spool('assessment','manifest.json'),assessment);add_file(host,spool('risk-output','MANIFEST.json'),manifest);add_file(host,spool('risk-output','risk.json'),risk)
        outputs={'assessment_manifest':{'path':'manifest.json','sha256':sha(assessment)},'output_manifest_sha256':sha(manifest),'risk_sha256':sha(risk),
                 'counts':{'READY':2,'COMPLETED_NULL':1},'symbol_count':3}
    body=dict(bound,schema='R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1',status='COMPLETE',namespace=namespace,session_date=DAY,started_at='2026-10-06T02:41:10+00:00',
              completed_at='2026-10-06T03:10:00+00:00',previous_receipt_sha256=previous,outputs=outputs,operation_activation=False,certification_granted=False)
    if receipt:
        complete=dict(body);complete.update(changes or {});add_file(host,spool(phase+'.RECEIPT.json'),f.canonical(complete))
    if failed:add_file(host,spool(phase+'.FAILED.json'),f.canonical(dict(bound,schema='R2D2_V2_RISK_HOST_FAILED_V1',status=failed,code='PHASE_WINDOW_EXPIRED')))
    return body

def result_world(k,operation,*,exit_code=0,state='exited',with_step=True,**step_options):
    host=world(k);launch=READ[operation][2];container=launched(host,launch,exit_code=exit_code,state=state);record(host,launch,container)
    if with_step:(packaged if launch in ('acquire_launch','execute_launch') else step)(host,launch,**step_options)
    return host

def policy_world(k):
    host=world(k)
    for path in (DATA+'/r2d2-v2-live',POLICY_DIRECTORY,RELEASE_DIRECTORY):host.tree.add(path,mode=0o700,dev=hostemu.DATA_DEVICE)
    add_file(host,POLICY_DIRECTORY+'/policy.json',POLICY);add_file(host,RELEASE_DIRECTORY+'/release.CERTIFIED.json',RELEASE)
    worker=host.docker.container(hostemu.WORKER)
    worker['Config']['Env']+=['C3PO_R2D2_V2_LIVE_POLICY_FILE=%s/r2d2-v2-live/2026-10-05/policy.json'%DATA_TARGET,'C3PO_R2D2_V2_LIVE_POLICY_SHA='+sha(POLICY),
                              'C3PO_R2D2_V2_SHADOW_RELEASE_FILE=%s/r2d2-v2-release-20261005/release.CERTIFIED.json'%DATA_TARGET,'C3PO_R2D2_V2_SHADOW_RELEASE_SHA='+sha(RELEASE)]
    return host

def case(operation='collect_result',now=None,**options):
    """(docs, host): a bound fixture of one operation that completes on a fresh emulated host at its grid instant."""
    k=f.load(DIRECTORY)
    mode=READ[operation][1] if operation!='TREE' else 'TREE'
    if mode=='TREE':host=world(k);plan=tree_fields(options.get('constant'));moment=TREE_MOMENT
    else:
        host=policy_world(k) if mode=='POLICY' else result_world(k,operation) if mode=='RESULT' else world(k)
        plan=fields(host,operation,**{key:value for key,value in options.items() if key in ('constant','slot','run_not_after','policy_read')});moment=GRID[operation][0]
    return f.Docs(k,plan,now=now or at(moment)),host

def state_of(host):
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)
