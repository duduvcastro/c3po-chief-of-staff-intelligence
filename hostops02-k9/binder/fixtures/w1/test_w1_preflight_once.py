"""Synthetic local tests only. No SSH, host, real credential, docker binary or operational GO.

The fake docker below emulates the Docker CLI's --format behaviour for the constructs the payload uses:
typed execution first; on any execution error a second execution against the raw JSON with
missingkey=error (the fallback the real host showed on 2026-10-01); parse errors for a '{' inside an
action. Its container inspect returns Mounts in a different order on every call, as the real daemon does
(the cause of the three problems of the read of 2026-10-02). Shapes follow the earlier receipts; every
identifier, name, count and size in the fixtures is synthetic. systemctl and pgrep outputs are documented
shapes. The template emulator is the block reviewed with the earlier family, plus eq and split.
"""
import ast
from datetime import datetime,timedelta,timezone
import errno
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import stat
import sys
import time
import types
import pytest

ROOT=Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/(name+'.py'))
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result;spec.loader.exec_module(result);return result
p=module('w1_preflight_readonly');t=module('transport_once');l=module('launcher_stdin');d=module('dispatch_once')
NOW=datetime(2026,10,3,13,tzinfo=timezone.utc)          # Saturday 03/10 10:00 BRT
# The signed date set, written out here on its own: Friday 02/10 to Saturday 10/10, UTC days.
DATE_SET=['2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10']
SOURCE=(ROOT/'w1_preflight_readonly.py').read_bytes()
TRANSPORT_PIN='5900efbf916d679a6ce176dd71413f304e21e0c9ab65b0ff8ee742cc212f2918'
LAUNCHER_PIN='2842444ec6e46f5e47cad87265927ea3a1a853f21fe72ec2459cf7ac31c3a08e'
REVIEWED_DISPATCH_PIN='8415e357e48e5662c959b4105acea19bc280cda10112b8370bafd27f7920c409'
RECEIPT='READONLY_W1PREFLIGHT01_RECEIPT_V1'
PUBLICATION='W1PREFLIGHT01_INTENT_PUBLICATION_V1'
REFUSAL='READONLY_SUPERVISOR_HOSTFACTS_STDIN_RESULT_V1'       # the launcher bytes are the reviewed ones, label included


# ---------------------------------------------------------------- Go text/template subset, Docker CLI semantics
class TemplateSyntax(Exception):pass
class ExecError(Exception):pass
class Number(str):
    """json.Number: the raw fallback decodes with UseNumber, so a number is a string kind there."""
NOTHING=object()
STRING=re.compile(r'"(?:[^"\\\n]|\\.)*"')

def rawify(value):
    if type(value) is int:return Number(str(value))
    if type(value) is list:return [rawify(item) for item in value]
    if type(value) is dict:return {key:rawify(item) for key,item in value.items()}
    return value

class TypedMap:
    def __init__(self,data,zero):self.data,self.zero=data,zero
class Struct:
    def __init__(self,schema,data):self.schema,self.data=schema,data
    def field(self,name):
        if name not in self.schema:raise ExecError("can't evaluate field %s in type struct"%name)
        spec=self.schema[name];value=self.data.get(spec[1])
        if spec[0]=='scalar':return value
        if spec[0]=='ptr':return None if value is None else Struct(spec[2],value)
        if spec[0]=='slice':return None if value is None else [Struct(spec[2],item) for item in value] if len(spec)>2 else value
        return TypedMap(value or {},spec[2])
def fields(*names,**others):
    schema={name:('scalar',name) for name in names};schema.update(others);return schema

def go_json(value):
    if isinstance(value,Struct) or isinstance(value,TypedMap):value=value.data
    if isinstance(value,Number):return str(value)
    if value is None:return 'null'
    if value is True:return 'true'
    if value is False:return 'false'
    if type(value) in (int,str):return json.dumps(value,ensure_ascii=False)
    if type(value) is list:return '['+','.join(go_json(item) for item in value)+']'
    if type(value) is dict:return '{'+','.join(json.dumps(key)+':'+go_json(value[key]) for key in sorted(value))+'}'
    raise ExecError('json: unsupported value')
def go_index(item,*keys):
    if item is None:raise ExecError('index of untyped nil')
    for key in keys:
        if item is None:raise ExecError('index of nil pointer')
        if isinstance(item,TypedMap):item=item.data.get(key,item.zero)
        elif type(item) is dict:
            if type(key) is not str:raise ExecError('value has type int; should be string')
            item=item.get(key)
        elif type(item) is list:
            if type(key) is not int or not 0<=key<len(item):raise ExecError('index out of range')
            item=item[key]
        else:raise ExecError("can't index item of type %s"%type(item).__name__)
    return item
FUNCTIONS={'json':go_json,'index':go_index}

def truth(value):
    if isinstance(value,TypedMap):return bool(value.data)
    if isinstance(value,Struct):return True
    if value is None or value is False:return False
    if value is True:return True
    if type(value) is int:return value!=0
    return len(value)>0          # str, json.Number (string kind: "0" is true), list, dict
def show(value):
    if value is None:return '<no value>'
    if value is True or value is False:return 'true' if value else 'false'
    if isinstance(value,str) or type(value) is int:return str(value)
    return '<complex value>'

def lex_action(body):
    tokens=[];i=0
    while i<len(body):
        c=body[i];glued=i>0 and body[i-1] not in ' \t'
        if c in ' \t':i+=1;continue
        if c=='"':
            m=STRING.match(body,i)
            if not m:raise TemplateSyntax('unterminated quoted string')
            tokens.append(('string',json.loads(m.group()),glued));i=m.end();continue
        if body.startswith(':=',i):tokens.append(('declare',None,glued));i+=2;continue
        if c in '(),|':tokens.append((c,None,glued));i+=1;continue
        if c=='$':
            m=re.compile(r'\$[A-Za-z0-9_]*').match(body,i);tokens.append(('var',m.group(),glued));i=m.end();continue
        if c=='.':
            m=re.compile(r'(?:\.[A-Za-z_][A-Za-z0-9_]*)+').match(body,i)
            if m:tokens.append(('fields',m.group()[1:].split('.'),glued));i=m.end()
            else:tokens.append(('dot',None,glued));i+=1
            continue
        m=re.compile(r'[A-Za-z_][A-Za-z0-9_]*').match(body,i)
        if m:tokens.append(('ident',m.group(),glued));i=m.end();continue
        m=re.compile(r'[0-9]+').match(body,i)
        if m:tokens.append(('number',int(m.group()),glued));i=m.end();continue
        raise TemplateSyntax('unrecognized character in action: %r'%c)   # Go: '{' or '}' inside an action
    return tokens

def split(template):
    parts=[];pos=0
    while True:
        start=template.find('{{',pos)
        if start<0:parts.append(('text',template[pos:]));return parts
        parts.append(('text',template[pos:start]));i=start+2
        while True:
            if i>=len(template):raise TemplateSyntax('unclosed action')
            if template[i]=='"':
                m=STRING.match(template,i)
                if not m:raise TemplateSyntax('unterminated quoted string')
                i=m.end();continue
            if template.startswith('}}',i):break
            i+=1
        parts.append(('action',lex_action(template[start+2:i])));pos=i+2

def parse_pipeline(tokens,pos,allow_two=False,nested=False):
    names=[]
    if pos<len(tokens) and tokens[pos][0]=='var':
        if pos+1<len(tokens) and tokens[pos+1][0]=='declare':names=[tokens[pos][1]];pos+=2
        elif pos+3<len(tokens) and [token[0] for token in tokens[pos+1:pos+4]]==[',','var','declare']:
            if not allow_two:raise TemplateSyntax('too many declarations')
            names=[tokens[pos][1],tokens[pos+2][1]];pos+=4
    commands=[[]]
    def chain():
        nonlocal pos
        if pos<len(tokens) and tokens[pos][0]=='fields' and tokens[pos][2]:pos+=1;return tokens[pos-1][1]
        return []
    while pos<len(tokens):
        kind,value,_=tokens[pos]
        if kind==')':
            if not nested:raise TemplateSyntax('unexpected right paren')
            break
        pos+=1
        if kind=='|':commands.append([])
        elif kind=='(':
            inner,pos=parse_pipeline(tokens,pos,nested=True)
            if pos>=len(tokens) or tokens[pos][0]!=')':raise TemplateSyntax('unclosed left paren')
            pos+=1;commands[-1].append(('paren',inner,chain()))
        elif kind=='var':commands[-1].append(('var',value,chain()))
        elif kind=='ident':
            if value in ('true','false','nil'):commands[-1].append(('literal',{'true':True,'false':False,'nil':None}[value]))
            elif value in FUNCTIONS:commands[-1].append(('function',value))
            else:raise TemplateSyntax('function "%s" not defined'%value)
        elif kind in ('string','number'):commands[-1].append(('literal',value))
        elif kind=='dot':commands[-1].append(('dot',))
        elif kind=='fields':commands[-1].append(('fields',value))
        else:raise TemplateSyntax('unexpected %s'%kind)
    if any(not command for command in commands):raise TemplateSyntax('missing value for command')
    return (names,commands),pos

def parse(template):
    parts=split(template);index=[0]
    def block(closers):
        nodes=[]
        while index[0]<len(parts):
            kind,value=parts[index[0]];index[0]+=1
            if kind=='text':
                if value:nodes.append(('text',value))
                continue
            head=value[0] if value else ('',None,False)
            if head[0]=='ident' and head[1] in ('end','else'):
                if head[1] not in closers:raise TemplateSyntax('unexpected {{%s}}'%head[1])
                if len(value)>1:raise NotImplementedError('else-if is outside the emulated subset')
                return nodes,head[1]
            if head[0]=='ident' and head[1] in ('if','with','range'):
                pipe,end=parse_pipeline(value,1,allow_two=head[1]=='range')
                body,closer=block(('end','else'));other=[]
                if closer=='else':other,closer=block(('end',))
                nodes.append((head[1],pipe,body,other));continue
            pipe,end=parse_pipeline(value,0);nodes.append(('print',pipe))
        if closers:raise TemplateSyntax('unexpected EOF')
        return nodes,None
    return block(())[0]

class Engine:
    def __init__(self,missing_error):self.missing_error=missing_error
    def field(self,value,name):
        if isinstance(value,Struct):return value.field(name)
        if value is None:raise ExecError('nil pointer evaluating .%s'%name)
        if isinstance(value,TypedMap):return value.data.get(name,value.zero)
        if type(value) is dict:
            if name in value:return value[name]
            if self.missing_error:raise ExecError('map has no entry for key "%s"'%name)
            return None
        raise ExecError("can't evaluate field %s in type %s"%(name,type(value).__name__))
    def operand(self,node,dot,variables):
        if node[0]=='dot':return dot
        if node[0]=='literal':return node[1]
        if node[0]=='fields':value,names=dot,node[1]
        elif node[0]=='var':
            if node[1] not in variables:raise ExecError('undefined variable %s'%node[1])
            value,names=variables[node[1]],node[2]
        elif node[0]=='paren':value,names=self.pipeline(node[1],dot,variables),node[2]
        else:raise NotImplementedError(node[0])
        for name in names:value=self.field(value,name)
        return value
    def pipeline(self,pipe,dot,variables):
        value=NOTHING
        for command in pipe[1]:
            if command[0][0]=='function':
                arguments=[self.operand(node,dot,variables) for node in command[1:]]
                if value is not NOTHING:arguments.append(value)
                value=FUNCTIONS[command[0][1]](*arguments)
            else:
                if len(command)>1 or value is not NOTHING:raise ExecError("can't give argument to non-function")
                value=self.operand(command[0],dot,variables)
        return value
    def walk(self,nodes,dot,variables,out):
        for node in nodes:
            if node[0]=='text':out.append(node[1])
            elif node[0]=='print':
                value=self.pipeline(node[1],dot,variables)
                if node[1][0]:variables[node[1][0][0]]=value
                else:out.append(show(value))
            elif node[0] in ('if','with'):
                scope=dict(variables);value=self.pipeline(node[1],dot,scope)
                if node[1][0]:scope[node[1][0][0]]=value
                if truth(value):self.walk(node[2],value if node[0]=='with' else dot,scope,out)
                else:self.walk(node[3],dot,dict(variables),out)
            else:
                value=self.pipeline(node[1],dot,variables);names=node[1][0]
                if isinstance(value,TypedMap):value=value.data
                if value is None:items=[]
                elif type(value) is list:items=list(enumerate(value))
                elif type(value) is dict:items=[(key,value[key]) for key in sorted(value)]
                else:raise ExecError("range can't iterate over %s"%type(value).__name__)
                if not items:self.walk(node[3],dot,dict(variables),out)
                for key,element in items:
                    scope=dict(variables)
                    if len(names)==1:scope[names[0]]=element
                    elif len(names)==2:scope[names[0]],scope[names[1]]=key,element
                    self.walk(node[2],element,scope,out)
def execute(nodes,data,missing_error):
    out=[];Engine(missing_error).walk(nodes,data,{'$':data},out);return ''.join(out)

# Two more functions of the Docker CLI template set, used by the one new environment-flag template.
def go_kind(value):
    return 'bool' if isinstance(value,bool) else 'string' if isinstance(value,str) else 'int' if type(value) is int else 'nil' if value is None else 'other'
def go_eq(first,*others):
    if not others:raise ExecError('missing argument for comparison')
    for other in others:
        if go_kind(first) in ('nil','other') or go_kind(other) in ('nil','other') or go_kind(first)!=go_kind(other):
            raise ExecError('incompatible types for comparison')
    return any(first==other for other in others)
def go_split(value,separator):
    if not isinstance(value,str) or not isinstance(separator,str):raise ExecError('wrong type for value; expected string')
    return value.split(separator)
FUNCTIONS.update(eq=go_eq,split=go_split)

HEALTH=fields('Status','FailingStreak')
STATE=fields('Status','Running','Paused','Restarting','Dead','Pid','ExitCode','StartedAt','FinishedAt',Health=('ptr','Health',HEALTH))
CONFIG=fields('Hostname','User','Image',Env=('slice','Env'),Labels=('map','Labels',''))
HOSTCONFIG=fields('NetworkMode','UsernsMode','ReadonlyRootfs','Init',Binds=('slice','Binds'))
MOUNT=fields('Type','Name','Source','Destination','Driver','Mode','RW','Propagation')
NETWORKS=fields(Networks=('map','Networks',None))
CONTAINER=fields('Created','Path','Image','Name','RestartCount','Driver','Platform',ID=('scalar','Id'),State=('ptr','State',STATE),
                 Config=('ptr','Config',CONFIG),HostConfig=('ptr','HostConfig',HOSTCONFIG),Mounts=('slice','Mounts',MOUNT),
                 NetworkSettings=('ptr','NetworkSettings',NETWORKS))
IMAGE=fields('Created','Architecture','Os','Size',ID=('scalar','Id'),RepoTags=('slice','RepoTags'),Config=('ptr','Config',CONFIG))
VERSION=fields(Client=('ptr','Client',fields('Version')),Server=('ptr','Server',fields('Version')))
PS=fields('ID','Names','State','Image')
NETWORK=fields('Name','Created','Scope','Driver','Internal','Attachable','Ingress',ID=('scalar','Id'),Containers=('map','Containers',None))
NETWORK_IDS={'c3po_c3po_internal':'a1'*32,'c3po_db_loopback':'b2'*32,'chief-of-staff-digital_default':'c3'*32}

class FakeDocker:
    def __init__(self,containers,images,version,networks):
        self.containers,self.images,self.version,self.networks=containers,images,version,networks
        self.modes=[];self.inspections=0;self.before_inspect=None;self.shuffle=None;self.network_typed=True
    def render(self,template,schema,raw,fallback):
        try:nodes=parse(template)
        except TemplateSyntax:return 64,b''
        try:
            line=execute(nodes,Struct(schema,raw),False);self.modes.append('typed');return 0,(line+'\n').encode()
        except ExecError:
            if not fallback:return 1,b''
        try:
            line=execute(nodes,rawify(json.loads(json.dumps(raw))),True);self.modes.append('raw');return 0,(line+'\n').encode()
        except ExecError:return 1,b''
    def network(self,name):
        if name not in self.networks:return None
        members={item['Id']:{'Name':item['Name'][1:],'EndpointID':'e'*64,'MacAddress':'02:42:ac:13:00:07','IPv4Address':'172.19.0.7/16',
                             'IPv6Address':''} for item in self.containers
                 if item['State']['Running'] and name in item['NetworkSettings']['Networks']}
        return dict(self.networks[name],Name=name,Id=NETWORK_IDS.get(name,'d4'*32),Containers=members)
    def run(self,args):
        if args[:4]==['ps','-a','--no-trunc','--format'] and len(args)==5:
            out=b''
            for item in self.containers:
                code,line=self.render(args[4],PS,{'ID':item['Id'],'Names':item['Name'][1:],'State':item['State']['Status'],
                                                  'Image':item['Config']['Image']},False)
                if code:return code,b''
                out+=line
            return 0,out
        if args[:3]==['container','inspect','--format'] and len(args)==5:
            self.inspections+=1
            if self.before_inspect:self.before_inspect(self)
            for item in self.containers:
                if args[4] in (item['Id'],item['Name'],item['Name'][1:]):
                    view=item
                    if self.shuffle is not None:
                        # The daemon builds Mounts by ranging over a map: every answer has its own order.
                        mounts=list(item['Mounts']);self.shuffle.shuffle(mounts);view=dict(item,Mounts=mounts)
                    return self.render(args[3],CONTAINER,view,True)
            return 1,b''
        if args[:3]==['image','inspect','--format'] and len(args)==5:
            for item in self.images:
                if args[4]==item['Id'] or args[4] in (item.get('RepoTags') or []):return self.render(args[3],IMAGE,item,True)
            return 1,b''
        if args[:3]==['network','inspect','--format'] and len(args)==5:
            raw=self.network(args[4])
            if raw is None:return 1,b''
            return self.render(args[3],NETWORK if self.network_typed else fields(),raw,True)
        if args[:2]==['version','--format'] and len(args)==3:return self.render(args[2],VERSION,self.version,False)
        raise AssertionError('docker argv outside the fixed set: %r'%args[:3])


# ---------------------------------------------------------------- in-memory host
NOATIME=1<<30
ROOT_DEV=66305;DATA_DEV=66320;RUN_DEV=25
STAMP=int(NOW.timestamp())-3600
class Node:
    def __init__(self,kind,uid=0,gid=0,mode=0o755,dev=ROOT_DEV,ino=0,content=b'',mtime=STAMP,nlink=1,target=None,path=None):
        self.kind,self.uid,self.gid,self.mode,self.dev,self.ino,self.content=kind,uid,gid,mode,dev,ino,content
        self.mtime,self.nlink,self.target,self.path=mtime,nlink,target,path
        self.children={};self.atime=1
    def stat(self):
        form={'dir':stat.S_IFDIR,'file':stat.S_IFREG,'symlink':stat.S_IFLNK,'fifo':stat.S_IFIFO}[self.kind]
        return types.SimpleNamespace(st_mode=form|self.mode,st_uid=self.uid,st_gid=self.gid,st_dev=self.dev,st_ino=self.ino,
                                     st_nlink=self.nlink,st_size=len(self.content),st_atime_ns=self.atime,
                                     st_mtime_ns=self.mtime*10**9,st_ctime_ns=self.mtime*10**9)
class Tree:
    def __init__(self):self.root=Node('dir',ino=2,path='/');self.next=5000
    def add(self,path,kind='dir',**attributes):
        node=self.root;parts=path.strip('/').split('/')
        for index,part in enumerate(parts):
            last=index==len(parts)-1
            if part not in node.children:
                self.next+=1
                node.children[part]=Node(kind if last else 'dir',dev=node.dev,ino=self.next,path='/'+'/'.join(parts[:index+1]))
                if last and kind=='file' and 'mode' not in attributes:node.children[part].mode=0o644
            node=node.children[part]
            if last:
                for key,value in attributes.items():setattr(node,key,value)
        return node
    def get(self,path):
        node=self.root
        for part in path.strip('/').split('/'):node=node.children[part]
        return node
    def remove(self,path):
        parts=path.strip('/').split('/');node=self.root
        for part in parts[:-1]:node=node.children[part]
        del node.children[parts[-1]]

def command_key(argv):
    """Every argv the payload starts must be an entry of the signed table, with at most its one declared argument."""
    for name,(tool,args,extra) in p.COMMANDS.items():
        if argv[0].rsplit('/',1)[1]==tool and argv[1:1+len(args)]==args and len(argv)-1-len(args)==(1 if extra else 0):return name
    raise AssertionError('argv outside the signed table: %r'%argv[:5])

class FakeHost:
    def __init__(self,tree,docker,vfs):
        self.tree,self.docker,self.vfs=tree,docker,vfs
        self.fds={};self.next=100;self.log=[];self.keys=[];self.hang=set();self.noatime_available=True;self.on_run=None
        self.units={};self.processes={};self.answers={};self.files_opened=[];self.directories_listed=[];self.clock=NOW.timestamp()
        self.version=((3,12,3),'cpython');self.up=302400.5;self.expect_noatime=True;self.opened=[]
    def identity(self):return 0,0
    def pid(self):return 4242
    def now(self):return self.clock
    def python(self):return self.version
    def uptime(self):return self.up
    def noatime(self):
        if not self.noatime_available:raise p.Refused('NOATIME_UNAVAILABLE')
        return NOATIME
    def open(self,name,flags,dir_fd=None):
        assert flags&os.O_NOFOLLOW,'every open must be nofollow'
        assert not flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND),'every open must be read-only'
        if dir_fd is None:
            assert name in ('/','/proc');node=self.tree.root if name=='/' else self.tree.root.children.get('proc')
        else:
            assert '/' not in name and name not in ('','.','..');node=self.fds[dir_fd][0].children.get(name)
        if node is None:raise FileNotFoundError(errno.ENOENT,'absent')
        # the access-time discipline: every open outside /proc carries O_NOATIME, whatever the helper that makes it
        if self.expect_noatime and not (node.path=='/proc' or str(node.path).startswith('/proc/')):
            assert flags&NOATIME,'an open outside /proc without O_NOATIME: %s'%node.path
        self.opened.append(node.path)
        if node.kind=='symlink':raise OSError(errno.ELOOP,'link')
        if flags&os.O_DIRECTORY and node.kind!='dir':raise NotADirectoryError(errno.ENOTDIR,'not a directory')
        if node.kind!='dir':
            assert node.kind=='file' and flags&os.O_NONBLOCK,'only a regular file is opened for content, non-blocking'
            self.files_opened.append(node.path)
        self.next+=1;self.fds[self.next]=[node,flags,0];return self.next
    def close(self,fd):del self.fds[fd]
    def fstat(self,fd):return self.fds[fd][0].stat()
    def lstat(self,name,dir_fd):
        assert '/' not in name;node=self.fds[dir_fd][0].children.get(name)
        if node is None:raise FileNotFoundError(errno.ENOENT,'absent')
        return node.stat()
    def readlink(self,name,dir_fd):
        node=self.fds[dir_fd][0].children[name];assert node.kind=='symlink';return node.target
    def fstatvfs(self,fd):return self.vfs[self.fds[fd][0].dev]
    def read(self,fd,size):
        node,_,offset=self.fds[fd];block=node.content[offset:offset+size];self.fds[fd][2]+=len(block);return block
    def names(self,fd):
        node,flags,_=self.fds[fd];self.directories_listed.append(node.path)
        if not flags&NOATIME:node.atime+=1
        for name in list(node.children):yield name
    def run(self,argv,gate,seconds,capture=True):
        gate();assert seconds==p.CALL_SECONDS and argv[0].startswith('/') and all(type(item) is str for item in argv) and capture is True
        key=command_key(argv);self.log.append(list(argv));self.keys.append(key);tool=argv[0].rsplit('/',1)[1]
        if tool=='docker':
            # invariants of every docker command of every test: the pinned local endpoint, and never before the unit was asked
            assert argv[1:3]==['--host','unix:///var/run/docker.sock'],'a docker command without the pinned endpoint'
            assert 'docker_unit' in self.keys[:-1],'a docker command before the state of docker.service was asked'
        if self.on_run:self.on_run(self)
        if tool in self.hang or key in self.hang:raise p.Refused('COMMAND_TIMEOUT')
        if key in self.answers:
            answer=self.answers[key];return answer(argv) if callable(answer) else answer
        if tool=='docker':return self.docker.run(argv[3:])
        if tool=='systemctl':return self.systemctl(argv[1:])
        if tool=='pgrep':
            count=self.processes.get(argv[-1],0);return (0 if count else 1),b'%d\n'%count
        raise AssertionError(argv[0])
    def systemctl(self,args):
        assert args[0]=='show' and args[2::2]==['-p']*((len(args)-2)//2),args
        unit,wanted=args[1],args[3::2]
        values=self.units.get(unit,{'Id':unit,'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','UnitFileState':''})
        # systemd prints in its own property order, not in argument order.
        return 0,''.join('%s=%s\n'%(key,values[key]) for key in sorted(wanted,reverse=True) if key in values).encode()

REVISION='5e'*20
BACKEND_IMAGE='sha256:'+'fb'*32      # containerd-store style: a manifest digest, unrelated to any CI image ID
ROLLBACK_IMAGE='sha256:'+'fa'*32
WEB_IMAGE='sha256:'+'9c'*32
DATABASE_IMAGE='sha256:'+'d8'*32
DATA='/mnt/day-d-data'
APP='/opt/chief-of-staff-digital'
SECURITY=APP+'/runtime/security'
MAINTENANCE=SECURITY+'/maintenance'
RAW=DATA+'/provider=eodhd/microstructure/raw'
SOURCE_DIR=DATA+'/r2d2-v2-source'
CAPACITY='/var/lib/c3po-capacity'
RELEASE_NAME='r2d2-v2-release-epoch03'
CANARIES=(b'canary',b'NEVEREMIT',b'172.19.',b'02:42',b'postgresql://',b'never-emit',b'hc-ping')
def bind(source,destination,rw=True):
    return {'Type':'bind','Source':source,'Destination':destination,'Mode':'rw' if rw else 'ro','RW':rw,'Propagation':'rprivate'}
def volume(name,destination,rw=True):
    return {'Type':'volume','Name':name,'Source':'/var/lib/docker/volumes/'+name+'/_data','Destination':destination,
            'Driver':'local','Mode':'rw' if rw else 'ro','RW':rw,'Propagation':''}
BASE_ENV=['C3PO_MAINTENANCE_GATE_DIR=/run/c3po-maintenance','C3PO_BUILD_SHA='+REVISION,'C3PO_MIGRATIONS_DIR=/app/db',
          'C3PO_DATABASE_URL=postgresql://c3po:never-emit-this-canary@db:5432/c3po','MASSIVE_API_TOKEN=never-emit-token-canary',
          'EODHD_API_TOKEN=never-emit-provider-canary','PATH=/usr/local/bin:/usr/bin']
WORKER_ENV=BASE_ENV+['C3PO_R2D2_EXPERIMENT_CODE=R2D2-90D-001','C3PO_R2D2_MICROSTRUCTURE_RAW_DIR=/app/day-d-data/provider=eodhd/microstructure/raw',
                     'C3PO_SERVICE_NAME=r2d2-worker','TZ=America/Sao_Paulo']
def container(number,name,pid,*,project='c3po',service=None,image=BACKEND_IMAGE,reference='c3po/backend:production',mounts=(),
              networks=('c3po_c3po_internal',),health=None,oneoff='False',status='running',labels=True,env=None):
    state={'Status':status,'Running':status=='running','Paused':False,'Restarting':False,'Dead':False,'Pid':pid,'ExitCode':0,
           'StartedAt':'2026-10-02T22:21:03.321759952Z','FinishedAt':'0001-01-01T00:00:00Z'}
    if health:state['Health']={'Status':health,'FailingStreak':0}
    tags={'com.docker.compose.project':project,'com.docker.compose.service':service or name,'com.docker.compose.oneoff':oneoff,
          'com.docker.compose.container-number':'1','org.opencontainers.image.revision':REVISION} if labels else None
    return {'Id':('%02x'%number)*32,'Created':'2026-10-02T22:20:50Z','Path':'python','Name':'/'+name,'Image':image,'RestartCount':0,
            'Driver':'overlayfs','Platform':'linux','State':state,
            'Config':{'Hostname':'never-emit-hostname-canary','User':'','Image':reference,'Labels':tags,
                      'Env':list(BASE_ENV if env is None else env)},
            'HostConfig':{'NetworkMode':networks[0] if networks else 'none','UsernsMode':'','ReadonlyRootfs':False,'Init':None,'Binds':[]},
            'Mounts':list(mounts),
            'NetworkSettings':{'Networks':{name_:{'IPAddress':'172.19.0.%d'%number,'MacAddress':'02:42:ac:13:00:%02x'%number,
                                                   'Gateway':'172.19.0.1','NetworkID':NETWORK_IDS.get(name_,'d4'*32)} for name_ in networks}}}

def stack(capacity='placeholder'):
    """The compose stack after the deploy of the merged release: eight services, three containers of another stack."""
    maintenance=bind(MAINTENANCE,'/run/c3po-maintenance',False);legacy=bind(APP,'/legacy',False)
    pagers=volume('c3po_c3po_one_pagers','/app/generated-one-pagers');data=bind(DATA,'/app/day-d-data')
    slot={'placeholder':[volume('c3po_c3po_capacity_unprovisioned','/c3po-capacity',False)],'bind':[bind(CAPACITY,'/c3po-capacity',False)],
          'absent':[]}[capacity]
    both=('c3po_c3po_internal','chief-of-staff-digital_default')
    return [
        container(0x23,'chief-of-staff-digital-pluggy-webhook-1',1601,project='chief-of-staff-digital',service='pluggy-webhook',
                  image='sha256:'+'09'*32,reference='chief-of-staff-digital-pluggy-webhook',networks=('chief-of-staff-digital_default',)),
        container(0x25,'c3po-api-1',410243,service='api',mounts=[data,maintenance,legacy,pagers],networks=both),
        container(0x40,'c3po-db-1',409966,service='db',image=DATABASE_IMAGE,reference='c3po/database:production',health='healthy',
                  mounts=[volume('c3po_c3po_postgres','/var/lib/postgresql/data')],networks=('c3po_c3po_internal','c3po_db_loopback'),
                  env=['POSTGRES_PASSWORD=never-emit-db-canary','POSTGRES_USER=c3po']),
        container(0x46,'c3po-r2d2-worker-1',410227,service='r2d2-worker',mounts=[data,maintenance]+slot,networks=both,env=WORKER_ENV),
        container(0x7d,'c3po-web-1',410551,service='web',image=WEB_IMAGE,reference='c3po/web:production',networks=both,env=['NODE_ENV=production']),
        container(0x81,'c3po-investor-relations-worker-1',410298,service='investor-relations-worker',mounts=[maintenance,pagers],networks=both),
        container(0x85,'c3po-r2d2-shadow-candidate-worker-1',410291,service='r2d2-shadow-candidate-worker',mounts=[data,maintenance,legacy]),
        container(0xaf,'chief-of-staff-digital-cloudflared-1',1602,project='chief-of-staff-digital',service='cloudflared',
                  image='sha256:'+'0a'*32,reference='cloudflare/cloudflared:latest',networks=('chief-of-staff-digital_default',)),
        container(0xa8,'c3po-valuation-worker-1',410300,service='valuation-worker',mounts=[maintenance],networks=both),
        container(0xb0,'chief-of-staff-digital-caddy-1',0,project='chief-of-staff-digital',service='caddy',image='sha256:'+'5f'*32,
                  reference='caddy:2-alpine',status='exited',networks=('chief-of-staff-digital_default',)),
        container(0xc5,'c3po-server-usage-worker-1',410307,service='server-usage-worker',networks=both,
                  mounts=[maintenance,bind('/proc/stat','/host/proc/stat',False),bind(APP,'/host/disk',False)]),
    ]

def sealed_report(body):
    """The repository's seal: sha256 of the compact, key-sorted, not ASCII-escaped report without the seal member."""
    body=dict(body)
    body['report_sha256']=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return (json.dumps(body,sort_keys=True,indent=2)+'\n').encode()
POLICY=b'{\n  "schema": "C3PO_SECURITY_AUTOMATION_POLICY-v1",\n  "automatic_merge": true,\n  "automatic_reboot": true\n}\n'
def automation_report(**changes):
    body={'schema':'C3PO_SECURITY_AUTOMATION-v1','generated_at':(NOW-timedelta(minutes=50)).isoformat(),'alerts':[],'unresolved':[],
          'security_pending':0,'reboot_required':False,'deployed_sha':REVISION,'main_sha':REVISION,'errors':[],'escalation_errors':[],
          'status':'waiting_maintenance_window','automatic_reboot':True,'healthy':True,
          'reboot':{'state':'verified','containers':[{'name':'never-emit-container-canary'}]}}
    body.update(changes);return sealed_report(body)
def host_report(**changes):
    body={'schema':'C3PO_HOST_OS_VULNERABILITY_REPORT-v1','generated_at':(NOW-timedelta(minutes=7)).isoformat(),
          'updates':{'security_pending':0,'all_pending':3},'unattended_upgrades':{'healthcheck_configured':True,'automatic_reboot':False},
          'reboot_required':False,'reboot_packages':[],'kernel':'never-emit-kernel-canary'}
    body.update(changes);return sealed_report(body)

MOUNTINFO=(b'24 30 0:22 / /proc rw,nosuid,nodev,noexec,relatime shared:13 - proc proc rw\n'
           b'31 24 0:31 / /proc/sys/fs/binfmt_misc rw,relatime shared:14 - autofs systemd-1 rw,fd=29,pgrp=1,timeout=0,minproto=5,maxproto=5,direct\n'
           b'25 30 0:25 / /run rw,nosuid,nodev,noexec shared:5 - tmpfs tmpfs rw,size=796892k,mode=755\n'
           b'30 1 259:1 / / rw,relatime shared:1 - ext4 /dev/nvme0n1p1 rw,discard,errors=remount-ro\n'
           b'97 30 259:16 / /mnt/day-d-data rw,relatime shared:60 - ext4 /dev/nvme1n1 rw\n'
           b'410 30 0:60 / /var/lib/docker/rootfs/overlayfs/never\\040emit\\040canary rw,relatime shared:200 - overlay overlay rw,lowerdir=/never-emit-layer-canary\n')
UNIT_LOADED={'LoadState':'loaded','ActiveState':'active','SubState':'waiting','UnitFileState':'enabled'}
SIGNED_ROOT_NAMES=('.r2d2-v2-pinned','r2d2-v2-source','provider=eodhd')          # constants of the signed scope
SYNTHETIC_ROOT_NAME=re.compile(r'lost\+found|\.synthetic-[a-z.]+|provider=synthetic-[ab]|NEVEREMIT-[A-Z]+-[0-9]+'
                               r'|r2d2-v2-release-(diagnostic-)?0[0-9a-f]{11}(\.json)?|\.r2d2-v2-(trial|probe)-2025010[1-8](-r2|-syn[AB])?')
def entries_before():
    """A synthetic data volume root. No name here is the name of anything on a real host: apart from three constants of the
    signed scope and the generic lost+found, every name is made up (dates of January 2025, a NEVEREMIT or synthetic marker),
    and a test holds the fixture to that."""
    rows=[('.r2d2-v2-pinned','file',0,0o600),('lost+found','dir',0,0o700),('.synthetic-offload.lock','file',0,0o600),
          ('r2d2-v2-release-diagnostic-0a1b2c3d4e5f.json','file',0,0o600),('r2d2-v2-source','dir',0,0o700),
          ('provider=eodhd','dir',0,0o755),('provider=synthetic-a','dir',0,0o755),('provider=synthetic-b','dir',0,0o755)]
    rows+=[('r2d2-v2-release-%012x'%index,'dir',0,0o700) for index in range(3)]
    rows+=[('.r2d2-v2-trial-2025010%d'%index,'dir',0,0o700) for index in (1,2,3)]+[('.r2d2-v2-probe-20250104-r2','dir',0,0o700)]
    # two names the controller's pattern does not recognise (its veto clause): a suffix that is not -r<digits>
    rows+=[('.r2d2-v2-trial-20250107-synA','dir',0,0o700),('.r2d2-v2-probe-20250108-synB','dir',0,0o700)]
    rows+=[('NEVEREMIT-AAPL-%02d'%index,'dir',1000 if index%4==0 else 0,0o755 if index%3 else 0o700) for index in range(20)]
    return rows

def world(containers=None,*,provisioned=False,entries=None,shuffle=20261003):
    containers=stack('bind' if provisioned else 'placeholder') if containers is None else containers
    tree=Tree()
    for path in ('/etc/systemd/system','/var/lib/docker/volumes','/usr/local/bin','/usr/sbin','/usr/libexec','/proc','/mnt','/opt',
                 '/usr/local/lib/c3po-security','/usr/local/sbin'):tree.add(path)
    tree.add('/var/lib',ino=70001);tree.add('/mnt',ino=1700);tree.add('/run',dev=RUN_DEV,ino=1)
    tree.add('/var/run',kind='symlink',target='/run',mode=0o777)
    for name in ('docker','systemctl','pgrep','curl'):tree.add('/usr/bin/'+name,kind='file',mode=0o755,content=b'ELF')
    tree.add('/usr/share/update-notifier/notify-reboot-required',kind='file',mode=0o755,content=b'#!/bin/sh\n')
    tree.add('/usr/local/sbin/c3po-healthcheck-ping',kind='file',mode=0o755,content=b'#!/bin/sh\n')
    tree.add('/etc/systemd/system/apt-daily-upgrade.service.d/c3po-healthcheck.conf',kind='file',content=b'[Unit]\n')
    tree.add('/proc/4242/mountinfo',kind='file',mode=0o444,content=MOUNTINFO)
    tree.add('/proc/sys/kernel/osrelease',kind='file',mode=0o444,content=b'6.8.0-1013-aws\n')
    tree.add('/proc/stat',kind='file',mode=0o444,content=b'cpu 1 2 3\n')
    tree.add(APP,uid=1000,gid=1000);tree.add(APP+'/.deploy-version',kind='file',uid=1000,gid=1000,content=REVISION.encode()+b'\n')
    tree.add(MAINTENANCE,mode=0o755)
    tree.add(SECURITY+'/security-automation-report.json',kind='file',content=automation_report())
    tree.add(SECURITY+'/host-os-vulnerability-report.json',kind='file',content=host_report())
    tree.add(SECURITY+'/security-reboot-state.json',kind='file',mode=0o600,content=b'{"boot_id":"never-emit-boot-canary"}')
    tree.add('/etc/c3po',mode=0o700);tree.add('/etc/c3po/security-automation.json',kind='file',content=POLICY)
    tree.add('/etc/c3po/host-security.env',kind='file',mode=0o600,content=b'HEALTHCHECK_URL=https://hc-ping.invalid/never-emit-url-canary\n')
    for name in p.MODULES:tree.add('/usr/local/lib/c3po-security/'+name,kind='file',content=('# synthetic '+name+'\n').encode())
    tree.add(DATA,uid=1000,gid=1000,dev=DATA_DEV,ino=2)          # the volume root is 1000:1000 0755 on its own device
    for name,kind,uid,mode in (entries_before() if entries is None else entries):tree.add(DATA+'/'+name,kind=kind,uid=uid,gid=uid,mode=mode)
    tree.add(DATA+'/provider=eodhd/microstructure');tree.add(RAW)
    for day in ('2026-09-28','2026-09-29','2026-09-30','2026-10-01','2026-10-02'):
        tree.add(RAW+'/session_date='+day)
        for index in range(4):tree.add(RAW+'/session_date=%s/feed=%s-part-%05d.ndjson'%(day,'quote' if index%2 else 'trade',index),kind='file',mode=0o644)
    tree.add(SOURCE_DIR,mode=0o700);tree.add(SOURCE_DIR+'/snapshot.json',kind='file',mode=0o600,content=b'{"symbol":"NEVEREMIT-SNAPSHOT"}')
    tree.add(SOURCE_DIR+'/events',mode=0o700);tree.add(SOURCE_DIR+'/causal_list',mode=0o700)
    for index in range(40):tree.add(SOURCE_DIR+'/events/NEVEREMIT-MSFT-%03d.%s.json'%(index,'ab'*32),kind='file',mode=0o600)
    tree.add(SOURCE_DIR+'/causal_list/R2D2-V2-SHADOW-2026-09-28',mode=0o700)
    tree.add(SOURCE_DIR+'/causal_list/R2D2-V2-SHADOW-2026-09-28/2026-09-28.json',kind='file',mode=0o600)
    images=[{'Id':BACKEND_IMAGE,'RepoTags':['c3po/backend:production','never-emit-tag-canary:latest'],'Created':'x','Architecture':'arm64','Os':'linux','Size':1,
             'Config':{'Labels':{'org.opencontainers.image.revision':REVISION},'Env':['IMAGE_ENV=never-emit-image-canary']}},
            {'Id':ROLLBACK_IMAGE,'RepoTags':['c3po/backend:rollback'],'Config':{'Labels':{'org.opencontainers.image.revision':'4d'*20}}},
            {'Id':WEB_IMAGE,'RepoTags':['c3po/web:production'],'Config':{'Labels':{'org.opencontainers.image.revision':REVISION}}},
            {'Id':DATABASE_IMAGE,'RepoTags':['c3po/database:production'],'Config':{'Labels':None}}]
    network={'Created':'2026-08-01T00:00:00Z','Scope':'local','Driver':'bridge','EnableIPv4':True,'EnableIPv6':False,
             'IPAM':{'Driver':'default','Config':[{'Subnet':'172.19.0.0/16','Gateway':'172.19.0.1'}]},'Internal':True,'Attachable':False,
             'Ingress':False,'Options':{},'Labels':{'com.docker.compose.network':'c3po_internal'}}
    docker=FakeDocker(containers,images,{'Client':{'Version':'29.9.9'},'Server':{'Version':'29.9.9'}},
                      {'c3po_c3po_internal':network,'never-emit-network-canary':dict(network)})
    docker.shuffle=random.Random(shuffle) if shuffle is not None else None
    statvfs=lambda blocks,free,available:types.SimpleNamespace(f_frsize=4096,f_blocks=blocks,f_bfree=free,f_bavail=available,f_files=6553600,
                                                               f_favail=6000000,f_flag=4096)
    vfs={DATA_DEV:statvfs(25600000,14500000,13200000),ROOT_DEV:statvfs(162000000,145004096,145000000),RUN_DEV:statvfs(199223,199000,199000)}
    host=FakeHost(tree,docker,vfs)
    host.units['docker.service']={'Id':'docker.service','ActiveState':'active','SubState':'running','UnitFileState':'enabled'}
    for unit in ('c3po-security-daily.timer','c3po-security-watchdog.timer','c3po-host-security-snapshot.timer','apt-daily-upgrade.timer'):
        host.units[unit]=dict(UNIT_LOADED,Id=unit)
    host.units['c3po-unattended-upgrades-healthcheck-failure.service']={'Id':'c3po-unattended-upgrades-healthcheck-failure.service',
        'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','UnitFileState':'static'}
    if provisioned:provision(host)
    return host

def provision(host):
    """What the weekend operations leave behind: supervisor and reader layout, catalog, capacity tree, release and causal lists."""
    tree=host.tree;private=dict(mode=0o700)
    for path in ('/etc/c3po-bar','/etc/c3po-bar/manifests','/etc/c3po-bar/docker-cli','/var/lib/c3po-bar','/var/lib/c3po-bar/journal',
                 '/var/lib/c3po-bar/supervisor','/etc/c3po-reader','/etc/c3po-reader/docker-cli','/etc/c3po-reader/launcher',
                 '/var/lib/c3po-reader',CAPACITY,CAPACITY+'/config',CAPACITY+'/documents',CAPACITY+'/payload',CAPACITY+'/go',
                 CAPACITY+'/receipts',DATA+'/'+RELEASE_NAME):tree.add(path,**private)
    secret=dict(kind='file',mode=0o600)
    tree.add('/etc/c3po-bar/token',content=b'never-emit-token-canary\n',**secret)
    tree.add('/etc/c3po-reader/secret.env',content=b'C3PO_DATABASE_URL=postgresql://never-emit-this-canary\n',**secret)
    tree.add('/etc/c3po-reader/pins.env',content=b'C3PO_R2D2_V2_SHADOW_RELEASE_SHA=never-emit-pin-canary\n',**secret)
    tree.add('/etc/c3po-reader/launcher/reader_launcher.py',content=b'# launcher\n',**secret)
    tree.add('/var/lib/c3po-bar/journal/epoch.json',content=b'{}',**secret);tree.add('/var/lib/c3po-bar/journal/maintenance.lock',**secret)
    tree.add(DATA+'/'+RELEASE_NAME+'/release.json',content=b'{"symbols":["NEVEREMIT-RELEASE"]}',**secret)
    tree.add(SOURCE_DIR+'/causal_list/'+p.EPOCH,**private)
    tree.add(SOURCE_DIR+'/causal_list/'+p.EPOCH+'/2026-10-05.json',content=b'{"symbols":["NEVEREMIT-CAUSAL"]}',**secret)
    for name in p.UNIT_FILES:
        tree.add('/etc/systemd/system/'+name,kind='file',mode=0o644,content=b'[Unit]\n')
        host.units[name]={'Id':name,'LoadState':'loaded','ActiveState':'inactive','SubState':'dead',
                          'UnitFileState':'disabled' if name.endswith('.timer') else 'static'}
CANDIDATES={'release_directories':[RELEASE_NAME],'capacity_roots':[CAPACITY]}
ALLOWED_FILE_OPENS={'/proc/4242/mountinfo','/proc/sys/kernel/osrelease',APP+'/.deploy-version','/etc/c3po/security-automation.json',
                    SECURITY+'/security-automation-report.json',SECURITY+'/host-os-vulnerability-report.json'}|{
                    '/usr/local/lib/c3po-security/'+name for name in p.MODULES}


# ---------------------------------------------------------------- synthetic authority fixtures
@pytest.fixture
def bound(tmp_path):
    root=tmp_path.resolve();root.chmod(0o700)
    def put(name,raw):
        path=root/name;path.write_bytes(raw);path.chmod(0o600)
        return {'path':str(path),'sha256':p.sha(raw)}
    window={'not_before':NOW.isoformat(),'not_after':(NOW+timedelta(minutes=5)).isoformat()}
    request=json.loads((ROOT/'REQUEST.UNBOUND.json').read_bytes())
    request.update(status='BOUND',host_binding_sha256='1'*64,**window)
    request['collection'].update(status='BOUND',host_binding_sha256='1'*64,
        window={'not_before':window['not_before'],'expires_at':window['not_after']})
    authority=json.loads((ROOT/'AUTHORITY.UNBOUND.json').read_bytes())
    authority.update(status='SIGNED',decision='APPROVED',execution_authorized=True,
                     owner='SYNTHETIC_NEVER_AUTHORITATIVE',host_binding_sha256='1'*64,**window)
    go=json.loads((ROOT/'GO.UNBOUND.json').read_bytes())
    go.update(status='SIGNED',action='GO',execution_authorized=True,
              owner=authority['owner'],host_binding_sha256='1'*64,**window)
    config=json.loads((ROOT/'DISPATCH.UNBOUND.json').read_bytes())
    config.update(status='BOUND',decision='GO',owner=authority['owner'],authorization_ref='SYNTHETIC_TEST_ONLY',
                  target='fixture@unused.invalid',host_binding_sha256='1'*64,
                  local_root_identity={'path':str(root),'device':root.stat().st_dev,'inode':root.stat().st_ino},
                  attempt_directory=str(root/'attempt'),latest_start=(NOW+timedelta(seconds=220)).isoformat(),**window)
    # These are plain synthetic strings in this private test directory, not keys.
    config['ssh_key']=put('synthetic-key',b'NOT_A_KEY_SYNTHETIC')
    config['known_hosts']=put('synthetic-hosts',b'NOT_HOSTS_SYNTHETIC')
    config['command_sha256']=t.command_pin(d.command(config))
    config['runtime_sha256']={n:p.sha((ROOT/n).read_bytes()) for n in config['runtime_sha256']}
    def save_docs():
        authority['request_sha256']=p.sha(p.canonical(request))
        go.update(request_sha256=authority['request_sha256'],authority_sha256=p.sha(p.canonical(authority)),
                  payload_sha256=p.sha(SOURCE),claim_root_identity=config['local_root_identity'],
                  transport_binding={k:config[k] for k in ('target','remote_command','command_sha256','runtime_sha256')})
        payload=l.build(SOURCE,p.canonical(request),p.canonical(authority),p.canonical(go),
                        expected_payload_sha256=p.sha(SOURCE),expected_request_sha256=p.sha(p.canonical(request)),
                        expected_authority_sha256=p.sha(p.canonical(authority)),expected_go_sha256=p.sha(p.canonical(go)))
        for key,raw in [('source',SOURCE),('request',p.canonical(request)),('authority',p.canonical(authority)),('go',p.canonical(go)),('payload',payload)]:
            config[key]=put(key,raw)
        return put('config',p.canonical(config))
    pin=save_docs()
    return root,request,authority,go,config,save_docs,pin,put

def authcall(bound,**extra):
    _,q,a,g,_,_,_,_=bound
    raw=[p.canonical(o) for o in (q,a,g)]
    pins=p.Pins(payload=p.sha(SOURCE),request=p.sha(raw[0]),authority=p.sha(raw[1]),go=p.sha(raw[2]))
    opts=dict(clock=lambda:NOW,monotonic=lambda:0,executor_uid=lambda:0)
    opts.update(extra)
    return p.observe(*raw,pins=pins,payload_bytes=SOURCE,**opts)

def facts(bound,host,**extra):
    return authcall(bound,collector=lambda request,gate:p.collect(request,gate,host=host),**extra)
def line(receipt):
    """Exactly what the stdin launcher writes."""
    return json.dumps(receipt,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
def never(*args,**kwargs):pytest.fail('transport or collector must not run')

def prep(bound):
    *_,pin,_=bound
    return d.execute(pin['path'],pin['sha256'],phase='prepare',clock=lambda:NOW,monotonic=lambda:0,transport=never)
def proof(bound,intent):
    root,q,a,g,c,save,pin,put=bound
    return put('publication',p.canonical({'schema':PUBLICATION,'status':'PUBLISHED',
        'owner':c['owner'],'publication_ref':'SYNTHETIC_TEST_ONLY','go_sha256':c['go']['sha256'],
        'config_sha256':pin['sha256'],'intent_sha256':intent['intent_sha256'],'published_at':NOW.isoformat()}))
def resume(bound,publication,transport):
    *_,pin,_=bound
    return d.execute(pin['path'],pin['sha256'],phase='resume',publication_path=publication['path'],
                     publication_sha256=publication['sha256'],clock=lambda:NOW,monotonic=lambda:0,transport=transport)
def fake(bound,out=None,status='KNOWN_PARTIAL'):
    c=bound[4]
    def run(payload,**kwargs):
        assert kwargs['authorize'](kwargs['payload_sha256'],kwargs['command_sha256']) is True
        receipt=p.canonical({'schema':RECEIPT,'request_sha256':c['request']['sha256'],
                             'go_sha256':c['go']['sha256'],'payload_sha256':c['source']['sha256']}) if out is None else out
        return {'status':status,'retry_allowed':False},receipt,b''
    return run
def rebind(bound):
    pin=bound[5]();mutable=list(bound);mutable[6]=pin;return mutable
def with_candidates(bound,candidates=None):
    bound[1]['collection']['candidates']=json.loads(json.dumps(CANDIDATES if candidates is None else candidates));return rebind(bound)
def hidden(value):
    if type(value) is dict:return value.get('status') not in (None,'COMPLETE') or any(hidden(item) for item in value.values())
    return type(value) is list and any(hidden(item) for item in value)
def observed(bound,host,**extra):
    receipt=facts(bound,host,**extra);o=receipt['observation']
    # invariants of every receipt: no failed part hides below a COMPLETE section, and the verdict is exactly "no problem"
    for name,section in o['sections'].items():assert section['status']!='COMPLETE' or not hidden(section),name
    assert (o['status']=='OBSERVED_COMPLETE')==(o['problems']==[] and not o['size_reductions'])==(receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW')
    assert all(re.fullmatch('[a-z_]+:[A-Z][A-Z0-9_]*',item) for item in o['problems']+o['findings']) and host.fds=={}
    return receipt,o,o['sections']


# ---------------------------------------------------------------- authority and once-dispatch tests (family, adapted)
def test_shipped_payload_is_exact_builder_bytes_and_unbound():
    names=['w1_preflight_readonly.py','REQUEST.UNBOUND.json','AUTHORITY.UNBOUND.json','GO.UNBOUND.json']
    raw=[(ROOT/n).read_bytes() for n in names]
    pins=p.Pins(payload=p.sha(raw[0]),request=p.sha(raw[1]),authority=p.sha(raw[2]),go=p.sha(raw[3]))
    assert l.build(*raw,expected_payload_sha256=pins.payload,expected_request_sha256=pins.request,
                   expected_authority_sha256=pins.authority,expected_go_sha256=pins.go)==(ROOT/'FINAL_PAYLOAD.UNBOUND.py').read_bytes()
    with pytest.raises(p.Refused,match='REQUEST_OR_EXECUTOR_UNBOUND'):
        p.observe(*raw[1:],pins=pins,payload_bytes=raw[0],collector=never)
    assert len(raw[1])<=l.MAX_DOCUMENT and len(raw[0])<=l.MAX_SOURCE          # the signed scope fits the launcher's document limit

def test_unbound_set_hash_chain_and_null_bindings():
    q,a,g,c,proof_=[json.loads((ROOT/(n+'.UNBOUND.json')).read_bytes()) for n in ('REQUEST','AUTHORITY','GO','DISPATCH','PUBLICATION_PROOF')]
    digest=lambda name:p.sha((ROOT/name).read_bytes())
    assert a['request_sha256']==g['request_sha256']==c['request']['sha256']==digest('REQUEST.UNBOUND.json')
    assert g['authority_sha256']==c['authority']['sha256']==digest('AUTHORITY.UNBOUND.json')
    assert g['payload_sha256']==q['payload_sha256']==c['source']['sha256']==p.sha(SOURCE)
    assert c['go']['sha256']==proof_['go_sha256']==digest('GO.UNBOUND.json') and proof_['config_sha256']==digest('DISPATCH.UNBOUND.json')
    assert c['payload']['sha256']==digest('FINAL_PAYLOAD.UNBOUND.py')
    assert g['transport_binding']['runtime_sha256']==c['runtime_sha256']=={n:digest(n) for n in ('dispatch_once.py','transport_once.py','launcher_stdin.py','w1_preflight_readonly.py')}
    assert c['runtime_sha256']['transport_once.py']==TRANSPORT_PIN and c['runtime_sha256']['launcher_stdin.py']==LAUNCHER_PIN
    assert q['scope_sha256']==p.SCOPE_SHA256 and p.canonical(q['collection']['scope'])==p.canonical(p.SCOPE)
    assert q['dates']==p.DATES==DATE_SET and len(DATE_SET)==9 and p.SCOPE['dates']==DATE_SET and q['collection']['candidates']=={'capacity_roots':[],'release_directories':[]}
    for document,keys in ((q,('host_binding_sha256','not_before','not_after')),(a,('owner','decision','host_binding_sha256','not_before','not_after')),
                          (g,('action','owner','host_binding_sha256','not_before','not_after')),
                          (c,('attempt_directory','authorization_ref','command_sha256','host_binding_sha256','latest_start','not_before','not_after','owner','target')),
                          (proof_,('intent_sha256','owner','publication_ref','published_at'))):
        assert all(document[key] is None for key in keys) and document['status']=='UNBOUND'
    assert g['claim_root_identity']==c['local_root_identity']=={'device':None,'inode':None,'path':None}
    assert c['ssh_key']==c['known_hosts']=={'path':None,'sha256':None} and g['transport_binding']['target'] is None
    assert q['collection']['window']=={'expires_at':None,'not_before':None} and a['execution_authorized'] is g['execution_authorized'] is False
    for name in ('REQUEST','AUTHORITY','GO','DISPATCH','PUBLICATION_PROOF'):
        raw=(ROOT/(name+'.UNBOUND.json')).read_bytes();assert raw==p.canonical(json.loads(raw)) and b'SIGNED' not in raw
        assert b'HOSTFACTS' not in raw and b'SUPERVISOR_PREFLIGHT' not in raw and b'POSTDEPLOY' not in raw

def test_authenticated_fixture_receipt_complete_and_hash(bound):
    seen=[]
    def collector(q,gate):gate();seen.append(True);return {'status':'OBSERVED_COMPLETE','sections':{}}
    result=authcall(bound,collector=collector)
    assert seen==[True] and result['status']=='METADATA_ONLY_REQUIRES_REVIEW' and result['schema']==RECEIPT
    assert result['ready'] is False and result['installation_authorized'] is False and result['activation_authorized'] is False
    assert result['w1_is_not_readiness'] is True and result['observation']['sections']['clock']['status']=='COMPLETE'
    pin=result.pop('metadata_sha256');assert p.sha(p.canonical(result))==pin

@pytest.mark.parametrize('document,local',[('authority','AUTHORITY_UNSIGNED'),('go','GO_UNSIGNED')])
def test_unsigned_documents_refused_locally_before_claim(bound,document,local):
    index=2 if document=='authority' else 3;bound[index]['status']='UNBOUND'
    with pytest.raises(p.Refused) as refusal:prep(rebind(bound))
    assert str(refusal.value)==local and not list(bound[0].glob('.go-*.claim'))

OLD=[('READONLY_POSTDEPLOY01_GO_V1','GO_READONLY_POSTDEPLOY_01',None,'INNER_AUTHORITY'),
     ('READONLY_SUPERVISOR_PREFLIGHT_GO_V1','GO_READONLY_SUPERVISOR_PREFLIGHT_01','READONLY_PREFLIGHT','INNER_AUTHORITY'),
     ('READONLY_SUPERVISOR_PREFLIGHT_GO_V1','GO_READONLY_SUPERVISOR_PREFLIGHT_STANDALONE_01','READONLY_PREFLIGHT','INNER_AUTHORITY'),
     ('READONLY_SUPERVISOR_HOSTFACTS_GO_V1','GO_READONLY_SUPERVISOR_HOSTFACTS_01','READONLY_HOSTFACTS','INNER_AUTHORITY'),
     ('READONLY_SUPERVISOR_HOSTFACTS_GO_V1','GO_READONLY_W1PREFLIGHT_01','READONLY_W1PREFLIGHT','INNER_AUTHORITY'),
     ('READONLY_W1PREFLIGHT01_GO_V1','GO_READONLY_SUPERVISOR_HOSTFACTS_01','READONLY_W1PREFLIGHT','GO_UNBOUND'),
     ('READONLY_W1PREFLIGHT01_GO_V1','GO_READONLY_SUPERVISOR_PREFLIGHT_STANDALONE_01','READONLY_W1PREFLIGHT','GO_UNBOUND'),
     ('READONLY_W1PREFLIGHT01_GO_V1','GO_READONLY_W1PREFLIGHT_01','READONLY_HOSTFACTS','READONLY_SCOPE'),
     ('READONLY_W1PREFLIGHT01_GO_V1','GO_READONLY_W1PREFLIGHT_01','READONLY_PREFLIGHT','READONLY_SCOPE')]
@pytest.mark.parametrize('schema,operation,phase,local',OLD)
def test_go_of_any_earlier_operation_refused_before_collection_and_before_claim(bound,schema,operation,phase,local):
    bound[3].update(schema=schema,operation=operation)
    if phase is None:bound[3].pop('phase')
    else:bound[3]['phase']=phase
    mutable=rebind(bound)
    with pytest.raises(p.Refused,match='GO_UNBOUND'):authcall(mutable,collector=never)
    with pytest.raises(p.Refused) as refusal:prep(mutable)
    assert str(refusal.value)==local and not list(bound[0].glob('.go-*.claim'))          # the dispatcher's own check, where it has one

@pytest.mark.parametrize('document,field,value,local',[('request','schema','READONLY_SUPERVISOR_PREFLIGHT_REQUEST_V1','INNER_AUTHORITY'),
    ('request','schema','READONLY_SUPERVISOR_HOSTFACTS_REQUEST_V1','INNER_AUTHORITY'),
    ('request','operation','GO_READONLY_SUPERVISOR_HOSTFACTS_01','INNER_AUTHORITY'),
    ('request','operation','GO_READONLY_SUPERVISOR_PREFLIGHT_STANDALONE_01','INNER_AUTHORITY'),
    ('authority','schema','READONLY_SUPERVISOR_HOSTFACTS_AUTHORITY_V1','INNER_AUTHORITY'),
    ('authority','schema','READONLY_SUPERVISOR_PREFLIGHT_AUTHORITY_V1','INNER_AUTHORITY'),
    ('authority','operation','GO_READONLY_SUPERVISOR_HOSTFACTS_01','INNER_AUTHORITY'),
    ('config','schema','SUPERVISOR_HOSTFACTS_DISPATCH_AUTHORIZATION_V1','DISPATCH_UNBOUND'),
    ('config','schema','SUPERVISOR_PREFLIGHT_DISPATCH_AUTHORIZATION_V1','DISPATCH_UNBOUND'),
    ('config','operation','GO_READONLY_SUPERVISOR_HOSTFACTS_01','DISPATCH_UNBOUND'),
    ('config','operation','GO_READONLY_SUPERVISOR_PREFLIGHT_STANDALONE_01','DISPATCH_UNBOUND'),('request','executor_uid',1000,'INNER_AUTHORITY')])
def test_earlier_request_authority_or_config_names_refused_before_claim(bound,document,field,value,local):
    bound[{'request':1,'authority':2,'config':4}[document]][field]=value
    with pytest.raises(p.Refused) as refusal:prep(rebind(bound))
    assert str(refusal.value)==local and not list(bound[0].glob('.go-*.claim'))

def test_wrong_effective_remote_uid_refused(bound):
    with pytest.raises(p.Refused,match='REQUEST_OR_EXECUTOR_UNBOUND'):authcall(bound,executor_uid=lambda:501,collector=never)

def test_expiration_retains_partial_without_further_collection(bound):
    clock=[NOW]
    def collector(q,gate):
        gate();clock[0]+=timedelta(minutes=6)
        return {'status':'PARTIAL_OR_WINDOW_EXPIRED','sections':{'one':{'status':'COMPLETE','exists':False}}}
    result=authcall(bound,clock=lambda:clock[0],collector=collector)
    assert result['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert 'one' in result['observation']['sections'] and result['ready'] is False

def test_prepare_does_not_spawn_then_resume_once(bound):
    prepared=prep(bound);assert prepared['status']=='AWAITING_PUBLICATION_NO_SPAWN'
    published=proof(bound,prepared)
    assert resume(bound,published,fake(bound))['status']=='KNOWN_PARTIAL'
    with pytest.raises(FileExistsError):resume(bound,published,never)
    with pytest.raises(FileExistsError):prep(bound)

def test_same_go_cannot_move_claim_root(bound,tmp_path):
    c=bound[4];other=tmp_path.resolve()/'other';other.mkdir(mode=0o700)
    c['local_root_identity']={'path':str(other),'device':other.stat().st_dev,'inode':other.stat().st_ino}
    c['attempt_directory']=str(other/'attempt')
    pin=bound[7]('config-other',p.canonical(c));mutable=list(bound);mutable[6]=pin
    with pytest.raises(p.Refused,match='GO_CLAIM_ROOT_BINDING'):prep(mutable)
    assert list(other.iterdir())==[]

def test_target_transplant_rejected_before_claim(bound):
    c=bound[4];c['target']='changed@unused.invalid';c['command_sha256']=t.command_pin(d.command(c))
    pin=bound[7]('config-changed',p.canonical(c));mutable=list(bound);mutable[6]=pin
    with pytest.raises(p.Refused,match='GO_TRANSPORT_BINDING'):prep(mutable)
    assert not list(bound[0].glob('.go-*.claim'))

def test_late_start_refused_before_claim(bound):
    pin=bound[6]
    with pytest.raises(p.Refused,match='WINDOW_WITH_WATCHDOG'):
        d.execute(pin['path'],pin['sha256'],clock=lambda:NOW+timedelta(seconds=221),monotonic=lambda:0,transport=never)
    assert not list(bound[0].glob('.go-*.claim'))

def test_bad_publication_refused_before_spawn_marker(bound):
    intent=prep(bound);published=proof(bound,intent)
    body=json.loads(Path(published['path']).read_bytes());body['intent_sha256']='0'*64
    changed=bound[7]('badpublication',p.canonical(body))
    with pytest.raises(p.Refused):resume(bound,changed,never)
    for earlier in ('SUPERVISOR_PREFLIGHT_INTENT_PUBLICATION_V1','SUPERVISOR_HOSTFACTS_INTENT_PUBLICATION_V1'):
        body=json.loads(Path(published['path']).read_bytes());body['schema']=earlier
        with pytest.raises(p.Refused,match='PUBLICATION_BINDINGS'):resume(bound,bound[7]('oldpublication',p.canonical(body)),never)
    assert not (Path(bound[4]['attempt_directory'])/'spawn.claim').exists()

def test_host_binding_mismatch_refused_before_collect(bound):
    bound[3]['host_binding_sha256']='2'*64
    with pytest.raises(p.Refused,match='HOST_BINDING'):authcall(bound,collector=never)

def shift(bound,start,end):
    _,q,a,g,c,_,_,_=bound
    for document in (q,a,g,c):document.update(not_before=start.isoformat(),not_after=end.isoformat())
    q['collection']['window']={'not_before':start.isoformat(),'expires_at':end.isoformat()}
    c['latest_start']=(end-timedelta(seconds=80)).isoformat()
    return rebind(bound)
def test_date_scope_is_one_of_the_nine_signed_utc_dates_and_never_two_of_them(bound):
    friday=datetime(2026,10,2,22,tzinfo=timezone.utc);mutable=shift(bound,friday,friday+timedelta(minutes=5))      # Friday 19:00 BRT
    assert d.execute(mutable[6]['path'],mutable[6]['sha256'],clock=lambda:friday,monotonic=lambda:0,transport=never)['status']=='AWAITING_PUBLICATION_NO_SPAWN'
    assert authcall(mutable,clock=lambda:friday,collector=lambda q,gate:{'status':'OBSERVED_COMPLETE','sections':{}})['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    for day in DATE_SET:          # the source accepts a window on each date of the set (the dispatcher: the whole-day test below)
        noon=p.instant(day+'T12:00:00Z');mutable=shift(bound,noon,noon+timedelta(minutes=5))
        assert authcall(mutable,clock=lambda:noon,collector=lambda q,gate:{'status':'OBSERVED_COMPLETE','sections':{}})['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    for moment in (datetime(2026,10,1,17,tzinfo=timezone.utc),datetime(2026,10,11,1,tzinfo=timezone.utc),datetime(2026,11,2,13,tzinfo=timezone.utc),
                   datetime(2025,10,3,13,tzinfo=timezone.utc)):          # the day before, the day after, the same day of another month and year
        mutable=shift(bound,moment,moment+timedelta(minutes=5))
        with pytest.raises(p.Refused,match='DISPATCH_DATE'):
            d.execute(mutable[6]['path'],mutable[6]['sha256'],clock=lambda:moment,monotonic=lambda:0,transport=never)
        with pytest.raises(p.Refused,match='DATE_WINDOW_MISMATCH'):authcall(mutable,clock=lambda:moment,collector=never)
    for day in DATE_SET:          # a window that crosses midnight UTC lies on two dates: refused, whether or not both are in the set
        late=p.instant(day+'T23:58:00Z');mutable=shift(bound,late,late+timedelta(minutes=5))
        with pytest.raises(p.Refused,match='DISPATCH_DATE'):
            d.execute(mutable[6]['path'],mutable[6]['sha256'],clock=lambda:late,monotonic=lambda:0,transport=never)
        with pytest.raises(p.Refused,match='DATE_WINDOW_MISMATCH'):authcall(mutable,clock=lambda:late,collector=never)
    assert len(list(bound[0].glob('.go-*.claim')))==1          # only the accepted Friday window prepared
    # the request names the whole set, in order: one date, the set of revision 2, a shorter, a longer or a reordered set are refused
    for value in ('2026-10-03',['2026-10-03'],['2026-10-02','2026-10-03'],DATE_SET[:-1],DATE_SET[1:],DATE_SET+['2026-10-11'],DATE_SET[::-1],None):
        bound[1]['dates']=value
        with pytest.raises(p.Refused,match='REQUEST_OR_EXECUTOR_UNBOUND'):authcall(shift(bound,NOW,NOW+timedelta(minutes=5)),collector=never)

def test_scope_is_fixed_by_the_source_and_checked_locally_before_claim(bound):
    bound[1]['collection']['scope']['data_destination']='/app/other'
    mutable=rebind(bound)
    with pytest.raises(p.Refused,match='SCOPE_MISMATCH'):authcall(mutable,collector=never)
    with pytest.raises(p.Refused,match='SCOPE_MISMATCH'):prep(mutable)
    bound[1]['collection']['scope']=json.loads(p.canonical(p.SCOPE));bound[1]['scope_sha256']='3'*64
    with pytest.raises(p.Refused,match='REQUEST_OR_EXECUTOR_UNBOUND'):prep(rebind(bound))
    bound[1]['scope_sha256']=p.SCOPE_SHA256;bound[1]['collection']['extra']=1
    with pytest.raises(p.Refused,match='COLLECTION_KEYS'):prep(rebind(bound))
    assert not list(bound[0].glob('.go-*.claim'))
    # the signed command table is the executed command table
    assert p.SCOPE['commands'] is p.COMMANDS and all(tool in p.BINARIES for tool,_,_ in p.COMMANDS.values())

@pytest.mark.parametrize('candidates',[None,[],{'release_directories':[]},{'release_directories':[],'capacity_roots':[],'extra':[]},
    {'release_directories':['a/b'],'capacity_roots':[]},{'release_directories':['..'],'capacity_roots':[]},
    {'release_directories':['with space'],'capacity_roots':[]},{'release_directories':['x','x'],'capacity_roots':[]},
    {'release_directories':['a','b','c','d','e'],'capacity_roots':[]},{'release_directories':[7],'capacity_roots':[]},
    {'release_directories':[['x']],'capacity_roots':[]},{'release_directories':'x','capacity_roots':[]},
    {'release_directories':[],'capacity_roots':['relative/path']},{'release_directories':[],'capacity_roots':['/']},
    {'release_directories':[],'capacity_roots':['/proc/1/root']},{'release_directories':[],'capacity_roots':['/var/lib/../etc']},
    {'release_directories':[],'capacity_roots':['/var/lib/x','/var/lib/x']},{'release_directories':[],'capacity_roots':['/a','/b','/c','/d']},
    {'release_directories':[],'capacity_roots':[None]},{'release_directories':[],'capacity_roots':['/var/lib/with space']}])
def test_malformed_candidates_are_refused_locally_before_claim_and_before_any_observation(bound,candidates):
    bound[1]['collection']['candidates']=candidates;mutable=rebind(bound)
    with pytest.raises(p.Refused,match='CANDIDATES_INVALID'):authcall(mutable,collector=never)
    with pytest.raises(p.Refused,match='CANDIDATES_INVALID'):prep(mutable)
    assert not list(bound[0].glob('.go-*.claim'))

def test_signed_candidates_are_accepted_and_never_copied_into_the_receipt(bound):
    mutable=with_candidates(bound);assert prep(mutable)['status']=='AWAITING_PUBLICATION_NO_SPAWN'
    receipt=facts(mutable,world(provisioned=True));raw=line(receipt)
    assert receipt['observation']['candidate_counts']=={'release_directories':1,'capacity_roots':1}
    assert RELEASE_NAME.encode() not in raw and CAPACITY.encode() not in raw

def test_dry_gate_stops_before_any_observation(bound):
    """The binding step validates with a gate that raises: nothing may be observed and the exception must surface."""
    class Dry(Exception):pass
    touched=[]
    class Untouchable:
        def __getattr__(self,name):touched.append(name);raise AssertionError('host touched: '+name)
    calls=[]
    def gate():calls.append(1);raise Dry()
    collection=json.loads(p.canonical(bound[1]['collection']))
    with pytest.raises(Dry):p.collect(collection,gate,host=Untouchable())
    assert touched==[] and calls==[1]          # the first gate call is outside every handler: one call, nothing touched
    with pytest.raises(Dry):p.collect(collection,gate)
    collection['max_seconds']=61
    with pytest.raises(p.Refused,match='LIMITS_INVALID'):p.collect(collection,never,host=Untouchable())
    assert touched==[] and calls==[1,1]

def test_receipt_over_64k_from_transport_is_uncertain_not_complete(bound):
    prepared=prep(bound);published=proof(bound,prepared);c=bound[4]
    big=p.canonical({'schema':RECEIPT,'request_sha256':c['request']['sha256'],
                     'go_sha256':c['go']['sha256'],'payload_sha256':c['source']['sha256'],'pad':'x'*65536})
    result=resume(bound,published,fake(bound,out=big,status='KNOWN_COMPLETE'))
    assert result['status']=='UNCERTAIN' and result['code']=='TRANSPORT_OR_RECEIPT_REFUSED'
    stored=json.loads((Path(c['attempt_directory'])/'exit.json').read_bytes());assert stored['status']=='UNCERTAIN'

@pytest.mark.parametrize('schema',['READONLY_SUPERVISOR_PREFLIGHT_RECEIPT_V1','READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1','READONLY_POSTDEPLOY01_RECEIPT_V1'])
def test_earlier_receipt_schema_refused_by_dispatcher(bound,schema):
    prepared=prep(bound);published=proof(bound,prepared);c=bound[4]
    old=p.canonical({'schema':schema,'request_sha256':c['request']['sha256'],
                     'go_sha256':c['go']['sha256'],'payload_sha256':c['source']['sha256']})
    assert resume(bound,published,fake(bound,out=old))['status']=='UNCERTAIN'

def test_cli_imports_sibling_modules_and_never_spawns_on_prepare(bound):
    """Runs the dispatcher as a script on synthetic documents. Outside the synthetic window it prints the fixed refusal; inside it
    it only prepares. Either way the exit status is 2 and no transport exists in the prepare phase."""
    import subprocess
    pin=bound[6]
    done=subprocess.run([sys.executable,'-B',str(ROOT/'dispatch_once.py'),'--config',pin['path'],'--config-sha256',pin['sha256'],'--phase','prepare'],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'},timeout=60)
    assert done.returncode==2 and done.stderr==b''
    assert json.loads(done.stdout)['status'] in ('REFUSED_OR_UNCERTAIN','AWAITING_PUBLICATION_NO_SPAWN')
    assert not (Path(bound[4]['attempt_directory'])/'spawn.claim').exists()

SOURCE_NAMES=[(1,'schema','READONLY_SUPERVISOR_PREFLIGHT_REQUEST_V1','REQUEST_OR_EXECUTOR_UNBOUND'),(1,'schema','READONLY_POSTDEPLOY01_REQUEST_V1','REQUEST_OR_EXECUTOR_UNBOUND'),
    (1,'schema','READONLY_SUPERVISOR_HOSTFACTS_REQUEST_V1','REQUEST_OR_EXECUTOR_UNBOUND'),(1,'operation','GO_READONLY_SUPERVISOR_HOSTFACTS_01','REQUEST_OR_EXECUTOR_UNBOUND'),
    (1,'operation','GO_READONLY_SUPERVISOR_PREFLIGHT_01','REQUEST_OR_EXECUTOR_UNBOUND'),(1,'operation','GO_READONLY_SUPERVISOR_PREFLIGHT_STANDALONE_01','REQUEST_OR_EXECUTOR_UNBOUND'),
    (1,'operation','GO_READONLY_POSTDEPLOY_01','REQUEST_OR_EXECUTOR_UNBOUND'),(1,'phase','READONLY_PREFLIGHT','REQUEST_OR_EXECUTOR_UNBOUND'),
    (1,'phase','READONLY_HOSTFACTS','REQUEST_OR_EXECUTOR_UNBOUND'),(1,'status','UNBOUND','REQUEST_OR_EXECUTOR_UNBOUND'),
    (1,'executor_uid',1000,'REQUEST_OR_EXECUTOR_UNBOUND'),(1,'executor_uid',False,'REQUEST_OR_EXECUTOR_UNBOUND'),(1,'executor_uid',0.0,'REQUEST_OR_EXECUTOR_UNBOUND'),
    (1,'executor_uid','0','REQUEST_OR_EXECUTOR_UNBOUND'),(1,'executor_uid',None,'REQUEST_OR_EXECUTOR_UNBOUND'),
    (1,'max_seconds',61,'REQUEST_SCOPE'),(1,'writes_allowed',True,'REQUEST_SCOPE'),(1,'activation_allowed',True,'REQUEST_SCOPE'),
    (2,'schema','READONLY_SUPERVISOR_PREFLIGHT_AUTHORITY_V1','AUTHORITY_UNBOUND'),(2,'schema','READONLY_POSTDEPLOY01_AUTHORITY_V1','AUTHORITY_UNBOUND'),
    (2,'schema','READONLY_SUPERVISOR_HOSTFACTS_AUTHORITY_V1','AUTHORITY_UNBOUND'),(2,'operation','GO_READONLY_SUPERVISOR_HOSTFACTS_01','AUTHORITY_UNBOUND'),
    (2,'operation','GO_READONLY_SUPERVISOR_PREFLIGHT_01','AUTHORITY_UNBOUND'),(2,'operation','GO_READONLY_SUPERVISOR_PREFLIGHT_STANDALONE_01','AUTHORITY_UNBOUND'),
    (2,'operation','GO_READONLY_POSTDEPLOY_01','AUTHORITY_UNBOUND'),(2,'status','UNBOUND','AUTHORITY_UNBOUND'),(2,'decision','REJECTED','AUTHORITY_UNBOUND'),
    (2,'execution_authorized',False,'AUTHORITY_UNBOUND'),(2,'writes_allowed',True,'AUTHORITY_UNBOUND'),(2,'activation_allowed',True,'AUTHORITY_UNBOUND'),
    (3,'schema','READONLY_SUPERVISOR_HOSTFACTS_GO_V1','GO_UNBOUND'),(3,'operation','GO_READONLY_SUPERVISOR_HOSTFACTS_01','GO_UNBOUND'),
    (3,'phase','READONLY_HOSTFACTS','GO_UNBOUND'),
    (3,'status','UNBOUND','GO_UNBOUND'),(3,'execution_authorized',False,'GO_UNBOUND'),(3,'action','NO_GO','GO_UNBOUND'),(3,'writes_allowed',True,'GO_UNBOUND'),
    (3,'activation_allowed',True,'GO_UNBOUND'),(3,'owner','SOMEONE_ELSE','OWNER_UNBOUND'),(3,'owner','UNBOUND','OWNER_UNBOUND')]
@pytest.mark.parametrize('document,field,value,code',SOURCE_NAMES)
def test_remote_source_alone_refuses_earlier_names_and_unbound_fields(bound,document,field,value,code):
    """Source level, not dispatcher level: the dispatcher's duplicate check must not be what refuses."""
    bound[document][field]=value
    with pytest.raises(p.Refused) as refusal:authcall(rebind(bound),collector=never)
    assert str(refusal.value)==code

@pytest.mark.parametrize('document,field,code',[(3,'request_sha256','GO_UNBOUND'),(3,'authority_sha256','GO_UNBOUND'),(3,'payload_sha256','GO_UNBOUND'),
                                                (2,'request_sha256','AUTHORITY_UNBOUND'),(1,'payload_sha256','REQUEST_OR_EXECUTOR_UNBOUND')])
def test_remote_source_hash_chain(bound,document,field,code):
    bound[document][field]='6'*64                       # raw: rebinding would repair the chain
    with pytest.raises(p.Refused) as refusal:authcall(bound,collector=never)
    assert str(refusal.value)==code

def test_remote_source_pins_window_and_collection_bindings(bound):
    _,q,a,g,_,_,_,_=bound;raw=[p.canonical(o) for o in (q,a,g)]
    good=dict(payload=p.sha(SOURCE),request=p.sha(raw[0]),authority=p.sha(raw[1]),go=p.sha(raw[2]))
    call=lambda pins,payload=SOURCE:p.observe(*raw,pins=pins,payload_bytes=payload,clock=lambda:NOW,monotonic=lambda:0,executor_uid=lambda:0,collector=never)
    for key in good:
        with pytest.raises(p.Refused,match='PIN_MISMATCH'):call(p.Pins(**dict(good,**{key:'5'*64})))
    with pytest.raises(p.Refused,match='PIN_MISMATCH'):call(p.Pins(**good),SOURCE+b'#')
    for delta in (timedelta(seconds=-1),timedelta(minutes=5),timedelta(days=1)):
        with pytest.raises(p.Refused,match='OUTSIDE_GO_WINDOW'):authcall(bound,clock=lambda:NOW+delta,collector=never)
    bound[2]['owner']='UNBOUND';bound[3]['owner']='UNBOUND'
    with pytest.raises(p.Refused,match='OWNER_UNBOUND'):authcall(rebind(bound),collector=never)
    bound[2]['owner']=bound[3]['owner']='SYNTHETIC_NEVER_AUTHORITATIVE'
    bound[1]['collection']['window']['expires_at']=(NOW+timedelta(minutes=4)).isoformat()
    with pytest.raises(p.Refused,match='COLLECTION_WINDOW'):authcall(rebind(bound),collector=never)
    bound[1]['collection']['window']['expires_at']=(NOW+timedelta(minutes=5)).isoformat();bound[1]['collection']['status']='UNBOUND'
    with pytest.raises(p.Refused,match='COLLECTION_UNBOUND'):authcall(rebind(bound),collector=never)

def test_gate_monotonic_deadline_and_clock_reversal(bound):
    """The codes are collected and asserted outside the collector: observe() would swallow an assertion raised inside it."""
    def code(gate):
        try:gate();return None
        except p.Refused as error:return str(error)
    done={'status':'OBSERVED_COMPLETE','sections':{}}
    mono=[0.0];seen=[]
    def deadline(q,gate):
        gate();mono[0]=59.9;seen.append(code(gate));mono[0]=60.0;seen.append(code(gate));return dict(done)
    assert authcall(bound,monotonic=lambda:mono[0],collector=deadline)['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert seen==[None,'GO_EXPIRED']
    wall=[NOW+timedelta(seconds=2)];seen=[]          # one second back, still inside the signed window
    def wall_back(q,gate):
        gate();wall[0]=NOW+timedelta(seconds=1);seen.append(code(gate));return dict(done)
    assert authcall(bound,clock=lambda:wall[0],collector=wall_back)['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert seen==['CLOCK_REVERSED']
    mono=[5.0];seen=[]
    def mono_back(q,gate):
        gate();mono[0]=4.0;seen.append(code(gate));return dict(done)
    assert authcall(bound,monotonic=lambda:mono[0],collector=mono_back)['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert seen==['CLOCK_REVERSED']

WORK=Path('/offline/optional-work')
STANDALONE=WORK/'supervisor-preflight-standalone-fable-20261001'/'bound';REV4=WORK/'postdeploy01-rev4-fable-20261001'/'bound'
HOSTFACTS=WORK/'hostfacts01-fable-20261002'/'bound'
REAL={'standalone':(STANDALONE/'REQUEST.BOUND.json',STANDALONE/'AUTHORITY.SIGNED.json',STANDALONE/'GO.SIGNED.json',STANDALONE/'preflight_readonly.py',STANDALONE/'DISPATCH.BOUND.json'),
      'postdeploy01_rev4':(REV4/'REQUEST.BOUND.json',REV4/'DUDU_POSTDEPLOY01_AUTHORITY_REV4.json',REV4/'DUDU_POSTDEPLOY01_GO_REV4.json',REV4/'disk_readonly.py',REV4/'DISPATCH.BOUND.json'),
      'hostfacts01':(HOSTFACTS/'REQUEST.BOUND.json',HOSTFACTS/'AUTHORITY.SIGNED.json',HOSTFACTS/'GO.SIGNED.json',HOSTFACTS/'hostfacts_readonly.py',HOSTFACTS/'DISPATCH.BOUND.json')}
INSIDE_OLD={'standalone':datetime(2026,10,1,18,tzinfo=timezone.utc),'postdeploy01_rev4':datetime(2026,10,1,18,tzinfo=timezone.utc),
            'hostfacts01':datetime(2026,10,2,1,51,tzinfo=timezone.utc)}          # inside each earlier signed window
def present(family):return pytest.mark.skipif(not all(path.is_file() for path in REAL[family]),reason='the signed documents of '+family+' are not on this machine')
FAMILIES=[pytest.param(family,marks=present(family)) for family in sorted(REAL)]

@pytest.mark.parametrize('family',FAMILIES)
def test_real_earlier_documents_are_refused_by_the_source_even_inside_their_own_window_as_uid_0(bound,family):
    """Bytes are read only to be refused; nothing from these files is copied into the candidate."""
    q,a,g,old_source,_=[path.read_bytes() for path in REAL[family]]
    for payload in (old_source,SOURCE):
        pins=p.Pins(payload=p.sha(payload),request=p.sha(q),authority=p.sha(a),go=p.sha(g))
        with pytest.raises(p.Refused,match='REQUEST_OR_EXECUTOR_UNBOUND'):
            p.observe(q,a,g,pins=pins,payload_bytes=payload,clock=lambda:INSIDE_OLD[family],monotonic=lambda:0,executor_uid=lambda:0,collector=never)
    expected={'request':'REQUEST_OR_EXECUTOR_UNBOUND','authority':'AUTHORITY_UNBOUND','go':'GO_UNBOUND'}
    for index,which in enumerate(('request','authority','go')):
        raw={'request':p.canonical(bound[1]),'authority':p.canonical(bound[2]),'go':p.canonical(bound[3])};raw[which]=REAL[family][index].read_bytes()
        pins=p.Pins(payload=p.sha(SOURCE),request=p.sha(raw['request']),authority=p.sha(raw['authority']),go=p.sha(raw['go']))
        with pytest.raises(p.Refused) as refusal:
            p.observe(raw['request'],raw['authority'],raw['go'],pins=pins,payload_bytes=SOURCE,clock=lambda:NOW,monotonic=lambda:0,executor_uid=lambda:0,collector=never)
        assert str(refusal.value)==expected[which]

@pytest.mark.parametrize('family',FAMILIES)
def test_real_earlier_config_is_refused_by_the_dispatcher_before_any_claim(bound,family):
    """The earlier config with its key and known-hosts references replaced by the synthetic files; no key file is opened."""
    root,_,_,_,c,_,_,put=bound
    old=json.loads(REAL[family][4].read_bytes())
    old.update(ssh_key=c['ssh_key'],known_hosts=c['known_hosts'],local_root_identity=c['local_root_identity'],attempt_directory=c['attempt_directory'])
    pin=put('old-config',p.canonical(old))
    with pytest.raises(p.Refused,match='DISPATCH_UNBOUND'):
        d.execute(pin['path'],pin['sha256'],phase='prepare',clock=lambda:INSIDE_OLD[family],monotonic=lambda:0,transport=never)
    for index,key in enumerate(('request','authority','go')):          # new config names around one real earlier document
        relabelled=json.loads(p.canonical(c));relabelled[key]=put('real-'+key,REAL[family][index].read_bytes())
        pin=put('relabel-'+key,p.canonical(relabelled))
        with pytest.raises(p.Refused):d.execute(pin['path'],pin['sha256'],phase='prepare',clock=lambda:NOW,monotonic=lambda:0,transport=never)
    assert not list(root.glob('.go-*.claim')) and not (root/'attempt').exists()

@present('hostfacts01')
def test_the_earlier_final_payload_and_the_earlier_dispatcher_cannot_carry_this_operation(bound):
    """The bytes executed on 2026-10-02 are read only to show that neither direction of a replay is possible."""
    old_dispatch=(HOSTFACTS/'dispatch_once.py').read_bytes();assert p.sha(old_dispatch)==REVIEWED_DISPATCH_PIN
    assert (HOSTFACTS/'launcher_stdin.py').read_bytes()==(ROOT/'launcher_stdin.py').read_bytes()
    assert (HOSTFACTS/'transport_once.py').read_bytes()==(ROOT/'transport_once.py').read_bytes()
    root,q,a,g,c,save,pin,put=bound
    changed=json.loads(p.canonical(c));changed['payload']=put('old-final',(HOSTFACTS/'FINAL_PAYLOAD.BOUND.py').read_bytes())
    other=put('config-old-final',p.canonical(changed))
    with pytest.raises(p.Refused,match='FINAL_BUNDLE_BYTES'):d.execute(other['path'],other['sha256'],phase='prepare',clock=lambda:NOW,monotonic=lambda:0,transport=never)
    for name in ('OPERATION','REQUEST_SCHEMA','AUTHORITY_SCHEMA','GO_SCHEMA','RECEIPT_SCHEMA','COLLECTION_SCHEMA','OBSERVATION_SCHEMA','PHASE'):
        assert getattr(p,name).encode() not in old_dispatch and getattr(p,name).encode() not in (HOSTFACTS/'hostfacts_readonly.py').read_bytes()
    assert not list(root.glob('.go-*.claim'))

def window(bound,start,end,clock,latest=None,watchdog=None):
    _,q,a,g,c,_,_,_=bound
    for document in (q,a,g,c):document.update(not_before=start,not_after=end)
    q['collection']['window']={'not_before':start,'expires_at':end}
    c['latest_start']=latest if latest is not None else (p.instant(end)-timedelta(seconds=80)).isoformat()
    if watchdog is not None:c['watchdog_seconds']=watchdog
    mutable=rebind(bound)
    return d.execute(mutable[6]['path'],mutable[6]['sha256'],phase='prepare',clock=lambda:clock,monotonic=lambda:0,transport=never)
def utc(*parts):return datetime(*parts,tzinfo=timezone.utc)
def whole(day):return (day+'T00:00:00Z',day+'T23:59:59Z')
DAY=whole('2026-10-03');FRIDAY=whole('2026-10-02');LAST=whole('2026-10-10')

# every date of the set, at the first and at the last instant at which a whole-day window still admits a start
@pytest.mark.parametrize('day,clock',[(whole(day),p.instant(day+moment)) for day in DATE_SET for moment in ('T00:00:00Z','T23:58:39Z')])
def test_whole_utc_day_window_first_and_last_admissible_start(bound,day,clock):
    assert window(bound,day[0],day[1],clock)['status']=='AWAITING_PUBLICATION_NO_SPAWN'

@pytest.mark.parametrize('start,end,clock,code',[
    ('2026-10-03T00:00:00Z','2026-10-04T00:00:00Z',utc(2026,10,3,12),'DISPATCH_DATE'),
    ('2026-10-02T23:59:59Z','2026-10-03T12:00:00Z',utc(2026,10,3,1),'DISPATCH_DATE'),
    ('2026-10-02T00:00:00Z','2026-10-03T00:00:00Z',utc(2026,10,2,12),'DISPATCH_DATE'),
    ('2026-10-11T00:00:00Z','2026-10-11T12:00:00Z',utc(2026,10,11,1),'DISPATCH_DATE'),
    ('2026-10-10T00:00:00Z','2026-10-11T00:00:00Z',utc(2026,10,10,12),'DISPATCH_DATE'),
    ('2026-10-09T23:59:59Z','2026-10-10T12:00:00Z',utc(2026,10,10,1),'DISPATCH_DATE'),
    ('2026-10-04T00:00:00Z','2026-10-05T00:00:00Z',utc(2026,10,4,12),'DISPATCH_DATE'),
    ('2026-11-02T10:00:00Z','2026-11-02T12:00:00Z',utc(2026,11,2,11),'DISPATCH_DATE'),
    ('2025-10-03T10:00:00Z','2025-10-03T12:00:00Z',utc(2025,10,3,11),'DISPATCH_DATE'),
    (LAST[0],LAST[1],utc(2026,10,11,0,0,0),'DISPATCH_WINDOW'),(LAST[0],LAST[1],utc(2026,10,10,23,58,40),'WINDOW_WITH_WATCHDOG'),
    ('2026-10-01T17:00:00Z','2026-10-01T21:00:00Z',utc(2026,10,1,18),'DISPATCH_DATE'),
    ('2026-10-03T00:30:00+01:00','2026-10-03T12:00:00+00:00',utc(2026,10,3,1),'WINDOW_NOT_UTC'),
    ('2026-10-03T21:00:00-03:00','2026-10-03T23:00:00-03:00',utc(2026,10,4,1),'WINDOW_NOT_UTC'),
    ('2026-10-03T17:00:00','2026-10-03T18:00:00',utc(2026,10,3,17,1),'WINDOW_NOT_UTC'),
    (DAY[0],DAY[1],utc(2026,10,2,23,59,59),'DISPATCH_WINDOW'),(DAY[0],DAY[1],utc(2026,10,3,23,59,59),'DISPATCH_WINDOW'),
    (DAY[0],DAY[1],utc(2026,10,4,0,0,1),'DISPATCH_WINDOW'),(DAY[0],DAY[1],utc(2026,10,3,23,58,40),'WINDOW_WITH_WATCHDOG'),
    (FRIDAY[0],FRIDAY[1],utc(2026,10,3,0,0,0),'DISPATCH_WINDOW'),
    ('2026-10-03T17:00:00Z','2026-10-03T17:01:00Z',utc(2026,10,3,17),'LATEST_START_BINDING')])
def test_dispatcher_window_boundaries(bound,start,end,clock,code):
    with pytest.raises(p.Refused) as refusal:window(bound,start,end,clock)
    assert str(refusal.value)==code and not list(bound[0].glob('.go-*.claim'))

@pytest.mark.parametrize('latest,watchdog,code',[('2026-10-03T13:03:41+00:00',None,'LATEST_START_BINDING'),('2026-10-03T13:03:39+00:00',None,'LATEST_START_BINDING'),
    ('2026-10-03T13:05:00+00:00',None,'LATEST_START_BINDING'),('2026-10-03T13:03:41+00:00',79,'PREFLIGHT_BUDGET'),('2026-10-03T13:03:30+00:00',90,'PREFLIGHT_BUDGET'),
    ('2026-10-03T13:03:29+00:00',91,'WATCHDOG_LIMIT'),(None,80.0,'WATCHDOG_LIMIT')])
def test_latest_start_and_budget_arithmetic(bound,latest,watchdog,code):
    with pytest.raises(p.Refused) as refusal:window(bound,NOW.isoformat(),(NOW+timedelta(minutes=5)).isoformat(),NOW,latest=latest,watchdog=watchdog)
    assert str(refusal.value)==code and not list(bound[0].glob('.go-*.claim'))

@pytest.mark.parametrize('field,value,code',[('executor_uid',1000,'REMOTE_UID'),('executor_uid',True,'REMOTE_UID'),('single_use',False,'DISPATCH_UNBOUND'),
    ('retry',True,'DISPATCH_UNBOUND'),('status','UNBOUND','DISPATCH_UNBOUND'),('decision','UNBOUND','DISPATCH_UNBOUND'),('owner','UNBOUND','DISPATCH_AUTHORITY'),
    ('authorization_ref','UNBOUND','DISPATCH_AUTHORITY'),('host_binding_sha256','7'*64,'HOST_BINDING'),('finalize_local_receipts_after_window',False,'LOCAL_FINALIZATION_AUTHORITY'),
    ('remote_command','sudo -n /usr/bin/python3 -','REMOTE_COMMAND'),('command_sha256','a'*64,'COMMAND_PIN'),('owner','SOMEONE_ELSE','INNER_AUTHORITY')])
def test_dispatcher_config_fields(bound,field,value,code):
    bound[4][field]=value
    with pytest.raises(p.Refused) as refusal:prep(rebind(bound))
    assert str(refusal.value)==code and not list(bound[0].glob('.go-*.claim'))

def test_dispatcher_inner_window_runtime_pins_and_final_bytes(bound):
    root,q,a,g,c,save,pin,put=bound
    changed=json.loads(p.canonical(c));changed['runtime_sha256']['w1_preflight_readonly.py']='8'*64
    other=put('config-runtime',p.canonical(changed))
    with pytest.raises(p.Refused,match='LOCAL_PIN'):d.execute(other['path'],other['sha256'],phase='prepare',clock=lambda:NOW,monotonic=lambda:0,transport=never)
    changed=json.loads(p.canonical(c));changed['runtime_sha256']['hostfacts_readonly.py']=changed['runtime_sha256'].pop('w1_preflight_readonly.py')
    other=put('config-old-module',p.canonical(changed))
    with pytest.raises(p.Refused,match='RUNTIME_PINS_UNBOUND'):d.execute(other['path'],other['sha256'],phase='prepare',clock=lambda:NOW,monotonic=lambda:0,transport=never)
    changed=json.loads(p.canonical(c));changed['payload']=put('payload-changed',Path(c['payload']['path']).read_bytes()+b'\n#x\n')
    other=put('config-payload',p.canonical(changed))
    with pytest.raises(p.Refused,match='FINAL_BUNDLE_BYTES'):d.execute(other['path'],other['sha256'],phase='prepare',clock=lambda:NOW,monotonic=lambda:0,transport=never)
    for field in ('request_sha256','authority_sha256','payload_sha256'):          # the dispatcher's own chain check, before the source's
        broken=json.loads(p.canonical(g));broken[field]='6'*64
        changed=json.loads(p.canonical(c));changed['go']=put('go-'+field,p.canonical(broken));other=put('config-'+field,p.canonical(changed))
        with pytest.raises(p.Refused,match='INNER_BINDINGS'):d.execute(other['path'],other['sha256'],phase='prepare',clock=lambda:NOW,monotonic=lambda:0,transport=never)
    c['not_before']=(NOW-timedelta(minutes=1)).isoformat()
    with pytest.raises(p.Refused,match='INNER_WINDOW'):prep(rebind(bound))
    assert not list(root.glob('.go-*.claim'))

def test_single_use_is_per_go_not_per_attempt_directory(bound):
    root,q,a,g,c,save,pin,put=bound
    assert prep(bound)['status']=='AWAITING_PUBLICATION_NO_SPAWN'
    second=json.loads(p.canonical(c));second.update(attempt_directory=str(root/'attempt-two'),authorization_ref='SYNTHETIC_SECOND')
    other=put('config-two',p.canonical(second))
    with pytest.raises(FileExistsError):d.execute(other['path'],other['sha256'],phase='prepare',clock=lambda:NOW,monotonic=lambda:0,transport=never)
    assert not (root/'attempt-two').exists()
    published=put('publication-two',p.canonical({'schema':PUBLICATION,'status':'PUBLISHED','owner':c['owner'],
        'publication_ref':'SYNTHETIC','go_sha256':c['go']['sha256'],'config_sha256':other['sha256'],'intent_sha256':'4'*64,'published_at':NOW.isoformat()}))
    with pytest.raises(p.Refused,match='LOCAL_PIN'):          # the stored claim names the first config
        d.execute(other['path'],other['sha256'],phase='resume',publication_path=published['path'],publication_sha256=published['sha256'],
                  clock=lambda:NOW,monotonic=lambda:0,transport=never)
    assert not (root/'attempt-two').exists()

def test_resume_without_prepare_and_remote_refusal_spends_the_go(bound):
    root,q,a,g,c,save,pin,put=bound
    orphan=put('publication-orphan',p.canonical({'schema':PUBLICATION,'status':'PUBLISHED','owner':c['owner'],
        'publication_ref':'SYNTHETIC','go_sha256':c['go']['sha256'],'config_sha256':pin['sha256'],'intent_sha256':'4'*64,'published_at':NOW.isoformat()}))
    with pytest.raises(FileNotFoundError):resume(bound,orphan,never)
    assert not list(root.glob('.go-*.claim'))
    prepared=prep(bound);published=proof(bound,prepared)
    def refusing(payload,**kwargs):
        assert kwargs['authorize'](kwargs['payload_sha256'],kwargs['command_sha256']) is True
        return {'status':'KNOWN_REFUSAL','retry_allowed':False},b'{"status":"REFUSED"}\n',b''
    assert resume(bound,published,refusing)['status']=='KNOWN_REFUSAL'
    with pytest.raises(FileExistsError):resume(bound,published,never)
    with pytest.raises(FileExistsError):prep(bound)

def test_publication_order_late_resume_and_receipt_bindings(bound):
    prepared=prep(bound);published=proof(bound,prepared);pin=bound[6];c=bound[4]
    body=json.loads(Path(published['path']).read_bytes());body['published_at']=(NOW-timedelta(seconds=1)).isoformat()
    with pytest.raises(p.Refused,match='INTENT_PUBLICATION_ORDER'):resume(bound,bound[7]('early',p.canonical(body)),never)
    with pytest.raises(p.Refused,match='WINDOW_WITH_WATCHDOG'):
        d.execute(pin['path'],pin['sha256'],phase='resume',publication_path=published['path'],publication_sha256=published['sha256'],
                  clock=lambda:NOW+timedelta(seconds=221),monotonic=lambda:0,transport=never)
    assert not (Path(c['attempt_directory'])/'spawn.claim').exists()
    other=p.canonical({'schema':RECEIPT,'request_sha256':c['request']['sha256'],'go_sha256':'9'*64,'payload_sha256':c['source']['sha256']})
    assert resume(bound,published,fake(bound,out=other))['status']=='UNCERTAIN'

@pytest.mark.parametrize('field,value',[('request_sha256','9'*64),('payload_sha256','9'*64),('go_sha256','9'*64),('schema','READONLY_SUPERVISOR_HOSTFACTS_RECEIPT_V1'),
                                        ('request_sha256',None),('payload_sha256',None)])
def test_receipt_bindings_to_request_payload_go_and_schema_are_each_enforced(bound,field,value):
    prepared=prep(bound);published=proof(bound,prepared);c=bound[4]
    body={'schema':RECEIPT,'request_sha256':c['request']['sha256'],'go_sha256':c['go']['sha256'],'payload_sha256':c['source']['sha256']};body[field]=value
    if value is None:body.pop(field)
    result=resume(bound,published,fake(bound,out=p.canonical(body),status='KNOWN_COMPLETE'))
    assert result['status']=='UNCERTAIN' and result['code']=='TRANSPORT_OR_RECEIPT_REFUSED'
    stored=json.loads((Path(c['attempt_directory'])/'exit.json').read_bytes());assert stored['status']=='UNCERTAIN'

def test_dispatcher_refuses_an_earlier_operation_named_alike_in_request_and_authority(bound):
    for index in (1,2):bound[index]['operation']='GO_READONLY_SUPERVISOR_HOSTFACTS_01'
    with pytest.raises(p.Refused) as refusal:prep(rebind(bound))
    assert str(refusal.value)=='INNER_AUTHORITY' and not list(bound[0].glob('.go-*.claim'))          # the dispatcher's own check, not the source's

def test_the_claim_and_the_intent_carry_the_names_of_this_operation_and_no_other_intent_is_accepted(bound):
    root=bound[0];c=bound[4];prepared=prep(bound);claims=list(root.glob('.go-*.claim'))
    assert len(claims)==1 and json.loads(claims[0].read_bytes())=={'schema':'W1PREFLIGHT01_GO_CLAIM_V1','go_sha256':c['go']['sha256'],'config_sha256':bound[6]['sha256']}
    path=Path(c['attempt_directory'])/'intent.json';body=json.loads(path.read_bytes())
    assert body['schema']=='W1PREFLIGHT01_DISPATCH_INTENT_V1' and p.sha(path.read_bytes())==prepared['intent_sha256']
    # an intent of the earlier family in its place, published under its own hash, is refused before any spawn marker
    body['schema']='SUPERVISOR_HOSTFACTS_DISPATCH_INTENT_V1';raw=p.canonical(body);path.write_bytes(raw)
    with pytest.raises(p.Refused,match='INTENT_PUBLICATION_ORDER'):resume(bound,proof(bound,{'intent_sha256':p.sha(raw)}),never)
    assert not (Path(c['attempt_directory'])/'spawn.claim').exists()

def test_start_after_latest_start_is_refused_inside_authorize(bound):
    prepared=prep(bound);published=proof(bound,prepared);pin=bound[6];ticks=[NOW];seen=[]
    def transport(payload,**kwargs):          # the dispatcher swallows what is raised here, so the code is recorded
        ticks[0]=NOW+timedelta(seconds=221)
        try:kwargs['authorize'](kwargs['payload_sha256'],kwargs['command_sha256']);seen.append('AUTHORIZED')
        except p.Refused as error:seen.append(str(error));raise
        return {'status':'KNOWN_REFUSAL','retry_allowed':False},b'',b''
    out=d.execute(pin['path'],pin['sha256'],phase='resume',publication_path=published['path'],publication_sha256=published['sha256'],
                  clock=lambda:ticks[0],monotonic=lambda:0,transport=transport)
    assert seen==['WINDOW_WITH_WATCHDOG'] and out['status']=='UNCERTAIN' and out['code']=='TRANSPORT_OR_RECEIPT_REFUSED'

@pytest.mark.parametrize('status,code',[('KNOWN_COMPLETE',0),('KNOWN_PARTIAL',2),('AWAITING_PUBLICATION_NO_SPAWN',2),('UNCERTAIN',2),('KNOWN_REFUSAL',2)])
def test_cli_exit_status_is_zero_only_for_known_complete(monkeypatch,capsys,status,code):
    monkeypatch.setattr(d,'execute',lambda *args,**kwargs:{'status':status})
    monkeypatch.setattr(sys,'argv',['dispatch_once.py','--config','/unused','--config-sha256','0'*64])
    assert d.main()==code and json.loads(capsys.readouterr().out)=={'status':status}

def test_launcher_refuses_wrong_pins_at_build_and_on_stdin(bound):
    documents=[p.canonical(bound[index]) for index in (1,2,3)];receipt=facts(bound,world())
    standin=('import json\nclass Pins:\n    def __init__(self,**pins):self.pins=pins\n'
             'def observe(*documents,**options):return json.loads(%r)\n'%json.dumps(receipt)).encode()
    good=dict(expected_payload_sha256=p.sha(standin),expected_request_sha256=p.sha(documents[0]),
              expected_authority_sha256=p.sha(documents[1]),expected_go_sha256=p.sha(documents[2]))
    for key in good:
        with pytest.raises(ValueError,match='BUILD_PIN'):l.build(standin,*documents,**dict(good,**{key:'5'*64}))
    payload=l.build(standin,*documents,**good);command=[sys.executable,'-I','-B','-']
    def run(raw):
        result,out,err=t.once(raw,payload_sha256=p.sha(raw),command=command,command_sha256=t.command_pin(command),authorize=lambda a,b:True,seconds=30)
        assert err==b'';return result['status'],json.loads(out)
    assert run(payload)==('KNOWN_COMPLETE',receipt)
    for key,code in (('expected_payload_sha256','STDIN_SOURCE_PIN'),('expected_request_sha256','STDIN_DOCUMENT_PIN'),('expected_go_sha256','STDIN_DOCUMENT_PIN')):
        changed=payload.replace(good[key].encode(),b'5'*64);assert changed!=payload
        assert run(changed)==('KNOWN_REFUSAL',{'schema':REFUSAL,'status':'REFUSED','code':code,'source_mutation':False})


# ---------------------------------------------------------------- real transport bytes, real launcher bytes, local only
ECHO='import sys;data=sys.stdin.buffer.read();sys.stdout.buffer.write(data);raise SystemExit(%d)'
def broken_world():
    host=world();host.answers['version']=(1,b'');return host
@pytest.mark.parametrize('partial,code,expected',[(False,0,'KNOWN_COMPLETE'),(True,2,'KNOWN_PARTIAL'),(False,2,'UNCERTAIN'),(True,0,'UNCERTAIN')])
def test_reviewed_transport_accepts_the_sealed_receipt_and_the_exit_pairing(bound,partial,code,expected):
    assert p.sha((ROOT/'transport_once.py').read_bytes())==TRANSPORT_PIN
    payload=line(facts(bound,broken_world() if partial else world()));command=[sys.executable,'-I','-B','-c',ECHO%code]
    result,out,err=t.once(payload,payload_sha256=p.sha(payload),command=command,command_sha256=t.command_pin(command),
                          authorize=lambda a,b:True,seconds=30)
    assert result['status']==expected and out==payload and err==b''
    if expected!='UNCERTAIN':assert len(out)<=65536 and d.decode(out)['schema']==RECEIPT

@pytest.mark.skipif(os.geteuid()==0,reason='as root the payload would start observing this machine')
def test_final_stdin_payload_runs_under_isolated_python_and_refuses_as_non_root(bound):
    payload=Path(bound[4]['payload']['path']).read_bytes();command=[sys.executable,'-I','-B','-']
    result,out,err=t.once(payload,payload_sha256=p.sha(payload),command=command,command_sha256=t.command_pin(command),
                          authorize=lambda a,b:True,seconds=30)
    assert result['status']=='KNOWN_REFUSAL' and result['returncode']==1 and err==b''
    assert json.loads(out)=={'schema':REFUSAL,'status':'REFUSED','code':'REQUEST_OR_EXECUTOR_UNBOUND','source_mutation':False}

@pytest.mark.skipif(os.geteuid()==0,reason='as root the payload would start observing this machine')
def test_shipped_unbound_final_payload_refuses_under_the_system_python_with_an_empty_stderr():
    """The file that would be sent, byte for byte, run as python3 -I -B - by a non-root user: it compiles, imports and refuses."""
    payload=(ROOT/'FINAL_PAYLOAD.UNBOUND.py').read_bytes();command=['/usr/bin/python3','-I','-B','-']
    result,out,err=t.once(payload,payload_sha256=p.sha(payload),command=command,command_sha256=t.command_pin(command),
                          authorize=lambda a,b:True,seconds=30)
    assert result['status']=='KNOWN_REFUSAL' and err==b'' and json.loads(out)['code']=='REQUEST_OR_EXECUTOR_UNBOUND'

@pytest.mark.parametrize('partial,expected,code',[(False,'KNOWN_COMPLETE',0),(True,'KNOWN_PARTIAL',2)])
def test_launcher_body_maps_a_sealed_receipt_to_the_exit_code_the_transport_expects(bound,partial,expected,code):
    """Real launcher bytes and real transport bytes around a stand-in source that returns a receipt sealed by the real source."""
    receipt=facts(bound,broken_world() if partial else world())
    standin=('import json\nclass Pins:\n    def __init__(self,**pins):self.pins=pins\n'
             'def observe(*documents,**options):return json.loads(%r)\n'%json.dumps(receipt)).encode()
    documents=[p.canonical(bound[index]) for index in (1,2,3)]
    payload=l.build(standin,*documents,expected_payload_sha256=p.sha(standin),expected_request_sha256=p.sha(documents[0]),
                    expected_authority_sha256=p.sha(documents[1]),expected_go_sha256=p.sha(documents[2]))
    command=[sys.executable,'-I','-B','-']
    result,out,err=t.once(payload,payload_sha256=p.sha(payload),command=command,command_sha256=t.command_pin(command),
                          authorize=lambda a,b:True,seconds=30)
    assert result['status']==expected and result['returncode']==code and err==b'' and out==line(receipt)
    assert d.decode(out)['metadata_sha256']==receipt['metadata_sha256']

class LocalNative(p.Native):
    """The real Native on this machine, where O_NOATIME does not exist: the flag is replaced by zero for the smoke tests only."""
    def noatime(self):return 0
def test_native_runner_local_smoke(tmp_path,capfd):
    native=p.Native();gate=lambda:30.0
    assert native.run(['/bin/echo','hello'],gate,5)==(0,b'hello\n') and native.run(['/bin/echo','hello'],gate,5,False)==(0,b'')
    # what a child writes to its standard error goes nowhere: not into the answer, not into this process's own standard error
    assert native.run(['/bin/sh','-c','echo never-emit-stderr-canary >&2; echo out'],gate,5)==(0,b'out\n') and capfd.readouterr().err==''
    assert native.run(['/usr/bin/false'],gate,5)[0]==1
    # the output cap: a child that writes more than the limit is refused, whatever its exit status
    with pytest.raises(p.Refused,match='COMMAND_OUTPUT_LIMIT'):native.run(['/bin/dd','if=/dev/zero','bs=1024','count=%d'%(p.MAX_COMMAND_BYTES//1024+8)],gate,5)
    assert len(native.run(['/bin/dd','if=/dev/zero','bs=1024','count=%d'%(p.MAX_COMMAND_BYTES//1024)],gate,5)[1])==p.MAX_COMMAND_BYTES
    # a child that outlives its limit is killed, and nothing of it is left behind
    mark=tmp_path.parent/(tmp_path.name+'.child.pid')
    with pytest.raises(p.Refused,match='COMMAND_TIMEOUT'):native.run(['/bin/sh','-c','echo $$ > %s; exec /bin/sleep 30'%mark],gate,0.5,False)
    with pytest.raises(ProcessLookupError):os.kill(int(mark.read_text()),0)
    # the overall deadline of the context, on its own clock
    ctx=p.Context(native,gate);assert ctx.check()==30.0;ctx.started-=p.MAX_SECONDS
    with pytest.raises(p.Refused,match='DEADLINE'):ctx.check()
    with pytest.raises(p.Refused,match='COMMAND_TIMEOUT'):native.run(['/bin/sleep','5'],gate,0.3)
    with pytest.raises(p.Refused,match='COMMAND_TIMEOUT'):native.run(['/bin/sleep','5'],gate,0.3,False)
    with pytest.raises(FileNotFoundError):native.run(['/nonexistent/binary'],gate,5)
    def expired():raise p.Refused('GO_EXPIRED')
    with pytest.raises(p.Refused,match='GO_EXPIRED'):native.run(['/bin/echo','x'],expired,5)
    (tmp_path/'one').write_bytes(b'1');(tmp_path/'two').mkdir();os.symlink('one',tmp_path/'link')
    fd=native.open(str(tmp_path.resolve()),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        assert sorted(native.names(fd))==['link','one','two'] and p.kind(native.lstat('link',fd).st_mode)=='symlink'
        assert p.shape(native.lstat('two',fd))['type']=='dir' and native.fstatvfs(fd).f_frsize>0 and native.readlink('link',fd)=='one'
        with pytest.raises(OSError):native.open('link',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
    finally:native.close(fd)
    assert native.identity()==(os.geteuid(),os.getegid()) and native.pid()==os.getpid() and abs(native.now()-time.time())<5
    version,implementation=native.python();assert version==tuple(sys.version_info[:3]) and implementation==sys.implementation.name
    assert not hasattr(native,'kernel')          # the release is read from procfs: uname, and with it the node name, is never called


# ---------------------------------------------------------------- static properties of the remote source
def test_remote_source_is_python_3_7_stdlib_only_and_shell_free():
    text_=SOURCE.decode();tree=ast.parse(text_,feature_version=(3,7))
    imported=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imported|={alias.name.split('.')[0] for alias in node.names}
        if isinstance(node,ast.ImportFrom):imported.add(node.module.split('.')[0])
        assert not isinstance(node,(ast.JoinedStr,ast.AsyncFunctionDef)) and type(node).__name__ not in ('NamedExpr','Match')
    assert imported=={'hashlib','json','os','pathlib','re','selectors','stat','subprocess','sys','time','dataclasses','datetime'}
    used=lambda owner:{node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id==owner}
    assert used('os')=={'open','close','fstat','stat','fstatvfs','read','readlink','scandir','geteuid','getegid','getpid','set_blocking',
                        'O_RDONLY','O_DIRECTORY','O_NOFOLLOW','O_NONBLOCK'}            # O_NOATIME is looked up lazily by name; no uname
    assert used('subprocess')=={'Popen','PIPE','DEVNULL','TimeoutExpired'} and used('pwd')==used('grp')==used('socket')==set()
    assert used('sys')=={'version_info','implementation'} and used('time')=={'monotonic','time','clock_gettime'}
    called={node.func.id for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)}
    assert not called&{'open','eval','exec','print','compile','input','__import__','globals','locals','setattr','breakpoint'}
    for forbidden in ('shell=True','.Env',"'Env'",'os.environ','getenv','socket','urllib','O_WRONLY','O_RDWR','O_CREAT','O_TRUNC','O_APPEND',
                      'SUPERVISOR_PREFLIGHT','POSTDEPLOY','HOSTFACTS','hostfacts',"'exec'","'run'","'restart'","'kill'","'rm'","'enable'",
                      'getpwnam','getpwuid','import pwd','nsswitch','IPAddress','MacAddress','nodename','os.kill','os.remove','os.unlink',
                      'os.rename','os.mkdir','os.chmod','os.chown','os.write','os.system','flock','daemon-reload','is-active','os.uname(',
                      'gethostname','--context','DOCKER_CONTEXT'):
        assert forbidden not in text_,forbidden
    assert text_.count('"Env"')==1 and text_.count('subprocess.Popen(')==1 and "stderr=subprocess.DEVNULL" in text_ and 'print(' not in text_
    assert p.OPERATION=='GO_READONLY_W1PREFLIGHT_01' and p.DATES==DATE_SET and p.MAX_SECONDS==60
    assert p.COMPLETE_STATUS=='METADATA_ONLY_REQUIRES_REVIEW' and p.PARTIAL_STATUS=='PARTIAL_METADATA_REQUIRES_REVIEW'   # fixed by the transport bytes

def test_dispatcher_carries_only_the_listed_delta_and_launcher_and_transport_are_the_reviewed_bytes():
    dispatcher=(ROOT/'dispatch_once.py').read_text()
    assert p.sha((ROOT/'launcher_stdin.py').read_bytes())==LAUNCHER_PIN and p.sha((ROOT/'transport_once.py').read_bytes())==TRANSPORT_PIN
    assert dispatcher.count('PREFLIGHT_BUDGET')==1 and 'HOSTFACTS' not in dispatcher and 'hostfacts' not in dispatcher
    assert dispatcher.count('w1_preflight_readonly')==5 and dispatcher.count('W1PREFLIGHT')==12
    assert "start.date().isoformat() in ("+','.join(repr(day) for day in DATE_SET)+") and end.date()==start.date()" in dispatcher
    assert dispatcher.count('2026-')==len(DATE_SET) and SOURCE.decode().count(repr(DATE_SET[-1]))==1          # one date literal, in each file
    assert "config['watchdog_seconds']==80 and request.get('max_seconds')==60" in dispatcher
    delta=(ROOT/'DISPATCH_SCOPE_DELTA.diff').read_text().splitlines()
    removed=[row[1:] for row in delta if row.startswith('-') and not row.startswith('---')]
    added=[row[1:] for row in delta if row.startswith('+') and not row.startswith('+++')]
    assert len(removed)==16==len(added)
    # every changed line differs only by the family literals: mapping the new names back gives the reviewed line
    back=[('w1_preflight_readonly','hostfacts_readonly'),("'W1PREFLIGHT01_DISPATCH_AUTHORIZATION_V1'","'SUPERVISOR_HOSTFACTS_DISPATCH_AUTHORIZATION_V1'"),
          ("'GO_READONLY_W1PREFLIGHT_01'","'GO_READONLY_SUPERVISOR_HOSTFACTS_01'"),(" in ("+','.join(repr(day) for day in DATE_SET)+")","=='2026-10-02'"),
          ("'READONLY_W1PREFLIGHT01_","'READONLY_SUPERVISOR_HOSTFACTS_"),("=='READONLY_W1PREFLIGHT'","=='READONLY_HOSTFACTS'"),
          ("'W1PREFLIGHT01_","'SUPERVISOR_HOSTFACTS_")]
    for old,new in zip(removed,added):
        for ours,theirs in back:new=new.replace(ours,theirs)
        assert new==old
    reviewed=Path(os.environ.get('BIND_TEST_REVIEWED_REFERENCE_ROOT', str(Path(__file__).resolve().parent/'missing-reviewed-references')))/'hostfacts01/candidate/dispatch_once.py'
    assert reviewed.is_file(),'the reviewed dispatcher of 2026-10-02 must be present: this comparison is not optional'
    base=reviewed.read_text();assert p.sha(base.encode())==REVIEWED_DISPATCH_PIN
    rebuilt=dispatcher
    for ours,theirs in back:rebuilt=rebuilt.replace(ours,theirs)
    assert rebuilt==base
    for name in ('launcher_stdin.py','transport_once.py'):assert (reviewed.parent/name).read_bytes()==(ROOT/name).read_bytes(),name

KEPT=['CommandFailed.__init__','Context.__init__','Context.check','Gate.__call__','Gate.__init__','Native.close','Native.fstat','Native.fstatvfs',
      'Native.identity','Native.lstat','Native.names','Native.noatime','Native.open','Native.read','Native.run','Pins','Refused','_label',
      '_reduce_sections','attempt','binary','canonical','clean_path','combined','data_path','descend','instant','kind','need','properties',
      'reason_codes','safe','seal','sha','shape','text','trusted_executable']
def units(source):
    tree=ast.parse(source);out={}
    for node in tree.body:
        if isinstance(node,ast.ClassDef):
            methods=[sub for sub in node.body if isinstance(sub,ast.FunctionDef)]
            for sub in methods:out[node.name+'.'+sub.name]=ast.get_source_segment(source,sub)
            if not methods:out[node.name]=ast.get_source_segment(source,node)
        elif isinstance(node,ast.FunctionDef):out[node.name]=ast.get_source_segment(source,node)
    return out
REVIEWED_SOURCE=Path(os.environ.get('BIND_TEST_REVIEWED_REFERENCE_ROOT', str(Path(__file__).resolve().parent/'missing-reviewed-references')))/'hostfacts01/candidate/hostfacts_readonly.py'
def test_the_functions_named_as_kept_are_textually_the_reviewed_ones():
    assert sys.version_info>=(3,8) and REVIEWED_SOURCE.is_file(),'needs ast.get_source_segment and the reviewed source of 2026-10-02: not optional'
    earlier=REVIEWED_SOURCE.read_text();assert p.sha(earlier.encode())=='00d20785a667e5ea4d034c4c046537844327ff1e227d61a9fa19e4a390d94664'
    old,new=units(earlier),units(SOURCE.decode())
    assert sorted(name for name in old if name in new and old[name]==new[name])==sorted(KEPT)
    assert sorted(name for name in old if name in new and old[name]!=new[name])==['Context.call','Context.output','authenticate','collect','containers',
        'data_volume','decode','docker_daemon','family_facts','family_row','filesystem','images','observe','probe','strict','systemd','validate_collection']
    assert sorted(name for name in old if name not in new)==['_drop_names','_drop_rows','_each_listing','_reduce_family','_reduce_mounts','definite','docker_init',
                                                             'entries','process_maps','reference','supervisor_trees']
    import difflib
    changed=[row for row in difflib.unified_diff(old['authenticate'].splitlines(),new['authenticate'].splitlines(),lineterm='',n=0) if row[:1] in '+-' and row[:3] not in ('+++','---')]
    assert len(changed)==5 and all('date' in row or 'days' in row for row in changed)          # the dates check and nothing else
    changed=[row for row in difflib.unified_diff(old['observe'].splitlines(),new['observe'].splitlines(),lineterm='',n=0) if row[:1] in '+-' and row[:3] not in ('+++','---')]
    assert len(changed)==2 and all('is_not_readiness' in row for row in changed)

def test_the_contract_names_every_problem_and_finding_code_of_the_source():
    contract=(ROOT/'CONTRACT.txt').read_text();text_=SOURCE.decode();body=text_[text_.index('class Native'):text_.index('# Authenticated stdin API')]
    codes=set()
    for pattern in (r"need\([^\n]*?,'([A-Z][A-Z0-9_]+)'\)",r"Refused\('([A-Z][A-Z0-9_]+)'\)",r"CommandFailed\('([A-Z][A-Z0-9_]+)'",r"issues\.append\('([A-Z][A-Z0-9_]+)'\)",
                    r"failure='([A-Z][A-Z0-9_]+)'",r"issues=\['([A-Z][A-Z0-9_]+)'\]",r"'code':'([A-Z][A-Z0-9_]+)'",r"document\(raw,[A-Z_]+,'([A-Z_]+)'\)",
                    r"problems\.append\('([A-Z][A-Z0-9_]+)'\)",r"findings\.append\('([A-Z][A-Z0-9_]+)'",r"findings=\['([A-Z][A-Z0-9_]+)'\]",r" else '([A-Z][A-Z0-9_]+)'\)",
                    r"listed\('[a-z_]+',[A-Z_]+,'([A-Z_]+)'\)",r"else \['([A-Z][A-Z0-9_]+)'\]",r"(?m)^\s+'([A-Z][A-Z0-9_]+)'\)$"):
        codes|=set(re.findall(pattern,body))
    codes-={'CLASS_INVALID'}          # counted as an unclassified container, never emitted
    assert len(codes)>140 and {'CONTAINER_CHANGED','PRIVATE_INPUT_NOT_UID0','REBOOT_PENDING','ENVFLAGS_INVALID','CENSUS_CAPPED','NO_RUNNING_WORKER_TO_EVALUATE'}<=codes
    words=set(re.findall(r'[A-Z][A-Z0-9_]+',contract))
    assert sorted(codes-words)==[]
    # and every code that any test of this file has seen in a receipt is a code of the source
    refusals=set(re.findall(r"'([A-Z][A-Z0-9_]+)'\)",text_[text_.index('def validate_candidates'):]))
    assert {'CANDIDATES_INVALID','DATE_WINDOW_MISMATCH','SCOPE_MISMATCH','PIN_MISMATCH','OUTSIDE_GO_WINDOW'}<=refusals and sorted(refusals-words-{'RECEIPT_LIMIT'})==[]


# ---------------------------------------------------------------- Docker --format semantics reproduced from the real host
REV3_FORMAT='{"name":{{json .Name}},"id":{{json .Id}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}}}'
REV4_FORMAT='{"name":{{json .Name}},"id":{{json .Id}},"image_id":{{json .Image}},"image_reference":{{json .Config.Image}},"running":{{json .State.Running}},"state":{{json .State.Status}},"started_at":{{json .State.StartedAt}},"host_pid":{{json .State.Pid}},"restarts":{{json .RestartCount}},"health":{{if index .State "Health"}}{{json (index .State "Health" "Status")}}{{else}}null{{end}}}'
def test_fake_docker_reproduces_rev3_failure_and_rev4_success():
    docker=world().docker;inspect=lambda template,item:docker.run(['container','inspect','--format',template,item['Id']])
    failed=[item['Name'] for item in docker.containers if inspect(REV3_FORMAT,item)[0]!=0]
    assert len(failed)==10 and '/c3po-db-1' not in failed          # the host on 2026-10-01: 10 of 11 failed, only db passed
    rows=[json.loads(inspect(REV4_FORMAT,item)[1]) for item in docker.containers]
    assert all(set(row)=={'name','id','image_id','image_reference','running','state','started_at','host_pid','restarts','health'} for row in rows)
    assert [row['health'] for row in rows].count('healthy')==1 and [row['health'] for row in rows].count(None)==10
    assert {row['host_pid'] for row in rows}>={0,410243} and all(row['name'].startswith('/') for row in rows)
    assert set(docker.modes)=={'raw'}                                  # .Id is not a typed field: always the raw fallback
    assert docker.run(['container','inspect','--format','{{json .Name}}{{if .State.Health}}x{{else}}null{{end}}',docker.containers[0]['Id']])==(0,b'"/chief-of-staff-digital-pluggy-webhook-1"null\n')
    assert docker.modes[-1]=='typed'

def test_fake_docker_template_edge_semantics():
    docker=world().docker;first=docker.containers[1]['Id'];run=lambda template:docker.run(['container','inspect','--format',template,first])
    assert run('{{{"x"}}')[0]==64 and run('{{"{"}}{{json .Id}}}')[0]==0          # an action may not begin with a brace
    assert run('{{json .Id}}{{json .State.Health.Status}}')[0]==1                  # missingkey=error on an absent key
    assert run('{{json .Id}}{{json (index .State "Health")}}')==(0,('"%s"null\n'%first).encode())
    assert run('{{json .Id}}{{if eq "a" "a"}}T{{end}}{{if eq "a" "b"}}F{{end}}')[1].endswith(b'"T\n')
    assert run('{{json .Id}}{{if eq .State.Pid "x"}}T{{end}}')[0]==0 and run('{{json .Id}}{{if eq .State.Running "x"}}T{{end}}')[0]==1   # kinds must agree
    assert run('{{json .Id}}{{index (split "A=b=c" "=") 0}}|{{index (split "plain" "=") 0}}|{{index (split "" "=") 0}}|')[1].endswith(b'"A|plain||\n')
    assert run('{{json .Id}}{{split .State.Running "="}}')[0]==1 and run('{{json .Id}}{{nosuchfunction .Id}}')[0]==64
    docker.containers[1]['Config']['Labels']=None
    assert run('{{json .Id}}{{json (index .Config.Labels "a")}}')[0]==1            # index of untyped nil
    assert run('{{json .Id}}{{with index .Config "Labels"}}{{json (index . "a")}}{{else}}null{{end}}')[1].endswith(b'null\n')
    assert run('{{json .Id}}{{range $m := index . "Missing"}}x{{end}}|')[1].endswith(b'|\n')
    for outside in (['info','--format','{{json .ServerVersion}}'],['exec','x'],['compose','ps'],['network','ls']):
        with pytest.raises(AssertionError):docker.run(outside)

PROVEN={'PS_FORMAT':'c9451cef63dde3eae0fe8191bfece13a0061d22627cf76951bd8f4503743c85e',
        'CLASS_FORMAT':'9b06cd69e7cf5d610e60ba6af2348aea98161e1c29d446787b9863609d0e5909',
        'FAMILY_FORMAT':'c0b825daef525afab3edbb9fc721a1d4cc8c1eac49e72d0f501ff67c69fce761',
        'IMAGE_FORMAT':'da570479ee9ebac635b5cc8134be62b859a51e38d62e0c234cdc3accae325b17',
        'VERSION_FORMAT':'4880842e5952cc6c44f03791561e6509c6c2328e2775b215bcd86cfd30e52fc6'}
ALLOWED_CHAINS={'.ID','.Names','.State','.Id','.Name','.Image','.Config.Image','.State.Running','.State.Status','.State.StartedAt',
                '.State.Pid','.RestartCount','.Config','.HostConfig','.NetworkSettings','.Server.Version',
                '.Driver','.Scope','.Internal','.Attachable','.Containers'}
def test_every_template_is_lexer_clean_and_the_five_proven_ones_are_the_bytes_run_on_the_host():
    assert set(p.TEMPLATES.values())=={args[args.index('--format')+1] for _,args,_ in p.COMMANDS.values() if '--format' in args}
    for name,template in p.TEMPLATES.items():
        assert not template.startswith('{{{') and '{{{' not in template,name
        parse(template)
        assert 'IPAddress' not in template and 'MacAddress' not in template and '{{json .}}' not in template and '{{.}}' not in template,name
        assert ('Env' in template)==(name=='ENVFLAGS_FORMAT'),name
        chains=set(re.findall(r'(?<![A-Za-z0-9"$])\.[A-Z][A-Za-z.]*',re.sub(r'"[^"]*"','""',template)))
        assert chains<=ALLOWED_CHAINS,(name,chains-ALLOWED_CHAINS)
    for name in ('CLASS_FORMAT','FAMILY_FORMAT','IMAGE_FORMAT','ENVFLAGS_FORMAT','ATTACH_FORMAT'):assert '{{json .Id}}' in p.TEMPLATES[name]   # forces the proven raw mode
    assert '.Id' not in p.NETWORK_FORMAT and '.ID' not in p.NETWORK_FORMAT          # executes in either inspect mode
    assert sorted(p.TEMPLATES)==['ATTACH_FORMAT','CLASS_FORMAT','ENVFLAGS_FORMAT','FAMILY_FORMAT','IMAGE_FORMAT','NETWORK_FORMAT','PS_FORMAT','VERSION_FORMAT']
    assert {name:p.sha(p.TEMPLATES[name].encode()) for name in PROVEN}==PROVEN and sorted(PROVEN)==p.PROVEN_TEMPLATES
    reviewed=Path(os.environ.get('BIND_TEST_REVIEWED_REFERENCE_ROOT', str(Path(__file__).resolve().parent/'missing-reviewed-references')))/'hostfacts01/candidate/hostfacts_readonly.py'
    assert reviewed.is_file(),'the reviewed source of 2026-10-02 must be present: this comparison is not optional'
    earlier=reviewed.read_text()
    for name in PROVEN:assert repr(p.TEMPLATES[name])[1:-1] in earlier or name in ('CLASS_FORMAT','FAMILY_FORMAT','IMAGE_FORMAT')

def test_the_signed_argv_table_holds_only_read_commands():
    shapes={('docker','ps'),('docker','container','inspect'),('docker','image','inspect'),('docker','network','inspect'),('docker','version'),
            ('systemctl','show'),('pgrep','-c','-f')}
    for name,(tool,args,extra) in p.COMMANDS.items():
        if tool=='docker':          # every docker argv names the one local endpoint before its subcommand
            assert args[:2]==['--host','unix:///var/run/docker.sock']==p.ENDPOINT_ARGV and p.DOCKER_ENDPOINT==p.SCOPE['docker_endpoint'];args=args[2:]
            assert not {'--context','-c','-H','--host','--tls','--tlsverify','--config'}&set(args),name
        head=(tool,)+tuple(args[:2 if tool=='docker' and args[0] in ('container','image','network') else 2 if tool=='pgrep' else 1])
        assert head in shapes,(name,head)
        assert not {'exec','run','start','stop','restart','kill','rm','enable','disable','create','cp','pull','prune','-e','--env','sh','-c=','daemon-reload'}&set(args),name
        assert all(type(item) is str and item and not item.startswith('/') for item in args)
    assert sorted(p.BINARIES)==['docker','pgrep','systemctl'] and all(path.startswith('/') for paths in p.BINARIES.values() for path in paths)
    assert len(p.COMMANDS)==9+len(p.UNITS)+len(p.PROCESS_PATTERNS) and p.COMMANDS['network'][1][-1]=='c3po_c3po_internal'
    # worst case of waiting: systemctl and pgrep hang until their shared budget ends (three timeouts), docker until it is skipped
    assert p.SYSTEM_TOOLS_SECONDS==15==3*p.CALL_SECONDS and p.SYSTEM_TOOLS_SECONDS+p.MAX_TOOL_TIMEOUTS*p.CALL_SECONDS==25<=p.MAX_SECONDS//2
    # worst case of slowness without a timeout: each of the two groups uses its whole budget and one last call
    assert p.SYSTEM_TOOLS_SECONDS+p.CALL_SECONDS+p.DOCKER_SECONDS+p.CALL_SECONDS==50<p.MAX_SECONDS and p.DOCKER_SECONDS==25
    assert p.SCOPE['limits']['system_tools_seconds']==p.SYSTEM_TOOLS_SECONDS and p.SCOPE['limits']['docker_seconds']==p.DOCKER_SECONDS
    assert {tool for tool,_,_ in p.COMMANDS.values()}=={'docker','systemctl','pgrep'}          # every tool is in one of the two groups

def test_environment_template_can_print_nothing_but_the_container_id_and_fixed_tokens():
    actions=re.findall(r'\{\{(.*?)\}\}',p.ENVFLAGS_FORMAT);printing=[]
    for action in actions:
        if action in ('end','range $e := index .Config "Env"','$k := index (split $e "=") 0'):continue
        if re.fullmatch(r'if eq \$k "[A-Z0-9_]+"',action) or re.fullmatch(r'if eq \$e "[A-Za-z0-9_=/.-]+"',action):continue
        printing.append(action)
    assert printing==['json .Id']          # the only action that prints anything at all
    literal=re.sub(r'\{\{.*?\}\}','\x00',p.ENVFLAGS_FORMAT)
    assert re.fullmatch(r'\{"id":\x00,"flags":\[\x00\x00(\x00"[A-Z_]+",\x00)+\x00null\]\}',literal)
    assert set(re.findall(r'\x00"([A-Z_]+)",\x00',literal))==set(p.ENV_TOKENS) and len(p.ENV_TOKENS)==len(set(p.ENV_TOKENS))==22
    host=world();worker=[item for item in host.docker.containers if item['Name']=='/c3po-r2d2-worker-1'][0]
    worker['Config']['Env']+=['C3PO_R2D2_V2_CAPACITY_REQUIRED=true','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=/c3po-capacity/config/never-emit-file-canary',
                              'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=never-emit-sha-canary','C3PO_R2D2_V2_SHADOW_ENABLED=never-emit-value-canary',
                              'NOEQUALS','','=never-emit-empty-key-canary','C3PO_DATABASE_URL"=x','C3PO_DATABASE_URL_OTHER=never-emit-suffix-canary']
    for item in host.docker.containers:
        code,out=host.docker.run(['container','inspect','--format',p.ENVFLAGS_FORMAT,item['Id']]);row=json.loads(out)
        assert code==0 and row['id']==item['Id'] and row['flags'][-1] is None and set(row['flags'][:-1])<=set(p.ENV_TOKENS)
        for value in item['Config']['Env'] or []:
            _,_,secret=value.partition('=')
            assert len(secret)<6 or secret.encode() not in out or secret in ('true',)
        assert b'canary' not in out and b'postgresql' not in out
    flags=set(json.loads(host.docker.run(['container','inspect','--format',p.ENVFLAGS_FORMAT,worker['Id']])[1])['flags'][:-1])
    assert flags=={'DATABASE_URL_KEY','RAW_DIR_KEY','RAW_DIR_DOCUMENTED','CAPACITY_REQUIRED_KEY','CAPACITY_REQUIRED_TRUE','CAPACITY_CONFIG_FILE_KEY',
                   'CAPACITY_CONFIG_SHA_KEY','SHADOW_ENABLED_KEY'}
    assert host.docker.modes[-1]=='raw'
    worker['Config']['Env']=None          # a container without any environment: the range is empty, the list is the sentinel alone
    assert json.loads(host.docker.run(['container','inspect','--format',p.ENVFLAGS_FORMAT,worker['Id']])[1])['flags']==[None]

def test_network_template_gives_the_same_answer_in_the_typed_and_in_the_raw_inspect_mode():
    host=world();argv=['network','inspect','--format',p.NETWORK_FORMAT,'c3po_c3po_internal']
    typed=host.docker.run(argv);assert typed[0]==0 and host.docker.modes[-1]=='typed'
    host.docker.network_typed=False;raw=host.docker.run(argv);assert raw==typed and host.docker.modes[-1]=='raw'
    row=json.loads(typed[1]);assert set(row)=={'name','driver','scope','internal','attachable','containers'} and row['containers'][-1] is None
    assert len(row['containers'])==9 and b'172.19' not in typed[1] and b'02:42' not in typed[1] and b'Subnet' not in typed[1]
    code,out=host.docker.run(['container','inspect','--format',p.ATTACH_FORMAT,host.docker.containers[2]['Id']])
    assert code==0 and json.loads(out)['networks']==[{'name':'c3po_c3po_internal','network_id':'a1'*32},{'name':'c3po_db_loopback','network_id':'b2'*32},None]
    assert b'172.19' not in out and b'02:42' not in out


# ---------------------------------------------------------------- the host as it is before provisioning
BEFORE=['capacity_candidates:NO_CAPACITY_ROOT_CANDIDATE_SIGNED','data_volume:TRIAL_VETO_INDEPENDENT_OF_PIN','data_volume:TRIAL_VETO_PRESENT',
        'release_directories:NO_RELEASE_DIRECTORY_CANDIDATE_SIGNED']
SECTIONS=['alert_channels','capacity_candidates','clock','containers','data_volume','deploy_version','docker_daemon','host_layout','images',
          'journal_filesystem','network','processes','raw_spool','release_directories','runtime','security_controller','source_directory',
          'systemd','worker','worker_environment']
def absent(path):return {'status':'COMPLETE','exists':False,'absent_at':path}
def k_veto(sections):return sections['security_controller']['controller_trial_veto']
def docker_argv(host):return [argv for argv in host.log if argv[0].endswith('/docker')]
NEGATIVE={'containers:SERVICE_MISSING','worker:WORKER_COUNT_NOT_ONE','worker_environment:NO_RUNNING_WORKER_TO_EVALUATE','network:DB_CONTAINER_NOT_RUNNING',
          'network:DB_NOT_ON_NETWORK','network:WORKER_NOT_ON_NETWORK','images:PRODUCTION_TAG_NOT_RUNNING_IMAGE','images:REVISION_LABEL_MISMATCH',
          'images:SERVICE_TAG_NOT_RUNNING_IMAGE','images:BACKEND_SERVICE_WITHOUT_RUNNING_CONTAINER','deploy_version:DEPLOY_VERSION_NOT_THE_RUNNING_REVISION',
          'data_volume:DATA_MOUNT_NOT_FOUND'}          # what may be said only of containers that were all classified and read
def clean(raw):
    for canary in CANARIES:assert canary not in raw,canary

def test_host_before_provisioning_is_complete_and_every_family_is_observed(bound):
    host=world();receipt,o,s=observed(bound,host);raw=line(receipt)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['status']=='OBSERVED_COMPLETE' and o['problems']==[] and o['findings']==BEFORE
    assert sorted(s)==SECTIONS and {name:section['status'] for name,section in s.items()}=={name:'COMPLETE' for name in SECTIONS}
    assert o['actor']=={'uid':0,'gid':0} and o['scope_sha256']==p.SCOPE_SHA256==bound[1]['scope_sha256'] and o['size_reductions']==[]
    assert host.fds=={} and len(raw)<45000 and o['entry_names_emitted']==0 and o['container_environment_values_received']==0
    assert o['writes']==0 and o['container_commands']==0 and o['file_contents_read']==p.FILE_CONTENTS_READ
    clean(raw)
    # runtime: never measured before
    assert s['runtime']['python']=={'status':'COMPLETE','major':3,'minor':12,'micro':3,'implementation':'cpython'}
    assert s['runtime']['kernel']=={'status':'COMPLETE','version':'6.8.0','abi':1013,'release_withheld':False,'suffix_withheld':True}
    assert s['runtime']['boot']['uptime_seconds']==302400 and b'aws' not in raw
    assert s['runtime']['boot']['boot_epoch_utc']==int(NOW.timestamp()-302400.5)
    assert s['docker_daemon']=={'status':'COMPLETE','server_version':'29.9.9','server_version_suffix_withheld':False,'docker_path':'/usr/bin/docker',
                                'docker_endpoint':'unix:///var/run/docker.sock','docker_info_requested':False}
    assert o['automount_guard']=={'applied':True,'autofs_rows':1,'armed_points':1}
    # containers: eight services of the stack, each exactly once, all running; rows compared in canonical order
    c=s['containers'];assert [row['service'] for row in c['rows']]==p.SERVICES and c['list_stable'] and c['listed_before']==c['listed_after']==11
    assert c['services']=={name:{'count':1,'running':1,'oneoff_count':0} for name in p.SERVICES} and c['services_missing']==c['services_duplicated']==[]
    assert c['outside_stack_count']==3 and c['running_outside_stack_count']==2 and c['stack_other_services_count']==0 and c['unclassified_count']==0
    assert c['fixed_names']=={'c3po-massive':{'present':False,'state':None},'c3po-reader':{'present':False,'state':None}}
    assert all(row['status']=='COMPLETE' and row['unchanged_during_read'] and row['changed_keys']==[] and row['findings']==[] for row in c['rows'])
    api=c['rows'][0]
    assert api['name']=='c3po-api-1' and api['name_conforming'] and api['image_id']==BACKEND_IMAGE and api['image_reference']=='c3po/backend:production'
    assert api['networks']==['c3po_c3po_internal','chief-of-staff-digital_default'] and api['networks_other_count']==0 and api['revision_label']==REVISION
    assert api['user']=='' and api['userns_mode']=='' and api['readonly_rootfs'] is False and api['network_mode']=='c3po_c3po_internal' and 'host_pid' not in api
    assert api['mounts']==[{'type':'bind','rw':True,'destination':'/app/day-d-data','source':DATA},
                           {'type':'volume','rw':True,'destination':'/app/generated-one-pagers','volume':'c3po_c3po_one_pagers'},
                           {'type':'bind','rw':False,'destination':'/legacy','source':APP},
                           {'type':'bind','rw':False,'destination':'/run/c3po-maintenance','source':MAINTENANCE}]
    # worker: exactly one, the capacity mount is the unprovisioned placeholder, read-only
    w=s['worker'];assert w['exactly_one_running'] and w['count']==w['running']==1 and w['findings']==[]
    assert w['workers'][0]['capacity_mount']=={'present':True,'count':1,'type':'volume','rw':False,'volume':'c3po_c3po_capacity_unprovisioned',
                                               'is_the_unprovisioned_placeholder':True,'source_capacity_candidate_index':None}
    assert w['workers'][0]['data_mount']=={'present':True,'type':'bind','rw':True,'source_in_data_sources':True}
    e=s['worker_environment'];flags=e['workers'][0]
    assert e['evaluated_count']==1 and e['values_in_this_process']==0 and flags['database_url']=='SET' and flags['capacity_required']=='ABSENT'
    assert flags['raw_dir']=='DOCUMENTED' and flags['shadow_enabled']=='ABSENT' and flags['massive_bars_enabled']=='ABSENT' and flags['token_count']==3
    assert flags['shadow_source_dir']=='ABSENT' and flags['massive_journal_dir']=='ABSENT' and flags['capacity_veto_mode']=='ABSENT'
    assert flags['keys_present']=={name:name in ('DATABASE_URL_KEY','RAW_DIR_KEY') for _,name in p.ENV_KEYS}
    # network: name and id of the compose network, db attached
    n=s['network'];assert n['network_id']=='a1'*32 and n['network_ids_agree'] and n['db_attached_by_network_inspect'] and n['worker_attached_by_network_inspect']
    assert n['inspect']=={'status':'COMPLETE','name':'c3po_c3po_internal','driver':'bridge','scope':'local','internal':True,'attachable':False,
                          'attached_count':8,'attached_not_a_container_id_count':0} and n['backend_attached_count']==6
    assert n['attachments']['db']=={'status':'COMPLETE','evaluated':True,'network_ids':{'c3po_c3po_internal':'a1'*32,'c3po_db_loopback':'b2'*32},
                                    'other_network_count':0,'on_compose_network':True}
    # images: the ID to render is the one read here
    i=s['images'];production=i['tags']['c3po/backend:production']
    assert production=={'status':'COMPLETE','issues':[],'resolved':True,'id':BACKEND_IMAGE,'revision_label':REVISION,
                        'repo_tags':['c3po/backend:production'],'retention_tag_count':0,'other_tag_count':1}
    assert i['production_id_equals_every_running_backend'] and i['revision_label_equal_across_backend_and_production'] and i['rollback_differs_from_production']
    assert i['service_tag_equals_running']=={'db':True,'web':True} and i['stack_images_without_a_listed_tag']==[] and i['backend_image_ids_distinct']==1
    assert i['backend_services_without_a_running_container']==[] and i['backend_containers_compared']==6
    v=s['deploy_version'];assert v['revision']==REVISION and v['equals_production_revision_label'] and v['equals_every_backend_container_revision']
    assert v['file']=={'status':'COMPLETE','exists':True,'type':'file','uid':1000,'gid':1000,'mode_octal':'0644','mtime_epoch':STAMP,'content_read':True}
    # data volume: device, space, mount holder, root classes
    a=s['data_volume'];assert a['source']==DATA and a['source_basis']=='MOUNT_OF_THE_RUNNING_CONTAINERS' and a['distinct_source_count']==1
    assert a['stopped_or_oneoff_containers_with_the_data_mount']==[] and a['root_private'] is False and a['findings']==['TRIAL_VETO_INDEPENDENT_OF_PIN','TRIAL_VETO_PRESENT']
    assert a['root_access_as_uid0_without_capabilities']=={'read':True,'search_or_execute':True}          # 1000:1000 0755: through the other bits
    assert [item['service'] for item in a['carriers']]==['api','r2d2-shadow-candidate-worker','r2d2-worker']
    assert [(row['path'],row['uid'],row['gid'],row['mode_octal'],row['device'],row['mount_point_by_device_change']) for row in a['ancestors']]==[
        ('/',0,0,'0755',ROOT_DEV,True),('/mnt',0,0,'0755',ROOT_DEV,False),(DATA,1000,1000,'0755',DATA_DEV,True)]
    f=a['filesystem'];assert (f['device'],f['device_major'],f['device_minor'],f['inode'])==(DATA_DEV,259,16,2) and f['read_only'] is False
    assert f['bytes_available_to_non_root_f_bavail']==13200000*4096 and f['bytes_free_for_root_f_bfree']==14500000*4096 and f['f_files']==6553600
    assert a['mount']=={'status':'COMPLETE','mount_point':DATA,'mount_point_is_the_path':True,'mounted_root_is_the_filesystem_root':True,
                        'filesystem_type':'ext4','source_device':'/dev/nvme1n1','read_write':True,'device_equals_the_directory_device':True,
                        'source_device_withheld':False}
    root=a['root'];assert root['count']==37 and root['capped'] is False and root['atime_unchanged'] and 'live_directory' not in root
    assert root['pin']=={'exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','mtime_epoch':STAMP}
    assert root['classes']=={'pin':1,'release_json':1,'release_json_with_a_diagnostic_name':1,'release_directory':3,'trial_or_probe':6,
                             'trial_or_probe_dated_in_the_past':4,'trial_or_probe_name_unrecognised':2,'provider_directory':3}
    assert root['controller_trial_veto']['by_pin'] and root['controller_trial_veto']['by_unrecognised_name'] and root['controller_trial_veto']['definite']
    assert root['controller_trial_veto']['remains_without_the_pin'] is True and root['controller_trial_veto']['by_release_file']=='UNDETERMINED_WITHOUT_CONTENT'
    assert root['controller_trial_veto']['listing_capped'] is False and k_veto(s)==root['controller_trial_veto']
    assert sum(row[4] for row in root['histogram'])+root['histogram_other_entries']==37 and all(len(row)==5 for row in root['histogram'])
    assert o['histogram_columns']==['type','uid','gid','mode_octal','count'] and ['dir',0,0,'0700',16] in root['histogram']
    assert root['counters']=={'not_uid0':5,'private_not_uid0':2,'not_private':16,'uid0_nocap_unreadable':2} and o['counters_listed_only_when_not_zero']==p.COUNTERS
    # journal on the root filesystem: device, owner and mode of /var/lib, space against the two numbers, another device than the data volume
    j=s['journal_filesystem'];assert j['statvfs_of']=='/var/lib' and j['journal_parent']==j['journal_root']==j['state_root']=={'exists':False}
    assert [(row['path'],row['uid'],row['gid'],row['mode_octal'],row['device']) for row in j['ancestors']]==[('/',0,0,'0755',ROOT_DEV),('/var',0,0,'0755',ROOT_DEV),('/var/lib',0,0,'0755',ROOT_DEV)]
    assert j['filesystem']['device']==ROOT_DEV and j['filesystem']['inode']==70001 and (j['filesystem']['device_major'],j['filesystem']['device_minor'])==(259,1)
    assert j['filesystem']['bytes_available_to_non_root_f_bavail']==145000000*4096 and j['filesystem']['bytes_free_for_root_f_bfree']==145004096*4096
    assert j['available_ge_floor'] and j['available_ge_five_session_need'] and j['margin_over_five_session_need_bytes']==145000000*4096-56706990080
    assert j['device_differs_from_data_volume'] is True and j['docker_root_on_the_same_device'] is True and j['floor_bytes']==53687091200
    assert j['mount']['mount_point']=='/' and j['mount']['filesystem_type']=='ext4' and j['mount']['source_device']=='/dev/nvme0n1p1' and 'journal_listing' not in j
    # reader inputs: owner, mode and what uid 0 without capabilities may do
    r=s['raw_spool'];assert [item['label'] for item in r['components']]==p.RAW_PARTS and all(item['exists'] and item['uid']==0 for item in r['components'])
    assert r['sessions']=={'count':5,'not_a_session_count':0,'oldest_date':'2026-09-28','newest_date':'2026-10-02'}
    assert [item['date'] for item in r['sampled_newest_sessions']]==['2026-10-02','2026-10-01','2026-09-30']
    assert all(item['parts_count']==4 and item['not_a_part_count']==0 and item['access_as_uid0_without_capabilities']=={'read':True,'search_or_execute':True}
               and item['live_directory'] and item['histogram']==[['file',0,0,'0644',4]] and item['counters']=={'not_private':4}
               for item in r['sampled_newest_sessions'])
    q=s['source_directory']['candidates'][0]
    assert q['exists'] and q['private'] and (q['uid'],q['gid'],q['mode_octal'])==(0,0,'0700') and q['snapshot']=={'exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','private':True}
    assert q['events']['count']==40 and q['events']['counters']=={} and q['events']['histogram']==[['file',0,0,'0600',40]] and q['events']['private']
    assert q['causal_list']['count']==1 and q['causal_epoch']=={'status':'COMPLETE','exists':False} and 'listing' not in q
    assert s['release_directories']['candidates']==[] and s['capacity_candidates']['candidates']==[]
    # layout: everything of the supervisor and of the reader is still absent, and that is a fact
    layout=s['host_layout'];assert layout['present']==['/etc/systemd/system'] and layout['findings']==[]
    assert layout['paths']['/etc/c3po-bar']==absent('/etc/c3po-bar') and layout['paths']['/etc/c3po-bar/manifests']==absent('/etc/c3po-bar')
    assert layout['paths']['/etc/systemd/system']=={'status':'COMPLETE','exists':True,'type':'dir','uid':0,'gid':0,'mode_octal':'0755','as_documented':True}
    assert layout['paths']['/etc/systemd/system/c3po-reader.timer']==absent('/etc/systemd/system/c3po-reader.timer') and set(layout['paths'])=={row[0] for row in p.LAYOUT}
    units=s['systemd']['units'];assert units['docker.service']=={'status':'COMPLETE','issues':[],'ActiveState':'active','SubState':'running','UnitFileState':'enabled'}
    assert units['c3po-reader.service']=={'status':'COMPLETE','issues':[],'LoadState':'not-found','ActiveState':'inactive','UnitFileState':''}
    assert s['systemd']['docker_commands_allowed'] is True and host.keys.index('docker_unit')<min(index for index,argv in enumerate(host.log) if argv[0].endswith('/docker'))
    assert s['systemd']['installed']==['apt-daily-upgrade.timer','c3po-host-security-snapshot.timer','c3po-security-daily.timer','c3po-security-watchdog.timer',
                                       'c3po-unattended-upgrades-healthcheck-failure.service'] and len(units)==11
    # security controller: no reboot pending, and the reboot is held by host state
    k=s['security_controller'];assert k['reboot_pending'] is False and k['reboot_flag_can_be_written'] is True and k['findings']==[]
    assert k['var_run']=={'status':'COMPLETE','exists':True,'type':'symlink','resolves_to_run':True}
    assert k['probes']['reboot_required']==absent('/run/reboot-required') and k['probes']['maintenance_hold']==absent('/etc/c3po/security-maintenance.hold')
    assert k['probes']['host_security_environment']=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','mtime_epoch':STAMP,'age_seconds':3600}
    assert k['policy']['sha256']==p.sha(POLICY) and k['policy']['automatic_reboot']=='true' and k['policy']['automatic_merge']=='true' and k['policy']['schema_known'] and k['policy']['other_key_count']==0
    assert k['automation_report']['seal_ok'] and k['automation_report']['status_reported']=='waiting_maintenance_window' and k['automation_report']['age_seconds']==3000
    assert k['automation_report']['deployed_sha']==REVISION and k['automation_report']['deployed_equals_main'] and k['automation_report']['reboot_required']=='false'
    assert k['host_report']['seal_ok'] and k['host_report']['reboot_required']=='false' and k['host_report']['all_pending']==3 and k['host_report']['age_seconds']==420
    assert {name:item['sha256'] for name,item in k['modules'].items()}=={name:p.sha(('# synthetic '+name+'\n').encode()) for name in p.MODULES}
    assert k['automatic_reboot_held_by']==['TRIAL_PIN','TRIAL_NAME_UNRECOGNISED','TRIAL_RELEASE_FILE_UNDETERMINED_WITHOUT_CONTENT'] and k['host_state_holds_automatic_reboot'] is True
    assert s['processes']['counts']=={label:{'status':'COMPLETE','count':0} for label,_ in p.PROCESS_PATTERNS} and s['processes']['pgrep_path']=='/usr/bin/pgrep'
    alerts=s['alert_channels'];assert alerts['clients_present']==['curl'] and alerts['probes']['healthcheck_ping']=={'status':'COMPLETE','exists':True,'type':'file'}
    assert alerts['probes']['reader_failure_marker_directory']==absent('/var/lib/c3po-reader') and alerts['forwarder_of_the_reader_failure_marker_defined_in_the_repository'] is False
    assert s['clock']['utc_start']==s['clock']['utc_end']==NOW.isoformat() and s['clock']['monotonic_elapsed_ms']==0
    # what was executed: absolute binaries, the signed table, nothing else; what was opened for content: the signed list, nothing else
    assert {argv[0] for argv in host.log}=={'/usr/bin/docker','/usr/bin/systemctl','/usr/bin/pgrep'}
    assert len(host.log)==o['commands_started']==53 and [key.split(':')[0] for key in host.keys].count('unit')==10
    assert host.keys.count('envflags')==1 and host.keys.count('attach')==2 and host.keys.count('network')==1 and host.keys.count('image')==4
    assert set(host.files_opened)==ALLOWED_FILE_OPENS and len(host.files_opened)==len(ALLOWED_FILE_OPENS)
    assert set(host.directories_listed)<={DATA,RAW,RAW+'/session_date=2026-10-02',RAW+'/session_date=2026-10-01',RAW+'/session_date=2026-09-30',
                                         SOURCE_DIR,SOURCE_DIR+'/events',SOURCE_DIR+'/causal_list'}
    claimed=receipt.pop('metadata_sha256');assert p.sha(p.canonical(receipt))==claimed

def test_mounts_in_another_order_on_every_inspect_do_not_make_the_receipt_partial(bound):
    """The cause of the three problems of the earlier read: the daemon lists Mounts by ranging over a map."""
    host=world(shuffle=7);api=host.docker.containers[1];orders=set()
    for _ in range(12):
        row=json.loads(host.docker.run(['container','inspect','--format',p.FAMILY_FORMAT,api['Id']])[1])
        orders.add(tuple(item['destination'] for item in row['mounts'][:-1]))
    assert len(orders)>3          # the emulated daemon really answers in different orders
    for seed in range(40):
        receipt,o,s=observed(bound,world(shuffle=seed))
        assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[],seed
        assert all(row['unchanged_during_read'] for row in s['containers']['rows']) and len(s['data_volume']['carriers'])==3
        assert [item['destination'] for item in s['containers']['rows'][0]['mounts']]==['/app/day-d-data','/app/generated-one-pagers','/legacy','/run/c3po-maintenance']

def test_a_real_restart_between_the_two_reads_is_still_a_changed_container_and_names_what_changed(bound):
    host=world()
    def restart(docker):
        if docker.inspections==13:docker.containers[1]['State'].update(Pid=4000001,StartedAt='2026-10-03T13:00:01.000000001Z')
    host.docker.before_inspect=restart;receipt,o,s=observed(bound,host);row=s['containers']['rows'][0]
    assert row['service']=='api' and row['unchanged_during_read'] is False and row['changed_keys']==['host_pid','started_at'] and row['issues']==['CONTAINER_CHANGED']
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and o['problems']==['containers:CONTAINER_CHANGED','containers:FAMILY_ROW_INCOMPLETE','data_volume:FAMILY_MOUNT_FACTS_INCOMPLETE']
    assert len(s['data_volume']['carriers'])==2 and s['data_volume']['root']['status']=='COMPLETE'          # the volume is still read


# ---------------------------------------------------------------- after provisioning
AFTER=['data_volume:TRIAL_VETO_INDEPENDENT_OF_PIN','data_volume:TRIAL_VETO_PRESENT','worker:CAPACITY_MOUNT_IS_BIND']
def test_host_after_provisioning_reports_every_object_with_owner_and_mode_and_stays_complete(bound):
    host=world(provisioned=True);receipt,o,s=observed(with_candidates(bound),host);raw=line(receipt)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[] and o['findings']==AFTER and host.fds=={} and len(raw)<55000
    clean(raw);assert RELEASE_NAME.encode() not in raw and CAPACITY.encode() not in raw and o['size_reductions']==[]
    layout=s['host_layout'];paths=layout['paths']
    assert paths['/etc/c3po-bar/token']=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','as_documented':True,
                                          'link_count':1,'size_within_1_4096':True}
    assert paths['/etc/c3po-reader/secret.env']=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','as_documented':True,'link_count':1}
    assert paths['/etc/c3po-bar/manifests']['empty'] is True and paths['/etc/c3po-bar/manifests']['listing']['classes']=={} and paths['/etc/c3po-bar/manifests']['as_documented']
    assert paths['/etc/c3po-bar']['listing']['count']==3 and paths['/etc/c3po-reader']['listing']['count']==4 and paths['/etc/c3po-reader/docker-cli']['empty']
    assert paths['/etc/c3po-reader/activation.env']==absent('/etc/c3po-reader/activation.env') and paths['/opt/c3po-bar']==absent('/opt/c3po-bar')
    assert paths['/etc/systemd/system/c3po-massive.service']=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0644','as_documented':True,'link_count':1}
    assert all(item.get('as_documented',True) for item in paths.values()) and layout['findings']==[] and len(layout['present'])==17
    j=s['journal_filesystem'];assert j['statvfs_of']=='/var/lib/c3po-bar/journal' and j['journal_root']['root_root_private'] and j['state_root']['root_root_private']
    assert (j['journal_root']['uid'],j['journal_root']['gid'],j['journal_root']['mode_octal'],j['journal_root']['device'])==(0,0,'0700',ROOT_DEV) and j['journal_parent']['root_root_private']
    assert j['journal_listing']['classes']=={'epoch_json':1,'maintenance_lock':1} and j['journal_listing']['sessions_of_this_epoch_present']=={day:False for day in p.SESSIONS}
    assert j['device_differs_from_data_volume'] is True and j['mount']['mount_point']=='/' and j['mount']['mount_point_is_the_path'] is False and j['findings']==[]
    k=s['capacity_candidates']['candidates'][0]
    assert k['exists'] and k['candidate_index']==0 and k['root_root_private'] and (k['uid'],k['gid'],k['mode_octal'],k['device'])==(0,0,'0700',ROOT_DEV)
    assert k['listing']['classes']=={'known_child':4,'other_child':1} and k['device_equals_root_filesystem'] and k['device_equals_data_volume'] is False
    assert {name:(item['exists'],item['root_root_private']) for name,item in k['children'].items()}=={name:(True,True) for name in p.CAPACITY_CHILDREN}
    assert k['under_app_dir'] is False and k['under_data_source'] is False and [set(row) for row in k['ancestors']]==[{'type','uid','gid','mode_octal','device','inode','mount_point_by_device_change'}]*4
    release=s['release_directories']['candidates'][0]
    assert release['exists'] and release['private'] and release['json_file_count']==1 and release['counters']=={} and release['candidate_index']==0
    epoch=s['source_directory']['candidates'][0]['causal_epoch']
    assert epoch['exists'] and epoch['private'] and epoch['session_dates_present']=={'2026-10-05':True,'2026-10-06':False,'2026-10-07':False,'2026-10-08':False,'2026-10-09':False}
    w=s['worker']['workers'][0]['capacity_mount'];assert w=={'present':True,'count':1,'type':'bind','rw':False,'volume':None,'is_the_unprovisioned_placeholder':False,'source_capacity_candidate_index':0}
    mount=[item for item in s['containers']['rows'][4]['mounts'] if item['destination']=='/c3po-capacity'][0]
    assert mount=={'type':'bind','rw':False,'destination':'/c3po-capacity','source_capacity_candidate_index':0}
    units=s['systemd']['units'];assert units['c3po-reader.timer']=={'status':'COMPLETE','issues':[],'LoadState':'loaded','ActiveState':'inactive','UnitFileState':'disabled'}
    assert set(p.UNIT_FILES)<=set(s['systemd']['installed']) and s['alert_channels']['probes']['reader_failure_marker_directory']['exists'] is True
    forbidden={'/etc/c3po-bar/token','/etc/c3po-reader/secret.env','/etc/c3po-reader/pins.env','/etc/c3po-reader/launcher/reader_launcher.py',
               '/var/lib/c3po-bar/journal/epoch.json',DATA+'/'+RELEASE_NAME+'/release.json'}
    assert set(host.files_opened)==ALLOWED_FILE_OPENS and not forbidden&set(host.files_opened)

def test_objects_that_are_not_as_documented_are_findings_with_their_real_owner_and_mode(bound):
    host=world(provisioned=True);tree=host.tree
    tree.add('/etc/c3po-bar/manifests',mode=0o755);tree.add('/etc/c3po-bar/manifests/2026-10-05.json',kind='file',mode=0o600)
    tree.add('/etc/c3po-bar/token',uid=1000,mode=0o644,nlink=2,content=b'');tree.add('/var/lib/c3po-bar/journal',uid=1000,gid=1000)
    tree.add('/var/lib/c3po-bar/supervisor',mode=0o750);tree.add(CAPACITY,mode=0o755);tree.add('/opt/c3po-bar')
    receipt,o,s=observed(with_candidates(bound),host);paths=s['host_layout']['paths']
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[]
    assert set(o['findings'])-set(AFTER)=={'host_layout:LAYOUT_NOT_AS_DOCUMENTED','host_layout:MANIFESTS_NOT_EMPTY','host_layout:UNDOCUMENTED_PATH_PRESENT',
                                           'journal_filesystem:JOURNAL_ROOT_NOT_ROOT_0700','journal_filesystem:STATE_ROOT_NOT_ROOT_0700','capacity_candidates:CAPACITY_ROOT_NOT_ROOT_0700'}
    assert paths['/etc/c3po-bar/token']=={'status':'COMPLETE','exists':True,'type':'file','uid':1000,'gid':0,'mode_octal':'0644','as_documented':False,'link_count':2,'size_within_1_4096':False}
    assert paths['/etc/c3po-bar/manifests']['empty'] is False and paths['/etc/c3po-bar/manifests']['listing']['classes']=={'day_file':1} and b'2026-10-05.json' not in line(receipt)
    assert s['journal_filesystem']['journal_root']['uid']==1000 and s['journal_filesystem']['state_root']['mode_octal']=='0750'


# ---------------------------------------------------------------- a pending reboot
def test_a_pending_reboot_is_a_finding_and_the_receipt_says_what_holds_it(bound):
    host=world();tree=host.tree
    tree.add('/run/reboot-required',kind='file',content=b'*** System restart required ***\n',mtime=STAMP-7200)
    tree.add('/run/reboot-required.pkgs',kind='file',content=b'never-emit-package-canary\nlinux-image-never-emit\n')
    tree.add(SECURITY+'/host-os-vulnerability-report.json',content=host_report(reboot_required=True,reboot_packages=['never-emit-package-canary','linux-image-never-emit']))
    tree.add(SECURITY+'/security-automation-report.json',content=automation_report(reboot_required=True,status='reboot_deferred',reboot_action='deferred',healthy=False))
    receipt,o,s=observed(bound,host);k=s['security_controller']
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[]
    assert o['findings']==BEFORE+['security_controller:REBOOT_PENDING','security_controller:REBOOT_PENDING_AND_HELD']
    assert k['reboot_pending'] is True and k['probes']['reboot_required']=={'status':'COMPLETE','exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0644',
                                                                           'mtime_epoch':STAMP-7200,'age_seconds':10800}
    assert k['probes']['reboot_required_packages']['exists'] is True and k['host_report']['reboot_required']=='true' and k['host_report']['reboot_package_count']==2
    assert k['automation_report']['status_reported']=='reboot_deferred' and k['automation_report']['reboot_action']=='deferred' and k['automation_report']['healthy']=='false'
    assert k['automatic_reboot_held_by'][0]=='TRIAL_PIN' and k['host_state_holds_automatic_reboot'] is True
    assert '/run/reboot-required.pkgs' not in host.files_opened and '/run/reboot-required' not in host.files_opened
    clean(line(receipt));assert b'linux-image' not in line(receipt)

def test_reboot_flag_markers_hold_and_policy_variants(bound):
    host=world();tree=host.tree
    tree.add('/run/c3po-security/reboot.pending',kind='file',content=b'never-emit-boot-canary\n');tree.add(MAINTENANCE+'/reboot.pending',kind='file',content=b'never-emit-boot-canary\n')
    tree.add('/etc/c3po/security-maintenance.hold',kind='file',mode=0o600,content=b'never-emit-hold-canary\n')
    tree.add('/etc/c3po/security-automation.json',content=b'{"schema":"C3PO_SECURITY_AUTOMATION_POLICY-v1","automatic_merge":false,"automatic_reboot":"yes","note":"never-emit-policy-canary"}')
    tree.remove('/usr/share/update-notifier/notify-reboot-required')
    receipt,o,s=observed(bound,host);k=s['security_controller']
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and k['reboot_pending'] is False and k['reboot_flag_can_be_written'] is False
    assert k['findings']==['HOLD_PRESENT','REBOOT_REQUEST_MARKER_PRESENT'] and k['policy']['automatic_reboot']=='other' and k['policy']['automatic_merge']=='false' and k['policy']['other_key_count']==1
    assert k['automatic_reboot_held_by'][:2]==['EXPLICIT_HOLD','POLICY_AUTOMATIC_REBOOT_NOT_TRUE'] and k['probes']['controller_reboot_marker']['exists'] and k['probes']['gate_reboot_marker']['exists']
    clean(line(receipt));assert set(host.files_opened)==ALLOWED_FILE_OPENS
    # the controller's files absent altogether: facts, not problems
    host=world()
    for path in ('/etc/c3po',SECURITY+'/security-automation-report.json',SECURITY+'/host-os-vulnerability-report.json','/usr/local/lib/c3po-security'):host.tree.remove(path)
    receipt,o,s=observed(bound,host);k=s['security_controller']
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and k['policy']=={'status':'COMPLETE','exists':False} and k['automation_report']=={'status':'COMPLETE','exists':False}
    assert all(item=={'status':'COMPLETE','exists':False} for item in k['modules'].values()) and 'POLICY_ABSENT' in k['automatic_reboot_held_by']

def test_var_run_as_a_directory_of_its_own_or_as_a_link_elsewhere(bound):
    host=world();host.tree.remove('/var/run');host.tree.add('/var/run/reboot-required',kind='file')
    receipt,o,s=observed(bound,host);k=s['security_controller']
    assert k['var_run']['type']=='dir' and k['var_run']['reboot_required_below_var_run']['exists'] is True and k['reboot_pending'] is True
    assert 'security_controller:VAR_RUN_IS_NOT_A_LINK_TO_RUN' in o['findings'] and 'security_controller:REBOOT_PENDING' in o['findings'] and o['problems']==[]
    host=world();host.tree.add('/var/run',target='/never-emit-target-canary')
    receipt,o,s=observed(bound,host)
    assert s['security_controller']['var_run']=={'status':'COMPLETE','exists':True,'type':'symlink','resolves_to_run':False} and o['problems']==[]
    assert 'security_controller:VAR_RUN_IS_NOT_A_LINK_TO_RUN' in o['findings'];clean(line(receipt))

@pytest.mark.parametrize('content,code',[(b'not json',b'POLICY_INVALID'),(b'[]',b'POLICY_INVALID'),(b'',b'POLICY_INVALID'),(b'{"a":1,"a":2}',b'POLICY_INVALID'),
                                         (b'{"x":"'+b'y'*5000+b'"}',b'CONTENT_SIZE_LIMIT')])
def test_an_unreadable_policy_or_report_is_a_problem_of_its_own_and_nothing_else(bound,content,code):
    host=world();host.tree.add('/etc/c3po/security-automation.json',content=content)
    host.tree.add(SECURITY+'/security-automation-report.json',content=b'{"truncated":')
    host.tree.get(SECURITY+'/host-os-vulnerability-report.json').kind='symlink'
    receipt,o,s=observed(bound,host);k=s['security_controller']
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert o['problems']==sorted({'security_controller:'+code.decode(),'security_controller:REPORT_INVALID','security_controller:NOT_A_REGULAR_FILE'})
    assert k['policy']=={'status':'UNAVAILABLE','code':code.decode()} and k['automation_report']=={'status':'UNAVAILABLE','code':'REPORT_INVALID'}
    assert k['host_report']=={'status':'UNAVAILABLE','code':'NOT_A_REGULAR_FILE','exists':True,'type':'symlink','uid':0,'gid':0,'mode_octal':'0644','mtime_epoch':STAMP,
                              'content_read':False}
    # a policy that could not be read is not taken for 'automatic_reboot is not true'
    assert not [token for token in k['automatic_reboot_held_by'] if token.startswith('POLICY')] and k['host_state_holds_automatic_reboot'] is None
    assert {name:section['status'] for name,section in s.items() if name!='security_controller'}=={name:'COMPLETE' for name in SECTIONS if name!='security_controller'}

def test_report_whose_seal_does_not_match_is_a_finding(bound):
    host=world();body=json.loads(automation_report());body['status']='failed'
    host.tree.add(SECURITY+'/security-automation-report.json',content=json.dumps(body).encode())
    receipt,o,s=observed(bound,host)
    assert s['security_controller']['automation_report']['seal_ok'] is False and s['security_controller']['automation_report']['status_reported']=='failed'
    assert 'security_controller:REPORT_SEAL_MISMATCH' in o['findings'] and o['problems']==[]
    body['status']='never-emit-status-canary';host.tree.add(SECURITY+'/security-automation-report.json',content=json.dumps(body).encode())
    receipt,o,s=observed(bound,host);assert s['security_controller']['automation_report']['status_reported']=='OTHER';clean(line(receipt))


# ---------------------------------------------------------------- a second r2d2-worker
def second(host,name='c3po-r2d2-worker-2',**options):
    template=[item for item in host.docker.containers if item['Name']=='/c3po-r2d2-worker-1'][0]
    extra=container(0x47,name,3670000,service='r2d2-worker',mounts=template['Mounts'],networks=('c3po_c3po_internal','chief-of-staff-digital_default'),
                    env=WORKER_ENV,**options)
    host.docker.containers.append(extra);return extra
def test_a_second_r2d2_worker_is_observed_counted_and_reported_as_a_finding(bound):
    host=world();second(host);receipt,o,s=observed(bound,host)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[]
    assert o['findings']==sorted(BEFORE+['containers:SERVICE_DUPLICATED','worker:WORKER_COUNT_NOT_ONE'])
    c=s['containers'];assert c['services']['r2d2-worker']=={'count':2,'running':2,'oneoff_count':0} and c['services_duplicated']==['r2d2-worker'] and len(c['rows'])==9
    assert [row['name'] for row in c['rows'] if row['service']=='r2d2-worker']==['c3po-r2d2-worker-1','c3po-r2d2-worker-2']
    w=s['worker'];assert w['count']==2 and w['running']==2 and w['exactly_one_running'] is False and len(w['workers'])==2
    assert s['worker_environment']['evaluated_count']==2 and all(item['database_url']=='SET' for item in s['worker_environment']['workers'])
    assert len(s['data_volume']['carriers'])==4 and host.keys.count('envflags')==2

def test_a_stopped_second_worker_and_a_one_off_worker_are_told_apart(bound):
    host=world();second(host,status='exited');receipt,o,s=observed(bound,host)
    assert s['containers']['services']['r2d2-worker']=={'count':2,'running':1,'oneoff_count':0} and s['worker']['exactly_one_running'] is False
    assert set(o['findings'])-set(BEFORE)=={'containers:SERVICE_DUPLICATED','containers:SERVICE_CONTAINER_NOT_RUNNING','containers:CONTAINER_NOT_RUNNING','worker:WORKER_COUNT_NOT_ONE'}
    assert o['problems']==[] and s['worker_environment']['evaluated_count']==1
    host=world();second(host,name='c3po-r2d2-worker-run-never-emit-canary',oneoff='True');receipt,o,s=observed(bound,host)
    assert s['containers']['services']['r2d2-worker']=={'count':1,'running':1,'oneoff_count':1} and s['worker']['exactly_one_running'] is True
    assert set(o['findings'])-set(BEFORE)=={'containers:ONEOFF_CONTAINER_PRESENT'} and o['problems']==[]
    row=[row for row in s['containers']['rows'] if row['oneoff']][0];assert row['name'] is None and row['name_conforming'] is False
    clean(line(receipt))

def test_no_worker_at_all_and_the_fixed_name_containers(bound):
    containers=[item for item in stack() if item['Name']!='/c3po-r2d2-worker-1']
    containers+=[container(0xd0,'c3po-massive',4100000,labels=False,networks=('c3po_c3po_internal',)),
                 container(0xd1,'c3po-reader',0,labels=False,status='exited',networks=('c3po_c3po_internal',))]
    receipt,o,s=observed(bound,world(containers))
    assert o['problems']==[] and s['containers']['services_missing']==['r2d2-worker'] and s['worker']['workers']==[] and s['worker_environment']['evaluated_count']==0
    assert s['containers']['fixed_names']=={'c3po-massive':{'present':True,'state':'running'},'c3po-reader':{'present':True,'state':'exited'}}
    # every backend container that runs is on the production image: the service without a container is reported apart
    assert set(o['findings'])-set(BEFORE)=={'containers:SERVICE_MISSING','containers:FIXED_NAME_CONTAINER_PRESENT','worker:WORKER_COUNT_NOT_ONE',
                                           'worker_environment:NO_RUNNING_WORKER_TO_EVALUATE','images:BACKEND_SERVICE_WITHOUT_RUNNING_CONTAINER'}
    assert s['images']['production_id_equals_every_running_backend'] is True and s['images']['backend_services_without_a_running_container']==['r2d2-worker']
    assert s['deploy_version']['equals_every_backend_container_revision'] is True and s['images']['backend_containers_compared']==5
    assert s['containers']['outside_stack_count']==5 and s['network']['attachments']['worker']=={'status':'COMPLETE','evaluated':False}


# ---------------------------------------------------------------- the database variable
def environment(host,env):
    worker=[item for item in host.docker.containers if item['Name']=='/c3po-r2d2-worker-1'][0];worker['Config']['Env']=env;return host
def test_the_database_variable_missing_is_a_finding_and_no_value_is_ever_received(bound):
    host=environment(world(),[item for item in WORKER_ENV if not item.startswith('C3PO_DATABASE_URL=')])
    receipt,o,s=observed(bound,host);flags=s['worker_environment']['workers'][0]
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[] and o['findings']==sorted(BEFORE+['worker_environment:DATABASE_URL_KEY_ABSENT'])
    assert flags['database_url']=='ABSENT' and flags['keys_present']['DATABASE_URL_KEY'] is False and flags['findings']==['DATABASE_URL_KEY_ABSENT']
    for env,state,finding in ((WORKER_ENV,'SET',None),([item for item in WORKER_ENV if 'DATABASE' not in item]+['C3PO_DATABASE_URL='],'EMPTY','DATABASE_URL_EMPTY'),
                              (None,'ABSENT','DATABASE_URL_KEY_ABSENT'),([],'ABSENT','DATABASE_URL_KEY_ABSENT'),
                              (['C3PO_DATABASE_URL_BACKUP=postgresql://never-emit-this-canary'],'ABSENT','DATABASE_URL_KEY_ABSENT')):
        receipt,o,s=observed(bound,environment(world(),env));flags=s['worker_environment']['workers'][0]
        assert flags['database_url']==state and flags['findings']==([finding] if finding else []) and o['problems']==[]
        clean(line(receipt))

def test_capacity_and_shadow_settings_are_reported_as_states_never_as_values(bound):
    env=WORKER_ENV+['C3PO_R2D2_V2_CAPACITY_REQUIRED=true','C3PO_R2D2_V2_CAPACITY_CONFIG_FILE=/c3po-capacity/config/never-emit-file-canary',
                    'C3PO_R2D2_V2_CAPACITY_CONFIG_SHA=never-emit-sha-canary','C3PO_R2D2_V2_CAPACITY_VETO_MODE=DISPATCH_AND_DERIVATION_ONLY',
                    'C3PO_R2D2_V2_SHADOW_ENABLED=1','C3PO_R2D2_V2_MASSIVE_BARS_ENABLED=true','C3PO_R2D2_V2_SHADOW_SOURCE_DIR=/app/day-d-data/r2d2-v2-source',
                    'C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR=/never-emit-journal-canary','C3PO_R2D2_V2_SHADOW_RELEASE_SHA=never-emit-release-canary']
    receipt,o,s=observed(bound,environment(world(),env));flags=s['worker_environment']['workers'][0]
    assert (flags['capacity_required'],flags['capacity_veto_mode'],flags['shadow_enabled'],flags['massive_bars_enabled'])==('TRUE','DOCUMENTED','SET_OTHER','TRUE')
    assert (flags['shadow_source_dir'],flags['massive_journal_dir'],flags['raw_dir'])==('CANDIDATE','SET','DOCUMENTED') and o['problems']==[]
    assert flags['keys_present']['CAPACITY_CONFIG_FILE_KEY'] and flags['keys_present']['CAPACITY_CONFIG_SHA_KEY'] and flags['keys_present']['SHADOW_RELEASE_SHA_KEY']
    assert not flags['keys_present']['SHADOW_RELEASE_FILE_KEY'] and not flags['keys_present']['LIVE_POLICY_FILE_KEY'];clean(line(receipt))


# ---------------------------------------------------------------- thousands of entries with names that look like symbols
def crowd(host,events=6000,parts=5000,root=3000,release=0,tag='NEVEREMIT',first=100):
    tree=host.tree
    for index in range(events):tree.add(SOURCE_DIR+'/events/%s-SYM%05d.%s.json'%(tag,index,'cd'*32),kind='file',mode=0o600)
    for index in range(parts):tree.add(RAW+'/session_date=2026-10-02/feed=quote-part-%05d.ndjson'%(first+index),kind='file',mode=0o644)
    for index in range(root):tree.add(DATA+'/%s-ROOT-TSLA-%05d'%(tag,index),kind='file' if index%2 else 'dir',uid=1000 if index%7==0 else 0,mode=0o600 if index%5==0 else 0o644)
    for index in range(release):tree.add(DATA+'/'+RELEASE_NAME+'/%s-NVDA-%04d.json'%(tag,index),kind='file',mode=0o600)
    # foreign names in every other directory that is counted: the journal root, the causal lists, the configuration directories, the capacity tree
    for base in ELSEWHERE:
        if present_in(tree,base):
            for index in range(9):tree.add(base+'/%s-ELSEWHERE-%02d.json'%(tag,index),kind='dir' if index%4==3 else 'file',mode=0o700 if index%4==3 else 0o600)
    return host
ELSEWHERE=('/var/lib/c3po-bar/journal',SOURCE_DIR+'/causal_list',SOURCE_DIR+'/causal_list/'+p.EPOCH,'/etc/c3po-bar/manifests','/etc/c3po-bar',
           '/etc/c3po-bar/docker-cli','/etc/c3po-reader','/etc/c3po-reader/docker-cli','/etc/c3po-reader/launcher','/var/lib/c3po-reader',CAPACITY)
def present_in(tree,path):
    try:tree.get(path);return True
    except KeyError:return False
def test_directories_with_thousands_of_symbol_like_names_are_reduced_to_counts_and_no_name_leaks(bound):
    host=crowd(world(provisioned=True),release=300);receipt,o,s=observed(with_candidates(bound),host);raw=line(receipt)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[] and o['size_reductions']==[] and len(raw)<58000 and host.fds=={}
    # none of these words can occur in a hash: a receipt carries several hexadecimal digests that change from run to run
    for word in (b'NEVEREMIT',b'SYM0',b'TSLA',b'NVDA',b'AAPL',b'MSFT',b'part-0',b'feed=',b'.ndjson',b'cd'*32,b'ab'*32,b'lost+found',b'synthetic-a',b'r2d2-v2-release-0',
                 b'-synA',b'synB',b'trial-2025',b'probe-2025',b'offload',b'synthetic-'):assert word not in raw,word
    assert set(o['findings'])-set(AFTER)=={'source_directory:EVENT_FILE_LIMIT','raw_spool:RAW_ENTRY_LIMIT','host_layout:MANIFESTS_NOT_EMPTY'}
    # every counted directory held foreign names, and each was listed: the journal root, both causal lists, the configuration directories
    assert set(ELSEWHERE)<=set(host.directories_listed) and s['journal_filesystem']['journal_listing']['classes']=={'epoch_json':1,'maintenance_lock':1,'other':9}
    assert s['source_directory']['candidates'][0]['causal_epoch']['classes']=={'day_file':1,'other':9} and s['host_layout']['paths']['/etc/c3po-bar/manifests']['listing']['classes']=={'other':9}
    assert s['capacity_candidates']['candidates'][0]['listing']['classes']=={'known_child':4,'other_child':10} and b'ELSEWHERE' not in raw
    events=s['source_directory']['candidates'][0]['events'];assert events['count']==6040 and events['capped'] is False and events['counters']=={}
    assert events['histogram']==[['file',0,0,'0600',6040]] and events['histogram_other_entries']==0
    newest=s['raw_spool']['sampled_newest_sessions'][0];assert newest['date']=='2026-10-02' and newest['parts_count']==5004 and newest['not_a_part_count']==0
    root=s['data_volume']['root'];assert root['count']==3038 and root['counters']['private_not_uid0']>=80 and len(root['histogram'])<=p.HISTOGRAM_ROWS
    assert sum(row[4] for row in root['histogram'])+root['histogram_other_entries']==3038
    release=s['release_directories']['candidates'][0];assert release['json_file_count']==301 and release['count']==301
    # the same host with every one of those entries under another name gives the same receipt, byte for byte
    other=crowd(world(provisioned=True),release=300,tag='QQQ.other name; $(x)',first=70000)
    assert line(facts(with_candidates(bound),other))==raw and set(other.directories_listed)==set(host.directories_listed)

def test_a_directory_beyond_the_cap_is_a_problem_wherever_an_answer_needs_the_whole_listing(bound):
    host=crowd(world(),events=p.CENSUS_CAP+5,parts=0,root=p.CENSUS_CAP+5);receipt,o,s=observed(bound,host)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and o['problems']==['data_volume:CENSUS_CAPPED','source_directory:CENSUS_CAPPED']
    events=s['source_directory']['candidates'][0]['events'];assert events['capped'] and events['count']==p.CENSUS_CAP and events['status']=='PARTIAL'
    root=s['data_volume']['root'];assert root['capped'] is True and root['count']==p.CENSUS_CAP and root['status']=='PARTIAL' and root['issues']==['CENSUS_CAPPED']
    assert root['controller_trial_veto']['listing_capped'] is True and root['controller_trial_veto']['remains_without_the_pin'] is True      # seen before the cap: still definite
    assert b'NEVEREMIT' not in line(receipt) and len(line(receipt))<p.RECEIPT_LIMIT

def filler(count):return [('NEVEREMIT-FILL-%05d'%index,'file',0,0o600) for index in range(count)]
def test_a_veto_clause_hidden_beyond_the_cap_is_undetermined_never_absent(bound):
    """The pin, then exactly the cap of plain entries, then a trial directory dated in the future and a name the pattern does
    not recognise: both are beyond what is listed. The answer may not be 'no veto remains'."""
    hidden_=[('.r2d2-v2-trial-20270101','dir',0,0o700),('.r2d2-v2-probe-x','dir',0,0o700)]
    host=world(entries=[('.r2d2-v2-pinned','file',0,0o600)]+filler(p.CENSUS_CAP-1)+hidden_);receipt,o,s=observed(bound,host)
    root=s['data_volume']['root'];veto=root['controller_trial_veto']          # the pin and the fillers are exactly the cap
    assert root['capped'] is True and root['count']==p.CENSUS_CAP and root['status']=='PARTIAL' and 'data_volume:CENSUS_CAPPED' in o['problems']
    assert veto['by_pin'] is True and veto['by_unrecognised_name'] is False and veto['by_current_or_future_date'] is False and veto['listing_capped'] is True
    assert veto['remains_without_the_pin']=='UNDETERMINED' and 'data_volume:TRIAL_VETO_INDEPENDENT_OF_PIN' not in o['findings']
    k=s['security_controller'];assert k['automatic_reboot_held_by']==['TRIAL_PIN'] and k['host_state_holds_automatic_reboot'] is True      # the pin was seen
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    # without the pin nothing that holds was seen, and under a cap that is not 'nothing holds'
    host=world(entries=filler(p.CENSUS_CAP)+hidden_);receipt,o,s=observed(bound,host);k=s['security_controller']
    assert s['data_volume']['root']['capped'] is True and k['automatic_reboot_held_by']==[] and k['host_state_holds_automatic_reboot'] is None
    assert s['data_volume']['root']['controller_trial_veto']['definite'] is False and 'data_volume:TRIAL_VETO_PRESENT' not in o['findings']
    # exactly the cap (the fixture adds provider=eodhd and r2d2-v2-source): the listing is whole, and the answer is definite
    host=world(entries=filler(p.CENSUS_CAP-4)+hidden_);receipt,o,s=observed(bound,host)
    assert s['data_volume']['root']['count']==p.CENSUS_CAP and s['data_volume']['root']['capped'] is False and o['problems']==[]
    assert s['data_volume']['root']['controller_trial_veto']['remains_without_the_pin'] is True
    assert s['security_controller']['host_state_holds_automatic_reboot'] is True

def test_a_journal_root_beyond_the_cap_is_a_problem_and_an_unseen_session_is_null(bound):
    host=world(provisioned=True)
    for index in range(p.CENSUS_CAP):host.tree.add('/var/lib/c3po-bar/journal/NEVEREMIT-JOURNAL-%05d'%index,kind='file',mode=0o600)
    host.tree.add('/var/lib/c3po-bar/journal/session_date=2026-10-05',mode=0o700)          # beyond the cap
    receipt,o,s=observed(with_candidates(bound),host);listing=s['journal_filesystem']['journal_listing']
    assert listing['capped'] is True and listing['status']=='PARTIAL' and o['problems']==['journal_filesystem:CENSUS_CAPPED']
    assert listing['sessions_of_this_epoch_present']=={day:None for day in p.SESSIONS} and b'NEVEREMIT' not in line(receipt)
    host=world(provisioned=True);host.tree.add('/var/lib/c3po-bar/journal/session_date=2026-10-05',mode=0o700)
    receipt,o,s=observed(with_candidates(bound),host)
    assert s['journal_filesystem']['journal_listing']['sessions_of_this_epoch_present']=={day:day=='2026-10-05' for day in p.SESSIONS} and o['problems']==[]

def test_private_inputs_not_owned_by_uid_0_and_inputs_writable_by_others_are_findings(bound):
    host=world(provisioned=True);tree=host.tree
    tree.add(SOURCE_DIR+'/events/NEVEREMIT-OWNED.'+'ef'*32+'.json',kind='file',uid=1000,gid=1000,mode=0o600)
    tree.add(SOURCE_DIR+'/causal_list',mode=0o750);tree.add(DATA+'/'+RELEASE_NAME+'/release.json',mode=0o640)
    tree.add(RAW+'/session_date=2026-10-01',mode=0o777);tree.add(RAW+'/session_date=2026-09-30/feed=trade-part-00000.ndjson',mode=0o666)
    tree.add(RAW+'/session_date=2026-10-02/NEVEREMIT-stray',kind='file',uid=1000,gid=1000,mode=0o600)
    receipt,o,s=observed(with_candidates(bound),host)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[]
    assert set(o['findings'])-set(AFTER)=={'source_directory:PRIVATE_INPUT_NOT_UID0','source_directory:INPUT_UNREADABLE_UID0_NOCAP','source_directory:SOURCE_NOT_PRIVATE',
                                           'release_directories:RELEASE_FILE_NOT_PRIVATE','raw_spool:RAW_WRITABLE_BY_OTHERS','raw_spool:PRIVATE_INPUT_NOT_UID0',
                                           'raw_spool:INPUT_UNREADABLE_UID0_NOCAP'}
    events=s['source_directory']['candidates'][0]['events']['counters'];assert events=={'not_uid0':1,'private_not_uid0':1,'uid0_nocap_unreadable':1}
    assert s['source_directory']['candidates'][0]['causal_list']['private'] is False
    newest=s['raw_spool']['sampled_newest_sessions'][0];assert newest['not_a_part_count']==1 and newest['counters']['private_not_uid0']==1
    clean(line(receipt))

def test_missing_reader_inputs_are_facts_with_findings_and_a_link_is_never_followed(bound):
    host=world();host.tree.remove(SOURCE_DIR);host.tree.remove(RAW)
    receipt,o,s=observed(bound,host)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[]
    assert set(o['findings'])-set(BEFORE)=={'source_directory:SOURCE_DIRECTORY_ABSENT','raw_spool:RAW_COMPONENT_MISSING'}
    assert s['raw_spool']['components'][-1]=={'label':'raw','exists':False} and s['source_directory']['candidates'][0]['exists'] is False
    host=world();host.tree.get(DATA+'/provider=eodhd/microstructure').kind='symlink';host.tree.get(SOURCE_DIR).kind='symlink'
    receipt,o,s=observed(bound,host)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and o['problems']==['raw_spool:SYMLINK_COMPONENT']
    assert s['source_directory']['candidates'][0]=={'status':'COMPLETE','exists':True,'type':'symlink','uid':0,'gid':0,'mode_octal':'0700','candidate_index':0}
    assert 'source_directory:SOURCE_NOT_A_DIRECTORY' in o['findings'];clean(line(receipt))


# ---------------------------------------------------------------- journal on the root filesystem
def space(host,device,available,free=None):
    host.vfs[device]=types.SimpleNamespace(f_frsize=4096,f_blocks=200000000,f_bfree=available if free is None else free,f_bavail=available,
                                           f_files=1000,f_favail=900,f_flag=4096)
@pytest.mark.parametrize('available,floor,need,findings',[(13107200,True,False,['BELOW_FIVE_SESSION_NEED']),(13107199,False,False,['BELOW_FIVE_SESSION_NEED','BELOW_FLOOR']),
                                                         (13844480,True,True,[]),(13844479,True,False,['BELOW_FIVE_SESSION_NEED']),(0,False,False,['BELOW_FIVE_SESSION_NEED','BELOW_FLOOR'])])
def test_free_space_of_the_journal_filesystem_against_the_floor_and_the_five_session_need(bound,available,floor,need,findings):
    assert 13107200*4096==53687091200==p.FLOOR_BYTES and 13844480*4096==56706990080==p.FIVE_SESSION_NEED_BYTES
    host=world();space(host,ROOT_DEV,available,free=available+1000);receipt,o,s=observed(bound,host);j=s['journal_filesystem']
    assert (j['available_ge_floor'],j['available_ge_five_session_need'])==(floor,need) and j['findings']==findings and o['problems']==[]
    assert j['margin_over_five_session_need_bytes']==available*4096-56706990080 and j['filesystem']['bytes_free_for_root_f_bfree']==(available+1000)*4096
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW'

def test_journal_on_the_same_device_as_the_data_volume_or_on_a_mount_of_its_own(bound):
    host=world(provisioned=True);host.tree.add('/var/lib/c3po-bar',dev=DATA_DEV);host.tree.add('/var/lib/c3po-bar/journal',dev=DATA_DEV)
    host.tree.get('/proc/4242/mountinfo').content+=b'130 30 259:16 /sub /var/lib/c3po-bar rw,relatime - ext4 /dev/nvme1n1 rw\n'
    receipt,o,s=observed(with_candidates(bound),host);j=s['journal_filesystem']
    assert j['device_differs_from_data_volume'] is False and 'journal_filesystem:JOURNAL_DEVICE_EQUALS_DATA_DEVICE' in o['findings'] and o['problems']==[]
    assert j['filesystem']['bytes_available_to_non_root_f_bavail']==13200000*4096 and 'journal_filesystem:BELOW_FIVE_SESSION_NEED' in o['findings']
    assert j['mount']['mount_point']=='/var/lib/c3po-bar' and j['mount']['mounted_root_is_the_filesystem_root'] is False and j['docker_root_on_the_same_device'] is False
    assert j['ancestors'][-1]['path']=='/var/lib' and j['journal_parent']['device']==DATA_DEV
    host=world();space(host,ROOT_DEV,145000000);host.vfs[ROOT_DEV].f_flag=4097
    receipt,o,s=observed(bound,host);assert 'journal_filesystem:JOURNAL_FILESYSTEM_READ_ONLY' in o['findings'] and s['journal_filesystem']['filesystem']['read_only'] is True

def test_a_link_at_var_lib_or_a_file_where_the_journal_parent_should_be(bound):
    host=world();host.tree.add('/var/lib/c3po-bar',kind='symlink',target='/never-emit-target-canary')
    receipt,o,s=observed(bound,host);j=s['journal_filesystem']
    assert o['problems']==[] and j['statvfs_of']=='/var/lib' and j['journal_parent']['type']=='symlink' and j['journal_root']=={'exists':False}
    assert 'journal_filesystem:JOURNAL_PARENT_NOT_ROOT_0700' in o['findings'];clean(line(receipt))
    host=world();host.tree.get('/var/lib').kind='symlink'
    receipt,o,s=observed(bound,host)
    assert s['journal_filesystem']=={'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT'} and 'journal_filesystem:SYMLINK_COMPONENT' in o['problems']
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and host.fds=={}

def test_mount_table_shapes(bound):
    host=world();host.tree.get('/proc/4242/mountinfo').content=(b'30 1 0:55 / / rw - zfs rpool/ROOT/never-emit-pool-canary rw\n'
        b'97 30 259:16 / /mnt/day-d-data ro,relatime - fuse.never-emit-fs-canary fileserver.never-emit-host-canary:/export rw\n')
    receipt,o,s=observed(bound,host);clean(line(receipt));assert o['problems']==[]
    assert s['data_volume']['mount']=={'status':'COMPLETE','mount_point':DATA,'mount_point_is_the_path':True,'mounted_root_is_the_filesystem_root':True,
                                       'filesystem_type':'OTHER','source_device':None,'read_write':False,'device_equals_the_directory_device':True,'source_device_withheld':True}
    assert s['journal_filesystem']['mount']['filesystem_type']=='zfs' and s['journal_filesystem']['mount']['device_equals_the_directory_device'] is False
    host=world();host.tree.get('/proc/4242/mountinfo').content=b'a line of another shape\n'+MOUNTINFO+b'30 1 x:y / /mnt/day-d-data rw - ext4 /dev/sdz rw\n'
    receipt,o,s=observed(bound,host);assert o['problems']==[] and s['data_volume']['mount']['source_device']=='/dev/nvme1n1'          # skipped, not fatal
    for content,code in ((b'garbage line\n','MOUNTINFO_INVALID'),(b'','MOUNTINFO_INVALID'),(b'30 1 x:y / / rw - ext4 /dev/root rw\n','MOUNTINFO_INVALID')):
        host=world();host.tree.get('/proc/4242/mountinfo').content=content;receipt,o,s=observed(bound,host)
        assert o['problems']==['data_volume:'+code,'journal_filesystem:'+code] and s['data_volume']['filesystem']['status']=='COMPLETE'
    host=world();host.tree.remove('/proc/4242');receipt,o,s=observed(bound,host)
    assert o['problems']==['data_volume:OS_ERROR','journal_filesystem:OS_ERROR'] and s['data_volume']['root']['status']=='COMPLETE'


# ---------------------------------------------------------------- names and values outside the allow-lists
def test_names_outside_the_allow_lists_are_withheld_and_flagged_never_copied(bound):
    containers=stack();api=containers[1]
    api['Mounts']+=[bind('/srv/never-emit-path-canary','/app/never-emit-destination-canary'),volume('never-emit-volume-canary','/var/lib/postgresql/data')]
    api['Config']['User']='never-emit-user-canary';api['Config']['Image']='registry.invalid/never-emit-image-canary:1';api['RestartCount']=3
    api['HostConfig'].update(NetworkMode='never-emit-mode-canary',UsernsMode='never-emit-userns-canary')
    api['NetworkSettings']['Networks']['never-emit-network-canary']={'IPAddress':'172.19.9.9','NetworkID':'ee'*32}
    containers.append(container(0xd5,'c3po-never-emit-service-canary-1',4100009,service='never-emit-service-canary'))
    host=world(containers);host.units['c3po-reader.timer']={'Id':'c3po-reader.timer','LoadState':'never-emit-load-canary','ActiveState':'active','UnitFileState':'enabled'}
    host.tree.get('/proc/sys/kernel/osrelease').content=b'never-emit-kernel-canary with space\n'
    receipt,o,s=observed(bound,host);raw=line(receipt);clean(raw);row=s['containers']['rows'][0]
    assert o['problems']==[] and s['runtime']['kernel']=={'status':'COMPLETE','version':None,'abi':None,'release_withheld':True}
    assert row['findings']==['IMAGE_REFERENCE_OUTSIDE_ALLOW_LIST','MOUNT_OUTSIDE_ALLOW_LIST','NETWORK_MODE_OUTSIDE_ALLOW_LIST','RESTARTS_NONZERO','USERNS_MODE_OUTSIDE_ALLOW_LIST','USER_NOT_NUMERIC']
    assert row['image_reference']=='OTHER' and row['network_mode']=='OTHER' and row['userns_mode']=='OTHER' and row['user'] is None and row['restarts']==3
    assert row['networks_other_count']==1 and row['mount_count']==6 and row['status']=='COMPLETE'
    withheld=[item for item in row['mounts'] if item.get('destination_withheld') or item.get('source_withheld')]
    assert withheld==[{'type':'volume','rw':True,'destination':'/var/lib/postgresql/data','source':None,'source_withheld':True},
                      {'type':'bind','rw':True,'destination':None,'source':None,'destination_withheld':True,'source_withheld':True}]
    assert s['containers']['stack_other_services_count']==1 and s['systemd']['units']['c3po-reader.timer']['LoadState']=='OTHER'
    assert 'systemd:UNIT_STATE_OUTSIDE_ALLOW_LIST' in o['findings'] and s['network']['attachments']['db']['other_network_count']==0

def test_numeric_user_is_emitted_and_a_malformed_mount_is_a_problem(bound):
    containers=stack();containers[1]['Config']['User']='1000:1000';containers[3]['Mounts'][1]['Destination']='bad path with space'
    receipt,o,s=observed(bound,world(containers));rows=s['containers']['rows']
    assert rows[0]['user']=='1000:1000' and rows[4]['issues']==['MOUNT_INVALID'] and {'withheld':True} in rows[4]['mounts']
    assert o['problems']==['containers:FAMILY_ROW_INCOMPLETE','containers:MOUNT_INVALID'] and b'bad path' not in line(receipt)

def test_data_mount_source_outside_the_signed_list_is_never_walked(bound):
    containers=stack()
    for item in containers:
        for mount in item['Mounts']:
            if mount['Destination']=='/app/day-d-data':mount['Source']='/srv/never-emit-path-canary'
    host=world(containers);host.tree.add('/srv/never-emit-path-canary/NEVEREMIT-entry')
    receipt,o,s=observed(bound,host);a=s['data_volume'];clean(line(receipt))
    assert a['status']=='UNAVAILABLE' and a['source'] is None and 'data_volume:DATA_SOURCE_NOT_IN_SCOPE' in o['problems'] and '/srv/never-emit-path-canary' not in host.directories_listed
    assert all(item['source_in_data_sources'] is False for item in a['carriers']) and s['raw_spool']=={'status':'UNAVAILABLE','code':'DATA_SOURCE_UNAVAILABLE'}
    assert s['journal_filesystem']['device_differs_from_data_volume'] is None and s['journal_filesystem']['status']=='COMPLETE'

def test_two_sources_disagreeing_and_a_named_volume(bound):
    containers=stack();containers[3]['Mounts'][0]=volume('c3po_c3po_day_d_data','/app/day-d-data')
    receipt,o,s=observed(bound,world(containers))
    assert s['data_volume']['distinct_source_count']==2 and 'data_volume:DATA_SOURCE_DISAGREE' in o['problems'] and s['data_volume']['source'] is None
    containers=stack()
    for item in containers:item['Mounts']=[volume('c3po_c3po_day_d_data','/app/day-d-data') if mount['Destination']=='/app/day-d-data' else mount for mount in item['Mounts']]
    host=world(containers);host.tree.add('/var/lib/docker/volumes/c3po_c3po_day_d_data/_data/only-entry')
    receipt,o,s=observed(bound,host);a=s['data_volume']
    assert a['source']=='/var/lib/docker/volumes/c3po_c3po_day_d_data/_data' and a['root']['count']==1 and a['root']['pin']=={'exists':False}
    assert a['root']['controller_trial_veto']['definite'] is False and a['root']['controller_trial_veto']['remains_without_the_pin'] is False
    assert s['journal_filesystem']['device_differs_from_data_volume'] is False and 'journal_filesystem:JOURNAL_DEVICE_EQUALS_DATA_DEVICE' in o['findings']
    assert 'raw_spool:RAW_COMPONENT_MISSING' in o['findings'] and o['problems']==[]

def test_no_container_mounts_the_data_destination_the_signed_default_is_still_read(bound):
    containers=stack()
    for item in containers:item['Mounts']=[mount for mount in item['Mounts'] if mount['Destination']!='/app/day-d-data']
    receipt,o,s=observed(bound,world(containers));a=s['data_volume']
    assert a['source']==DATA and a['source_basis']=='SIGNED_DEFAULT_NO_CARRIER' and a['carriers']==[] and 'data_volume:DATA_MOUNT_NOT_FOUND' in o['findings']
    assert o['problems']==[] and a['root']['count']==37 and 'worker:WORKER_DATA_MOUNT_ABSENT' in o['findings']

def test_trial_veto_clauses_follow_the_controller_guard(bound):
    def veto(entries):
        receipt,o,s=observed(bound,world(entries=entries));return s['data_volume']['root']['controller_trial_veto'],s['data_volume']['root']['classes'],o
    v,classes,o=veto([('plain','dir',0,0o755)])
    assert v['definite'] is False and v['remains_without_the_pin'] is False and v['by_release_file']=='NONE' and 'data_volume:TRIAL_VETO_PRESENT' not in o['findings']
    v,classes,o=veto([('.r2d2-v2-pinned','symlink',0,0o777)]);assert v['by_pin'] and v['definite'] and v['remains_without_the_pin'] is False
    v,classes,o=veto([('.r2d2-v2-trial-20261003','dir',0,0o700)]);assert v['by_current_or_future_date'] and v['remains_without_the_pin'] is True      # today, UTC
    v,classes,o=veto([('.r2d2-v2-trial-20250109-r3','dir',0,0o700)]);assert not v['definite'] and v['remains_without_the_pin']=='UNDETERMINED' and classes=={'trial_or_probe':1,'trial_or_probe_dated_in_the_past':1,'provider_directory':1}
    v,classes,o=veto([('.r2d2-v2-probe-20261340','dir',0,0o700)]);assert v['controller_would_fail_on_a_date'] and not v['definite']
    v,classes,o=veto([('.r2d2-v2-probe-20250110','symlink',0,0o777)]);assert v['by_symlink'] and v['definite']
    v,classes,o=veto([('.r2d2-v2-trial-x','dir',0,0o700)]);assert v['by_unrecognised_name'] and v['remains_without_the_pin'] is True
    v,classes,o=veto([('r2d2-v2-release-x.json','symlink',0,0o777)]);assert v['by_release_file']=='SYMLINK' and v['definite']
    v,classes,o=veto([('r2d2-v2-release-x.json','file',0,0o600)]);assert v['by_release_file']=='UNDETERMINED_WITHOUT_CONTENT' and v['remains_without_the_pin']=='UNDETERMINED'
    v,classes,o=veto([('r2d2-v2-release-x.json.bak','file',0,0o600),('xr2d2-v2-release-y.json','file',0,0o600)]);assert v['by_release_file']=='NONE' and 'release_json' not in classes
    guard=Path('/offline/optional-references/opsart/scripts/c3po_security_guard.py')
    if guard.is_file():          # the repository's own expression, read only to keep the class definition honest
        text_=guard.read_text();assert p.NAME_CLASSES['trial_or_probe'] in text_ and "startswith(('.r2d2-v2-trial-', '.r2d2-v2-probe-'))" in text_
        assert "path.name.startswith('r2d2-v2-release-') and path.suffix == '.json'" in text_ and "base / '.r2d2-v2-pinned'" in text_


# ---------------------------------------------------------------- each external command failing, timing out or answering garbage
DEPENDENT={'ps':'containers','class':'containers','family':'containers','envflags':'worker_environment','attach':'network','network':'network',
           'image':'images','version':'docker_daemon','docker_unit':'systemd'}
def section_of(key):return DEPENDENT.get(key) or ('systemd' if key.startswith('unit:') else 'processes')
INDEPENDENT=('runtime','journal_filesystem','host_layout','alert_channels','security_controller','clock')
@pytest.mark.parametrize('key',sorted(p.COMMANDS))
@pytest.mark.parametrize('mode',['exit','timeout','garbage','empty'])
def test_each_external_command_failing_marks_its_own_family_and_never_aborts_the_others(bound,key,mode):
    host=world();tool=p.COMMANDS[key][0]
    if mode=='exit':host.answers[key]=(2 if tool=='pgrep' else 1,b'')
    elif mode=='timeout':host.hang.add(key)
    elif mode=='garbage':host.answers[key]=(0,b'{"never-emit-garbage-canary":\xff\n')
    else:host.answers[key]=(0,b'')
    receipt,o,s=observed(bound,host);section=section_of(key);raw=line(receipt);clean(raw)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and o['status']=='PARTIAL_OBSERVED' and s[section]['status']!='COMPLETE'
    assert any(problem.startswith(section+':') for problem in o['problems']) and host.fds=={}
    assert {name:s[name]['status'] for name in INDEPENDENT}=={name:'COMPLETE' for name in INDEPENDENT}
    assert s['data_volume']['root']['status']=='COMPLETE' and s['data_volume']['filesystem']['status']=='COMPLETE'          # the volume is read whatever docker does
    assert s['raw_spool']['status']=='COMPLETE' and s['source_directory']['status']=='COMPLETE'
    # whatever failed, no section says of the containers what it could not see: a negative finding needs every container classified and read
    if key in ('ps','class','family','docker_unit'):assert not NEGATIVE&set(o['findings']),sorted(NEGATIVE&set(o['findings']))
    if key=='docker_unit':
        # the state of docker.service was not observed: not one docker command is started, and every docker family says why
        assert docker_argv(host)==[] and s['systemd']['docker_commands_allowed'] is False
        assert s['docker_daemon']==s['containers']=={'status':'UNAVAILABLE','code':'DOCKER_SKIPPED_UNIT_UNOBSERVED'}
        assert {'images:DOCKER_SKIPPED_UNIT_UNOBSERVED','worker:CONTAINERS_UNOBSERVED','network:CONTAINERS_UNOBSERVED','worker_environment:CONTAINERS_UNOBSERVED',
                'data_volume:DATA_MOUNT_UNOBSERVED'}<=set(o['problems'])
    elif tool!='docker':assert s['containers']['status']=='COMPLETE' and s['images']['status']=='COMPLETE'
    if tool!='systemctl' and key not in ('ps','class','family') and mode!='timeout':assert s['systemd']['status']=='COMPLETE'
    if tool!='pgrep':assert s['processes']['status']=='COMPLETE'
    if mode=='timeout':
        hung=[index for index,name in enumerate(host.keys) if name==key]
        assert len(hung)<=p.MAX_TOOL_TIMEOUTS and all(p.COMMANDS[name][0]!=tool for name in host.keys[hung[-1]+1:]) or len(hung)<p.MAX_TOOL_TIMEOUTS
    claimed=receipt.pop('metadata_sha256');assert p.sha(p.canonical(receipt))==claimed

@pytest.mark.parametrize('key,code',[('envflags','worker_environment:ENVFLAGS_COMMAND_FAILED'),('attach','network:ATTACH_COMMAND_FAILED'),
                                     ('network','network:NETWORK_COMMAND_FAILED'),('version','docker_daemon:COMMAND_FAILED'),
                                     ('process:shadow_worker','processes:PGREP_FAILED'),('unit:c3po-reader.timer','systemd:COMMAND_FAILED')])
def test_a_new_template_or_tool_that_the_host_rejects_costs_exactly_one_problem(bound,key,code):
    host=world();host.answers[key]=(3 if key.startswith('process') else 1,b'')
    receipt,o,s=observed(bound,host)
    assert o['problems']==[code] and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and o['findings']==BEFORE
    assert [name for name,section in s.items() if section['status']!='COMPLETE']==[code.split(':')[0]]

def test_image_tags_that_do_not_resolve_are_facts_except_the_production_tag(bound):
    host=world();host.docker.images=[item for item in host.docker.images if item['Id'] not in (ROLLBACK_IMAGE,)]
    receipt,o,s=observed(bound,host);i=s['images']
    assert o['problems']==[] and i['tags']['c3po/backend:rollback']=={'status':'COMPLETE','resolved':False} and i['rollback_differs_from_production'] is None
    host=world();host.docker.images=[item for item in host.docker.images if item['Id']!=BACKEND_IMAGE]
    receipt,o,s=observed(bound,host);i=s['images']
    assert i['tags']['c3po/backend:production']=={'status':'UNAVAILABLE','code':'IMAGE_UNRESOLVED','returncode':1}
    assert o['problems']==['images:IMAGE_UNRESOLVED'] and i['production_id_equals_every_running_backend'] is None and i['stack_images_without_a_listed_tag'][0]['code']=='IMAGE_UNRESOLVED'
    # exit 1 means 'no such tag' only when the daemon resolved the production tag in the same run: here it did not
    host=world();host.docker.images=[item for item in host.docker.images if item['Id'] not in (BACKEND_IMAGE,ROLLBACK_IMAGE)]
    receipt,o,s=observed(bound,host);i=s['images']
    assert i['tags']['c3po/backend:rollback']=={'status':'UNAVAILABLE','code':'IMAGE_UNRESOLVED','returncode':1} and i['rollback_differs_from_production'] is None
    # a tag that a running container was created from cannot be accepted as absent
    host=world();host.docker.images=[item for item in host.docker.images if item['Id']!=DATABASE_IMAGE]
    receipt,o,s=observed(bound,host);i=s['images']
    assert i['tags']['c3po/database:production']=={'status':'COMPLETE','resolved':False} and i['status']=='PARTIAL'
    assert 'images:IMAGE_REFERENCED_TAG_UNRESOLVED' in o['problems'] and 'db' not in i['service_tag_equals_running']
    host=world();host.docker.images[0]['RepoTags']=['c3po/backend:rollback'];host.docker.images[1]['RepoTags']=['c3po/backend:production','c3po/backend:massive-supervisor-epoch03']
    receipt,o,s=observed(bound,host);i=s['images']          # the tag was moved: the running image is not the production tag any more
    assert i['production_id_equals_every_running_backend'] is False and i['tags']['c3po/backend:production']['repo_tags']==['c3po/backend:production']
    assert i['tags']['c3po/backend:production']['retention_tag_count']==1 and i['tags']['c3po/backend:production']['other_tag_count']==0 and b'epoch03' not in line(receipt)
    assert {'images:PRODUCTION_TAG_NOT_RUNNING_IMAGE','images:REVISION_LABEL_MISMATCH','deploy_version:DEPLOY_VERSION_NOT_THE_RUNNING_REVISION'}<=set(o['findings']) and o['problems']==[]

def test_deploy_version_shapes(bound):
    for content,code in ((b'not a revision\n','DEPLOY_VERSION_INVALID'),(REVISION.encode()+b'\n\n','DEPLOY_VERSION_INVALID'),(b'x'*65,'CONTENT_SIZE_LIMIT')):
        host=world();host.tree.add(APP+'/.deploy-version',content=content);receipt,o,s=observed(bound,host)
        assert s['deploy_version']=={'status':'UNAVAILABLE','code':code} and o['problems']==['deploy_version:'+code] and b'not a revision' not in line(receipt)
    host=world();host.tree.add(APP+'/.deploy-version',content=('4d'*20).encode());receipt,o,s=observed(bound,host)
    assert s['deploy_version']['revision']=='4d'*20 and 'deploy_version:DEPLOY_VERSION_NOT_THE_RUNNING_REVISION' in o['findings'] and o['problems']==[]
    host=world();host.tree.remove(APP+'/.deploy-version');receipt,o,s=observed(bound,host)
    assert s['deploy_version']['file']=={'status':'COMPLETE','exists':False} and 'deploy_version:DEPLOY_VERSION_ABSENT' in o['findings'] and o['problems']==[]

QUIET=('runtime','journal_filesystem','host_layout','raw_spool','source_directory','alert_channels','security_controller')
def test_hung_tools_open_their_circuits_and_the_whole_run_stays_inside_the_budget(bound):
    """Worst case of waiting. Simulated time advances by the call limit at every hung call."""
    def tick(mono):
        def step(current):mono[0]+=p.CALL_SECONDS
        return step
    # all three tools hang: systemctl never answers about docker.service, so no docker command is started at all; systemctl is
    # skipped after two timeouts and the first pgrep timeout ends the 15 s that the two tools share
    host=world();mono=[0.0];host.hang|={'docker','systemctl','pgrep'};host.on_run=tick(mono);began=time.perf_counter()
    receipt,o,s=observed(bound,host,monotonic=lambda:mono[0]);elapsed=time.perf_counter()-began
    assert [argv[0].rsplit('/',1)[1] for argv in host.log]==['systemctl','systemctl','pgrep'] and docker_argv(host)==[]
    assert mono[0]==15.0==p.SYSTEM_TOOLS_SECONDS<p.MAX_SECONDS and elapsed<10
    assert o['status']=='PARTIAL_OBSERVED' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'          # partial, not expired
    assert [value.get('code') for value in s['processes']['counts'].values()]==['COMMAND_TIMEOUT']+['SYSTEM_TOOLS_BUDGET_EXHAUSTED']*3
    assert s['clock']['monotonic_elapsed_ms']==15000 and s['docker_daemon']==s['containers']=={'status':'UNAVAILABLE','code':'DOCKER_SKIPPED_UNIT_UNOBSERVED'}
    assert s['network']=={'status':'UNAVAILABLE','code':'CONTAINERS_UNOBSERVED'}
    assert {value.get('code') for value in s['systemd']['units'].values()}=={'COMMAND_TIMEOUT','COMMAND_SKIPPED_AFTER_TIMEOUT'}
    assert {name:s[name]['status'] for name in QUIET}=={name:'COMPLETE' for name in QUIET}
    assert s['data_volume']['source_basis']=='SIGNED_DEFAULT_NO_CARRIER' and s['data_volume']['root']['count']==37 and 'data_volume:DATA_MOUNT_UNOBSERVED' in o['problems']
    # systemctl answers, docker and pgrep hang: two timeouts each, then skipped
    host=world();mono=[0.0];host.hang|={'docker','pgrep'}
    def only_hung(current):
        if current.log[-1][0].rsplit('/',1)[1] in ('docker','pgrep'):mono[0]+=p.CALL_SECONDS
    host.on_run=only_hung;receipt,o,s=observed(bound,host,monotonic=lambda:mono[0])
    assert len(docker_argv(host))==p.MAX_TOOL_TIMEOUTS and mono[0]==20.0 and o['status']=='PARTIAL_OBSERVED'
    assert s['docker_daemon']=={'status':'UNAVAILABLE','code':'COMMAND_TIMEOUT'} and s['containers']=={'status':'UNAVAILABLE','code':'COMMAND_TIMEOUT'}
    assert s['systemd']['status']=='COMPLETE' and {name:s[name]['status'] for name in QUIET}=={name:'COMPLETE' for name in QUIET}

def test_a_daemon_that_is_slow_without_ever_timing_out_cannot_use_up_the_window(bound):
    """Each docker command takes 4.5 s and answers: no timeout, no circuit. The docker families stop at their own budget, and
    everything that needs no docker (read first) and the data volume (read after) is still observed."""
    host=world();mono=[0.0]
    def slow(current):
        if current.log[-1][0].endswith('/docker'):mono[0]+=4.5
    host.on_run=slow;receipt,o,s=observed(bound,host,monotonic=lambda:mono[0])
    assert o['status']=='PARTIAL_OBSERVED' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'          # partial, NOT expired
    assert len(docker_argv(host))==6 and mono[0]==27.0<=p.DOCKER_SECONDS+p.CALL_SECONDS          # 0, 4.5 ... 22.5 start; at 27 s the budget is spent
    codes={problem.split(':')[1] for problem in o['problems'] if problem.split(':')[0] in ('containers','images')}
    assert 'DOCKER_BUDGET_EXHAUSTED' in codes and 'containers:DOCKER_BUDGET_EXHAUSTED' in o['problems'] and not NEGATIVE&set(o['findings'])
    for name in ('runtime','journal_filesystem','host_layout','security_controller','alert_channels','systemd','processes','raw_spool','source_directory'):
        assert s[name]['status']=='COMPLETE',name
    assert s['data_volume']['root']['status']=='COMPLETE' and s['data_volume']['filesystem']['status']=='COMPLETE' and s['docker_daemon']['status']=='COMPLETE'
    assert s['journal_filesystem']['available_ge_five_session_need'] is True and s['security_controller']['reboot_pending'] is False
    assert s['journal_filesystem']['device_differs_from_data_volume'] is True          # joined at the end from two numbers already observed

def test_system_tools_that_are_slow_without_ever_timing_out_stop_at_their_shared_budget(bound):
    """Each systemctl and pgrep command takes 4.5 s and answers: no timeout, no circuit. The two tools stop at the budget they
    share. docker.service is the first unit asked, so the docker families and, after them, the data volume are still read."""
    host=world();mono=[0.0]
    def slow(current):
        if not current.log[-1][0].endswith('/docker'):mono[0]+=4.5
    host.on_run=slow;receipt,o,s=observed(bound,host,monotonic=lambda:mono[0])
    assert o['status']=='PARTIAL_OBSERVED' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'          # partial, NOT expired
    system=[key for key in host.keys if p.COMMANDS[key][0]!='docker']
    assert system==['docker_unit']+['unit:'+unit for unit in p.UNITS[:3]]          # 0, 4.5, 9 and 13.5 s start; at 18 s the budget is spent
    assert mono[0]==18.0<=p.SYSTEM_TOOLS_SECONDS+p.CALL_SECONDS and not [key for key in host.keys if key.startswith('process:')]
    assert o['problems']==['processes:SYSTEM_TOOLS_BUDGET_EXHAUSTED','systemd:SYSTEM_TOOLS_BUDGET_EXHAUSTED'] and not NEGATIVE&set(o['findings'])
    units=s['systemd']['units'];assert units['docker.service']['ActiveState']=='active' and s['systemd']['docker_commands_allowed'] is True
    assert [units[unit]['status'] for unit in p.UNITS[:3]]==['COMPLETE']*3 and s['systemd']['status']=='PARTIAL'
    assert all(units[unit]=={'status':'UNAVAILABLE','code':'SYSTEM_TOOLS_BUDGET_EXHAUSTED'} for unit in p.UNITS[3:]) and len(p.UNITS[3:])==7
    assert s['processes']['status']=='UNAVAILABLE' and set(s['processes']['counts'])=={label for label,_ in p.PROCESS_PATTERNS}
    assert all(value=={'status':'UNAVAILABLE','code':'SYSTEM_TOOLS_BUDGET_EXHAUSTED'} for value in s['processes']['counts'].values())
    for name in sorted(set(s)-{'systemd','processes'}):assert s[name]['status']=='COMPLETE',name          # docker and the volume lose nothing
    assert len(docker_argv(host))==38 and s['data_volume']['root']['count']==37 and s['security_controller']['reboot_pending'] is False

def test_slow_systemctl_alone_leaves_pgrep_what_is_left_of_the_shared_budget_and_slow_pgrep_alone_is_answered_whole(bound):
    host=world();mono=[0.0]
    def slow_systemctl(current):
        if current.log[-1][0].endswith('/systemctl'):mono[0]+=1.3
    host.on_run=slow_systemctl;receipt,o,s=observed(bound,host,monotonic=lambda:mono[0])          # 11 calls of 1.3 s: 14.3 s, inside the budget
    assert o['problems']==[] and round(mono[0],1)==14.3 and len([key for key in host.keys if key.startswith('process:')])==4
    host=world();mono=[0.0]
    def slower_systemctl(current):
        if current.log[-1][0].endswith('/systemctl'):mono[0]+=1.4
    host.on_run=slower_systemctl;receipt,o,s=observed(bound,host,monotonic=lambda:mono[0])          # 11 calls of 1.4 s: 15.4 s, pgrep finds the budget spent
    assert o['problems']==['processes:SYSTEM_TOOLS_BUDGET_EXHAUSTED'] and s['systemd']['status']=='COMPLETE' and not [key for key in host.keys if key.startswith('process:')]
    host=world();mono=[0.0]
    def slow_pgrep(current):
        if current.log[-1][0].endswith('/pgrep'):mono[0]+=4.9
    host.on_run=slow_pgrep;receipt,o,s=observed(bound,host,monotonic=lambda:mono[0])          # 0, 4.9, 9.8 and 14.7 s start: all four are answered
    assert o['problems']==[] and round(mono[0],1)==19.6 and receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW'

def test_every_tool_slow_without_ever_timing_out_still_leaves_the_data_volume_its_time(bound):
    """The worst case of slowness that the contract states: every command of every tool takes 4.9 s and answers. The two system
    tools end at 19.6 s, the docker families 29.4 s later, and the volume is read with more than 10 s of the 60 left."""
    host=world();mono=[0.0]
    def slow(current):mono[0]+=4.9
    host.on_run=slow;receipt,o,s=observed(bound,host,monotonic=lambda:mono[0])
    assert o['status']=='PARTIAL_OBSERVED' and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'          # partial, NOT expired
    assert [argv[0].rsplit('/',1)[1] for argv in host.log]==['systemctl']*4+['docker']*6 and round(mono[0],1)==49.0
    assert mono[0]<=p.SYSTEM_TOOLS_SECONDS+p.CALL_SECONDS+p.DOCKER_SECONDS+p.CALL_SECONDS==50 and s['clock']['monotonic_elapsed_ms'] in (48999,49000)
    codes={problem.split(':')[1] for problem in o['problems']};assert {'SYSTEM_TOOLS_BUDGET_EXHAUSTED','DOCKER_BUDGET_EXHAUSTED'}<=codes and not codes&set(p.EXPIRED)
    for name in ('runtime','journal_filesystem','host_layout','security_controller','alert_channels','raw_spool','source_directory'):
        assert s[name]['status']=='COMPLETE',name
    assert s['data_volume']['root']['status']=='COMPLETE' and s['data_volume']['root']['count']==37 and s['data_volume']['filesystem']['status']=='COMPLETE'

def test_the_families_that_need_no_docker_are_read_before_the_first_docker_command(bound):
    host=world(provisioned=True);order=[]
    original=host.names
    def names(fd):
        order.append(('list',host.fds[fd][0].path,len(docker_argv(host))));return original(fd)
    host.names=names;receipt,o,s=observed(with_candidates(bound),host)
    first=min(index for index,argv in enumerate(host.log) if argv[0].endswith('/docker'))
    assert set(host.keys[:first])=={key for key in p.COMMANDS if p.COMMANDS[key][0]!='docker'} and len(host.keys[:first])==15
    before={path for kind_,path,started in order if started==0};after={path for kind_,path,started in order if started}
    assert {'/var/lib/c3po-bar/journal','/etc/c3po-bar','/etc/c3po-bar/manifests','/etc/c3po-reader','/var/lib/c3po-reader'}<=before
    assert DATA in after and not {path for path in before if path.startswith(DATA)}
    assert list(s)[-1]=='clock' and o['problems']==[]

def test_total_runtime_of_a_whole_observation_on_the_emulated_host(bound):
    began=time.perf_counter();receipt,o,s=observed(with_candidates(bound),crowd(world(provisioned=True),release=300));elapsed=time.perf_counter()-began
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and elapsed<20          # 14,000 entries, 53 commands, pure-Python template engine
    assert p.MAX_SECONDS==60 and p.CALL_SECONDS==5 and p.CENSUS_CAP==20000 and o['commands_started']==53

def test_real_filesystem_census_of_thousands_of_entries_is_fast_and_holds_no_name(tmp_path):
    """The real Native on a local temporary directory: descend, census, statvfs and a bounded read, as the host would run them."""
    root=tmp_path.resolve()/'tree';root.mkdir(mode=0o700)
    for index in range(4000):(root/('NEVEREMIT-%05d.json'%index)).write_bytes(b'x')
    (root/'sub').mkdir();os.symlink('sub',root/'link');(root/'small').write_bytes(b'0123456789')
    ctx=p.Context(LocalNative(),lambda:30.0);rows=[];began=time.perf_counter()
    with p.Held(ctx.host) as held:
        fd=held.keep(p.descend(ctx.host,str(root),ctx.check,rows))
        listing,dates=p.census(ctx,fd,lambda name,info:[('json' if name.endswith('.json') else 'other',None)],live=True)
        facts_,raw=p.read_small(ctx,fd,'small',64);linked,_=p.read_small(ctx,fd,'link',64);missing,_=p.read_small(ctx,fd,'nothing',64)
        space=p.filesystem(ctx.host,fd);entered,opened=p.enter(ctx,fd,'link')
        with pytest.raises(p.Refused,match='CONTENT_SIZE_LIMIT'):p.read_small(ctx,fd,'small',9)
    elapsed=time.perf_counter()-began
    assert listing['count']==4003 and listing['classes']=={'json':4000,'other':3} and listing['counters']['symlink']==1 and elapsed<10
    assert b'NEVEREMIT' not in p.canonical(listing) and dates=={} and raw==b'0123456789' and facts_['content_read'] is True
    assert linked['type']=='symlink' and linked['content_read'] is False and missing=={'status':'COMPLETE','exists':False}
    assert space['bytes_total']>0 and opened is None and p.kind(entered.st_mode)=='symlink' and rows[-1]['path']==str(root) and rows[-1]['mode_octal']=='0700'
    assert p.probe(ctx,str(root/'absent'/'deeper'))=={'status':'COMPLETE','exists':False,'absent_at':str(root/'absent')}
    assert p.probe(ctx,str(root/'link'/'deeper'))=={'status':'UNAVAILABLE','code':'SYMLINK_COMPONENT','at':str(root/'link')}
    assert p.linux_device(66320)==(259,16) and p.linux_device(66305)==(259,1) and p.linux_device(0x800)==(8,0) and p.linux_device(0)==(0,0)


# ---------------------------------------------------------------- an unexpected extra field
def widened(host,key):
    def answer(argv):
        code,out=host.docker.run(argv[3:]);rows=[]
        for row in out.splitlines():
            value=json.loads(row);value['unexpected_field']='never-emit-extra-canary';rows.append(json.dumps(value).encode())
        return code,b'\n'.join(rows)+b'\n'
    host.answers[key]=answer;return host
@pytest.mark.parametrize('key,problems',[('ps',['containers:CONTAINER_LIST_INVALID']),('class',['containers:FAMILY_EMPTY','containers:UNCLASSIFIED_CONTAINERS']),
                                         ('family',['containers:FAMILY_METADATA_INVALID','containers:FAMILY_ROW_INCOMPLETE']),
                                         ('envflags',['worker_environment:ENVFLAGS_INVALID']),('attach',['network:ATTACH_INVALID']),
                                         ('network',['network:NETWORK_INVALID']),('image',['images:IMAGE_METADATA_INVALID'])])
def test_an_unexpected_extra_field_in_a_command_answer_is_refused_never_copied(bound,key,problems):
    receipt,o,s=observed(bound,widened(world(),key));clean(line(receipt))
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and set(problems)<=set(o['problems']) and b'unexpected_field' not in line(receipt)
    assert all(problem.split(':')[0] in ('containers','worker','worker_environment','network','images','deploy_version','data_volume') for problem in o['problems'])
    assert not NEGATIVE&set(o['findings'])

def test_unexpected_tokens_values_and_lines_in_the_answers_of_the_new_commands(bound):
    worker_id='46'*32
    for answer,code in (((0,json.dumps({'id':worker_id,'flags':['DATABASE_URL_KEY','NEVER_EMIT_TOKEN_CANARY',None]}).encode()),'ENVFLAGS_INVALID'),
                        ((0,json.dumps({'id':worker_id,'flags':['postgresql://never-emit-this-canary',None]}).encode()),'ENVFLAGS_INVALID'),
                        ((0,json.dumps({'id':worker_id,'flags':['DATABASE_URL_KEY']}).encode()),'ENVFLAGS_INVALID'),
                        ((0,json.dumps({'id':'47'*32,'flags':[None]}).encode()),'ENVFLAGS_INVALID'),
                        ((0,json.dumps({'id':worker_id,'flags':['DATABASE_URL_KEY']*70+[None]}).encode()),'ENVFLAGS_INVALID')):
        host=world();host.answers['envflags']=answer;receipt,o,s=observed(bound,host);clean(line(receipt))
        assert o['problems']==['worker_environment:'+code] and b'NEVER_EMIT' not in line(receipt)
    host=world();host.answers['network']=(0,json.dumps({'name':'never-emit-network-canary','driver':'bridge','scope':'local','internal':True,'attachable':False,'containers':[None]}).encode())
    receipt,o,s=observed(bound,host);clean(line(receipt));assert o['problems']==['network:NETWORK_INVALID']
    host=world();host.answers['network']=(0,json.dumps({'name':'c3po_c3po_internal','driver':'never-emit-driver-canary','scope':'local','internal':False,'attachable':True,
                                                        'containers':['ep-never-emit-endpoint-canary',None]}).encode())
    receipt,o,s=observed(bound,host);clean(line(receipt));n=s['network']
    assert o['problems']==[] and n['inspect']['driver']=='OTHER' and n['inspect']['attached_not_a_container_id_count']==1 and n['db_attached_by_network_inspect'] is False
    assert 'network:DB_NOT_ON_NETWORK' in o['findings']
    host=world();host.answers['attach']=(0,json.dumps({'id':'40'*32,'networks':[{'name':'c3po_c3po_internal','network_id':'never-emit-id-canary'},None]}).encode())
    receipt,o,s=observed(bound,host);clean(line(receipt));assert 'network:ATTACH_INVALID' in o['problems']
    host=world();host.answers['process:reader_launcher']=(0,b'2\nnever-emit-line-canary\n');receipt,o,s=observed(bound,host);clean(line(receipt))
    assert o['problems']==['processes:PGREP_OUTPUT_INVALID']
    for answer,problems in (((0,b'0\n'),['processes:PGREP_OUTPUT_INVALID']),((1,b'3\n'),['processes:PGREP_OUTPUT_INVALID']),((1,b'0\n'),[])):
        host=world();host.answers['process:reader_launcher']=answer;receipt,o,s=observed(bound,host);assert o['problems']==problems
    host=world();host.processes={'r2d2_v2_shadow_worker':2,'manifest_writer\\.py':1};receipt,o,s=observed(bound,host)
    assert s['processes']['counts']['shadow_worker']['count']==2 and s['processes']['counts']['manifest_writer']['count']==1 and o['problems']==[]
    assert 'processes:V2_PROCESS_RUNNING' in o['findings']
    host=world();host.answers['docker_unit']=(0,b'Id=docker.service\nActiveState=active\nSubState=running\nUnitFileState=enabled\nDescription=never-emit-line-canary\n')
    receipt,o,s=observed(bound,host);clean(line(receipt));assert o['problems']==[]          # a property that was not asked for is ignored, never copied
    for answer,code in (((0,b'Id=docker.socket\nActiveState=active\nSubState=running\nUnitFileState=enabled\n'),'UNIT_ID_MISMATCH'),((0,b'Id=docker.service\n'),'PROPERTY_MISSING'),
                        ((0,b'Id=docker.service\nActiveState=a b\nSubState=running\nUnitFileState=enabled\n'),'PROPERTY_VALUE_INVALID'),((0,b'no separator\n'),'PROPERTY_LINE_INVALID')):
        host=world();host.answers['docker_unit']=answer;receipt,o,s=observed(bound,host)
        # an answer about docker.service that is not complete is not 'active': no docker command is started
        assert 'systemd:'+code in o['problems'] and 'containers:DOCKER_SKIPPED_UNIT_UNOBSERVED' in o['problems'] and docker_argv(host)==[]
        assert [problem for problem in o['problems'] if problem.startswith('systemd:')]==['systemd:'+code]

@pytest.mark.parametrize('state',['inactive','failed','activating','deactivating','reloading','maintenance','never-emit-state-canary'])
def test_no_docker_command_is_started_unless_the_docker_unit_was_seen_active(bound,state):
    """With the daemon stopped, a client call to its endpoint can make the service manager start it, and a started daemon
    restarts containers: a read-only operation may not do that. Zero docker argv, and every docker family says why."""
    host=world(provisioned=True);host.units['docker.service']['ActiveState']=state;host.units['docker.service']['SubState']='dead'
    receipt,o,s=observed(with_candidates(bound),host);clean(line(receipt))
    assert docker_argv(host)==[] and s['systemd']['docker_commands_allowed'] is False and s['docker_daemon'].get('docker_path') is None
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and o['status']=='PARTIAL_OBSERVED' and 'systemd:DOCKER_UNIT_NOT_ACTIVE' in o['findings']
    assert s['systemd']['status']=='COMPLETE' and s['systemd']['units']['docker.service']['ActiveState']==(state if state in p.ACTIVE_STATES else 'OTHER')
    assert s['docker_daemon']==s['containers']=={'status':'UNAVAILABLE','code':'DOCKER_SKIPPED_UNIT_NOT_ACTIVE'}
    assert {name:s[name].get('code') for name in ('worker','worker_environment','network')}=={name:'CONTAINERS_UNOBSERVED' for name in ('worker','worker_environment','network')}
    assert all(item=={'status':'UNAVAILABLE','code':'DOCKER_SKIPPED_UNIT_NOT_ACTIVE'} for item in s['images']['tags'].values())
    assert not NEGATIVE&set(o['findings']) and s['data_volume']['source_basis']=='SIGNED_DEFAULT_NO_CARRIER' and s['data_volume']['root']['status']=='COMPLETE'
    for name in ('runtime','journal_filesystem','host_layout','security_controller','alert_channels','processes','raw_spool','source_directory','release_directories','capacity_candidates'):
        assert s[name]['status']=='COMPLETE',name
    assert len(host.log)==15 and o['commands_started']==15          # 11 systemctl show and 4 pgrep

def test_an_empty_daemon_version_and_unsafe_binaries_are_unavailable_never_facts(bound):
    host=world();host.docker.version={'Client':{'Version':'29.9.9'},'Server':{'Version':''}};receipt,o,s=observed(bound,host)
    assert s['docker_daemon']=={'status':'UNAVAILABLE','code':'DAEMON_VERSION_EMPTY'} and 'docker_daemon:DAEMON_VERSION_EMPTY' in o['problems']
    host=world();host.tree.remove('/usr/bin/systemctl');host.tree.get('/usr/bin/pgrep').mode=0o777;receipt,o,s=observed(bound,host)
    assert {'processes:BINARY_UNAVAILABLE_OR_UNSAFE','systemd:BINARY_UNAVAILABLE_OR_UNSAFE','containers:DOCKER_SKIPPED_UNIT_UNOBSERVED'}<=set(o['problems'])
    assert host.log==[] and s['systemd']['systemctl_path'] is None          # without systemctl the unit is not observed: no docker command either
    host=world();host.tree.get('/usr/bin/pgrep').mode=0o777;receipt,o,s=observed(bound,host)
    assert o['problems']==['processes:BINARY_UNAVAILABLE_OR_UNSAFE'] and s['containers']['status']=='COMPLETE' and 'process:shadow_worker' not in host.keys
    host=world();host.tree.get('/usr/bin/docker').kind='symlink';receipt,o,s=observed(bound,host)
    assert s['containers']=={'status':'UNAVAILABLE','code':'BINARY_UNAVAILABLE_OR_UNSAFE'} and host.log and all(argv[0]!='/usr/bin/docker' for argv in host.log)

def test_argument_of_a_command_is_only_an_id_or_a_signed_tag():
    host=world();ctx=p.Context(host,lambda:30.0)
    # a fresh context is closed for docker: nothing has seen the unit active yet
    with pytest.raises(p.Refused,match='DOCKER_SKIPPED_UNIT_UNOBSERVED'):ctx.call('class','25'*32)
    with pytest.raises(p.Refused,match='DOCKER_SKIPPED_UNIT_UNOBSERVED'):ctx.call('version')
    assert host.log==[] and host.opened==[] and p.Context.docker_block=='DOCKER_SKIPPED_UNIT_UNOBSERVED'
    assert p.systemd(ctx)['docker_commands_allowed'] is True and ctx.docker_block is None;asked=len(host.log)
    for bad in ('--help','c3po-api-1','../x','sha256:xyz','c3po/backend:other',''):
        with pytest.raises(p.Refused,match='ARGUMENT_INVALID'):ctx.call('class',bad)
    with pytest.raises(p.Refused,match='ARGUMENT_INVALID'):ctx.call('class','25'*32,'25'*32)
    assert len(host.log)==asked==11 and ctx.call('class','25'*32)[0]==0 and ctx.call('image','c3po/backend:rollback')[0]==0
    assert p.Context.docker_block=='DOCKER_SKIPPED_UNIT_UNOBSERVED'          # the state belongs to one context, never to the class


# ---------------------------------------------------------------- window, atime, size and collector failures
def test_window_expiry_during_collection_stops_all_further_commands(bound):
    host=world();clock=[NOW]
    def expire(current):
        if len(current.log)==16:clock[0]=NOW+timedelta(minutes=6)          # 11 systemctl, 4 pgrep, then the first docker command
    host.on_run=expire;receipt=facts(bound,host,clock=lambda:clock[0]);s=receipt['observation']['sections']
    assert len(host.log)==16 and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and receipt['observation']['status']=='PARTIAL_OR_WINDOW_EXPIRED'
    # what needs no docker was read first and is kept: the journal decision and the pending-reboot fact among it
    for name in ('runtime','journal_filesystem','host_layout','alert_channels','systemd','processes','docker_daemon'):assert s[name]['status']=='COMPLETE',name
    assert s['journal_filesystem']['available_ge_five_session_need'] is True and s['security_controller']['reboot_pending'] is False
    assert s['containers']=={'status':'UNAVAILABLE','code':'GO_EXPIRED'} and s['data_volume']=={'status':'UNAVAILABLE','code':'GO_EXPIRED'} and host.fds=={}
    assert s['raw_spool']=={'status':'UNAVAILABLE','code':'GO_EXPIRED'} and s['journal_filesystem']['device_differs_from_data_volume'] is None
    assert s['security_controller']['host_state_holds_automatic_reboot'] is None and s['security_controller']['controller_trial_veto'] is None

def test_noatime_unavailable_fails_closed_per_observation(bound):
    host=world();host.noatime_available=False;receipt,o,s=observed(bound,host)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and host.log==[] and host.fds=={} and host.directories_listed==[]
    assert s['containers']=={'status':'UNAVAILABLE','code':'DOCKER_SKIPPED_UNIT_UNOBSERVED'} and s['journal_filesystem']=={'status':'UNAVAILABLE','code':'NOATIME_UNAVAILABLE'}
    assert {item['code'] for item in s['systemd']['units'].values()}=={'NOATIME_UNAVAILABLE'}
    assert s['runtime']['status']=='COMPLETE' and s['host_layout']['paths']['/etc/c3po-bar']=={'status':'UNAVAILABLE','code':'NOATIME_UNAVAILABLE'}

def test_atime_change_is_a_problem_on_a_quiet_directory_and_a_fact_on_a_live_one(bound):
    host=world(provisioned=True);host.noatime=lambda:0;host.expect_noatime=False          # a flag that is accepted and has no effect
    receipt,o,s=observed(with_candidates(bound),host)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and s['data_volume']['root']['atime_unchanged'] is False
    assert set(o['problems'])=={'data_volume:ATIME_CHANGED_DURING_LISTING','host_layout:ATIME_CHANGED_DURING_LISTING','capacity_candidates:ATIME_CHANGED_DURING_LISTING'}
    assert s['source_directory']['status']==s['release_directories']['status']=='COMPLETE' and s['source_directory']['candidates'][0]['events']['atime_unchanged'] is False
    assert s['raw_spool']['status']=='COMPLETE' and s['raw_spool']['root']['atime_unchanged'] is False and s['raw_spool']['root']['live_directory'] is True
    assert s['journal_filesystem']['journal_listing']['status']=='COMPLETE' and s['data_volume']['root']['count']==38          # the facts are still reported

def test_an_entry_that_vanishes_during_the_listing_is_counted_not_fatal(bound):
    host=world();original=host.lstat
    def lstat(name,dir_fd):
        if name.startswith('NEVEREMIT-AAPL-0') and host.fds[dir_fd][0].path==DATA:raise FileNotFoundError(errno.ENOENT,'gone')
        return original(name,dir_fd)
    host.lstat=lstat;receipt,o,s=observed(bound,host)
    assert s['data_volume']['root']['vanished_count']==10 and s['data_volume']['root']['count']==37 and o['problems']==[]
    clean(line(receipt));assert b'AAPL' not in line(receipt)          # the name of an entry that vanished is not kept either

def extreme():
    """Every list at or beyond its cap."""
    containers=[]
    for index,service in enumerate(p.SERVICES*2):
        mounts=[bind(DATA,'/app/day-d-data')]+[bind('/srv/s%02d'%m+'x'*150,'/d%02d'%m+'y'*150) for m in range(19)]
        containers.append(container(0x10+index,'c3po-%s-%d'%(service,index//8+1),3000000+index,service=service,mounts=mounts,
                                    networks=tuple('net%02d'%n+'w'*100 for n in range(9))+('c3po_c3po_internal',),env=WORKER_ENV))
    host=crowd(world(containers,provisioned=True),events=500,parts=500,root=500,release=50)
    for index in range(40):
        for base in (SOURCE_DIR,SOURCE_DIR+'/events',RAW,RAW+'/session_date=2026-10-02',DATA,DATA+'/'+RELEASE_NAME,CAPACITY,'/etc/c3po-bar'):
            host.tree.add(base+'/NEVEREMIT-mixed-%02d'%index,kind='file' if index%2 else 'dir',uid=index,gid=index+1,mode=0o600+index%8)
    return host
def test_receipt_at_the_caps_is_reduced_with_flags_and_fits_the_decode_limit(bound,monkeypatch):
    mutable=with_candidates(bound);receipt=facts(mutable,extreme());raw=line(receipt);o=receipt['observation']
    assert len(raw)<=p.RECEIPT_LIMIT<65536 and d.decode(raw)['schema']==RECEIPT and b'NEVEREMIT' not in raw
    claimed=receipt.pop('metadata_sha256');assert p.sha(p.canonical(receipt))==claimed
    seen=set()
    for limit in (48000,36000,24000,12000,5000,2500):
        monkeypatch.setattr(p,'RECEIPT_LIMIT',limit);receipt=facts(mutable,extreme());raw=line(receipt)
        assert len(raw)<=limit and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and receipt['observation']['status']!='OBSERVED_COMPLETE',limit
        seen|=set(receipt['observation']['size_reductions']);claimed=receipt.pop('metadata_sha256');assert p.sha(p.canonical(receipt))==claimed
    assert seen>={'HISTOGRAMS_DROPPED','MOUNTS_DROPPED','CONTAINER_ROWS_REDUCED','SECTIONS_REDUCED'}
    assert receipt['observation']['size_reductions']==['RECEIPT_REDUCED_TO_MINIMUM'] or 'SECTIONS_REDUCED' in receipt['observation']['size_reductions']

def test_typical_sizes_need_no_reduction(bound):
    before=facts(bound,world());after=facts(with_candidates(bound),world(provisioned=True))
    assert before['observation']['size_reductions']==after['observation']['size_reductions']==[] and before['status']==after['status']=='METADATA_ONLY_REQUIRES_REVIEW'
    assert len(line(before))<45000 and len(line(after))<55000

def test_collector_bug_yields_partial_receipt_not_a_spent_refusal(bound):
    def broken(request,gate):raise RuntimeError('unexpected')
    receipt=authcall(bound,collector=broken)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and receipt['observation']['code']=='COLLECTOR_FAILED'
    receipt=authcall(bound,collector=lambda request,gate:{'status':'OBSERVED_COMPLETE','sections':{'x':{'status':'COMPLETE','value':float('nan')}}})
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and receipt['observation']['code']=='RECEIPT_REDUCED_TO_MINIMUM'
    claimed=receipt.pop('metadata_sha256');assert p.sha(p.canonical(receipt))==claimed

def test_a_failed_part_below_a_section_that_calls_itself_complete_still_makes_the_receipt_partial(bound,monkeypatch):
    def careless(ctx):return {'status':'COMPLETE','issues':[],'findings':[],'probes':{'one':{'status':'COMPLETE','exists':False},
                                                                                      'two':[{'status':'UNAVAILABLE','code':'HIDDEN_BELOW'}]}}
    monkeypatch.setattr(p,'alert_channels',careless);receipt,o,s=observed(bound,world())
    assert s['alert_channels']['status']=='PARTIAL' and o['problems']==['alert_channels:HIDDEN_BELOW'] and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'

def test_a_section_that_raises_something_unforeseen_is_unavailable_and_the_others_go_on(bound,monkeypatch):
    def broken(ctx):raise KeyError('never-emit-exception-canary')
    monkeypatch.setattr(p,'host_layout',broken);receipt,o,s=observed(bound,world());clean(line(receipt))
    assert s['host_layout']=={'status':'UNAVAILABLE','code':'OBSERVATION_FAILED'} and o['problems']==['host_layout:OBSERVATION_FAILED']
    assert {name:section['status'] for name,section in s.items() if name!='host_layout'}=={name:'COMPLETE' for name in SECTIONS if name!='host_layout'}


# ---------------------------------------------------------------- repair round: one test (or more) per accepted finding
def one_fails(host,key,name):
    """The answer of one command for ONE container is exit 1; every other answer is the daemon's."""
    target=[item for item in host.docker.containers if item['Name']=='/'+name][0]['Id'];real=host.docker.run
    host.answers[key]=lambda argv:(1,b'') if argv[-1]==target else real(argv[3:])
    return host
DOCKER_SECTIONS=('containers','worker','worker_environment','network','images','deploy_version','data_volume')

def test_a_running_worker_whose_row_cannot_be_read_is_not_taken_for_a_missing_worker(bound):
    receipt,o,s=observed(bound,one_fails(world(),'family','c3po-r2d2-worker-1'))
    assert s['containers']['services']['r2d2-worker']=={'count':1,'running':1,'oneoff_count':0} and not NEGATIVE&set(o['findings'])
    row=[row for row in s['containers']['rows'] if row['service']=='r2d2-worker'][0]
    assert row=={'status':'UNAVAILABLE','code':'COMMAND_FAILED','returncode':1,'service':'r2d2-worker','oneoff':False,'container_id':'46'*32,'running':True}
    # the environment and the network attachment are read by container id: they WERE observed
    e=s['worker_environment'];assert e['status']=='COMPLETE' and e['evaluated_count']==1 and e['workers'][0]['database_url']=='SET' and e['findings']==[]
    assert s['network']['status']=='COMPLETE' and s['network']['attachments']['worker']['on_compose_network'] is True and s['network']['worker_attached_by_network_inspect'] is True
    # what needs the row itself says that it could not be answered
    w=s['worker'];assert w['status']=='UNAVAILABLE' and w['exactly_one_running'] is True and w['workers']==[{'status':'UNAVAILABLE','code':'WORKER_ROW_UNAVAILABLE','container_id':'46'*32}]
    i=s['images'];assert i['status']=='PARTIAL' and i['issues']==['CONTAINER_ROW_UNAVAILABLE'] and i['production_id_equals_every_running_backend'] is None
    assert i['revision_label_equal_across_backend_and_production'] is None and i['backend_containers_compared']==5 and i['backend_services_without_a_running_container']==[]
    v=s['deploy_version'];assert v['status']=='PARTIAL' and v['equals_every_backend_container_revision'] is None and v['equals_production_revision_label'] is True
    assert o['problems']==['containers:COMMAND_FAILED','containers:FAMILY_ROW_INCOMPLETE','data_volume:FAMILY_MOUNT_FACTS_INCOMPLETE','deploy_version:CONTAINER_ROW_UNAVAILABLE',
                           'images:CONTAINER_ROW_UNAVAILABLE','worker:WORKER_ROW_UNAVAILABLE']
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and len(s['data_volume']['carriers'])==2

def test_a_running_db_whose_row_cannot_be_read_is_not_taken_for_a_stopped_db(bound):
    receipt,o,s=observed(bound,one_fails(world(),'family','c3po-db-1'));n=s['network']
    assert n['status']=='COMPLETE' and n['attachments']['db']['evaluated'] is True and n['attachments']['db']['on_compose_network'] is True
    assert n['db_attached_by_network_inspect'] is True and n['findings']==[] and not NEGATIVE&set(o['findings'])
    i=s['images'];assert i['service_tag_equals_running']=={'web':True} and i['issues']==['CONTAINER_ROW_UNAVAILABLE'] and i['production_id_equals_every_running_backend'] is True
    assert s['deploy_version']['status']=='COMPLETE' and 'images:CONTAINER_ROW_UNAVAILABLE' in o['problems']

def test_a_container_that_cannot_be_classified_may_be_any_service_and_nothing_is_said_to_be_missing(bound):
    receipt,o,s=observed(bound,one_fails(world(),'class','c3po-r2d2-worker-1'));c=s['containers']
    assert c['unclassified_count']==1 and c['services']['r2d2-worker']=={'count':0,'running':0,'oneoff_count':0} and c['services_missing'] is None
    assert not NEGATIVE&set(o['findings']),sorted(NEGATIVE&set(o['findings']))
    w=s['worker'];assert w['status']=='PARTIAL' and w['issues']==['UNCLASSIFIED_CONTAINERS'] and w['exactly_one_running'] is None and w['count']==0 and w['findings']==[]
    e=s['worker_environment'];assert e['status']=='PARTIAL' and e['evaluated_count']==0 and e['findings']==[]
    n=s['network'];assert n['status']=='PARTIAL' and n['worker_attached_by_network_inspect'] is None and n['db_attached_by_network_inspect'] is True
    i=s['images'];assert i['status']=='PARTIAL' and i['production_id_equals_every_running_backend'] is None and i['backend_services_without_a_running_container'] is None
    assert s['deploy_version']['status']=='PARTIAL' and s['deploy_version']['equals_every_backend_container_revision'] is None
    assert {problem.split(':')[0] for problem in o['problems']}==set(DOCKER_SECTIONS) and 'worker:UNCLASSIFIED_CONTAINERS' in o['problems']
    # two workers that WERE classified are a definite 'not one', whatever else could not be classified
    host=one_fails(world(),'class','c3po-web-1');second(host);receipt,o,s=observed(bound,host)
    assert s['worker']['exactly_one_running'] is False and 'worker:WORKER_COUNT_NOT_ONE' in o['findings'] and s['worker']['status']=='PARTIAL'

SERVICE_NAMES={'api':'c3po-api-1','db':'c3po-db-1','web':'c3po-web-1','r2d2-worker':'c3po-r2d2-worker-1','valuation-worker':'c3po-valuation-worker-1',
               'investor-relations-worker':'c3po-investor-relations-worker-1','r2d2-shadow-candidate-worker':'c3po-r2d2-shadow-candidate-worker-1',
               'server-usage-worker':'c3po-server-usage-worker-1','outside':'chief-of-staff-digital-cloudflared-1'}
@pytest.mark.parametrize('key,service',[(key,service) for key in ('class','family') for service in sorted(SERVICE_NAMES)
                                        if (key,service)!=('family','outside')])          # a container outside the stack has no family read
def test_one_container_that_cannot_be_read_never_becomes_a_negative_finding_under_a_complete_section(bound,key,service):
    host=one_fails(world(),key,SERVICE_NAMES[service]);receipt,o,s=observed(bound,host)
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and not NEGATIVE&set(o['findings']),sorted(NEGATIVE&set(o['findings']))
    assert s['containers']['status']=='PARTIAL' and s['data_volume']['status']=='PARTIAL' and 'data_volume:FAMILY_MOUNT_FACTS_INCOMPLETE' in o['problems']
    if key=='class':          # unclassified: every section that counts or compares containers is partial, and says why
        for name in ('worker','worker_environment','network','images','deploy_version'):
            assert s[name]['status']=='PARTIAL' and 'UNCLASSIFIED_CONTAINERS' in s[name]['issues'],name
    else:
        assert s['images']['status']=='PARTIAL' and 'CONTAINER_ROW_UNAVAILABLE' in s['images']['issues']
        assert (s['deploy_version']['status']=='PARTIAL')==(service in p.BACKEND) and (s['worker']['status']!='COMPLETE')==(service=='r2d2-worker')
        assert s['worker_environment']['status']=='COMPLETE' and s['network']['status']=='COMPLETE'          # both are read by container id

def test_a_difference_that_was_observed_is_still_a_finding_when_another_container_could_not_be_read(bound):
    containers=stack();containers[1].update(Image=ROLLBACK_IMAGE);containers[1]['Config']['Labels']['org.opencontainers.image.revision']='4d'*20
    receipt,o,s=observed(bound,one_fails(world(containers),'family','c3po-valuation-worker-1'))
    assert s['images']['production_id_equals_every_running_backend'] is False and s['deploy_version']['equals_every_backend_container_revision'] is False
    assert {'images:PRODUCTION_TAG_NOT_RUNNING_IMAGE','images:REVISION_LABEL_MISMATCH','deploy_version:DEPLOY_VERSION_NOT_THE_RUNNING_REVISION'}<=set(o['findings'])

def test_the_container_list_changing_between_the_two_listings_is_a_problem_and_stops_every_negative_answer(bound):
    host=world();calls=[0];real=host.docker.run
    def listing(argv):
        calls[0]+=1;code,out=real(argv[3:])
        return (code,out) if calls[0]==1 else (code,b'\n'.join(out.splitlines()[:-1])+b'\n')          # one container ended during the read
    host.answers['ps']=listing;receipt,o,s=observed(bound,host)
    assert calls[0]==2 and s['containers']['list_stable'] is False and (s['containers']['listed_before'],s['containers']['listed_after'])==(11,10)
    assert 'containers:LIST_UNSTABLE' in o['problems'] and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and o['status']=='PARTIAL_OBSERVED'
    assert {problem for problem in o['problems'] if problem.endswith(':LIST_UNSTABLE')}=={name+':LIST_UNSTABLE' for name in ('containers','worker','worker_environment','network','images','deploy_version')}
    assert s['worker']['exactly_one_running'] is None and not NEGATIVE&set(o['findings']) and 'data_volume:FAMILY_MOUNT_FACTS_INCOMPLETE' in o['problems']

def test_more_workers_than_the_limit_is_a_problem_of_both_worker_sections_never_a_silent_cut(bound):
    host=world();template=[item for item in host.docker.containers if item['Name']=='/c3po-r2d2-worker-1'][0]
    for index in range(4):
        host.docker.containers.append(container(0x50+index,'c3po-r2d2-worker-%d'%(index+2),3670000+index,service='r2d2-worker',mounts=template['Mounts'],
                                                networks=('c3po_c3po_internal','chief-of-staff-digital_default'),env=WORKER_ENV))
    receipt,o,s=observed(bound,host)
    assert s['containers']['services']['r2d2-worker']['count']==5 and len(s['worker']['workers'])==len(s['worker_environment']['workers'])==p.MAX_WORKERS==4
    assert o['problems']==['worker:WORKER_LIMIT','worker_environment:WORKER_LIMIT'] and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert s['worker']['exactly_one_running'] is False and 'worker:WORKER_COUNT_NOT_ONE' in o['findings']

# --- the data source is the mount of the running containers
def test_a_stopped_or_one_off_container_with_another_data_mount_does_not_take_the_data_volume_away(bound):
    named=volume('c3po_c3po_day_d_data','/app/day-d-data')
    for extra,finding in ((container(0x33,'c3po-api-run-0123456789ab',0,service='api',oneoff='True',status='exited',mounts=[named]),True),
                          (container(0x34,'c3po-api-run-0123456789ac',4100001,service='api',oneoff='True',mounts=[named]),True),
                          (container(0x35,'c3po-r2d2-shadow-candidate-worker-2',0,service='r2d2-shadow-candidate-worker',status='exited',mounts=[named]),True),
                          (container(0x36,'c3po-api-run-0123456789ad',0,service='api',oneoff='True',status='exited',mounts=[bind(DATA,'/app/day-d-data')]),False)):
        host=world();host.docker.containers.append(extra);receipt,o,s=observed(bound,host);a=s['data_volume']
        assert o['problems']==[] and receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and a['status']=='COMPLETE'
        assert a['source']==DATA and a['source_basis']=='MOUNT_OF_THE_RUNNING_CONTAINERS' and a['distinct_source_count']==1 and len(a['carriers'])==3
        assert a['root']['count']==37 and s['raw_spool']['status']=='COMPLETE' and s['source_directory']['status']=='COMPLETE'
        assert s['journal_filesystem']['device_differs_from_data_volume'] is True
        assert [item['same_source'] for item in a['stopped_or_oneoff_containers_with_the_data_mount']]==[not finding]
        assert ('data_volume:STOPPED_CONTAINER_DATA_SOURCE_DIFFERS' in o['findings'])==finding
    # two RUNNING service containers that disagree are still a problem
    containers=stack();containers[3]['Mounts'][0]=named;receipt,o,s=observed(bound,world(containers))
    assert 'data_volume:DATA_SOURCE_DISAGREE' in o['problems'] and s['data_volume']['source'] is None

# --- every component the reader traverses
@pytest.mark.parametrize('uid,gid,mode,expected',[(1000,1000,0o700,{'INPUT_UNREADABLE_UID0_NOCAP','PRIVATE_INPUT_NOT_UID0'}),(1000,1000,0o750,{'INPUT_UNREADABLE_UID0_NOCAP'}),
                                                 (1000,0,0o750,set()),(1000,1000,0o711,set()),(0,0,0o700,set()),(0,0,0o600,{'INPUT_UNREADABLE_UID0_NOCAP'}),(1000,1000,0o755,set())])
def test_a_component_or_a_volume_root_that_the_reader_cannot_traverse_is_the_design_refusal(bound,uid,gid,mode,expected):
    for path,section in ((DATA+'/provider=eodhd/microstructure','raw_spool'),(DATA+'/provider=eodhd','raw_spool'),(DATA,'data_volume')):
        host=world();node=host.tree.get(path);node.uid,node.gid,node.mode=uid,gid,mode
        receipt,o,s=observed(bound,host)
        assert {code for code in s[section]['findings'] if code in ('INPUT_UNREADABLE_UID0_NOCAP','PRIVATE_INPUT_NOT_UID0')}==expected,(path,s[section]['findings'])
        assert o['problems']==[] and receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW'
        if section=='raw_spool':
            row=[item for item in s['raw_spool']['components'] if item['label']==path.rsplit('/',1)[1]][0]
            assert (row['uid'],row['gid'],row['mode_octal'],row['private'])==(uid,gid,'%04o'%mode,mode&0o077==0)

# --- a path that exists and is not a regular file was not read
UNREAD={'policy':'/etc/c3po/security-automation.json','automation_report':SECURITY+'/security-automation-report.json','host_report':SECURITY+'/host-os-vulnerability-report.json'}
UNREAD.update({name:'/usr/local/lib/c3po-security/'+name for name in p.MODULES})
@pytest.mark.parametrize('label',sorted(UNREAD))
@pytest.mark.parametrize('form',['symlink','fifo','dir'])
def test_a_controller_file_that_is_not_a_regular_file_is_a_failed_observation_never_a_fact(bound,label,form):
    host=world();host.tree.get(UNREAD[label]).kind=form;receipt,o,s=observed(bound,host);k=s['security_controller']
    item=k['modules'][label] if label in p.MODULES else k[label]
    assert item['status']=='UNAVAILABLE' and item['code']=='NOT_A_REGULAR_FILE' and item['content_read'] is False and item['type']==('other' if form=='fifo' else form)
    assert o['problems']==['security_controller:NOT_A_REGULAR_FILE'] and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and UNREAD[label] not in host.files_opened
    assert 'sha256' not in item and k['status']=='PARTIAL'
    if label=='policy':          # the controller would follow the link and may read true: nothing is said about the policy
        assert k['automatic_reboot_held_by']==['TRIAL_PIN','TRIAL_NAME_UNRECOGNISED','TRIAL_RELEASE_FILE_UNDETERMINED_WITHOUT_CONTENT'] and k['host_state_holds_automatic_reboot'] is None
    else:assert k['host_state_holds_automatic_reboot'] is True

def test_an_unread_policy_alone_never_holds_the_automatic_reboot(bound):
    host=world(entries=[('plain','dir',0,0o755)]);host.tree.get(UNREAD['policy']).kind='symlink';receipt,o,s=observed(bound,host);k=s['security_controller']
    assert k['automatic_reboot_held_by']==[] and k['host_state_holds_automatic_reboot'] is None and k['policy']['code']=='NOT_A_REGULAR_FILE'
    host=world(entries=[('plain','dir',0,0o755)]);host.tree.add(UNREAD['policy'],content=b'{"automatic_reboot":false}');receipt,o,s=observed(bound,host)
    assert s['security_controller']['automatic_reboot_held_by']==['POLICY_AUTOMATIC_REBOOT_NOT_TRUE'] and s['security_controller']['host_state_holds_automatic_reboot'] is True
    host=world(entries=[('plain','dir',0,0o755)]);receipt,o,s=observed(bound,host)          # policy read and true, nothing else: a definite 'nothing holds it'
    assert s['security_controller']['automatic_reboot_held_by']==[] and s['security_controller']['host_state_holds_automatic_reboot'] is False and o['problems']==[]

# --- texts with a grammar, not a character set
LEAKS=(b'zqleak',b'10.99.88.77',b'88.77',b'.internal')
@pytest.mark.parametrize('release,expected',[('zqleak.internal',{'version':None,'abi':None,'release_withheld':True}),('10.99.88.77',{'version':None,'abi':None,'release_withheld':True}),
    ('6.8.0-zqleak.internal',{'version':'6.8.0','abi':None,'release_withheld':False,'suffix_withheld':True}),
    ('6.8.0-1013-zqleak.internal',{'version':'6.8.0','abi':1013,'release_withheld':False,'suffix_withheld':True}),
    ('6.8.0-10.99.88.77',{'version':'6.8.0','abi':10,'release_withheld':False,'suffix_withheld':True}),
    ('6.8.0-45',{'version':'6.8.0','abi':45,'release_withheld':False,'suffix_withheld':False}),('6.12',{'version':'6.12','abi':None,'release_withheld':False,'suffix_withheld':False}),
    ('6.8.0-1013-aws\xff',{'version':None,'abi':None,'release_withheld':True}),('',{'version':None,'abi':None,'release_withheld':True})])
def test_kernel_release_is_reduced_to_its_number_and_no_name_shaped_text_passes(bound,release,expected):
    host=world();host.tree.get('/proc/sys/kernel/osrelease').content=release.encode('latin-1')+b'\n';receipt,o,s=observed(bound,host);raw=line(receipt)
    assert s['runtime']['kernel']==dict(expected,status='COMPLETE') and o['problems']==[] and not [word for word in LEAKS if word in raw]

@pytest.mark.parametrize('version,expected',[('zqleak.internal',None),('10.99.88.77',None),('29.5',('29.5',False)),('29.5.3',('29.5.3',False)),
                                             ('29.5.3-zqleak.internal',('29.5.3',True)),('29.5.3+10.99.88.77',('29.5.3',True)),('v29.5.3',None),('29',None)])
def test_docker_server_version_is_reduced_to_its_number_and_no_name_shaped_text_passes(bound,version,expected):
    host=world();host.docker.version={'Client':{'Version':'1'},'Server':{'Version':version}};receipt,o,s=observed(bound,host);raw=line(receipt)
    assert not [word for word in LEAKS if word in raw]
    if expected is None:assert s['docker_daemon']=={'status':'UNAVAILABLE','code':'DAEMON_FIELD_INVALID'} and o['problems']==['docker_daemon:DAEMON_FIELD_INVALID']
    else:assert (s['docker_daemon']['server_version'],s['docker_daemon']['server_version_suffix_withheld'])==expected and o['problems']==[]

@pytest.mark.parametrize('stamp,accepted',[('2026-10-02T22:21:03.321759952Z',True),('0001-01-01T00:00:00Z',True),('2026-10-02T22:21:03+00:00',True),('10.99.88.77',False),
                                           ('2026-10-02',False),('2026-10-02T22:21:03',False),('zqleak.internal',False),('2026-10-02T22:21:03.1234567890Z',False)])
def test_started_at_is_an_rfc_3339_timestamp_or_the_row_is_refused(bound,stamp,accepted):
    containers=stack();containers[1]['State']['StartedAt']=stamp;receipt,o,s=observed(bound,world(containers));row=s['containers']['rows'][0]
    assert not [word for word in LEAKS if word in line(receipt)]
    if accepted:assert row['started_at']==stamp and o['problems']==[]
    else:assert row['code']=='FAMILY_METADATA_INVALID' and 'started_at' not in row and 'containers:FAMILY_METADATA_INVALID' in o['problems']

@pytest.mark.parametrize('value,emitted,flagged',[(0,0,False),(1000000,1000000,False),(1000001,None,True),(-1,None,True),(10**200,None,True),(True,None,True),('7',None,True),
                                                 (1.0,None,True),(None,None,False)])
def test_counts_taken_from_the_controller_reports_are_bounded(bound,value,emitted,flagged):
    host=world();host.tree.add(SECURITY+'/security-automation-report.json',content=automation_report(security_pending=value))
    host.tree.add(SECURITY+'/host-os-vulnerability-report.json',content=host_report(updates={'security_pending':value,'all_pending':value}))
    receipt,o,s=observed(bound,host);k=s['security_controller']
    assert (k['automation_report']['security_pending'],k['host_report']['security_pending'],k['host_report']['all_pending'])==(emitted,emitted,emitted)
    assert ('security_controller:REPORT_COUNT_OUT_OF_RANGE' in o['findings'])==flagged and o['problems']==[] and len(line(receipt))<45000
    assert p.REPORT_COUNT_LIMIT==1000000 and k['automation_report']['seal_ok'] is True

# --- automounts
def autofs(point,then=None):
    row=b'500 30 0:77 / %s rw,relatime shared:90 - autofs systemd-1 rw,fd=40,pgrp=1,timeout=0,minproto=5,maxproto=5,direct\n'%point.encode()
    return row+(b'501 500 259:16 / %s rw,relatime shared:91 - %s /dev/nvme1n1 rw\n'%(point.encode(),then.encode()) if then else b'')
@pytest.mark.parametrize('point,refused,kept',[
    (DATA,('data_volume','raw_spool','source_directory','release_directories'),{DATA}),
    (DATA+'/provider=eodhd/microstructure',('data_volume','raw_spool','source_directory','release_directories'),{DATA}),          # a point BELOW the tree that is descended
    ('/mnt',('data_volume','raw_spool','source_directory','release_directories'),{'/mnt',DATA}),
    ('/var/lib/c3po-bar',('journal_filesystem',),{'/var/lib/c3po-bar','/var/lib/c3po-bar/journal'}),
    ('/var/lib/c3po-bar/journal',('journal_filesystem',),{'/var/lib/c3po-bar/journal'}),
    ('/etc/c3po-reader',('host_layout',),{'/etc/c3po-reader','/etc/c3po-reader/launcher','/etc/c3po-reader/docker-cli'}),
    (CAPACITY,('capacity_candidates',),{CAPACITY}),
    ('/etc/c3po',('security_controller',),{'/etc/c3po','/etc/c3po/security-automation.json'}),
    ('/usr/local/lib/c3po-security',('security_controller',),{'/usr/local/lib/c3po-security'})])
def test_nothing_is_opened_at_or_below_an_armed_automount_point(bound,point,refused,kept):
    host=world(provisioned=True);host.tree.get('/proc/4242/mountinfo').content+=autofs(point);receipt,o,s=observed(with_candidates(bound),host)
    assert not kept&set(host.opened),sorted(kept&set(host.opened))          # an open with O_DIRECTORY is what would make the kernel mount it
    assert o['automount_guard']=={'applied':True,'autofs_rows':2,'armed_points':2} and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'
    assert {problem.split(':')[0] for problem in o['problems'] if problem.endswith(':AUTOMOUNT_PATH_REFUSED')}<=set(refused)
    assert {problem.split(':')[0] for problem in o['problems']}==set(refused) and any(problem.endswith(':AUTOMOUNT_PATH_REFUSED') for problem in o['problems'])

def test_an_automount_point_that_is_already_mounted_over_is_read_and_a_missing_table_is_said(bound):
    host=world(provisioned=True);host.tree.get('/proc/4242/mountinfo').content+=autofs(DATA,'ext4')+autofs('/proc/sys/fs/binfmt_misc','binfmt_misc')
    receipt,o,s=observed(with_candidates(bound),host)
    assert o['problems']==[] and o['automount_guard']=={'applied':True,'autofs_rows':3,'armed_points':0} and s['data_volume']['root']['status']=='COMPLETE'
    host=world();host.tree.remove('/proc/4242');receipt,o,s=observed(bound,host)
    assert o['automount_guard']=={'applied':False,'autofs_rows':None,'armed_points':None} and 'data_volume:OS_ERROR' in o['problems']
    host=world();host.tree.get('/proc/4242/mountinfo').content+=autofs('/usr/bin');receipt,o,s=observed(bound,host)          # even the tools: none is looked up, none is run
    assert host.log==[] and '/usr/bin' not in host.opened and 'systemd:AUTOMOUNT_PATH_REFUSED' in o['problems'] and 'processes:AUTOMOUNT_PATH_REFUSED' in o['problems']

# --- every section counts in the verdict
RUN_ORDER=['runtime','journal_filesystem','host_layout','security_controller','alert_channels','systemd','processes','docker_daemon','containers','worker',
           'worker_environment','network','images','deploy_version','data_volume','raw_spool','source_directory','release_directories','capacity_candidates']
@pytest.mark.parametrize('name',RUN_ORDER)
def test_a_problem_in_any_one_section_makes_the_receipt_partial(bound,monkeypatch,name):
    def broken(*args,**kwargs):raise KeyError('never-emit-exception-canary')
    monkeypatch.setattr(p,name,broken);receipt,o,s=observed(bound,world());clean(line(receipt))
    assert s[name]=={'status':'UNAVAILABLE','code':'OBSERVATION_FAILED'} and name+':OBSERVATION_FAILED' in o['problems']
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and o['status']=='PARTIAL_OBSERVED' and sorted(s)==SECTIONS
    assert list(s)[:len(RUN_ORDER)]==RUN_ORDER and sorted(RUN_ORDER+['clock'])==SECTIONS          # what needs no docker is read first

@pytest.mark.parametrize('change,code',[(lambda host:setattr(host,'up',-1.0),'RUNTIME_FIELD_INVALID'),(lambda host:setattr(host,'up',float(10**12)),'RUNTIME_FIELD_INVALID'),
                                        (lambda host:setattr(host,'version',((3,'x',1),'cpython')),'RUNTIME_FIELD_INVALID'),
                                        (lambda host:setattr(host,'uptime',lambda:p.need(False,'BOOTTIME_UNAVAILABLE')),'BOOTTIME_UNAVAILABLE'),
                                        (lambda host:host.tree.remove('/proc/sys/kernel/osrelease'),'OS_ERROR'),
                                        (lambda host:setattr(host.tree.get('/proc/sys/kernel/osrelease'),'content',b'6'*300),'CONTENT_SIZE_LIMIT')])
def test_a_runtime_fact_that_cannot_be_read_is_a_problem_of_runtime_alone(bound,change,code):
    host=world();change(host);receipt,o,s=observed(bound,host)
    assert o['problems']==['runtime:'+code] and receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and s['runtime']['status']=='PARTIAL'
    assert [name for name,section in s.items() if section['status']!='COMPLETE']==['runtime']

def test_a_release_candidate_whose_listing_fails_is_the_only_problem(bound):
    host=world(provisioned=True);original=host.names
    def names(fd):
        if host.fds[fd][0].path==DATA+'/'+RELEASE_NAME:raise OSError(errno.EIO,'never-emit-error-canary')
        return original(fd)
    host.names=names;receipt,o,s=observed(with_candidates(bound),host);clean(line(receipt))
    assert o['problems']==['release_directories:OS_ERROR'] and s['release_directories']['candidates']==[{'status':'UNAVAILABLE','code':'OS_ERROR','errno':errno.EIO,'candidate_index':0}]
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW' and host.fds=={}

def test_a_clock_that_cannot_be_read_at_the_end_makes_the_receipt_partial(bound):
    ticks=iter([0,0,5,4]+[4]*20)          # gate creation, first gate call, the mark, then a smaller value: the elapsed time is negative
    receipt=authcall(bound,monotonic=lambda:next(ticks),collector=lambda q,gate:{'status':'OBSERVED_COMPLETE','sections':{}})
    assert receipt['observation']['sections']['clock']=={'status':'UNAVAILABLE','code':'CLOCK_REVERSED'} and receipt['observation']['status']=='PARTIAL_OBSERVED'
    assert receipt['status']=='PARTIAL_METADATA_REQUIRES_REVIEW'

def test_the_schema_names_of_the_collection_and_of_the_observation(bound):
    assert p.COLLECTION_SCHEMA=='W1PREFLIGHT01_READONLY_REQUEST_V1' and p.OBSERVATION_SCHEMA=='W1PREFLIGHT01_READONLY_OBSERVATION_V1'
    receipt,o,s=observed(bound,world());assert o['schema']=='W1PREFLIGHT01_READONLY_OBSERVATION_V1' and bound[1]['collection']['schema']=='W1PREFLIGHT01_READONLY_REQUEST_V1'
    bound[1]['collection']['schema']='SUPERVISOR_READONLY_REQUEST_V1'
    with pytest.raises(p.Refused,match='COLLECTION_UNBOUND'):authcall(rebind(bound),collector=never)

# --- what is legitimately absent before provisioning is a fact
def test_signed_candidates_that_do_not_exist_yet_are_facts_not_problems(bound):
    host=world();receipt,o,s=observed(with_candidates(bound),host)
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[] and o['findings']==['data_volume:TRIAL_VETO_INDEPENDENT_OF_PIN','data_volume:TRIAL_VETO_PRESENT']
    assert s['release_directories']=={'status':'COMPLETE','issues':[],'findings':[],'candidate_count':1,'candidates':[{'status':'COMPLETE','exists':False,'candidate_index':0}]}
    k=s['capacity_candidates']['candidates'][0]
    assert k['status']=='COMPLETE' and k['exists'] is False and k['absent_at_depth']==3 and len(k['ancestors'])==3 and s['capacity_candidates']['status']=='COMPLETE'
    assert CAPACITY.encode() not in line(receipt) and RELEASE_NAME.encode() not in line(receipt)

@pytest.mark.parametrize('made,deepest',[(('/var/lib/c3po-bar',),'/var/lib/c3po-bar'),(('/var/lib/c3po-bar','/var/lib/c3po-bar/journal'),'/var/lib/c3po-bar/journal'),
                                         (('/var/lib/c3po-bar','/var/lib/c3po-bar/supervisor'),'/var/lib/c3po-bar')])
def test_a_partially_provisioned_journal_is_a_fact_not_a_problem(bound,made,deepest):
    host=world()
    for path in made:host.tree.add(path,mode=0o700)
    receipt,o,s=observed(bound,host);j=s['journal_filesystem']
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and o['problems']==[] and j['status']=='COMPLETE' and j['findings']==[] and j['statvfs_of']==deepest
    assert j['journal_parent']['exists'] is True and j['journal_parent']['root_root_private'] is True
    assert j['journal_root'].get('exists') is ('/var/lib/c3po-bar/journal' in made) and j['state_root'].get('exists') is ('/var/lib/c3po-bar/supervisor' in made)
    assert ('journal_listing' in j)==('/var/lib/c3po-bar/journal' in made) and j['available_ge_five_session_need'] is True and j['device_differs_from_data_volume'] is True

def test_var_run_absent_is_a_fact_not_a_problem(bound):
    host=world();host.tree.remove('/var/run');receipt,o,s=observed(bound,host)
    assert s['security_controller']['var_run']=={'status':'COMPLETE','exists':False} and o['problems']==[] and o['findings']==BEFORE
    assert receipt['status']=='METADATA_ONLY_REQUIRES_REVIEW' and s['security_controller']['reboot_pending'] is False

# --- the fixtures hold no name of a real host
PRIVATE_RECEIPT=Path('/offline/optional-work/hostfacts01-fable-20261002/.dispatch-root/supervisor-hostfacts-once/stdout.private.json')
def fixture_root_names():
    names=set()
    for host in (world(),world(provisioned=True),crowd(world(provisioned=True),events=3,parts=3,root=30,release=3),extreme()):names|=set(host.tree.get(DATA).children)
    return names
def test_every_fixture_name_at_the_volume_root_is_a_signed_constant_or_visibly_synthetic():
    scope=p.canonical(p.SCOPE).decode();assert all(name in scope for name in SIGNED_ROOT_NAMES)
    odd=[name for name in fixture_root_names() if name not in SIGNED_ROOT_NAMES+(RELEASE_NAME,) and not SYNTHETIC_ROOT_NAME.fullmatch(name)
         and not re.fullmatch(r'NEVEREMIT-(ROOT-TSLA|mixed)-[0-9]+',name)]
    assert odd==[] and len(fixture_root_names())>80
    # every trial or probe name written anywhere in this file carries a date that no such directory of the 2026 epochs can carry, or no date
    literals=set(re.findall(r'\.r2d2-v2-(?:trial|probe)-([0-9A-Za-z%-]*)',Path(__file__).read_text()))
    assert literals and all(re.match(r'202501|20261003|20261340|20270101|x$|$|\(',text_) for text_ in literals),sorted(literals)

@pytest.mark.skipif(not PRIVATE_RECEIPT.is_file(),reason='the private receipt of the earlier read is not on this machine')
def test_no_entry_name_of_the_private_receipt_is_in_a_fixture_or_in_this_file():
    """Reads the private receipt only to compare. Nothing of it is printed: a failure shows a count."""
    names=set()
    def walk(value):
        if type(value) is dict:
            for row in value.get('rows') if type(value.get('rows')) is list else []:
                if type(row) is dict and type(row.get('name')) is str:names.add(row['name'])
            for item in value.values():walk(item)
        elif type(value) is list:
            for item in value:walk(item)
    walk(json.loads(PRIVATE_RECEIPT.read_bytes()));total=len(names)
    assert total>20          # every assertion here compares plain numbers: a failure can show a count, never a name
    in_fixtures=len((fixture_root_names()&names)-set(SIGNED_ROOT_NAMES))
    assert in_fixtures==0
    words=set(re.findall(r'[A-Za-z0-9._=+-]+',Path(__file__).read_text()))          # every word of this file, compared as a whole word
    generic={word for word in names if re.fullmatch('[a-z]{1,12}',word)}             # plain dictionary words of any path or prose
    in_this_file=len((words&names)-set(SIGNED_ROOT_NAMES)-generic)
    assert in_this_file==0

# ---------------------------------------------------------------- the signed constants against the repository checkout
CHECKOUT=Path('/offline/optional-references/opsart')
@pytest.mark.skipif(not (CHECKOUT/'c3po'/'compose.yml').is_file(),reason='the repository checkout is not on this machine')
def test_signed_constants_are_the_ones_of_the_repository_checkout():
    """Read-only. Every name, pattern and number the scope signs is looked up where the repository defines it."""
    read=lambda name:(CHECKOUT/name).read_text()
    assembler=read('c3po/backend/app/r2d2_v2_epoch_assembler.py')
    assert re.search(r"^EPOCH = '([^']+)'",assembler,re.M).group(1)==p.EPOCH
    assert re.search(r"^SESSIONS = \(([^)]*)\)",assembler,re.M).group(1).replace("'",'').split(',')==p.SESSIONS
    assert 'MIN_SESSION_FREE_BYTES=50*1024**3' in read('c3po/backend/app/r2d2_v2_massive_producer.py') and p.FLOOR_BYTES==50*1024**3
    assert '603979776' in read('c3po/deployment/massive-supervisor/README.md') and p.FIVE_SESSION_NEED_BYTES==p.FLOOR_BYTES+5*603979776
    compose=read('c3po/compose.yml')
    assert sorted(re.findall(r'^  ([a-z0-9-]+):\n    (?:image|build)',compose,re.M))==p.SERVICES
    names=re.findall(r'^  (c3po_[a-z_]+):',compose,re.M)
    assert sorted('c3po_'+name for name in names if name!='c3po_internal')==p.VOLUMES and 'c3po_'+'c3po_internal'==p.COMPOSE_NETWORK
    assert ':-c3po_capacity_unprovisioned}:/c3po-capacity:ro' in compose and ':-c3po_day_d_data}:/app/day-d-data' in compose
    assert 'C3PO_R2D2_MICROSTRUCTURE_RAW_DIR: /app/day-d-data/'+'/'.join(p.RAW_PARTS) in compose and 'name: chief-of-staff-digital_default' in compose
    for destination in p.MOUNT_DESTINATIONS:assert ':'+destination in compose,destination
    config=read('c3po/backend/app/config.py');assert 'env_prefix="C3PO_"' in config
    for key,_ in p.ENV_KEYS:assert re.search(r'^    '+key[len('C3PO_'):].lower()+':',config,re.M),key
    assert 'r2d2_v2_capacity_veto_mode: str = "DISPATCH_AND_DERIVATION_ONLY"' in config
    raw=read('c3po/backend/app/r2d2_v2_raw_source.py')
    assert r'_SESSION = re.compile(r"session_date=(\d{4}-\d{2}-\d{2})\Z")' in raw and '_PART = re.compile(r"'+p.NAME_CLASSES['raw_part']+r'\Z")' in raw
    assert 'MAX_FILES = %d'%p.READER_FILE_LIMIT in raw and 'MAX_EVENT_FILES = %d'%p.READER_FILE_LIMIT in read('c3po/backend/app/r2d2_v2_sources.py')
    assert "_PARENT_FILES = {'epoch.json', 'maintenance.lock', 'producer.lock'}" in read('c3po/backend/app/r2d2_v2_massive_sessions.py')
    assert (CHECKOUT/'ops'/'security-automation.json').read_bytes()==POLICY and json.loads(POLICY)['schema']==p.POLICY_SCHEMA
    daily=read('scripts/c3po_security_daily.py');reboot=read('scripts/c3po_security_reboot.py');guard=read('scripts/c3po_security_guard.py')
    assert 'HOLD = Path("/etc/c3po/security-maintenance.hold")' in daily and 'CONFIG = Path("/etc/c3po/security-automation.json")' in daily
    assert 'MARKER = Path("/run/c3po-security/reboot.pending")' in reboot and 'REQUIRED = Path("/var/run/reboot-required")' in reboot
    assert 'REPORT = "'+p.AUTOMATION_REPORT+'"' in daily and "TRIAL_ROOT = Path('/mnt/day-d-data')" in guard and p.DATA_SOURCES[0]=='/mnt/day-d-data'
    for action in p.REBOOT_ACTIONS:assert '"'+action+'"' in daily+reboot,action
    for status in p.AUTOMATION_STATUS:assert '"'+(status if status in daily else status[len('reboot_'):])+'"' in daily+reboot,status
    assert p.HOST_REPORT_SCHEMA in read('scripts/c3po-host-security-snapshot.py') and p.HOST_REPORT in read('scripts/c3po-host-security-snapshot.py')
    installer=read('scripts/install-security-daily.sh')
    for name in p.MODULES:assert name in installer and '/usr/local/lib/c3po-security' in installer
    for name in p.UNIT_FILES:assert (CHECKOUT/'c3po'/'deployment'/('reader' if 'reader' in name else 'massive-supervisor')/name).is_file(),name
    for name in ('c3po-security-daily.timer','c3po-security-watchdog.timer','c3po-host-security-snapshot.timer','c3po-unattended-upgrades-healthcheck-failure.service'):
        assert name in p.UNITS and (CHECKOUT/'ops'/'systemd'/name).is_file()
    readers=read('c3po/deployment/reader/README.md')+read('c3po/deployment/massive-supervisor/README.md')
    for path,form,mode,_ in p.LAYOUT:
        if path.startswith(('/etc/c3po','/var/lib/c3po','/opt/c3po')):assert path in readers,path
    assert p.JOURNAL_ROOT in readers and p.STATE_ROOT in readers and "APP_DIR=/opt/chief-of-staff-digital" in read('.github/workflows/c3po-pipeline.yml')
    assert '.deploy-version' in read('.github/workflows/c3po-pipeline.yml') and p.APP_DIR=='/opt/chief-of-staff-digital'
