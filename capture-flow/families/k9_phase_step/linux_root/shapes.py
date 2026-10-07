"""K9W (k9_phase_step) on a real engine: the assembled source's own run(), its own Native and the real docker CLI under
the fixed environment of the family, as uid 0, against a throwaway K9 tree at the compiled placement. What no
workstation run and no emulation can show (DESIGN.md section 9, K9W-U1 to K9W-U8):

  - `docker create --pull never --init --user 0:0 --read-only --cap-drop ALL --security-opt no-new-privileges --restart no`
    with this source's middle (--name, two --label, --network, --env-file, two --env, the binds, the image ID, the
    command) accepted by the CLI, and `docker start` of the printed ID;
  - the two labels, the state and the exit code read back with the launched format (State.OOMKilled, index of the labels);
  - `timeout -s KILL <n>` of the image's busybox ending a container that outlives it (exit 137);
  - the env files read by the CLI as root and given to the container under --read-only (the stand-in counts the names
    it sees, never their values);
  - a runner in a 0600 file of root read by root in the container through a read-only bind under --cap-drop ALL, and
    its receipts written by exclusive creation into the 0700 day directory through a read-write bind;
  - `docker rm <id>` of the exited container of the previous step by the next step, and nothing else removed;
  - an attached `docker run --rm` with the nested read-write bind of receipts/ over a read-only day directory (stage's shape);
  - the real system calls of the source as real root on Linux (O_NOATIME, uid 0, the claim, the directories, the files).

The image of a throwaway runner is a plain python:3.12-alpine image with the revision label (busybox timeout, python).
It has no /app: the step's runner is a STAND-IN (STAND_IN below, written as tools/k9_runner-<its sha256>.py), not
k9_runner.py; it writes the start marker and the receipt of the contracts, so that the next step's needs are met.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root. NEVER the production host: it creates /var/lib/c3po
(refused if it or /mnt/day-d-data exists), two docker networks and containers. It refuses to run anywhere else: Linux,
effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted are all required. (Revision 2: the source
root is /var/lib/c3po/r2d2-v2-source-20261005, decision 6; /mnt/day-d-data is neither created nor used.) NOT RUN by the
author: no Linux and no docker were available offline. --self-test runs the same collection against the emulated
engine of tests/k9w.py; it proves that this script is coherent with the source, and nothing about a real engine.

usage: sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -B linux_root/shapes.py <image ID>
       /usr/bin/python3 -B linux_root/shapes.py --self-test
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when all ran and an
expectation is not met; 1 for a refusal.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime,timedelta

HERE=os.path.dirname(os.path.abspath(__file__))
OPERATION=os.path.dirname(HERE)
sys.path.insert(0,os.path.join(OPERATION,'..','core','tests'));sys.path.insert(0,os.path.join(OPERATION,'tests'))
import family as f
import k9w

SCHEMA='HOSTOPS02_K9_PHASE_STEP_LINUX_ROOT_SHAPES_V1'
COMPLETE='METADATA_ONLY_REQUIRES_REVIEW'
CANARY='never-emit-ci-canary'
NETWORKS={'PROVIDER':'bridge','DATABASE':'k9ci_internal','DATABASE_AND_PROVIDER':'k9ci_loopback'}
# The stand-in of the runner: the contracts' start marker and receipt for the step named by its plan, the names of
# the environment it sees counted (never printed), then an optional sleep. Standard library only.
STAND_IN=r'''import hashlib, json, os, sys, time
plan_path, plan_sha = sys.argv[2], sys.argv[4]
raw = open(plan_path, 'rb').read()
assert hashlib.sha256(raw).hexdigest() == plan_sha
plan = json.loads(raw)
op = plan['k9_operation']
identity = {'epoch': plan['epoch'], 'day': plan['day'], 'phase': plan['k9_phase'], 'operation': op, 'attempt_key': plan['attempt_key'], 'step_plan_sha256': plan_sha}
def put(name, body):
    fd = os.open('/c3po-k9-day/receipts/' + name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.write(fd, json.dumps(body, sort_keys=True, separators=(',', ':')).encode()); os.fsync(fd); os.close(fd)
when = '2026-10-05T21:29:30+00:00'
put(op + '.STARTED.json', dict(identity, schema='K9_STEP_STARTED_V1', started_at=when))
names = [name for name in ('C3PO_EODHD_API_TOKEN', 'C3PO_FINNHUB_API_TOKEN', 'C3PO_FMP_API_TOKEN', 'C3PO_R2D2_RISK_DATABASE_URL') if os.environ.get(name)]
counts = {'env_names_present': len(names), 'producers_enabled': int(os.environ.get('C3PO_R2D2_V2_PRODUCERS_ENABLED') == 'true'),
          'build_sha_given': int(os.environ.get('C3PO_BUILD_SHA') == plan['constants']['code_revision']), 'uid_zero': int(os.getuid() == 0)}
try:
    open('/probe-write', 'wb'); counts['root_writable'] = 1
except OSError:
    counts['root_writable'] = 0
put(op + '.RECEIPT.json', dict(identity, schema='K9_STEP_RECEIPT_V1', status='COMPLETE', code=None, started_at=when, completed_at=when,
                               package_sha256=plan['constants']['package_sha256'], build_sha=plan['constants']['code_revision'], outputs={}, aggregates={}, counts=counts))
time.sleep(float(os.environ.get('K9CI_SLEEP', '0')))
'''
STAND_IN_BYTES=STAND_IN.encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()

def refuse(text):
    sys.stderr.write('REFUSED: %s\n'%text);raise SystemExit(1)

def make_tree(root_path):
    """The K9 tree as E0 and K3-K9 leave it, under root_path ('' on the runner, a temporary root for the self-test)."""
    p=k9w.PLACEMENT;paths=['/var/lib/c3po',p['k9_root'],p['days'],p['tools'],p['claims'],p['secrets'],p['emitter'],p['source_root']]
    for path in paths:
        os.makedirs(root_path+path,exist_ok=False);os.chmod(root_path+path,0o755 if path=='/var/lib/c3po' else 0o700)
    def put(path,raw):
        fd=os.open(root_path+path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,raw);os.close(fd)
    put(p['provider_env_file'],('C3PO_EODHD_API_TOKEN=%s\nC3PO_FINNHUB_API_TOKEN=%s\nC3PO_FMP_API_TOKEN=%s\n'%(CANARY,CANARY,CANARY)).encode())
    put(p['risk_db_env_file'],('C3PO_R2D2_RISK_DATABASE_URL=postgresql://r:%s@db:5432/c3po\n'%CANARY).encode())
    put(p['emitter_password'],(CANARY+'\n').encode());put(p['tools']+'/k9_runner-'+k9w.RUNNER_SHA256+'.py',STAND_IN_BYTES)

def rows(path):
    out=[];prefix=''
    for part in ['']+[part for part in path.strip('/').split('/') if part]:
        if part:prefix+='/'+part
        info=os.lstat(prefix or '/')
        out.append({'path':prefix or '/','device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':info.st_mode&0o7777})
    return out

def documents(k,operation,image_id,boot_sha,rows_of):
    moment=k9w.at(k9w.GRID[operation])
    constants=k9w.constants(k,image_id=image_id,runner_sha256=k9w.RUNNER_SHA256,networks=dict(NETWORKS))
    plan={'mode':k9w.WRITE[operation][1],'epoch':k9w.EPOCH,'day':k9w.DAY,'k9_phase':k9w.WRITE[operation][0],'k9_operation':operation,'slot':'PRIMARY',
          'attempt_key':k9w.attempt_key(k9w.EPOCH,k9w.DAY,k9w.WRITE[operation][0],operation),'run_not_after':k9w.run_not_after(operation,moment),
          'constants':constants,'parent_rows':{name:{'path':k9w.PLACEMENT[name],'rows':rows_of(k9w.PLACEMENT[name]),'open_root':k9w.open_root(name)} for name in k9w.CHAINS},
          'evidence_boot_id_sha256':boot_sha,'bind':None}
    return f.Docs(k,plan,now=moment,minutes=k9w.MINUTES,evidence=list(k9w.EVIDENCE))

def collect(k,run,inspect,wait,exited,killed,listing):
    """collect_launch, then commit_launch (which removes the collect container), then the busybox timeout. run(docs)
    returns a receipt; inspect(id) the launched format of one container; wait(id) waits for it to exit; listing() the
    names of the K9 containers; killed() runs `timeout -s KILL 2 sleep 30` in the image and returns its status."""
    out={}
    def shape(label,action):
        try:out[label]=dict(action(),ok=True)
        except Exception as error:out[label]={'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}
    def brief(receipt):
        text=json.dumps(receipt,sort_keys=True)
        return {'status':receipt.get('status'),'outcome':receipt.get('outcome'),'code':receipt.get('code'),'phase_reached':receipt.get('phase_reached'),
                'mutating_calls':receipt.get('mutating_calls'),'commands_started':receipt.get('commands_started'),'timeout_seconds':receipt.get('timeout_seconds'),
                'removed':receipt.get('removed'),'elapsed_ms':(receipt.get('clock') or {}).get('monotonic_elapsed_ms'),'canary_in_receipt':CANARY in text,
                'container_id_present':bool(receipt.get('container_id'))}
    def launch(operation):
        receipt=run(operation);identifier=receipt.get('container_id');row={}
        if identifier:wait(identifier);row=inspect(identifier)
        receipts=exited(operation)
        return {'receipt':brief(receipt),'container':{key:row.get(key) for key in ('state','running','exit_code','oom_killed')},
                'labels_as_set':bool(row) and row.get('attempt_key')==k9w.attempt_key(k9w.EPOCH,k9w.DAY,k9w.WRITE[operation][0],operation),
                'step_receipts':receipts,'k9_containers_after':listing()}
    shape('collect_launch',lambda:launch('collect_launch'))
    shape('commit_launch_removes_the_collect_container',lambda:launch('commit_launch'))
    shape('busybox_timeout_kills',lambda:{'status':killed()})
    return out

def expectations(out):
    collect_=out.get('collect_launch',{});commit=out.get('commit_launch_removes_the_collect_container',{});kill=out.get('busybox_timeout_kills',{})
    def done(shape):
        receipt=shape.get('receipt') or {}
        return (receipt.get('status'),receipt.get('code'))==(COMPLETE,None) and receipt.get('canary_in_receipt') is False
    def counts(shape):return ((shape.get('step_receipts') or {}).get('counts') or {})
    return {
        'create with the fixed prefix and the middle of the builder, then start, completes a LAUNCH':done(collect_) and done(commit),
        'the container ran to its end with exit 0, not OOM-killed':(collect_.get('container') or {}).get('state')=='exited' and (collect_.get('container') or {}).get('exit_code')==0,
        'the labels read back with the launched format':collect_.get('labels_as_set') is True and commit.get('labels_as_set') is True,
        'the stand-in runner in a root 0600 file ran from the read-only tools bind and wrote its receipts as root into the day directory':
            (collect_.get('step_receipts') or {}).get('present')==['RECEIPT','STARTED'] and counts(collect_).get('uid_zero')==1,
        'the env file reached the container through the CLI (three names) and the two --env words':counts(collect_).get('env_names_present')==3
            and counts(collect_).get('producers_enabled')==1 and counts(collect_).get('build_sha_given')==1,
        'the root filesystem of the container is read-only':counts(collect_).get('root_writable')==0,
        'the database network class gives no env file':counts(commit).get('env_names_present')==0,
        'commit removed the exited collect container by its ID and left its own':(commit.get('receipt') or {}).get('removed') is True
            and commit.get('k9_containers_after')==['c3po-k9-20261006-commit_launch'],
        'the container timeout of the image (busybox) ends a longer command with SIGKILL':kill.get('status')==137}

def emulated():
    """The same collection on the emulated engine (--self-test): the container's side is the stand-in's, written by
    on_start into the emulated tree."""
    k=f.load(OPERATION);host=k9w.world(k)
    node=host.tree.get(k9w.PLACEMENT['tools']+'/k9_runner-'+k9w.RUNNER_SHA256+'.py');node.content=bytearray(STAND_IN_BYTES)   # the stand-in under the compiled name
    host.docker.networks=dict(NETWORKS)
    def on_start(item):
        name=item['Name'].split('-',3)[3];created=[call for call in host.docker.created if call.name==item['Name'][1:]][-1]
        plan_sha=created.command[10];phase=k9w.WRITE[name][0]
        identity={'epoch':k9w.EPOCH,'day':k9w.DAY,'phase':phase,'operation':name,'attempt_key':k9w.attempt_key(k9w.EPOCH,k9w.DAY,phase,name),'step_plan_sha256':plan_sha}
        environment={};created.container_environment={};host.docker.check_environment(created);environment=created.container_environment
        counts={'env_names_present':len([n for n in ('C3PO_EODHD_API_TOKEN','C3PO_FINNHUB_API_TOKEN','C3PO_FMP_API_TOKEN','C3PO_R2D2_RISK_DATABASE_URL') if environment.get(n)]),
                'producers_enabled':int(environment.get('C3PO_R2D2_V2_PRODUCERS_ENABLED')=='true'),'build_sha_given':int(environment.get('C3PO_BUILD_SHA')==k9w.REVISION),
                'uid_zero':1,'root_writable':0}
        when='2026-10-05T21:29:30+00:00'
        k9w.add_file(host,k9w.day_path('receipts',name+'.STARTED.json'),k9w.canonical(dict(identity,schema='K9_STEP_STARTED_V1',started_at=when)))
        k9w.add_file(host,k9w.day_path('receipts',name+'.RECEIPT.json'),k9w.canonical(dict(identity,schema='K9_STEP_RECEIPT_V1',status='COMPLETE',code=None,
            started_at=when,completed_at=when,package_sha256=k9w.PACKAGE,build_sha=k9w.REVISION,outputs={},aggregates={},counts=counts)))
        item['State'].update(Status='exited',Running=False,ExitCode=0)
    host.docker.on_start=on_start
    def run(operation):return documents(k,operation,k9w.hostemu.BACKEND,f.BOOT_SHA,lambda path:k9w.hostemu.rows(host,path)).run(host)
    def inspect(identifier):
        item=host.docker.container(identifier)
        return {} if item is None else {'state':item['State']['Status'],'running':item['State']['Running'],'exit_code':item['State']['ExitCode'],
                                        'oom_killed':item['State']['OOMKilled'],'attempt_key':item['Config']['Labels'].get('c3po.k9.attempt_key')}
    def exited(operation):
        present=sorted(suffix for suffix in ('STARTED','RECEIPT','FAILED') if host.tree.get(k9w.day_path('receipts',operation+'.'+suffix+'.json')) is not None)
        node=host.tree.get(k9w.day_path('receipts',operation+'.RECEIPT.json'))
        return {'present':present,'counts':json.loads(bytes(node.content))['counts'] if node is not None else None}
    def listing():return sorted(item['Name'][1:] for item in host.docker.containers if item['Name'].startswith('/c3po-k9-'))
    return collect(k,run,inspect,lambda identifier:None,exited,lambda:137,listing)

def real(image_id):
    k=f.load(OPERATION);docker=next(path for path in ('/usr/bin/docker','/usr/local/bin/docker') if os.path.isfile(path))
    def cli(*words,timeout=60):
        return subprocess.run([docker]+list(words),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin'},timeout=timeout)
    for network,internal in (('k9ci_internal',True),('k9ci_loopback',False)):
        cli('network','create',*(['--internal'] if internal else []),network)
    make_tree('')
    # Controlled capacity for the real-Docker interface smoke, not a physical-capacity proof.
    class CapacitySmokeNative(k.m.Native):
        def fstatvfs(self,fd):
            values=list(super().fstatvfs(fd));values[1]=1;values[4]=274877906944
            return os.statvfs_result(values)
    with open('/proc/sys/kernel/random/boot_id','rb') as stream:boot_sha=sha(stream.read().strip())
    def run(operation):
        docs=documents(k,operation,image_id,boot_sha,rows);start=time.monotonic()
        return docs.run(CapacitySmokeNative(),clock=lambda:docs.now+timedelta(seconds=time.monotonic()-start),monotonic=time.monotonic)
    def inspect(identifier):
        done=cli('container','inspect','--format',k.m.K9W_LAUNCHED_FORMAT,identifier)
        return json.loads(done.stdout) if done.returncode==0 else {}
    def wait(identifier):
        for _ in range(120):
            if inspect(identifier).get('state')=='exited':return
            time.sleep(1)
    def exited(operation):
        base=k9w.day_path('receipts')+'/'+operation;present=sorted(suffix for suffix in ('STARTED','RECEIPT','FAILED') if os.path.exists(base+'.'+suffix+'.json'))
        counts=None
        if 'RECEIPT' in present:
            with open(base+'.RECEIPT.json','rb') as stream:counts=json.loads(stream.read())['counts']
        return {'present':present,'counts':counts}
    def listing():
        done=cli('ps','-a','--format','{{.Names}}');return sorted(name for name in done.stdout.decode().split() if name.startswith('c3po-k9-'))
    def killed():return cli('run','--rm','--pull','never','--init','--network','none',image_id,'timeout','-s','KILL','2','sleep','30',timeout=60).returncode
    return collect(k,run,inspect,wait,exited,killed,listing)

def main(argv):
    if argv==['--self-test']:out=emulated()
    else:
        if len(argv)!=1 or not argv[0].startswith('sha256:'):refuse('usage: shapes.py <image ID> | --self-test')
        if sys.platform!='linux' or os.geteuid()!=0:refuse('Linux and uid 0 only')
        if os.environ.get('HOSTOPS_THROWAWAY_RUNNER')!='yes' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':refuse('a throwaway GitHub-hosted runner only')
        for path in ('/var/lib/c3po','/mnt/day-d-data'):
            if os.path.lexists(path):refuse(path+' exists: this is not a throwaway runner')
        out=real(argv[0])
    checks=expectations(out)
    result={'schema':SCHEMA,'shapes':out,'expectations':checks,'all_shapes_ran':all(shape.get('ok') for shape in out.values()),
            'all_expectations_met':all(checks.values()),'emulated':True,'docker_real':argv!=['--self-test'],
            'capacity_mode':'controlled_test_only','physical_capacity_proven':False,
            'capacity_available_bytes':274877906944,'compiled_floor_bytes':214748364800}
    sys.stdout.write(json.dumps(result,sort_keys=True,indent=1)+'\n')
    return 0 if result['all_shapes_ran'] and result['all_expectations_met'] else (2 if not result['all_shapes_ran'] else 3)

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
