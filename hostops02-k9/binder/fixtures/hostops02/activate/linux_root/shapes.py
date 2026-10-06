"""K6a (activate) end to end on a real engine: the assembled source's own run(), its own Native, the real docker CLI and
the real compose plugin under the fixed environment of the family (no HOME), on a throwaway compose project shaped like
the deploy tree of the host. What no workstation run and no emulation can show:

  - `docker compose config --format json` with the override on standard input and from the delivered file, started
    as root with PATH=/usr/bin:/bin and nothing else, and what its JSON says of a bind (type, source, target, read_only);
  - the override this source writes (json.dumps with its default separators) read by compose as a compose file;
  - `docker compose up -d --no-deps --no-build --pull never --force-recreate r2d2-worker` with that file list, the old
    container gone, one new container, every other container untouched, and how long it takes against the 30 s class
    when the worker is stopped as the production worker is (python as PID 1, no SIGTERM handler, no init, no
    stop_grace_period: the engine waits its whole stop timeout and then kills; c3po/compose.yml:138-176 at the release);
  - a container under a temporary name of the worker's (<12 hex>_<name>) refused before any effect;
  - what a recreate interrupted inside the stop leaves, on a third service nobody else uses: started as the runner of
    the core starts a command (own session, the fixed environment), its process group killed after 3 s, the containers
    of that service listed during the stop, right after the kill and 12 s later. It says which of the two orders the
    runner's compose makes its calls in (DESIGN.md section 6) and whether the engine finishes the stop without the client;
  - the environment template of the core on the new container (five names) and on the old one (the four absent);
  - the flock of the deployment lock on a read-only descriptor while flock(1) holds it; the bounded wait and the refusal;
  - a run of this source as real root on Linux: O_NOATIME walks, mkdir, exclusive open, link, unlink, fsync, the pause.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root (linux_root/run.sh prepares it). NEVER the production host:
it creates a compose project and containers. It refuses to run anywhere else: Linux, effective uid 0,
HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted are all required. NOT RUN by its author: no Linux and
no docker were available offline. --self-test runs the same collection against the emulated host of the core's
tests/hostemu.py; it proves that this script is coherent with the source, and nothing about a real engine.

usage: sudo -n /usr/bin/python3 -I -B linux_root/shapes.py --prepare <work directory> <image reference> <project> <core tests directory>
           writes the two trees below into the (empty, root-owned) work directory; starts nothing
       sudo -n env ... /usr/bin/python3 -I -B linux_root/shapes.py <image ID> <work directory> <project> <core tests directory>
           <image ID>        the local ID of an image that has `python` and carries the revision label of the epoch
           <work directory>  prepared by run.sh, root:root, not below a world-writable directory:
                             deploy/{.env,.deploy-version,<project>/compose.yml,runtime/security/deployment.lock}
                             data/{.r2d2-v2-pinned,r2d2-v2-live/,r2d2-v2-release-20261005/release.CERTIFIED.json}
                             and the project already up (the worker and two other services running)
           prints one JSON object: every shape, and the expectations the source relies on, each as a boolean
       /usr/bin/python3 -B linux_root/shapes.py --self-test
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when all ran and an
expectation is not met; 1 for a refusal.
"""
import json
import os
import sys
import time

HERE=os.path.dirname(os.path.abspath(__file__))
SCHEMA='HOSTOPS02_ACTIVATE_LINUX_ROOT_SHAPES_V1'
CANARY='never-emit-ci-canary'
COMPLETE='METADATA_ONLY_REQUIRES_REVIEW'

TEMPORARY='0123456789ab_'                 # the form of the name compose gives while it replaces the container of a service
def view(name,old,rows):
    """Rows (name, ID, state) of one service as [which name, state, whether it is a container that was there before]:
    no ID leaves this function."""
    import re
    def which(item):return 'NAME' if item==name else 'TEMPORARY_NAME' if re.fullmatch('[0-9a-f]{12}_'+re.escape(name),item) else 'OTHER_NAME'
    return sorted([which(row[0]),row[2],row[1] in old] for row in rows)
def order_of(during,later):
    """Which order the calls of the recreate were made in, as far as the listing during the stop of the old container
    shows it. NEW_FIRST: the new container already exists under the temporary name while the old one still carries the
    service's name. OLD_FIRST: only the old container exists while it is being stopped (it is renamed afterwards), or
    the old one already carries the temporary name. Anything else is UNDETERMINED (the stop was over before the look)."""
    temporary=[row for row in during if row[0]=='TEMPORARY_NAME'];named=[row for row in during if row[0]=='NAME']
    if len(temporary)==1 and temporary[0][2] is False and len(named)==1 and named[0][2] is True:return 'NEW_FIRST'
    if len(temporary)==1 and temporary[0][2] is True:return 'OLD_FIRST'
    if not temporary and len(during)==1 and named and named[0][2] is True and not [row for row in later if row[0]=='TEMPORARY_NAME' and row[2] is False]:return 'OLD_FIRST'
    return 'UNDETERMINED'

def collect(make,run,hold,inspect,leftover,interrupt):
    """Five runs of the source in the order that leaves the project usable for the next, then one interrupted recreate
    of a service no run looks at. make(**changes) gives a bound fixture; run(docs) its receipt; hold(seconds) makes
    another process hold the lock; inspect() what is on the host; leftover(True|False) creates and removes a container
    under a temporary name of the worker's; interrupt() the rows of the third service around an interrupted recreate."""
    out={}
    def shape(label,action):
        try:out[label]=dict(action(),ok=True)
        except Exception as error:
            out[label]={'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}
    def brief(receipt):
        text=json.dumps(receipt,sort_keys=True)
        return {'status':receipt.get('status'),'outcome':receipt.get('outcome'),'code':receipt.get('code'),'phase_reached':receipt.get('phase_reached'),
                'mutating_calls':receipt.get('mutating_calls'),'commands_started':receipt.get('commands_started'),'budget':receipt.get('budget'),
                'elapsed_ms':(receipt.get('clock') or {}).get('monotonic_elapsed_ms'),'recreate':receipt.get('recreate'),
                'precheck':{key:value for key,value in (receipt.get('precheck') or {}).items() if key!='worker'},
                'ledger_states':[row.get('state') for row in receipt.get('ledger') or []],'directory_states':[row.get('state') for row in receipt.get('directories') or []],
                'receipt_bytes':len(text),'canary_in_receipt':CANARY in text,'sealed':'metadata_sha256' in receipt}
    def wrong_mount():
        before=inspect();receipt=run(make(mount_target='/app/elsewhere'));after=inspect()
        return {'receipt':brief(receipt),'host_unchanged':before==after}
    def lock_busy():
        before=inspect();hold(8);receipt=run(make(wait_seconds=2));after=inspect()
        time.sleep(0 if receipt.get('_emulated') else 9)                 # the holder lets go before the next shape
        return {'receipt':brief(receipt),'host_unchanged':before==after,'seconds':((receipt.get('clock') or {}).get('monotonic_elapsed_ms') or 0)/1000.0}
    def left():
        leftover(True)
        try:
            before=inspect();receipt=run(make());after=inspect()
        finally:leftover(False)
        return {'receipt':brief(receipt),'host_unchanged':before==after,'listed_before':len(before.get('other') or [])}
    def complete():
        before=inspect();started=time.monotonic();receipt=run(make());seconds=round(time.monotonic()-started,2);after=inspect()
        return {'receipt':brief(receipt),'seconds':seconds,'before':before,'after':after}
    def interrupted():
        seen=interrupt();old=seen['old'];name=seen['name']
        rows={key:view(name,old,seen[key]) for key in ('before','during_the_stop','right_after_the_kill','twelve_seconds_later')}
        return dict(rows,order=order_of(rows['during_the_stop'],rows['twelve_seconds_later']),command_still_running_when_killed=seen['running_when_killed'],
                    seconds_until_the_kill=seen['seconds'],emulated=seen.get('emulated',False),
                    a_container_runs_under_the_name_twelve_seconds_later=bool([row for row in rows['twelve_seconds_later'] if row[:2]==['NAME','running']]),
                    the_old_container_stopped_or_went_after_the_client_was_killed=not [row for row in rows['twelve_seconds_later'] if row[1]=='running' and row[2] is True])
    def already_activated():
        before=inspect();receipt=run(make(directory_name='2026-10-05-second'));after=inspect()
        return {'receipt':brief(receipt),'host_unchanged':before==after}
    shape('refused_when_the_render_does_not_bind_the_data_root_at_the_signed_target',wrong_mount)
    shape('refused_while_another_process_holds_the_deployment_lock',lock_busy)
    shape('refused_while_a_container_carries_a_temporary_name_of_the_worker',left)
    shape('complete_run',complete)
    shape('refused_when_the_worker_already_carries_the_keys',already_activated)
    shape('recreate_of_a_third_service_interrupted_inside_the_stop',interrupted)
    return out

def expectations(out):
    """What the source relies on, read from the shapes: one boolean per statement, False when its shape did not run."""
    mount=out.get('refused_when_the_render_does_not_bind_the_data_root_at_the_signed_target',{});busy=out.get('refused_while_another_process_holds_the_deployment_lock',{})
    done=out.get('complete_run',{});again=out.get('refused_when_the_worker_already_carries_the_keys',{})
    left=out.get('refused_while_a_container_carries_a_temporary_name_of_the_worker',{});cut=out.get('recreate_of_a_third_service_interrupted_inside_the_stop',{})
    receipt=done.get('receipt') or {};run=receipt.get('recreate') or {};facts=run.get('facts') or {};budget=receipt.get('budget') or {}
    before=done.get('before') or {};after=done.get('after') or {}
    def refused(shape,code):
        row=shape.get('receipt') or {}
        return (row.get('status'),row.get('code'),row.get('phase_reached'))==('REFUSED',code,'PRECHECK') and shape.get('host_unchanged') is True and (row.get('mutating_calls') or {}).get('issued')==0
    return {
        'compose renders as root with the fixed environment (no HOME) and the override on standard input':receipt.get('status')==COMPLETE or receipt.get('phase_reached')=='EFFECTS',
        'the render says the bind of the data root as type, source and target, and a wrong target is refused before any effect':refused(mount,'WORKER_MOUNT_NOT_AS_SIGNED'),
        'a lock another process holds is waited for the signed seconds and refused before any effect':refused(busy,'DEPLOY_LOCK_BUSY') and 1.5<=busy.get('seconds',0)<=10,
        'the run completes':(receipt.get('status'),receipt.get('outcome'),receipt.get('code'))==(COMPLETE,'ACTIVATE_WORKER_RECREATED_AND_VERIFIED',None),
        'the override written with the default separators of json.dumps is a compose file':run.get('returncode')==0 and receipt.get('ledger_states')==['INSTALLED_DURABLE']*2,
        'the recreate replaces the worker and the old container is gone':facts.get('worker_is_new') is True and facts.get('old_container_gone') is True and facts.get('worker_listed_once') is True,
        'the new worker runs with restart count 0 at both readings, three seconds apart':facts.get('running') is True and facts.get('restarts')==0 and facts.get('second_check_passed') is True
            and facts.get('settle_pause_taken') is True and (facts.get('milliseconds_between_checks') or 0)>=3000,
        'the environment template says the five names present and equal on the new container':facts.get('environment_as_signed') is True,
        'every other container keeps its ID and name':facts.get('others_unchanged') is True and bool(before.get('other')) and before.get('other')==after.get('other'),
        'the environment file is the same object with the same bytes':facts.get('env_file_unchanged') is True and before.get('env_file')==after.get('env_file'),
        'the directory and the two files are root:root 0700 and 0600':after.get('live')==['dir 0 0 0700','compose.override.json file 0 0 0600 1','policy.json file 0 0 0600 1'],
        'the whole run fits the 60 s budget and the recreate its 30 s class':isinstance(receipt.get('elapsed_ms'),int) and receipt['elapsed_ms']<60000 and done.get('seconds',99)<60
            and isinstance(run.get('milliseconds'),int) and run['milliseconds']<30000,
        'the render from the files took no more than the allowance kept for it':isinstance(budget.get('render_from_the_files_milliseconds'),int)
            and budget['render_from_the_files_milliseconds']<=1000*budget.get('render_allowance_seconds',0),
        'the first render fits its class (15 s)':isinstance(budget.get('first_render_milliseconds'),int) and budget['first_render_milliseconds']<15000,
        'no value of the environment file reaches a receipt':all((shape.get('receipt') or {}).get('canary_in_receipt') is False for shape in (mount,busy,left,done,again)),
        'a worker that already carries the keys is refused before any effect':refused(again,'WORKER_ALREADY_CARRIES_THE_KEYS'),
        'a container under a temporary name of the worker is refused before any effect':refused(left,'WORKER_SERVICE_LEFTOVER_CONTAINER') and left.get('listed_before',0)>=3,
        # UA-5: python as PID 1 without a handler is not stopped by SIGTERM, so the recreate holds the engine's whole stop timeout (10 s), as on the host
        'the worker was stopped by the kill after the whole stop timeout, as the production worker is, and the recreate still fits its class':
            isinstance(run.get('milliseconds'),int) and 9500<=run['milliseconds']<30000,
        # UA-7, observed and recorded, not judged beyond this: the look fell inside the stop and shows one of the two orders
        'the interrupted recreate was looked at inside the stop of the old container and shows one of the two orders compose has used':
            cut.get('command_still_running_when_killed') is True and cut.get('order') in ('NEW_FIRST','OLD_FIRST'),
    }

def report(out):
    checks=expectations(out);return {'schema':SCHEMA,'shapes':out,'expectations':checks,'all_shapes_ran':all(row.get('ok') for row in out.values()),'all_expectations_met':all(checks.values())}

def plan_of(k6a,f,rows,paths,image,project,**changes):
    """The request plan, built from the tree as a binder would copy it from a read-only receipt."""
    data,deploy=paths
    plan={'data_root':data,'live_parent':rows(data+'/r2d2-v2-live'),'directory_name':changes.get('directory_name',k6a.LEAF),'policy':k6a.policy_member(),
          'override_name':k6a.OVERRIDE_NAME,
          'release':{'parent':rows(data),'directory_name':k6a.RELEASE_LEAF,'file_name':k6a.RELEASE_NAME,'sha256':f.sha(k6a.RELEASE),'bytes':len(k6a.RELEASE)},
          'worker':{'image_id':image,'mount_target':changes.get('mount_target',k6a.TARGET)},
          'compose':{'project':project,'env_file':deploy+'/.env','files':[deploy+'/'+project+'/compose.yml']},
          'deploy_directory':rows(deploy),'lock':{'directory':rows(deploy+'/runtime/security'),'wait_seconds':changes.get('wait_seconds',20)}}
    return plan

def emulated():
    """--self-test: the same collection on the emulated host."""
    import family as f
    import hostemu
    import k6a
    k=k6a.load();host=k6a.world(k);budget=[None]
    def make(**changes):
        plan=plan_of(k6a,f,lambda path:hostemu.rows(host,path),(hostemu.DATA,hostemu.DEPLOY),hostemu.BACKEND,hostemu.PROJECT,**changes)
        plan['evidence_boot_id_sha256']=f.BOOT_SHA;return f.Docs(k,plan)
    def run(docs):
        clock=f.Budget(docs.now,0.1);clock.cost(1.0,'config').cost(12.0,'up')
        previous=host.hook;clock.attach(host)
        try:receipt=docs.run(host,**clock.options())
        finally:host.hook=previous
        host.lock_holder.clear();host.lock_released_after=None;receipt['_emulated']=True;return receipt
    def hold(seconds):host.lock_holder[k6a.LOCK]='EX'
    def inspect():
        live=host.tree.get(k6a.LIVE);env=host.tree.get(hostemu.ENV_FILE)
        def line(name,node):return ('%s %s %d %d %04o'%(name,node.kind,node.uid,node.gid,node.mode)).strip()+('' if node.kind=='dir' else ' %d'%node.nlink)
        return {'live':None if live is None else [line('',live)]+[line(name,node) for name,node in sorted(live.children.items())],
                'second':host.tree.get(k6a.LIVE_PARENT+'/2026-10-05-second') is not None,
                'other':sorted((item['Name'],item['Id']) for item in host.docker.containers if item['Name']!='/'+hostemu.WORKER),
                'worker':k6a.worker(host)['Id'],'env_file':(env.ino,env.mtime,len(env.content))}
    def leftover(present):
        if present:host.docker.containers.append(k6a.service_container(TEMPORARY+hostemu.WORKER))
        else:host.docker.containers=[item for item in host.docker.containers if item['Name']!='/'+TEMPORARY+hostemu.WORKER]
    def interrupt():
        """No engine here: the rows the order NEW_FIRST would show, so that view() and order_of() run. Nothing is observed."""
        name=hostemu.PROJECT+'-probe-1';old,new='a'*64,'b'*64;both=[(name,old,'running'),(old[:12]+'_'+name,new,'created')]
        return {'emulated':True,'name':name,'old':[old],'before':[(name,old,'running')],'during_the_stop':both,'right_after_the_kill':both,
                'twelve_seconds_later':[(name,old,'exited'),(old[:12]+'_'+name,new,'created')],'running_when_killed':True,'seconds':3.0}
    return make,run,hold,inspect,leftover,interrupt

def real(image,work,project,core_tests):
    sys.path.insert(0,core_tests);sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
    import subprocess
    from datetime import timedelta
    import family as f
    import k6a
    k=k6a.load();m=k.m;native=m.Native();gate=lambda:55.0;data,deploy=work+'/data',work+'/deploy'
    def rows(path):
        found=[];m.Pinned(native,m.descend(native,path,gate,found),rows=found).close();return found
    def make(**changes):
        plan=plan_of(k6a,f,rows,(data,deploy),image,project,**changes)
        plan['evidence_boot_id_sha256']=m.boot_id_sha256(native,gate);return f.Docs(k,plan)
    def run(docs):
        start=time.monotonic()
        return docs.run(None,clock=lambda:docs.now+timedelta(seconds=time.monotonic()-start),monotonic=time.monotonic,executor_uid=os.geteuid)
    def hold(seconds):
        subprocess.Popen(['/usr/bin/flock','-x',deploy+'/runtime/security/deployment.lock','/bin/sleep',str(seconds)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        time.sleep(1)
    def inspect():
        live=data+'/r2d2-v2-live/'+k6a.LEAF
        def line(name,path):
            info=os.lstat(path);kind='dir' if os.path.isdir(path) and not os.path.islink(path) else 'file' if os.path.isfile(path) and not os.path.islink(path) else 'other'
            return ('%s %s %d %d %04o'%(name,kind,info.st_uid,info.st_gid,info.st_mode&0o7777)).strip()+('' if kind=='dir' else ' %d'%info.st_nlink)
        listed=subprocess.run(['/usr/bin/docker','ps','-a','--no-trunc','--format','{{.Names}} {{.ID}}'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL).stdout.decode().split('\n')
        pairs=sorted(tuple(item.split(' ',1)) for item in listed if item);name='%s-r2d2-worker-1'%project;env=os.lstat(deploy+'/.env')
        return {'live':None if not os.path.lexists(live) else [line('',live)]+[line(item,live+'/'+item) for item in sorted(os.listdir(live)) if not item.startswith('policy.json.')],
                'second':os.path.lexists(data+'/r2d2-v2-live/2026-10-05-second'),'other':[pair for pair in pairs if pair[0]!=name],
                'worker':[pair[1] for pair in pairs if pair[0]==name],'env_file':(env.st_ino,env.st_mtime_ns,env.st_size)}
    def docker(*words):
        done=subprocess.run(['/usr/bin/docker']+list(words),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        if done.returncode:raise RuntimeError('docker %s: exit %d'%(words[0],done.returncode))
        return done.stdout.decode()
    def leftover(present):
        name=TEMPORARY+'%s-r2d2-worker-1'%project
        if present:docker('create','--pull','never','--name',name,image,'true')          # created, never started: what the first call of a recreate leaves
        else:docker('rm','-f',name)
    def interrupt():
        """`up --force-recreate` of the third service, started as the runner of the core starts a command (its own
        session, the fixed environment of the family, the directory "/"), killed with its group after 3 s."""
        import signal
        name='%s-probe-1'%project
        def rows():
            listed=docker('ps','-a','--no-trunc','--format','{{.Names}} {{.ID}} {{.State}}').split('\n')
            return sorted(tuple(item.split(' ')) for item in listed if item and item.split(' ')[0].endswith(name))
        before=rows();old=[row[1] for row in before if row[0]==name];started=time.monotonic()
        process=subprocess.Popen(['/usr/bin/docker','compose','--project-name',project,'--env-file',deploy+'/.env','-f',deploy+'/'+project+'/compose.yml',
                                  'up','-d','--no-deps','--no-build','--pull','never','--force-recreate','probe'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,env=dict(m.COMMAND_ENVIRONMENT,C3PO_BUILD_SHA=m.EPOCH_REVISION),cwd=m.COMMAND_DIRECTORY,start_new_session=True)
        time.sleep(3);during=rows();running=process.poll() is None
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait();seconds=round(time.monotonic()-started,2);at_once=rows();time.sleep(12);later=rows()
        return {'name':name,'old':old,'before':before,'during_the_stop':during,'right_after_the_kill':at_once,'twelve_seconds_later':later,
                'running_when_killed':running,'seconds':seconds}
    return make,run,hold,inspect,leftover,interrupt

# The worker and the third service are stopped as the production worker is: python as PID 1 with no SIGTERM handler,
# no init and no stop_grace_period (c3po/compose.yml:138-176 at the release; no signal handler in app/r2d2_worker.py),
# so every stop waits the engine's whole timeout (10 s) and ends by the kill. `api` is only ever stopped by the cleanup.
COMPOSE='''services:
  r2d2-worker:
    image: %(reference)s
    command: ["python","-c","import time; time.sleep(3600)"]
    restart: unless-stopped
    env_file:
      - ../.env
    environment:
      C3PO_BUILD_SHA: ${C3PO_BUILD_SHA:-development}
      C3PO_SERVICE_NAME: r2d2-worker
    volumes:
      - ${C3PO_DAY_D_DATA_MOUNT_SOURCE:-c3po_day_d_data}:/app/day-d-data
  api:
    image: %(reference)s
    command: ["python","-c","import time; time.sleep(3600)"]
    stop_grace_period: 1s
    environment:
      C3PO_BUILD_SHA: ${C3PO_BUILD_SHA:-development}
  probe:
    image: %(reference)s
    command: ["python","-c","import time; time.sleep(3600)"]
    environment:
      C3PO_BUILD_SHA: ${C3PO_BUILD_SHA:-development}
volumes:
  c3po_day_d_data:
'''
def prepare(work,reference,project,core_tests):
    """The deploy tree and the data root of the shapes, as root: the layout of the host (c3po-pipeline.yml:631-658,
    743-746; c3po/compose.yml:138-176) with synthetic content. The release is the synthetic one of the tests."""
    sys.path.insert(0,core_tests);sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
    import k6a
    os.umask(0o022);assert os.geteuid()==0 and os.listdir(work)==[] and os.lstat(work).st_uid==0
    def put(path,raw,mode):
        fd=os.open(os.path.join(work,path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode);os.write(fd,raw);os.fchmod(fd,mode);os.close(fd)
    for path,mode in (('deploy',0o755),('deploy/'+project,0o755),('deploy/runtime',0o755),('deploy/runtime/security',0o755),('data',0o755),('data/r2d2-v2-live',0o755),
                      ('data/'+k6a.RELEASE_LEAF,0o700)):
        os.mkdir(os.path.join(work,path),mode);os.chmod(os.path.join(work,path),mode)
    put('deploy/.env',('C3PO_DAY_D_DATA_MOUNT_SOURCE=%s/data\nC3PO_DB_PASSWORD=%s\n'%(work,CANARY)).encode(),0o600)
    put('deploy/.deploy-version',b'dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858\n',0o644)
    put('deploy/%s/compose.yml'%project,(COMPOSE%{'reference':reference}).encode(),0o644)
    put('deploy/runtime/security/deployment.lock',b'',0o644);put('data/.r2d2-v2-pinned',b'',0o600)
    put('data/%s/%s'%(k6a.RELEASE_LEAF,k6a.RELEASE_NAME),k6a.RELEASE,0o600)
    os.chmod(work,0o755);return 0

def main(arguments):
    if arguments[:1]==['--prepare'] and len(arguments)==5:return prepare(*arguments[1:])
    if arguments==['--self-test']:
        result=report(collect(*emulated()))
    else:
        if len(arguments)!=4:
            print(__doc__);return 1
        if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'):
            print('REFUSED: a throwaway GitHub-hosted Linux runner, as root, with HOSTOPS_THROWAWAY_RUNNER=yes',file=sys.stderr);return 1
        result=report(collect(*real(*arguments)))
    print(json.dumps(result,indent=1,sort_keys=True,default=str));return 0 if result['all_shapes_ran'] and result['all_expectations_met'] else 3 if result['all_shapes_ran'] else 2

if __name__=='__main__':
    if sys.argv[1:]==['--self-test']:
        sys.path.insert(0,os.environ.get('HOSTOPS02_TEST_CORE_TESTS') or os.path.join(os.path.dirname(HERE),'..','core','tests'));sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
    raise SystemExit(main(sys.argv[1:]))
