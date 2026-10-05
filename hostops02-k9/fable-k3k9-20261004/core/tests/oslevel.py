"""The sources' own Native classes, unmodified, on a private temporary tree that stands in for '/'.

Nothing of Native is overridden: a test double that replaced open, fstat or lstat would leave the shipped lines
unexecuted. The substitution is made one level down, on the os module, and only while one candidate run is in
progress:
  - the single absolute open the sources make ('/') is redirected to the temporary tree;
  - the test user is reported as root: effective ids 0, and uid/gid 0 for what that user owns (as real root on Linux
    nothing is mapped);
  - where the platform has no O_NOATIME (macOS) a marker bit stands for it, is recorded as requested and is stripped
    before the real call; where it exists (Linux) the real flag reaches the kernel.
Every call that reads or changes the tree is recorded with the arguments the real system call received: the flags of
every open, follow_symlinks of every stat and link, the descriptor of every fsync, the mode of every mkdir, the
operation of every flock.
No host, no docker, no ssh, no credential: the only absolute path opened is the temporary tree.
The file of HOSTOPS01 with two additions: fcntl.flock is recorded (and still reaches the kernel); and ctypes.CDLL, which
the core's dumps_disabled() calls to reach prctl(2) (the token family's revision of the core), gives a C library that
records every prctl with its arguments, in order with the system calls above, and emulates the dumpable attribute of the
process (1 until it is set to 0), so that the process of the test suite is never made non-dumpable; with real_prctl
(a child process on Linux only) each prctl also reaches the kernel and the kernel's answer is the one returned."""
import ctypes
import fcntl
import os
import stat

MARKER=1<<28
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND
PATCHED=('open','close','stat','lstat','fstat','mkdir','fsync','link','unlink','remove','readlink','scandir','umask','geteuid','getegid')
PR_GET_DUMPABLE,PR_SET_DUMPABLE=3,4                 # <linux/prctl.h>: what the emulated library answers to


class Library:
    """The C library a source loads while one run is in progress: its prctl only, recorded. Emulated: PR_SET_DUMPABLE
    with 0 or 1 sets the attribute and returns 0, PR_GET_DUMPABLE answers it, anything else returns -1 (EINVAL, as the
    kernel). real: the kernel's prctl through the real C library of the interpreter, its answer returned."""
    def __init__(self,record,real):self.record,self.real,self.dumpable=record,real,1
    def prctl(self,option,*arguments):
        entry={'call':'prctl','option':option,'arguments':list(arguments)};self.record.calls.append(entry)
        if self.real:result=self.record.real_cdll(None,use_errno=True).prctl(option,*arguments)
        elif option==PR_SET_DUMPABLE and arguments[:1] in ((0,),(1,)):self.dumpable=arguments[0];result=0
        elif option==PR_GET_DUMPABLE:result=self.dumpable
        else:result=-1
        entry['result']=result;return result


class Info:
    """An os.stat_result with the test user reported as root."""
    def __init__(self,info,uids,gids):self._info,self._uids,self._gids=info,uids,gids
    def __getattr__(self,name):
        value=getattr(self._info,name)
        if name=='st_uid' and value in self._uids:return 0
        if name=='st_gid' and value in self._gids:return 0
        return value


class Substitute:
    """with Substitute(root) as record: <one candidate run with the module's own Native()>"""
    def __init__(self,root,real_prctl=False):
        self.root=str(root);self.calls=[];self.paths={};self.real={name:getattr(os,name) for name in PATCHED};self.real_flock=fcntl.flock
        self.real_cdll=ctypes.CDLL;self.real_prctl=real_prctl;self.libraries=[]
        self.native_noatime=hasattr(os,'O_NOATIME');self.noatime=os.O_NOATIME if self.native_noatime else MARKER
        self.uids={os.geteuid()};self.gids={os.getegid(),os.stat(self.root).st_gid}
    def info(self,info):return Info(info,self.uids,self.gids)
    def name(self,path,dir_fd):
        if dir_fd is None:return '/' if path=='/' else 'ABSOLUTE:'+str(path)
        return self.paths.get(dir_fd,'?').rstrip('/')+'/'+str(path)
    def call(self,entry,action):
        self.calls.append(entry)
        try:return action()
        except OSError as error:
            entry['errno']=error.errno;raise
    def __enter__(self):
        real=self.real;S=self;strip=0 if self.native_noatime else MARKER
        def open_(path,flags,mode=0o777,*,dir_fd=None):
            entry={'call':'open','path':S.name(path,dir_fd),'flags':flags,'noatime':bool(flags&S.noatime),'by_dir_fd':dir_fd is not None,
                   'mode':mode if flags&os.O_CREAT else None}
            target=S.root if dir_fd is None and path=='/' else path
            fd=S.call(entry,lambda:real['open'](target,flags&~strip,mode,dir_fd=dir_fd))
            S.paths[fd]=entry['path'];entry['fd']=fd;return fd
        def close_(fd):
            S.paths.pop(fd,None);return real['close'](fd)
        def stat_(path,*,dir_fd=None,follow_symlinks=True):
            entry={'call':'stat','path':S.name(path,dir_fd),'follow_symlinks':follow_symlinks,'by_dir_fd':dir_fd is not None}
            return S.info(S.call(entry,lambda:real['stat'](path,dir_fd=dir_fd,follow_symlinks=follow_symlinks)))
        def lstat_(path,*,dir_fd=None):return stat_(path,dir_fd=dir_fd,follow_symlinks=False)
        def fstat_(fd):
            entry={'call':'fstat','path':S.paths.get(fd,'?'),'fd':fd}
            return S.info(S.call(entry,lambda:real['fstat'](fd)))
        def mkdir_(path,mode=0o777,*,dir_fd=None):
            entry={'call':'mkdir','path':S.name(path,dir_fd),'mode':mode,'by_dir_fd':dir_fd is not None}
            return S.call(entry,lambda:real['mkdir'](path,mode,dir_fd=dir_fd))
        def fsync_(fd):
            entry={'call':'fsync','path':S.paths.get(fd,'?'),'fd':fd}
            return S.call(entry,lambda:real['fsync'](fd))
        def link_(src,dst,*,src_dir_fd=None,dst_dir_fd=None,follow_symlinks=True):
            entry={'call':'link','source':S.name(src,src_dir_fd),'path':S.name(dst,dst_dir_fd),'follow_symlinks':follow_symlinks,
                   'by_dir_fd':src_dir_fd is not None and dst_dir_fd is not None,'same_directory':src_dir_fd==dst_dir_fd}
            return S.call(entry,lambda:real['link'](src,dst,src_dir_fd=src_dir_fd,dst_dir_fd=dst_dir_fd,follow_symlinks=follow_symlinks))
        def unlink_(path,*,dir_fd=None):
            entry={'call':'unlink','path':S.name(path,dir_fd),'by_dir_fd':dir_fd is not None}
            return S.call(entry,lambda:real['unlink'](path,dir_fd=dir_fd))
        def readlink_(path,*,dir_fd=None):
            entry={'call':'readlink','path':S.name(path,dir_fd),'by_dir_fd':dir_fd is not None}
            return S.call(entry,lambda:real['readlink'](path,dir_fd=dir_fd))
        def scandir_(target='.'):
            S.calls.append({'call':'scandir','path':S.paths.get(target,'?') if type(target) is int else 'ABSOLUTE:'+str(target),'by_fd':type(target) is int})
            return real['scandir'](target)
        def umask_(mask):
            S.calls.append({'call':'umask','mask':mask});return real['umask'](mask)
        patched=dict(open=open_,close=close_,stat=stat_,lstat=lstat_,fstat=fstat_,mkdir=mkdir_,fsync=fsync_,link=link_,unlink=unlink_,
                     remove=unlink_,readlink=readlink_,scandir=scandir_,umask=umask_,geteuid=lambda:0,getegid=lambda:0)
        def flock_(fd,operation):
            entry={'call':'flock','path':S.paths.get(fd,'?'),'fd':fd,'operation':operation}
            return S.call(entry,lambda:S.real_flock(fd,operation))
        def cdll_(name,*arguments,**options):
            S.calls.append({'call':'dlopen','name':name,'arguments':list(arguments),'options':dict(options)})
            library=Library(S,S.real_prctl);S.libraries.append(library);return library
        assert set(patched)==set(PATCHED)
        for name,function in patched.items():setattr(os,name,function)
        fcntl.flock=flock_;ctypes.CDLL=cdll_
        if not self.native_noatime:os.O_NOATIME=MARKER
        return self
    def __exit__(self,*exception):
        for name,function in self.real.items():setattr(os,name,function)
        fcntl.flock=self.real_flock;ctypes.CDLL=self.real_cdll
        if not self.native_noatime:del os.O_NOATIME
        return False
    # -- views of the record
    def of(self,*names):return [entry for entry in self.calls if entry['call'] in names]
    def done(self,*names):return [entry for entry in self.of(*names) if 'errno' not in entry]
    def plain(self):
        """The record without descriptor numbers, for a JSON line."""
        return [{key:value for key,value in entry.items() if key!='fd'} for entry in self.calls]


def rows(root,path):
    """Six-key rows read from the real tree, the test user reported as root: exactly what the sources will read."""
    mapper=Substitute(root);out=[];current=str(root);prefix=''
    for part in ['']+[part for part in path.strip('/').split('/') if part]:
        if part:current=os.path.join(current,part);prefix+='/'+part
        info=mapper.info(os.lstat(current))
        out.append({'path':prefix or '/','device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)})
    return out
