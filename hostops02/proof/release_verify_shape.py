"""Release.verify of the release's OWN application code, in fresh containers of the backend image built from this
checkout with the repository's Dockerfile, on SYNTHETIC release and policy bytes. Driven with the command table,
helpers, runner and Native of the sealed epoch readback (K11): nothing of that operation is changed or copied here.

Why it exists beside epoch_readback/linux_root/shapes_k11.py: that script binds a stand-in package at /app, so it
proves the engine and nothing about the application. This one binds nothing at /app: the snippet imports the modules
the image carries (DESIGN.md section 10 of K11: K11-U4, "UNPROVEN in a fresh read-only container").

The documents are the ones of epoch_readback/tests/real_documents.py (sealed, run unchanged inside the image): every
pin is a repeated character and every reference says SYNTHETIC. Nothing here is a real release, consent or policy.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root. NEVER the production host: it creates directories under
<work directory> and runs containers. It refuses anywhere else: Linux, effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes
and RUNNER_ENVIRONMENT=github-hosted are all required. NOT RUN by its author on a real engine: no Linux and no docker
were available offline. --self-test runs the same collection on the emulated engine of the core with the release's
own modules run by the local interpreter; it proves that this script is coherent with the source and with the
application code, and nothing about a real engine or about the image.

usage: sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -B release_verify_shape.py <image ID> <work directory>
       python3 -B release_verify_shape.py --self-test <directory that holds the package app of the release>
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when all ran and an
expectation is not met; 1 for a refusal. One JSON object on standard output.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time

HERE=os.path.dirname(os.path.abspath(__file__))
FAMILY=os.path.dirname(HERE)
OPERATION=os.path.join(FAMILY,'epoch_readback')
DOCUMENTS=os.path.join(OPERATION,'tests','real_documents.py')
sys.path.insert(0,os.path.join(FAMILY,'core','tests'))
import family as f

SCHEMA='HOSTOPS02_PROOF_RELEASE_VERIFY_SHAPE_V1'
REVISION='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'          # the deployed release; the label the image must carry
PACKAGE='b5ce527a544ca0eb08f0718d83546d7b46f9e9774be8e4351afce212e72bdb84'       # the implementation package the three hands signed
REQUEST='7'*64
RELEASE_FILE='release.CERTIFIED.json'
TARGET='/c3po-epoch-release'
PROBE_TARGET='/c3po-bind-probe'
VALID_AT=['2026-10-05T08:45:00+00:00','2026-10-05T13:30:00+00:00','2026-10-09T19:59:59+00:00']
ACCEPTED={'read':True,'bytes_equal_signed':True,'verified':True,'code':None,'mode_certified':True,'epoch_equal':True,'first_session_equal':True,'ebar_bound':True}

def sha(raw):return hashlib.sha256(raw).hexdigest()
def b64(raw):return base64.b64encode(raw).decode('ascii')

def plan_of(mode,work,image_id,release,policy,revision=REVISION,probe=None):
    """The members frame_of, mounts_of and verify_line read. Never authenticated here: the shapes are not a dispatch."""
    pre=mode=='PRE'
    return {'mode':mode,'revision':revision,'package_sha256':PACKAGE,'image':{'reference':'unused','image_id':image_id},
            'release':{'sha256':sha(release),'bytes':len(release),'content_b64':b64(release) if pre else None,
                       'parent':{'path':work,'rows':None,'open_root':None},'directory_name':'release','file_name':RELEASE_FILE,
                       'container_target':None if pre else TARGET,'directory_entries':None if pre else 1},
            'policy':{'sha256':sha(policy),'bytes':len(policy),'content_b64':b64(policy),'valid_at':list(VALID_AT)},
            'render':None,'docker_config':None,'evidence_boot_id_sha256':'9'*64,'dry_run':'REDUCED' if pre else None,'live':None,'limits':None,
            'bind_probe':None if probe is None else {'directory':{'path':probe,'rows':None,'open_root':None},'file_name':RELEASE_FILE,'container_target':PROBE_TARGET}}

def collect(m,host,image_id,work,release,policy,gate=lambda:55.0):
    """Each shape with the source's own table and helpers. Returns {shape: result}; a failure is a row, never an exception."""
    out={};commands=m.Commands(host,gate)
    def shape(label,action):
        try:out[label]=dict(action(),ok=True)
        except Exception as error:
            out[label]={'ok':False,'error':type(error).__name__,'code':str(error)[:80] if isinstance(error,ValueError) else None}
    def run(plan,name):
        started=time.monotonic()
        result=m.container_run(commands,'verify',image_id,m.mounts_of(plan),m.VERIFY_COMMAND,m.frame_of(plan,REQUEST),container_name=m.CONTAINER_PREFIX+name)
        seconds=round(time.monotonic()-started,2)
        line=m.verify_line(result['output'],result['returncode'],plan,REQUEST) if result['returned'] else None
        left=m.CONTAINER_PREFIX+name in [row['name'] for row in m.container_list(commands)]
        done=bool(line and line.get('status')=='DONE')
        return {'returned':result['returned'],'returncode':result['returncode'],'code':result['code'],'seconds':seconds,'left_behind':left,
                'status':line and line.get('status'),'snippet_code':line.get('code') if line and not done else None,
                'release':line['release'] if done else None,'policy':line['policy'] if done else None,'probe':line['probe'] if done else None,
                'package_equal_signed':line['package_equal_signed'] if done else None,'facts':line['facts'] if done else None}
    def image():
        facts=m.image_facts(commands,image_id)
        return {'id_equal':facts['id']==image_id,'revision_label_is_the_release':facts['revision_label']==REVISION,'repo_tags':facts['repo_tags']}
    shape('image_inspect',image)
    shape('pre_release_on_standard_input',lambda:run(plan_of('PRE',work,image_id,release,policy),'relpre0000000000'))
    shape('pre_another_build_revision',lambda:run(plan_of('PRE',work,image_id,release,policy,revision='0'*40),'relrev0000000000'))
    shape('post_read_only_bind',lambda:run(plan_of('POST',work,image_id,release,policy),'relpost000000000'))
    shape('pre_with_the_probe_of_the_bind',lambda:run(plan_of('PRE',work,image_id,release,policy,probe=work+'/release'),'relprobe00000000'))
    def refused():
        plan=plan_of('POST',work,image_id,release,policy);plan['release']['directory_name']='release-open';return run(plan,'relopen000000000')
    shape('post_file_the_reader_refuses',refused)
    return out

RUNS=('pre_release_on_standard_input','pre_another_build_revision','post_read_only_bind','pre_with_the_probe_of_the_bind','post_file_the_reader_refuses')
def expectations(out):
    """What Sunday's dry run and Monday's readback rely on, read from the shapes: one boolean per statement, False when its shape did not run."""
    def get(label,key):return out.get(label,{}).get(key)
    pre,post,probe=(out.get(label,{}) for label in ('pre_release_on_standard_input','post_read_only_bind','pre_with_the_probe_of_the_bind'))
    policy=pre.get('policy') or {};other=get('pre_another_build_revision','release') or {};refused=get('post_file_the_reader_refuses','release') or {}
    return {
        'the image is the one built from this checkout: its ID resolves and it carries the revision label of the release':
            get('image_inspect','id_equal') is True and get('image_inspect','revision_label_is_the_release') is True,
        'K11-U4 the application modules of the release import in a fresh read-only container without network, and the snippet ends DONE':
            pre.get('returncode')==0 and pre.get('status')=='DONE',
        'Release.verify of the release code accepts the synthetic release given on standard input':pre.get('release')==dict(ACCEPTED,source='STDIN'),
        'the package hash the image computes from its own files is the signed one':pre.get('package_equal_signed') is True and post.get('package_equal_signed') is True,
        'the controller and the assembler of the release accept the synthetic policy at every signed instant':
            policy.get('hash_equal_signed') is True and policy.get('controller_at')==[{'valid':True,'code':None}]*len(VALID_AT) and policy.get('assembler')=={'valid':True,'code':None},
        'Release.verify refuses another build revision with its own code':(other.get('verified'),other.get('code'))==(False,'RELEASE_CODE_OR_AUTHORIZATION_UNVERIFIED'),
        'K11-U2 the installed file is read by the reader of the worker through a read-only bind under a read-only root, and verified':post.get('release')==dict(ACCEPTED,source='FILE'),
        'the full dry run reads one private file through its bind and verifies the release on standard input':
            probe.get('probe')=={'valid':True,'code':None} and probe.get('release')==dict(ACCEPTED,source='STDIN'),
        'the reader of the worker refuses a file group or other can read, through the bind':(refused.get('read'),refused.get('code'))==(False,'RELEASE_FILE_NOT_PRIVATE_OR_INVALID'),
        'K11-U1 no named container is left when its run has returned':all(get(label,'left_behind') is False for label in RUNS),
        'every run ends well inside the alarm of the snippet (30 s)':all(type(get(label,'seconds')) in (int,float) and get(label,'seconds')<30 for label in RUNS),
    }

def report(out,documents):
    met=expectations(out);ran=all(row.get('ok') for row in out.values())
    return {'schema':SCHEMA,'revision':REVISION,'package_sha256':PACKAGE,'synthetic_documents':documents,'shapes':out,'expectations':met,
            'every_shape_ran':ran,'every_expectation_met':all(met.values())},(0 if ran and all(met.values()) else 3 if ran else 2)

def facts_of(release,policy):
    """What is said of the two synthetic documents: sizes and hashes of bytes that are not secret and not real."""
    with open(DOCUMENTS,'rb') as handle:builder=handle.read()
    return {'release_sha256':sha(release),'release_bytes':len(release),'policy_sha256':sha(policy),'policy_bytes':len(policy),
            'builder_sha256':sha(builder),'every_reference_says_synthetic':b'"SYNTHETIC"' in release}

def decoded(raw):
    value=json.loads(raw);return base64.b64decode(value['release']),base64.b64decode(value['policy'])

def documents_in_the_image(m,image_id):
    """The sealed builder, unchanged, on standard input of a container of the image: the documents are made by the
    constants of the code the image carries. The same prefix as every attached run of the family; no bind."""
    with open(DOCUMENTS,'rb') as handle:source=handle.read()
    argv=[m.BINARIES['docker'][0]]+list(m.RUN_PREFIX)+[image_id,'python','-I','-B','-','/app',REVISION,'{}','{}']
    done=subprocess.run(argv,input=source,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=dict(m.COMMAND_ENVIRONMENT),cwd=m.COMMAND_DIRECTORY,timeout=60)
    if done.returncode!=0:raise RuntimeError('the builder of the synthetic documents ended with status %d in the image'%done.returncode)
    return decoded(done.stdout)

def prepare(work,release):
    """An installed release twice, as install_release leaves it (0700 directory, 0600 file), and one the reader must refuse (0644)."""
    for name,mode in (('release',0o600),('release-open',0o644)):
        os.mkdir(work+'/'+name,0o700);path=work+'/'+name+'/'+RELEASE_FILE
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.write(fd,release);os.fsync(fd);os.close(fd);os.chmod(path,mode)

def emulated(tree):
    """--self-test: the emulated engine of the core, the snippet run by the local interpreter on the release's own package."""
    sys.path.insert(0,os.path.join(OPERATION,'tests'))
    import hostemu
    import k11
    assert hostemu.REVISION==REVISION and k11.PACKAGE==PACKAGE and (k11.TARGET,k11.PROBE_TARGET,k11.RELEASE_FILE,k11.VALID_AT)==(TARGET,PROBE_TARGET,RELEASE_FILE,VALID_AT)
    done=subprocess.run([sys.executable,'-B',DOCUMENTS,tree,REVISION,'{}','{}'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
    if done.returncode!=0:raise RuntimeError(done.stderr.decode()[-1000:])
    release,policy=decoded(done.stdout);k=f.load(OPERATION);host=f.world(k);work='/srv/hostops02-release-verify'
    for name,mode in (('release',0o600),('release-open',0o644)):
        host.tree.add(work+'/'+name,mode=0o700);host.tree.add(work+'/'+name+'/'+RELEASE_FILE,kind='file',mode=mode,content=release)
    host.docker.on_run=k11.Container(tree)
    return k.m,host,hostemu.BACKEND,work,release,policy

def main(arguments):
    if arguments[:1]==['--self-test'] and len(arguments)==2:
        m,host,image_id,work,release,policy=emulated(arguments[1])
        result,code=report(collect(m,host,image_id,work,release,policy),facts_of(release,policy))
        sys.stdout.write(json.dumps(dict(result,self_test_on_the_emulation=True),sort_keys=True)+'\n');return code
    if len(arguments)!=2:
        sys.stdout.write(__doc__);return 1
    if not (sys.platform.startswith('linux') and os.geteuid()==0 and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'):
        sys.stdout.write('REFUSED: a throwaway GitHub-hosted Linux runner as root only\n');return 1
    image_id,work=arguments
    if not (os.path.isdir(work) and not os.listdir(work) and os.stat(work).st_uid==0):
        sys.stdout.write('REFUSED: the work directory must exist, be root-owned and empty\n');return 1
    m=f.load(OPERATION).m
    try:release,policy=documents_in_the_image(m,image_id)
    except Exception as error:
        sys.stdout.write(json.dumps({'schema':SCHEMA,'every_shape_ran':False,'every_expectation_met':False,'documents':type(error).__name__,
                                     'detail':str(error)[:200] if isinstance(error,RuntimeError) else None},sort_keys=True)+'\n');return 2
    prepare(work,release);result,code=report(collect(m,m.Native(),image_id,work,release,policy),facts_of(release,policy))
    sys.stdout.write(json.dumps(result,sort_keys=True)+'\n');return code

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
