"""Child interpreter for the native test of K6a: one run with the source's own Native (the docker CLI alone answered
by the emulated engine, tests/native_engine.py) against a private temporary tree, under an audit hook that records
every file-changing and process-starting event of the interpreter, and under the os-level record of the core's
tests/oslevel.py. Usage: native_child.py <tree root> <fields json file>. Prints one JSON line."""
import json
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.environ.get('HOSTOPS02_TEST_CORE_TESTS') or os.path.join(HERE,'..','..','core','tests'));sys.path.insert(0,HERE)
import family as f
import k6a
import native_engine
import oslevel

WATCHED=('os.chmod','os.chown','os.rename','os.link','os.mkdir','os.remove','os.rmdir','os.truncate','os.utime','os.symlink',
         'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','os.spawn','socket.connect','socket.bind',
         'shutil.rmtree','shutil.move','shutil.copyfile')
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

def main():
    root,fields_path=sys.argv[1:3];k=k6a.load();events=[];armed=[False]
    def hook(event,arguments):
        if not armed[0]:return
        if event in WATCHED:events.append([event]+[str(item) for item in arguments[:2]])
        elif event=='open' and type(arguments[2]) is int and arguments[2]&WRITE:events.append(['open-for-writing',str(arguments[0]),arguments[2]])
    sys.addaudithook(hook)
    with open(fields_path,'rb') as stream:fields=json.loads(stream.read())
    docs=f.Docs(k,fields);host,emulated=native_engine.engine(k,root)
    old=os.umask(0o027);armed[0]=True
    try:
        with oslevel.Substitute(root) as record:receipt=docs.run(host,**native_engine.real_clocks(docs))
    finally:armed[0]=False;os.umask(old)
    sys.stdout.write(json.dumps({'receipt':receipt,'events':events,'calls':record.plain(),'noatime_is_the_kernel_flag':record.native_noatime,
                                 'commands':[entry['argv'][1:3] for entry in emulated.commands]},sort_keys=True)+'\n')

if __name__=='__main__':main()
