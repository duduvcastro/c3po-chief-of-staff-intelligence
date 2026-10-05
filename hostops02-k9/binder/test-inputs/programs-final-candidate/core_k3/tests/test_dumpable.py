"""The process made non-dumpable (the token family's revision of the core, CORE.md section 14): dumps_disabled() of the
core part, as every source carries it, with a stand-in C library injected (the order and the arguments of the two
prctl calls, a first call that fails with an errno, an attribute that reads back 1 or 2, a library without prctl or
whose call raises), the C library a source loads itself (ctypes.CDLL(None, use_errno=True), loaded inside the function
and never handed out), NativeRead.not_dumpable(), the emulated host's call, the C library of tests/oslevel.py, and, on
Linux only, the real kernel in a child process (the process of this suite is never made non-dumpable).
What the kernel then does with a signal that dumps core (nothing reaches kernel.core_pattern, a pipe or a file) needs
root and is shown by the Linux job of the token family (its linux_root/dump_proof.py), not here."""
import ctypes
import errno
import json
import os
import subprocess
import sys

import pytest

import demos
import family as f
import hostemu
import oslevel

ENV={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1'}
LINUX=sys.platform.startswith('linux')
SOURCES=(demos.READ,demos.WRITE)

class Stub:
    """A C library whose prctl answers from a script and records every call: answers maps an option number to what
    that call returns (an int, or an exception to raise); errno is set as the real C library sets it on a failure."""
    def __init__(self,answers,number=None):self.answers,self.number,self.calls=dict(answers),number,[]
    def prctl(self,*arguments):
        self.calls.append(arguments);answer=self.answers.get(arguments[0],-1)
        if isinstance(answer,BaseException):raise answer
        if answer==-1 and self.number is not None:ctypes.set_errno(self.number)
        return answer

def refused(action):
    """The code of the Refused the action raises, with nothing but the code in it."""
    with pytest.raises(ValueError) as caught:action()
    error=caught.value;assert type(error).__name__=='Refused' and error.args==(str(error),)
    assert error.__cause__ is None and error.__context__ is None,'no exception of the C library rides along'
    return str(error)

@pytest.mark.parametrize('directory',SOURCES,ids=['read','write'])
def test_the_attribute_is_set_to_0_and_read_back_0_in_that_order(directory):
    m=f.load(directory).m;library=Stub({4:0,3:0})
    assert (m.PR_GET_DUMPABLE,m.PR_SET_DUMPABLE)==(3,4)
    assert m.dumps_disabled(library) is True and library.calls==[(4,0,0,0,0),(3,0,0,0,0)]

@pytest.mark.parametrize('directory',SOURCES,ids=['read','write'])
def test_a_first_call_that_fails_with_an_errno_is_a_refusal_and_nothing_is_read_back(directory):
    m=f.load(directory).m
    for number in (errno.EPERM,errno.EINVAL,errno.ENOSYS):
        library=Stub({4:-1,3:0},number)
        assert refused(lambda:m.dumps_disabled(library))=='PROCESS_DUMPABLE_NOT_DISABLED' and library.calls==[(4,0,0,0,0)]
    library=Stub({4:1,3:0});assert refused(lambda:m.dumps_disabled(library))=='PROCESS_DUMPABLE_NOT_DISABLED' and library.calls==[(4,0,0,0,0)]

@pytest.mark.parametrize('directory',SOURCES,ids=['read','write'])
def test_an_attribute_that_does_not_read_back_0_is_a_refusal(directory):
    m=f.load(directory).m
    for answer in (1,2,-1):
        library=Stub({4:0,3:answer},errno.EINVAL)
        assert refused(lambda:m.dumps_disabled(library))=='PROCESS_DUMPABLE_NOT_DISABLED' and library.calls==[(4,0,0,0,0),(3,0,0,0,0)]

@pytest.mark.parametrize('directory',SOURCES,ids=['read','write'])
def test_a_library_without_prctl_or_whose_call_raises_is_a_refusal(directory):
    m=f.load(directory).m
    for library in (object(),None.__class__,Stub({4:OSError(errno.EPERM,'x')}),Stub({4:0,3:RuntimeError('x')}),Stub({4:'0',3:0})):
        assert refused(lambda:m.dumps_disabled(library))=='PROCESS_DUMPABLE_NOT_DISABLED'

def test_the_library_is_the_interpreter_s_own_loaded_inside_the_function(monkeypatch):
    """Without a library the function loads ctypes.CDLL(None, use_errno=True): the C library the interpreter itself is
    linked with (dlopen of the program), once, with errno kept by ctypes; NativeRead.not_dumpable() is that call. A
    library that cannot be loaded is a refusal, never an OSError."""
    loads=[];library=Stub({4:0,3:0})
    def load(*arguments,**options):loads.append((arguments,options));return library
    monkeypatch.setattr(ctypes,'CDLL',load)
    for directory in SOURCES:
        m=f.load(directory).m;del loads[:];del library.calls[:]
        assert m.dumps_disabled() is True and loads==[((None,),{'use_errno':True})] and library.calls==[(4,0,0,0,0),(3,0,0,0,0)]
        del loads[:];del library.calls[:]
        assert m.Native().not_dumpable() is True and loads==[((None,),{'use_errno':True})] and library.calls==[(4,0,0,0,0),(3,0,0,0,0)]
        assert m.NativeRead.not_dumpable is m.Native.not_dumpable
    def missing(*arguments,**options):raise OSError(errno.ENOENT,'x')
    monkeypatch.setattr(ctypes,'CDLL',missing)
    assert refused(lambda:f.load(demos.WRITE).m.Native().not_dumpable())=='PROCESS_DUMPABLE_NOT_DISABLED'

def test_the_emulated_host_records_the_call_and_can_refuse_as_the_core_does():
    k=f.load(demos.WRITE);host=f.world(k)
    assert host.dumpable==1 and host.not_dumpable() is True and host.dumpable==0 and host.log==[('not_dumpable',)] and host.mutating()==[]
    host=f.world(k);host.dumpable_refused=True
    assert refused(host.not_dumpable)=='PROCESS_DUMPABLE_NOT_DISABLED' and host.dumpable==1 and host.log==[('not_dumpable',)]

def test_the_c_library_of_the_os_level_substitution_records_and_emulates(tmp_path):
    m=f.load(demos.WRITE).m
    with oslevel.Substitute(tmp_path) as record:
        assert m.Native().not_dumpable() is True
        library=ctypes.CDLL(None,use_errno=True)
        assert (library.prctl(4,1,0,0,0),library.prctl(3,0,0,0,0),library.prctl(7,0,0,0,0),library.prctl(4,2,0,0,0))==(0,1,-1,-1)
    assert ctypes.CDLL is record.real_cdll and record.of('dlopen')[0]=={'call':'dlopen','name':None,'arguments':[],'options':{'use_errno':True}}
    assert [(entry['option'],entry['arguments'],entry['result']) for entry in record.of('prctl')][:2]==[(4,[0,0,0,0],0),(3,[0,0,0,0],0)]
    assert record.libraries[0].dumpable==0 and record.libraries[1].dumpable==1

@pytest.mark.skipif(LINUX,reason='Linux has prctl: the real call is made in a child process (the test below)')
def test_without_prctl_the_real_library_refuses():
    """macOS: the C library of the interpreter has no prctl, and the function refuses (nothing else happens)."""
    assert refused(f.load(demos.WRITE).m.dumps_disabled)=='PROCESS_DUMPABLE_NOT_DISABLED'

CHILD='''
import ctypes,json,sys
sys.path.insert(0,sys.argv[1])
import demos,family
library=ctypes.CDLL(None,use_errno=True)
before=library.prctl(3,0,0,0,0)
m=family.load(demos.WRITE).m
done=m.Native().not_dumpable()
after=library.prctl(3,0,0,0,0)
again=m.dumps_disabled()
print(json.dumps({'before':before,'done':done,'after':after,'again':again,'last':library.prctl(3,0,0,0,0)}))
'''
@pytest.mark.skipif(not LINUX,reason='prctl(2) is Linux; the real kernel is exercised by the Linux job')
def test_the_real_kernel_in_a_child_process():
    """A fresh interpreter is dumpable (1); after the source's own NativeRead.not_dumpable() the kernel answers 0, and
    making it so again is harmless. A child, so that the process of this suite keeps its own attribute."""
    done=subprocess.run([sys.executable,'-B','-c',CHILD,str(f.CORE/'tests')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=ENV,timeout=120)
    assert done.returncode==0 and done.stderr==b'',done.stderr.decode()[-2000:]
    assert json.loads(done.stdout)=={'before':1,'done':True,'after':0,'again':True,'last':0}
