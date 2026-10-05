"""parts/runner.py: the runner with real processes (standard input, time and output limits, environment, working
directory), the command table, the budget rule before an effect, and the accounting of an effect command.
No docker, no host: the real processes are /bin/cat, /bin/echo, /bin/sleep, /usr/bin/env, /usr/bin/yes and the like."""
import os
import sys
import time

import pytest

import demos
import family as f
import hostemu

@pytest.fixture(params=['selftest_read','selftest_write'])
def m(request):return f.load(demos.DIRECTORIES[request.param]).m
W=lambda:f.load(demos.WRITE).m
R=lambda:f.load(demos.READ).m
gate=lambda:30.0
refusal=f.refusal

# ---------------------------------------------------------------- NativeRunner, real processes
def test_native_runner_fixed_environment_working_directory_and_exit_status(m):
    native=m.Native()
    assert native.run(['/bin/echo','hello'],gate,5)==(0,b'hello\n') and native.run(['/bin/echo','hello'],gate,5,False)==(0,b'')
    assert native.run(['/usr/bin/false'],gate,5)[0]==1 and native.run(['/bin/pwd'],gate,5)==(0,b'/\n')
    code,out=native.run(['/usr/bin/env'],gate,5);assert code==0 and sorted(out.decode().split())==['LANG=C','LC_ALL=C','PATH=/usr/bin:/bin']
    code,out=native.run(['/usr/bin/env'],gate,5,True,'/etc/c3po-bar/docker-cli',None,{'C3PO_BUILD_SHA':'a'*40})
    assert sorted(out.decode().split())==['C3PO_BUILD_SHA='+'a'*40,'DOCKER_CONFIG=/etc/c3po-bar/docker-cli','LANG=C','LC_ALL=C','PATH=/usr/bin:/bin']
    assert native.identity()==(os.geteuid(),os.getegid())

def test_native_runner_writes_the_bytes_on_standard_input_and_closes_it(m):
    native=m.Native();big=bytes(range(256))*512                                   # 128 KiB: more than a pipe holds
    assert native.run(['/bin/cat'],gate,10,True,None,b'one line\n')==(0,b'one line\n')
    code,out=native.run(['/bin/cat'],gate,10,True,None,big,None,len(big));assert code==0 and out==big
    assert native.run(['/usr/bin/wc','-c'],gate,10,True,None,big)[1].split()==[b'131072']
    # a program read from standard input, as the pinned snippets are: python sees EOF and runs it
    code,out=native.run([sys.executable,'-I','-B','-','argument'],gate,20,True,None,b'import sys\nprint(sys.argv[1:],sys.stdin.read()=="")\n')
    assert (code,out)==(0,b"['argument'] True\n")
    # without bytes the child's standard input is /dev/null: it reads nothing and is not left waiting
    assert native.run(['/bin/cat'],gate,5)==(0,b'')
    # a child that never reads its input, and one that exits before it is all written: neither blocks the runner
    assert native.run(['/usr/bin/true'],gate,10,True,None,big)==(0,b'')
    assert native.run(['/bin/sh','-c','exit 7'],gate,10,True,None,big)[0]==7
    assert native.run(['/bin/cat'],gate,10,False,None,b'discarded\n')==(0,b'')

def test_native_runner_time_limit_output_limit_and_expiry(m):
    native=m.Native()
    for capture in (True,False):
        started=time.monotonic()
        with pytest.raises(m.Refused,match='COMMAND_TIMEOUT'):native.run(['/bin/sleep','5'],gate,0.3,capture)
        assert time.monotonic()-started<3
    with pytest.raises(m.Refused,match='COMMAND_TIMEOUT'):native.run(['/bin/sleep','5'],gate,0.3,True,None,b'x'*200000)   # input nobody reads
    with pytest.raises(m.Refused,match='COMMAND_TIMEOUT'):native.run(['/bin/sleep','5'],lambda:0.3,30)                    # the budget is the shorter limit
    with pytest.raises(m.Refused,match='COMMAND_OUTPUT_LIMIT'):native.run(['/usr/bin/yes'],gate,5)
    with pytest.raises(m.Refused,match='COMMAND_OUTPUT_LIMIT'):native.run(['/bin/cat'],gate,5,True,None,b'x'*5000,None,4096)
    assert native.run(['/bin/cat'],gate,5,True,None,b'x'*4096,None,4096)==(0,b'x'*4096)
    def expired():raise m.Refused('GO_EXPIRED')
    with pytest.raises(m.NotStarted,match='GO_EXPIRED'):native.run(['/bin/echo','x'],expired,5)       # before any process: nothing ran
    calls=[0]
    def expires_later():
        calls[0]+=1
        if calls[0]>3:raise m.Refused('GO_EXPIRED')
        return 30.0
    with pytest.raises(m.Refused,match='GO_EXPIRED') as caught:native.run(['/bin/sleep','5'],expires_later,10)
    assert type(caught.value) is m.Refused,'an expiry while the process runs is not NotStarted'

def test_native_runner_says_not_started_only_when_no_process_was_created(m):
    native=m.Native()
    for argv in (['/nonexistent/binary'],['/etc/hosts'],['/']):
        with pytest.raises(m.NotStarted,match='COMMAND_NOT_STARTED'):native.run(argv,gate,5)
    assert issubclass(m.NotStarted,m.Refused)
    with pytest.raises(m.Refused) as caught:native.run(['/bin/sleep','5'],gate,0.2)
    assert type(caught.value) is m.Refused,'a timeout is never NotStarted'

def test_native_runner_leaves_no_process_and_no_descriptor_behind(m,tmp_path):
    native=m.Native();marker=tmp_path/'pid'
    before=len(os.listdir('/dev/fd'))
    with pytest.raises(m.Refused):native.run(['/bin/sh','-c','echo $$ > %s; exec sleep 30'%marker],gate,0.5)
    pid=int(marker.read_text());time.sleep(0.2)
    with pytest.raises(ProcessLookupError):os.kill(pid,0)
    for index in range(20):native.run(['/bin/cat'],gate,5,True,None,b'x')
    assert len(os.listdir('/dev/fd'))==before

def gone(pid,seconds=3.0):
    """True once no process has this pid (a killed process that lost its parent is reaped by init a moment later)."""
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        try:os.kill(pid,0)
        except ProcessLookupError:return True
        time.sleep(0.05)
    return False

def test_native_runner_gives_the_command_a_session_and_a_process_group_of_its_own(m):
    code,out=m.Native().run([sys.executable,'-B','-c','import os;print(os.getpid(),os.getpgrp(),os.getsid(0))'],gate,20)
    pid,group,session=[int(item) for item in out.split()]
    assert code==0 and pid==group==session and group!=os.getpgrp(),'the command leads its own group: the group kill reaches it and what it started, and nothing else'

@pytest.mark.parametrize('label,script,capture,limit,code',[
    ('timeout','sleep 30 & echo $! > %s; wait',True,65536,'COMMAND_TIMEOUT'),
    ('timeout_without_capture','sleep 30 & echo $! > %s; wait',False,65536,'COMMAND_TIMEOUT'),
    ('command_ended_and_left_a_process_holding_its_output','sleep 30 & echo $! > %s; exit 0',True,65536,'COMMAND_TIMEOUT'),
    ('output_limit','sleep 30 & echo $! > %s; exec /usr/bin/yes',True,4096,'COMMAND_OUTPUT_LIMIT')])
def test_native_runner_kills_the_whole_process_group_when_a_call_does_not_end_by_itself(m,tmp_path,label,script,capture,limit,code):
    """What a command started as a process of its own (the compose plugin of a docker CLI) ends with it. A process
    left behind would go on acting after the run has sealed its receipt and released the deployment lock."""
    marker=tmp_path/label;started=time.monotonic()
    with pytest.raises(m.Refused,match=code):m.Native().run(['/bin/sh','-c',script%marker],gate,0.8,capture,None,None,None,limit)
    assert time.monotonic()-started<4
    child=int(marker.read_text());assert child!=os.getpid() and gone(child),'the process the command started is still running'

def test_native_runner_kills_nothing_when_the_command_returns(m,tmp_path):
    """A command that returned is reaped and its group is left alone: its pid may belong to anything by then."""
    marker=tmp_path/'left';native=m.Native()
    assert native.run(['/bin/sh','-c','sleep 30 > /dev/null 2>&1 & echo $! > %s; exit 3'%marker],gate,10)==(3,b'')
    child=int(marker.read_text())
    try:os.kill(child,0)                                  # still there: a normal return kills nothing
    finally:os.kill(child,9)
    assert gone(child)


# ---------------------------------------------------------------- Commands on the emulated host
def commands(m,host=None,remaining=lambda:60.0):
    host=host or f.wire(types_k(m),hostemu.world());return m.Commands(host,remaining),host
def types_k(m):
    import types;return types.SimpleNamespace(m=m)

def test_command_starts_only_a_signed_row_with_its_fixed_prefix_middle_and_tail():
    m=W();c,host=commands(m)
    c.output('image',hostemu.BACKEND)
    assert host.commands[-1]['argv']==['/usr/bin/docker','image','inspect','--format',m.IMAGE_FORMAT,hostemu.BACKEND] and host.commands[-1]['seconds']==8
    with pytest.raises(KeyError):c.call('no_such_row')
    with pytest.raises(KeyError):c.call('image; rm -rf /')
    assert c.calls==1 and c.started=={'READ':1,'CONTAINER':0,'EFFECT':0}
    # the class of the row decides the time and the output limit the runner receives
    c.output('render',*m.compose_arguments(hostemu.PROJECT,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE],True),stdin=demos.override(),variables={'C3PO_BUILD_SHA':hostemu.REVISION})
    last=host.commands[-1];assert (last['seconds'],last['limit'],last['stdin'],last['variables'])==(15,1048576,demos.override(),{'C3PO_BUILD_SHA':hostemu.REVISION})
    assert last['argv'][1:2]==['compose'] and last['argv'][-3:]==['config','--format','json'],'the tail is fixed by the row'

def test_command_refusals_before_any_process_are_not_started_and_start_nothing():
    m=W()
    cases=[(lambda c:c.call('image'),None),                                                    # (a call that is fine, for the count below)
           (lambda c:c.call('container_list','unexpected'),'COMMAND_ARGUMENTS'),              # the row takes no argument
           (lambda c:c.call('image',''),'COMMAND_ARGUMENTS'),(lambda c:c.call('image','a\x00b'),'COMMAND_ARGUMENTS'),(lambda c:c.call('image',7),'COMMAND_ARGUMENTS'),
           (lambda c:c.call('image',*['x']*65),'COMMAND_ARGUMENTS'),
           (lambda c:c.call('image','x',stdin=b'bytes'),'COMMAND_STDIN'),(lambda c:c.call('render','x'),'COMMAND_STDIN'),
           (lambda c:c.call('render','x',stdin=b''),'COMMAND_STDIN'),(lambda c:c.call('render','x',stdin='text'),'COMMAND_STDIN'),
           (lambda c:c.call('render','x',stdin=b'x'*131073),'COMMAND_STDIN'),
           (lambda c:c.call('image','x',docker_config='relative/path'),'COMMAND_VARIABLES'),(lambda c:c.call('image','x',docker_config='/a b'),'COMMAND_VARIABLES'),
           (lambda c:c.call('image','x',variables={'PATH':'/evil'}),'COMMAND_VARIABLES'),(lambda c:c.call('image','x',variables={'LD_PRELOAD':'/x'}),'COMMAND_VARIABLES'),
           (lambda c:c.call('image','x',variables={'DOCKER_CONFIG':'/x'}),'COMMAND_VARIABLES'),(lambda c:c.call('image','x',variables={'C3PO_BUILD_SHA':'development'}),'COMMAND_VARIABLES'),
           (lambda c:c.call('image','x',variables=[('C3PO_BUILD_SHA','a'*40)]),'COMMAND_VARIABLES'),
           (lambda c:c.call('recreate','x'),'COMMAND_KIND'),(lambda c:c.call('script','x',stdin=b'x'),'COMMAND_KIND'),(lambda c:c.output('recreate','x'),'COMMAND_KIND')]
    for action,code in cases[1:]:
        c,host=commands(m)
        with pytest.raises(m.NotStarted) as caught:action(c)
        assert str(caught.value)==code and host.commands==[] and c.calls==0 and c.started=={'READ':0,'CONTAINER':0,'EFFECT':0},code

def test_only_a_read_row_with_a_fixed_template_is_started_directly_every_other_row_through_its_helper():
    """A CONTAINER row only through container_run() (the image by ID, read-only binds, the command grammar), an EFFECT
    row only through effect() (counted), the row whose template comes at call time only through
    container_environment() (booleans, never a value). A direct call starts nothing."""
    r=R();w=W();run=(hostemu.BACKEND,'python');template=('{{json .Config.Env}}','a'*64)
    cases=[(r,lambda c:c.call('verify',*run,stdin=b'x')),(r,lambda c:c.output('verify',*run,stdin=b'x')),
           (r,lambda c:c.call('container_environment',*template)),(r,lambda c:c.output('container_environment',*template)),
           (w,lambda c:c.output('container_environment',*template)),
           (r,lambda c:c.call('image','x',through='effect')),(r,lambda c:c.call('image','x',through='container_run')),
           (r,lambda c:c.call('image','x',through='container_environment')),(r,lambda c:c.output('image','x',through='container_environment')),
           (r,lambda c:c.call('verify',*run,stdin=b'x',through='effect')),(r,lambda c:c.call('verify',*run,stdin=b'x',through='container_environment')),
           (r,lambda c:c.call('verify',*run,stdin=b'x',through=True)),
           (r,lambda c:c.output('container_environment',*template,through='container_run')),(r,lambda c:c.output('container_environment',*template,through='effect')),
           (w,lambda c:c.call('script',*run,stdin=b'x',through='container_run')),(w,lambda c:c.call('script',*run,stdin=b'x',through=True)),
           (w,lambda c:c.call('recreate','x',through='container_run')),(w,lambda c:c.call('recreate','x',through='container_environment'))]
    for m,action in cases:
        c,host=commands(m);host.docker.on_run=lambda call:(0,b'')
        with pytest.raises(m.NotStarted,match='COMMAND_KIND'):action(c)
        assert host.commands==[] and c.calls==0 and c.started=={'READ':0,'CONTAINER':0,'EFFECT':0}
    assert r.STARTED_THROUGH=={'READ':None,'CONTAINER':'container_run','EFFECT':'effect'} and r.TEMPLATE_AT_CALL_TIME=='container_environment' and r.SECRET_ENVIRONMENT_ROW=='container_secret_environment'
    # the helpers are the way in, and each is the way in for its own kind only
    c,host=commands(r);host.docker.on_run=lambda call:(0,b'{}\n')
    assert r.container_run(c,'verify',hostemu.BACKEND,[],['python'],b'x')['returned'] and c.started['CONTAINER']==1
    worker=r.container_facts(c,hostemu.WORKER)['id']
    assert r.container_environment(c,worker,{'C3PO_BUILD_SHA':hostemu.REVISION})=={'C3PO_BUILD_SHA':{'present':True,'equal':True}}
    assert refusal(lambda:r.container_run(c,'image',hostemu.BACKEND,[],['python'],b'x'))=='COMMAND_KIND'

def test_binary_must_be_root_owned_not_writable_and_executable_or_nothing_starts():
    m=W()
    for change,expected in ((lambda node:setattr(node,'uid',1000),'BINARY_UNAVAILABLE_OR_UNSAFE'),(lambda node:setattr(node,'mode',0o775),'BINARY_UNAVAILABLE_OR_UNSAFE'),
                            (lambda node:setattr(node,'mode',0o644),'BINARY_UNAVAILABLE_OR_UNSAFE'),(lambda node:setattr(node,'kind','symlink'),'BINARY_UNAVAILABLE_OR_UNSAFE')):
        c,host=commands(m);change(host.tree.get('/usr/bin/docker'))
        with pytest.raises(m.NotStarted,match=expected):c.call('image','x')
        with pytest.raises(m.NotStarted,match=expected):c.call('image','x')               # remembered: the walk is not repeated
        assert host.commands==[] and len([entry for entry in host.log if entry[0]=='lstat' and entry[1]=='/usr/bin/docker'])==1
    c,host=commands(m);host.tree.remove('/usr/bin/docker');host.tree.add('/usr/local/bin/docker',kind='file',content=b'ELF')
    c.output('image',hostemu.BACKEND);assert host.commands[-1]['argv'][0]=='/usr/local/bin/docker'
    c,host=commands(m);host.tree.get('/usr/bin').mode=0o777
    with pytest.raises(m.NotStarted,match='BINARY_UNAVAILABLE_OR_UNSAFE'):c.call('image','x')

def test_a_tool_that_timed_out_twice_is_not_started_again():
    m=W();c,host=commands(m);host.hang={'docker'}
    for attempt in range(2):
        with pytest.raises(m.Refused,match='COMMAND_TIMEOUT') as caught:c.call('image','x')
        assert type(caught.value) is m.Refused
    with pytest.raises(m.NotStarted,match='COMMAND_SKIPPED_AFTER_TIMEOUT'):c.call('image','x')
    assert len(host.commands)==2 and c.calls==2 and c.started['READ']==2 and m.MAX_TOOL_TIMEOUTS==2

def test_output_is_a_refusal_with_the_exit_status_when_the_command_fails():
    m=W();c,host=commands(m)
    with pytest.raises(m.CommandFailed) as caught:c.output('image','sha256:'+'0'*64)
    assert str(caught.value)=='COMMAND_FAILED' and caught.value.returncode==1 and m.safe(caught.value)=={'status':'UNAVAILABLE','code':'COMMAND_FAILED','returncode':1}

@pytest.mark.parametrize('name,seconds',[('script',20),('recreate',30)])
def test_an_effect_is_not_started_unless_its_whole_class_and_the_reserve_fit_the_budget(name,seconds):
    """A command killed by the budget would leave its effect unknown: it is refused while nothing has changed."""
    m=W();need=seconds+m.AFTER_EFFECT_RESERVE_SECONDS
    for remaining,starts in ((need+0.01,True),(need,True),(need-0.01,False),(1.0,False)):
        host=f.wire(types_k(m),hostemu.world());host.docker.on_run=lambda call:(0,b'');c=m.Commands(host,lambda:remaining);state=m.Effects()
        middle=m.compose_arguments(hostemu.PROJECT,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE]) if name=='recreate' else m.run_arguments('script',hostemu.BACKEND,[],['python'])
        result=m.effect(state,c,name,*middle,stdin=b'x' if name=='script' else None,variables={'C3PO_BUILD_SHA':hostemu.REVISION} if name=='recreate' else None)
        assert result['started'] is starts
        if not starts:
            assert result=={'started':False,'returned':False,'returncode':None,'output':b'','code':'COMMAND_NOT_STARTED_BUDGET'} and host.commands==[]
            assert state.counts()=={'issued':1,'succeeded':0,'failed_nothing_changed':1,'uncertain':0} and state.clean() and not state.pending
    # a READ row has no such rule: it runs with whatever is left
    host=f.wire(types_k(m),hostemu.world());c=m.Commands(host,lambda:1.0);c.output('image',hostemu.BACKEND);assert len(host.commands)==1

def test_effects_budget_is_the_sum_of_the_classes_plus_one_reserve():
    m=W();assert m.effects_budget('script','recreate')==20+30+4 and m.effects_budget('recreate')==34 and m.effects_budget()==4
    assert refusal(lambda:m.effects_budget('image'))=='COMMAND_KIND'
    r=R();assert r.effects_budget('verify')==24

def test_effect_accounting_not_started_unknown_and_left_pending_for_the_caller():
    m=W();arguments=m.compose_arguments(hostemu.PROJECT,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE]);variables={'C3PO_BUILD_SHA':hostemu.REVISION}
    def attempt(prepare):
        host=f.wire(types_k(m),hostemu.world());prepare(host);c=m.Commands(host,lambda:60.0);state=m.Effects()
        return m.effect(state,c,'recreate',*arguments,variables=variables),state,host
    # returned: the caller settles it; until then the call is uncertain and the run is not clean
    result,state,host=attempt(lambda host:None)
    assert result=={'started':True,'returned':True,'returncode':0,'output':b'','code':None} and state.pending and not state.clean() and state.counts()['uncertain']==1
    state.done();assert state.counts()=={'issued':1,'succeeded':1,'failed_nothing_changed':0,'uncertain':0} and host.commands[-1]['capture'] is False
    # a non-zero exit is still "returned": only a readback tells what happened
    result,state,host=attempt(lambda host:setattr(host.docker.compose,'up_returncode',1))
    assert result['returned'] and result['returncode']==1 and state.pending
    state.unknown();assert state.counts()['uncertain']==1 and not state.clean()
    # nothing started: failed, nothing changed, the run can still be a refusal
    for prepare,code in ((lambda host:host.absent.add('docker'),'COMMAND_NOT_STARTED'),(lambda host:host.tree.remove('/usr/bin/docker'),'BINARY_UNAVAILABLE_OR_UNSAFE')):
        result,state,host=attempt(prepare)
        assert (result['started'],result['code'])==(False,code) and state.clean() and not state.pending and state.counts()['failed_nothing_changed']==1
    # started and not returned: unknown, whether the effect happened (hang_after) or not (hang)
    for group in ('hang','hang_after'):
        result,state,host=attempt(lambda host:getattr(host,group).add(('compose','up')))
        assert result=={'started':True,'returned':False,'returncode':None,'output':b'','code':'COMMAND_TIMEOUT'} and not state.pending and not state.clean()
        assert state.counts()=={'issued':1,'succeeded':0,'failed_nothing_changed':0,'uncertain':1}
        assert (('compose-recreate',hostemu.WORKER) in host.log)==(group=='hang_after')
    # an exception that is not a refusal after the process existed: unknown as well
    def explode(host):
        def hook(host,name,detail,calls):
            if name=='run':raise RuntimeError('injected')
        host.hook=hook
    result,state,host=attempt(explode);assert (result['started'],result['returned'],result['code'])==(True,False,'COMMAND_FAILED') and state.counts()['uncertain']==1
    # the death of the process: nothing is settled, the call stays pending, and the last resort of run() calls it uncertain
    def die(host):
        def hook(host,name,detail,calls):
            if name=='run':raise hostemu.Death('dead')
        host.hook=hook
    host=f.wire(types_k(m),hostemu.world());die(host);state=m.Effects()
    with pytest.raises(hostemu.Death):m.effect(state,m.Commands(host,lambda:60.0),'recreate',*arguments,variables=variables)
    assert state.pending and not state.clean()

def test_effect_refuses_a_row_that_is_not_an_effect_before_anything_is_counted():
    m=W();c,host=commands(m);state=m.Effects()
    assert refusal(lambda:m.effect(state,c,'image','x'))=='COMMAND_KIND' and state.issued==0 and host.commands==[]

def test_a_reading_source_cannot_start_an_effect_row_even_if_its_table_had_one(monkeypatch):
    r=R();c,host=commands(r);state=r.Effects()
    monkeypatch.setitem(r.COMMANDS,'recreate',r.command_row('docker',['compose'],'x','RECREATE','EFFECT',tail=r.compose_up_tail('r2d2-worker')))
    result=r.effect(state,c,'recreate',*r.compose_arguments(hostemu.PROJECT,hostemu.ENV_FILE,[hostemu.COMPOSE_FILE]),variables={'C3PO_BUILD_SHA':hostemu.REVISION})
    assert (result['started'],result['code'])==(False,'COMMAND_KIND') and host.commands==[] and state.clean()

def test_emulated_runner_and_real_runner_take_the_same_arguments():
    """The emulated host's run() has the signature of NativeRunner.run(), so nothing is passed that only one of them takes."""
    import inspect
    m=W();real=inspect.signature(m.NativeRunner.run);fake=inspect.signature(hostemu.FakeHost.run)
    assert [(name,parameter.default) for name,parameter in real.parameters.items()]==[(name,parameter.default) for name,parameter in fake.parameters.items()]
    for name in ('umask','mkdir','create','write','fsync','link','unlink'):
        assert list(inspect.signature(getattr(m.NativeFiles,name)).parameters)==list(inspect.signature(getattr(hostemu.FakeHost,name)).parameters),name
    for name in ('flock','pause'):
        assert list(inspect.signature(getattr(m.NativeLock,name)).parameters)==list(inspect.signature(getattr(hostemu.FakeHost,name)).parameters),name
    for name in ('identity','noatime','open','close','fstat','lstat','fstatvfs','read','names'):
        assert list(inspect.signature(getattr(m.NativeRead,name)).parameters)==list(inspect.signature(getattr(hostemu.FakeHost,name)).parameters),name
