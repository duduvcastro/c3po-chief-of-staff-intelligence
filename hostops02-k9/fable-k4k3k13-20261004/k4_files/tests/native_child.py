"""Child interpreter for the K4 files family's native tests: runs the source with its own, unmodified Native against a
private temporary tree, under an audit hook that records every file-changing and process-starting event of the
interpreter and under the os-level record of the core's tests/oslevel.py (arguments of every system call).

usage: native_child.py <tree root> <fields json file> [<death point>]
Prints one JSON line. With a death point the process ends there by os._exit(137), as a killed process does: nothing is
printed, no receipt exists, and what the tree holds is what a later read would find. Death points: after_link_<n> (after
the n-th link, n = 1 ... 8), in_write (half of the first file's bytes written). (K4-E0's child with its fixtures import
changed and its death points reduced to what these modes do.) Never touches the real host: the only absolute path ever
opened is the temporary tree, substituted for '/'."""
import json
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..','..','core','tests'));sys.path.insert(0,HERE)
import family as f
import k4f
import oslevel

WATCHED=('os.chmod','os.chown','os.rename','os.link','os.mkdir','os.remove','os.rmdir','os.truncate','os.utime','os.symlink',
         'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','os.spawn','socket.connect','socket.bind',
         'shutil.rmtree','shutil.move','shutil.copyfile')
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

def dying(native,point):
    linked=[0]
    class Dying(native):
        def write(self,fd,data):
            if point=='in_write':
                native.write(self,fd,data[:len(data)//2]);os._exit(137)
            return native.write(self,fd,data)
        def link(self,source,target,dir_fd):
            native.link(self,source,target,dir_fd);linked[0]+=1
            if point=='after_link_%d'%linked[0]:os._exit(137)
    return Dying()

def main():
    root,fields_path=sys.argv[1:3];point=sys.argv[3] if len(sys.argv)>3 else None;k=k4f.K();events=[];armed=[False]
    def hook(event,arguments):
        if not armed[0]:return
        if event in WATCHED:events.append([event]+[str(item) for item in arguments[:2]])
        elif event=='open' and type(arguments[2]) is int and arguments[2]&WRITE:events.append(['open-for-writing',str(arguments[0]),arguments[2]])
        elif event=='open':events.append(['open',str(arguments[0])])
    sys.addaudithook(hook)
    with open(fields_path,'rb') as stream:fields=json.loads(stream.read())
    docs=f.Docs(k,fields)
    old=os.umask(0o027);armed[0]=True
    try:
        with oslevel.Substitute(root) as record:receipt=docs.run(dying(k.m.Native,point) if point else None)
    finally:armed[0]=False;os.umask(old)
    sys.stdout.write(json.dumps({'receipt':receipt,'events':events,'calls':record.plain(),'noatime_is_the_kernel_flag':record.native_noatime,'go16':docs.go16()},sort_keys=True)+'\n')

if __name__=='__main__':main()
