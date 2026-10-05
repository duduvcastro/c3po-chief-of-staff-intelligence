"""Child interpreter for the native tests of K9R: runs the source with its own, unmodified Native against a private
temporary tree, under an audit hook that records every file-changing and process-starting event of the interpreter,
and under the os-level record of the core's tests/oslevel.py (the arguments of every system call).
Usage: native_child_k9r.py <tree root> <fields json file> <now>. Prints one JSON line. Never touches the real host: the
only absolute path ever opened is the temporary tree, substituted for '/'."""
from datetime import datetime
import json
import os
import sys

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(HERE,'..','..','core','tests'));sys.path.insert(0,HERE)
import family as f
import k9r
import oslevel

WATCHED=('os.chmod','os.chown','os.rename','os.link','os.mkdir','os.remove','os.rmdir','os.truncate','os.utime','os.symlink',
         'subprocess.Popen','os.system','os.exec','os.fork','os.forkpty','os.posix_spawn','os.spawn','socket.connect','socket.bind',
         'shutil.rmtree','shutil.move','shutil.copyfile')
WRITE=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND

def main():
    root,fields_path,now=sys.argv[1:4];k=f.load(k9r.DIRECTORY);events=[];armed=[False]
    def hook(event,arguments):
        if not armed[0]:return
        if event in WATCHED:events.append([event]+[str(item) for item in arguments[:2]])
        elif event=='open' and type(arguments[2]) is int and arguments[2]&WRITE:events.append(['open-for-writing',str(arguments[0]),arguments[2]])
        elif event=='open':events.append(['open',str(arguments[0])])
    sys.addaudithook(hook)
    with open(fields_path,'rb') as stream:fields=json.loads(stream.read())
    docs=f.Docs(k,fields,now=datetime.fromisoformat(now));armed[0]=True
    try:
        with oslevel.Substitute(root) as record:receipt=docs.run(None)          # host=None: the source builds its own Native()
    finally:armed[0]=False
    sys.stdout.write(json.dumps({'receipt':receipt,'events':events,'calls':record.plain()},sort_keys=True)+'\n')

if __name__=='__main__':main()
