"""Exclusive local storage. No network, transport, authority or signature."""
import hashlib,json,os,pathlib,stat,types,sys
class Refused(ValueError):pass
def need(ok,code):
 if not ok:raise Refused(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def strict(raw):
 def pairs(items):
  out={}
  for k,v in items:need(k not in out,'FILES_DUPLICATE');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False,'FILES_CONSTANT'))
def path(value):
 p=pathlib.Path(value);need(p.is_absolute() and '..' not in p.parts,'FILES_PATH')
 for q in (p,*p.parents):need(not q.is_symlink(),'FILES_LINK')
 return p
def read(value,expected=None,private=True,limit=32*1024*1024,empty=False):
 p=path(value);fd=os.open(str(p),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_nlink==1 and not a.st_mode&0o022 and (empty or a.st_size>0) and a.st_size<=limit,'FILES_REGULAR')
  need(not private or a.st_uid==os.getuid() and stat.S_IMODE(a.st_mode)==0o600,'FILES_PRIVATE');raw=f.read(limit+1);b=os.fstat(f.fileno())
 def ident(s):return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns
 need(ident(a)==ident(b)==ident(p.lstat()) and len(raw)==a.st_size,'FILES_CHANGED')
 need(expected is None or sha(raw)==expected,'FILES_PIN');return raw
def directory(value,new=False):
 p=path(value)
 if new:p.mkdir(mode=0o700)
 s=p.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'FILES_DIRECTORY');return p
def put(value,raw):
 p=path(value);directory(p.parent);need(type(raw) is bytes,'FILES_BYTES');fd=os.open(str(p),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 need(read(p,empty=not raw)==raw,'FILES_READBACK');return sha(raw)
def load(value,pin,name):
 p=path(value);raw=read(p,pin,False);need(name not in sys.modules,'FILES_MODULE_LOADED');m=types.ModuleType(name);m.__file__=str(p);sys.modules[name]=m;exec(compile(raw,str(p),'exec'),m.__dict__);return m
