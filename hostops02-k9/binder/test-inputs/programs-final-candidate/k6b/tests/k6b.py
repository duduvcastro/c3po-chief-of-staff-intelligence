"""Fixtures of K6b (capacity switch): the emulated host as the activation (K6a, M3) leaves it on the first session day,
with the capacity tree provisioned (A4/E2) and its static config delivered (B5), and a request plan built from it as a
binder would copy it from read-only receipts of the same boot.

The core's emulation knows neither the interpolation of the capacity mount from the environment file nor what
env_file does to a render; both are added here by subclassing, as the core's CORE.md section 7.2 asks:
  CapacityCompose  config: the worker's /c3po-capacity is the placeholder volume (declared at the top level with its
                   project name) while .env sets no C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE, and a read-only bind of its
                   value when it does (compose.yml:169 at the release); every C3PO_R2D2_V2_CAPACITY_ line of .env
                   reaches the environment of the six backend services (env_file: ../.env). up: the new container
                   carries the rendered mounts in its inspect object.
  editor()         what the editor container does to the bound environment file, written here independently of the
                   source (a differential test runs the source's real script against a real file).
Every byte, number, ID and value is synthetic."""
import copy
import json
import re
from pathlib import Path

import family as f
import hostemu

HERE=Path(__file__).resolve().parent
DIRECTORY=HERE.parent
TARGET='/app/day-d-data'
LIVE=hostemu.DATA+'/r2d2-v2-live/2026-10-05'
OVERRIDE_NAME='compose.override.json'
OVERRIDE_FILE=LIVE+'/'+OVERRIDE_NAME
KEYS=('C3PO_R2D2_V2_LIVE_POLICY_FILE','C3PO_R2D2_V2_LIVE_POLICY_SHA','C3PO_R2D2_V2_SHADOW_RELEASE_FILE','C3PO_R2D2_V2_SHADOW_RELEASE_SHA')
ACTIVATION={KEYS[0]:TARGET+'/r2d2-v2-live/2026-10-05/policy.json',KEYS[1]:'5'*63+'1',
            KEYS[2]:TARGET+'/r2d2-v2-release-20261005/release.CERTIFIED.json',KEYS[3]:'7'*63+'2'}
CAPACITY='/var/lib/c3po-capacity'
CONFIG_NAME='week.static.capacity.json'
CONFIG=b'{"note":"synthetic static capacity config, never a real one","schema":"SYNTHETIC"}'
CONFIG_SHA=f.sha(CONFIG)
LOCK=hostemu.LOCK_DIRECTORY+'/'+hostemu.LOCK_NAME
PENDING='/run/c3po-security/reboot.pending'
EDITOR_TARGET='/c3po-env/.env'
PLACEHOLDER='c3po_capacity_unprovisioned'
MOUNT_LINE='C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE='+CAPACITY
BLOCK=[MOUNT_LINE,'C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=/c3po-capacity/config/'+CONFIG_NAME,'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA='+CONFIG_SHA,
       'C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY','C3PO_R2D2_V2_CAPACITY_REQUIRED=true']
CAPACITY_NAMES=[line.split('=',1)[0] for line in BLOCK]
BEFORE={'MOUNT':0,'ENABLE':1,'DISABLE_FAST':5,'DISABLE_FULL':5}
AFTER={'MOUNT':1,'ENABLE':5,'DISABLE_FAST':4,'DISABLE_FULL':0}
VOLUMES=[{'type':'bind','source':hostemu.DEPLOY+'/runtime/security/maintenance','target':'/run/c3po-maintenance','read_only':True,'bind':{'create_host_path':True}},
         {'type':'bind','source':hostemu.DATA,'target':TARGET,'bind':{'create_host_path':True}},
         {'type':'volume','source':PLACEHOLDER,'target':'/c3po-capacity','read_only':True,'volume':{}}]
CAPACITY_LINE=re.compile(r'[ \t]*(export[ \t]+)?C3PO_R2D2_V2_CAPACITY_')

def override_bytes(values=None):
    return json.dumps({'services':{'r2d2-worker':{'environment':dict(ACTIVATION if values is None else values)}}},sort_keys=True).encode()

def env_values(host):
    """The C3PO_R2D2_V2_CAPACITY_ lines of the emulated .env as a dict (what env_file and the interpolation see)."""
    node=host.tree.get(hostemu.ENV_FILE);out={}
    if node is None:return out
    for line in bytes(node.content).decode('latin-1').split('\n'):
        match=re.fullmatch(r'[ \t]*(?:export[ \t]+)?(C3PO_R2D2_V2_CAPACITY_[A-Z_]+)=(.*)',line)
        if match:out[match.group(1)]=match.group(2)
    return out

class CapacityCompose(hostemu.FakeCompose):
    def render(self,files,stdin,environment):
        code,result=super().render(files,stdin,environment)
        if code:return code,result
        values=env_values(self.docker.host)
        for name,kind in hostemu.SERVICES.items():
            if kind=='backend':result['services'][name].setdefault('environment',{}).update(values)
        source=values.get('C3PO_R2D2_V2_CAPACITY_MOUNT_SOURCE') or ''
        worker=result['services']['r2d2-worker'];volumes=[]
        for volume in worker.get('volumes') or []:
            if volume.get('target')=='/c3po-capacity' and source:
                volumes.append({'type':'bind','source':source,'target':'/c3po-capacity','read_only':True,'bind':{'create_host_path':True}})
            else:volumes.append(volume)
        worker['volumes']=volumes
        declared=result.setdefault('volumes',{})
        if source:declared.pop(PLACEHOLDER,None)
        if not declared:result.pop('volumes')
        return 0,result
    def recreate(self,service,rendered):
        after,self.after_up=self.after_up,None
        try:new=super().recreate(service,rendered)
        finally:self.after_up=after
        new['Mounts']=inspect_mounts(rendered.get('volumes') or [])
        if after is not None:after(self,new)
        return new

def inspect_mounts(volumes):
    """The Mounts member of docker inspect for rendered volumes (long form)."""
    out=[]
    for volume in volumes:
        if volume['type']=='bind':
            out.append({'Type':'bind','Source':volume['source'],'Destination':volume['target'],'Mode':'ro' if volume.get('read_only') else '',
                        'RW':not volume.get('read_only'),'Propagation':'rprivate'})
        else:
            name=hostemu.PROJECT+'_'+volume['source']
            out.append({'Type':'volume','Name':name,'Source':'/var/lib/docker/volumes/'+name+'/_data','Destination':volume['target'],'Driver':'local',
                        'Mode':'z','RW':not volume.get('read_only'),'Propagation':''})
    return out

# ---------------------------------------------------------------- the editor container, emulated
class Editor:
    """What the editor does to the file bound at /c3po-env/.env. Knobs: effect False (nothing written, the line and
    the code still said), returncode/output to answer something else, after(host) to act after the edit."""
    def __init__(self,host,script):
        self.host,self.script=host,script;self.calls=[];self.effect=True;self.returncode=None;self.output=None;self.after=None;self.before=None
    def __call__(self,call):
        assert call.options.get('--user')==['1000:1000'] and call.network=='none' and call.read_only_root and '--init' in call.flags
        assert call.options.get('--cap-drop')==['ALL'] and call.options.get('--security-opt')==['no-new-privileges']
        assert call.mounts==[{'source':hostemu.ENV_FILE,'target':EDITOR_TARGET,'read_only':False}] and call.command==['python','-I','-B','-']
        text=call.stdin.decode('ascii');assert text.startswith(self.script)
        match=re.fullmatch(r'raise SystemExit\(main\(json\.loads\((".*")\)\)\)\n',text[len(self.script):],re.S);assert match
        spec=json.loads(json.loads(match.group(1)));self.calls.append(spec)
        if self.before is not None:self.before(self.host)
        code,line=self.apply(spec)
        if self.after is not None:self.after(self.host)
        if self.returncode is not None:code=self.returncode
        if self.output is not None:return code,self.output
        return code,(json.dumps({'code':line[1],'status':line[0]},sort_keys=True)+'\n').encode()
    def apply(self,spec):
        node=self.host.tree.get(hostemu.ENV_FILE)
        if node is None or node.kind!='file':return 1,('ENV_EDIT_REFUSED','ENV_FILE_OPEN')
        if not (node.nlink==1 and [node.uid,node.gid]==spec['owner'] and node.mode==spec['mode']):return 1,('ENV_EDIT_REFUSED','ENV_FILE_NOT_AS_EXPECTED')
        raw=bytes(node.content)
        if raw and not raw.endswith(b'\n'):return 1,('ENV_EDIT_REFUSED','ENV_FILE_NOT_NEWLINE_TERMINATED')
        lines=raw.decode('latin-1').split('\n')[:-1] if raw else []
        count=len([line for line in lines if CAPACITY_LINE.match(line)]);tail=lines[len(lines)-count:] if count else []
        if not all(CAPACITY_LINE.match(line) for line in tail):return 1,('ENV_EDIT_REFUSED','ENV_CAPACITY_LINES_NOT_TRAILING')
        if tail not in spec['before']:return 1,('ENV_EDIT_REFUSED','ENV_CAPACITY_BLOCK_NOT_AS_SIGNED')
        new=''.join(line+'\n' for line in lines[:len(lines)-count]+spec['after']).encode('latin-1')
        if self.effect:
            node.content=bytearray(new);node.mtime+=1;node.ctime+=1
            self.host.log.append(('editor',hostemu.ENV_FILE))
        return 0,('ENV_EDIT_DONE',None)

# ---------------------------------------------------------------- the host
def settle_worker(host):
    """Recreate the worker from the files as they are: what the activation (and later a capacity switch) leaves."""
    compose=host.docker.compose;code,rendered=compose.render([hostemu.COMPOSE_FILE,OVERRIDE_FILE],None,{'C3PO_BUILD_SHA':hostemu.REVISION})
    assert code==0;return compose.recreate('r2d2-worker',rendered['services']['r2d2-worker'])

def set_block(host,count):
    node=host.tree.get(hostemu.ENV_FILE);raw=bytes(node.content).decode('latin-1')
    lines=[line for line in raw.split('\n')[:-1] if not CAPACITY_LINE.match(line)]+BLOCK[:count]
    node.content=bytearray(''.join(line+'\n' for line in lines).encode('latin-1'))

def prepare(host,k,state=0):
    """After the activation: the live directory with its override, the worker recreated with it; the capacity tree
    with its static config; .env holding the first `state` lines of the block, the worker recreated from it."""
    old=host.docker.compose
    compose=CapacityCompose(old.docker,old.project,old.env_file,old.base_file,old.base);host.docker.compose=compose
    compose.base['services']['r2d2-worker']['volumes']=copy.deepcopy(VOLUMES)
    compose.base['volumes']={PLACEHOLDER:{'name':hostemu.PROJECT+'_'+PLACEHOLDER},'c3po_day_d_data':{'name':'c3po_c3po_day_d_data'}}
    host.tree.add(hostemu.DATA+'/r2d2-v2-live',dev=hostemu.DATA_DEVICE,mode=0o755)
    host.tree.add(LIVE,dev=hostemu.DATA_DEVICE,mode=0o700)
    host.tree.add(LIVE+'/policy.json',kind='file',dev=hostemu.DATA_DEVICE,mode=0o600,content=b'{"synthetic":true}')
    host.tree.add(OVERRIDE_FILE,kind='file',dev=hostemu.DATA_DEVICE,mode=0o600,content=override_bytes())
    host.tree.add(CAPACITY,mode=0o700)
    for name in ('config','documents','go','payload'):host.tree.add(CAPACITY+'/'+name,mode=0o700)
    host.tree.add(CAPACITY+'/config/'+CONFIG_NAME,kind='file',mode=0o600,content=CONFIG)
    set_block(host,state);settle_worker(host)
    host.editor=Editor(host,k.m.ENV_EDIT_SCRIPT);host.docker.on_run=host.editor
    del host.log[:]                                           # what the fixture did is not what a run did
    return host

def world(k,state=0):return prepare(f.world(k),k,state)

def fields(host,mode='MOUNT'):
    return {'mode':mode,'data_root':hostemu.DATA,
            'capacity':{'root':hostemu.rows(host,CAPACITY),'config_name':CONFIG_NAME,'config_sha256':CONFIG_SHA},
            'override':{'directory':hostemu.rows(host,LIVE),'name':OVERRIDE_NAME,'environment':dict(ACTIVATION)},
            'worker':{'image_id':hostemu.BACKEND},
            'compose':{'project':hostemu.PROJECT,'env_file':hostemu.ENV_FILE,'files':[hostemu.COMPOSE_FILE]},
            'deploy_directory':hostemu.rows(host,hostemu.DEPLOY),
            'lock':{'directory':hostemu.rows(host,hostemu.LOCK_DIRECTORY),'wait_seconds':20},
            'probe_load_receipt_sha256':'9'*63+'4' if mode=='ENABLE' else None,'withdrawal_authorized':True,
            'evidence_boot_id_sha256':f.BOOT_SHA}

def load():return f.load(DIRECTORY)
def case(now=None,minutes=5,mode='MOUNT',state=None):
    """(docs, host): a bound fixture of K6b in that mode that completes on a fresh emulated host."""
    k=load();host=world(k,BEFORE[mode] if state is None else state);return f.Docs(k,fields(host,mode),now=now,minutes=minutes),host
def fresh(mode='MOUNT',now=None,minutes=5,state=None):
    docs,host=case(now,minutes,mode,state);return docs.k.m,docs,host
def timed(seconds=0.0,mode='MOUNT',now=None,minutes=5):
    m,docs,host=fresh(mode,now,minutes);budget=f.Budget(docs.now,seconds).attach(host);return m,docs,host,budget

def env_bytes(host):return bytes(host.tree.get(hostemu.ENV_FILE).content)
def base_env(host):
    raw=env_bytes(host).decode('latin-1');return ''.join(line+'\n' for line in raw.split('\n')[:-1] if not CAPACITY_LINE.match(line)).encode()
def expected_env(host,count):return base_env(host)+''.join(line+'\n' for line in BLOCK[:count]).encode()
def state_of(host):
    return host.tree.snapshot(),json.dumps(host.docker.containers,sort_keys=True),json.dumps(host.docker.images,sort_keys=True)
def worker(host):return host.docker.container(hostemu.WORKER)
def worker_env(host):return dict(item.split('=',1) for item in worker(host)['Config']['Env'])

# ---------------------------------------------------------------- hostile hosts (as K6a's fixtures)
def replace(host,path,kind,**attributes):
    if host.tree.get(path) is not None:host.tree.remove(path)
    parent=host.tree.get(path.rsplit('/',1)[0] or '/')
    if parent is not None:attributes.setdefault('dev',parent.dev)
    return host.tree.add(path,kind=kind,**attributes)
def answer(host,match,reply,nth=None):
    original=host.docker.run;count=[0]
    def run(args,stdin=None,environment=None):
        real=lambda:original(args,stdin,environment)
        if match(args):
            count[0]+=1
            if nth is None or count[0]==nth:return reply(real)
        return real()
    host.docker.run=run
def during(host,match,action,nth=1):
    original=host.docker.run;count=[0]
    def run(args,stdin=None,environment=None):
        if match(args):
            count[0]+=1
            if count[0]==nth:action(host)
        return original(args,stdin,environment)
    host.docker.run=run
is_inspect=lambda args:args[:2]==['container','inspect'] and 'RestartCount' in args[3]
is_environment=lambda args:args[:2]==['container','inspect'] and '.Config.Env' in args[3]
is_mounts=lambda args:args[:2]==['container','inspect'] and args[3]=='{{json .Mounts}}'
is_image=lambda args:args[:2]==['image','inspect']
is_list=lambda args:args[:1]==['ps']
is_render=lambda args:args[:1]==['compose'] and 'config' in args
is_up=lambda args:args[:1]==['compose'] and 'up' in args
is_editor=lambda args:args[:1]==['run']
