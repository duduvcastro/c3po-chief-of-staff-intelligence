"""The capacity probe on a real engine: the operation's own perform(), command table, helpers, runner and Native, with
the steps' own argv, against an image built by run.sh from the release checkout (dd4ec4bb, c3po/backend/Dockerfile,
its revision label) and a capacity tree that run.sh made under /var/lib/c3po-capacity (root:root 0700, four private
children, a config file 0600 that is NOT a valid static config) and bound read-only in a stand-in worker container
named c3po-r2d2-worker-1 (run.sh starts it detached with that bind, the release pin and the mount source of K6b's block in
its environment, and removes it at the end).

What it shows, each as a boolean (the expectations below), and which unproven item of DESIGN.md each closes:
- CALENDAR completes: calendar-pin.py runs in the image under --read-only, --network none, uid 0 and no capability, and
  its line names the pinned epoch, package and document order (U-C1, U-C2);
- IDENT completes: two containers with the read-only bind print identities equal to the ones the source computed from
  the numbers it read on the host by descriptor (U-B1: a bind shows the host's device and inode numbers);
- LOAD reaches the image's own startup checks through the bind: the worker's mount is read with MOUNTS_FORMAT on this
  engine (U-W1), the application imports under --read-only (U-L1), Settings takes the five values by name, CapacityConfig
  opens the config directory through AnchoredRoot and refuses the CI config by its fields (CAPACITY_CONFIG_FIELDS), so the
  receipt is STEP_RAN_ANSWER_NOT_AS_EXPECTED with CAPACITY_STARTUP_REFUSED_IN_THE_IMAGE (a valid static config needs the
  epoch's documents and is not made here: the success of LOAD stays unproven, U-L2);
- no step leaves a container, and every container ends far inside its class.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root (run.sh prepares it). NEVER the production host. It refuses
to run anywhere else: Linux, effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted are
all required. NOT RUN by its author: no Linux and no docker were available offline. --self-test runs the same
collection against the emulated engine of the core's tests/hostemu.py; it proves that this script is coherent with the
source, and nothing about a real engine.

perform() is entered directly, after validate_members(), with a gate that only counts the 60 seconds: the documents,
the date set, the bands and the windows are the conformance suite's ground and do not depend on the engine.

usage: sudo -n env ... /usr/bin/python3 -I -B linux_root/probe_shape.py <image ID> <config sha256>
       /usr/bin/python3 -B linux_root/probe_shape.py --self-test
exit 0 only when every run was made AND every expectation is met; 2 when a run was not made; 3 when all were made and
an expectation is not met; 1 for a refusal.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime,timezone

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
import conftest                                    # puts the tests of the frozen core on the path
import family as f
import hostemu
import kprobe

SCHEMA='HOSTOPS02_CAPACITY_PROBE_LINUX_ROOT_SHAPE_V1'
ROOT='/var/lib/c3po-capacity'
CI_RELEASE_SHA=hashlib.sha256(b'hostops02 capacity probe ci release sha').hexdigest()
CI_MOUNT_RECEIPT=hashlib.sha256(b'hostops02 capacity probe ci mount receipt').hexdigest()

def bound(label):
    return {'request_sha256':'1'*64,'authority_sha256':'2'*64,'go_sha256':hashlib.sha256(label.encode()).hexdigest(),'payload_sha256':'4'*64,
            'host_binding_sha256':'5'*64}

def plan_of(m,host,step,image,config_sha,release_sha):
    gate=lambda:55.0
    rows=[];fd=m.descend(host,'/var/lib',gate,rows);host.close(fd)
    plan={'step':step,'image_id':image,'image_revision':m.RELEASE_REVISION,'evidence_boot_id_sha256':m.boot_id_sha256(host,gate),
          'capacity':None if step=='CALENDAR' else {'root_path':ROOT,'parent_rows':rows},'load':None}
    if step=='LOAD':plan['load']={'config_file':'/c3po-capacity/config/'+kprobe.CONFIG_NAME,'config_sha256':config_sha,'release_sha':release_sha,
                                  'mount_receipt_sha256':CI_MOUNT_RECEIPT}
    return plan

def one(m,host,plan,label):
    """validate_members, then perform with a clock of its own. Returns the receipt; a failure is a row, never an exception."""
    started=time.monotonic()
    def gate():
        left=60.0-(time.monotonic()-started)
        if left<=0:raise m.Refused('GO_EXPIRED')
        return left
    try:
        m.validate_members(plan)
        return dict(m.perform(plan,gate,host,bound(label),lambda:datetime.now(timezone.utc),time.monotonic,m.Effects()),ok=True)
    except Exception as error:
        return {'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}

def collect(engine):
    m=kprobe.K().m;out={}
    for step in ('CALENDAR','IDENT','LOAD'):
        host=engine.host()
        try:plan=plan_of(m,host,step,engine.image,engine.config_sha,engine.release_sha)
        except Exception as error:
            out[step]={'ok':False,'error':type(error).__name__,'code':None};continue
        out[step]=one(m,host,plan,step)
    return out

def facts(receipt):
    """What a receipt says, reduced to what the expectations read."""
    if not receipt or not receipt.get('ok'):return None
    lines=[line['line'] for line in receipt.get('lines') or [] if line and line['valid']]
    return {'verdict':[receipt['status'],receipt['outcome'],receipt['code']],'lines':lines,
            'seconds':[item['seconds'] for item in receipt.get('containers') or []],
            'left':None if receipt.get('containers_after') is None else [receipt['containers_after']['names_present'],receipt['containers_after']['not_there_before']],
            'comparison':receipt.get('comparison'),'precheck_worker':(receipt.get('precheck') or {}).get('worker'),
            'tree_after':receipt.get('tree_after'),'worker_after':receipt.get('worker_after')}

def expectations(out):
    m=kprobe.K().m;calendar,ident,load=(facts(out.get(step)) for step in ('CALENDAR','IDENT','LOAD'))
    def left_nothing(item):return item is not None and item['left']==[False,0]
    def inside(item,seconds):return item is not None and bool(item['seconds']) and all(type(value) in (int,float) and value<seconds for value in item['seconds'])
    return {
        'CALENDAR completes in the image: the line names the pinned epoch, package and document order':
            calendar is not None and calendar['verdict']==['METADATA_ONLY_REQUIRES_REVIEW',m.CALENDAR_OUTCOME,None]
            and len(calendar['lines'])==1 and calendar['lines'][0]['package_sha']==m.PACKAGE_SHA,
        'IDENT completes: two runs agree and equal the identities computed from the host numbers (a bind shows them)':
            ident is not None and ident['verdict']==['METADATA_ONLY_REQUIRES_REVIEW',m.IDENT_OUTCOME,None]
            and ident['comparison']=={'runs_agree':True,'equal_to_the_host':{name:True for name in m.CAPACITY_CHILDREN}},
        'LOAD reads the worker mount and reaches CapacityConfig through the bind, which refuses the CI config by its fields':
            load is not None and load['verdict']==['PARTIAL_METADATA_REQUIRES_REVIEW',m.NOT_AS_EXPECTED_OUTCOME,'CAPACITY_STARTUP_REFUSED_IN_THE_IMAGE']
            and load['lines']==[{'status':'CAPACITY_STARTUP_REFUSED','code':'CAPACITY_CONFIG_FIELDS'}]
            and load['precheck_worker'] is not None and load['precheck_worker']['capacity_mount']=={'type':'bind','source_as_signed':True,'read_only':True}
            and load['worker_after']=={'status':'COMPLETE','unchanged':True,'code':None},
        'no step leaves a container':all(left_nothing(item) for item in (calendar,ident,load)),
        'the held tree is unchanged after IDENT and LOAD':all(item is not None and item['tree_after']=={'status':'COMPLETE','unchanged':True,'code':None}
                                                             for item in (ident,load)),
        'every container ends far inside its class (IDENT under 14 s, CALENDAR and LOAD under 34 s)':
            inside(ident,14) and inside(calendar,34) and inside(load,34)}

def report(out):
    expected=expectations(out)
    return {'schema':SCHEMA,'runs':out,'all_runs_made':all(out.get(step,{}).get('ok') for step in ('CALENDAR','IDENT','LOAD')),
            'expectations':expected,'all_expectations_met':all(expected.values())}


class Real:
    """The engine of the runner and the source's own Native."""
    def __init__(self,image,config_sha):self.image,self.config_sha,self.release_sha=image,config_sha,CI_RELEASE_SHA
    def host(self):return kprobe.K().m.Native()

class Emulated:
    """The core's emulated engine, with the tree and the stand-in worker run.sh makes, and the model containers of the
    tests; LOAD answers what the release answers for the CI config (refused by its fields)."""
    def __init__(self):
        self.image=hostemu.BACKEND;self.config_sha=kprobe.CONFIG_SHA;self.release_sha=kprobe.RELEASE_SHA
    def host(self):
        k,host=kprobe.world()
        def on_run(call):
            step=kprobe.assert_run(call)
            if step=='LOAD':return 1,kprobe.compact({'status':'CAPACITY_STARTUP_REFUSED','code':'CAPACITY_CONFIG_FIELDS'})
            return kprobe.container(call)
        host.docker.on_run=on_run;return host

def main(arguments):
    if arguments==['--self-test']:
        result=report(collect(Emulated()))
    else:
        if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes'
                and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and len(arguments)==2):
            sys.stderr.write('REFUSED: a throwaway GitHub-hosted Linux runner as root only, with <image ID> <config sha256>\n');return 1
        result=report(collect(Real(arguments[0],arguments[1])))
    sys.stdout.write(json.dumps(result,sort_keys=True,indent=1,default=str)+'\n')
    if not result['all_runs_made']:return 2
    return 0 if result['all_expectations_met'] else 3

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
