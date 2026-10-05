"""Shared fixtures of the K12 tests (a byte-identical copy in k12_window, k12_collect and k12_preflight; a test of each
family pins the copies equal). Everything here is synthetic: no value, identity or byte of the real host, release,
writer, documents or database.

  world(k)            hostemu.world() + supervisor operation 2 + what E2 (capacity tree, receipts directory), A7/E7
                      (secret.env), B6 (pins.env), K4 WRITER (the writer by hash in the config root) and the evening's
                      delivery (the window configs) would leave, with the emulated engine extended by subclassing:
                      K12Docker knows docker create, start, stop, logs and rm, and this family's inspect format.
  capacity_request()  the documents tool's REQUEST of one window, built as request_document() builds it.
  writer_line()       a line as manifest_writer.py prints it.
  at_view()           what the writer does in its container at the view: the manifest, the line, the exit.

hostemu is never edited. The writer's container is a state machine of the test, not the writer: created, parked
(running), exited with a line and an exit code, stopped by a signal."""
import base64
import copy
import hashlib
import json
import types
from datetime import datetime,timedelta,timezone
from pathlib import Path

import family as f
import hostemu
import request_document as rd

EPOCH='R2D2-V2-SHADOW-2026-10-05'
DAY='2026-10-06'
IMAGE=hostemu.BACKEND
REVISION=hostemu.REVISION
NETWORK='c3po_c3po_internal'
JOURNAL='/var/lib/c3po-bar/journal'
JOURNAL_TARGET='/c3po-journal'
CAPACITY='/var/lib/c3po-capacity'
CONFIG=CAPACITY+'/config'
MANIFESTS='/etc/c3po-bar/manifests'
READER='/etc/c3po-reader'
DOCKER_CLI=READER+'/docker-cli'
RECEIPTS='/var/lib/c3po-reader/capacity-receipts'
DATA=hostemu.DATA                          # the data volume (uid 1000 in hostemu's world): the named read-only exception
RELEASE=DATA+'/r2d2-v2-release-20261005'    # the release directory M1 installs (root 0700)
RELEASE_BYTES=b'{"schema":"SYNTHETIC_RELEASE","never":"a real release"}\n'
WINDOWS={1:'primary',2:'contingency_1',3:'contingency_2'}
VIEWS={1:'10:45:00',2:'11:45:00',3:'12:45:00'}
STARTS={1:'10:38:00',2:'11:38:00',3:'12:38:00'}
WRITER=b''.join(b'# SYNTHETIC TEST BYTES %04d: NOT manifest_writer.py, never executed\n'%index for index in range(700))
SECRET_URL='postgresql://reader:'+hostemu.SECRET+'@db:5432/c3po'
SECRET_ENV=('C3PO_DATABASE_URL='+SECRET_URL+'\n').encode()
PINS=b'C3PO_BUILD_SHA='+REVISION.encode()+b'\nC3PO_R2D2_V2_CAPACITY_REQUIRED=true\nSYNTHETIC_PIN_LINES=never-a-real-pin\n'
MANIFEST_BYTES=b'{"epoch":"R2D2-V2-SHADOW-2026-10-05","owner_uid":0,"session":"2026-10-06","symbols":["SYNTHA","SYNTHB"]}'
MANIFEST_SHA=hashlib.sha256(MANIFEST_BYTES).hexdigest()
SYMBOL_CANARY=b'SYNTHA'

def sha(raw):return hashlib.sha256(raw).hexdigest()
def label(text):return sha(('k12 synthetic '+text).encode())
def at(text):return datetime.fromisoformat(text)
def utc(day,clock):return '%sT%s+00:00'%(day,clock)
def b64(raw):return base64.b64encode(raw).decode('ascii')
def config_bytes(day,window):return f.canonical({'schema':'SYNTHETIC_CAPACITY_CONFIG','day':day,'window':window,'never':'a real config'})
def name_of(day,index):return 'c3po-k12-%s-w%d'%(day.replace('-',''),index)

# ---------------------------------------------------------------- the documents tool's REQUEST of one window
def mounts():
    return [{'source':DATA,'target':'/app/day-d-data','readonly':True},{'source':JOURNAL,'target':JOURNAL_TARGET,'readonly':True},
            {'source':CAPACITY,'target':'/c3po-capacity','readonly':True},{'source':MANIFESTS,'target':MANIFESTS,'readonly':False}]
def capacity_request(day=DAY,index=1,go_mode='DELEGATED_ACT_B',max_wait=900,**changes):
    """The REQUEST of window slot `index` (1, 2, 3), written by the documents tool's own request_document() (tests/
    request_document.py, a pinned copy): window_index = slot - 1, as the tool counts. `changes` replace members after."""
    window=WINDOWS[index];view=utc(day,VIEWS[index]);until=(at(view)+timedelta(seconds=10)).isoformat()
    config='/c3po-capacity/config/session=%s.%s.capacity.json'%(day,window);config_sha=sha(config_bytes(day,window))
    d={'manifest_directory':MANIFESTS,'writer_require_go_mode':go_mode or 'NOT_REQUIRED','image_id':IMAGE,'build_sha':REVISION,'network':NETWORK,
       'mounts':mounts(),'secret_env_path':READER+'/secret.env','pins_env':{'path':READER+'/pins.env','sha256':sha(PINS)},'docker_config':DOCKER_CLI,
       'writer_sha256':sha(WRITER),'authority_sha256':label('authority'),'host_binding_sha256':label('host binding')}
    documentary={key:label(key) for key in ('act_b_sha256','template_record_sha256','template_sha256','admission_go_sha256','admission_go_record_sha256',
                 'bar_manifest_go_sha256','bar_manifest_go_record_sha256','publication_sha256','veto_view_sha256','contract_sha256',
                 'causal_commitment_sha256','causal_list_sha256')}
    body=rd.request_document(types.SimpleNamespace(EPOCH=EPOCH),day=day,window=window,index=index-1,count=3,view_mode='PRE_DELIVERED',d=d,
                             release_sha=sha(RELEASE_BYTES),package_sha=label('package'),config_path=config,config_sha=config_sha,max_wait=max_wait,
                             start=utc(day,STARTS[index]),observed=view,until=until,cutoff=utc(day,'13:20:00'),documentary=documentary)
    body.update(changes);return body
def member(body):raw=f.canonical(body);return {'b64':b64(raw),'sha256':sha(raw)}
def raw_member(raw):return {'b64':b64(raw),'sha256':sha(raw)}

# ---------------------------------------------------------------- the writer's line
def writer_line(status='PUBLISHED_VERIFIED',code=None,day=DAY,index=1,**changes):
    line={'schema':'R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1','status':status,'code':code,'session':day,'mode':'PUBLISH','epoch':EPOCH,
          'owner_uid':0,'release_sha256':sha(RELEASE_BYTES),'capacity_config_sha256':sha(config_bytes(day,WINDOWS[index])),
          'package_sha256':label('package'),'build_sha':REVISION,'capacity_veto_mode':'DISPATCH_AND_DERIVATION_ONLY','massive_bars_enabled':True,
          'cutoff_at':utc(day,'13:20:00'),'stale_temporaries':0,'repaired_temporaries':0}
    if status in ('PUBLISHED_VERIFIED','ALREADY_PUBLISHED_VERIFIED'):
        line.update(prepare_status='COMMITTED',waited_seconds=401.5,view={'observed_at':utc(day,VIEWS[index]),'valid_until':'x'},
                    go_sha256=label('go'),go_mode='DELEGATED_ACT_B',template_sha256=label('template'),window={'not_before':'a','not_after':'b'},
                    binding_sha256=label('binding'),symbol_count=2,manifest_sha256=MANIFEST_SHA,published_at=utc(day,VIEWS[index]).replace(':00+',':03+'),
                    file={'uid':0,'gid':0,'mode':'0600','links':1})
    line.update(changes)
    return (json.dumps(line,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
EMPTY_LIST=dict(status='REFUSED',code='MANIFEST_SYMBOLS_EMPTY',prepare_status='COMMITTED',binding_sha256=label('binding'))

# ---------------------------------------------------------------- the emulated engine
STATE12=dict(hostemu.STATE,OOMKilled=('scalar','OOMKilled'))
CONFIG12=dict(hostemu.CONFIG,Cmd=('slice','Cmd'))
HOSTCONFIG12=dict(hostemu.HOSTCONFIG,AutoRemove=('scalar','AutoRemove'),RestartPolicy=('ptr','RestartPolicy',hostemu.fields('Name')))
CONTAINER12=dict(hostemu.CONTAINER,State=('ptr','State',STATE12),Config=('ptr','Config',CONFIG12),HostConfig=('ptr','HostConfig',HOSTCONFIG12))
FLAGS=('--rm','-i','--init','--read-only')
VALUES=('--pull','--user','--network','--cap-drop','--security-opt','--mount','--name','--env-file','--env','--label','--restart')
NEVER='0001-01-01T00:00:00Z'
CREATE_PREFIX=['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no']

def parse(arguments):
    """Options up to the first word that is not one, then the image and the command, as the CLI reads them."""
    flags=[];options={};binds=[];index=0
    while index<len(arguments) and arguments[index].startswith('-'):
        word=arguments[index]
        if word in FLAGS:flags.append(word);index+=1
        elif word in VALUES:
            value=arguments[index+1];index+=2
            if word=='--mount':binds.append(hostemu.parse_mount(value))
            else:options.setdefault(word,[]).append(value)
        else:raise AssertionError('docker option outside the emulated set: %r'%word)
    assert index<len(arguments),'no image'
    return flags,options,binds,arguments[index],list(arguments[index+1:])

def env_file(raw):
    out={}
    for line in raw.decode().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            name,_,value=line.partition('=');out[name]=value
    return out

class K12Docker(hostemu.FakeDocker):
    """The engine of hostemu, with what this family adds. Knobs: create_returncode, start_returncode, stop_returncode,
    logs_returncode, rm_fail (IDs rm refuses), on_start(container) -> 'PARK' or (exit_code, stdout), on_preflight(call)."""
    def setup(self):
        self.create_returncode=0;self.create_effect=True;self.create_output=None;self.start_returncode=0;self.start_effect=True
        self.stop_returncode=0;self.stop_effect=True;self.logs_returncode=0;self.rm_fail=set();self.rm_returncode=None
        self.on_start=lambda container:'PARK';self.stop_finished='2026-10-06T10:41:30.000000000Z';self.stdout={};self.environment_of={};self.created=[];self.on_preflight=None;self.k12_calls=[]
        return self
    def run(self,args,stdin=None,environment=None):
        if args[:3]==['container','inspect','--format'] and len(args)==5 and '"capacity_label"' in args[3]:
            self.environments.append(dict(environment or {}));self.k12_calls.append(('inspect',args[4]))
            if self.inspect_returncode:return self.inspect_returncode,b''
            item=self.container(args[4])
            return (1,b'') if item is None else self.render(args[3],CONTAINER12,item,True)
        verb=args[:1]
        if verb in (['create'],['start'],['stop'],['logs'],['rm']):
            self.environments.append(dict(environment or {}));self.k12_calls.append(tuple(args[:1]))
            return getattr(self,'do_'+args[0])(args[1:])
        if verb==['run'] and '--env-file' in args:
            self.environments.append(dict(environment or {}));self.k12_calls.append(('run',))
            flags,options,binds,image,command=parse(args[1:])
            assert '--rm' in flags and options.get('--pull')==['never'],'an attached run of this family is removed on exit and never pulls'
            if self.find(image) is None or self.find(image)['Id']!=image:return 125,b''
            for bind in binds:
                if self.host.tree.get(bind['source']) is None:return 125,b''
            for path in options.get('--env-file',[]):
                node=self.host.tree.get(path)
                if node is None or node.kind!='file':return 125,b''
            name=(options.get('--name') or [None])[0]
            if name is not None and self.container(name) is not None:return 125,b''
            assert self.on_preflight is not None,'the test gave no behaviour for the preflight container'
            code,out=self.on_preflight({'flags':flags,'options':options,'binds':binds,'image':image,'command':command});return code,out
        return hostemu.FakeDocker.run(self,args,stdin,environment)
    def do_create(self,arguments):
        flags,options,binds,image,command=parse(arguments)
        assert options.get('--pull')==['never'] and '--rm' not in flags and '-d' not in arguments,'create: never pulls, never --rm'
        if self.create_returncode:return self.create_returncode,b''
        if self.find(image) is None or self.find(image)['Id']!=image:return 125,b''
        for bind in binds:
            if self.host.tree.get(bind['source']) is None:return 125,b''
        environment={}
        for path in options.get('--env-file',[]):
            node=self.host.tree.get(path)
            if node is None or node.kind!='file':return 125,b''
            environment.update(env_file(bytes(node.content)))
        for word in options.get('--env',[]):name,_,value=word.partition('=');environment[name]=value
        name=options['--name'][0]
        if self.container(name) is not None:return 125,b''
        if not self.create_effect:return 0,b''
        labels=dict(word.split('=',1) for word in options.get('--label',[]))
        item=hostemu.container(name,image,image,['%s=%s'%pair for pair in sorted(environment.items())],running=False)
        item['State'].update(Status='created',Running=False,StartedAt=NEVER,FinishedAt=NEVER,OOMKilled=False,ExitCode=0,Pid=0)
        item['Config'].update(Labels=labels,Cmd=command,Image=image)
        item['HostConfig']=dict(NetworkMode=options['--network'][0],UsernsMode='',ReadonlyRootfs='--read-only' in flags,Init='--init' in flags,
                                Binds=None,AutoRemove='--rm' in flags,RestartPolicy={'Name':(options.get('--restart') or [''])[0]})
        item['Mounts']=[{'Type':'bind','Source':bind['source'],'Destination':bind['target'],'Mode':'','RW':not bind['read_only'],'Propagation':'rprivate'}
                        for bind in binds]
        self.containers.append(item);self.created.append(item['Id']);self.environment_of[item['Id']]=environment
        return 0,(self.create_output if self.create_output is not None else (item['Id']+'\n').encode())
    def do_start(self,arguments):
        assert len(arguments)==1;item=self.container(arguments[0])
        if item is None:return 1,b''
        if self.start_returncode and not self.start_effect:return self.start_returncode,b''
        outcome=self.on_start(item);item['State'].update(StartedAt='2026-10-06T10:40:01.000000000Z',Pid=4242)
        if outcome=='PARK':item['State'].update(Status='running',Running=True)
        else:self.exit(item,*outcome)
        return self.start_returncode,(arguments[0]+'\n').encode()
    def exit(self,item,code,stdout,oom=False,finished='2026-10-06T10:45:04.000000000Z'):
        item['State'].update(Status='exited',Running=False,ExitCode=code,Pid=0,FinishedAt=finished,OOMKilled=oom)
        self.stdout[item['Id']]=stdout
    def do_stop(self,arguments):
        assert arguments[:2]==['-t','5'] and len(arguments)==3;item=self.container(arguments[2])
        if item is None:return 1,b''
        if self.stop_effect and item['State']['Running']:self.exit(item,143,self.stdout.get(item['Id'],b''),finished=self.stop_finished)
        return self.stop_returncode,(arguments[2]+'\n').encode()
    def do_logs(self,arguments):
        assert len(arguments)==1;item=self.container(arguments[0])
        if item is None or self.logs_returncode:return self.logs_returncode or 1,b''
        return 0,self.stdout.get(item['Id'],b'')
    def do_rm(self,arguments):
        assert arguments and not [word for word in arguments if word.startswith('-')],'rm: no -f, no -v'
        out=b'';failed=False
        for identifier in arguments:
            item=self.container(identifier)
            if item is None or item['State']['Running'] or identifier in self.rm_fail:failed=True;continue
            self.containers.remove(item);out+=(identifier+'\n').encode()
        return (self.rm_returncode if self.rm_returncode is not None else (1 if failed else 0)),out

def at_view(host,name,line=None,code=0,publish=True,day=DAY,two_links=False):
    """What the writer does at the view in the parked container: the manifest (0600 root, one link) and the line."""
    item=host.docker.container(name);assert item['State']['Running']
    if publish:
        host.tree.add(MANIFESTS+'/'+day+'.json',kind='file',mode=0o600,content=MANIFEST_BYTES)
        if two_links:
            node=host.tree.get(MANIFESTS+'/'+day+'.json');host.tree.get(MANIFESTS).children['.%s.json.%s.tmp'%(day,'ab'*8)]=node;node.nlink=2
    host.docker.exit(item,code,writer_line() if line is None else line)
    return item

# ---------------------------------------------------------------- the host
def world(k,day=DAY,windows=(1,2,3),writer=WRITER):
    host=f.world(k);hostemu.provision_supervisor(host)
    host.docker.__class__=K12Docker;host.docker.setup()
    tree=host.tree
    for path in (READER,DOCKER_CLI,'/var/lib/c3po-reader',RECEIPTS,CAPACITY,CONFIG,CAPACITY+'/documents',CAPACITY+'/payload',CAPACITY+'/go',RELEASE):
        tree.add(path,mode=0o700)
    tree.add(RELEASE+'/release.CERTIFIED.json',kind='file',mode=0o600,content=RELEASE_BYTES)
    tree.add(READER+'/secret.env',kind='file',mode=0o600,content=SECRET_ENV)
    tree.add(READER+'/pins.env',kind='file',mode=0o600,content=PINS)
    tree.add(CONFIG+'/manifest_writer-%s.py'%sha(writer),kind='file',mode=0o600,content=writer)
    for index in windows:tree.add(CONFIG+'/session=%s.%s.capacity.json'%(day,WINDOWS[index]),kind='file',mode=0o600,content=config_bytes(day,WINDOWS[index]))
    for name in ('epoch.json','maintenance.lock'):tree.add(JOURNAL+'/'+name,kind='file',mode=0o600,content=b'{}')
    return host

def rows(host,path):return hostemu.rows(host,path)
def chains(host,names,journal=JOURNAL,data=RELEASE):
    paths={'config':CONFIG,'manifests':MANIFESTS,'reader_config':READER,'docker_cli':DOCKER_CLI,'journal':journal,'data':data,'receipts':RECEIPTS}
    return {name:rows(host,paths[name]) for name in names}

def launched(host,k,day=DAY,index=1,request_sha='5e'*32,body=None,state='running'):
    """A container of this family as K12w LAUNCH leaves it (created by the emulated engine itself, then started)."""
    body=body or capacity_request(day,index);raw=f.canonical(body);name=name_of(day,index)
    derived=k.m.k12_capacity_request(raw_member(raw))[2]
    words=k.m.k12_container_words(derived,name,[('c3po.k12.request_sha256',request_sha),('c3po.k12.capacity_request_sha256',sha(raw))])
    code,out=host.docker.run(CREATE_PREFIX+words);assert code==0,code
    identifier=out.decode().strip()
    if state in ('running','exited'):host.docker.do_start([identifier])
    return host.docker.container(identifier)

def persisted(host,k,item,day=DAY,index=1,stdout=None,launch_sha='5e'*32,body=None,**changes):
    """The private receipt K12w PERSIST leaves for an exited container."""
    body=body or capacity_request(day,index);raw=f.canonical(body)
    stdout=host.docker.stdout.get(item['Id'],b'') if stdout is None else stdout
    value={'schema':'K12_PERSISTED_WRITER_RECEIPT_V1','epoch':EPOCH,'day':day,'window':WINDOWS[index],'window_slot':index,'container_id':item['Id'],
           'container_name':item['Name'][1:],'launch_request_sha256':launch_sha,'capacity_request_sha256':sha(raw),'persist_request_sha256':'6f'*32,
           'image_id':item['Image'],'exit_code':item['State']['ExitCode'],'oom_killed':item['State']['OOMKilled'],'started_at':item['State']['StartedAt'],
           'finished_at':item['State']['FinishedAt'],'stdout_b64':b64(stdout),'stdout_sha256':sha(stdout),'stdout_bytes':len(stdout)}
    value.update(changes);path=RECEIPTS+'/k12-%s-w%d.writer.json'%(day,index)
    if host.tree.get(path) is not None:host.tree.remove(path)
    host.tree.add(RECEIPTS+'/k12-%s-w%d.writer.json'%(day,index),kind='file',mode=0o600,content=f.canonical(value))
    return value

def engine(host):return json.dumps(host.docker.containers,sort_keys=True)
