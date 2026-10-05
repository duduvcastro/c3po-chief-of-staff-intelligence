"""Child interpreter for the native tests of K3: one run of the source with its own Native (only the docker CLI answered
by the emulated engine, tests/nativehost.py) against a private temporary tree substituted for "/" (the core's
tests/oslevel.py), under an audit hook that records every file-changing, process-starting, network and environment
event of the interpreter while the run is in progress. Usage: native_child.py <tree root> <fields json file> <value
file>. The value file holds the synthetic canary value of the worker's entry (never a real one). Prints one JSON line
(the receipt, the audit events, the system calls with their arguments, the sizes asked of every read, and on Linux the
dumpable attribute of this process as the kernel holds it before and after the run); never the content of a file.
Never touches the real host."""
import ctypes
import json
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
import conftest      # noqa: F401  (puts the tests of the core on sys.path)
import family as f
import k3env
import nativehost
import oslevel

WATCHED=('os.chmod','os.chown','os.rename','os.link','os.mkdir','os.remove','os.rmdir','os.truncate','os.utime','os.symlink','os.putenv','os.unsetenv',
         'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','os.spawn','socket.connect','socket.bind','socket.getaddrinfo',
         'shutil.rmtree','shutil.move','shutil.copyfile')
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

def main():
    root,fields_path,value_path=sys.argv[1:4];events=[];armed=[False]
    def hook(event,arguments):
        if not armed[0]:return
        if event in WATCHED:events.append([event]+[str(item) for item in arguments[:2]])
        elif event=='open' and type(arguments[2]) is int and arguments[2]&WRITE:events.append(['open-for-writing',str(arguments[0]),arguments[2]])
        elif event=='open':events.append(['open',str(arguments[0])])
    sys.addaudithook(hook)
    with open(fields_path,'rb') as stream:fields=json.loads(stream.read())
    with open(value_path,'rb') as stream:value=stream.read().decode('ascii')
    docs=f.Docs(k3env.K(),fields,now=k3env.NOW);linux=sys.platform.startswith('linux');host=nativehost.native(value)
    def dumpable():return ctypes.CDLL(None,use_errno=True).prctl(3,0,0,0,0) if linux else None      # PR_GET_DUMPABLE, outside the substitution
    before=dumpable()
    old=os.umask(0o022);armed[0]=True
    try:
        with oslevel.Substitute(root,real_prctl=linux) as record:receipt=docs.run(host)
    finally:armed[0]=False;os.umask(old)
    sys.stdout.write(json.dumps({'receipt':receipt,'events':events,'calls':record.plain(),'docker':host.argv,'reads':host.reads,
                                'noatime_is_the_kernel_flag':record.native_noatime,'dumpable_before':before,'dumpable_after':dumpable()},sort_keys=True)+'\n')

if __name__=='__main__':main()
