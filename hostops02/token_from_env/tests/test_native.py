"""The real system calls of the token placement, made by the source's own unmodified Native on a private temporary tree
that stands in for "/": the substitution of "/" and of the uid is made on the os module (the core's tests/oslevel.py),
and every system call is recorded with the arguments it received. Nothing of Native is overridden, except in the one
test that makes the write fail (a subclass whose write raises ENOSPC: the creation, the removal by identity and the
fsync that follow are real). One more test runs the source in a child interpreter under an audit hook and scans
everything that process printed.

On the workstation this proves the real exclusive create relative to a held descriptor, fsync of a file and of a
directory, lstat of a symbolic link, the readback by a new open, and the removal by identity, as an ordinary user
reported as root, with a marker bit for O_NOATIME; the kernel's O_NOATIME, Linux errno values and real uid 0 only when
the suite runs as root on Linux (the job of the proof branch)."""
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

import family as f
import oslevel
import tok

BOOT=b'0f8fad5b-d9cb-469f-a165-70867728950e\n'
DEPLOY='/opt/deploy'
CREATING=os.O_CREAT|os.O_EXCL
WRITING=os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND
CHILD=Path(__file__).resolve().parent/'native_child.py'
ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}

@pytest.fixture
def tree(tmp_path):
    root=Path(str(tmp_path)).resolve()/'root';root.mkdir(mode=0o755)
    for path in ('etc','opt/deploy','proc/sys/kernel/random'):(root/path).mkdir(parents=True,mode=0o755)
    for path in list(root.rglob('*'))+[root]:os.chmod(str(path),0o755)
    for path in ('etc/c3po-bar','etc/c3po-bar/manifests','etc/c3po-bar/docker-cli'):(root/path).mkdir();os.chmod(str(root/path),0o700)
    (root/'proc/sys/kernel/random/boot_id').write_bytes(BOOT)
    write_env(root,tok.env_with())
    return root

def write_env(root,content,mode=0o600):
    path=root/'opt/deploy/.env'
    if path.exists() or path.is_symlink():path.unlink()
    path.write_bytes(content);os.chmod(str(path),mode)

def fields(root):
    return {'config_chain':oslevel.rows(root,tok.CONFIG),'deploy_directory':DEPLOY,'evidence_boot_id_sha256':f.sha(BOOT.strip())}

def run(root,native=None,after_signing=None):
    """One run in this process with the module's own Native (or the subclass given)."""
    k=tok.K();docs=f.Docs(k,fields(root),now=tok.NOW)
    if after_signing is not None:after_signing()
    with oslevel.Substitute(root) as record:receipt=docs.run(native)
    assert f.sealed(receipt) and tok.leaks(tok.line(receipt))==[]
    return k.m,receipt,record

def creating(record):return [entry for entry in record.of('open') if entry['flags']&WRITING]

def test_complete_run_with_real_system_calls(tree):
    m,receipt,record=run(tree)
    assert (receipt['status'],receipt['outcome'],receipt['code'])==(m.COMPLETE_STATUS,m.COMPLETE_OUTCOME,None)
    token=tree/'etc/c3po-bar/token';info=os.lstat(str(token))
    assert token.read_bytes()==tok.TOKEN.encode()+b'\n' and stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
    assert (receipt['token_file']['device'],receipt['token_file']['inode'])==(info.st_dev,info.st_ino)
    made=creating(record)
    assert len(made)==1 and made[0]['path']==tok.TOKEN_PATH and made[0]['by_dir_fd'] and made[0]['mode']==0o600
    assert made[0]['flags']==os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC
    opens=record.of('open')
    assert all(entry['flags']&os.O_NOFOLLOW for entry in opens) and all(entry['by_dir_fd'] or entry['path']=='/' for entry in opens)
    env=[entry for entry in opens if entry['path']==DEPLOY+'/.env']
    assert len(env)==1 and env[0]['noatime'] and env[0]['flags']&os.O_NONBLOCK and not env[0]['flags']&WRITING
    back=[entry for entry in opens if entry['path']==tok.TOKEN_PATH and not entry['flags']&WRITING]
    assert len(back)==1 and back[0]['noatime'] and back[0]['by_dir_fd']
    assert [entry['path'] for entry in record.done('fsync')]==[tok.TOKEN_PATH,tok.CONFIG] and record.of('unlink','remove','link','mkdir')==[]
    assert [entry['mask'] for entry in record.of('umask')]==[0o077] and all(entry['follow_symlinks'] is False for entry in record.of('stat'))
    # the environment file and the rest of the tree are as they were
    assert (tree/'opt/deploy/.env').read_bytes()==tok.env_with() and sorted(os.listdir(str(tree/'etc/c3po-bar')))==['docker-cli','manifests','token']

def test_a_write_that_fails_is_withdrawn_by_identity_with_real_calls(tree):
    m=tok.K().m
    class Full(m.Native):
        def write(self,fd,data):raise OSError(errno.ENOSPC,'full')
    m,receipt,record=run(tree,Full())
    row=receipt['token_file']
    assert (receipt['status'],receipt['code'],row['state'],row['withdrawn'],row['fsync_directory_after_withdrawal'])==(m.PARTIAL_STATUS,'FILESYSTEM_FULL','WITHDRAWN',True,True)
    assert not (tree/'etc/c3po-bar/token').exists() and sorted(os.listdir(str(tree/'etc/c3po-bar')))==['docker-cli','manifests']
    removed=record.done('unlink');assert len(removed)==1 and removed[0]['path']==tok.TOKEN_PATH and removed[0]['by_dir_fd']
    assert [entry['path'] for entry in record.done('fsync')]==[tok.CONFIG]

def refusal(tree,code,**options):
    m,receipt,record=run(tree,**options)
    assert (receipt['status'],receipt['code'],receipt['phase_reached'])==('REFUSED',code,'PRECHECK')
    assert creating(record)==[] and record.of('unlink','remove','link','mkdir')==[]
    return receipt,record

def test_an_existing_token_is_refused_and_never_opened(tree):
    token=tree/'etc/c3po-bar/token';token.write_bytes(b'previous\n');os.chmod(str(token),0o600)
    receipt,record=refusal(tree,'TOKEN_FILE_PRESENT')
    assert token.read_bytes()==b'previous\n' and not [entry for entry in record.of('open') if entry['path']==tok.TOKEN_PATH]
    assert not [entry for entry in record.of('open') if entry['path']==DEPLOY+'/.env'],'the environment file is not even read'

def test_links_are_refused(tree):
    os.unlink(str(tree/'opt/deploy/.env'));(tree/'opt/deploy/env.real').write_bytes(tok.env_with());os.chmod(str(tree/'opt/deploy/env.real'),0o600)
    os.symlink('env.real',str(tree/'opt/deploy/.env'))
    receipt,record=refusal(tree,'ENV_FILE_NOT_REGULAR')
    assert not [entry for entry in record.of('open') if entry['path'] in (DEPLOY+'/.env',DEPLOY+'/env.real')]
    os.unlink(str(tree/'opt/deploy/.env'));os.rename(str(tree/'opt/deploy/env.real'),str(tree/'opt/deploy/.env'))
    os.rename(str(tree/'opt/deploy'),str(tree/'opt/deploy-real'));os.symlink('deploy-real',str(tree/'opt/deploy'))
    refusal(tree,'DEPLOY_CHAIN_SYMLINK')

def test_unsafe_modes_are_refused(tree):
    os.chmod(str(tree/'opt/deploy/.env'),0o606);refusal(tree,'ENV_FILE_WORLD_WRITABLE');os.chmod(str(tree/'opt/deploy/.env'),0o600)
    os.chmod(str(tree/'opt/deploy'),0o777);refusal(tree,'DEPLOY_CHAIN_WORLD_WRITABLE');os.chmod(str(tree/'opt/deploy'),0o755)
    os.chmod(str(tree/'opt'),0o775);refusal(tree,'DEPLOY_CHAIN_NOT_ROOT_OWNED_ABOVE_THE_DEPLOY_DIRECTORY');os.chmod(str(tree/'opt'),0o755)
    refusal(tree,'PARENT_IDENTITY_MISMATCH',after_signing=lambda:os.chmod(str(tree/'etc/c3po-bar'),0o750))

def test_a_file_outside_the_rules_is_refused(tree):
    write_env(tree,tok.BASE_ENV+b'export MASSIVE_API_TOKEN='+tok.TOKEN.encode()+b'\n');refusal(tree,'ENV_TOKEN_DEFINITION_NOT_PLAIN')
    write_env(tree,tok.BASE_ENV+b'MASSIVE_API_TOKEN="'+tok.TOKEN.encode()+b'"\n');refusal(tree,'ENV_TOKEN_VALUE_GRAMMAR')
    write_env(tree,b'#\n'*32769);refusal(tree,'ENV_FILE_TOO_LARGE')

@pytest.mark.parametrize('content,status,code',[(tok.env_with(),'METADATA_ONLY_REQUIRES_REVIEW',None),
                                                (tok.env_with(token=tok.LITERAL),'METADATA_ONLY_REQUIRES_REVIEW',None),
                                                (tok.BASE_ENV+b'MASSIVE_API_TOKEN="'+tok.TOKEN.encode()+b'"\n','REFUSED','ENV_TOKEN_VALUE_GRAMMAR'),
                                                (tok.env_with()+b'C3PO_MASSIVE_API_TOKEN='+tok.LONGER.encode()+b'\n','REFUSED','ENV_TOKEN_DEFINITIONS_DISAGREE')],
                         ids=['complete','literal_fake_value','quoted','disagreeing'])
def test_nothing_the_child_process_prints_holds_the_token(tree,tmp_path,content,status,code):
    """Everything the process printed, on standard output and on standard error, scanned for every substring of four
    characters or more of the main fake token (and for the literal fake value whole); and what that process did, from
    the interpreter's own audit events."""
    write_env(tree,content);path=Path(str(tmp_path))/'fields.json';path.write_text(json.dumps(fields(tree)))
    environment=dict(ENV,HOSTOPS02_TEST_CORE=str(f.CORE))
    done=subprocess.run([sys.executable,'-B',str(CHILD),str(tree),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment,timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    for value in (tok.TOKEN,tok.LONGER):assert tok.leaks(done.stdout,value)==[]
    assert tok.LITERAL.encode() not in done.stdout
    result=json.loads(done.stdout);receipt=result['receipt']
    assert (receipt['status'],receipt['code'])==(status,code)
    writes=[event for event in result['events'] if event[0]=='open-for-writing']
    assert writes==([['open-for-writing','token',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC]] if code is None else [])
    assert not [event for event in result['events'] if event[0] not in ('open','open-for-writing')],'no process, network, environment, rename, chmod or removal'
    assert all(event[1] in ('/','etc','c3po-bar','token','opt','deploy','.env','proc','sys','kernel','random','boot_id') or event[1].endswith('/root')
               for event in result['events'] if event[0]=='open')
