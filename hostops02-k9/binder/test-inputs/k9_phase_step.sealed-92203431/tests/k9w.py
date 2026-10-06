"""Fixtures of the K9W tests: request plans built from the emulated host as a binder would copy them from the TREE
receipt (K9R), the K9 tree as K4-E0 and K3-K9 would leave it, what the earlier steps of the eve leave on the host (step
plans, launch records, the runner's and the packaged executor's receipts, exited containers with their labels), and
the emulated engine extended for docker create / start / rm and for the attached runs of bind, preflight and stage.

hostemu is extended here by subclassing, never edited. Everything is synthetic: no value, identity or byte of the real
host, release, runner or provider."""
import copy
import hashlib
import json
from datetime import datetime,timedelta
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
EPOCH='R2D2-V2-SHADOW-2026-10-05'
DAY='2026-10-06'
YMD='20261006'
REVISION=hostemu.REVISION
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'
NOTE='ab5159bea34b3239379e87c2500d383f0777cc6186618435ba0ea9f61e3d596c'
DATA=hostemu.DATA
K9_ROOT='/var/lib/c3po/r2d2-v2-k9-20261005'
SOURCE_ROOT='/var/lib/c3po/r2d2-v2-source-20261005'          # decision 6: off the data volume, beside the K9 tree
PLACEMENT={'k9_root':K9_ROOT,'source_root':SOURCE_ROOT,'days':K9_ROOT+'/days','tools':K9_ROOT+'/tools','claims':K9_ROOT+'/claims',
           'secrets':K9_ROOT+'/secrets','emitter':K9_ROOT+'/secrets/emitter','provider_env_file':K9_ROOT+'/secrets/provider.env',
           'risk_db_env_file':K9_ROOT+'/secrets/risk-db.env','emitter_password':K9_ROOT+'/secrets/emitter/password','source_open_root':None,'k9_open_root':None,
           'decision':'d30f7f9048af4a39cf4fa7d9f49292ad387a2d41f33bad39816e83d3d1fc2c53','decision_6':'#429 comment 5985748037','september_open_root':DATA}
CHAINS=('days','source_root','secrets','tools','claims')
CANARY='never-emit-provider-token-canary'
RUNNER=b'"""synthetic stand-in of k9_runner.py: never executed by these tests"""\n'
RUNNER_SHA256='563a4797ab2a7ef4c02a1c1937061a2644420b69bdcc2dca842cd1efd7fb7690'      # the compiled runner hash; K9W only lstats the file of that name, TREE hashes it
NETWORKS={'PROVIDER':'bridge','DATABASE':'c3po_c3po_internal','DATABASE_AND_PROVIDER':'c3po_db_loopback'}
LIMITS={'max_symbols':550,'max_total_requests':2200,'max_body_bytes':16777216,'max_total_bytes':1073741824,'max_elapsed_seconds':3600}
PINS='c3'*32
TREE_RECEIPT='7e'*32

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def attempt_key(epoch,day,phase,operation):
    """actb03_lib.attempt_key, written out again."""
    return sha(json.dumps([epoch,day,phase,operation],separators=(',',':'),ensure_ascii=True).encode('ascii'))
def open_root(name):return None
def device(path):return hostemu.DATA_DEVICE if path.startswith(DATA+'/') else hostemu.ROOT_DEVICE
def at(text):return datetime.fromisoformat(text)

# operation: (phase, mode)
WRITE={'collect_launch':('causal_list','LAUNCH'),'commit_launch':('causal_list','LAUNCH'),'publish_launch':('causal_list','LAUNCH'),
       'components_launch':('components','LAUNCH'),'sources_launch':('sources','LAUNCH'),'bind':('risk','ATTACHED'),'preflight':('risk','ATTACHED'),
       'acquire_launch':('risk','LAUNCH'),'execute_launch':('risk','LAUNCH'),'stage':('risk','ATTACHED'),'capture_launch':('capture','LAUNCH'),
       'capture_cleanup':('capture','CLEANUP')}
CEILING={'collect_launch':900,'commit_launch':600,'publish_launch':600,'components_launch':2400,'sources_launch':4500,'acquire_launch':3600,
         'execute_launch':1200,'capture_launch':780}
# G18 of K9_INTERFACE_NOTE.md 5.3 and 5.5 for D=2026-10-06: the first instant of each write window (UTC)
GRID={'collect_launch':'2026-10-05T21:29:00+00:00','commit_launch':'2026-10-05T21:52:00+00:00','publish_launch':'2026-10-05T22:26:00+00:00',
      'components_launch':'2026-10-06T00:00:00+00:00','sources_launch':'2026-10-06T00:48:00+00:00','bind':'2026-10-06T02:29:00+00:00',
      'preflight':'2026-10-06T02:38:00+00:00','acquire_launch':'2026-10-06T02:41:00+00:00','execute_launch':'2026-10-06T03:50:00+00:00',
      'stage':'2026-10-06T04:29:00+00:00','capture_launch':'2026-10-06T13:50:00+00:00','capture_cleanup':'2026-10-06T14:29:00+00:00'}
MINUTES=5
CUTOFF='2026-10-06T02:26:00+00:00'
WINDOWS={'preflight':{'not_before':'2026-10-06T02:38:00+00:00','not_after':'2026-10-06T02:44:59+00:00'},
         'acquire':{'not_before':'2026-10-06T02:41:00+00:00','not_after':'2026-10-06T03:46:59+00:00'},
         'execute':{'not_before':'2026-10-06T03:50:00+00:00','not_after':'2026-10-06T04:15:59+00:00'}}
def owner_order(day=DAY,cutoff=CUTOFF):
    return canonical({'schema':'R2D2_V2_RISK_HOST_ORDER_V1','actions':['READ_PROVIDERS','READ_DATABASE','WRITE_PRIVATE_RISK_ARTIFACTS'],
                      'scope':{'namespace':'R2D2-V2-DIAG-R4-'+day,'session_date':day,'cutoff_at':cutoff,'phases':['preflight','acquire','execute']}})
def bind_member(day=DAY,cutoff=CUTOFF,windows=None):
    raw=owner_order(day,cutoff)
    return {'namespace':'R2D2-V2-DIAG-R4-'+day,'cutoff_at':cutoff,'phase_windows':copy.deepcopy(windows or WINDOWS),'owner_order_text':raw.decode('ascii'),
            'owner_order_sha256':sha(raw)}

# ---------------------------------------------------------------- the emulated engine, extended by subclassing
STATE9=dict(hostemu.STATE,OOMKilled=('scalar','OOMKilled'))
CONTAINER9=dict(hostemu.CONTAINER,State=('ptr','State',STATE9))
CREATE_FLAGS=('--init','--read-only')
CREATE_VALUES=('--pull','--user','--cap-drop','--security-opt','--restart','--name','--label','--network','--env-file','--env','--mount')
RUN_FLAGS=('--rm','-i','--init','--read-only')
RUN_VALUES=('--pull','--user','--network','--cap-drop','--security-opt','--mount','--name','--label','--env-file','--env')

def parse_env_file(raw):
    out={}
    for line in raw.decode().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        name,_,value=line.partition('=');out[name]=value
    return out

class Call(hostemu.RunCall):
    """One docker create or attached run, parsed as the CLI parses it (options, the image, the command)."""
    def __init__(self,docker,arguments,stdin,environment,flags,values):
        self.docker,self.stdin,self.environment=docker,stdin,dict(environment or {})
        self.flags=[];self.options={};self.mounts=[];index=0
        while index<len(arguments) and arguments[index].startswith('-'):
            word=arguments[index]
            if word in flags:self.flags.append(word);index+=1
            elif word in values:
                value=arguments[index+1];index+=2
                if word=='--mount':self.mounts.append(hostemu.parse_mount(value))
                else:self.options.setdefault(word,[]).append(value)
            else:raise AssertionError('docker option outside the emulated set: %r'%word)
        assert index<len(arguments),'docker without an image'
        self.image=arguments[index];self.command=list(arguments[index+1:]);self.name=(self.options.get('--name') or [None])[0]
        self.network=(self.options.get('--network') or ['bridge'])[0];self.read_only_root='--read-only' in self.flags
        self.labels=dict(word.split('=',1) for word in self.options.get('--label',[]))
        self.container_environment={}
    def mkdir(self,path):
        source,mount=self.bound(path)
        assert mount is not None and not mount['read_only']
        parent=self.docker.host.tree.get(source.rsplit('/',1)[0])
        assert parent is not None and parent.kind=='dir'
        self.docker.host.tree.add(source,mode=0o700,dev=parent.dev)

class Docker(hostemu.FakeDocker):
    """+ docker create (no --rm), start, rm of one ID, an attached run with labels and env files, and the inspect format
    of K9R/K9W (State.OOMKilled, the labels). Knobs: create_returncode, start_returncode, rm_returncode, rm_effect,
    on_start(container) (what the started container does at once: e.g. exit), on_run(call) (the attached run),
    create_output (what create prints)."""
    def setup(self):
        self.create_returncode=0;self.start_returncode=0;self.rm_returncode=None;self.rm_effect=True;self.on_start=None;self.create_output=None
        self.created=[];self.started=[];self.removed=[];self.attached=[];self.start_effect=True;self.check_mounts=True
    def check_environment(self,call):
        for path in call.options.get('--env-file',[]):
            node=self.host.tree.get(path)
            if node is None or node.kind!='file':return False
            call.container_environment.update(parse_env_file(bytes(node.content)))
        for word in call.options.get('--env',[]):
            name,_,value=word.partition('=');call.container_environment[name]=value
        return True
    def run(self,args,stdin=None,environment=None):
        if args[:3]==['container','inspect','--format'] and len(args)==5 and 'OOMKilled' in args[3]:
            self.environments.append(dict(environment or {}))
            if self.inspect_returncode:return self.inspect_returncode,b''
            item=self.container(args[4])
            return (1,b'') if item is None else self.render(args[3],CONTAINER9,item,True)
        if args[:1]==['create']:
            self.environments.append(dict(environment or {}))
            call=Call(self,args[1:],stdin,environment,CREATE_FLAGS,CREATE_VALUES)
            assert call.options.get('--pull')==['never'] and call.options.get('--restart')==['no'] and '--rm' not in args
            assert call.options.get('--user')==['0:0'] and call.options.get('--cap-drop')==['ALL'] and call.read_only_root and '--init' in call.flags
            if self.create_returncode:return self.create_returncode,b''
            if self.find(call.image) is None or self.find(call.image)['Id']!=call.image:return 125,b''
            if not self.check_environment(call):return 125,b''
            for mount in call.mounts:
                node=self.host.tree.get(mount['source'])
                if self.check_mounts and (node is None or node.kind!='dir'):return 125,b''
            if call.name is not None and self.container(call.name) is not None:return 125,b''
            item=hostemu.container(call.name,call.image,call.image,[],running=False)
            item['State'].update(Status='created',Running=False,ExitCode=0,OOMKilled=False,StartedAt='0001-01-01T00:00:00Z')
            item['Config']['Labels']=dict(call.labels);item['Mounts']=[{'Type':'bind','Source':mount['source'],'Destination':mount['target'],
                                                                        'RW':not mount['read_only']} for mount in call.mounts]
            self.containers.append(item);self.created.append(call)
            return 0,(self.create_output if self.create_output is not None else (item['Id']+'\n').encode())
        if args[:1]==['start'] and len(args)==2:
            item=self.container(args[1])
            if item is None:return 1,b''
            if self.start_returncode and not getattr(self,'start_failure_after_effect',False):return self.start_returncode,b''
            if self.start_effect:
                item['State'].update(Status='running',Running=True,StartedAt='2026-10-05T21:29:11.000000000Z');self.started.append(item)
                if self.on_start is not None:self.on_start(item)
            if self.start_returncode:return self.start_returncode,b''
            return 0,(args[1]+'\n').encode()
        if args[:1]==['rm'] and len(args)==2:
            item=self.container(args[1])
            if item is None:return 1,b''
            if self.rm_returncode is not None:return self.rm_returncode,b''
            if item['State']['Running']:return 1,b''
            if self.rm_effect:self.containers.remove(item);self.removed.append(args[1])
            return 0,(args[1]+'\n').encode()
        if args[:1]==['run'] and '--label' in args:
            self.environments.append(dict(environment or {}))
            call=Call(self,args[1:],stdin,environment,RUN_FLAGS,RUN_VALUES);self.runs.append(call);self.attached.append(call)
            assert '--rm' in call.flags and call.options.get('--pull')==['never'] and call.network=='none'
            if self.find(call.image) is None or self.find(call.image)['Id']!=call.image:return 125,b''
            if not self.check_environment(call):return 125,b''
            for mount in call.mounts:
                if self.check_mounts and self.host.tree.get(mount['source']) is None:return 125,b''
            if call.name is not None and self.container(call.name) is not None:return 125,b''
            assert self.on_run is not None,'the test gave no behaviour for the container (docker.on_run)'
            code,out=self.on_run(call);assert type(code) is int and type(out) is bytes
            return code,out
        return hostemu.FakeDocker.run(self,args,stdin,environment)


# ---------------------------------------------------------------- the host: the K9 tree as E0 and K3-K9 leave it
def day_path(*parts):return '/'.join((PLACEMENT['days'],DAY)+parts)
def add_file(host,path,content,mode=0o600):
    if host.tree.get(path) is not None:host.tree.remove(path)
    host.tree.add(path,kind='file',mode=mode,dev=device(path),content=content)
def add_dir(host,path,mode=0o700):
    if host.tree.get(path) is None:host.tree.add(path,mode=mode,dev=device(path))
def put(host,key,content):
    root,_,rest=key.partition('/');path=(day_path() if root=='day' else SOURCE_ROOT)+'/'+rest
    parts=path.split('/');first=len(day_path().split('/')) if root=='day' else len(SOURCE_ROOT.split('/'))
    for index in range(first+1,len(parts)):add_dir(host,'/'.join(parts[:index]))
    add_file(host,path,content)

def world(k):
    host=f.world(k);host.docker.__class__=Docker;host.docker.setup();tree=host.tree;dev=hostemu.ROOT_DEVICE
    tree.add('/var/lib/c3po',mode=0o755)
    for path in (K9_ROOT,PLACEMENT['days'],PLACEMENT['tools'],PLACEMENT['claims'],PLACEMENT['secrets'],PLACEMENT['emitter'],SOURCE_ROOT):
        tree.add(path,mode=0o700,dev=device(path))
    tree.add(PLACEMENT['provider_env_file'],kind='file',mode=0o600,dev=dev,
             content=('C3PO_EODHD_API_TOKEN=%s\nC3PO_FINNHUB_API_TOKEN=%s-finnhub\nC3PO_FMP_API_TOKEN=%s-fmp\n'%(CANARY,CANARY,CANARY)).encode())
    tree.add(PLACEMENT['risk_db_env_file'],kind='file',mode=0o600,dev=dev,content=('C3PO_R2D2_RISK_DATABASE_URL=postgresql://reader:%s@db:5432/c3po\n'%CANARY).encode())
    tree.add(PLACEMENT['emitter_password'],kind='file',mode=0o600,dev=dev,content=(CANARY+'-emitter\n').encode())
    tree.add(PLACEMENT['tools']+'/k9_runner-'+RUNNER_SHA256+'.py',kind='file',mode=0o600,dev=dev,content=RUNNER)
    host.docker.on_run=Attached()
    return host

def constants(k=None,**changes):
    k=k or f.load(DIRECTORY)
    values={'k9_interface_note_sha256':NOTE,'act_b_sha256':'a1'*32,'package_sha256':PACKAGE,'code_revision':REVISION,'release_sha256':'d1'*32,
            'policy_sha256':'d2'*32,'image_id':hostemu.BACKEND,'runner_sha256':RUNNER_SHA256,'probe_snippet_sha256':'b4'*32,'networks':dict(NETWORKS),
            'step_table_sha256':k.m.K9W_STEP_TABLE_SHA256,'risk_source_pins_sha256':PINS,'risk_limits':dict(LIMITS),
            'readiness_rule':{'numerator':95,'denominator':100},'disk_floor_bytes':214748364800,'placement':dict(PLACEMENT)}
    values.update(changes);return values

def chains(host):
    return {name:{'path':PLACEMENT[name],'rows':hostemu.rows(host,PLACEMENT[name]),'open_root':open_root(name)} for name in CHAINS}

def window_end(operation,now=None):
    start=now or at(GRID[operation]);return start+timedelta(minutes=MINUTES)

def run_not_after(operation,now=None):
    if WRITE[operation][1]!='LAUNCH':return None
    if operation=='capture_launch':return DAY+'T14:03:00+00:00'
    return (window_end(operation,now)+timedelta(seconds=CEILING[operation])).isoformat()

def fields(host,operation,*,day=DAY,slot='PRIMARY',constant=None,now=None,**overrides):
    phase,mode=WRITE[operation]
    plan={'mode':mode,'epoch':EPOCH,'day':day,'k9_phase':phase,'k9_operation':operation,'slot':slot,'attempt_key':attempt_key(EPOCH,day,phase,operation),
          'run_not_after':run_not_after(operation,now),'constants':constant or constants(),'parent_rows':chains(host),
          'evidence_boot_id_sha256':f.BOOT_SHA,'bind':bind_member() if operation=='bind' else None}
    plan.update(overrides);return plan

EVIDENCE=[{'role':'TREE','operation':'GO_READONLY_HOSTOPS02_K9_PHASE_READ_01','receipt_sha256':TREE_RECEIPT}]


# ---------------------------------------------------------------- what the earlier steps of the eve leave
REQUEST_OF='5e'*32
OUTPUTS={'collect_launch':{'day/inputs/registry.json':b'{"registry":"synthetic"}','day/inputs/daily_contract.json':b'{"daily":"synthetic"}'},
         'commit_launch':{'day/causal/commitment.private.json':b'{"commitment":"synthetic"}'},
         'publish_launch':{'source/causal_list/R2D2-V2-SHADOW-2026-10-05/2026-10-06.json':b'{"envelope":"synthetic"}',
                           'day/relay/R2D2-V2-SHADOW-2026-10-05/2026-10-06.json':b'{"relay":"synthetic"}','day/control/symbols.txt':b'S000\nS001\n'},
         'components_launch':{'source/components/2026-10-06/registry.json':b'{"registry":"synthetic"}'},
         'sources_launch':{'day/risk/plan/replay.private.json':b'{"replay":1}','day/risk/plan/risk-input-names.private.json':b'{"names":1}'},
         'capture_launch':{'source/snapshot.json':b'{"snapshot":1}'}}

def layout(host):
    add_dir(host,day_path())
    for name in ('plans','launches','receipts'):add_dir(host,day_path(name))

def container_of(host,launch,*,state='exited',exit_code=0,oom=False,labels=None,image=None):
    phase=WRITE[launch][0]
    item=hostemu.container('c3po-k9-%s-%s'%(YMD,launch),image or hostemu.BACKEND,hostemu.BACKEND,[],running=state=='running')
    item['State'].update(Status=state,Running=state=='running',ExitCode=exit_code,OOMKilled=oom,FinishedAt='2026-10-05T21:45:10.123456789Z')
    item['Config']['Labels']=labels if labels is not None else {'c3po.k9.attempt_key':attempt_key(EPOCH,DAY,phase,launch),'c3po.k9.request_sha256':REQUEST_OF}
    host.docker.containers.append(item);return item

def launched(host,launch,*,record_changes=None,**container_options):
    """A launch of an earlier step: its step plan, its launch record and its exited container."""
    layout(host);phase=WRITE[launch][0];plan=b'{"synthetic step plan of %s"}'%launch.encode()
    add_file(host,day_path('plans',launch+'.json'),plan)
    item=container_of(host,launch,**container_options)
    body={'schema':'K9_LAUNCH_RECORD_V1','epoch':EPOCH,'day':DAY,'operation':launch,'slot':'PRIMARY','attempt_key':attempt_key(EPOCH,DAY,phase,launch),
          'request_sha256':REQUEST_OF,'step_plan_sha256':sha(plan),'container_id':item['Id'],'container_name':'c3po-k9-%s-%s'%(YMD,launch),
          'created_at':'2026-10-05T21:29:10+00:00','started_at':'2026-10-05T21:29:11+00:00','timeout_seconds':960}
    body.update(record_changes or {});add_file(host,day_path('launches',launch+'.json'),canonical(body));return item

def runner_receipts(host,launch,*,receipt=True,failed=None,started=True,changes=None,plan=True,outputs=None):
    """The K9 runner's files of an earlier step (its plan when it was attached, the start marker, one receipt)."""
    layout(host);phase=WRITE[launch][0]
    if plan and host.tree.get(day_path('plans',launch+'.json')) is None:add_file(host,day_path('plans',launch+'.json'),b'{"synthetic step plan of %s"}'%launch.encode())
    plan_sha=sha(bytes(host.tree.get(day_path('plans',launch+'.json')).content)) if host.tree.get(day_path('plans',launch+'.json')) else '9a'*32
    identity={'epoch':EPOCH,'day':DAY,'phase':phase,'operation':launch,'attempt_key':attempt_key(EPOCH,DAY,phase,launch),'step_plan_sha256':plan_sha}
    if started:add_file(host,day_path('receipts',launch+'.STARTED.json'),canonical(dict(identity,schema='K9_STEP_STARTED_V1',started_at='2026-10-05T21:29:12+00:00')))
    named={}
    for key,content in (OUTPUTS.get(launch,{}) if outputs is None else outputs).items():put(host,key,content);named[key]=sha(content)
    body=dict(identity,schema='K9_STEP_RECEIPT_V1',status='COMPLETE',code=None,started_at='2026-10-05T21:29:12+00:00',completed_at='2026-10-05T21:40:00+00:00',
              package_sha256=PACKAGE,build_sha=REVISION,outputs=named,aggregates={},counts={'logical_fetch_calls':1})
    if receipt:
        complete=dict(body);complete.update(changes or {});add_file(host,day_path('receipts',launch+'.RECEIPT.json'),canonical(complete))
    if failed:add_file(host,day_path('receipts',launch+'.FAILED.json'),canonical(dict(body,status=failed,code='STEP_'+failed,outputs={})))
    return body

def step_done(host,launch,**options):
    if WRITE[launch][1]=='LAUNCH':launched(host,launch,**{key:value for key,value in options.items() if key in ('state','exit_code','oom','labels','image','record_changes')})
    return runner_receipts(host,launch,**{key:value for key,value in options.items() if key in ('receipt','failed','started','changes','outputs')})

HOST_PLAN=canonical({'schema':'R2D2_V2_RISK_HOST_PLAN_V1','synthetic':True,'phase_windows':WINDOWS})+b'\n'
HOST_GO=b'{"schema":"R2D2_V2_RISK_HOST_GO_V1","synthetic":true}\n'
def spool(*parts):return day_path('risk','spool',sha(HOST_PLAN),*parts)
def bound_plan(host):
    """What bind leaves: the five documents in risk/plan, the spool directory, its runner receipt."""
    layout(host)
    docs={'OWNER_ORDER.json':owner_order(),'SOURCE_PINS.json':b'{"pins":"synthetic"}\n','list.private.json':b'{"list":1}\n','HOST_PLAN.json':HOST_PLAN,'GO.json':HOST_GO}
    outputs={'day/risk/plan/'+name:content for name,content in docs.items()}
    runner_receipts(host,'bind',outputs=outputs);add_dir(host,day_path('risk','spool'))
    return docs
PINS_DOC=b'{"pins":"synthetic"}\n'
PACKAGED_TIMES={'preflight':('2026-10-06T02:38:05+00:00','2026-10-06T02:38:10+00:00'),'acquire':('2026-10-06T02:41:10+00:00','2026-10-06T03:10:00+00:00'),
                'execute':('2026-10-06T03:50:10+00:00','2026-10-06T03:55:00+00:00')}
def packaged_receipt(host,phase,*,receipt=True,failed=False,started=True,changes=None):
    add_dir(host,spool())
    bound={'phase':phase,'manifest_sha256':sha(HOST_PLAN),'go_sha256':sha(HOST_GO)}
    begun,ended=PACKAGED_TIMES[phase]
    if started:add_file(host,spool(phase+'.STARTED.json'),canonical(dict(bound,started_at=begun)))
    outputs={'preflight':{},'acquire':{'batch_manifest_sha256':'d4'*32,'acquired_manifest':{'path':'acquired.json','sha256':'d5'*32},'counts':{'symbols':2}},
             'execute':{'assessment_manifest':{'path':'manifest.json','sha256':'d6'*32},'output_manifest_sha256':'d7'*32,'risk_sha256':sha(RISK),
                        'counts':{'READY':2}}}[phase]
    body=dict(bound,schema='R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1',status='COMPLETE',namespace='R2D2-V2-DIAG-R4-'+DAY,session_date=DAY,
              started_at=begun,completed_at=ended,previous_receipt_sha256=None,outputs=outputs,
              operation_activation=False,certification_granted=False)
    body.update(changes or {})
    if receipt:add_file(host,spool(phase+'.RECEIPT.json'),canonical(body))
    if failed:add_file(host,spool(phase+'.FAILED.json'),canonical(dict(bound,schema='R2D2_V2_RISK_HOST_FAILED_V1',status='REFUSED',code='PHASE_OUTSIDE_WINDOW')))
    return body
RISK=b'{"schema":"V2_RISK_COMPONENTS_V1","synthetic":true}'

class Attached:
    """docker.on_run for the attached steps: what the runner (bind, stage) or the packaged CLI (preflight) leave, written
    through the binds of the call. Knobs: returncode, receipt (False: no receipt), failed (a FAILED receipt), marker."""
    def __init__(self,returncode=0,receipt=True,failed=False,marker=True,changes=None,documents=None,line=None,claimed=None):
        self.returncode,self.receipt,self.failed,self.marker,self.changes,self.documents,self.line=returncode,receipt,failed,marker,changes,documents,line
        self.claimed=claimed;self.calls=[];self.no_spool=False;self.risk=None;self.during=None
    def __call__(self,call):
        self.calls.append(call);name=call.name.split('-',3)[3]
        assert call.command[:4]==['timeout','-s','KILL',{'bind':'35','preflight':'35','stage':'18'}[name]]
        if name=='preflight':
            assert call.command[4:8]==['python','-m','app.r2d2_v2_risk_host_executor','preflight'] and '--previous-receipt-sha256' not in call.command
            base='/c3po-k9-day/risk/spool/'+sha(HOST_PLAN)
            call.mkdir(base)
            bound={'phase':'preflight','manifest_sha256':sha(HOST_PLAN),'go_sha256':sha(HOST_GO)}
            if self.marker:call.write(base+'/preflight.STARTED.json',canonical(dict(bound,started_at=GRID['preflight'])))
            if self.receipt:
                body=dict(bound,schema='R2D2_V2_RISK_HOST_PHASE_RECEIPT_V1',status='COMPLETE',namespace='R2D2-V2-DIAG-R4-'+DAY,session_date=DAY,
                          started_at=GRID['preflight'],completed_at=GRID['preflight'],previous_receipt_sha256=None,outputs={},
                          operation_activation=False,certification_granted=False);body.update(self.changes or {})
                call.write(base+'/preflight.RECEIPT.json',canonical(body))
            if self.failed:call.write(base+'/preflight.FAILED.json',canonical(dict(bound,schema='R2D2_V2_RISK_HOST_FAILED_V1',status='REFUSED',code='PHASE_OUTSIDE_WINDOW')))
            return self.returncode,b'{"status":"COMPLETE"}\n'
        assert call.command[4:6]==['python','-I'] and call.command[7]=='--plan' and call.command[9]=='--plan-sha256'
        plan_raw=call.read('/c3po-k9-day/plans/'+name+'.json');assert sha(plan_raw)==call.command[10]
        plan=json.loads(plan_raw);phase='risk'
        identity={'epoch':EPOCH,'day':DAY,'phase':phase,'operation':name,'attempt_key':attempt_key(EPOCH,DAY,phase,name),'step_plan_sha256':call.command[10]}
        if self.marker:call.write('/c3po-k9-day/receipts/'+name+'.STARTED.json',canonical(dict(identity,schema='K9_STEP_STARTED_V1',started_at=GRID[name])))
        outputs={}
        if name=='bind' and not self.failed:
            assert plan['risk']['owner_order_text'].encode()==owner_order()
            docs={'OWNER_ORDER.json':plan['risk']['owner_order_text'].encode(),'SOURCE_PINS.json':PINS_DOC,'list.private.json':b'{"list":1}\n',
                  'HOST_PLAN.json':HOST_PLAN,'GO.json':HOST_GO};docs.update(self.documents or {})
            for doc,content in docs.items():call.write('/c3po-k9-day/risk/plan/'+doc,content);outputs['day/risk/plan/'+doc]=sha(content)
            outputs['day/risk/plan/SOURCE_PINS.json']=PINS                   # the signed pins (the stand-in's bytes are not the real pins file)
            outputs.update(self.claimed or {})
            if not self.no_spool:call.mkdir('/c3po-k9-day/risk/spool')
        if name=='stage' and not self.failed:
            staged=self.risk or RISK;call.write('/c3po-source/components/'+DAY+'/risk.json',staged);outputs['source/components/%s/risk.json'%DAY]=sha(staged)
            if self.during is not None:self.during(call)
        body=dict(identity,schema='K9_STEP_RECEIPT_V1',status='COMPLETE',code=None,started_at=GRID[name],completed_at=GRID[name],
                  package_sha256=PACKAGE,build_sha=REVISION,outputs=outputs,aggregates={},counts={'symbols_staged':2})
        body.update(self.changes or {})
        line=b''
        if self.receipt and not self.failed:call.write('/c3po-k9-day/receipts/'+name+'.RECEIPT.json',canonical(body));line=canonical(body)+b'\n'
        if self.failed:
            failed=canonical(dict(body,status='FAILED',code='STEP_FAILED_SYNTHETIC',outputs={}));call.write('/c3po-k9-day/receipts/'+name+'.FAILED.json',failed);line=failed+b'\n'
        if self.line=='STRIPPED':return self.returncode,line.rstrip(b'\n')
        return self.returncode,(line if self.line is None else self.line)

def prepared(k,operation):
    """The host as the eve leaves it right before this operation's window (every needed input complete)."""
    host=world(k)
    if operation=='collect_launch':return host
    if operation in ('commit_launch',):step_done(host,'collect_launch')
    if operation=='publish_launch':step_done(host,'collect_launch');step_done(host,'commit_launch')
    if operation in ('components_launch','sources_launch','bind','preflight','acquire_launch','execute_launch','stage','capture_launch','capture_cleanup'):
        runner_receipts(host,'collect_launch');runner_receipts(host,'commit_launch');step_done(host,'publish_launch')
    if operation=='sources_launch':step_done(host,'components_launch')
    if operation in ('bind','preflight','acquire_launch','execute_launch','stage'):runner_receipts(host,'components_launch');step_done(host,'sources_launch')
    if operation in ('preflight','acquire_launch','execute_launch','stage'):
        bound_plan(host)
        host.tree.get(day_path('risk','plan','SOURCE_PINS.json')).content=bytearray(PINS_DOC)
    if operation in ('acquire_launch','execute_launch','stage'):packaged_receipt(host,'preflight')
    if operation in ('execute_launch','stage'):packaged_receipt(host,'acquire');launched(host,'acquire_launch')
    if operation=='stage':packaged_receipt(host,'execute');launched(host,'execute_launch');add_dir(host,SOURCE_ROOT+'/components');add_dir(host,SOURCE_ROOT+'/components/'+DAY)
    if operation=='capture_cleanup':launched(host,'capture_launch')
    if operation in ('capture_launch','capture_cleanup'):
        # the morning of D: the eve's containers are gone (stage removed the last one)
        host.docker.containers=[item for item in host.docker.containers if not item['Name'].startswith('/c3po-k9-') or item['Name'].endswith('capture_launch')]
    return host

def case(operation='commit_launch',now=None,**options):
    """(docs, host): a bound fixture of one operation that completes on its prepared host at its grid instant."""
    k=f.load(DIRECTORY);host=prepared(k,operation);moment=at(GRID[operation])
    plan=fields(host,operation,now=moment,**options)
    return f.Docs(k,plan,now=now or moment,minutes=MINUTES,evidence=list(EVIDENCE)),host

def state_of(host):
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)
