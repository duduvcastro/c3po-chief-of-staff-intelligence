"""Child interpreter for the native test of K9W: one run with the source's own Native (the docker CLI alone answered by
the emulated engine, tests/native_engine.py) against a private temporary tree, under an audit hook that records every
file-changing and process-starting event of the interpreter, and under the os-level record of the core's
tests/oslevel.py. Usage: native_child.py <tree root> <operation>. Prints one JSON line."""
import json
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.environ.get('HOSTOPS02_TEST_CORE_TESTS') or os.path.join(HERE,'..','..','core','tests'));sys.path.insert(0,HERE)
import family as f
import k9w
import native_engine
import oslevel

WATCHED=('os.chmod','os.chown','os.rename','os.link','os.mkdir','os.remove','os.rmdir','os.truncate','os.utime','os.symlink',
         'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','os.spawn','socket.connect','socket.bind',
         'shutil.rmtree','shutil.move','shutil.copyfile')
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

def main():
    root,operation=sys.argv[1:3];k=f.load(k9w.DIRECTORY);events=[];armed=[False]
    emulated=k9w.prepared(k,operation);native_engine.build(root,emulated)
    docs,_=k9w.case(operation)
    for name in k9w.CHAINS:docs.plan['parent_rows'][name]['rows']=oslevel.rows(root,k9w.PLACEMENT[name])
    docs.chain();host=native_engine.engine(k,emulated)
    def hook(event,arguments):
        if not armed[0]:return
        if event in WATCHED:events.append([event]+[str(item) for item in arguments[:2]])
        elif event=='open' and type(arguments[2]) is int and arguments[2]&WRITE:events.append(['open-for-writing',str(arguments[0]),arguments[2]])
    sys.addaudithook(hook)
    old=os.umask(0o022);armed[0]=True
    try:
        with oslevel.Substitute(root) as record:receipt=docs.run(host)
    finally:armed[0]=False;os.umask(old)
    sys.stdout.write(json.dumps({'receipt':receipt,'events':events,'calls':record.plain(),'noatime_is_the_kernel_flag':record.native_noatime,
                                 'commands':[entry['argv'][1:2] for entry in emulated.commands]},sort_keys=True)+'\n')

if __name__=='__main__':main()
