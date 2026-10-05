"""Real-Docker shapes of the K9 interface note (N-7) and of K12 (U1-U6, U9, U10) on the backend image BUILT FROM THIS
CHECKOUT (release dd4ec4bb; run_group.py builds it as the pipeline does). What no emulation can show:

  - the image's `timeout` is busybox; the supported --init prefix ends a longer command with 137; no-init is diagnostic only;
  - `create --pull never` refuses an image that is not local and pulls nothing; `create` prints exactly the ID;
  - K9's fixed create prefix (--pull never --init --user 0:0 --read-only --cap-drop ALL --security-opt
    no-new-privileges --restart no) with two labels, two --env-file, two --env and two binds accepted, then started;
    inside: uid 0, no effective capability, no_new_privs, docker-init as PID 1, the root filesystem read-only, the tools
    bind read-only, the day bind writable, a 0600 root file of the read-only bind readable by root;
  - the env files read by the CLI and given to the container under --read-only: each value equal to the literal after
    the first "=" of its line (compared by SHA-256 inside the container; no value is printed anywhere); the CLI's
    reading of harder lines (quotes, blanks, "#", "$") recorded, not judged;
  - single-file binds (read-only: readable, write refused; read-write: written through), `python -I -B <file>` of a
    file in a read-only bind (K12-U9), the nested read-write receipts bind under a read-only day bind (stage's shape);
  - the inspect formats AS THE SEALED SOURCES HOLD THEM (K9R K9_LAUNCHED_FORMAT, K9W K9W_LAUNCHED_FORMAT, K12_FORMAT,
    read from op.py by the syntax tree, never imported) on this engine: the keys, the labels, State.OOMKilled true for a
    container killed by the kernel's OOM killer, a never-started container's StartedAt, .Mounts field names and RW;
  - `docker logs` of an exited container gives exactly the writer's stdout line (K12-U3); `docker stop -t 5` ends a
    parked python through docker-init with 143 (K12-U5); `docker rm` of several IDs with one missing (K12-U6);
    `create` with DOCKER_CONFIG of an empty directory and no HOME (K12-U1);
  - the release's compose file rendered with the project name c3po (the network names c3po_c3po_internal, internal,
    and c3po_db_loopback), and a throwaway project c3po with those two networks and a stand-in `db` listener in the
    release image: `db` resolves and answers on both networks and not on bridge; c3po_c3po_internal has no egress,
    c3po_db_loopback has (one TCP connection to github.com:443) (N-4, K12-U10);
  - the time of every CLI call (the budgets of the note's section 4.1 are judged on the host, not here).

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner, as root. NEVER the production host. It refuses unless Linux, uid 0,
HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted, and unless nothing it would create exists. Every
value in it is a fake test value. It removes everything it created (containers hk9ci-*, the compose project, its tag,
its work directory under /var/tmp).

usage: sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B proof/docker_shapes.py \
           <image ID> <release tree> --out <file>
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when all ran and an
expectation is not met; 1 for a refusal.
"""
import ast
import hashlib
import json
import os
import shutil
import socketserver
import threading
import ipaddress
import subprocess
import sys
import tempfile
import time

HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)
SCHEMA='HOSTOPS02_K9_PROOF_DOCKER_SHAPES_V1'
RELEASE='dd4ec4bb8dab4d8b0372b0f9eabc90bf6443e858'
PREFIX='hk9ci-'
TAG='hostops02-k9-ci/shapes:db'
NEVER_STARTED='0001-01-01T00:00:00Z'
DOCKER=next((path for path in ('/usr/bin/docker','/usr/local/bin/docker') if os.path.isfile(path)),'docker')
ENV={'PATH':'/usr/bin:/bin:/usr/local/bin','HOME':'/root'}
AK='a1'*32
RQ='b2'*32
TIMINGS=[]

def sha(raw):return hashlib.sha256(raw if isinstance(raw,bytes) else raw.encode()).hexdigest()
def refuse(text):
    sys.stderr.write('REFUSED: %s\n'%text);raise SystemExit(1)

def cli(*words,env=None,timeout=120,label=None,stdin=None):
    started=time.monotonic()
    done=subprocess.run([DOCKER]+list(words),stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env or ENV,timeout=timeout,input=stdin)
    elapsed=round(time.monotonic()-started,3)
    TIMINGS.append({'call':label or ' '.join(words[:2]),'seconds':elapsed,'exit':done.returncode})
    return done.returncode,done.stdout.decode('utf-8','replace'),done.stderr.decode('utf-8','replace'),elapsed

# ---------------------------------------------------------------- the formats, as the sealed sources hold them
class Unsupported(Exception):pass
def evaluate(node,names):
    if isinstance(node,ast.Constant):return node.value
    if isinstance(node,ast.Name):
        if node.id in names:return names[node.id]
        raise Unsupported(node.id)
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):return evaluate(node.left,names)+evaluate(node.right,names)
    if isinstance(node,(ast.Tuple,ast.List)):return tuple(evaluate(item,names) for item in node.elts)
    if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='frozenset' and len(node.args)==1:return frozenset(evaluate(node.args[0],names))
    raise Unsupported(type(node).__name__)
def constants(path,wanted):
    with open(path,'rb') as handle:tree=ast.parse(handle.read())
    names={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
            try:names[node.targets[0].id]=evaluate(node.value,names)
            except Unsupported:pass
    return {name:names.get(name) for name in wanted}
def sealed_constants():
    with open(os.path.join(HERE,'UNITS.json'),'rb') as handle:units=json.load(handle)['units']
    found={}
    for suffix,wanted in (('k9_phase_read',('K9_LAUNCHED_FORMAT',)),('k9_phase_step',('K9W_LAUNCHED_FORMAT','K9W_LAUNCHED_KEYS')),
                          ('k12_collect',('K12_FORMAT','K12_INSPECT_KEYS','K12_MOUNT_KEYS','K12_NEVER_STARTED'))):
        unit=next((row for row in units if row['dest'].rsplit('/',1)[-1]==suffix),None)
        path=os.path.join(ROOT,unit['dest'],'op.py') if unit else None
        values=constants(path,wanted) if path and os.path.isfile(path) else {name:None for name in wanted}
        for name,value in values.items():found[name]={'value':value,'from':(unit['dest']+'/op.py') if unit else None,'seal':unit['seal_sha256'] if unit else None}
    return found

# ---------------------------------------------------------------- the stand-in programs (run in the image; standard library)
INSIDE=r'''import hashlib, json, os, sys
expected = json.loads(sys.argv[1])
def sha(value): return hashlib.sha256(value.encode()).hexdigest()
out = {'env': {name: {'present': name in os.environ, 'equal': name in os.environ and sha(os.environ[name]) == digest} for name, digest in expected['env'].items()},
       'other_c3po_names': sorted(name for name in os.environ if name.startswith('C3PO_') and name not in expected['env'] and name not in expected['words']),
       'words': {name: os.environ.get(name) == value for name, value in expected['words'].items()},
       'uid': os.getuid(), 'gid': os.getgid(), 'home_set': 'HOME' in os.environ}
status = dict(line.split(':', 1) for line in open('/proc/self/status').read().splitlines() if ':' in line)
out['cap_eff_zero'] = int(status['CapEff'].strip(), 16) == 0
out['cap_bnd_zero'] = int(status['CapBnd'].strip(), 16) == 0
out['no_new_privs'] = status.get('NoNewPrivs', '').strip() == '1'
out['pid1'] = os.path.basename(open('/proc/1/cmdline', 'rb').read().split(b'\0')[0].decode())
def writable(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); os.close(fd); os.unlink(path); return True
    except OSError as error:
        return error.errno
out['root_write'] = writable('/hk9ci-probe')
out['tmp_write'] = writable('/tmp/hk9ci-probe')
out['tools_write'] = writable('/c3po-k9-tools/hk9ci-probe')
out['tools_private_file_read'] = sha(open('/c3po-k9-tools/runner.py').read()) == expected['runner_sha256']
fd = os.open('/c3po-k9-day/receipts/probe.RECEIPT.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
os.write(fd, json.dumps(out, sort_keys=True).encode()); os.fsync(fd); os.close(fd)
'''

def guard(arguments):
    if len(arguments)!=4 or arguments[2]!='--out' or not arguments[0].startswith('sha256:'):refuse('usage: docker_shapes.py <image ID> <release tree> --out <file>')
    if not sys.platform.startswith('linux') or os.geteuid()!=0:refuse('Linux and uid 0 only')
    if os.environ.get('HOSTOPS_THROWAWAY_RUNNER')!='yes' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':refuse('a throwaway GitHub-hosted runner only')
    status,text,_,_=cli('ps','-a','--format','{{.Names}}')
    if status!=0:refuse('docker ps failed')
    if any(name.startswith(PREFIX) for name in text.split()):refuse('a container %s* exists'%PREFIX)
    status,text,_,_=cli('network','ls','--format','{{.Name}}')
    if any(name.startswith('c3po_') for name in text.split()):refuse('a network c3po_* exists: this is not a throwaway runner')
    if cli('image','inspect',TAG)[0]==0:refuse('%s exists'%TAG)

def put(path,raw,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,mode);os.write(fd,raw if isinstance(raw,bytes) else raw.encode());os.fchmod(fd,mode);os.close(fd)

class Shapes:
    def __init__(self,image,release_tree,work):
        self.image=image;self.release_tree=release_tree;self.work=work;self.out={};self.compose_up=None;self.tagged=False
        self.formats=sealed_constants()
        for name in ('secrets','tools','day','day/receipts','one','empty-config','deploy','net'):os.makedirs(os.path.join(work,name),mode=0o700)
        # the production-like env files: fake values, one per line, NAME=VALUE (K3-K9 writes these two files)
        self.provider_lines={'C3PO_EODHD_API_TOKEN':'fake-eodhd-token-0001','C3PO_FINNHUB_API_TOKEN':'fake-finnhub=token=0002','C3PO_FMP_API_TOKEN':'fake fmp token 0003'}
        self.risk_lines={'C3PO_R2D2_RISK_DATABASE_URL':'postgresql://c3po_v2_risk_reader:fake%2Fpassword0004@db:5432/c3po'}
        self.provider=os.path.join(work,'secrets','provider.env');self.risk=os.path.join(work,'secrets','risk-db.env')
        put(self.provider,''.join('%s=%s\n'%item for item in self.provider_lines.items()))
        put(self.risk,''.join('%s=%s\n'%item for item in self.risk_lines.items()))
        self.runner=os.path.join(work,'tools','runner.py');put(self.runner,INSIDE)

    def shape(self,label,action):
        try:self.out[label]=dict(action(),ok=True)
        except Exception as error:self.out[label]={'ok':False,'error':type(error).__name__,'message':str(error)[:300]}

    def run_inside(self,*words,timeout=120):
        return cli('run','--rm','--pull','never','--network','none','--read-only',*words,timeout=timeout,label='run '+(words[-1][:30] if words else ''))

    # -------------------------------------------------------- shapes
    def image_facts(self):
        status,text,_,_=cli('image','inspect','--format','{{.Id}} {{ index .Config.Labels "org.opencontainers.image.revision" }}',self.image)
        identifier,_,label=text.strip().partition(' ')
        return {'id_equal':identifier==self.image,'revision_label':label}

    def timeout_busybox(self):
        status,which,_,_=self.run_inside('--entrypoint','sh',self.image,'-c','readlink -f "$(command -v timeout)"')
        plain=self.run_inside(self.image,'timeout','-s','KILL','2','sleep','30',timeout=60)
        init=self.run_inside('--init',self.image,'timeout','-s','KILL','2','sleep','30',timeout=60)
        short=self.run_inside('--init',self.image,'timeout','-s','KILL','30','python','-I','-c','print("k9-short")',timeout=60)
        return {'timeout_binary':which.strip(),'kill_exit':plain[0],'kill_seconds':plain[3],'kill_with_init_exit':init[0],'kill_with_init_seconds':init[3],
                'short_exit':short[0],'short_stdout':short[1].strip()}

    def pull_never(self):
        missing='sha256:'+'0'*64
        by_id=cli('create','--pull','never','--name',PREFIX+'pull-never-id',missing)
        by_tag=cli('create','--pull','never','--name',PREFIX+'pull-never-tag','busybox:hk9ci-never-pulled')
        after=cli('image','inspect','busybox:hk9ci-never-pulled')
        return {'by_id_exit':by_id[0],'by_tag_exit':by_tag[0],'tag_absent_after':after[0]!=0,'stdout_empty':not by_id[1].strip() and not by_tag[1].strip()}

    def k9_create(self):
        name=PREFIX+'20261006-collect_launch'
        words=['create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--restart','no',
               '--name',name,'--label','c3po.k9.attempt_key='+AK,'--label','c3po.k9.request_sha256='+RQ,'--network','none',
               '--env-file',self.provider,'--env-file',self.risk,'--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true','--env','C3PO_BUILD_SHA='+RELEASE,
               '--mount','type=bind,source=%s,target=/c3po-k9-tools,readonly'%os.path.join(self.work,'tools'),
               '--mount','type=bind,source=%s,target=/c3po-k9-day'%os.path.join(self.work,'day'),self.image]
        expected={'env':{key:sha(value) for key,value in dict(self.provider_lines,**self.risk_lines).items()},
                  'words':{'C3PO_R2D2_V2_PRODUCERS_ENABLED':'true','C3PO_BUILD_SHA':RELEASE},'runner_sha256':sha(INSIDE)}
        command=['timeout','-s','KILL','60','python','-I','/c3po-k9-tools/runner.py',json.dumps(expected,sort_keys=True,separators=(',',':'))]
        status,stdout,stderr,_=cli(*(words+command),label='create (K9 prefix)')
        lines=stdout.splitlines();identifier=lines[0] if lines else ''
        result={'create_exit':status,'create_stdout_is_one_64_hex_line':len(lines)==1 and len(identifier)==64 and all(c in '0123456789abcdef' for c in identifier),
                'create_stderr_empty':not stderr.strip()}
        if status!=0:return dict(result,create_error=stderr.strip()[:300])
        result['start_exit']=cli('start',identifier,label='start')[0]
        waited=cli('wait',identifier,timeout=120,label='wait');result['wait_exit_code']=waited[1].strip()
        result['inspect']=self.inspect_all(identifier,command)
        receipt=os.path.join(self.work,'day','receipts','probe.RECEIPT.json')
        if os.path.isfile(receipt):
            info=os.lstat(receipt)
            with open(receipt,'rb') as handle:result['inside']=json.load(handle)
            result['receipt_on_host']={'uid':info.st_uid,'gid':info.st_gid,'mode':oct(info.st_mode&0o7777),'links':info.st_nlink}
        else:
            result['inside']=None
        result['logs_stdout_empty']=cli('logs',identifier,label='logs')[1]==''
        result['remove_exit']=cli('rm',identifier,label='rm')[0]
        return result

    def inspect_all(self,identifier,command=None):
        rows={}
        for key,name in (('k9r','K9_LAUNCHED_FORMAT'),('k9w','K9W_LAUNCHED_FORMAT'),('k12','K12_FORMAT')):
            form=self.formats[name]['value']
            if not form:rows[key]={'format':'NOT_STAGED'};continue
            status,text,stderr,elapsed=cli('container','inspect','--format',form,identifier,label='inspect '+key)
            try:value=json.loads(text)
            except ValueError:value=None
            rows[key]={'exit':status,'json':value,'seconds':elapsed,'stderr':stderr.strip()[:200]}
        rows['k9r_k9w_formats_identical']=self.formats['K9_LAUNCHED_FORMAT']['value']==self.formats['K9W_LAUNCHED_FORMAT']['value']
        return rows

    def env_file_literal(self):
        lines=['A_PLAIN=plain-value','A_QUOTED="quoted value"',"A_SINGLE='single quoted'",'A_LEADING=  leading blanks','A_TRAILING=trailing blanks  ',
               'A_HASH=value # not a comment','A_EMPTY=','A_DOLLAR=$HOME/x','A_EQUALS=a=b=c','   A_INDENTED=indented','# a comment line','','A_LAST=last']
        path=os.path.join(self.work,'secrets','edge.env');put(path,'\n'.join(lines)+'\n')
        literal={}
        for line in lines:
            stripped=line.strip()
            if not stripped or stripped.startswith('#'):continue
            name,_,value=line.partition('=');literal[name.strip()]=value
        script=('import hashlib,json,os,sys;names=json.loads(sys.argv[1]);'
                'print(json.dumps({n:(hashlib.sha256(os.environ[n].encode()).hexdigest() if n in os.environ else None) for n in names}))')
        status,text,stderr,_=self.run_inside('--env-file',path,self.image,'python','-I','-c',script,json.dumps(sorted(literal)))
        seen=json.loads(text) if status==0 else {}
        return {'exit':status,'recorded_not_judged':{name:('ABSENT' if seen.get(name) is None else 'LITERAL_AFTER_FIRST_EQUALS' if seen[name]==sha(value)
                                                           else 'STRIPPED' if seen[name]==sha(value.strip()) else 'OTHER') for name,value in literal.items()},
                'stderr':stderr.strip()[:200]}

    def single_file_binds(self):
        secret=os.path.join(self.work,'one','password');put(secret,'fake-password-0005\n')
        writable=os.path.join(self.work,'one','out.json');put(writable,'{}\n')
        script_file=os.path.join(self.work,'one','writer.py');put(script_file,'import sys\nsys.stdout.write("k12-writer-line\\n")\n',0o600)
        reader=('import errno,hashlib,json,os;r={};r["sha"]=hashlib.sha256(open("/c3po-one/password","rb").read()).hexdigest()\n'
                'try:\n open("/c3po-one/password","ab").write(b"x");r["write"]="ALLOWED"\nexcept OSError as e:\n r["write"]=errno.errorcode.get(e.errno)\n'
                'f=open("/c3po-one/out.json","r+b");f.write(b"{\\"w\\":1}\\n");f.close();print(json.dumps(r))')
        status,text,stderr,_=self.run_inside('--mount','type=bind,source=%s,target=/c3po-one/password,readonly'%secret,
                                               '--mount','type=bind,source=%s,target=/c3po-one/out.json'%writable,self.image,'python','-I','-c',reader)
        seen=json.loads(text) if status==0 else {}
        with open(writable,'rb') as handle:written=handle.read()
        run_file=self.run_inside('--mount','type=bind,source=%s,target=/c3po-k12/writer.py,readonly'%script_file,self.image,'python','-I','-B','/c3po-k12/writer.py')
        day=os.path.join(self.work,'day')
        nested=('import errno,json,os\ndef w(p):\n try:\n  fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd);return "WRITTEN"\n except OSError as e:\n  return errno.errorcode.get(e.errno)\n'
                'print(json.dumps({"day":w("/c3po-k9-day/hk9ci-nested"),"receipts":w("/c3po-k9-day/receipts/hk9ci-nested")}))')
        stage=self.run_inside('--mount','type=bind,source=%s,target=/c3po-k9-day,readonly'%day,'--mount','type=bind,source=%s,target=/c3po-k9-day/receipts'%os.path.join(day,'receipts'),
                              self.image,'python','-I','-c',nested)
        for leftover in ('hk9ci-nested',):
            for folder in (day,os.path.join(day,'receipts')):
                if os.path.lexists(os.path.join(folder,leftover)):os.unlink(os.path.join(folder,leftover))
        return {'readonly_file_exit':status,'readonly_file_sha_equal':seen.get('sha')==sha(b'fake-password-0005\n'),'readonly_file_write':seen.get('write'),
                'readwrite_file_written_through':written==b'{"w":1}\n','python_file_in_readonly_bind_exit':run_file[0],'python_file_stdout':run_file[1],
                'nested':json.loads(stage[1]) if stage[0]==0 else {'exit':stage[0],'stderr':stage[2].strip()[:200]},'stderr':stderr.strip()[:200]}

    def oom_killed(self):
        status,stdout,stderr,_=cli('create','--pull','never','--init','--network','none','--read-only','--memory','64m','--memory-swap','64m',
                                   '--name',PREFIX+'oom','--label','c3po.k9.attempt_key='+AK,'--label','c3po.k9.request_sha256='+RQ,
                                   self.image,'python','-I','-c','b=b"\\x01"*(1<<30)\nprint(len(b))',label='create (oom)')
        if status!=0:return {'create_exit':status,'stderr':stderr.strip()[:300]}
        identifier=stdout.strip()
        cli('start',identifier,label='start');cli('wait',identifier,timeout=120,label='wait')
        rows=self.inspect_all(identifier)
        cli('rm',identifier,label='rm')
        return {'inspect':rows}

    def logs_stop_rm(self):
        writer=('import sys;sys.stdout.write("{\\"k12\\":\\"the writer line\\"}\\n");sys.stdout.flush();sys.stderr.write("to-stderr\\n")')
        status,stdout,_,_=cli('create','--pull','never','--init','--network','none','--read-only','--name',PREFIX+'logs',self.image,'python','-I','-c',writer,label='create (logs)')
        logs_id=stdout.strip();cli('start',logs_id,label='start');cli('wait',logs_id,timeout=60,label='wait')
        logs=cli('logs',logs_id,label='logs')
        status,stdout,_,_=cli('create','--pull','never','--init','--network','none','--read-only','--name',PREFIX+'stop',self.image,
                              'python','-I','-c','import time;time.sleep(600)',label='create (parked)')
        stop_id=stdout.strip();cli('start',stop_id,label='start');time.sleep(2)
        stopped=cli('stop','-t','5',stop_id,label='stop -t 5')
        state=cli('container','inspect','--format','{{json .State.ExitCode}} {{json .State.OOMKilled}} {{json .State.Status}}',stop_id)[1].split()
        stop_logs=cli('logs',stop_id,label='logs')
        missing='0'*64
        removed=cli('rm',logs_id,stop_id,missing,label='rm several')
        gone=[cli('container','inspect',identifier)[0]!=0 for identifier in (logs_id,stop_id)]
        _,driver,_,_=cli('info','--format','{{.LoggingDriver}}')
        return {'logging_driver':driver.strip(),'logs_exit':logs[0],'logs_stdout_exact':logs[1]=='{"k12":"the writer line"}\n','logs_stderr_exact':logs[2]=='to-stderr\n',
                'stop_exit':stopped[0],'stop_seconds':stopped[3],'stopped_exit_code':state[0] if state else None,'stopped_oom':state[1] if len(state)>1 else None,
                'stopped_logs_empty':stop_logs[1]=='' and stop_logs[2]=='','rm_several_exit':removed[0],'rm_several_stdout':removed[1].split(),
                'rm_several_stdout_names_the_two':sorted(removed[1].split())==sorted([logs_id,stop_id]),'both_removed':all(gone)}

    def docker_config_empty(self):
        env={'PATH':'/usr/bin:/bin:/usr/local/bin','DOCKER_CONFIG':os.path.join(self.work,'empty-config')}
        status,stdout,stderr,_=cli('create','--pull','never','--init','--user','0:0','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',
                                   '--restart','no','--name',PREFIX+'k12-config','--label','c3po.k12.request_sha256='+RQ,'--label','c3po.k12.capacity_request_sha256='+AK,
                                   '--network','none','--env-file',self.provider,'--env-file',self.risk,'--env','C3PO_R2D2_V2_PRODUCERS_ENABLED=true',
                                   self.image,'true',env=env,label='create (empty DOCKER_CONFIG, no HOME)')
        identifier=stdout.strip()
        rows=self.inspect_all(identifier) if status==0 else {}
        if status==0:cli('rm',identifier,label='rm')
        return {'create_exit':status,'stdout_one_id':len(stdout.splitlines())==1 and len(identifier)==64,'stderr':stderr.strip()[:200],
                'config_directory_still_empty':os.listdir(os.path.join(self.work,'empty-config'))==[],'never_started_inspect':rows}

    def compose_networks(self):
        deploy=os.path.join(self.work,'deploy')
        shutil.copytree(os.path.join(self.release_tree,'c3po'),os.path.join(deploy,'c3po'),symlinks=True)
        put(os.path.join(deploy,'.env'),'')
        status,text,stderr,_=cli('compose','--project-name','c3po','--env-file',os.path.join(deploy,'.env'),'-f',os.path.join(deploy,'c3po','compose.yml'),
                                 'config','--format','json',label='compose config (release)')
        rendered=json.loads(text) if status==0 else {}
        networks={key:{'name':value.get('name'),'internal':value.get('internal',False),'external':value.get('external',False)} for key,value in rendered.get('networks',{}).items()}
        result={'render_exit':status,'render_stderr':stderr.strip()[:300],'networks':networks,
                'db_networks':sorted((rendered.get('services',{}).get('db',{}).get('networks') or {}))}
        # a throwaway project c3po: the two networks of the release and a stand-in db listener in the release image
        if cli('tag',self.image,TAG)[0]==0:self.tagged=True
        listener=('import socket\ns=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(("0.0.0.0",5432));s.listen(8)\n'
                  'while True:\n c,_=s.accept();c.sendall(b"hk9ci-db\\n");c.close()\n')
        compose=('services:\n  db:\n    image: %s\n    command: ["python","-I","-c",%s]\n    read_only: true\n    networks: [c3po_internal, db_loopback]\n'
                 'networks:\n  c3po_internal:\n    internal: true\n  db_loopback: {}\n')%(TAG,json.dumps(listener))
        net=os.path.join(self.work,'net');put(os.path.join(net,'compose.yml'),compose,0o644)
        self.compose_up=net
        up=cli('compose','--project-name','c3po','-f',os.path.join(net,'compose.yml'),'up','-d','--no-build','--pull','never',timeout=180,label='compose up (stand-in db)')
        result['up_exit']=up[0];result['up_stderr_tail']=up[2].strip()[-300:]
        probe=('import socket,sys\nhost,port=sys.argv[1],int(sys.argv[2])\ntry:\n c=socket.create_connection((host,port),timeout=5);data=c.recv(16);c.close();print("CONNECTED",data.decode().strip())\n'
               'except OSError as e:\n print("FAILED",type(e).__name__);sys.exit(3)')
        def connect(network,host,port):
            status,text,_,_=cli('run','--rm','--pull','never','--network',network,'--read-only',self.image,'python','-I','-c',probe,host,str(port),timeout=60,label='run probe')
            return text.strip() or 'EXIT %s'%status
        for _ in range(20):
            if connect('c3po_c3po_internal','db',5432).startswith('CONNECTED'):break
            time.sleep(1)
        result['probes']={'internal_db':connect('c3po_c3po_internal','db',5432),'loopback_db':connect('c3po_db_loopback','db',5432),
                          'bridge_db':connect('bridge','db',5432)}
        status,gateway,_,_=cli('network','inspect','--format','{{(index .IPAM.Config 0).Gateway}}','bridge',label='default bridge gateway')
        if status!=0:raise RuntimeError('default bridge gateway unavailable')
        gateway=str(ipaddress.IPv4Address(gateway.strip()))
        with ControlledEndpoint() as endpoint:
            result['probes'].update({
                'bridge_egress_control':connect('bridge',gateway,endpoint.port),
                'internal_egress':connect('c3po_c3po_internal',gateway,endpoint.port),
                'loopback_egress':connect('c3po_db_loopback',gateway,endpoint.port)})
        result['egress_scope']='controlled CI-host endpoint outside both tested networks; not a public Internet/TLS proof'
        result['internal_flag']=cli('network','inspect','--format','{{.Internal}}','c3po_c3po_internal')[1].strip()
        down=cli('compose','--project-name','c3po','-f',os.path.join(net,'compose.yml'),'down','--timeout','2',timeout=120,label='compose down')
        self.compose_up=None
        result['down_exit']=down[0]
        result['networks_left']=[name for name in cli('network','ls','--format','{{.Name}}')[1].split() if name.startswith('c3po_')]
        return result

    def cleanup(self):
        if self.compose_up:cli('compose','--project-name','c3po','-f',os.path.join(self.compose_up,'compose.yml'),'down','--timeout','2',timeout=120)
        _,text,_,_=cli('ps','-a','--format','{{.ID}} {{.Names}}')
        for line in text.splitlines():
            identifier,_,name=line.partition(' ')
            if name.startswith(PREFIX):cli('rm','-f',identifier)
        if self.tagged:cli('image','rm',TAG)
        shutil.rmtree(self.work,ignore_errors=True)

class ControlledEndpoint:
    """A disposable CI-host listener, outside both tested Compose networks.
    Positive controls must reach the same marker before a negative result is meaningful.
    This proves the tested route, not unrestricted Internet or TLS availability.
    """
    def __enter__(self):
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):self.request.sendall(b'hk9ci-egress\n')
        self.server=socketserver.ThreadingTCPServer(('0.0.0.0',0),Handler)
        self.server.daemon_threads=True
        self.port=self.server.server_address[1]
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        return self
    def __exit__(self,*exc):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

def expectations(out,formats):
    def get(*path):
        node=out
        for key in path:
            if not isinstance(node,dict):return None
            node=node.get(key)
        return node
    k9r=get('k9_create','inspect','k9r','json') or {}
    k12=get('k9_create','inspect','k12','json') or {}
    inside=get('k9_create','inside') or {}
    keys=formats['K9W_LAUNCHED_KEYS']['value'];k12keys=formats['K12_INSPECT_KEYS']['value'];mountkeys=formats['K12_MOUNT_KEYS']['value']
    oom=get('oom_killed','inspect','k9r','json') or {}
    never=get('docker_config_empty','never_started_inspect','k12','json') or {}
    probes=get('compose_networks','probes') or {}
    networks=get('compose_networks','networks') or {}
    staged=lambda name:formats[name]['value'] is not None
    return {
        'the image is the release build (its ID, the revision label)':get('image_facts','id_equal') is True and get('image_facts','revision_label')==RELEASE,
        "the image's timeout is busybox":str(get('timeout_busybox','timeout_binary')).endswith('busybox'),
        'timeout -s KILL with the supported --init prefix ends a longer command with 137':get('timeout_busybox','kill_with_init_exit')==137
            and (get('timeout_busybox','kill_with_init_seconds') or 99)<20,
        'timeout -s KILL lets a short command finish (exit 0)':get('timeout_busybox','short_exit')==0 and get('timeout_busybox','short_stdout')=='k9-short',
        'create --pull never refuses a missing image, by ID and by tag, and pulls nothing':get('pull_never','by_id_exit') not in (0,None) and get('pull_never','by_tag_exit') not in (0,None)
            and get('pull_never','tag_absent_after') is True,
        'create with the K9 prefix prints exactly the ID, and starts':get('k9_create','create_stdout_is_one_64_hex_line') is True and get('k9_create','start_exit')==0,
        'inside: uid 0, no effective or bounding capability, no_new_privs, docker-init as PID 1':inside.get('uid')==0 and inside.get('cap_eff_zero') is True
            and inside.get('cap_bnd_zero') is True and inside.get('no_new_privs') is True and inside.get('pid1') in ('docker-init','tini'),
        'inside: the root filesystem and the tools bind are read-only (EROFS), the day bind is written':inside.get('root_write')==30 and inside.get('tools_write')==30
            and get('k9_create','receipt_on_host','mode')=='0o600' and get('k9_create','receipt_on_host','uid')==0,
        'inside: a root 0600 file of the read-only bind is read by root':inside.get('tools_private_file_read') is True,
        'the two env files reach the container under --read-only, each value the literal after the first "="':bool(inside.get('env'))
            and all(row.get('present') and row.get('equal') for row in inside['env'].values()) and all((inside.get('words') or {}).values()) and inside.get('other_c3po_names')==[],
        'the K9R and K9W launched formats are the same bytes in the sealed sources':staged('K9_LAUNCHED_FORMAT') and get('k9_create','inspect','k9r_k9w_formats_identical') is True,
        'the K9 launched format: its keys, the labels, exited 0, not OOM-killed':staged('K9_LAUNCHED_FORMAT') and keys is not None and set(k9r)==set(keys)
            and k9r.get('attempt_key')==AK and k9r.get('request_sha256')==RQ and k9r.get('state')=='exited' and k9r.get('exit_code')==0 and k9r.get('oom_killed') is False,
        'State.OOMKilled true and 137 for a container the kernel OOM-killed':staged('K9_LAUNCHED_FORMAT') and oom.get('oom_killed') is True and oom.get('exit_code')==137,
        'the K12 format: its keys, read-only root, restart no, network none, the two binds with RW as given':staged('K12_FORMAT') and k12keys is not None and set(k12)==set(k12keys)
            and k12.get('read_only_root') is True and k12.get('restart_policy')=='no' and k12.get('network_mode')=='none' and k12.get('auto_remove') is False
            and isinstance(k12.get('mounts'),list) and len(k12['mounts'])==2 and all(set(row)<=set(mountkeys or ()) for row in k12['mounts'])
            and sorted((row.get('Destination'),row.get('RW')) for row in k12['mounts'])==[('/c3po-k9-day',True),('/c3po-k9-tools',False)],
        'a never-started container: K12 format with StartedAt 0001-01-01T00:00:00Z (DOCKER_CONFIG empty, no HOME)':staged('K12_FORMAT') and get('docker_config_empty','create_exit')==0
            and get('docker_config_empty','stdout_one_id') is True and never.get('started_at')==(formats['K12_NEVER_STARTED']['value'] or NEVER_STARTED) and never.get('state')=='created',
        'a single-file read-only bind is read and refuses a write; a read-write one is written through':get('single_file_binds','readonly_file_sha_equal') is True
            and get('single_file_binds','readonly_file_write')=='EROFS' and get('single_file_binds','readwrite_file_written_through') is True,
        'python -I -B of a file in a read-only bind runs (K12-U9)':get('single_file_binds','python_file_in_readonly_bind_exit')==0 and get('single_file_binds','python_file_stdout')=='k12-writer-line\n',
        "the nested read-write receipts bind under a read-only day bind (stage's shape)":get('single_file_binds','nested','day')=='EROFS' and get('single_file_binds','nested','receipts')=='WRITTEN',
        'docker logs of an exited container: exactly the stdout line, stderr apart (K12-U3)':get('logs_stop_rm','logs_stdout_exact') is True and get('logs_stop_rm','logs_stderr_exact') is True,
        'docker stop -t 5 ends a parked python through docker-init with 143, no line (K12-U5)':get('logs_stop_rm','stopped_exit_code')=='143' and get('logs_stop_rm','stopped_logs_empty') is True
            and (get('logs_stop_rm','stop_seconds') or 99)<6,
        'docker rm of two IDs and a missing one: both removed, exit not 0 (K12-U6)':get('logs_stop_rm','both_removed') is True and get('logs_stop_rm','rm_several_exit') not in (0,None),
        'the release compose file names the networks c3po_c3po_internal (internal) and c3po_db_loopback':get('compose_networks','render_exit')==0
            and (networks.get('c3po_internal') or {}).get('name')=='c3po_c3po_internal' and (networks.get('c3po_internal') or {}).get('internal') is True
            and (networks.get('db_loopback') or {}).get('name')=='c3po_db_loopback',
        'db resolves and answers on both networks, not on bridge (N-4, K12-U10)':str(probes.get('internal_db','')).startswith('CONNECTED')
            and str(probes.get('loopback_db','')).startswith('CONNECTED') and not str(probes.get('bridge_db','')).startswith('CONNECTED'),
        'controlled off-network endpoint blocked internally and reachable by loopback, with bridge positive control':
            probes.get('bridge_egress_control')=='CONNECTED hk9ci-egress'
            and probes.get('loopback_egress')=='CONNECTED hk9ci-egress'
            and str(probes.get('internal_egress','')).startswith('FAILED')
            and get('compose_networks','internal_flag')=='true',
        'the throwaway project is down and its networks gone':get('compose_networks','down_exit')==0 and get('compose_networks','networks_left')==[]}

def main(arguments):
    guard(arguments)
    image,release_tree,output=arguments[0],arguments[1],arguments[3]
    work=tempfile.mkdtemp(prefix='hostops02-k9-shapes-',dir='/var/tmp');os.chmod(work,0o700)
    shapes=Shapes(image,release_tree,work)
    try:
        for label in ('image_facts','timeout_busybox','pull_never','k9_create','env_file_literal','single_file_binds','oom_killed','logs_stop_rm','docker_config_empty','compose_networks'):
            shapes.shape(label,getattr(shapes,label))
    finally:
        shapes.cleanup()
    formats=shapes.formats
    checks=expectations(shapes.out,formats)
    _,version,_,_=cli('version','--format','{{.Client.Version}} {{.Server.Version}}')
    result={'schema':SCHEMA,'image_id':image,'docker':version.strip(),'formats_from_the_sealed_sources':{name:{'from':row['from'],'seal':row['seal'],'staged':row['value'] is not None} for name,row in formats.items()},
            'shapes':shapes.out,'expectations':checks,'all_shapes_ran':all(row.get('ok') for row in shapes.out.values()),'all_expectations_met':all(checks.values()),
            'timings':TIMINGS,'slowest_quick_call_seconds':max([row['seconds'] for row in TIMINGS if row['call'].split()[0] in ('create','start','inspect','rm','container','logs')] or [0])}
    with open(output,'w',encoding='utf-8') as handle:handle.write(json.dumps(result,indent=1,sort_keys=True,default=sorted)+'\n')
    for key,value in checks.items():print('%s %s'%('MET  ' if value else 'UNMET',key))
    return 0 if result['all_shapes_ran'] and result['all_expectations_met'] else (2 if not result['all_shapes_ran'] else 3)

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
