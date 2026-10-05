"""Child interpreter for the native tests: runs one demonstration operation with the module's own, unmodified Native
against a private temporary tree, under an audit hook that records every file-changing and process-starting event of
the interpreter, and under the os-level record of tests/oslevel.py (arguments of every system call).
Usage: native_child.py <selftest_read|selftest_write> <tree root> <fields json file>. Prints one JSON line. Never
touches the real host: the only absolute path ever opened is the temporary tree, substituted for '/'."""
import json
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
import demos
import family as f
import oslevel

WATCHED=('os.chmod','os.chown','os.rename','os.link','os.mkdir','os.remove','os.rmdir','os.truncate','os.utime','os.symlink',
         'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','os.spawn','socket.connect','socket.bind',
         'shutil.rmtree','shutil.move','shutil.copyfile')
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

def main():
    name,root,fields_path=sys.argv[1:4];k=f.load(demos.DIRECTORIES[name]);events=[];armed=[False]
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
        with oslevel.Substitute(root) as record:receipt=docs.run(None)          # host=None: the source builds its own Native()
    finally:armed[0]=False;os.umask(old)
    sys.stdout.write(json.dumps({'receipt':receipt,'events':events,'calls':record.plain(),'noatime_is_the_kernel_flag':record.native_noatime},sort_keys=True)+'\n')

if __name__=='__main__':main()
