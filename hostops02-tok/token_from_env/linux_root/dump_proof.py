"""What the kernel does with a crash of a process that holds a secret, before and after the source's own protection, on a
throwaway Linux runner as real root (revision 3, CONTRACT D9). The production host forwards core dumps to a crash
collector through a pipe (its precheck receipt: kernel.core_pattern is a pipe), and RLIMIT_CORE does not stop a pipe.

For each kernel.core_pattern this script sets in turn,
  pipe   "|/usr/bin/python3 -I -B <directory>/collector.py %P %s": a small collector that reads everything the kernel
         sends on its standard input and writes a marker with the count of the bytes it received and whether a fake
         canary was among them;
  file   "<directory>/cores/core.%P": an absolute file path;
and for SIGQUIT and SIGSEGV, a child interpreter (/usr/bin/python3 -I -B, RLIMIT_CORE unlimited, a FAKE canary held in
its memory as the bytes of .env would be) kills itself with the signal:
  dumpable   as it starts (the kernel holds 1): the collector receives the dump, with the canary in it (the file holds
             it), and its parent sees the signal and the core-dumped flag;
  protected  the same child after the core's protection of the SOURCE ITSELF (build/token_from_env.py loaded as the
             launcher loads it, then its own Native().not_dumpable(): prctl PR_SET_DUMPABLE 0, read back 0): its parent
             sees the same signal and no core-dumped flag, and nothing reaches the collector or the file (looked for 5 s
             after the child is reaped).
Each child writes, before its signal, the attribute the kernel holds for it and whether RLIMIT_CORE is unlimited.
The original kernel.core_pattern (the runner's, not the production host's) is read first, put back at the end whatever
happened, and both are printed. The directory of the collector, the markers and the core files is a private temporary
one, removed at the end. No network, no docker, no token of any provider: the canary is fake.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner only (linux_root/run.sh calls it, stage 3a): it refuses anywhere else
(Linux, effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted are all required). NOT RUN by
its author: no Linux and no root were available offline.

usage: sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/dump_proof.py
exit 0 only when every case ran AND every expectation is met; 2 when a case did not run; 3 when an expectation is not
met; 1 for a refusal. Prints one JSON object.
"""
import json
import os
import shutil
import signal
import sys
import tempfile
import time

HERE=os.path.dirname(os.path.abspath(__file__))
SOURCE=os.path.join(os.path.dirname(HERE),'build','token_from_env.py')
SCHEMA='HOSTOPS02_TOKEN_FROM_ENV_LINUX_ROOT_DUMP_PROOF_V1'
PATTERN='/proc/sys/kernel/core_pattern'
PYTHON='/usr/bin/python3'
SIGNALS=('SIGQUIT','SIGSEGV')
MODES=('pipe','file')
WAIT_FOR_A_DUMP=30.0            # seconds a dump of a dumpable child may take to reach the collector
WAIT_FOR_NOTHING=5.0            # seconds looked for a dump of a protected child after it was reaped
CANARY_PARTS=('FAKE-CORE-DUMP-CANARY-','0123456789',3)          # built at run time: the whole canary is in no argv and in no file

COLLECTOR='''import json,os,sys
pid,number=sys.argv[1],sys.argv[2];directory=os.path.dirname(os.path.abspath(__file__))
canary=(%r+%r*%d).encode()
total=0;found=False;tail=b''
while True:
    block=sys.stdin.buffer.read(1<<20)
    if not block:break
    total+=len(block);found=found or canary in tail+block;tail=block[-len(canary):]
path=os.path.join(directory,'marker.%%s.json'%%pid)
with open(path+'.partial','w') as handle:handle.write(json.dumps({'pid':int(pid),'signal':int(number),'bytes':total,'canary_found':found}))
os.rename(path+'.partial',path)
'''%CANARY_PARTS

CHILD='''import ctypes,json,os,resource,signal,sys,types
protected,name,report,source=sys.argv[1]=='protected',sys.argv[2],sys.argv[3],sys.argv[4]
resource.setrlimit(resource.RLIMIT_CORE,(resource.RLIM_INFINITY,resource.RLIM_INFINITY))
held=bytearray((%r+%r*%d).encode())*64
if protected:
    module=types.ModuleType('_dump_proof_token_source');sys.modules[module.__name__]=module
    with open(source,'rb') as handle:exec(compile(handle.read(),'<token_from_env>','exec'),module.__dict__)
    module.Native().not_dumpable()
state={'pid':os.getpid(),'dumpable':ctypes.CDLL(None,use_errno=True).prctl(3,0,0,0,0),
       'core_limit_unlimited':resource.getrlimit(resource.RLIMIT_CORE)==(resource.RLIM_INFINITY,resource.RLIM_INFINITY)}
with open(report,'w') as handle:handle.write(json.dumps(state))
os.kill(os.getpid(),getattr(signal,name))
'''%CANARY_PARTS

def canary():return (CANARY_PARTS[0]+CANARY_PARTS[1]*CANARY_PARTS[2]).encode()

def read_pattern():
    with open(PATTERN,'rb') as handle:return handle.read()
def write_pattern(raw):
    with open(PATTERN,'wb') as handle:handle.write(raw)

def holds_canary(path):
    """Whether a core file holds the canary, read in blocks (a core of an interpreter is some tens of megabytes)."""
    found=False;tail=b'';wanted=canary()
    with open(path,'rb') as handle:
        while not found:
            block=handle.read(1<<20)
            if not block:break
            found=wanted in tail+block;tail=block[-len(wanted):]
    return found

def one(directory,mode,protected,name):
    """One child: started, killed by its own signal, reaped; then what reached the collector or the file."""
    report=os.path.join(directory,'child.%s.%s.%s.json'%(mode,'protected' if protected else 'dumpable',name))
    pid=os.fork()
    if pid==0:
        try:os.execv(PYTHON,[PYTHON,'-I','-B','-c',CHILD,'protected' if protected else 'dumpable',name,report,SOURCE])
        finally:os._exit(127)
    _,status=os.waitpid(pid,0)
    row={'signalled':os.WIFSIGNALED(status),'signal':os.WTERMSIG(status) if os.WIFSIGNALED(status) else None,
         'expected_signal':int(getattr(signal,name)),'core_dumped_flag':bool(os.WIFSIGNALED(status) and os.WCOREDUMP(status))}
    try:
        with open(report,'rb') as handle:child=json.loads(handle.read())
    except (OSError,ValueError):child={}
    row.update(child_pid_matches=child.get('pid')==pid,dumpable_before_the_signal=child.get('dumpable'),core_limit_unlimited=child.get('core_limit_unlimited'))
    if mode=='pipe':
        marker=os.path.join(directory,'marker.%d.json'%pid);until=time.monotonic()+(WAIT_FOR_NOTHING if protected else WAIT_FOR_A_DUMP)
        while not os.path.exists(marker) and time.monotonic()<until:time.sleep(0.1)
        if protected and not os.path.exists(marker):time.sleep(0.5)
        if os.path.exists(marker):
            with open(marker,'rb') as handle:found=json.loads(handle.read())
            row.update(dump_received=True,dump_bytes=found['bytes'],canary_in_the_dump=found['canary_found'],collector_signal=found['signal'])
        else:row.update(dump_received=False,dump_bytes=None,canary_in_the_dump=None,collector_signal=None)
    else:
        core=os.path.join(directory,'cores','core.%d'%pid)
        if not protected:
            until=time.monotonic()+WAIT_FOR_A_DUMP
            while not os.path.exists(core) and time.monotonic()<until:time.sleep(0.1)
        else:time.sleep(WAIT_FOR_NOTHING)
        if os.path.exists(core):row.update(dump_received=True,dump_bytes=os.path.getsize(core),canary_in_the_dump=holds_canary(core),collector_signal=None)
        else:row.update(dump_received=False,dump_bytes=None,canary_in_the_dump=None,collector_signal=None)
    return row

def collect(directory):
    """Every case, the core_pattern of each mode set before its children and the original one put back by the caller."""
    os.chmod(directory,0o700);os.mkdir(os.path.join(directory,'cores'),0o700)
    with open(os.path.join(directory,'collector.py'),'w') as handle:handle.write(COLLECTOR)
    os.chmod(os.path.join(directory,'collector.py'),0o755)
    patterns={'pipe':'|%s -I -B %s %%P %%s'%(PYTHON,os.path.join(directory,'collector.py')),'file':os.path.join(directory,'cores','core.%P')}
    out={'patterns_set':{}}
    for mode in MODES:
        write_pattern(patterns[mode].encode());out['patterns_set'][mode]=read_pattern().rstrip(b'\n')==patterns[mode].encode()
        for protected in (False,True):
            for name in SIGNALS:
                label='%s %s %s'%(mode,'protected' if protected else 'dumpable',name)
                try:out[label]=dict(one(directory,mode,protected,name),ok=True)
                except Exception as error:out[label]={'ok':False,'error':type(error).__name__}
    return out

def expectations(out):
    def rows(mode,protected):return [out.get('%s %s %s'%(mode,'protected' if protected else 'dumpable',name)) or {} for name in SIGNALS]
    def dumped(row):
        return (row.get('signalled') is True and row.get('signal')==row.get('expected_signal') and row.get('core_dumped_flag') is True and row.get('child_pid_matches') is True
                and row.get('dumpable_before_the_signal')==1 and row.get('core_limit_unlimited') is True and row.get('dump_received') is True
                and type(row.get('dump_bytes')) is int and row['dump_bytes']>0 and row.get('canary_in_the_dump') is True)
    def nothing(row):
        return (row.get('signalled') is True and row.get('signal')==row.get('expected_signal') and row.get('core_dumped_flag') is False and row.get('child_pid_matches') is True
                and row.get('dumpable_before_the_signal')==0 and row.get('core_limit_unlimited') is True and row.get('dump_received') is False)
    return {
        'pipe: a dumpable child killed by SIGQUIT and by SIGSEGV is dumped to the collector, the canary of its memory in the bytes':
            (out.get('patterns_set') or {}).get('pipe') is True and all(dumped(row) and row.get('collector_signal')==row.get('expected_signal') for row in rows('pipe',False)),
        'pipe: the same child after the source\'s own Native().not_dumpable() dies by the same signals, and nothing reaches the collector':
            all(nothing(row) for row in rows('pipe',True)),
        'file: a dumpable child killed by SIGQUIT and by SIGSEGV leaves a core file, the canary of its memory in it':
            (out.get('patterns_set') or {}).get('file') is True and all(dumped(row) for row in rows('file',False)),
        'file: the same child after the source\'s own Native().not_dumpable() dies by the same signals, and no core file is written':
            all(nothing(row) for row in rows('file',True)),
        'kernel.core_pattern put back as it was found':out.get('restored') is True,
    }

def labels():return ['%s %s %s'%(mode,kind,name) for mode in MODES for kind in ('dumpable','protected') for name in SIGNALS]
def report(out):
    checks=expectations(out);cases=[name for name in labels() if name in out]
    return {'schema':SCHEMA,'core_pattern_before':out.get('before'),'core_pattern_after':out.get('after'),'restored':out.get('restored'),
            'note':'kernel.core_pattern of this throwaway runner, not of the production host','patterns_set':out.get('patterns_set'),'error':out.get('error'),
            'cases':{name:out[name] for name in cases},'expectations':checks,
            'all_cases_ran':len(cases)==8 and all(out[name].get('ok') for name in cases),'all_expectations_met':all(checks.values())}

def main(arguments):
    if arguments:
        print(__doc__);return 1
    throwaway=sys.platform.startswith('linux') and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
    if not (throwaway and os.geteuid()==0):
        print('REFUSED: a throwaway GitHub-hosted Linux runner, as root, with HOSTOPS_THROWAWAY_RUNNER=yes',file=sys.stderr);return 1
    if not os.path.isfile(SOURCE):
        print('REFUSED: build/token_from_env.py is not beside this script',file=sys.stderr);return 1
    before=read_pattern();directory=tempfile.mkdtemp(prefix='hostops02-dump-proof-');out={}
    try:out=collect(directory)
    except Exception as error:out={'error':type(error).__name__}             # every case not run is said: all_cases_ran is false
    finally:
        try:write_pattern(before)
        finally:
            after=read_pattern()
            out.update(before=before.decode('utf-8','replace').rstrip('\n'),after=after.decode('utf-8','replace').rstrip('\n'),restored=after==before)
            shutil.rmtree(directory,ignore_errors=True)
    result=report(out)
    print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_cases_ran'] and result['all_expectations_met'] else 3 if result['all_cases_ran'] else 2

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
