"""The frozen core: its seal, its pins, what it shares with HOSTOPS01, the literal tables every operation signs, and
the rules assemble.py refuses to build without. Offline. Tests whose name contains "static" pin bytes and text; the
mutation harness does not count them (which is why this file is not named after them)."""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

import demos
import family as f

CORE=f.CORE
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
PARTS=('core','runner','docker','parents','files','lock')
BASE={'dispatch_once.py':'8415e357e48e5662c959b4105acea19bc280cda10112b8370bafd27f7920c409',
      'launcher_stdin.py':'2842444ec6e46f5e47cad87265927ea3a1a853f21fe72ec2459cf7ac31c3a08e',
      'transport_once.py':'5900efbf916d679a6ce176dd71413f304e21e0c9ab65b0ff8ee742cc212f2918'}
# Where the sealed HOSTOPS01 candidate lies on the build machine; elsewhere the tests that read it are skipped and say so.
HOSTOPS01=Path(os.environ.get('HOSTOPS02_TEST_HOSTOPS01_DIR') or CORE.parent.parent/'hostops01'/'candidate')

def run(*arguments,cwd=None):
    return subprocess.run([sys.executable,'-B']+[str(item) for item in arguments],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,cwd=cwd,timeout=120)


# ---------------------------------------------------------------- the seal
def test_static_seal_lists_every_file_and_every_hash_holds():
    lines=(CORE/'CORE_SHA256SUMS').read_text(encoding='ascii').splitlines();listed={}
    for line in lines:
        digest,name=line.split('  ',1);assert re.fullmatch('[0-9a-f]{64}',digest) and name not in listed;listed[name]=digest
    present=sorted(path.relative_to(CORE).as_posix() for path in CORE.rglob('*') if path.is_file() and path.name!='CORE_SHA256SUMS'
                   and not {'__pycache__','.pytest_cache','_tmp'}&set(path.relative_to(CORE).parts) and path.suffix!='.pyc'
                   and not re.fullmatch(r'linux_root/(TESTS\..*\.xml|SHAPES\.linux-root\.json)',path.relative_to(CORE).as_posix()))      # the Linux job's own output
    assert sorted(listed)==present,'a file that is not listed, or a listed file that is gone'
    for name,digest in listed.items():assert f.sha((CORE/name).read_bytes())==digest,name
    assert run(CORE/'seal.py','check').stdout.strip()==b'SEAL_OK'

def test_static_assembler_pins_every_part_and_base_file_and_its_own_hash_is_the_generation():
    a=f.assembler()
    assert sorted(a.PINS)==sorted(['parts/%s.py'%name for name in PARTS]+['reviewed_base/'+name for name in BASE]) and a.PART_ORDER==PARTS
    for name,digest in a.PINS.items():assert f.sha((CORE/name).read_bytes())==digest,name
    for name,digest in BASE.items():assert a.PINS['reviewed_base/'+name]==digest
    generation=f.sha((CORE/'assemble.py').read_bytes());assert a.core_sha256()==generation
    done=run(CORE/'assemble.py','--core');assert done.returncode==0 and done.stdout.strip().decode()==generation and done.stderr==b''
    for directory in (demos.READ,demos.WRITE):
        k=f.load(directory);assert k.m.CORE_SHA256==generation==k.report['core_sha256'] and k.m.SCOPE['core_sha256']==generation
        assert run(CORE/'assemble.py','--check',directory).stdout.strip()==b'BUILD_EQUAL'

def test_static_launcher_and_transport_are_the_bytes_hostops01_shipped():
    a=f.assembler();assert f.sha(a.launcher_bytes())==f.LAUNCHER_PIN and f.sha(a.reviewed('transport_once.py'))==f.TRANSPORT_PIN
    for directory in (demos.READ,demos.WRITE):
        k=f.load(directory);assert f.sha((k.dir/'launcher_stdin.py').read_bytes())==f.LAUNCHER_PIN and f.sha((k.dir/'transport_once.py').read_bytes())==f.TRANSPORT_PIN

@pytest.mark.skipif(not (HOSTOPS01/'parts'/'core.py').is_file(),reason='the sealed HOSTOPS01 candidate is not on this machine')
def test_static_delta_against_hostops01_is_the_shipped_one_and_the_identical_parts_are_identical():
    done=run(CORE/'delta.py','check',HOSTOPS01);assert done.returncode==0 and done.stdout.strip()==b'DELTA_OK',done.stdout+done.stderr
    rows=json.loads((CORE/'DELTA'/'IDENTICAL.json').read_text())['rows'];assert len(rows)==16 and all(row['identical'] and row['sha256_here']==row['sha256_hostops01'] for row in rows)
    # the whole delta of the shared core: these hunks and no other (a hunk header per changed region)
    diff=(CORE/'DELTA'/'core.diff').read_text();changed=[line for line in diff.splitlines() if line[:1] in '+-' and line[:3] not in ('+++','---')]
    words=' '.join(changed)
    for must in ('DATE_SETS','ACTIVATION_ALLOWED','CORE_SHA256','def timing(','limit=65536','EVIDENCE_OPERATION_MISSING'):assert must in words
    removed=[line[1:] for line in changed if line.startswith('-')]
    assert len(removed)==18,'the lines of the HOSTOPS01 core that are not carried unchanged'
    assert sum(1 for line in changed if line.startswith('+'))==ADDED_LINES

ADDED_LINES=60
def test_static_shipped_delta_and_identity_table_do_not_depend_on_hostops01_being_present():
    table=json.loads((CORE/'DELTA'/'IDENTICAL.json').read_text())
    for row in table['rows']:
        assert row['identical'] is True
        if ':' not in row['here']:assert f.sha((CORE/row['here']).read_bytes())==row['sha256_here']
    assert table['hostops01_pins']['parts/core.py']=='9a053347b0129c0ca4bc5973b8977422fafb014952d4c0f8c789fded46e73641'


# ---------------------------------------------------------------- the literal tables every operation signs
def test_date_sets_are_the_five_classes_through_2026_10_10():
    for directory in (demos.READ,demos.WRITE):
        m=f.load(directory).m
        assert m.EPOCH_DAYS==('2026-10-02','2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')
        assert m.DATE_SETS=={'READ':m.EPOCH_DAYS,'WRITE_WEEKEND':('2026-10-02','2026-10-03','2026-10-04'),'WRITE_FIRST_SESSION':('2026-10-05',),
                             'WRITE_SESSIONS':('2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10'),
                             'WRITE_EPOCH':('2026-10-03','2026-10-04','2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-10')}
        assert all(type(days) is tuple for days in m.DATE_SETS.values()) and not hasattr(m,'READ_DATES') and not hasattr(m,'WRITE_DATES')

def test_timeout_table_environment_and_budget_constants():
    m=f.load(demos.WRITE).m
    assert m.COMMAND_CLASSES=={'QUICK':{'seconds':8,'output_bytes':65536},'RENDER':{'seconds':15,'output_bytes':1048576},
                               'RUN_SHORT':{'seconds':20,'output_bytes':65536},'RUN':{'seconds':40,'output_bytes':65536},
                               'RECREATE':{'seconds':30,'output_bytes':65536},'SWITCH':{'seconds':30,'output_bytes':65536}}
    assert m.COMMAND_KINDS==('READ','CONTAINER','EFFECT') and m.AFTER_EFFECT_RESERVE_SECONDS==4 and m.MAX_TOOL_TIMEOUTS==2
    assert m.COMMAND_ENVIRONMENT=={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C'} and m.COMMAND_DIRECTORY=='/'
    assert m.COMMAND_VARIABLES=={'DOCKER_CONFIG':'/[A-Za-z0-9._/-]{1,199}','C3PO_BUILD_SHA':'[0-9a-f]{40}'}
    assert m.MAX_SECONDS==60 and m.RECEIPT_LIMIT==60000 and m.MAX_STDIN_BYTES==131072 and m.MAX_LOCK_WAIT_SECONDS==20 and m.LOCK_POLL_SECONDS==.25
    assert m.REMOTE_COMMAND=='sudo -n /usr/bin/python3 -I -B -'
    import hostemu;assert set(hostemu.COMMAND_SECONDS)=={row['seconds'] for row in m.COMMAND_CLASSES.values()}
    # every class leaves room in the 60 s budget for its own reserve
    assert all(row['seconds']+m.AFTER_EFFECT_RESERVE_SECONDS<m.MAX_SECONDS for row in m.COMMAND_CLASSES.values())

def test_proven_templates_and_argv_are_the_literals_of_their_sources():
    m=f.load(demos.WRITE).m
    # the read-only post-deploy family (rev 4 and rev 5), byte for byte
    assert m.CONTAINER_FORMAT=='{"name":{{json .Name}},"id":{{json .Id}},"image_id":{{json .Image}},"image_reference":{{json .Config.Image}},"running":{{json .State.Running}},"state":{{json .State.Status}},"started_at":{{json .State.StartedAt}},"host_pid":{{json .State.Pid}},"restarts":{{json .RestartCount}},"health":{{if index .State "Health"}}{{json (index .State "Health" "Status")}}{{else}}null{{end}}}'
    assert m.PS_FORMAT=='{"id":{{json .ID}},"name":{{json .Names}},"state":{{json .State}}}'
    # the catalog initialisation of the supervisor README at dd4ec4bb, option for option
    assert m.RUN_PREFIX=='run --rm -i --pull never --init --user 0:0 --network none --read-only --cap-drop ALL --security-opt no-new-privileges'.split()
    # the activation of 2026-09-28: the render and the recreate
    assert m.COMPOSE_CONFIG_TAIL==['config','--format','json']
    assert m.compose_up_tail('r2d2-worker')=='up -d --no-deps --no-build --pull never --force-recreate r2d2-worker'.split()
    assert m.compose_arguments('c3po','/opt/x/.env',['/opt/x/c3po/compose.yml','/mnt/d/live/compose.proof.json'])==[
        '--project-name','c3po','--env-file','/opt/x/.env','-f','/opt/x/c3po/compose.yml','-f','/mnt/d/live/compose.proof.json']
    assert m.TEMPORARY=='.hostops-%s-%d.partial' and m.PRIVATE_FILE_MODE==0o600 and m.PRIVATE_DIRECTORY_MODE==0o700
    for template in (m.IMAGE_FORMAT,m.CONTAINER_FORMAT,m.PS_FORMAT,m.environment_format({'A':'b'})):assert '{{{' not in template

README=os.environ.get('HOSTOPS02_TEST_RELEASE_REPOSITORY')
@pytest.mark.skipif(not README,reason='HOSTOPS02_TEST_RELEASE_REPOSITORY (a checkout that holds dd4ec4bb) is not set')
def test_static_run_prefix_is_the_readme_argv_at_the_release():
    m=f.load(demos.WRITE).m
    text=subprocess.run(['/usr/bin/git','-C',README,'show','dd4ec4bb:c3po/deployment/massive-supervisor/README.md'],stdout=subprocess.PIPE,timeout=60).stdout.decode()
    block=text[text.index('DOCKER_CONFIG=<HOST_CONFIG_DIR>/docker-cli docker run'):];block=block[:block.index('```')].replace('\\\n',' ')
    words=block.split();assert words[1]=='docker' and words[2:2+len(m.RUN_PREFIX)]==m.RUN_PREFIX
    assert words[2+len(m.RUN_PREFIX):2+len(m.RUN_PREFIX)+2]==['--mount','type=bind,source=<HOST_JOURNAL_ROOT>,target=<CONTAINER_JOURNAL_ROOT>']
    assert words[2+len(m.RUN_PREFIX)+2:2+len(m.RUN_PREFIX)+7]==['<IMAGE_ID>','python','-I','-B','-']
    assert m.mount_argument({'source':'/var/lib/c3po-bar/journal','target':'/c3po-bar-journal','read_only':False})=='type=bind,source=/var/lib/c3po-bar/journal,target=/c3po-bar-journal'


# ---------------------------------------------------------------- the parts, by syntax tree
OS_OF={'core':{'O_DIRECTORY','O_NOFOLLOW','O_NONBLOCK','O_RDONLY','close','fstat','fstatvfs','getegid','geteuid','open','read','scandir','stat'},
       'runner':{'O_DIRECTORY','O_NOFOLLOW','O_RDONLY','killpg','read','set_blocking','write'},'docker':set(),'parents':set(),
       'files':{'O_CLOEXEC','O_CREAT','O_DIRECTORY','O_EXCL','O_NOFOLLOW','O_RDONLY','O_WRONLY','fsync','link','mkdir','open','umask','unlink','write'},
       'lock':{'O_NOFOLLOW','O_NONBLOCK','O_RDONLY'}}
IMPORTS_OF={'core':{'ctypes','dataclasses','datetime','errno','hashlib','json','os','pathlib','re','stat','time'},'runner':{'selectors','signal','subprocess'},
            'docker':set(),'parents':set(),'files':set(),'lock':{'fcntl'}}
@pytest.mark.parametrize('name',PARTS)
def test_static_each_part_is_python_37_stdlib_only_and_uses_exactly_these_os_members(name):
    text=(CORE/'parts'/(name+'.py')).read_text(encoding='ascii');tree=ast.parse(text,feature_version=(3,7))
    imports=set();attributes=set();process=set();names=set();keywords=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports|={alias.name for alias in node.names}
        elif isinstance(node,ast.ImportFrom):imports.add(node.module)
        elif isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='os':attributes.add(node.attr)
        elif isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='subprocess':process.add(node.attr)
        elif isinstance(node,ast.Name):names.add(node.id)
        elif isinstance(node,ast.keyword):keywords.add(node.arg)
        assert not isinstance(node,(ast.NamedExpr,ast.AsyncFunctionDef,ast.Await)),'python 3.7 syntax only'
    assert imports==IMPORTS_OF[name] and attributes==OS_OF[name]
    assert process==({'DEVNULL','PIPE','Popen','TimeoutExpired'} if name=='runner' else set()) and 'shell' not in keywords and 'preexec_fn' not in keywords
    # the one signal this core ever sends: SIGKILL to the process group of a command the runner itself started, in one place
    signals={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute) and isinstance(node.value,ast.Name) and node.value.id=='signal'}
    assert signals==({'SIGKILL'} if name=='runner' else set()) and text.count('os.killpg(')==(1 if name=='runner' else 0)
    assert name!='runner' or 'os.killpg(process.pid,signal.SIGKILL)' in text and 'start_new_session=True' in text
    assert not names&{'eval','exec','compile','__import__','open','input','breakpoint','print','shutil','socket'}
    # ctypes in the core part only, once: the C library of the interpreter for prctl (dumps_disabled, CORE.md section 14)
    uses=[node for node in ast.walk(tree) if isinstance(node,ast.Name) and node.id=='ctypes']
    assert len(uses)==(1 if name=='core' else 0) and text.count('ctypes.CDLL(None,use_errno=True)')==(1 if name=='core' else 0)
    for word in ('TODO','FIXME','XXX'):assert word not in text
    a=f.assembler();assert a.OS_OF[name]<=OS_OF[name] and a.IMPORTS_OF[name]==IMPORTS_OF[name]
    # no part can change an object that exists: none of these os members is named anywhere in the core
    assert not attributes&{'chmod','fchmod','chown','fchown','lchown','rename','replace','renames','truncate','ftruncate','utime','rmdir','remove','removedirs',
                           'symlink','mknod','mkfifo','system','popen','fork','execv','execve','spawnv','posix_spawn','kill','setuid','setgid','chroot','chdir'}

def test_static_no_part_and_no_demonstration_source_can_exec_into_a_container_or_start_a_shell():
    for directory in (demos.READ,demos.WRITE):
        k=f.load(directory);text=k.source.decode()
        for row in k.m.COMMANDS.values():
            words=row['argv']+row['tail'];assert 'exec' not in words and 'sh' not in words and '-c' not in words and '--privileged' not in words
        assert "'exec'" not in text.replace("row['argv'][0]!='exec'",'') and '/bin/sh' not in text and 'shell=' not in text


# ---------------------------------------------------------------- assemble.py refuses what breaks a rule
def copy_of(directory,target):
    target.mkdir(parents=True);[shutil.copy(str(Path(directory)/name),str(target/name)) for name in ('spec.py','op.py')];return target
def edit(path,old,new,count=1):
    text=path.read_text();assert text.count(old)==count,(old,text.count(old));path.write_text(text.replace(old,new))
def refused(directory):
    with pytest.raises(SystemExit) as caught:f.assembler().build(directory)
    return str(caught.value)

RULES=[
 ('write','op.py',"DATE_CLASS='WRITE_EPOCH'","DATE_CLASS='READ'",'DATES is not DATE_SETS[DATE_CLASS], or the class does not fit'),
 ('read','op.py',"DATE_CLASS='READ'","DATE_CLASS='WRITE_EPOCH'",'DATES is not DATE_SETS[DATE_CLASS], or the class does not fit'),
 ('write','op.py',"DATES=DATE_SETS[DATE_CLASS]","DATES=('2026-10-11',)",'DATES is not DATE_SETS[DATE_CLASS]'),
 ('write','op.py',"DATES=DATE_SETS[DATE_CLASS]","DATES=DATE_SETS['WRITE_SESSIONS']",'DATES is not DATE_SETS[DATE_CLASS]'),
 ('read','op.py',"ACTIVATION_ALLOWED=False","ACTIVATION_ALLOWED=True",'only a writing source may switch a unit'),
 ('write','op.py',"MAX_GATE_SPAN_SECONDS=900","MAX_GATE_SPAN_SECONDS=901",'MAX_GATE_SPAN_SECONDS above 900'),
 ('read','op.py',"MAX_GATE_SPAN_SECONDS=3600","MAX_GATE_SPAN_SECONDS=3601",'MAX_GATE_SPAN_SECONDS above 900'),
 ('write','op.py',"SOURCE_NAME='selftest_write.py'","SOURCE_NAME='other.py'",'SOURCE_NAME is not <MODULE>.py'),
 ('write','op.py',"REQUEST_SCHEMA='WRITE_HOSTOPS02_SELFTEST_WRITE_REQUEST_V1'","REQUEST_SCHEMA='WRITE_HOSTOPS_PROVISION_REQUEST_V1'",'schema names are not'),
 ('write','op.py',"OPERATION='GO_WRITE_HOSTOPS02_CORE_SELFTEST_01'","OPERATION='GO_WRITE_SUPERVISOR_READER_PROVISION_01'",'OPERATION is not GO_WRITE_HOSTOPS02_'),
 ('read','op.py',"OPERATION='GO_READONLY_HOSTOPS02_CORE_SELFTEST_01'","OPERATION='GO_WRITE_HOSTOPS02_CORE_SELFTEST_02'",'OPERATION is not GO_WRITE_HOSTOPS02_'),
 ('read','op.py',"PHASE='READONLY_CORE_SELFTEST_NEVER_DISPATCHED'","PHASE='WRITE_CORE_SELFTEST'",'PHASE does not begin with'),
 ('write','op.py',"REFUSED_OUTCOME='REFUSED_NOTHING_CHANGED'","REFUSED_OUTCOME='SELFTEST_ALL_EFFECTS_VERIFIED'",'the success outcome is also the name of another outcome'),
 ('write','op.py',"'core_sha256':CORE_SHA256,","'core_sha256':'0'*64,",'SCOPE lacks operation, dates, statement, core_sha256'),
 ('write','op.py',"'limits':{'max_seconds':MAX_SECONDS,","'limits':{'max_seconds':61,",'SCOPE lacks operation'),
 ('write','op.py',"'command_classes':COMMAND_CLASSES,","'command_classes':dict(COMMAND_CLASSES,QUICK={'seconds':59,'output_bytes':1}),",'SCOPE does not carry commands, binaries, command_classes'),
 ('write','op.py',"SCOPE_SHA256=sha(canonical(SCOPE))","SCOPE_SHA256='1'*64",'SCOPE_SHA256 is not the hash of SCOPE'),
 ('read','op.py',"'QUICK','READ'),\n          'container':","'QUICK','EFFECT'),\n          'container':",'is an EFFECT in a source that does not write'),
 ('write','op.py',"['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','READ')","['image','inspect','--format',IMAGE_FORMAT],'one image ID or reference','QUICK','EFFECT')",'does not fit the docker verb'),
 ('write','op.py',"command_row('docker',RUN_PREFIX,","command_row('docker',['run','-d'],",'an attached run starts with run --rm'),
 ('write','op.py',"command_row('docker',RUN_PREFIX,","command_row('docker',[word for word in RUN_PREFIX if word not in ('--pull','never')],",'an attached run starts with run --rm'),
 ('write','op.py',"command_row('docker',RUN_PREFIX,","command_row('docker',RUN_PREFIX+['--privileged'],",'an attached run starts with run --rm'),
 ('write','op.py',"command_row('docker',RUN_PREFIX,","command_row('docker',RUN_PREFIX+['-v/:/host'],",'an attached run starts with run --rm'),
 ('read','op.py',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),","'container_list':command_row('docker',['exec','-i'],'x','QUICK','CONTAINER'),",'docker exec is not used by this core'),
 ('read','op.py',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),","'container_list':command_row('docker',['container','inspect','--format','{{json .Config.Env}}'],'x','QUICK','READ'),",'names the environment of a container in a fixed template'),
 ('read','op.py',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),","'container_list':command_row('docker',['container','inspect','--format'],'any template','QUICK','READ'),",'a template given at call time exists only for container_environment'),
 ('read','op.py',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),","'container_list':command_row('docker',['ps','-a'],None,'SLOW','READ'),",'is not a command_row()'),
 ('read','op.py',"BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}","BINARIES={'docker':['/usr/bin/docker'],'systemctl':['/usr/bin/systemctl']}\nEXTRA=command_row('systemctl',['restart','x.service'],None,'SWITCH','READ')",None),
 ('read','op.py',"class Native(NativeRead,NativeRunner,NativeLock):","class Native(NativeRead,NativeRunner,NativeLock):\n    def mkdir(self,name,mode,dir_fd):pass",'a reading source carries the files part or a Native that can create'),
 ('read','spec.py',"PARTS=['core','runner','docker','parents','lock']","PARTS=['core','runner','docker','parents','files','lock']",'a reading source carries the files part'),
 ('write','op.py',"import base64\n","import base64\nimport shutil\n",'imports outside the standard-library set'),
 ('write','op.py',"import base64\n","import base64\nimport socket\n",'imports outside the standard-library set'),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);os.chmod('/tmp',0o777)\n",'os members outside those of the carried parts'),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);os.rename('/a','/b')\n",'os members outside those of the carried parts'),
 ('read','op.py',"    gate()                                                    # first gate call","    os.mkdir('/tmp/x');gate()                                 # first gate call",'os members outside those of the carried parts'),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);eval('1')\n",'forbidden names'),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);print('x')\n",'forbidden names'),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);subprocess.run(['/bin/true'])\n",'subprocess use outside the runner'),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);subprocess.Popen(['/bin/true'],shell=True)\n",'subprocess use outside the runner'),
 ('write','op.py',"    begun,mark=clock(),monotonic()\n","    begun,mark=clock(),monotonic()\n    if (x:=1):pass\n",'ssignment expression'),
 ('write','op.py',"def success_of(plan):return COMPLETE_OUTCOME","def success_of(plan,/):return COMPLETE_OUTCOME",'ositional-only parameters'),
 ('write','op.py',"def success_of(plan):return COMPLETE_OUTCOME","def success(plan):return COMPLETE_OUTCOME",'does not define success_of'),
 ('write','op.py',"PLAN_KEYS=frozenset(('parent',","PLAN_KEYS=frozenset(('schema','parent',",'PLAN_KEYS overlaps the common plan keys'),
 ('write','op.py',"EVIDENCE_REQUIRED=True","EVIDENCE_REQUIRED=False",'EVIDENCE_REQUIRED / EVIDENCE_OPERATIONS'),
 ('write','spec.py',"STEM='HOSTOPS02_SELFTEST_WRITE'","STEM='HOSTOPS_PROVISION'",'SPEC_STEM'),
 ('write','spec.py',"PARTS=['core','runner','docker','parents','files','lock']","PARTS=['runner','core','docker','parents','files','lock']",'SPEC_PARTS'),
 ('write','spec.py',"PARTS=['core','runner','docker','parents','files','lock']","PARTS=['core','docker','parents','files','lock']",'SPEC_PARTS'),
 ('write','spec.py',"PARTS=['core','runner','docker','parents','files','lock']","PARTS=['core','runner','docker','files','parents','lock']",'SPEC_PARTS'),
 ('write','spec.py',"PARTS=['core','runner','docker','parents','files','lock']","PARTS=['core','runner','docker','parents','files','lock','scan']",'SPEC_PARTS'),
 ('write','spec.py',"MODULE='selftest_write'","MODULE='dispatch_once'",'SPEC_MODULE'),
 ('write','spec.py',"No action on import.","",'SPEC_HEADER'),
 ('write','spec.py',"'evidence_boot_id_sha256':None}","'evidence_boot_id_sha256':None,'extra':None}",'UNBOUND_PLAN_KEYS'),
 ('write','spec.py',"'parent':None,","",'UNBOUND_PLAN_KEYS'),
 ('write','op.py',"import base64\n","import base64\n# ==== BEGIN CORE (x) ====\n",'OPERATION_PART_CARRIES_A_MARKER'),
 # frozen means the names too: the operation's own part cannot bind a name of the carried parts again, nor change what one holds
 ('write','op.py',"import base64\n","import base64\nIMAGE_ID='sha256:'+'f'*64\n","binds names of the frozen core again: ['IMAGE_ID']"),
 ('read','op.py',"import base64\n","import base64\ndef need(ok,code):pass\n","binds names of the frozen core again: ['need']"),
 ('write','op.py',"import base64\n","import base64\nimport json\n","binds names of the frozen core again: ['json']"),
 ('write','op.py',"import base64\n","import base64\nclass Gate:pass\n","binds names of the frozen core again: ['Gate']"),
 ('read','op.py',"import base64\n","import base64\nfor MAX_SECONDS in (600,):pass\n","binds names of the frozen core again: ['MAX_SECONDS']"),
 ('write','op.py',"import base64\n","import base64\nif True:\n    try:AFTER_EFFECT_RESERVE_SECONDS=0\n    finally:pass\n","binds names of the frozen core again: ['AFTER_EFFECT_RESERVE_SECONDS']"),
 ('write','op.py',"import base64\n","import base64\nRUN_PREFIX+=['--tmpfs','/tmp']\n","binds names of the frozen core again: ['RUN_PREFIX']"),
 ('write','op.py',"import base64\n","import base64\nCOMMAND_CLASSES['RUN']['seconds']=55\n","stores into objects of the frozen core: ['COMMAND_CLASSES']"),
 ('write','op.py',"import base64\n","import base64\nGate.__call__=lambda self:60.0\n","stores into objects of the frozen core: ['Gate']"),
 ('read','op.py',"import base64\n","import base64\ndel COMMAND_VARIABLES['C3PO_BUILD_SHA']\n","stores into objects of the frozen core: ['COMMAND_VARIABLES']"),
 ('write','op.py',"import base64\n","import base64\nCOMMAND_ENVIRONMENT.update(HOME='/root')\n","constants of the frozen core differ once the operation part is loaded: ['COMMAND_ENVIRONMENT']"),
 ('read','op.py',"import base64\n","import base64\nDATE_SETS['READ'].__class__\nDATE_SETS.update(READ=('2026-10-11',))\n","constants of the frozen core differ once the operation part is loaded: ['DATE_SETS']"),
 # the operation's own part makes no system call and starts no process of its own
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);subprocess.Popen(['/bin/true'])\n","names a module it must not use itself: ['subprocess']"),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);time.sleep(1)\n","names a module it must not use itself: ['time']"),
 ('read','op.py',"    gate()                                                    # first gate call","    fcntl.flock(0,2);gate()                                   # first gate call","names a module it must not use itself: ['fcntl']"),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);ctypes.CDLL(None,use_errno=True).prctl(4,0,0,0,0)\n","names a module it must not use itself: ['ctypes']"),
 ('read','op.py',"import base64\n","import base64\nimport ctypes as c\n","imports a module it must not use itself: ['ctypes']"),
 ('write','op.py',"import base64\n","import base64\nfrom ctypes import CDLL\n","imports a module it must not use itself: ['ctypes']"),
 ('write','op.py',"import base64\n","import base64\nimport ctypes\n","binds names of the frozen core again: ['ctypes']"),
 ('write','op.py',"import base64\n","import base64\nfrom subprocess import Popen\n","imports a module it must not use itself: ['subprocess']"),
 ('read','op.py',"import base64\n","import base64\nimport time as clock_module\n","imports a module it must not use itself: ['time']"),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);os.unlink('/etc/x')\n","uses the os module for more than open flags: ['unlink']"),
 ('write','op.py',"            host.umask(0o077)\n","            host.umask(0o077);os.write(1,b'x')\n","uses the os module for more than open flags: ['write']"),
 ('read','op.py',"    gate()                                                    # first gate call","    system=os;gate()                                          # first gate call",'uses the os module for more than open flags: []'),
 ('read','op.py',"values=container_environment(commands,target['id'],plan['environment']['expected'])",
  "values=decode(commands.output('container_environment','{{json .Config.Env}}',target['id'],through='container_environment'))",'starts a command as if it were a helper of the core'),
 # the command table: two tools, a CONTAINER row is an attached run, binds only at call time, a docker read fixes its template
 ('read','op.py',"BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}","BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'sh':['/bin/sh']}",'BINARIES names a tool other than docker and systemctl'),
 ('read','op.py',"BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}","BINARIES={'docker':['/usr/bin/docker','docker']}",'or a path that is not an absolute path of that tool'),
 ('read','op.py',"BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}","BINARIES={'docker':['/usr/bin/docker','/bin/sh']}",'or a path that is not an absolute path of that tool'),
 ('read','op.py',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),","'container_list':command_row('docker',['rm','-f'],'x','QUICK','CONTAINER'),",'a CONTAINER row is an attached docker run'),
 ('read','op.py',"command_row('docker',RUN_PREFIX,","command_row('docker',RUN_PREFIX+['--mount','type=bind,source=/,target=/host'],",'takes its binds at call time (no -v, no fixed --mount)'),
 ('read','op.py',"command_row('docker',RUN_PREFIX,","command_row('docker',RUN_PREFIX+['--mount=type=bind,source=/,target=/host'],",'takes its binds at call time (no -v, no fixed --mount)'),
 ('write','op.py',"command_row('docker',RUN_PREFIX,","command_row('docker',RUN_PREFIX+['--cap-add','SYS_ADMIN'],",'adds no device or capability'),
 ('write','op.py',"command_row('docker',RUN_PREFIX,","command_row('docker',RUN_PREFIX+['--device','/dev/sda'],",'adds no device or capability'),
 ('read','op.py',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),","'container_list':command_row('docker',['ps','-a','--no-trunc'],None,'QUICK','READ'),",'a docker read fixes its --format'),
 # the one row that prints values of a container's environment (the secrets family's revision, CORE.md section 15)
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(('C3PO_EODHD_API_TOKEN',))],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),",'are read only through the fixed row of secret_environment_format(SECRET_ENVIRONMENT_NAMES), in a writing source'),
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],'one ID','QUICK','READ'),",'are read only through the fixed row of secret_environment_format(SECRET_ENVIRONMENT_NAMES), in a writing source'),
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'RUN_SHORT','READ'),",'are read only through the fixed row of secret_environment_format(SECRET_ENVIRONMENT_NAMES), in a writing source'),
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ',stdin=True),",'are read only through the fixed row of secret_environment_format(SECRET_ENVIRONMENT_NAMES), in a writing source'),
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ',tail=['--size']),",'are read only through the fixed row of secret_environment_format(SECRET_ENVIRONMENT_NAMES), in a writing source'),
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--size','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),",'are read only through the fixed row of secret_environment_format(SECRET_ENVIRONMENT_NAMES), in a writing source'),
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)+'{{json .Config.Env}}'],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),",'are read only through the fixed row of secret_environment_format(SECRET_ENVIRONMENT_NAMES), in a writing source'),
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),\n          'other':command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),",'names the environment of a container in a fixed template'),
 ('write','op.py',"SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),","'container_values':command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),",'names the environment of a container in a fixed template'),
 ('read','op.py',"'container_list':command_row('docker',['ps','-a','--no-trunc','--format',PS_FORMAT],None,'QUICK','READ'),","'container_list':command_row('docker',['container','inspect'],'one container','QUICK','READ'),",'a docker read fixes its --format'),
]
@pytest.mark.parametrize('which,name,old,new,message',RULES,ids=[str(index) for index in range(len(RULES))])
def test_assembly_refuses_a_source_that_breaks_a_rule(tmp_path,which,name,old,new,message):
    directory=copy_of(demos.WRITE if which=='write' else demos.READ,tmp_path/'op');edit(directory/name,old,new)
    if message is None:
        # the row is built but never enters COMMANDS: the table is what is signed, and the table is unchanged
        assert f.assembler().build(directory)
        edit(directory/'op.py',"SCOPE_STATEMENT=(","COMMANDS['restart']=EXTRA\nSCOPE_STATEMENT=(")
        message='a reading systemctl verb is kind READ; a verb that changes something needs ACTIVATION_ALLOWED and kind EFFECT'
    text=refused(directory);assert text.startswith('ASSEMBLY_REFUSED') and message in text,text
    assert not (directory/'build').exists(),'nothing is written for a refused source'

def test_ctypes_only_as_the_one_load_of_the_core():
    """The core part names ctypes once, to load the C library of the interpreter (dumps_disabled). The rule on the
    whole source refuses any other use: another library, errno not kept by ctypes, a second load, another member."""
    a=f.assembler();spec=a.load_spec(demos.WRITE);k=f.load(demos.WRITE)
    assert a.lint(spec,k.source,k.m)==[] and a.CTYPES_LOAD=='ctypes.CDLL(None,use_errno=True)' and 'ctypes' not in a.FORBIDDEN_NAMES
    assert 'ctypes' in a.OWN_MODULES_FORBIDDEN and 'ctypes' in a.IMPORTS_OF['core']
    anchor=b'if library is None:library=ctypes.CDLL(None,use_errno=True)';assert k.source.count(anchor)==1
    for new in (b"if library is None:library=ctypes.CDLL('libc.so.6',use_errno=True)",b'if library is None:library=ctypes.CDLL(None,use_errno=False)',
                b'if library is None:library=ctypes.CDLL(None,use_errno=1)',b'if library is None:library=ctypes.CDLL(None)',
                b'if library is None:library=ctypes.CDLL(None,use_errno=True,mode=0)',b'if library is None:library=ctypes.PyDLL(None,use_errno=True)',
                b'if library is None:library=ctypes.CDLL(None,use_errno=True);ctypes.CDLL(None,use_errno=True)',
                b'if library is None:library=ctypes.CDLL(None,use_errno=True);ctypes.memmove(0,0,0)',b'if library is None:library=ctypes.pythonapi'):
        broken=a.lint(spec,k.source.replace(anchor,new),k.m)
        assert any('ctypes is named for something else than ctypes.CDLL(None,use_errno=True)' in item for item in broken),(new,broken)

def test_assembly_allows_a_switching_verb_only_in_a_source_that_declares_activation(tmp_path):
    directory=copy_of(demos.WRITE,tmp_path/'op')
    edit(directory/'op.py',"BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}","BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker'],'systemctl':['/usr/bin/systemctl']}")
    edit(directory/'op.py',"SCOPE_STATEMENT=(","COMMANDS['enable']=command_row('systemctl',['enable','--now','c3po-x.timer'],None,'SWITCH','EFFECT')\nSCOPE_STATEMENT=(")
    assert 'needs ACTIVATION_ALLOWED and kind EFFECT' in refused(directory)
    edit(directory/'op.py',"ACTIVATION_ALLOWED=False","ACTIVATION_ALLOWED=True")
    files=f.assembler().build(directory);request=json.loads(files['REQUEST.UNBOUND.json'])
    assert request['activation_allowed'] is True and json.loads(files['GO.UNBOUND.json'])['activation_allowed'] is True
    assert json.loads(files['AUTHORITY.UNBOUND.json'])['activation_allowed'] is True and request['plan']['scope']['activation_allowed'] is True
    edit(directory/'op.py',"['enable','--now','c3po-x.timer'],None,'SWITCH','EFFECT')","['enable','--now','c3po-x.timer'],None,'SWITCH','READ')")
    assert 'needs ACTIVATION_ALLOWED and kind EFFECT' in refused(directory)

def test_assembly_refuses_a_core_that_is_not_the_pinned_one(tmp_path):
    copy=tmp_path/'core';copy.mkdir()
    for name in ('parts','reviewed_base'):shutil.copytree(str(CORE/name),str(copy/name))
    shutil.copy(str(CORE/'assemble.py'),str(copy/'assemble.py'));op=copy_of(demos.READ,tmp_path/'op')
    assert run(copy/'assemble.py','--check',op).returncode==1                           # nothing built yet
    assert run(copy/'assemble.py',op).returncode==0 and run(copy/'assemble.py','--check',op).stdout.strip()==b'BUILD_EQUAL'
    built=(op/'build'/'selftest_read.py').read_bytes()
    for relative,old,new in (('parts/core.py','MAX_SECONDS=60','MAX_SECONDS=61'),('parts/lock.py','MAX_LOCK_WAIT_SECONDS=20','MAX_LOCK_WAIT_SECONDS=21'),
                             ('reviewed_base/transport_once.py','seconds<=270','seconds<=271')):
        saved=(copy/relative).read_text();edit(copy/relative,old,new)
        done=run(copy/'assemble.py',op);assert done.returncode==1 and b'CORE_CHANGED '+relative.encode() in done.stderr
        assert run(copy/'assemble.py','--core').returncode==1 and (op/'build'/'selftest_read.py').read_bytes()==built
        (copy/relative).write_text(saved)
    # a part that the operation does not carry is checked as well: the generation is one hash for the whole core
    edit(copy/'parts'/'files.py','MAX_FILE_BYTES=1048576','MAX_FILE_BYTES=1048577')
    assert b'CORE_CHANGED parts/files.py' in run(copy/'assemble.py',op).stderr

def test_a_change_to_the_assembler_is_a_new_generation_and_moves_every_source_hash(tmp_path):
    """Why a signed tier 0 hash cannot move: the source names the hash of the assembler that pins every part."""
    copy=tmp_path/'core';copy.mkdir()
    for name in ('parts','reviewed_base'):shutil.copytree(str(CORE/name),str(copy/name))
    shutil.copy(str(CORE/'assemble.py'),str(copy/'assemble.py'));op=copy_of(demos.READ,tmp_path/'op')
    assert run(copy/'assemble.py',op).returncode==0;old=(op/'build'/'selftest_read.py').read_bytes();generation=f.sha((copy/'assemble.py').read_bytes())
    edit(copy/'assemble.py','MAX_UNBOUND_REQUEST_BYTES=40000','MAX_UNBOUND_REQUEST_BYTES=40001')
    assert run(copy/'assemble.py',op).returncode==0
    new=(op/'build'/'selftest_read.py').read_bytes();changed=f.sha((copy/'assemble.py').read_bytes())
    assert changed!=generation and new!=old and new.replace(changed.encode(),generation.encode())==old,'the two sources differ in the generation they name and in nothing else'
    assert json.loads((op/'build'/'ASSEMBLY.json').read_bytes())['core_sha256']==changed


def test_assembly_admits_the_secret_row_only_in_a_writing_source_and_in_its_exact_shape(tmp_path):
    """The write demonstration carries the row and is built; the read demonstration with the same constant and row is
    refused for that row alone; the operation part cannot start it as if it were the helper."""
    k=f.load(demos.WRITE);assert k.m.SECRET_ENVIRONMENT_ROW in k.m.COMMANDS and f.assembler().lint(f.assembler().load_spec(demos.WRITE),k.source,k.m)==[]
    directory=copy_of(demos.READ,tmp_path/'op')
    edit(directory/'op.py',"BINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}","SECRET_ENVIRONMENT_NAMES=('C3PO_EODHD_API_TOKEN',)\nBINARIES={'docker':['/usr/bin/docker','/usr/local/bin/docker']}")
    assert f.assembler().build(directory)
    edit(directory/'op.py',"          'verify':command_row(","          SECRET_ENVIRONMENT_ROW:command_row('docker',['container','inspect','--format',secret_environment_format(SECRET_ENVIRONMENT_NAMES)],SECRET_ENVIRONMENT_MIDDLE,'QUICK','READ'),\n          'verify':command_row(")
    text=refused(directory);assert "COMMANDS['container_secret_environment']: the values of a container's environment are read only through the fixed row" in text,text
    assert 'names the environment of a container in a fixed template' not in text
    directory=copy_of(demos.WRITE,tmp_path/'w')
    edit(directory/'op.py',"            host.umask(0o077)\n","            host.umask(0o077);commands.output(SECRET_ENVIRONMENT_ROW,'x',through=SECRET_ENVIRONMENT_ROW)\n")
    assert 'starts a command as if it were a helper of the core' in refused(directory)


def test_assembly_pins_the_secret_names_and_closes_the_ways_around_the_helpers(tmp_path):
    """Section 15 after the independent read: the row prints only provider token names; the operation part starts no
    command by a method of the host or of Commands, unpacks no keyword arguments but into dict(), names no getattr."""
    cases=[("SECRET_ENVIRONMENT_NAMES=('C3PO_EODHD_API_TOKEN','EODHD_API_TOKEN')","SECRET_ENVIRONMENT_NAMES=('C3PO_DATABASE_URL','EODHD_API_TOKEN')",
            'SECRET_ENVIRONMENT_NAMES outside the provider token names'),
           ("            host.umask(0o077)\n","            host.umask(0o077);host.run(['/usr/bin/docker','info'],gate,8)\n",'the operation part starts a command itself'),
           ("            host.umask(0o077)\n","            host.umask(0o077);commands.output('image','x')\n",'the operation part starts a command itself'),
           ("            host.umask(0o077)\n","            host.umask(0o077);commands.call('image','x')\n",'the operation part starts a command itself'),
           ("            host.umask(0o077)\n","            host.umask(0o077);container_list(commands,**{'docker_config':None})\n",'unpacks keyword arguments into a call other than dict()'),
           ("            host.umask(0o077)\n","            host.umask(0o077);getattr(commands,'out'+'put')('image','x')\n",'the operation part names getattr')]
    for index,(old,new,message) in enumerate(cases):
        directory=copy_of(demos.WRITE,tmp_path/('op%d'%index));edit(directory/'op.py',old,new)
        text=refused(directory);assert message in text,(index,text)
    assert f.assembler().SECRET_NAMES_ALLOWED==frozenset(('C3PO_EODHD_API_TOKEN','EODHD_API_TOKEN','C3PO_FINNHUB_API_TOKEN','FINNHUB_API_TOKEN','C3PO_FMP_API_TOKEN','FMP_API_TOKEN'))
