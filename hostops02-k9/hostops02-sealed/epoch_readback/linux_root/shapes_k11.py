"""The command shapes of K11 (epoch readback) that never ran on any Linux host, executed with the operation's own
command table, helpers, runner and Native on a real engine. DESIGN.md section 10: K11-U1 (--name), K11-U2 (a read-only
bind under --read-only read with the worker's reader), K11-U3 (the alarm ends the interpreter under --init), K11-U5
(systemctl show with the ten properties), and, with them, the core's U2 for this operation's argv.

The image of a throwaway runner is a plain Python image: it has no /app. The stand-in for the application package
(tests/k11.py, FAKE) is therefore bound read-only at /app, so that the pinned snippet runs to its end unchanged. What
this proves about the application itself is nothing: that is the Sunday dry run. What it proves is the engine: the
argv, standard input, the bind, the reader's view of a 0600 file through it, the alarm, the name.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root. NEVER the production host: it creates directories under
<work directory> and runs containers. It refuses to run anywhere else: Linux, effective uid 0,
HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted are all required. NOT RUN by the author: no Linux and
no docker were available offline. --self-test runs the same collection against the emulated engine; it proves that
this script is coherent with the source, and nothing about a real engine.

usage: sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -B linux_root/shapes_k11.py <image ID> <work directory>
       /usr/bin/python3 -B linux_root/shapes_k11.py --self-test
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when all ran and an
expectation is not met; 1 for a refusal. The alarm shape takes thirty seconds on a real engine.
"""
import json
import os
import sys
import time

HERE=os.path.dirname(os.path.abspath(__file__))
OPERATION=os.path.dirname(HERE)
sys.path.insert(0,os.path.join(OPERATION,'..','core','tests'));sys.path.insert(0,os.path.join(OPERATION,'tests'))
import family as f
import hostemu
import k11

SCHEMA='HOSTOPS02_K11_LINUX_ROOT_SHAPES_V1'
REQUEST='7'*64
GO={'request_sha256':REQUEST,'go_sha256':'8'*64}
APP='/app'

def plan_of(mode,work,image_id,probe=None):
    """The members frame_of, verify_line and Readback read; never authenticated here (the shapes are not a dispatch).
    probe: the directory the full dry run binds read-only and reads one file of (PRE)."""
    pre=mode=='PRE'
    return {'mode':mode,'revision':k11.REVISION,'package_sha256':k11.PACKAGE,'image':{'reference':'unused','image_id':image_id},
            'release':{'sha256':f.sha(k11.RELEASE),'bytes':len(k11.RELEASE),'content_b64':k11.b64(k11.RELEASE) if pre else None,
                       'parent':{'path':work,'rows':None,'open_root':None},'directory_name':'release','file_name':k11.RELEASE_FILE,
                       'container_target':None if pre else k11.TARGET,'directory_entries':None if pre else 1},
            'policy':{'sha256':f.sha(k11.POLICY),'bytes':len(k11.POLICY),'content_b64':k11.b64(k11.POLICY),'valid_at':list(k11.VALID_AT)},
            'render':None,'docker_config':None,'evidence_boot_id_sha256':'9'*64,'dry_run':'REDUCED' if pre else None,'live':None,'limits':None,
            'bind_probe':None if probe is None else {'directory':{'path':probe,'rows':None,'open_root':None},'file_name':k11.RELEASE_FILE,'container_target':k11.PROBE_TARGET}}

def collect(m,host,image_id,work,gate=lambda:55.0):
    """Each shape with the source's own table and helpers. Returns {shape: result}; a failure is a row, never an exception."""
    out={};commands=m.Commands(host,gate)
    def shape(label,action):
        try:out[label]=dict(action(),ok=True)
        except Exception as error:
            out[label]={'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}
    def app(name):return {'source':work+'/'+name,'target':APP,'read_only':True}
    def run(mode,mounts,name,tree='app',probe=None):
        plan=plan_of(mode,work,image_id,probe);started=time.monotonic()
        result=m.container_run(commands,'verify',image_id,[app(tree)]+mounts,m.VERIFY_COMMAND,m.frame_of(plan,REQUEST),container_name=name)
        seconds=round(time.monotonic()-started,2)
        line=m.verify_line(result['output'],result['returncode'],plan,REQUEST) if result['returned'] else None
        listed=[row['name'] for row in m.container_list(commands)]
        return plan,result,line,seconds,name in listed
    def pre():
        plan,result,line,seconds,left=run('PRE',[],m.CONTAINER_PREFIX+'pre0000000000000')
        return {'returned':result['returned'],'returncode':result['returncode'],'seconds':seconds,'left_behind':left,'line':line and line['status'],
                'verified':bool(line and line['status']=='DONE' and line['release']['verified'] and line['release']['source']=='STDIN'),
                'policy_accepted':bool(line and line['status']=='DONE' and all(item['valid'] for item in line['policy']['controller_at']) and line['policy']['assembler']['valid'])}
    def probe(directory,name):
        """The container of the full dry run: the release on standard input AND one read-only bind of a private
        directory, one 0600 file of it read by the reader of the worker (what Sunday's request signs as bind_probe)."""
        def action():
            source=work+'/'+directory;plan,result,line,seconds,left=run('PRE',m.mounts_of(plan_of('PRE',work,image_id,source)),m.CONTAINER_PREFIX+name,probe=source)
            done=bool(line and line['status']=='DONE')
            return {'returned':result['returned'],'returncode':result['returncode'],'seconds':seconds,'left_behind':left,'verified':done and line['release']['verified'],
                    'probe':line['probe'] if done else None}
        return action
    def post(directory,name):
        def action():
            plan,result,line,seconds,left=run('POST',[{'source':work+'/'+directory,'target':k11.TARGET,'read_only':True}],m.CONTAINER_PREFIX+name)
            release=line['release'] if line and line['status']=='DONE' else {}
            return {'returned':result['returned'],'returncode':result['returncode'],'seconds':seconds,'left_behind':left,'read':release.get('read'),
                    'verified':release.get('verified'),'code':release.get('code'),'source':release.get('source')}
        return action
    def alarm():
        plan,result,line,seconds,left=run('PRE',[],m.CONTAINER_PREFIX+'alarm00000000000','app-hang')
        return {'returned':result['returned'],'returncode':result['returncode'],'seconds':seconds,'left_behind':left,'code':result['code']}
    def unit():
        reader=m.Readback(plan_of('PRE',work,image_id),host,gate,commands,GO,time.monotonic);item=reader.unit({'name':'docker.service','expected':None})
        return {'properties':sorted(item['properties']),'active':item['properties']['ActiveState'],'load':item['properties']['LoadState']}
    shape('pre_release_on_standard_input',pre);shape('post_read_only_bind',post('release','post000000000000'))
    shape('pre_with_the_probe_of_the_bind',probe('release','probe00000000000'))
    shape('post_file_the_reader_refuses',post('release-open','open000000000000'));shape('alarm_ends_a_hanging_interpreter',alarm);shape('unit_show',unit)
    return out

def expectations(out):
    def get(label,key):return out.get(label,{}).get(key)
    return {'the PRE container returns 0 with a verified release and an accepted policy':get('pre_release_on_standard_input','returncode')==0 and get('pre_release_on_standard_input','verified') is True
                and get('pre_release_on_standard_input','policy_accepted') is True,
            'a named container is gone when its run has returned (K11-U1)':all(get(label,'left_behind') is False for label in ('pre_release_on_standard_input','post_read_only_bind','pre_with_the_probe_of_the_bind','alarm_ends_a_hanging_interpreter')),
            'the installed file is read through a read-only bind under a read-only root (K11-U2)':(get('post_read_only_bind','read'),get('post_read_only_bind','verified'),get('post_read_only_bind','source'))==(True,True,'FILE'),
            'the full dry run reads one private file through its read-only bind and verifies the release on standard input':
                (get('pre_with_the_probe_of_the_bind','returncode'),get('pre_with_the_probe_of_the_bind','verified'),get('pre_with_the_probe_of_the_bind','probe'))==(0,True,{'valid':True,'code':None}),
            'the reader refuses a file group or other can read, through the bind':(get('post_file_the_reader_refuses','read'),get('post_file_the_reader_refuses','code'))==(False,'RELEASE_FILE_NOT_PRIVATE_OR_INVALID'),
            'the alarm ends the interpreter and the run returns with the status of the signal (K11-U3)':get('alarm_ends_a_hanging_interpreter','returned') is True and get('alarm_ends_a_hanging_interpreter','returncode')==128+14,
            'systemctl show prints the ten properties for a loaded unit (K11-U5)':get('unit_show','properties')==sorted(['Id','LoadState','ActiveState','SubState','UnitFileState','FragmentPath','DropInPaths','WantedBy','RequiredBy','TriggeredBy'])}

def report(out):
    met=expectations(out);ran=all(row.get('ok') for row in out.values())
    return {'schema':SCHEMA,'shapes':out,'expectations':met,'every_shape_ran':ran,'every_expectation_met':all(met.values())},(0 if ran and all(met.values()) else 3 if ran else 2)

def prepare(work):
    """The directories of the shapes, created on the throwaway runner as root: the stand-in package twice (once with
    the knob that makes it hang), and an installed release twice (0600, and 0644 for the reader to refuse)."""
    for name,knobs in (('app',{}),('app-hang',{'hang':True})):
        os.makedirs(work+'/'+name+'/app',mode=0o755)
        for item,text in k11.FAKE.items():
            with open(work+'/'+name+'/app/'+item,'w') as stream:stream.write(text)
        with open(work+'/'+name+'/app/knobs.json','w') as stream:stream.write(json.dumps(knobs))
    for name,mode in (('release',0o600),('release-open',0o644)):
        os.mkdir(work+'/'+name,0o700);path=work+'/'+name+'/'+k11.RELEASE_FILE
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,k11.RELEASE);os.close(fd);os.chmod(path,mode)

def emulated(k,work):
    """The emulated engine for --self-test: the stand-in package is what k11.Container gives the snippet; the alarm of
    the hanging one is scaled to one second."""
    host=f.world(k);quick=k11.Container();hanging=k11.Container(k11.fake_tree(hang=True),alarm_scale=1)
    for name in ('app','app-hang'):host.tree.add(work+'/'+name)
    for name,mode in (('release',0o600),('release-open',0o644)):
        host.tree.add(work+'/'+name,mode=0o700);host.tree.add(work+'/'+name+'/'+k11.RELEASE_FILE,kind='file',mode=mode,content=k11.RELEASE)
    def on_run(call):
        source=[mount['source'] for mount in call.mounts if mount['target']==APP][0]
        call.mounts=[mount for mount in call.mounts if mount['target']!=APP];return (hanging if source.endswith('-hang') else quick)(call)
    host.docker.on_run=on_run
    return host

def main(arguments):
    k=f.load(OPERATION)
    if arguments==['--self-test']:
        work='/srv/k11-shapes';result,code=report(collect(k.m,emulated(k,work),hostemu.BACKEND,work))
        sys.stdout.write(json.dumps(dict(result,self_test_on_the_emulation=True),sort_keys=True)+'\n');return code
    if len(arguments)!=2:
        sys.stdout.write(__doc__);return 1
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'):
        sys.stdout.write('REFUSED: a throwaway GitHub-hosted Linux runner as root only\n');return 1
    image_id,work=arguments
    if not (os.path.isdir(work) and not os.listdir(work) and os.stat(work).st_uid==0):
        sys.stdout.write('REFUSED: the work directory must exist, be root-owned and empty\n');return 1
    prepare(work);result,code=report(collect(k.m,k.m.Native(),image_id,work,gate=lambda:55.0))
    sys.stdout.write(json.dumps(result,sort_keys=True)+'\n');return code

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
