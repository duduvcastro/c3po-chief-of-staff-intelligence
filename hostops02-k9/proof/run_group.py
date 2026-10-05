"""One group of the K9 proof job, on a THROWAWAY GitHub-hosted ubuntu-24.04 runner. Started as the runner's ordinary user;
root is taken with `sudo -n` where a step needs it (the sealed run.sh scripts refuse to start as root).

  /usr/bin/python3 -I -B hostops02-k9/proof/run_group.py <group>          (a group of proof/GROUPS.json)

NEVER the production host and never a self-hosted runner. It refuses unless Linux, GITHUB_ACTIONS=true,
RUNNER_ENVIRONMENT=github-hosted, HOSTOPS_THROWAWAY_RUNNER=yes, an ordinary uid and `sudo -n` are all given, and unless
none of the paths of the production layout exists. What it changes on the runner (and only there), each shown before
and after in RUNNER.txt:
  - /opt made root:root 0755 when it is not already root-owned without write for group or other (the GitHub image
    leaves it 0777, and the programs refuse a deploy directory below such a component: DEPLOY_CHAIN_UNSAFE...; the
    lesson of the token proof, revision 2c);
  - one sudoers drop-in (validated by visudo -c before it is installed) that keeps the release-tree variables of the
    tests across `sudo` (HOSTOPS02_TEST_RELEASE_TREE, HOSTOPS02_TEST_RELEASE_EXPORT, HOSTOPS02_TEST_APP_PYTHON,
    HOSTOPS02_TEST_CORE_TESTS, HOSTOPS02_CORE_DIRECTORY, K9_TEST_PYTHON, K9_TEST_APP), so the root runs of the suites
    see the same release tree as the user runs. HOSTOPS02_TEST_RELEASE_REPOSITORY is NOT kept (git refuses a checkout
    owned by another uid): its tests run in the user runs only;
  - the release export: `git archive` of the release commit (byte-identical to the dd4ec4bb.tar of the scratchpad,
    sha256 61bf5dd5...; checked), extracted under $RUNNER_TEMP; and, for a group marked app-python, a venv under
    $RUNNER_TEMP with the release's requirements from the package index (an interpreter that imports the release's app).
Then the group's steps in order, each whatever the earlier ones did (a failed step is recorded and the next runs):
  core <core dir> <op ...>   the core's own linux_root/run.sh with the operations (their suites as real root and as
                             the user, the core's shapes; it switches the engine to the containerd image store)
  opsh <op dir> [args]       the operation's own linux_root/run.sh (@RELEASE = this checkout, the release tree)
  runner-tests <dir>         the K9 runner's tests with the app interpreter, as the user and as root
  containerd-store           the engine switched to the containerd image store (what the cores' run.sh do)
  release-image              the backend image BUILT FROM THIS CHECKOUT as the pipeline builds it (the release's own
                             Dockerfile, the rebuild token of the release, the revision label)
  docker-shapes              proof/docker_shapes.py on that image (N-7 and K12 U1-U6, U9, U10)
  systemd-shapes             proof/systemd_shapes.py (K5 and K13 systemctl rows on stand-in units)
  k9w-release-shapes <dir>   K9W's own linux_root/shapes.py with the release image instead of python:3.12-alpine
Outputs: proof/out/<group>/ (RUNNER.txt, RESULT.json, the junit and shape files of every step, copied from where the
scripts write them, with their sha256). Exit 0 only when every step ran and exited 0.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import stat
import tarfile
import time
import xml.etree.ElementTree as ElementTree

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)
REPOSITORY=os.path.dirname(ROOT)
RELEASE='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
RELEASE_TAR_SHA256='61bf5dd5e8b4c5b1e421b16949b4294f5dbfefe44a164d7097cdce7167e57660'
C3PO_TREE='058a83e92aae5cb052ca74bf8a56d4667c5cfc08'          # git rev-parse dd4ec4bb:c3po, the build context of the image
IMAGE_REFERENCE='c3po/backend:hostops02-k9-ci-release'
PRODUCTION_PATHS=('/var/lib/c3po','/var/lib/c3po-capacity','/mnt/day-d-data','/opt/chief-of-staff-digital','/etc/c3po-bar','/var/lib/c3po-bar',
                  '/etc/c3po-reader','/var/lib/c3po-reader','/run/c3po-security')
KEPT=('HOSTOPS02_TEST_RELEASE_TREE','HOSTOPS02_TEST_RELEASE_EXPORT','HOSTOPS02_TEST_APP_PYTHON','HOSTOPS02_TEST_CORE_TESTS','HOSTOPS02_CORE_DIRECTORY',
      'K9_TEST_PYTHON','K9_TEST_APP','K9_RELEASE_TREE','K9R_ASSEMBLED')
SUDOERS='/etc/sudoers.d/90-hostops02-k9-ci-env'
ROOT_ENV=['HOSTOPS_THROWAWAY_RUNNER=yes','RUNNER_ENVIRONMENT=github-hosted']

def say(text):
    sys.stdout.write('\n== %s\n'%text);sys.stdout.flush()
def refuse(text):
    sys.stderr.write('REFUSED: %s\n'%text);raise SystemExit(1)
def sha_file(path):
    digest=hashlib.sha256()
    with open(path,'rb') as handle:
        for block in iter(lambda:handle.read(1<<20),b''):digest.update(block)
    return digest.hexdigest()
def run(argv,cwd=None,env=None,timeout=None,capture=False,input=None):
    """A command with its status; its output goes to the job log unless captured. Never raises for a status."""
    started=time.monotonic()
    try:
        done=subprocess.run(argv,cwd=cwd,env=env,timeout=timeout,input=input,stdout=subprocess.PIPE if capture else None,stderr=subprocess.STDOUT if capture else None)
        return done.returncode,(done.stdout.decode('utf-8','replace') if capture else ''),round(time.monotonic()-started,1)
    except subprocess.TimeoutExpired:
        return 'TIMEOUT',None,round(time.monotonic()-started,1)
    except OSError as error:
        return 'NOT_STARTED:%s'%type(error).__name__,None,0.0
def sudo(argv,**keywords):return run(['sudo','-n']+argv,**keywords)

def guard():
    if not sys.platform.startswith('linux'):refuse('Linux only')
    if os.environ.get('HOSTOPS_THROWAWAY_RUNNER')!='yes':refuse('HOSTOPS_THROWAWAY_RUNNER=yes is required')
    if os.environ.get('GITHUB_ACTIONS')!='true':refuse('a GitHub Actions job is required')
    if os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':refuse('a GitHub-hosted runner is required')
    if os.geteuid()==0:refuse("start as the runner's ordinary user")
    for path in PRODUCTION_PATHS:
        if os.path.lexists(path):refuse('%s exists: this is not a throwaway runner'%path)
    if run(['sudo','-n','true'])[0]!=0:refuse('sudo -n is not available')

class Group:
    def __init__(self,name):
        with open(os.path.join(HERE,'GROUPS.json'),'rb') as handle:groups=json.load(handle)
        with open(os.path.join(HERE,'UNITS.json'),'rb') as handle:self.units=json.load(handle)
        if name not in groups['groups']:refuse('no group %r in proof/GROUPS.json'%name)
        self.name=name;self.spec=groups['groups'][name];self.results=[];self.image_id=None;self.app_python=None;self.release_tree=None
        self.out=os.path.join(HERE,'out',name);os.makedirs(self.out,exist_ok=True)
        self.temp=os.environ.get('RUNNER_TEMP') or '/tmp'
        self.marker=time.time()
        self.facts=[]

    def note(self,text):
        self.facts.append(text);sys.stdout.write(text+'\n');sys.stdout.flush()
    def record(self,step,status,detail=None,elapsed=None):
        row={'step':step,'status':status,'ok':status==0,'detail':detail,'elapsed_seconds':elapsed}
        self.results.append(row);self.note('STEP %s: %s%s'%(step,'OK' if row['ok'] else 'FAILED (%s)'%status,'' if detail is None else ' - %s'%detail))
        return row['ok']

    # ---------------------------------------------------------------- the runner, shown and normalised
    def runner_facts(self,label):
        self.note('-- runner facts (%s)'%label)
        for argv in (['uname','-srvm'],['id'],['stat','-c','%n %U:%G %a','/','/opt','/var/lib','/var/tmp','/tmp','/mnt',REPOSITORY],
                     ['df','-B1','--output=target,fstype,avail','/','/var/lib','/tmp'],['/usr/bin/python3','-V'],['systemctl','--version'],
                     ['docker','version','--format','docker client {{.Client.Version}} server {{.Server.Version}}'],['docker','compose','version','--short'],
                     ['git','--version']):
            status,text,_=run(argv,capture=True)
            self.note('$ %s -> %s\n%s'%(' '.join(argv),status,(text or '').rstrip()))
        status,text,_=sudo(['docker','info','--format','{{.Driver}} {{json .DriverStatus}} logging={{.LoggingDriver}} cgroup={{.CgroupVersion}} init={{.InitBinary}}'],capture=True)
        self.note('$ docker info -> %s\n%s'%(status,(text or '').rstrip()))

    def normalise(self):
        info=os.stat('/opt')
        if info.st_uid!=0 or info.st_gid!=0 or info.st_mode&0o022:
            ok=sudo(['chown','0:0','/opt'])[0]==0 and sudo(['chmod','0755','/opt'])[0]==0
            self.record('runner: /opt made root:root 0755 (was %d:%d %o)'%(info.st_uid,info.st_gid,info.st_mode&0o7777),0 if ok else 1)
        else:
            self.note('/opt already root-owned and closed to group and other writes: left as it is')
        # Repair only the disposable CI runner's own drop-in before global validation.
        existing='/etc/sudoers.d/runner'
        try:
            info=os.lstat(existing)
        except FileNotFoundError:
            self.note('CI runner sudoers drop-in absent; no repair needed')
        else:
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_gid!=0:
                self.record('runner sudoers: existing runner drop-in is not root-owned regular file',1)
                return
            status,output,elapsed=sudo(['chmod','0440',existing],capture=True)
            self.record('runner sudoers: existing CI runner drop-in mode 0440',status,output,elapsed)
            if status!=0:return
        line='Defaults env_keep += "%s"\n'%' '.join(KEPT)
        candidate=os.path.join(self.temp,'hostops02-k9-sudoers')
        with open(candidate,'w',encoding='ascii') as handle:handle.write(line)
        checked=candidate+'.root-checked'
        installed=False
        ok=True
        stages=[('stage root-owned 0440 candidate', ['sudo','-n','install','-o','root','-g','root','-m','0440',candidate,checked]),
                ('validate candidate', ['sudo','-n','visudo','-c','-f',checked]),
                ('install validated drop-in', ['sudo','-n','install','-o','root','-g','root','-m','0440',checked,SUDOERS]),
                ('validate complete sudoers', ['sudo','-n','visudo','-c']),
                ('check noninteractive sudo', ['sudo','-n','true'])]
        for label,argv in stages:
            status,output,elapsed=run(argv,capture=True)
            self.record('runner sudoers: '+label,status,output,elapsed)
            if status!=0:
                ok=False
                break
            if label=='install validated drop-in':installed=True
        if not ok and installed:
            status,output,elapsed=sudo(['rm','-f',SUDOERS],capture=True)
            self.record('runner sudoers: remove rejected drop-in',status,output,elapsed)
        status,output,elapsed=sudo(['rm','-f',checked],capture=True)
        self.record('runner sudoers: remove validation copy',status,output,elapsed)
        self.record('runner: sudoers keeps the release-tree variables of the tests',0 if ok and status==0 else 1)

    def release_export(self):
        base=os.path.join(self.temp,'hostops02-release');tree=os.path.join(base,'tree');tar=os.path.join(base,'dd4ec4bb.tar')
        os.makedirs(tree,exist_ok=True)
        status,text,_=run(['git','-C',REPOSITORY,'rev-parse',RELEASE+':c3po'],capture=True)
        if status!=0 or (text or '').strip()!=C3PO_TREE:
            return self.record('release export: the release commit is in the checkout with its c3po tree',1,(text or '').strip()[:120])
        with open(tar,'wb') as handle:
            done=subprocess.run(['git','-C',REPOSITORY,'archive','--format=tar',RELEASE],stdout=handle)
        digest=sha_file(tar) if done.returncode==0 else None
        if digest is None:return self.record('release export: git archive of the release',done.returncode)
        same=digest==RELEASE_TAR_SHA256
        self.note('git archive %s: sha256 %s (%s the dd4ec4bb.tar of the scratchpad)'%(RELEASE[:12],digest,'equal to' if same else 'NOT equal to'))
        with tarfile.open(tar) as archive:
            if hasattr(tarfile,'data_filter'):archive.extractall(tree,filter='tar')
            else:archive.extractall(tree)
        self.release_tree=tree
        os.environ['K9_RELEASE_TREE']=os.path.join(tree,'c3po','backend')
        os.environ['HOSTOPS02_TEST_RELEASE_TREE']=tree
        os.environ['HOSTOPS02_TEST_RELEASE_REPOSITORY']=REPOSITORY
        if same:os.environ['HOSTOPS02_TEST_RELEASE_EXPORT']=base
        return self.record('release export: git archive of the release, extracted (byte-identical tar: %s)'%same,0 if same else 1)

    def venv(self):
        target=os.path.join(self.temp,'hostops02-app-venv');python=os.path.join(target,'bin','python')
        status=run(['/usr/bin/python3','-m','venv',target])[0]
        if status!=0:
            sudo(['env','DEBIAN_FRONTEND=noninteractive','apt-get','install','-y','-q','--no-install-recommends','python3-venv'])
            status=run(['/usr/bin/python3','-m','venv',target])[0]
        if status==0:
            status=run([python,'-m','pip','install','--disable-pip-version-check','-q','-r',os.path.join(self.release_tree,'c3po','backend','requirements.txt')])[0]
        if status==0:
            status=run([python,'-I','-c','import pydantic_settings, exchange_calendars, pandas, psycopg, httpx, pytest'])[0]
        if status==0:
            self.app_python=python;os.environ['HOSTOPS02_TEST_APP_PYTHON']=python;os.environ['K9_TEST_PYTHON']=python
            os.environ['K9_TEST_APP']=os.path.join(self.release_tree,'c3po','backend')
            run([python,'-V'])
        return self.record('app interpreter: a venv with the release requirements (from the package index)',status)

    # ---------------------------------------------------------------- the steps
    def step_core(self,core,*operations):
        directory=os.path.join(ROOT,core)
        status,_,elapsed=run(['sh','linux_root/run.sh']+list(operations),cwd=directory)
        return self.record('core %s %s: linux_root/run.sh'%(core,' '.join(operations)),status,None,elapsed)

    def step_opsh(self,operation,*arguments):
        directory=os.path.join(ROOT,operation)
        unit=self.unit_of(directory)
        if unit is not None and unit.get('withheld'):
            return self.record('opsh %s: linux_root/run.sh'%operation,'NOT_RUN_WITHHELD','its run.sh verifies every sealed file and %d are withheld: %s'%(len(unit['withheld']),', '.join(sorted(unit['withheld']))))
        words=[REPOSITORY if word=='@RELEASE' else word for word in arguments]
        status,_,elapsed=run(['sh','linux_root/run.sh']+words,cwd=directory)
        return self.record('opsh %s %s: linux_root/run.sh'%(operation,' '.join(arguments)),status,None,elapsed)

    def step_runner_tests(self,directory):
        path=os.path.join(ROOT,directory)
        if not self.app_python:return self.record('runner-tests %s'%directory,'NOT_RUN','no app interpreter (the group is not marked app-python, or its venv failed)')
        ok=True
        for label,prefix in (('linux-user',[]),('linux-root',['sudo','-n','env']+ROOT_ENV+['K9_TEST_RUN=ci-root','K9_TEST_PYTHON='+self.app_python,
                                                                                      'K9_TEST_APP='+os.environ['K9_TEST_APP'], 'K9_RELEASE_TREE='+os.environ['K9_RELEASE_TREE']])):
            report=os.path.join(self.out,'TESTS.%s.%s.xml'%(os.path.basename(directory.rstrip('/')),label))
            env=dict(os.environ,K9_TEST_RUN='ci-user',PYTHONDONTWRITEBYTECODE='1')
            status,_,elapsed=run(prefix+[self.app_python,'-B','-m','pytest','-p','no:cacheprovider','-q','-rfEs','tests','--junitxml',report,'-o','junit_family=xunit2'],
                                 cwd=path,env=env,timeout=3600)
            ok=self.record('runner-tests %s as %s'%(directory,label),status,None,elapsed) and ok
        sudo(['chown','-R','%d:%d'%(os.getuid(),os.getgid()),path,self.out])
        return ok

    def step_containerd_store(self):
        script=('import json,os\npath="/etc/docker/daemon.json"\ntry:\n    config=json.load(open(path))\nexcept FileNotFoundError:\n    config={}\n'
                'config.setdefault("features",{})["containerd-snapshotter"]=True\nos.makedirs("/etc/docker",mode=0o755,exist_ok=True)\n'
                'open(path,"w").write(json.dumps(config,indent=1,sort_keys=True)+"\\n")\n')
        status,text,_=sudo(['docker','info','--format','{{.Driver}} {{json .DriverStatus}}'],capture=True)
        if 'io.containerd.snapshotter.v1' in (text or ''):return self.record('containerd-store: already the containerd image store',0)
        status=sudo(['/usr/bin/python3','-I','-B','-c',script])[0]
        if status==0:status=sudo(['systemctl','restart','docker'])[0]
        for _ in range(30):
            if sudo(['docker','info'],capture=True)[0]==0:break
            time.sleep(2)
        status2,text,_=sudo(['docker','info','--format','{{.Driver}} {{json .DriverStatus}}'],capture=True)
        return self.record('containerd-store: the engine on the containerd image store',0 if status==0 and 'io.containerd.snapshotter.v1' in (text or '') else 1,(text or '').strip()[:160])

    def step_release_image(self):
        status,text,_=run(['git','-C',REPOSITORY,'rev-parse','HEAD:c3po'],capture=True)
        if (text or '').strip()!=C3PO_TREE:return self.record('release-image',1,'c3po/ of this checkout is not the tree of the release')
        status,text,_=run(['git','-C',REPOSITORY,'status','--porcelain','--untracked-files=all','--','c3po'],capture=True)
        if status!=0 or (text or '').strip():return self.record('release-image',1,'c3po/ of the checkout differs from its commit')
        for reference in (IMAGE_REFERENCE,'c3po/backend:production'):
            if sudo(['docker','image','inspect',reference],capture=True)[0]==0:refuse('%s exists: this is not a throwaway runner'%reference)
        token=sha_file(os.path.join(REPOSITORY,'c3po','security','container-rebuild-trigger.json'))
        status,text,elapsed=sudo(['docker','build','--file',os.path.join(REPOSITORY,'c3po','backend','Dockerfile'),'--build-arg','C3PO_SECURITY_REBUILD='+token,
                                  '--label','org.opencontainers.image.revision='+RELEASE,'--tag',IMAGE_REFERENCE,os.path.join(REPOSITORY,'c3po')],capture=True,timeout=1800)
        sys.stdout.write('\n'.join((text or '').splitlines()[-25:])+'\n')
        if status!=0:return self.record('release-image: docker build of the release',status,None,elapsed)
        _,image,_=sudo(['docker','image','inspect','--format','{{.Id}}',IMAGE_REFERENCE],capture=True);image=(image or '').strip()
        _,label,_=sudo(['docker','image','inspect','--format','{{ index .Config.Labels "org.opencontainers.image.revision" }}',IMAGE_REFERENCE],capture=True)
        facts=['reference %s'%IMAGE_REFERENCE,'image_id %s'%image,'revision_label %s'%(label or '').strip(),'c3po_tree %s'%C3PO_TREE,'rebuild_token %s'%token,
               'dockerfile_sha256 %s'%sha_file(os.path.join(REPOSITORY,'c3po','backend','Dockerfile')),
               'requirements_sha256 %s'%sha_file(os.path.join(REPOSITORY,'c3po','backend','requirements.txt'))]
        for argv in (['docker','run','--rm','--pull','never','--network','none','--entrypoint','python',image,'-V'],
                     ['docker','run','--rm','--pull','never','--network','none','--entrypoint','sh',image,'-c','readlink -f "$(command -v timeout)"; cat /etc/alpine-release'],
                     ['docker','image','inspect','--format','entrypoint {{json .Config.Entrypoint}} cmd {{json .Config.Cmd}} workdir {{json .Config.WorkingDir}} env {{len .Config.Env}} names',image]):
            _,text,_=sudo(argv,capture=True);facts.append('%s -> %s'%(argv[-1] if argv[1]=='image' else ' '.join(argv[-2:]),(text or '').strip().replace('\n',' | ')))
        with open(os.path.join(self.out,'IMAGE.release.txt'),'w',encoding='utf-8') as handle:handle.write('\n'.join(facts)+'\n')
        sys.stdout.write('\n'.join(facts)+'\n')
        ok=image.startswith('sha256:') and (label or '').strip()==RELEASE
        if ok:self.image_id=image
        return self.record('release-image: built from this checkout, revision label %s'%RELEASE[:12],0 if ok else 1,image,elapsed)

    def root_python(self,script,*arguments,output):
        status,_,elapsed=run(['sudo','-n','env']+ROOT_ENV+['/usr/bin/python3','-I','-B',script]+list(arguments)+['--out',output],timeout=3600)
        sudo(['chown','%d:%d'%(os.getuid(),os.getgid()),output])
        return status,elapsed

    def step_docker_shapes(self):
        if not self.image_id:return self.record('docker-shapes','NOT_RUN','no release image')
        status,elapsed=self.root_python(os.path.join(HERE,'docker_shapes.py'),self.image_id,self.release_tree or REPOSITORY,output=os.path.join(self.out,'SHAPES.docker.release-image.json'))
        return self.record('docker-shapes: N-7 and K12 shapes on the release image (2: a shape did not run; 3: an expectation not met)',status,None,elapsed)

    def step_systemd_shapes(self):
        status,elapsed=self.root_python(os.path.join(HERE,'systemd_shapes.py'),output=os.path.join(self.out,'SHAPES.systemd.json'))
        return self.record('systemd-shapes: the K5 and K13 systemctl rows on stand-in units (2: a shape did not run; 3: an expectation not met)',status,None,elapsed)

    def step_k9w_release_shapes(self,directory):
        if not self.image_id:return self.record('k9w-release-shapes','NOT_RUN','no release image')
        if not self.app_python:self.venv()
        if not self.app_python:return self.record('k9w-release-shapes', 'NOT_RUN', 'app interpreter unavailable')
        path=os.path.join(ROOT,directory);output=os.path.join(self.out,'SHAPES.k9_phase_step.release-image.json')
        for existing in ('/var/lib/c3po','/mnt/day-d-data'):
            if os.path.lexists(existing):return self.record('k9w-release-shapes',1,'%s exists before the shapes (a previous step left it)'%existing)
        with open(output,'wb') as handle:
            started=time.monotonic()
            done=subprocess.run(['sudo','-n','env']+ROOT_ENV+[self.app_python,'-B','linux_root/shapes.py',self.image_id],cwd=path,stdout=handle)
        status=done.returncode;elapsed=round(time.monotonic()-started,1)
        # what K9W's own run.sh removes after its shapes: the K9 containers, the two networks, the K9 tree
        _,ids,_=sudo(['docker','ps','-aq','--filter','name=c3po-k9-'],capture=True)
        for identifier in (ids or '').split():sudo(['docker','rm','-f',identifier],capture=True)
        sudo(['docker','network','rm','k9ci_internal','k9ci_loopback'],capture=True)
        sudo(['rm','-rf','/var/lib/c3po'])
        return self.record('k9w-release-shapes %s: K9W shapes.py with the release image (2: a shape did not run; 3: an expectation not met)'%directory,status,None,elapsed)

    def unit_of(self,directory):
        real=os.path.realpath(directory)
        for unit in self.units['units']:
            if os.path.realpath(os.path.join(ROOT,unit['dest']))==real:return unit
        return None

    # ---------------------------------------------------------------- outputs
    def collect(self):
        rows=[]
        for folder,names,found in os.walk(ROOT):                 # links are not followed: each file is taken where it lies
            names[:]=[name for name in names if not (folder==HERE and name=='out')]
            if os.path.basename(folder)!='linux_root':continue
            for name in found:
                path=os.path.join(folder,name)
                if os.path.islink(path) or not ((name.startswith('TESTS.') and name.endswith('.xml')) or (name.startswith('SHAPES') and name.endswith('.json'))):continue
                if os.path.getmtime(path)<self.marker-1:continue
                relative=os.path.relpath(path,ROOT);target=os.path.join(self.out,'files',relative)
                os.makedirs(os.path.dirname(target),exist_ok=True);shutil.copy2(path,target)
        for path in sorted(glob.glob(os.path.join(self.out,'**','*'),recursive=True)):
            if not os.path.isfile(path) or path.endswith('RESULT.json'):continue
            row={'file':os.path.relpath(path,self.out),'sha256':sha_file(path),'bytes':os.path.getsize(path)}
            if path.endswith('.xml'):row.update(junit(path))
            elif path.endswith('.json'):row.update(shape_summary(path))
            rows.append(row)
        return rows

def junit(path):
    try:
        node=ElementTree.parse(path).getroot();node=node if node.tag=='testsuite' else node.find('testsuite')
        counts={key:int(node.get(key,0)) for key in ('tests','failures','errors','skipped')}
        bad=[];skipped=[]
        for case in node.iter('testcase'):
            name='%s::%s'%(case.get('classname',''),case.get('name',''))
            if case.find('failure') is not None or case.find('error') is not None:bad.append(name)
            if case.find('skipped') is not None:skipped.append('%s (%s)'%(name,(case.find('skipped').get('message') or '')[:120]))
        return {'junit':counts,'failed_tests':bad[:200],'skipped_tests':skipped[:200]}
    except Exception as error:
        with open(path,'rb') as handle:head=handle.read(200).decode('utf-8','replace')
        return {'junit':None,'not_junit':head.strip()[:200],'error':type(error).__name__}

def shape_summary(path):
    try:
        with open(path,'rb') as handle:data=json.load(handle)
        expectations=data.get('expectations') if isinstance(data,dict) else None
        if isinstance(expectations,dict):
            return {'all_shapes_ran':data.get('all_shapes_ran'),'all_expectations_met':data.get('all_expectations_met'),
                    'unmet':sorted(key for key,value in expectations.items() if value is not True)}
        return {}
    except Exception:
        with open(path,'rb') as handle:head=handle.read(200).decode('utf-8','replace')
        return {'not_json':head.strip()[:200]}

def main(argv):
    if len(argv)!=1:refuse('usage: run_group.py <group>')
    guard()
    group=Group(argv[0])
    say('group %s: %d steps, units staged %d'%(group.name,len(group.spec['steps']),len(group.units['units'])))
    def safe(label,function):
        try:function()
        except SystemExit:raise
        except Exception as error:group.record(label,'EXCEPTION:%s'%type(error).__name__,str(error)[:300])
    safe('runner facts',lambda:group.runner_facts('before'))
    safe('runner normalisation',group.normalise)
    safe('release export',group.release_export)
    if group.spec.get('app_python'):safe('app interpreter',group.venv)
    for name,value in sorted(group.spec.get('env',{}).items()):
        value=value.replace('@ROOT',ROOT).replace('@RELEASE_TREE',group.release_tree or '').replace('@APP_PYTHON',group.app_python or '').replace('@RELEASE',REPOSITORY)
        os.environ[name]=value;group.note('env %s=%s'%(name,value))
    for step in group.spec['steps']:
        say('step %s %s'%(step['kind'],' '.join(step['args'])))
        method=getattr(group,'step_'+step['kind'].replace('-','_'))
        try:method(*step['args'])
        except SystemExit:raise
        except Exception as error:group.record('%s %s'%(step['kind'],' '.join(step['args'])),'EXCEPTION:%s'%type(error).__name__,str(error)[:300])
    group.runner_facts('after')
    files=group.collect()
    failed=[row for row in group.results if not row['ok']]
    result={'schema':'HOSTOPS02_K9_PROOF_GROUP_RESULT_V1','group':group.name,'release':RELEASE,'steps':group.results,'files':files,
            'failed_steps':len(failed),'green':not failed,'unit_seals':{unit['dest']:unit['seal_sha256'] for unit in group.units['units']}}
    with open(os.path.join(group.out,'RESULT.json'),'w',encoding='utf-8') as handle:handle.write(json.dumps(result,indent=1,sort_keys=True)+'\n')
    with open(os.path.join(group.out,'RUNNER.txt'),'w',encoding='utf-8') as handle:handle.write('\n'.join(group.facts)+'\n')
    say('outputs of group %s'%group.name)
    for row in files:
        sys.stdout.write('%s %s %s\n'%(row['sha256'],row['file'],json.dumps({key:row[key] for key in row if key in ('junit','failed_tests','all_shapes_ran','all_expectations_met','unmet','not_junit','not_json')},sort_keys=True)))
    say('group %s: %s (%d of %d steps failed)'%(group.name,'GREEN' if not failed else 'RED',len(failed),len(group.results)))
    return 0 if not failed else 1

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
