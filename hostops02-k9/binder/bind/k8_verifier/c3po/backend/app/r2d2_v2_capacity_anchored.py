"""No-follow directory capabilities with fixed ancestor identities."""
import os,stat,json
from pathlib import Path
from .r2d2_v2_store import ShadowIntegrityError,digest


def need(ok,code):
    if not ok:raise ShadowIntegrityError(code)


class AnchoredRoot:
    def __init__(self,path,*,expected_identity=None):
        self.nodes=[];self.closed=False
        absolute=Path(os.path.abspath(path))
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);self.fds=[fd]
        try:
            for part in absolute.parts[1:]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                self.fds.append(child);info=os.fstat(child)
                self.nodes.append((fd,part,child,(info.st_dev,info.st_ino)));fd=child
            self.fd=fd;info=os.fstat(fd)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and not info.st_mode&0o077,'ROOT_NOT_PRIVATE')
            self.identity=digest([[part,*identity] for _,part,_,identity in self.nodes])
            if expected_identity is not None:need(self.identity==expected_identity,'ROOT_IDENTITY_CHANGED')
        except BaseException:
            self.close();raise

    def verify(self):
        need(not self.closed,'ROOT_CLOSED')
        for parent,name,fd,identity in self.nodes:
            info=os.stat(name,dir_fd=parent,follow_symlinks=False)
            need(stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino)==identity,'ROOT_IDENTITY_CHANGED')
            actual=os.fstat(fd);need((actual.st_dev,actual.st_ino)==identity,'ROOT_FD_CHANGED')
        leaf=os.fstat(self.fd);need(leaf.st_uid==os.geteuid() and not leaf.st_mode&0o077,'ROOT_NOT_PRIVATE')

    def read(self,name,limit=4*1024*1024):
        need(type(name) is str and name not in ('.','..') and '/' not in name,'ROOT_FILENAME')
        self.verify();fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fd)
        try:
            before=os.fstat(fd);need(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid()
                and before.st_nlink==1 and not before.st_mode&0o077 and before.st_size<=limit,'ROOT_FILE_POLICY')
            body=b''
            while len(body)<=limit:
                chunk=os.read(fd,min(65536,limit-len(body)+1))
                if not chunk:break
                body+=chunk
            after=os.fstat(fd);need(len(body)<=limit and (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),'ROOT_FILE_CHANGED')
            self.verify();return body
        finally:os.close(fd)

    def json(self,name):
        def pairs(items):
            result={}
            for key,value in items:need(key not in result,'JSON_DUPLICATE_KEY');result[key]=value
            return result
        return json.loads(self.read(name),object_pairs_hook=pairs)

    def reserve(self,name,body):
        self.verify();need('/' not in name and name not in ('.','..'),'ROOT_FILENAME')
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fd)
        try:
            offset=0
            while offset<len(body):offset+=os.write(fd,body[offset:])
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(self.fd);self.verify()

    def close(self):
        if getattr(self,'closed',False):return
        self.closed=True
        for fd in reversed(getattr(self,'fds',[])):os.close(fd)
        self.fds=[]

    def __del__(self):self.close()
