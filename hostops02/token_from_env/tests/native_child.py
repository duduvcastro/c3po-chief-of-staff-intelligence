"""Child interpreter for the native tests of the token placement: one run of the source with its own, unmodified Native
against a private temporary tree substituted for "/" (the core's tests/oslevel.py), under an audit hook that records
every file-changing, process-starting, network and environment event of the interpreter while the run is in progress.
Usage: native_child.py <tree root> <fields json file>. Prints one JSON line (the receipt, the audit events, the system
calls with their arguments); never the content of a file. Never touches the real host."""
import json
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
import conftest      # noqa: F401  (puts the tests of the frozen core on sys.path)
import family as f
import oslevel
import tok

WATCHED=('os.chmod','os.chown','os.rename','os.link','os.mkdir','os.remove','os.rmdir','os.truncate','os.utime','os.symlink','os.putenv','os.unsetenv',
         'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','os.spawn','socket.connect','socket.bind','socket.getaddrinfo',
         'shutil.rmtree','shutil.move','shutil.copyfile')
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

def main():
    root,fields_path=sys.argv[1:3];events=[];armed=[False]
    def hook(event,arguments):
        if not armed[0]:return
        if event in WATCHED:events.append([event]+[str(item) for item in arguments[:2]])
        elif event=='open' and type(arguments[2]) is int and arguments[2]&WRITE:events.append(['open-for-writing',str(arguments[0]),arguments[2]])
        elif event=='open':events.append(['open',str(arguments[0])])
    sys.addaudithook(hook)
    with open(fields_path,'rb') as stream:fields=json.loads(stream.read())
    docs=f.Docs(tok.K(),fields,now=tok.NOW)
    old=os.umask(0o022);armed[0]=True
    try:
        with oslevel.Substitute(root) as record:receipt=docs.run(None)          # host=None: the source builds its own Native()
    finally:armed[0]=False;os.umask(old)
    sys.stdout.write(json.dumps({'receipt':receipt,'events':events,'calls':record.plain(),'noatime_is_the_kernel_flag':record.native_noatime},sort_keys=True)+'\n')

if __name__=='__main__':main()
