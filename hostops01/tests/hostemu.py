"""Emulated host for the HOSTOPS01 tests. Synthetic and in memory: no SSH, host, credential, docker binary or GO.

The Go template emulation below is the one of the reviewed read-only family (test_hostfacts_once.py), unchanged:
typed execution first, on an execution error a second execution against the raw JSON with missingkey=error, parse
errors for a '{' inside an action. The in-memory host is that family's, extended with the calls the write sources
make (mkdir, exclusive create, write, fsync, link, unlink, umask), a log of every call with its flags, and one hook
that can fail or kill any call. docker image ls / image tag, systemctl is-enabled and the extra show properties are
documented shapes that were never observed on the host.

world() is calibrated to the HOSTFACTS_01 receipt of 2026-10-02T01:51:44Z (stdout sha256 47abfa0a...e528b): Docker
29.5.3, systemd 255 (255.4-1ubuntu8.17), docker-init only at /usr/libexec/docker/docker-init, the data volume root
1000:1000 0755 on a device of its own, "/" and /var/lib on one device, and the free space of both filesystems as
that receipt read it. Every device and inode number here is a neutral synthetic value (ROOT_DEVICE, DATA_DEVICE and
the 40xx inodes below): no device or inode number of the host is carried by these files, and no test needs one, only
that "/" and /var/lib share a device and the data volume has another. The image ID, the names and the canaries stay
synthetic.
"""
import errno
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


class FakeDocker:
    """Docker CLI behaviour for the fixed argv set of the four sources. image ls and image tag are documented
    behaviour (tag silently moves an existing reference); neither was ever observed on the host."""
    def __init__(self,images,info,version):
        self.images,self.info,self.version=images,info,version
        self.modes=[];self.tag_returncode=0;self.tag_effect=True;self.before=None;self.ls_returncode=0;self.ls_override=None
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
    def run(self,args):
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
        raise AssertionError('docker argv outside the fixed set: %r'%args[:3])


# ---------------------------------------------------------------- in-memory host
NOATIME=1<<30
ROOT_DEVICE,DATA_DEVICE=801,811      # neutral: "/" (with /etc, /var/lib, /mnt on it) and the data volume, two filesystems
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
class FakeHost:
    """An emulated host with exactly the calls the four sources use. It has no chmod, chown, rename, truncate or
    utime: a source that needs one fails. Every call is logged with its flags; one hook can fail or kill any call."""
    def __init__(self,tree,docker,vfs):
        self.tree,self.docker,self.vfs=tree,docker,vfs
        self.fds={};self.next=100;self.log=[];self.calls=0;self.hang=set();self.noatime_available=True
        self.units={};self.is_enabled={};self.systemd_version=b'systemd 255 (255.4-1ubuntu8.17)\n+PAM +AUDIT +SELINUX +APPARMOR +IMA\n'
        self.actor=(0,0);self.mask=0o022;self.creator=(0,0);self.grpid=False;self.hook=None;self.commands=[]
        self.created_device=None                                    # set to give every object this host creates another device
        self.clock_log=None;self.readonly=False;self.refused=ValueError      # set to the source's own Refused class by the tests
    # -- bookkeeping
    def event(self,name,*detail):
        self.calls+=1;self.log.append((name,)+detail)
        if self.hook is not None:self.hook(self,name,detail,self.calls)
    def path_of(self,fd):return self.fds[fd][3]
    def mutating(self):return [entry for entry in self.log if entry[0] in MUTATING or (entry[0]=='run' and entry[1][1:3]==['image','tag'])]
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
    def close(self,fd):del self.fds[fd]
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
    # -- the calls of the write sources
    def umask(self,mask):
        self.event('umask',mask);old,self.mask=self.mask,mask;return old
    def fresh(self,parent,kind,mode):
        self.tree.next+=1
        node=Node(kind,uid=self.creator[0],gid=self.creator[1],mode=mode&~self.mask&0o7777,
                  dev=parent.dev if self.created_device is None else self.created_device,ino=self.tree.next)
        if kind=='dir' and (parent.mode&stat.S_ISGID or self.grpid):
            node.gid=parent.gid
            if parent.mode&stat.S_ISGID:node.mode|=stat.S_ISGID
        return node
    def mkdir(self,name,mode,dir_fd):
        assert '/' not in name and name not in ('','.','..');parent=self.fds[dir_fd];path=parent[3].rstrip('/')+'/'+name
        self.event('mkdir',path,mode)
        if self.readonly:raise OSError(errno.EROFS,'read-only')
        if name in parent[0].children:raise FileExistsError(errno.EEXIST,'exists')
        parent[0].children[name]=self.fresh(parent[0],'dir',mode);parent[0].nlink+=0
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
    # -- fixed commands
    def run(self,argv,gate,seconds,capture=True,docker_config=None):
        gate();assert seconds==8 and argv[0].startswith('/') and all(type(item) is str for item in argv)
        self.commands.append({'argv':list(argv),'docker_config':docker_config,'capture':capture})
        self.event('run',list(argv),docker_config);tool=argv[0].rsplit('/',1)[1]
        if tool in self.hang or tuple(argv[1:3]) in self.hang:raise self.refused('COMMAND_TIMEOUT')
        if tool=='docker':code,out=self.docker.run(argv[1:])
        elif tool=='systemctl':
            assert docker_config is None;code,out=self.systemctl(argv[1:])
        else:raise AssertionError(argv[0])
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
REVISION='69c8e632802a06f81c32edc825462a6d2efe6485'
BACKEND='sha256:'+'fb'*32      # containerd-store style: a manifest digest, unrelated to any CI image ID
OTHER='sha256:'+'9c'*32
DATA='/mnt/day-d-data'
BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
INIT='/usr/libexec/docker/docker-init'
# Free space as the HOSTFACTS_01 receipt read it. The data volume holds 54070542336 bytes available: 383451136 above the
# producer's floor, less than one session (603979776), and 2636447744 short of the five-session number 56706990080.
DATA_VFS=dict(f_frsize=4096,f_blocks=25656558,f_bfree=14515632,f_bavail=13200816)
ROOT_VFS=dict(f_frsize=4096,f_blocks=162243833,f_bfree=145319603,f_bavail=145315507)
def free_space(host,bytes_freed):
    """Model space freed on the data volume under some other authorisation (nothing in this family frees space)."""
    blocks,rest=divmod(bytes_freed,4096);assert rest==0 and blocks>0
    old=host.vfs[DATA_DEVICE];host.vfs[DATA_DEVICE]=types.SimpleNamespace(f_frsize=old.f_frsize,f_blocks=old.f_blocks,f_bfree=old.f_bfree+blocks,f_bavail=old.f_bavail+blocks)

def world(*,init=(INIT,)):
    """The baseline before any operation of this family: no supervisor or reader path, no unit, the production image.
    Data volume root 1000:1000 0755 on its own device, as the HOSTFACTS_01 receipt read it."""
    tree=Tree()
    for path in ('/etc/systemd/system','/var/lib/docker','/usr/local/bin','/usr/sbin','/usr/libexec','/usr/lib/systemd/system',
                 '/run/systemd/system','/run/systemd/generator','/proc/sys/kernel/random','/mnt'):tree.add(path)
    tree.add('/etc/systemd/system/timers.target.wants');tree.add('/etc/systemd/system/multi-user.target.wants')
    tree.add('/etc/systemd/system/multi-user.target.wants/docker.service',kind='symlink',mode=0o777)
    tree.add('/usr/lib/systemd/system/timers.target.wants');tree.add('/usr/lib/systemd/system/docker.service',kind='file',mode=0o644,content=b'[Unit]\n')
    tree.add('/proc/sys/kernel/random/boot_id',kind='file',mode=0o444,content=BOOT)
    tree.add('/proc/sys/kernel/core_pattern',kind='file',mode=0o644,content=b'|/usr/share/apport/apport %p\n')
    for name in ('docker','systemctl'):tree.add('/usr/bin/'+name,kind='file',content=b'ELF')
    for path in init:tree.add(path,kind='file',content=b'ELF')
    if tree.get(INIT) is not None:tree.get(INIT).ino=4004
    tree.add('/mnt').ino=4002;tree.get('/etc/systemd/system').ino=4001;tree.get('/var/lib').ino=4003
    tree.add(DATA,uid=1000,gid=1000,dev=DATA_DEVICE,ino=4005)
    tree.add(DATA+'/lost+found',mode=0o700,dev=DATA_DEVICE);tree.add(DATA+'/provider=synthetic',dev=DATA_DEVICE)
    info={'SecurityOptions':['name=apparmor','name=seccomp,profile=builtin','name=cgroupns'],'Driver':'overlayfs',
          'DriverStatus':[['driver-type','io.containerd.snapshotter.v1']],'DockerRootDir':'/var/lib/docker','InitBinary':'docker-init',
          'ServerVersion':'29.5.3','HTTPProxy':'http://never-emit-proxy-canary:3128','Name':'never-emit-hostname-canary'}
    images=[{'Id':BACKEND,'RepoTags':['c3po/backend:production'],'Created':'x','Architecture':'arm64','Os':'linux','Size':1,
             'Config':{'Labels':{'org.opencontainers.image.revision':REVISION},'Env':['IMAGE_ENV=never-emit-image-canary']}},
            {'Id':OTHER,'RepoTags':['c3po/backend:rollback'],'Created':'x','Architecture':'arm64','Os':'linux','Size':1,
             'Config':{'Labels':{'org.opencontainers.image.revision':REVISION},'Env':[]}}]
    docker=FakeDocker(images,info,{'Client':{'Version':'29.5.3'},'Server':{'Version':'29.5.3'}})
    vfs={DATA_DEVICE:types.SimpleNamespace(**DATA_VFS),ROOT_DEVICE:types.SimpleNamespace(**ROOT_VFS)}
    host=FakeHost(tree,docker,vfs)
    host.units['docker.service']={'Id':'docker.service','LoadState':'loaded','ActiveState':'active','SubState':'running','UnitFileState':'enabled'}
    return host

def rows(host,path):
    """The six-key rows of a path as a read-only receipt would print them (read straight from the emulated tree)."""
    out=[];node=host.tree.root;prefix=''
    def row(path,node):return {'path':path,'device':node.dev,'inode':node.ino,'uid':node.uid,'gid':node.gid,'mode':node.mode}
    out.append(row('/',node))
    for part in [part for part in path.strip('/').split('/') if part]:
        node=node.children[part];prefix+='/'+part;out.append(row(prefix,node))
    return out
