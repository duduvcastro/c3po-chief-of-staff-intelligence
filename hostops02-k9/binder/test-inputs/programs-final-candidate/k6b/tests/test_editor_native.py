"""The editor's own script (ENV_EDIT_SCRIPT, the bytes the container runs), executed for real by this interpreter
against real files: the same rule as the source's in-memory edited_env() and as the emulation, case by case, and what
it does to a file it refuses (nothing: same bytes, same inode, same mtime). Only two things differ from the container:
the path of the file (the script's TARGET constant replaced by a temporary path in the bytes given to the
interpreter) and the owner it requires (this user instead of 1000:1000). Run with both interpreters."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import family as f
import k6b

M=k6b.load().m
HEAD=b'C3PO_DB_PASSWORD=never-emit-environment-canary\nEODHD_API_TOKEN=x\n'
PLAN=k6b.fields.__globals__  # fixture module globals, for the block values

def spec_for(mode,owner):
    m,docs,host=k6b.fresh(mode);spec=M.edit_spec(docs.plan);spec['owner']=list(owner);return spec

# prctl(2) exists on Linux only: the script's ctypes is replaced by a stand-in whose prctl answers as the kernel would
# (0 for PR_SET_DUMPABLE 0, then 0 for PR_GET_DUMPABLE). RECORD lists the calls, so a test can see they came first.
PRCTL='''import sys,types
_ctypes=types.ModuleType('ctypes');_prctl_calls=[]
class _Library:
    def prctl(self,option,*rest):
        _prctl_calls.append(option);return %s
_ctypes.CDLL=lambda name,use_errno=False:_Library()
sys.modules['ctypes']=_ctypes
import os as _os
_open=_os.open
def _guarded(path,*rest,**more):
    assert _prctl_calls[:2]==[4,3],'the file was opened before the process was made non-dumpable'
    return _open(path,*rest,**more)
_os.open=_guarded
'''
def execute(path,spec,answer='0'):
    stdin=PRCTL.encode()%answer.encode()+M.editor_stdin(spec).replace(b"TARGET='/c3po-env/.env'",("TARGET=%r"%str(path)).encode(),1)
    done=subprocess.run([sys.executable,'-I','-B','-'],input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,env={'PATH':'/usr/bin:/bin'})
    assert done.stderr==b'',done.stderr.decode()[-500:]
    lines=done.stdout.split(b'\n');assert len(lines)==2 and lines[1]==b'','exactly one line'
    line=json.loads(lines[0]);assert set(line)=={'status','code'}
    return done.returncode,line

def put(tmp_path,raw,mode=0o600):
    path=Path(str(tmp_path))/'env';path.write_bytes(raw);os.chmod(str(path),mode);return path

LINES=[l.encode() for l in k6b.BLOCK]
def text(*lines):return b''.join(line+b'\n' for line in lines)
CASES=[('MOUNT',HEAD),('MOUNT',b''),('MOUNT',b'\n'),('DISABLE_FULL',b'\n'+text(LINES[0])),('MOUNT',HEAD+b'# C3PO_R2D2_V2_CAPACITY_REQUIRED=true\n'),('MOUNT',HEAD+'café=1\n'.encode('latin-1')),
       ('MOUNT',HEAD+text(LINES[0])),('MOUNT',HEAD[:-1]),('MOUNT',HEAD+b'export C3PO_R2D2_V2_CAPACITY_REQUIRED=true\n'),
       ('ENABLE',HEAD+text(LINES[0])),('ENABLE',HEAD),('ENABLE',text(LINES[0])+HEAD),('ENABLE',HEAD+text(LINES[0]+b'\r')),
       ('ENABLE',HEAD+text(LINES[0],LINES[4])),('ENABLE',HEAD+text(b'  '+LINES[0])),
       ('DISABLE_FAST',HEAD+text(*LINES)),('DISABLE_FAST',HEAD+text(*LINES[:4])),('DISABLE_FAST',HEAD+text(*LINES)+b'X=1\n'),
       ('DISABLE_FULL',HEAD+text(*LINES)),('DISABLE_FULL',HEAD+text(*LINES[:4])),('DISABLE_FULL',HEAD+text(LINES[0])),('DISABLE_FULL',HEAD),
       ('DISABLE_FULL',text(*LINES)),('DISABLE_FULL',HEAD+text(*LINES[:3]))]

@pytest.mark.parametrize('mode,raw',CASES,ids=['case%02d_%s'%(index,mode) for index,(mode,_) in enumerate(CASES)])      # ids without file names: 'static' deselects
def test_the_script_applies_the_same_rule_as_the_source_and_the_emulation(tmp_path,mode,raw):
    owner=(os.getuid(),os.getgid());spec=spec_for(mode,owner);path=put(tmp_path,raw);before=os.lstat(str(path))
    try:expected,_=M.edited_env(raw,spec);reason=None
    except M.Refused as error:expected,reason=None,str(error)
    code,line=execute(path,spec);after=os.lstat(str(path))
    if expected is None:
        assert (code,line)==(1,{'status':'ENV_EDIT_REFUSED','code':reason}) and path.read_bytes()==raw
        assert (after.st_ino,after.st_mtime_ns,after.st_size)==(before.st_ino,before.st_mtime_ns,before.st_size)
    else:
        assert (code,line)==(0,{'status':'ENV_EDIT_DONE','code':None}) and path.read_bytes()==expected
        assert (after.st_ino,after.st_dev,after.st_uid,after.st_gid,after.st_mode,after.st_nlink)==(before.st_ino,before.st_dev,before.st_uid,before.st_gid,before.st_mode,1)
    # the emulation's own implementation of the rule agrees
    class Node:pass
    class Tree:
        def get(self,p):return node
    class Host:
        tree=Tree();log=[]
    node=type('N',(),{})();node.kind='file';node.nlink=1;node.uid,node.gid=owner;node.mode=0o600;node.content=bytearray(raw);node.mtime=node.ctime=1
    editor=k6b.Editor(Host(),M.ENV_EDIT_SCRIPT);rc,(status,why)=editor.apply(spec)
    assert (rc,status,why,bytes(node.content))==((0,'ENV_EDIT_DONE',None,expected) if expected is not None else (1,'ENV_EDIT_REFUSED',reason,raw))

def test_the_script_refuses_what_is_not_the_file_it_expects(tmp_path):
    owner=(os.getuid(),os.getgid());spec=spec_for('MOUNT',owner)
    path=put(tmp_path,HEAD,0o640);assert execute(path,spec)==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_NOT_AS_EXPECTED'}) and path.read_bytes()==HEAD
    os.chmod(str(path),0o600);os.link(str(path),str(path)+'.second')
    assert execute(path,spec)==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_NOT_AS_EXPECTED'});os.unlink(str(path)+'.second')
    other=dict(spec,owner=[owner[0]+1,owner[1]])
    assert execute(path,other)==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_NOT_AS_EXPECTED'})
    link=Path(str(tmp_path))/'link';os.symlink(str(path),str(link))
    assert execute(link,spec)==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_OPEN'}) and path.read_bytes()==HEAD
    assert execute(Path(str(tmp_path))/'absent',spec)==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_OPEN'})
    directory=Path(str(tmp_path))/'directory';directory.mkdir()
    assert execute(directory,spec)[0]==1
    fifo=Path(str(tmp_path))/'fifo';os.mkfifo(str(fifo),0o600)
    assert execute(fifo,spec)==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_NOT_AS_EXPECTED'})
    big=put(tmp_path,b'A=1\n'*300000);assert execute(big,spec)==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_NOT_AS_EXPECTED'})

def test_a_whole_week_on_one_real_file(tmp_path):
    owner=(os.getuid(),os.getgid());path=put(tmp_path,HEAD)
    for mode,count in (('MOUNT',1),('ENABLE',5),('DISABLE_FAST',4),('DISABLE_FULL',0)):
        assert execute(path,spec_for(mode,owner))==(0,{'status':'ENV_EDIT_DONE','code':None})
        assert path.read_bytes()==HEAD+text(*LINES[:count])

def test_the_withdrawal_spec_restores_the_bytes(tmp_path):
    owner=(os.getuid(),os.getgid())
    for mode,state in (('MOUNT',0),('ENABLE',1),('DISABLE_FAST',5),('DISABLE_FULL',4)):
        raw=HEAD+text(*LINES[:state]);path=put(tmp_path,raw);m,docs,host=k6b.fresh(mode)
        assert execute(path,spec_for(mode,owner))[0]==0
        back=M.edit_spec(docs.plan,(M.MODES[mode]['after'],),state);back['owner']=list(owner)
        assert execute(path,back)==(0,{'status':'ENV_EDIT_DONE','code':None}) and path.read_bytes()==raw

def test_the_script_is_what_the_scope_pins():
    assert f.sha(M.ENV_EDIT_SCRIPT.encode('ascii'))==M.ENV_EDIT_SCRIPT_SHA256==M.SCOPE['editor']['script_sha256']
    stdin=M.editor_stdin(spec_for('MOUNT',(1000,1000)))
    compile(stdin,'<editor>','exec')                                                     # the bytes the container runs are Python
    assert stdin.decode('ascii').count('\n')==M.ENV_EDIT_SCRIPT.count('\n')+1

def execute_with(path,spec,prelude):
    stdin=(PRCTL%'0').encode()+prelude.encode()+M.editor_stdin(spec).replace(b"TARGET='/c3po-env/.env'",("TARGET=%r"%str(path)).encode(),1)
    done=subprocess.run([sys.executable,'-I','-B','-'],input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,env={'PATH':'/usr/bin:/bin'})
    assert done.stderr==b'',done.stderr.decode()[-500:]
    return done.returncode,json.loads(done.stdout)

GROW='''import os
_fstat=os.fstat;_calls=[0]
def _second(fd):
    _calls[0]+=1
    if _calls[0]==2:
        with open(%r,'ab') as other:other.write(b'C3PO_SOMEONE=else\\n')
    return _fstat(fd)
os.fstat=_second
'''
SAME_SIZE='''import os
_fstat=os.fstat;_calls=[0]
def _second(fd):
    _calls[0]+=1
    if _calls[0]==2:
        info=_fstat(fd)
        with open(%r,'r+b') as other:other.write(b'Z')
        os.utime(%r,ns=(info.st_atime_ns,info.st_mtime_ns))
    return _fstat(fd)
os.fstat=_second
'''

def test_the_script_refuses_a_file_that_changed_between_its_read_and_its_write(tmp_path):
    """Review finding 7: another writer between the read and the write (an append, or the same size and mtime)."""
    owner=(os.getuid(),os.getgid());spec=spec_for('MOUNT',owner)
    path=put(tmp_path,HEAD);assert execute_with(path,spec,GROW%str(path))==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_CHANGED_DURING_THE_EDIT'})
    assert path.read_bytes()==HEAD+b'C3PO_SOMEONE=else\n'
    path=put(tmp_path,HEAD);assert execute_with(path,spec,SAME_SIZE%(str(path),str(path)))==(1,{'status':'ENV_EDIT_REFUSED','code':'ENV_FILE_CHANGED_DURING_THE_EDIT'})
    assert path.read_bytes()==b'Z'+HEAD[1:]

def test_a_file_larger_than_one_block_of_the_read(tmp_path):
    owner=(os.getuid(),os.getgid());big=b''.join(b'C3PO_FILLER_%06d=%s\n'%(index,b'x'*40) for index in range(2000))     # about 120 KiB
    path=put(tmp_path,big);assert execute(path,spec_for('MOUNT',owner))==(0,{'status':'ENV_EDIT_DONE','code':None})
    assert path.read_bytes()==big+(k6b.BLOCK[0]+'\n').encode()
    assert execute(path,spec_for('DISABLE_FULL',owner))==(0,{'status':'ENV_EDIT_DONE','code':None}) and path.read_bytes()==big


def test_the_editor_makes_itself_non_dumpable_before_it_opens_the_file(tmp_path):
    """A2 amendment 1 rev 3: no byte of .env in a process that can dump core. A prctl that fails leaves the file unopened."""
    owner=(os.getuid(),os.getgid());spec=spec_for('MOUNT',owner);path=put(tmp_path,HEAD);before=os.lstat(str(path))
    assert execute(path,spec,answer='-1')==(1,{'status':'ENV_EDIT_REFUSED','code':'EDITOR_DUMPABLE_NOT_DISABLED'})
    after=os.lstat(str(path));assert path.read_bytes()==HEAD and (after.st_mtime_ns,after.st_atime_ns)==(before.st_mtime_ns,before.st_atime_ns) or path.read_bytes()==HEAD
    assert execute(path,spec)==(0,{'status':'ENV_EDIT_DONE','code':None})        # the stand-in asserts prctl came before the open

def test_the_editor_without_prctl_refuses(tmp_path):
    """The real ctypes of this interpreter: on Linux prctl exists (the container); elsewhere the script fails closed."""
    owner=(os.getuid(),os.getgid());spec=spec_for('MOUNT',owner);path=put(tmp_path,HEAD)
    stdin=M.editor_stdin(spec).replace(b"TARGET='/c3po-env/.env'",("TARGET=%r"%str(path)).encode(),1)
    done=subprocess.run([sys.executable,'-I','-B','-'],input=stdin,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,env={'PATH':'/usr/bin:/bin'})
    line=json.loads(done.stdout)
    if sys.platform.startswith('linux'):assert line['status']=='ENV_EDIT_DONE'
    else:assert (done.returncode,line)==(1,{'status':'ENV_EDIT_REFUSED','code':'EDITOR_DUMPABLE_NOT_DISABLED'}) and path.read_bytes()==HEAD
