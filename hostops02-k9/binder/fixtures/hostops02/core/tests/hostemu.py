"""Emulated host for the HOSTOPS02 tests. Synthetic and in memory: no SSH, host, credential, docker binary or GO.

Derived from the emulation of HOSTOPS01 (same Go template subset with typed execution first and the raw-JSON fallback
with missingkey=error, same in-memory tree with a log of every call and one hook that can fail or kill any call) and
extended with what the frozen core adds:
  templates   eq, ne, or, and, not, split, lower, len; a variable assigned with "=" in an inner block; else-if
  docker      container inspect, ps -a, an attached `docker run` (options parsed as the CLI parses them; what the
              container does is a function the test gives), docker compose config and up of one service
  host        standard input, variables, the time and output limit of every command; flock and pause; a way to make
              a command hang before or after its effect, or not start at all
world() is the host as the signed read-only receipts describe it before any operation of the epoch: Docker 29.5.3 on
the containerd snapshotter, systemd 255, the compose project under /opt/chief-of-staff-digital with eight services
(c3po-r2d2-worker-1 among them), the data volume on a device of its own, nothing of the supervisor provisioned. Every
device and inode number, container and image ID, and every value of an environment is synthetic: no number, ID or
value of the real host is carried by these files. The shapes that were never observed on the host say so where they
are defined.
"""
import copy
import errno
import fcntl
import hashlib
import json
import os
import re
import stat
import types

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
def basic(value):
    if isinstance(value,Number):return 'number-string'
    if type(value) is bool:return 'bool'
    if type(value) is int:return 'int'
    if type(value) is str:return 'string'
    raise ExecError('invalid type for comparison')
def go_eq(*values):
    if len(values)<2:raise ExecError('missing argument for comparison')
    first=values[0];kind=basic(first)
    for other in values[1:]:
        if basic(other)!=kind:raise ExecError('incompatible types for comparison')
        if first==other:return True
    return False
def go_ne(*values):
    if len(values)!=2:raise ExecError('wrong number of args for ne')
    return not go_eq(*values)
def go_or(*values):
    if not values:raise ExecError('wrong number of args for or')
    for value in values:
        if truth(value):return value
    return values[-1]
def go_and(*values):
    if not values:raise ExecError('wrong number of args for and')
    for value in values:
        if not truth(value):return value
    return values[-1]
def go_not(*values):
    if len(values)!=1:raise ExecError('wrong number of args for not')
    return not truth(values[0])
def go_split(*values):
    if len(values)!=2 or not all(type(value) is str for value in values):raise ExecError('wrong type for value; expected string')
    text,separator=values
    return text.split(separator) if separator else list(text)
def go_lower(*values):
    if len(values)!=1 or type(values[0]) is not str:raise ExecError('wrong type for value; expected string')
    return values[0].lower()
def go_len(*values):
    if len(values)!=1 or type(values[0]) not in (str,list,dict):raise ExecError('len of type')
    return len(values[0])
FUNCTIONS={'json':go_json,'index':go_index,'eq':go_eq,'ne':go_ne,'or':go_or,'and':go_and,'not':go_not,'split':go_split,'lower':go_lower,'len':go_len}

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
        if c=='=':tokens.append(('assign',None,glued));i+=1;continue
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
    names=[];assign=False
    if pos<len(tokens) and tokens[pos][0]=='var':
        if pos+1<len(tokens) and tokens[pos+1][0]=='declare':names=[tokens[pos][1]];pos+=2
        elif pos+1<len(tokens) and tokens[pos+1][0]=='assign':
            if nested:raise TemplateSyntax('unexpected = in operand')
            names=[tokens[pos][1]];assign=True;pos+=2
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
    return (names,commands,assign),pos

def parse(template):
    parts=split(template);index=[0]
    def conditional(kind,tokens,start):
        pipe,end=parse_pipeline(tokens,start,allow_two=kind=='range')
        body,closer=block(('end','else'));other=[]
        if closer=='else':other,closer=block(('end',))
        elif type(closer) is tuple:
            if kind=='range':raise NotImplementedError('else-if after range is not emulated')
            other=[conditional('if',closer[1],0)]
        return (kind,pipe,body,other)
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
                if len(value)>1:
                    # {{else if x}} is {{else}}{{if x}} sharing the one {{end}}; else-with and else-range are not emulated
                    if head[1]!='else' or value[1][:2]!=('ident','if'):raise NotImplementedError('only else-if is emulated')
                    return nodes,('elseif',value[2:])
                return nodes,head[1]
            if head[0]=='ident' and head[1] in ('if','with','range'):
                nodes.append(conditional(head[1],value,1));continue
            pipe,end=parse_pipeline(value,0);nodes.append(('print',pipe))
        if closers:raise TemplateSyntax('unexpected EOF')
        return nodes,None
    return block(())[0]

class Scope:
    """Variables of one block. := declares here; = changes the nearest declaration, in whichever enclosing block it is."""
    def __init__(self,parent=None):self.values={};self.parent=parent
    def holder(self,name):
        scope=self
        while scope is not None:
            if name in scope.values:return scope
            scope=scope.parent
        raise ExecError('undefined variable %s'%name)
    def __contains__(self,name):
        try:self.holder(name);return True
        except ExecError:return False
    def __getitem__(self,name):return self.holder(name).values[name]
    def declare(self,name,value):self.values[name]=value
    def assign(self,name,value):self.holder(name).values[name]=value
    def store(self,pipe,value):
        if pipe[2]:self.assign(pipe[0][0],value)
        else:self.declare(pipe[0][0],value)

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
                if node[1][0]:variables.store(node[1],value)
                else:out.append(show(value))
            elif node[0] in ('if','with'):
                scope=Scope(variables);value=self.pipeline(node[1],dot,scope)
                if node[1][0]:scope.store(node[1],value)
                if truth(value):self.walk(node[2],value if node[0]=='with' else dot,scope,out)
                else:self.walk(node[3],dot,Scope(variables),out)
            else:
                value=self.pipeline(node[1],dot,variables);names=node[1][0]
                if isinstance(value,TypedMap):value=value.data
                if value is None:items=[]
                elif type(value) is list:items=list(enumerate(value))
                elif type(value) is dict:items=[(key,value[key]) for key in sorted(value)]
                else:raise ExecError("range can't iterate over %s"%type(value).__name__)
                if not items:self.walk(node[3],dot,Scope(variables),out)
                for key,element in items:
                    scope=Scope(variables)
                    if len(names)==1:scope.declare(names[0],element)
                    elif len(names)==2:scope.declare(names[0],key);scope.declare(names[1],element)
                    self.walk(node[2],element,scope,out)
def execute(nodes,data,missing_error):
    out=[];top=Scope();top.declare('$',data);Engine(missing_error).walk(nodes,data,top,out);return ''.join(out)

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
INFO=fields('Driver','DockerRootDir','InitBinary','ServerVersion','HTTPProxy','Name',SecurityOptions=('slice','SecurityOptions'),
            DriverStatus=('slice','DriverStatus'))
VERSION=fields(Client=('ptr','Client',fields('Version')),Server=('ptr','Server',fields('Version')))
PS=fields('ID','Names','State','Image')
LS=fields('ID','Repository','Tag')

_SERIAL=[0]
def synthetic_id(label):
    """A 64-hex identifier that is new at every call: what the engine gives a container it creates."""
    _SERIAL[0]+=1;return hashlib.sha256(('%s#%d'%(label,_SERIAL[0])).encode()).hexdigest()
def container(name,image_id,reference,environment,*,project=None,service=None,running=True,restarts=0,health=None):
    """One container as `docker inspect` describes it (only the members the templates of this family reach)."""
    serial=_SERIAL[0]+1;state={'Status':'running' if running else 'exited','Running':running,'Paused':False,'Restarting':False,'Dead':False,
                              'Pid':4000+serial if running else 0,'ExitCode':0,'StartedAt':'2026-10-02T15:%02d:%02d.000000000Z'%(serial//60%60,serial%60),
                              'FinishedAt':'0001-01-01T00:00:00Z'}
    if health is not None:state['Health']={'Status':health,'FailingStreak':0}
    labels={} if project is None else {'com.docker.compose.project':project,'com.docker.compose.service':service}
    return {'Id':synthetic_id(name),'Name':'/'+name,'Image':image_id,'RestartCount':restarts,'Created':'x','Path':'python','Driver':'overlayfs',
            'Platform':'linux','State':state,'Config':{'Hostname':'x','User':'','Image':reference,'Env':list(environment),'Labels':labels},
            'HostConfig':{'NetworkMode':'default','Binds':[]},'Mounts':[],'NetworkSettings':{'Networks':{}}}

RUN_FLAGS=('--rm','-i','--init','--read-only')
RUN_VALUES=('--pull','--user','--network','--cap-drop','--security-opt','--mount','--name')
def parse_mount(value):
    """--mount as the CLI reads it, for the one form this family writes: type=bind,source=S,target=T[,readonly]."""
    found={};flags=[]
    for item in value.split(','):
        key,equals,rest=item.partition('=')
        if equals:found[key]=rest
        else:flags.append(key)
    assert set(found)=={'type','source','target'} and found['type']=='bind' and flags in ([],['readonly']),'mount outside the emulated form: %r'%value
    return {'source':found['source'],'target':found['target'],'read_only':flags==['readonly']}

class RunCall:
    """One attached `docker run`, parsed as the CLI parses it: options up to the first word that is not one, then the
    image, then the command. What the container does is the test's function; it reaches the host only through the
    binds, with the methods below (a read-only bind and the read-only root filesystem refuse a write, as the kernel does)."""
    def __init__(self,docker,arguments,stdin,environment):
        self.docker,self.stdin,self.environment=docker,stdin,dict(environment or {})
        self.flags=[];self.options={};self.mounts=[];index=0
        while index<len(arguments) and arguments[index].startswith('-'):
            word=arguments[index]
            if word in RUN_FLAGS:self.flags.append(word);index+=1
            elif word in RUN_VALUES:
                value=arguments[index+1];index+=2
                if word=='--mount':self.mounts.append(parse_mount(value))
                else:self.options.setdefault(word,[]).append(value)
            else:raise AssertionError('docker run option outside the emulated set: %r'%word)
        assert index<len(arguments),'docker run without an image'
        self.image=arguments[index];self.command=list(arguments[index+1:]);self.name=(self.options.get('--name') or [None])[0]
        self.network=(self.options.get('--network') or ['bridge'])[0];self.read_only_root='--read-only' in self.flags
    def bound(self,path):
        """(host path, mount) of a container path that lies in a bind; (None, None) otherwise."""
        for mount in sorted(self.mounts,key=lambda mount:-len(mount['target'])):
            if path==mount['target'] or path.startswith(mount['target'].rstrip('/')+'/'):
                return mount['source']+path[len(mount['target']):],mount
        return None,None
    def node(self,path):
        source,_=self.bound(path);return None if source is None else self.docker.host.tree.get(source)
    def listdir(self,path):
        node=self.node(path)
        if node is None or node.kind!='dir':raise FileNotFoundError(errno.ENOENT,'absent')
        return sorted(node.children)
    def read(self,path):
        node=self.node(path)
        if node is None or node.kind!='file':raise FileNotFoundError(errno.ENOENT,'absent')
        return bytes(node.content)
    def stat(self,path):
        node=self.node(path)
        if node is None:raise FileNotFoundError(errno.ENOENT,'absent')
        return node.stat()
    def write(self,path,content,mode=0o600,exclusive=True):
        """Create a regular file as uid 0 through a bind. EROFS through a read-only bind or outside every bind when
        the root filesystem is read-only."""
        source,mount=self.bound(path)
        if mount is None:
            if self.read_only_root:raise OSError(errno.EROFS,'read-only file system')
            raise AssertionError('a write outside every bind is not emulated')
        if mount['read_only']:raise OSError(errno.EROFS,'read-only file system')
        tree=self.docker.host.tree;parent=tree.get(source.rsplit('/',1)[0] or '/')
        if parent is None or parent.kind!='dir':raise FileNotFoundError(errno.ENOENT,'absent')
        name=source.rsplit('/',1)[1]
        if name in parent.children:
            if exclusive:raise FileExistsError(errno.EEXIST,'exists')
            parent.children[name].content=bytearray(content);return
        tree.next+=1;node=Node('file',uid=0,gid=0,mode=mode,dev=parent.dev,ino=tree.next,content=content);parent.children[name]=node
        self.docker.host.log.append(('container-write',source,len(content)))


class FakeDocker:
    """Docker CLI behaviour for the fixed argv set of the core. image ls and image tag are documented behaviour;
    container inspect and ps print what the post-deploy readback saw on the host; `run` and `compose` are documented
    behaviour that this family has not run on the host."""
    def __init__(self,images,info,version,containers=()):
        self.images,self.info,self.version=images,info,version;self.containers=list(containers)
        self.modes=[];self.tag_returncode=0;self.tag_effect=True;self.before=None;self.ls_returncode=0;self.ls_override=None
        self.ps_returncode=0;self.inspect_returncode=0
        self.host=None;self.compose=None;self.runs=[];self.on_run=None;self.environments=[]
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
    def find(self,reference):
        for item in self.images:
            if reference==item['Id'] or reference in (item.get('RepoTags') or []):return item
        return None
    def container(self,reference):
        """By full ID or by name, as the CLI resolves an argument (ID prefixes are not emulated)."""
        for item in self.containers:
            if reference in (item['Id'],item['Name'],item['Name'][1:]):return item
        return None
    def run(self,args,stdin=None,environment=None):
        self.environments.append(dict(environment or {}))
        if self.before:self.before(self,args)
        if args[:3]==['image','inspect','--format'] and len(args)==5:
            item=self.find(args[4])
            return (1,b'') if item is None else self.render(args[3],IMAGE,item,True)
        if args[:4]==['image','ls','--no-trunc','--format'] and len(args)==6:
            if self.ls_returncode:return self.ls_returncode,b''
            if self.ls_override is not None:return 0,self.ls_override
            out=b''
            for item in self.images:
                for reference in item.get('RepoTags') or []:
                    repository,_,tag=reference.rpartition(':')
                    if repository!=args[5]:continue
                    code,line=self.render(args[4],LS,{'ID':item['Id'],'Repository':repository,'Tag':tag},False)
                    if code:return code,b''
                    out+=line
            return 0,out
        if args[:2]==['image','tag'] and len(args)==4:
            if self.tag_returncode:return self.tag_returncode,b''
            item=self.find(args[2])
            if item is None:return 1,b''
            if self.tag_effect:
                for other in self.images:
                    if args[3] in (other.get('RepoTags') or []):other['RepoTags'].remove(args[3])
                item.setdefault('RepoTags',[]).append(args[3])
            return 0,b''
        if args[:2]==['info','--format'] and len(args)==3:return self.render(args[2],INFO,self.info,False)
        if args[:2]==['version','--format'] and len(args)==3:return self.render(args[2],VERSION,self.version,False)
        if args[:3]==['container','inspect','--format'] and len(args)==5:
            if self.inspect_returncode:return self.inspect_returncode,b''
            item=self.container(args[4])
            return (1,b'') if item is None else self.render(args[3],CONTAINER,item,True)
        if args[:4]==['ps','-a','--no-trunc','--format'] and len(args)==5:
            if self.ps_returncode:return self.ps_returncode,b''
            out=b''
            for item in self.containers:
                code,line=self.render(args[4],PS,{'ID':item['Id'],'Names':item['Name'][1:],'State':item['State']['Status'],'Image':item['Config']['Image']},False)
                if code:return code,b''
                out+=line
            return 0,out
        if args[:1]==['run']:
            call=RunCall(self,args[1:],stdin,environment);self.runs.append(call)
            assert '--rm' in call.flags and call.options.get('--pull')==['never'],'this family never runs a container that stays or pulls'
            # 125: the engine could not create or start the container (image not present with --pull never, bind source absent)
            if self.find(call.image) is None or self.find(call.image)['Id']!=call.image:return 125,b''
            for mount in call.mounts:
                node=self.host.tree.get(mount['source'])
                if node is None:return 125,b''
            if call.name is not None and self.container(call.name) is not None:return 125,b''
            assert self.on_run is not None,'the test gave no behaviour for the container (docker.on_run)'
            code,out=self.on_run(call);assert type(code) is int and type(out) is bytes
            return code,out
        if args[:1]==['compose']:
            assert self.compose is not None,'the test gave no compose project (docker.compose)'
            return self.compose.run(args[1:],stdin,dict(environment or {}))
        raise AssertionError('docker argv outside the fixed set: %r'%args[:3])


UP_OPTIONS=['-d','--no-deps','--no-build','--pull','never','--force-recreate']
class FakeCompose:
    """`docker compose` for one project, as far as the core uses it. The global options are parsed as the CLI parses
    them and nothing is defaulted: a call without --project-name, --env-file and at least one -f is an assertion.
      config --format json   prints `base` (what the first file renders to, a dict) with C3PO_BUILD_SHA interpolated
                             from the variables of the call ("development" when absent, as compose.yml defaults it)
                             and every further file merged over it. A further file is a JSON object in the emulated
                             tree, or standard input for "-": services.<name>.environment is merged key by key.
      up -d --no-deps --no-build --pull never --force-recreate <service>
                             replaces the container <project>-<service>-1 by a new one (new ID, new start instant,
                             restart count 0) whose environment is the image's plus the rendered one.
    Exit statuses: 14 for a file that does not exist, 15 for a file that is not an object (documented compose values;
    the core only distinguishes zero from non-zero)."""
    def __init__(self,docker,project,env_file,base_file,base):
        self.docker,self.project,self.env_file,self.base_file,self.base=docker,project,env_file,base_file,base
        self.calls=[];self.config_returncode=0;self.config_output=None;self.up_returncode=0;self.up_effect=True;self.after_up=None
    def parse(self,arguments):
        found={'project':None,'env_file':None,'files':[]};index=0
        while index<len(arguments) and arguments[index].startswith('-') and arguments[index]!='-':
            word=arguments[index];assert word in ('--project-name','--env-file','-f'),'compose option outside the emulated set: %r'%word
            value=arguments[index+1];index+=2
            if word=='-f':found['files'].append(value)
            else:
                key='project' if word=='--project-name' else 'env_file';assert found[key] is None;found[key]=value
        assert found['project'] is not None and found['env_file'] is not None and found['files'],'an implicit project, environment file or file list'
        return found,list(arguments[index:])
    def render(self,files,stdin,environment):
        tree=self.docker.host.tree;result=copy.deepcopy(self.base)
        for service in result['services'].values():
            if 'C3PO_BUILD_SHA' in service.get('environment',{}):service['environment']['C3PO_BUILD_SHA']=environment.get('C3PO_BUILD_SHA','development')
        for item in files[1:]:
            if item=='-':
                if stdin is None:return 15,None
                raw=stdin
            else:
                node=tree.get(item)
                if node is None or node.kind!='file':return 14,None
                raw=bytes(node.content)
            try:override=json.loads(raw)
            except ValueError:return 15,None
            if type(override) is not dict or type(override.get('services',{})) is not dict:return 15,None
            for name,changes in override.get('services',{}).items():
                service=result['services'].setdefault(name,{})
                for key,value in changes.items():
                    if key=='environment':service.setdefault('environment',{}).update(value)
                    else:service[key]=value
        return 0,result
    def run(self,arguments,stdin,environment):
        found,rest=self.parse(arguments);self.calls.append(dict(found,command=rest,variables=dict(environment),stdin=stdin))
        tree=self.docker.host.tree
        if found['project']!=self.project:raise AssertionError('another compose project: %r'%found['project'])
        if tree.get(found['env_file']) is None or tree.get(found['files'][0]) is None:return 14,b''
        assert found['env_file']==self.env_file and found['files'][0]==self.base_file,'the emulated project has one environment file and one base file'
        assert found['files'].count('-')<=1 and (found['files'][-1]=='-' or '-' not in found['files']),'standard input is the last file'
        if rest==['config','--format','json']:
            if self.config_returncode:return self.config_returncode,b''
            if self.config_output is not None:return 0,self.config_output
            code,result=self.render(found['files'],stdin,environment)
            return (code,b'') if code else (0,json.dumps(result,indent=2).encode()+b'\n')
        if rest[:1]==['up']:
            assert rest[1:-1]==UP_OPTIONS and len(rest)==len(UP_OPTIONS)+2,'compose up outside the one emulated form: %r'%rest
            service=rest[-1];assert stdin is None and '-' not in found['files']
            if self.up_returncode:
                if not self.up_effect:return self.up_returncode,b''
            code,result=self.render(found['files'],None,environment)
            if code:return code,b''
            if service not in result['services']:return 1,b''
            if self.up_effect:self.recreate(service,result['services'][service])
            return self.up_returncode,b''
        raise AssertionError('compose command outside the emulated set: %r'%rest[:2])
    def recreate(self,service,rendered):
        docker=self.docker;name='%s-%s-1'%(self.project,service);old=docker.container(name)
        image=docker.find(rendered['image']);assert image is not None,'the rendered image is not in the store'
        environment=list(image['Config'].get('Env') or [])+['%s=%s'%(key,value) for key,value in sorted(rendered.get('environment',{}).items()) if value is not None]
        new=container(name,image['Id'],rendered['image'],environment,project=self.project,service=service)
        if old is None:docker.containers.append(new)
        else:docker.containers[docker.containers.index(old)]=new
        self.docker.host.log.append(('compose-recreate',name))
        if self.after_up is not None:self.after_up(self,new)
        return new


# ---------------------------------------------------------------- in-memory host
NOATIME=1<<30
ROOT_DEVICE,DATA_DEVICE=801,811      # neutral: "/" (with /etc, /var/lib, /opt, /mnt on it) and the data volume, two filesystems
class Death(BaseException):
    """The process dies here: nothing after this call happens, and no receipt exists."""
class Node:
    def __init__(self,kind,uid=0,gid=0,mode=0o755,dev=ROOT_DEVICE,ino=0,content=b''):
        self.kind,self.uid,self.gid,self.mode,self.dev,self.ino=kind,uid,gid,mode,dev,ino
        self.content=bytearray(content);self.children={};self.atime=1;self.mtime=1;self.ctime=1;self.nlink=1;self.synced=False
        self.target=''                                              # text of a symbolic link
    def stat(self):
        form={'dir':stat.S_IFDIR,'file':stat.S_IFREG,'symlink':stat.S_IFLNK,'fifo':stat.S_IFIFO}[self.kind]
        return types.SimpleNamespace(st_mode=form|self.mode,st_uid=self.uid,st_gid=self.gid,st_dev=self.dev,st_ino=self.ino,
                                     st_nlink=self.nlink,st_size=len(self.content),st_atime_ns=self.atime,st_mtime_ns=self.mtime,
                                     st_ctime_ns=self.ctime)
class Tree:
    def __init__(self):self.root=Node('dir',ino=2);self.next=5000
    def add(self,path,kind='dir',**attributes):
        """Create path (and, as root-owned 0755 directories on the parent's device, whatever is missing above it).
        Attributes (uid, gid, mode, dev, ino, content, target) apply to the last component only, and only when it is created."""
        node=self.root;parts=path.strip('/').split('/')
        for index,part in enumerate(parts):
            if part not in node.children:
                self.next+=1;last=index==len(parts)-1
                child=Node(kind if last else 'dir',dev=node.dev,ino=self.next)
                if last:
                    for key,value in attributes.items():setattr(child,key,bytearray(value) if key=='content' else value)
                node.children[part]=child
            node=node.children[part]
        return node
    def get(self,path):
        node=self.root
        for part in [part for part in path.strip('/').split('/') if part]:
            node=node.children.get(part)
            if node is None:return None
        return node
    def remove(self,path):
        parts=path.strip('/').split('/');node=self.root
        for part in parts[:-1]:node=node.children[part]
        del node.children[parts[-1]]
    def snapshot(self):
        """Everything a write could change, as a plain structure: names, kind, owner, mode, identity, links, bytes."""
        def one(node):
            return (node.kind,node.uid,node.gid,node.mode,node.dev,node.ino,node.nlink,bytes(node.content),
                    {name:one(child) for name,child in sorted(node.children.items())})
        return one(self.root)
    def paths(self):
        found=[]
        def walk(node,prefix):
            for name,child in sorted(node.children.items()):
                found.append(prefix+'/'+name);walk(child,prefix+'/'+name)
        walk(self.root,'');return found

MUTATING=('mkdir','create','write','link','unlink')
WRITE_FLAGS=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND
COMMAND_SECONDS=(8,15,20,30,40)                # the classes of parts/runner.py; a test pins the equality
class FakeHost:
    """An emulated host with exactly the calls the core's Native classes make. It has no chmod, chown, rename, truncate
    or utime: a source that needs one fails. Every call is logged with its flags; one hook can fail or kill any call."""
    def __init__(self,tree,docker,vfs):
        self.tree,self.docker,self.vfs=tree,docker,vfs;docker.host=self
        self.fds={};self.next=100;self.log=[];self.calls=0;self.noatime_available=True
        self.units={};self.is_enabled={};self.systemd_version=b'systemd 255 (255.4-1ubuntu8.17)\n+PAM +AUDIT +SELINUX +APPARMOR +IMA\n'
        self.actor=(0,0);self.mask=0o022;self.creator=(0,0);self.grpid=False;self.hook=None;self.commands=[]
        self.created_device=None                                    # set to give every object this host creates another device
        self.readonly=False
        # the source's own exception classes, set by the tests (family.world does it)
        self.refused=ValueError;self.not_started=ValueError
        # commands: what never starts, what hangs before it does anything, what hangs after it took effect.
        # Each is a set of tool names ('docker') or of (first, second) argv words after the binary (('compose','up')).
        self.absent=set();self.hang=set();self.hang_after=set()
        # the deployment lock: who else holds it ('EX', 'SH' or None), and after how many refused requests they let go
        self.lock_holder={};self.lock_released_after=None;self.locks={};self.paused=0.0;self.on_pause=None
    # -- bookkeeping
    def event(self,name,*detail):
        self.calls+=1;self.log.append((name,)+detail)
        if self.hook is not None:self.hook(self,name,detail,self.calls)
    def path_of(self,fd):return self.fds[fd][3]
    def effect_commands(self):
        """The commands that change the engine: image tag, compose up, and a run with a bind that is not read-only."""
        found=[]
        for entry in self.commands:
            argv=entry['argv'][1:]
            if argv[:2]==['image','tag'] or (argv[:1]==['compose'] and 'up' in argv):found.append(entry)
            elif argv[:1]==['run'] and any(word.startswith('type=bind') and not word.endswith(',readonly') for word in argv):found.append(entry)
        return found
    def container_runs(self):return [entry for entry in self.commands if entry['argv'][1:2]==['run']]
    def mutating(self):
        return [entry for entry in self.log if entry[0] in MUTATING or entry[0] in ('container-write','compose-recreate')]+self.effect_commands()
    # -- read primitives
    def identity(self):return self.actor
    def noatime(self):
        if not self.noatime_available:raise self.refused('NOATIME_UNAVAILABLE')
        return NOATIME
    def open(self,name,flags,dir_fd=None):
        assert flags&os.O_NOFOLLOW,'every open must be nofollow'
        assert not flags&WRITE_FLAGS,'a read open carries no write or create flag'
        if dir_fd is None:
            assert name=='/','only the root is opened by absolute path';node=self.tree.root;path='/'
        else:
            assert '/' not in name and name not in ('','.','..');parent=self.fds[dir_fd]
            node=parent[0].children.get(name);path=parent[3].rstrip('/')+'/'+name
        self.event('open',path,flags)
        if node is None:raise FileNotFoundError(errno.ENOENT,'absent')
        if node.kind=='symlink':raise OSError(errno.ELOOP,'link')
        if flags&os.O_DIRECTORY and node.kind!='dir':raise NotADirectoryError(errno.ENOTDIR,'not a directory')
        self.next+=1;self.fds[self.next]=[node,flags,0,path];return self.next
    def close(self,fd):
        self.locks.pop(fd,None);del self.fds[fd]
    def fstat(self,fd):
        self.event('fstat',self.path_of(fd));return self.fds[fd][0].stat()
    def lstat(self,name,dir_fd):
        assert '/' not in name and name not in ('','.','..');parent=self.fds[dir_fd]
        self.event('lstat',parent[3].rstrip('/')+'/'+name)
        node=parent[0].children.get(name)
        if node is None:raise FileNotFoundError(errno.ENOENT,'absent')
        return node.stat()
    def readlink(self,name,dir_fd):
        assert '/' not in name and name not in ('','.','..');parent=self.fds[dir_fd]
        self.event('readlink',parent[3].rstrip('/')+'/'+name)
        node=parent[0].children.get(name)
        if node is None:raise FileNotFoundError(errno.ENOENT,'absent')
        if node.kind!='symlink':raise OSError(errno.EINVAL,'not a link')
        return node.target
    def fstatvfs(self,fd):
        self.event('fstatvfs',self.path_of(fd));return self.vfs[self.fds[fd][0].dev]
    def read(self,fd,size):
        node,flags,offset,path=self.fds[fd];self.event('read',path)
        assert not flags&os.O_DIRECTORY
        block=bytes(node.content[offset:offset+size]);self.fds[fd][2]+=len(block);return block
    def names(self,fd):
        node,flags,_,path=self.fds[fd];self.event('names',path)
        if not flags&NOATIME:node.atime+=1
        for name in list(node.children):yield name
    # -- the calls of parts/files.py
    def umask(self,mask):
        self.event('umask',mask);old,self.mask=self.mask,mask;return old
    def fresh(self,parent,kind,mode):
        self.tree.next+=1
        node=Node(kind,uid=self.creator[0],gid=self.creator[1],mode=mode&~self.mask&0o7777,
                  dev=parent.dev if self.created_device is None else self.created_device,ino=self.tree.next)
        if parent.mode&stat.S_ISGID or self.grpid:
            node.gid=parent.gid
            if kind=='dir' and parent.mode&stat.S_ISGID:node.mode|=stat.S_ISGID
        return node
    def mkdir(self,name,mode,dir_fd):
        assert '/' not in name and name not in ('','.','..');parent=self.fds[dir_fd];path=parent[3].rstrip('/')+'/'+name
        self.event('mkdir',path,mode)
        if self.readonly:raise OSError(errno.EROFS,'read-only')
        if name in parent[0].children:raise FileExistsError(errno.EEXIST,'exists')
        parent[0].children[name]=self.fresh(parent[0],'dir',mode)
    def create(self,name,flags,mode,dir_fd):
        assert '/' not in name and name not in ('','.','..');parent=self.fds[dir_fd];path=parent[3].rstrip('/')+'/'+name
        self.event('create',path,flags,mode)
        if self.readonly:raise OSError(errno.EROFS,'read-only')
        node=parent[0].children.get(name)
        if node is not None:
            if flags&os.O_EXCL:raise FileExistsError(errno.EEXIST,'exists')
            if node.kind=='symlink':
                if flags&os.O_NOFOLLOW:raise OSError(errno.ELOOP,'link')
                raise AssertionError('a creating open followed a symbolic link')
            if flags&os.O_TRUNC:node.content=bytearray()
        else:
            assert flags&os.O_CREAT;node=self.fresh(parent[0],'file',mode);parent[0].children[name]=node
        self.next+=1;self.fds[self.next]=[node,flags,0,path];return self.next
    def write(self,fd,data):
        node,flags,_,path=self.fds[fd];self.event('write',path,len(data))
        assert flags&os.O_WRONLY and type(data) is bytes
        node.content.extend(data);node.mtime+=1;return len(data)
    def fsync(self,fd):
        self.event('fsync',self.path_of(fd));self.fds[fd][0].synced=True
    def link(self,source,target,dir_fd):
        parent=self.fds[dir_fd];prefix=parent[3].rstrip('/')+'/'
        self.event('link',prefix+source,prefix+target)
        if target in parent[0].children:raise FileExistsError(errno.EEXIST,'exists')
        node=parent[0].children[source];parent[0].children[target]=node;node.nlink+=1
    def unlink(self,name,dir_fd):
        parent=self.fds[dir_fd];self.event('unlink',parent[3].rstrip('/')+'/'+name)
        node=parent[0].children.pop(name);node.nlink-=1
    # -- the calls of parts/lock.py
    def flock(self,fd,operation):
        node,flags,_,path=self.fds[fd];self.event('flock',path,operation)
        assert node.kind=='file' and not flags&WRITE_FLAGS
        if operation==fcntl.LOCK_UN:
            self.locks.pop(fd,None);return
        assert operation&fcntl.LOCK_NB,'a blocking flock would park the run'
        exclusive=bool(operation&fcntl.LOCK_EX);assert exclusive!=bool(operation&fcntl.LOCK_SH)
        other=self.lock_holder.get(path)
        if other=='EX' or (other=='SH' and exclusive):
            if self.lock_released_after is not None:
                self.lock_released_after-=1
                if self.lock_released_after<=0:self.lock_holder.pop(path,None);self.lock_released_after=None
            raise BlockingIOError(errno.EWOULDBLOCK,'locked')
        self.locks[fd]='EX' if exclusive else 'SH'
    def lock_held(self,path):
        """'EX', 'SH' or None: the lock this run holds on a path right now."""
        for fd,mode in self.locks.items():
            if self.fds[fd][3]==path:return mode
        return None
    def pause(self,seconds):
        self.event('pause',seconds);self.paused+=seconds
        if self.on_pause is not None:self.on_pause(self)
    # -- fixed commands
    def selected(self,group,argv):
        tool=argv[0].rsplit('/',1)[1];return tool in group or tuple(argv[1:3]) in group or any(type(item) is tuple and item==tuple(word for word in argv[1:] if word in item) for item in group)
    def run(self,argv,gate,seconds,capture=True,docker_config=None,stdin=None,variables=None,limit=65536):
        try:gate()
        except self.refused as error:raise self.not_started(str(error)) from None          # as the real runner: an expiry before the process exists
        assert seconds in COMMAND_SECONDS and argv[0].startswith('/') and all(type(item) is str for item in argv)
        assert (stdin is None or (type(stdin) is bytes and stdin)) and (variables is None or type(variables) is dict)
        if self.selected(self.absent,argv):raise self.not_started('COMMAND_NOT_STARTED')
        self.commands.append({'argv':list(argv),'docker_config':docker_config,'capture':capture,'stdin':stdin,'variables':dict(variables or {}),
                              'seconds':seconds,'limit':limit})
        self.event('run',list(argv),docker_config);tool=argv[0].rsplit('/',1)[1]
        if self.selected(self.hang,argv):raise self.refused('COMMAND_TIMEOUT')
        environment=dict(variables or {})
        if docker_config is not None:environment['DOCKER_CONFIG']=docker_config
        if tool=='docker':code,out=self.docker.run(argv[1:],stdin,environment)
        elif tool=='systemctl':
            assert docker_config is None and stdin is None and not variables;code,out=self.systemctl(argv[1:])
        else:raise AssertionError(argv[0])
        if self.selected(self.hang_after,argv):raise self.refused('COMMAND_TIMEOUT')
        if capture and len(out)>limit:raise self.refused('COMMAND_OUTPUT_LIMIT')
        return code,(out if capture else b'')
    def systemctl(self,args):
        if args==['--version']:return 0,self.systemd_version
        if args[0]=='is-enabled' and len(args)==2:
            word=self.is_enabled.get(args[1]);return (1,b'') if word is None else (0 if word.startswith('enabled') else 1,(word+'\n').encode())
        assert args[0]=='show' and args[2::2]==['-p']*((len(args)-2)//2),args
        unit,wanted=args[1],args[3::2]
        defaults={'Id':unit,'LoadState':'not-found','ActiveState':'inactive','SubState':'dead','UnitFileState':'','FragmentPath':'',
                  'DropInPaths':'','WantedBy':'','RequiredBy':'','TriggeredBy':''}
        values=dict(defaults,**self.units.get(unit,{}))
        # systemd prints in its own property order, not in argument order.
        return 0,''.join('%s=%s\n'%(key,values[key]) for key in sorted(wanted,reverse=True) if key in values).encode()


# ---------------------------------------------------------------- a host shaped like the real one
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'      # the release commit (public); the image IDs below are synthetic
BACKEND='sha256:'+'fb'*32      # containerd-store style: a manifest digest, unrelated to any CI image ID
WEB='sha256:'+'7e'*32
DATABASE='sha256:'+'d6'*32
OTHER='sha256:'+'9c'*32
DATA='/mnt/day-d-data'
DEPLOY='/opt/chief-of-staff-digital'
PROJECT='c3po'
ENV_FILE=DEPLOY+'/.env'
COMPOSE_FILE=DEPLOY+'/c3po/compose.yml'
LOCK_DIRECTORY=DEPLOY+'/runtime/security'
LOCK_NAME='deployment.lock'
PIN=DATA+'/.r2d2-v2-pinned'
WORKER='c3po-r2d2-worker-1'
SERVICES={'api':'backend','investor-relations-worker':'backend','valuation-worker':'backend','server-usage-worker':'backend',
          'r2d2-shadow-candidate-worker':'backend','r2d2-worker':'backend','web':'web','db':'database'}
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
INIT='/usr/libexec/docker/docker-init'
SECRET='never-emit-environment-canary'
# Free space of the two filesystems as the HOSTFACTS_01 receipt read it (figures, not identities).
DATA_VFS=dict(f_frsize=4096,f_blocks=25656558,f_bfree=14515632,f_bavail=13200816)
ROOT_VFS=dict(f_frsize=4096,f_blocks=162243833,f_bfree=145319603,f_bavail=145315507)
def free_space(host,bytes_freed):
    """Model space freed on the data volume under some other authorisation (nothing in this family frees space)."""
    blocks,rest=divmod(bytes_freed,4096);assert rest==0 and blocks>0
    old=host.vfs[DATA_DEVICE];host.vfs[DATA_DEVICE]=types.SimpleNamespace(f_frsize=old.f_frsize,f_blocks=old.f_blocks,f_bfree=old.f_bfree+blocks,f_bavail=old.f_bavail+blocks)

def service_environment(service):
    """What compose renders for a backend service: the build revision (interpolated), a database URL that carries
    the password of the environment file, and the service name. Synthetic values; the canary must never leave a run."""
    return {'C3PO_BUILD_SHA':REVISION,'C3PO_DATABASE_URL':'postgresql://c3po:'+SECRET+'@db:5432/c3po','C3PO_SERVICE_NAME':service,
            'EODHD_API_TOKEN':SECRET+'-token'}

def world(*,init=(INIT,)):
    """The baseline before any operation of the epoch: the compose project deployed and running, the data volume
    mounted with the maintenance pin in its root, no supervisor or reader path, no unit of this family."""
    tree=Tree()
    for path in ('/etc/systemd/system','/var/lib/docker','/usr/local/bin','/usr/sbin','/usr/libexec','/usr/lib/systemd/system',
                 '/run/systemd/system','/run/systemd/generator','/proc/sys/kernel/random','/mnt','/opt'):tree.add(path)
    tree.add('/etc/systemd/system/timers.target.wants');tree.add('/etc/systemd/system/multi-user.target.wants')
    tree.add('/etc/systemd/system/multi-user.target.wants/docker.service',kind='symlink',mode=0o777)
    tree.add('/usr/lib/systemd/system/timers.target.wants');tree.add('/usr/lib/systemd/system/docker.service',kind='file',mode=0o644,content=b'[Unit]\n')
    tree.add('/proc/sys/kernel/random/boot_id',kind='file',mode=0o444,content=BOOT)
    for name in ('docker','systemctl'):tree.add('/usr/bin/'+name,kind='file',content=b'ELF')
    for path in init:tree.add(path,kind='file',content=b'ELF')
    tree.get('/mnt').ino=4002;tree.get('/etc/systemd/system').ino=4001;tree.get('/var/lib').ino=4003;tree.get('/opt').ino=4006
    tree.add(DATA,uid=1000,gid=1000,dev=DATA_DEVICE,ino=4005)
    tree.add(DATA+'/lost+found',mode=0o700,dev=DATA_DEVICE);tree.add(DATA+'/provider=synthetic',dev=DATA_DEVICE)
    tree.add(PIN,kind='file',mode=0o600,dev=DATA_DEVICE,content=b'')
    # the deploy tree belongs to the operational account, as the pipeline's rsync leaves it
    tree.add(DEPLOY,uid=1000,gid=1000,ino=4007)
    for path in (DEPLOY+'/c3po',DEPLOY+'/runtime',LOCK_DIRECTORY,LOCK_DIRECTORY+'/maintenance'):tree.add(path,uid=1000,gid=1000)
    tree.add(ENV_FILE,kind='file',uid=1000,gid=1000,mode=0o600,content=('C3PO_DB_PASSWORD='+SECRET+'\nEODHD_API_TOKEN='+SECRET+'-token\n').encode())
    tree.add(COMPOSE_FILE,kind='file',uid=1000,gid=1000,mode=0o644,content=b'services: {}\n')
    tree.add(DEPLOY+'/.deploy-version',kind='file',uid=1000,gid=1000,mode=0o644,content=(REVISION+'\n').encode())
    tree.add(LOCK_DIRECTORY+'/'+LOCK_NAME,kind='file',uid=1000,gid=1000,mode=0o644,content=b'')
    info={'SecurityOptions':['name=apparmor','name=seccomp,profile=builtin','name=cgroupns'],'Driver':'overlayfs',
          'DriverStatus':[['driver-type','io.containerd.snapshotter.v1']],'DockerRootDir':'/var/lib/docker','InitBinary':'docker-init',
          'ServerVersion':'29.5.3','HTTPProxy':'http://never-emit-proxy-canary:3128','Name':'never-emit-hostname-canary'}
    def image(identifier,repository,tags=('production',)):
        return {'Id':identifier,'RepoTags':['%s:%s'%(repository,tag) for tag in tags],'Created':'x','Architecture':'arm64','Os':'linux','Size':1,
                'Config':{'Labels':{'org.opencontainers.image.revision':REVISION},'Env':['PATH=/usr/local/bin:/usr/bin','IMAGE_ENV=never-emit-image-canary']}}
    images=[image(BACKEND,'c3po/backend'),image(WEB,'c3po/web'),image(DATABASE,'c3po/database'),image(OTHER,'c3po/backend',('rollback',))]
    by={'backend':(BACKEND,'c3po/backend:production'),'web':(WEB,'c3po/web:production'),'database':(DATABASE,'c3po/database:production')}
    base={'name':PROJECT,'services':{}};containers=[]
    for service,kind in SERVICES.items():
        environment=service_environment(service) if kind=='backend' else {}
        base['services'][service]={'image':by[kind][1],'environment':dict(environment)}
        containers.append(container('%s-%s-1'%(PROJECT,service),by[kind][0],by[kind][1],
                                    list(images[0]['Config']['Env'])+['%s=%s'%item for item in sorted(environment.items())],
                                    project=PROJECT,service=service,health='healthy' if service=='db' else None))
    docker=FakeDocker(images,info,{'Client':{'Version':'29.5.3'},'Server':{'Version':'29.5.3'}},containers)
    vfs={DATA_DEVICE:types.SimpleNamespace(**DATA_VFS),ROOT_DEVICE:types.SimpleNamespace(**ROOT_VFS)}
    host=FakeHost(tree,docker,vfs)
    docker.compose=FakeCompose(docker,PROJECT,ENV_FILE,COMPOSE_FILE,base)
    host.units['docker.service']={'Id':'docker.service','LoadState':'loaded','ActiveState':'active','SubState':'running','UnitFileState':'enabled'}
    return host

def provision_supervisor(host,journal='journal'):
    """What supervisor operation 2 leaves under placement A: the configuration directory with its two children, the
    private parent with the state root and the journal root. All root:root 0700 and empty, on the root filesystem."""
    for path in ('/etc/c3po-bar','/etc/c3po-bar/manifests','/etc/c3po-bar/docker-cli','/var/lib/c3po-bar','/var/lib/c3po-bar/supervisor',
                 '/var/lib/c3po-bar/'+journal):host.tree.add(path,mode=0o700)
    return host

def rows(host,path):
    """The six-key rows of a path as a read-only receipt would print them (read straight from the emulated tree)."""
    out=[];node=host.tree.root;prefix=''
    def row(path,node):return {'path':path,'device':node.dev,'inode':node.ino,'uid':node.uid,'gid':node.gid,'mode':node.mode}
    out.append(row('/',node))
    for part in [part for part in path.strip('/').split('/') if part]:
        node=node.children[part];prefix+='/'+part;out.append(row(prefix,node))
    return out
