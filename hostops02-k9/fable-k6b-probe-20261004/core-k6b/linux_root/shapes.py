"""The command shapes of the HOSTOPS02 core that never ran on any Linux host, executed with the demonstration sources'
own command tables, helpers, runner and Native on a real engine: an attached `docker run` with the fixed prefix (a
read-only bind, a read-write bind, bytes on standard input, an empty DOCKER_CONFIG), the environment template of
container_environment, `docker compose` with an explicit file list and the fixed environment (render with the override
on standard input, render from files, the recreate of one service), and the flock of the deployment lock on a read-only
descriptor while another process holds it. CORE.md section 10, items U2 to U7.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root (run.sh prepares it). NEVER the production host: it creates
containers and a compose project. It refuses to run anywhere else: Linux, effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes
and RUNNER_ENVIRONMENT=github-hosted are all required. NOT RUN by the author of the core: no Linux and no docker were
available offline. --self-test runs the same collection against the emulated engine of tests/hostemu.py; it proves that
this script is coherent with the sources, and nothing about a real engine.

usage: sudo -n env ... /usr/bin/python3 -I -B linux_root/shapes.py <image ID> <work directory>
           <image ID>        the local ID of an image that has `python` (run.sh pulls one and tags it c3po/backend:hostops02-ci-probe)
           <work directory>  prepared by run.sh, root:root 0700: bound/ (0700, one file), written/ (0700, empty), docker-cli/ (0700, empty),
                             project/ (.env, compose.yml, override.json, deployment.lock)
           prints one JSON object: every shape, and the expectations the sources rely on, each as a boolean
       /usr/bin/python3 -B linux_root/shapes.py --self-test
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when all ran and an
expectation is not met; 1 for a refusal.
"""
import json
import os
import sys
import time

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
import demos
import family as f
import hostemu

SCHEMA='HOSTOPS02_CORE_LINUX_ROOT_SHAPES_V1'
PROJECT='hostops02ci'
SERVICE='r2d2-worker'
REFERENCE='c3po/backend:hostops02-ci-probe'
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
KEYS={'C3PO_R2D2_V2_LIVE_POLICY_FILE':'/app/day-d-data/live/policy.json','C3PO_R2D2_V2_LIVE_POLICY_SHA':'5'*64}
# What runs inside the containers. Standard library only; one JSON line each.
READ_SCRIPT=b'''import json,os,sys
root=sys.argv[1];out={'argv':sys.argv[1:],'uid':os.getuid(),'entries':sorted(os.listdir(root)),'environment_names':sorted(os.environ)}
info=os.stat(root);out['device'],out['inode']=info.st_dev,info.st_ino
for name,path in (('write_in_the_bind',os.path.join(root,'made-by-the-container')),('write_in_the_root','/made-by-the-container')):
    try:
        os.close(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600));out[name]='CREATED'
    except OSError as error:out[name]=error.errno
print(json.dumps(out,sort_keys=True))
'''
WRITE_SCRIPT=b'''import json,os,sys
root=sys.argv[1];fd=os.open(os.path.join(root,'made.json'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,b'{}');os.fsync(fd);os.close(fd)
info=os.stat(root);print(json.dumps({'created':'made.json','device':info.st_dev,'inode':info.st_ino,'status':'DONE'},sort_keys=True))
'''
EROFS=30

def collect(read,write,read_host,write_host,image_id,work,count,hold):
    """Each shape with the sources' own tables and helpers. Returns {shape: result}; a failure is a row, never an exception."""
    gate=lambda:55.0;out={};r=read.Commands(read_host,gate);w=write.Commands(write_host,gate);project=work+'/project'
    compose=(PROJECT,project+'/.env',[project+'/compose.yml']);name='%s-%s-1'%(PROJECT,SERVICE)
    def shape(label,action):
        try:out[label]=dict(action(),ok=True)
        except Exception as error:
            out[label]={'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}
    def pinned(module,host,path):
        rows=[];fd=module.descend(host,path,gate,rows);return module.Pinned(host,fd,rows=rows)
    def image():
        by_id=read.image_facts(r,image_id);by_reference=read.image_facts(r,REFERENCE)
        return {'id_equal':by_id['id']==image_id,'reference_resolves_to_the_id':by_reference['id']==image_id and by_reference['reference_among_repo_tags']}
    def run_read_only():
        before=count(work+'/docker-cli');directory=pinned(read,read_host,work+'/bound')
        try:
            started=time.monotonic()
            result=read.container_run(r,'verify',image_id,[{'source':work+'/bound','target':'/hostops02-bound','read_only':True}],
                                      ['python','-I','-B','-','/hostops02-bound'],READ_SCRIPT,docker_config=work+'/docker-cli')
            seconds=round(time.monotonic()-started,2);line=read.single_line(result['output']) if result['returned'] and result['returncode']==0 else {}
            return {'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],'seconds':seconds,'line':line,
                    'host_identity_of_the_bind':list(directory.identity[:2]),'entries_of_the_bind_after':count(work+'/bound'),
                    'docker_config_entries_before':before,'docker_config_entries_after':count(work+'/docker-cli')}
        finally:directory.close()
    def run_read_write():
        state=write.Effects();started=time.monotonic()
        result=write.container_effect(state,w,'script',image_id,[{'source':work+'/written','target':'/hostops02-written','read_only':False}],
                                      ['python','-I','-B','-','/hostops02-written'],WRITE_SCRIPT)
        seconds=round(time.monotonic()-started,2);line=write.single_line(result['output']) if result['returned'] and result['returncode']==0 else {}
        made=write.probe(write_host,work+'/written/made.json',gate);state.done() if result['returned'] else None
        return {'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],'seconds':seconds,'line':line,
                'made':{key:made.get(key) for key in ('exists','type','uid','gid','mode_octal','links')},'counts':state.counts()}
    def render():
        override=f.canonical({'services':{SERVICE:{'environment':dict(KEYS)}}});started=time.monotonic()
        with_input=write.compose_service(write.compose_render(w,'render',*compose,REVISION,override=override),SERVICE)
        middle=round(time.monotonic()-started,2)
        raw=w.output('render_files',*write.compose_arguments(PROJECT,project+'/.env',[project+'/compose.yml',project+'/override.json']),variables={'C3PO_BUILD_SHA':REVISION})
        from_files=write.compose_service(write.strict(raw,1048576),SERVICE)
        def facts(service):
            environment=service['environment']
            return {'build_revision_is_the_variable':environment.get('C3PO_BUILD_SHA')==REVISION,'value_of_the_environment_file_interpolated':environment.get('FROM_ENV_FILE')=='from-env-file',
                    'override_names_equal':all(environment.get(key)==value for key,value in KEYS.items()),'image_reference':service['image']}
        return {'standard_input':facts(with_input),'files':facts(from_files),'seconds_standard_input':middle,'output_bytes':len(raw)}
    def recreate():
        state=write.Effects();files=[project+'/compose.yml',project+'/override.json'];rows=[]
        for attempt in range(2):                                   # the first creates the container, the second replaces it
            started=time.monotonic();result=write.compose_up(state,w,'recreate',PROJECT,project+'/.env',files,REVISION)
            seconds=round(time.monotonic()-started,2)
            if result['returned']:state.done()
            facts=write.container_facts(w,name) if result['returned'] and result['returncode']==0 else None
            rows.append({'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],'seconds':seconds,
                         'container':None if facts is None else {key:facts[key] for key in ('id','running','state','restarts','image_id','health')}})
        listed=[row for row in write.container_list(w) if row['name']==name]
        return {'attempts':rows,'listed_once':len(listed)==1,'listed_id_is_the_inspected_one':bool(listed) and rows[-1]['container'] is not None and listed[0]['id']==rows[-1]['container']['id'],
                'counts':state.counts()}
    def environment():
        target=write.container_facts(w,name)['id']
        expected=dict(KEYS,C3PO_BUILD_SHA=REVISION,FROM_ENV_FILE='from-env-file',ABSENT_NAME='x',C3PO_BUILD=REVISION)
        expected['C3PO_R2D2_V2_LIVE_POLICY_SHA']='6'*64                      # present with another value
        return {'names':write.container_environment(w,target,expected)}
    def lock():
        directory=pinned(write,write_host,project)
        try:
            hold(project+'/deployment.lock')                         # another process takes the lock exclusively for a few seconds
            fd=write.open_lock(write_host,'deployment.lock',directory,gate);first=write.probe_lock(write_host,fd)
            started=time.monotonic();attempts=write.acquire_lock(write_host,fd,gate,20,10);waited=round(time.monotonic()-started,2)
            named=write.lock_still_named(write_host,'deployment.lock',directory,fd);write.release_lock(write_host,fd)
            again=write.open_lock(write_host,'deployment.lock',directory,gate);after=write.probe_lock(write_host,again);write_host.close(again)
            return {'probe_while_another_process_holds_it':first,'attempts':attempts,'seconds_waited':waited,'still_named':named,'probe_after_release':after}
        finally:directory.close()
    shape('image_inspect_by_id_and_reference',image);shape('attached_run_read_only_bind_standard_input_empty_docker_config',run_read_only)
    shape('attached_run_read_write_bind',run_read_write);shape('compose_render_standard_input_and_files',render);shape('compose_recreate_twice',recreate)
    shape('container_environment_template',environment);shape('deployment_lock_read_only_descriptor',lock)
    return out

def expectations(out):
    """What the sources rely on, read from the shapes: one boolean per statement, False when its shape did not run."""
    image=out.get('image_inspect_by_id_and_reference',{});ro=out.get('attached_run_read_only_bind_standard_input_empty_docker_config',{});line=ro.get('line') or {}
    rw=out.get('attached_run_read_write_bind',{});render=out.get('compose_render_standard_input_and_files',{});up=out.get('compose_recreate_twice',{})
    names=(out.get('container_environment_template',{}).get('names') or {});lock=out.get('deployment_lock_read_only_descriptor',{})
    attempts=up.get('attempts') or [{},{}];first,second=(attempts+[{},{}])[:2];containers=[row.get('container') or {} for row in (first,second)]
    return {
        'U2 image resolves by ID and by reference to the same ID':image.get('id_equal') is True and image.get('reference_resolves_to_the_id') is True,
        'U2 the attached run with the fixed prefix returns 0 and one JSON line':ro.get('returncode')==0 and bool(line),
        'U2 standard input reached python and the arguments are the signed ones':line.get('argv')==['/hostops02-bound'],
        'U2 the container runs as uid 0':line.get('uid')==0,
        'U2 the read-only bind refuses a creation with EROFS':line.get('write_in_the_bind')==EROFS and ro.get('entries_of_the_bind_after')==1,
        'U2 the root filesystem of the container is read-only':line.get('write_in_the_root')==EROFS,
        'U2 the bind shows the host directory (device and inode equal)':[line.get('device'),line.get('inode')]==ro.get('host_identity_of_the_bind'),
        'U2 no variable of the host or of the CLI reaches the container':type(line.get('environment_names')) is list and not [name for name in line['environment_names'] if name.startswith(('DOCKER_','C3PO_'))],
        'U2 the docker CLI writes nothing into an empty DOCKER_CONFIG':ro.get('docker_config_entries_before')==0 and ro.get('docker_config_entries_after')==0,
        'U2 the attached run fits its class (20 s)':type(ro.get('seconds')) in (int,float) and ro['seconds']<20,
        'U2 a read-write bind lets the container create a root-owned 0600 file':rw.get('returncode')==0 and rw.get('made')=={'exists':True,'type':'file','uid':0,'gid':0,'mode_octal':'0600','links':1},
        'U4 compose renders with the fixed environment (no HOME) and the override on standard input':render.get('standard_input',{}).get('override_names_equal') is True,
        'U4 compose interpolates C3PO_BUILD_SHA from the variable of the call':render.get('standard_input',{}).get('build_revision_is_the_variable') is True and render.get('files',{}).get('build_revision_is_the_variable') is True,
        'U4 compose reads the named environment file':render.get('standard_input',{}).get('value_of_the_environment_file_interpolated') is True,
        'U4 compose renders the same from an override file':render.get('files',{}).get('override_names_equal') is True,
        'U6 the render fits its class (15 s, 1 MiB)':type(render.get('seconds_standard_input')) in (int,float) and render['seconds_standard_input']<15 and 0<render.get('output_bytes',0)<=1048576,
        'U4 compose up of one service returns 0 and the container runs with restart count 0':all(row.get('returncode')==0 for row in (first,second)) and all(c.get('running') is True and c.get('restarts')==0 for c in containers),
        'U7 the forced recreate replaces the container and fits its class (30 s)':bool(containers[0].get('id')) and bool(containers[1].get('id')) and containers[0]['id']!=containers[1]['id']
            and all(type(row.get('seconds')) in (int,float) and row['seconds']<30 for row in (first,second)),
        'U4 the project holds exactly one container of the service, the inspected one':up.get('listed_once') is True and up.get('listed_id_is_the_inspected_one') is True,
        'U3 the template says present and equal for a name with the signed value':all(names.get(key)=={'present':True,'equal':True} for key in ('C3PO_BUILD_SHA','FROM_ENV_FILE','C3PO_R2D2_V2_LIVE_POLICY_FILE')),
        'U3 the template says present and not equal for another value':names.get('C3PO_R2D2_V2_LIVE_POLICY_SHA')=={'present':True,'equal':False},
        'U3 the template says absent for a name the container lacks, and for a prefix of a name':names.get('ABSENT_NAME')=={'present':False,'equal':False} and names.get('C3PO_BUILD')=={'present':False,'equal':False},
        'U5 a lock another process holds exclusively is seen busy through a read-only descriptor':lock.get('probe_while_another_process_holds_it')=='BUSY',
        'U5 the exclusive lock is obtained after the holder lets go, within the bounded wait':type(lock.get('attempts')) is int and lock['attempts']>1 and lock.get('seconds_waited',99)<20 and lock.get('still_named') is True,
        'U5 the lock is free again after the release':lock.get('probe_after_release')=='FREE',
    }

def report(out):
    checks=expectations(out);return {'schema':SCHEMA,'shapes':out,'expectations':checks,'all_shapes_ran':all(row.get('ok') for row in out.values()),'all_expectations_met':all(checks.values())}

def emulated(work):
    """The emulated engine and host for --self-test: what the two scripts and the lock holder do, said in Python."""
    read=f.load(demos.READ);write=f.load(demos.WRITE);host=hostemu.world();image=hostemu.BACKEND
    host.docker.images[0]['RepoTags'].append(REFERENCE)
    for path in (work,work+'/bound',work+'/written',work+'/docker-cli',work+'/project'):host.tree.add(path,mode=0o700)
    host.tree.add(work+'/bound/one-file',kind='file',mode=0o600)
    for name,content in (('.env',b'MARKER=from-env-file\n'),('compose.yml',b'services: {}\n'),('override.json',f.canonical({'services':{SERVICE:{'environment':dict(KEYS)}}})),('deployment.lock',b'')):
        host.tree.add(work+'/project/'+name,kind='file',mode=0o644,content=content)
    base={'name':PROJECT,'services':{SERVICE:{'image':REFERENCE,'environment':{'C3PO_BUILD_SHA':REVISION,'FROM_ENV_FILE':'from-env-file'}}}}
    host.docker.compose=hostemu.FakeCompose(host.docker,PROJECT,work+'/project/.env',work+'/project/compose.yml',base)
    def behaviour(call):
        root=call.command[4];info=call.stat(root)
        if call.stdin==READ_SCRIPT:
            line={'argv':call.command[4:],'uid':0,'entries':call.listdir(root),'environment_names':['PATH'],'device':info.st_dev,'inode':info.st_ino}
            for name,path in (('write_in_the_bind',root+'/made-by-the-container'),('write_in_the_root','/made-by-the-container')):
                try:call.write(path,b'');line[name]='CREATED'
                except OSError as error:line[name]=error.errno
            return 0,f.canonical(line)+b'\n'
        assert call.stdin==WRITE_SCRIPT;call.write(root+'/made.json',b'{}')
        return 0,f.canonical({'created':'made.json','device':info.st_dev,'inode':info.st_ino,'status':'DONE'})+b'\n'
    host.docker.on_run=behaviour
    def hold(path):host.lock_holder[path]='EX';host.lock_released_after=4
    return read,write,f.wire(read,host),image,lambda path:len(host.tree.get(path).children),hold

def held_by_another_process(path):
    """flock(1) holds the lock exclusively for four seconds in a process of its own; this returns once it holds it."""
    import subprocess
    subprocess.Popen(['/usr/bin/flock','-x',path,'/bin/sleep','4'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    time.sleep(1)

def main(arguments):
    if arguments==['--self-test']:
        work='/var/tmp/hostops02-shapes';read,write,host,image,count,hold=emulated(work)
        result=report(collect(read.m,write.m,host,f.wire(write,host),image,work,count,hold))
        print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_shapes_ran'] and result['all_expectations_met'] else 3 if result['all_shapes_ran'] else 2
    if len(arguments)!=2:
        print(__doc__);return 1
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'):
        print('REFUSED: a throwaway GitHub-hosted Linux runner, as root, with HOSTOPS_THROWAWAY_RUNNER=yes',file=sys.stderr);return 1
    image,work=arguments;read=f.load(demos.READ).m;write=f.load(demos.WRITE).m
    result=report(collect(read,write,read.Native(),write.Native(),image,work,lambda path:len(os.listdir(path)),held_by_another_process))
    print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_shapes_ran'] and result['all_expectations_met'] else 3 if result['all_shapes_ran'] else 2

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
