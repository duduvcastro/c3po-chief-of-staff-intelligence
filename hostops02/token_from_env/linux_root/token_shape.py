"""The token placement on a real filesystem, as real root: the operation's own run() and unmodified Native, on the
layout of supervisor operation 2 (/etc/c3po-bar, root:root 0700, with its two children) and a FAKE deploy tree in /opt,
created by this script on a throwaway runner and removed again. No network, no docker, no container, no token of any
provider: every value is fake.

Shapes: the complete run (the file as the supervisor needs it, the bytes, the environment file read without changing
its access time, which only the kernel's O_NOATIME explains); the same run again (refused, the file unchanged); a token
of another value and length (the receipt is the same, the inode of the file aside); a full filesystem at the write (a
tmpfs of a few pages mounted on /etc/c3po-bar and filled: the file of this run is withdrawn by identity); and four
refusals before any effect (the environment file through a link, a world-writable deploy directory, the export form, a
quoted value). Every receipt is scanned for every substring of four characters or more of the token.

  --compose-agreement   (as the runner's user, no root) for each environment file the parser accepts, the value docker
                        compose gives the service of a throwaway project (config only: nothing is pulled, created or
                        started) compared with the parser's; for files the parser refuses, what compose would have
                        given, for the record. When `docker compose` is not available it says so and exits 0.
  --self-test           the same collection on the emulated host of the core's tests (tests/hostemu.py): proves that
                        this script is coherent with the source, and nothing about a real filesystem.

For a THROWAWAY GitHub-hosted ubuntu-24.04 runner only (linux_root/run.sh prepares it); it refuses anywhere else:
Linux, effective uid 0, HOSTOPS_THROWAWAY_RUNNER=yes and RUNNER_ENVIRONMENT=github-hosted are all required, and it
refuses when /etc/c3po-bar or the deploy tree of the job exists before it starts. NOT RUN by its author: no Linux and no
root were available offline.

usage: sudo -n env HOSTOPS_THROWAWAY_RUNNER=yes RUNNER_ENVIRONMENT=github-hosted /usr/bin/python3 -I -B linux_root/token_shape.py <owner uid>
           <owner uid>   the uid that owns the fake deploy tree and its environment file (the runner's user)
       /usr/bin/python3 -I -B linux_root/token_shape.py --compose-agreement
       /usr/bin/python3 -B linux_root/token_shape.py --self-test
exit 0 only when every shape ran AND every expectation is met; 2 when a shape did not run; 3 when an expectation is not
met; 1 for a refusal. Prints one JSON object.
"""
import contextlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(os.path.dirname(HERE),'tests'))
import conftest                                    # noqa: F401 (puts the tests of the frozen core on the path)
import family as f
import hostemu
import tok

SCHEMA='HOSTOPS02_TOKEN_FROM_ENV_LINUX_ROOT_SHAPE_V1'
COMPOSE_SCHEMA='HOSTOPS02_TOKEN_FROM_ENV_COMPOSE_AGREEMENT_V1'
CONFIG=tok.CONFIG
TOKEN_PATH=tok.TOKEN_PATH
DEPLOY='/opt/hostops02-token-ci'
OTHER_LINES=(b'# the FAKE environment file of the proof job\nC3PO_DB_PASSWORD=fake-password-for-tests\n'
             b'OTHER="a quoted value # not a comment"\nexport OTHER_EXPORTED=1\nOTHER_YAML: yaml style\n')
def env_file(token=tok.TOKEN,line=b'MASSIVE_API_TOKEN=%s\n'):return OTHER_LINES+line%token.encode()
DAY=24*3600*10**9

def lstat_row(path):
    info=os.lstat(path);return {'path':path,'device':info.st_dev,'inode':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,'mode':stat.S_IMODE(info.st_mode)}
def boot_sha():
    with open('/proc/sys/kernel/random/boot_id','rb') as handle:return f.sha(handle.read().strip())


class Real:
    """The real filesystem of the runner, as root."""
    def __init__(self,owner):self.owner=owner;self.made=[];self.mounted=False
    def prepare(self):
        for path in (CONFIG,DEPLOY):
            if os.path.lexists(path):raise SystemExit('REFUSED: %s exists: this is not a throwaway runner'%path)
        os.umask(0o077)
        os.mkdir(CONFIG,0o700);self.made.append((CONFIG,os.lstat(CONFIG).st_ino))
        for name in ('manifests','docker-cli'):os.mkdir(CONFIG+'/'+name,0o700)
        os.mkdir(DEPLOY,0o755);os.chmod(DEPLOY,0o755);os.chown(DEPLOY,self.owner,self.owner);self.made.append((DEPLOY,os.lstat(DEPLOY).st_ino))
    def write_env(self,content,mode=0o600,link=False):
        for name in ('.env','env.real'):
            if os.path.lexists(DEPLOY+'/'+name):os.unlink(DEPLOY+'/'+name)
        target=DEPLOY+('/env.real' if link else '/.env')
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:os.write(fd,content)
        finally:os.close(fd)
        os.chown(target,self.owner,self.owner);os.chmod(target,mode)
        if link:os.symlink('env.real',DEPLOY+'/.env')
    def chmod_deploy(self,mode):os.chmod(DEPLOY,mode)
    def remove_token(self):
        if os.path.lexists(TOKEN_PATH):os.unlink(TOKEN_PATH)
    def token(self,expected):
        if not os.path.lexists(TOKEN_PATH):return {'exists':False}
        info=os.lstat(TOKEN_PATH)
        with open(TOKEN_PATH,'rb') as handle:equal=handle.read()==expected.encode()+b'\n'
        return {'exists':True,'regular':stat.S_ISREG(info.st_mode),'uid':info.st_uid,'gid':info.st_gid,'mode_octal':'%04o'%stat.S_IMODE(info.st_mode),
                'links':info.st_nlink,'size_within_1_4096':1<=info.st_size<=4096,'bytes_equal_the_token_and_a_newline':equal,'inode':info.st_ino}
    def run(self):
        fields={'config_chain':[lstat_row(path) for path in ('/','/etc',CONFIG)],'deploy_directory':DEPLOY,'evidence_boot_id_sha256':boot_sha()}
        return f.Docs(tok.K(),fields,now=tok.NOW).run(None)
    @contextlib.contextmanager
    def full(self):
        """A tmpfs of four pages on /etc/c3po-bar (root:root 0700), filled with one file until the filesystem refuses."""
        subprocess.run(['mount','-t','tmpfs','-o','size=16k,mode=0700,uid=0,gid=0','hostops02-token-ci',CONFIG],check=True)
        self.mounted=True
        try:
            fd=os.open(CONFIG+'/filler',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                while True:
                    try:os.write(fd,b'\0'*4096)
                    except OSError:break
                os.fsync(fd)
            finally:os.close(fd)
            yield
        finally:
            subprocess.run(['umount',CONFIG],check=True);self.mounted=False
    def env_atime(self):
        """Set the access time of the environment file three days back (after its change time, so that an ordinary read
        would move it under relatime) and return a function that says whether it is still that."""
        path=DEPLOY+'/.env';now=os.stat(path).st_ctime_ns;atime=now-3*DAY;os.utime(path,ns=(atime,now-4*DAY))
        return lambda:os.stat(path).st_atime_ns==atime
    def cleanup(self):
        if self.mounted:subprocess.run(['umount',CONFIG]);self.mounted=False
        for path,inode in reversed(self.made):
            if os.path.lexists(path) and os.lstat(path).st_ino==inode:shutil.rmtree(path)


class Emulated:
    """The emulated host of the core's tests, with the same layout."""
    def __init__(self):self.hook=None
    def prepare(self):
        self.k,self.host=tok.world();self.host.tree.add(DEPLOY,uid=1001,gid=1001)
    def write_env(self,content,mode=0o600,link=False):
        tree=self.host.tree
        for name in ('.env','env.real'):
            if tree.get(DEPLOY+'/'+name) is not None:tree.remove(DEPLOY+'/'+name)
        tree.add(DEPLOY+('/env.real' if link else '/.env'),kind='file',uid=1001,gid=1001,mode=mode,content=content)
        if link:tree.add(DEPLOY+'/.env',kind='symlink',mode=0o777,target='env.real')
    def chmod_deploy(self,mode):self.host.tree.get(DEPLOY).mode=mode
    def remove_token(self):
        if self.host.tree.get(TOKEN_PATH) is not None:self.host.tree.remove(TOKEN_PATH)
    def token(self,expected):
        node=self.host.tree.get(TOKEN_PATH)
        if node is None:return {'exists':False}
        return {'exists':True,'regular':node.kind=='file','uid':node.uid,'gid':node.gid,'mode_octal':'%04o'%node.mode,'links':node.nlink,
                'size_within_1_4096':1<=len(node.content)<=4096,'bytes_equal_the_token_and_a_newline':bytes(node.content)==expected.encode()+b'\n','inode':node.ino}
    def run(self):
        fields={'config_chain':hostemu.rows(self.host,CONFIG),'deploy_directory':DEPLOY,'evidence_boot_id_sha256':f.BOOT_SHA}
        self.host.hook=self.hook;return f.Docs(self.k,fields,now=tok.NOW).run(self.host)
    @contextlib.contextmanager
    def full(self):
        import errno
        def hook(host,name,detail,calls):
            if name=='write':raise OSError(errno.ENOSPC,'full')
        self.hook=hook
        try:yield
        finally:self.hook=None
    def env_atime(self):return lambda:True             # the emulation does not move an access time on a read
    def cleanup(self):pass


def summary(receipt,*values):
    line=tok.line(receipt)
    return {'status':receipt.get('status'),'outcome':receipt.get('outcome'),'code':receipt.get('code'),'phase_reached':receipt.get('phase_reached'),
            'token_file':receipt.get('token_file'),'mutating_calls':receipt.get('mutating_calls'),
            'leaks':sorted({item for value in values for item in tok.leaks(line,value)}),'literal_in_receipt':tok.LITERAL.encode() in line,
            'without_identity':tok.without_identity(receipt)}

def collect(backend):
    out={}
    def shape(name,action):
        try:out[name]=dict(action(),ok=True)
        except Exception as error:out[name]={'ok':False,'error':type(error).__name__}
    backend.prepare()
    try:
        def complete():
            backend.write_env(env_file());kept=backend.env_atime();receipt=backend.run()
            return {'receipt':summary(receipt,tok.TOKEN),'file':backend.token(tok.TOKEN),'access_time_kept':kept()}
        shape('complete',complete)
        def again():
            before=backend.token(tok.TOKEN);receipt=backend.run();return {'receipt':summary(receipt,tok.TOKEN),'file_before':before,'file_after':backend.token(tok.TOKEN)}
        shape('again',again)
        def other_length():
            backend.remove_token();backend.write_env(env_file(tok.LONGER));receipt=backend.run()
            return {'receipt':summary(receipt,tok.LONGER,tok.TOKEN),'file':backend.token(tok.LONGER)}
        shape('other_value_and_length',other_length)
        def full():
            backend.remove_token();backend.write_env(env_file())
            with backend.full():
                receipt=backend.run();left=backend.token(tok.TOKEN)
            return {'receipt':summary(receipt,tok.TOKEN),'file':left}
        shape('full_filesystem',full)
        def refusals():
            backend.remove_token();rows={}
            backend.write_env(env_file(),link=True);rows['link']=summary(backend.run(),tok.TOKEN)
            backend.write_env(env_file());backend.chmod_deploy(0o777);rows['world_writable']=summary(backend.run(),tok.TOKEN);backend.chmod_deploy(0o755)
            backend.write_env(env_file(line=b'export MASSIVE_API_TOKEN=%s\n'));rows['export']=summary(backend.run(),tok.TOKEN)
            backend.write_env(env_file(line=b'MASSIVE_API_TOKEN="%s"\n'));rows['quoted']=summary(backend.run(),tok.TOKEN)
            return {'receipts':rows,'file':backend.token(tok.TOKEN)}
        shape('refusals_before_any_effect',refusals)
        def literal():
            backend.remove_token();backend.write_env(env_file(tok.LITERAL));receipt=backend.run()
            return {'receipt':summary(receipt),'file':backend.token(tok.LITERAL)}
        shape('literal_fake_value',literal)
    finally:backend.cleanup()
    return out

def placed(run):
    receipt=run.get('receipt') or {};row=receipt.get('token_file') or {};file=run.get('file') or {}
    return (receipt.get('status'),receipt.get('outcome'),row.get('state'))==('METADATA_ONLY_REQUIRES_REVIEW','TOKEN_PLACED_METADATA_VERIFIED','PLACED_VERIFIED') and (
        file.get('exists'),file.get('regular'),file.get('uid'),file.get('gid'),file.get('mode_octal'),file.get('links'),file.get('size_within_1_4096'),
        file.get('bytes_equal_the_token_and_a_newline'))==(True,True,0,0,'0600',1,True,True) and row.get('inode')==file.get('inode')

def expectations(out):
    complete,again,other,full,refusals,literal=(out.get(name) or {} for name in ('complete','again','other_value_and_length','full_filesystem','refusals_before_any_effect','literal_fake_value'))
    receipts=[run.get('receipt') or {} for run in (complete,again,other,full,literal)]+list((refusals.get('receipts') or {}).values())
    codes={name:(row.get('status'),row.get('code'),row.get('phase_reached'),(row.get('mutating_calls') or {}).get('issued')) for name,row in (refusals.get('receipts') or {}).items()}
    return {
        'the token placed as real root: complete, root:root 0600, one link, size within 1-4096, the bytes written':placed(complete) and placed(other) and placed(literal),
        'the environment file read without moving its access time (the kernel O_NOATIME)':complete.get('access_time_kept') is True,
        'a second run refused before any effect, the file as it was':((again.get('receipt') or {}).get('status'),(again.get('receipt') or {}).get('code'),
            ((again.get('receipt') or {}).get('mutating_calls') or {}).get('issued'))==('REFUSED','TOKEN_FILE_PRESENT',0)
            and again.get('file_before')==again.get('file_after') and (again.get('file_after') or {}).get('bytes_equal_the_token_and_a_newline') is True,
        'the receipt the same for a token of another value and length, the inode of the file aside':bool(complete.get('receipt')) and
            (complete.get('receipt') or {}).get('without_identity')==(other.get('receipt') or {}).get('without_identity'),
        'a full filesystem at the write: the file of this run withdrawn by identity, nothing left':(
            ((full.get('receipt') or {}).get('status'),(full.get('receipt') or {}).get('code'),((full.get('receipt') or {}).get('token_file') or {}).get('state'),
             ((full.get('receipt') or {}).get('token_file') or {}).get('withdrawn'))==('PARTIAL_METADATA_REQUIRES_REVIEW','FILESYSTEM_FULL','WITHDRAWN',True)
            and (full.get('file') or {}).get('exists') is False),
        'a link at the environment file, a world-writable deploy directory, the export form and a quoted value refused before any effect':codes=={
            'link':('REFUSED','ENV_FILE_NOT_REGULAR','PRECHECK',0),'world_writable':('REFUSED','DEPLOY_CHAIN_WORLD_WRITABLE','PRECHECK',0),
            'export':('REFUSED','ENV_TOKEN_DEFINITION_NOT_PLAIN','PRECHECK',0),'quoted':('REFUSED','ENV_TOKEN_VALUE_GRAMMAR','PRECHECK',0)}
            and (refusals.get('file') or {}).get('exists') is False,
        'no receipt holds four consecutive characters of a token, nor the literal fake value':bool(receipts) and len(receipts)==9 and all(
            receipt.get('leaks')==[] and receipt.get('literal_in_receipt') is False for receipt in receipts),
    }

def report(out):
    checks=expectations(out)
    for run in out.values():                                   # what the record keeps: no copy of the comparison material
        for receipt in [run.get('receipt')]+list((run.get('receipts') or {}).values()):
            if receipt:receipt.pop('without_identity',None)
    return {'schema':SCHEMA,'runs':out,'expectations':checks,'all_runs_made':all(row.get('ok') for row in out.values()) and len(out)==6,
            'all_expectations_met':all(checks.values())}


# ---------------------------------------------------------------- what docker compose makes of the same files
COMPOSE_FILE=b'services:\n  probe:\n    image: hostops02-token-ci-never-pulled\n    env_file:\n      - .env\n'
T=tok.TOKEN.encode()
AGREEMENT=[('plain',b'MASSIVE_API_TOKEN='+T+b'\n'),('no_final_newline',b'MASSIVE_API_TOKEN='+T),('other_lines_around',OTHER_LINES+b'MASSIVE_API_TOKEN='+T+b'\n# end\n'),
           ('c3po_name',b'C3PO_MASSIVE_API_TOKEN='+T+b'\n'),('both_names',b'MASSIVE_API_TOKEN='+T+b'\nC3PO_MASSIVE_API_TOKEN='+T+b'\n'),
           ('quoted_others',b'A="x # y"\nB=\'$z\'\nC="" \nMASSIVE_API_TOKEN='+T+b'\nD: e\nexport E=1\n'),
           ('every_character_of_the_grammar',b'MASSIVE_API_TOKEN=ABCxyz0123456789._~+/=-\n'),
           # refused by the parser: what compose makes of them is recorded, not judged
           ('refused_export',b'export MASSIVE_API_TOKEN='+T+b'\n'),('refused_quoted',b'MASSIVE_API_TOKEN="'+T+b'"\n'),
           ('refused_spaces',b'MASSIVE_API_TOKEN = '+T+b'\n'),('refused_after_a_quote',b'A="x" MASSIVE_API_TOKEN=FaKeHiDdEnVaLuEfOrTeStS\nMASSIVE_API_TOKEN='+T+b'\n'),
           ('refused_inline_comment',b'MASSIVE_API_TOKEN='+T+b' # c\n'),('refused_two_lines',b'A="a\nMASSIVE_API_TOKEN=FaKeHiDdEnVaLuEfOrTeStS\n"\nMASSIVE_API_TOKEN='+T+b'\n')]

def ours(raw):
    m=tok.K().m
    try:return bytes(m.token_content(raw,m.token_definitions(raw)))[:-1]
    except m.Refused as error:return str(error)

def compose_agreement():
    try:version=subprocess.run(['docker','compose','version','--short'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60)
    except (OSError,subprocess.SubprocessError):version=None
    if version is None or version.returncode!=0:
        return {'schema':COMPOSE_SCHEMA,'available':False,'fixtures':{},'all_accepted_agree':None}
    fixtures={}
    with tempfile.TemporaryDirectory() as work:
        for name,raw in AGREEMENT:
            directory=os.path.join(work,name);os.mkdir(directory,0o700)
            with open(os.path.join(directory,'compose.yml'),'wb') as handle:handle.write(COMPOSE_FILE)
            with open(os.path.join(directory,'.env'),'wb') as handle:handle.write(raw)
            done=subprocess.run(['docker','compose','--project-name','hostops02tokenci','--project-directory',directory,'-f',os.path.join(directory,'compose.yml'),
                                 'config','--format','json'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60,env={'PATH':'/usr/bin:/bin','HOME':work})
            value=ours(raw);row={'parser':'ACCEPTED' if type(value) is bytes else value,'compose_returncode':done.returncode}
            if done.returncode==0:
                environment=(json.loads(done.stdout).get('services',{}).get('probe',{}) or {}).get('environment') or {}
                def seen(key):
                    found=environment.get(key)
                    if found is None:return 'ABSENT'
                    if type(value) is bytes:return 'EQUAL_TO_THE_PARSER' if found.encode()==value else 'DIFFERENT_FROM_THE_PARSER'
                    return 'EQUAL_TO_THE_TOKEN' if found.encode()==T else 'ANOTHER_VALUE'
                row['compose']={key:seen(key) for key in ('MASSIVE_API_TOKEN','C3PO_MASSIVE_API_TOKEN')}
            fixtures[name]=row
    accepted=[row for row in fixtures.values() if row['parser']=='ACCEPTED']
    agree=bool(accepted) and all(row.get('compose_returncode')==0 and 'DIFFERENT_FROM_THE_PARSER' not in row['compose'].values()
                                 and 'EQUAL_TO_THE_PARSER' in row['compose'].values() for row in accepted)
    return {'schema':COMPOSE_SCHEMA,'available':True,'compose_version':version.stdout.decode('ascii','replace').strip()[:40],'fixtures':fixtures,'all_accepted_agree':agree}


def main(arguments):
    if arguments==['--self-test']:
        result=report(collect(Emulated()))
        print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_runs_made'] and result['all_expectations_met'] else 3 if result['all_runs_made'] else 2
    throwaway=sys.platform.startswith('linux') and os.environ.get('HOSTOPS_THROWAWAY_RUNNER')=='yes' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
    if arguments==['--compose-agreement']:
        if not throwaway:
            print('REFUSED: a throwaway GitHub-hosted Linux runner, with HOSTOPS_THROWAWAY_RUNNER=yes',file=sys.stderr);return 1
        result=compose_agreement();print(json.dumps(result,indent=1,sort_keys=True))
        return 0 if result['all_accepted_agree'] in (True,None) else 3
    if len(arguments)!=1 or not arguments[0].isdigit():
        print(__doc__);return 1
    if not (throwaway and os.geteuid()==0):
        print('REFUSED: a throwaway GitHub-hosted Linux runner, as root, with HOSTOPS_THROWAWAY_RUNNER=yes',file=sys.stderr);return 1
    result=report(collect(Real(int(arguments[0]))))
    print(json.dumps(result,indent=1,sort_keys=True));return 0 if result['all_runs_made'] and result['all_expectations_met'] else 3 if result['all_runs_made'] else 2

if __name__=='__main__':raise SystemExit(main(sys.argv[1:]))
