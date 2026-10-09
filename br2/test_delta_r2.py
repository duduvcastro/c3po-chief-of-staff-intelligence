"""Only NEW R2 deltas: no R1 test imports or repeated 22-method suite."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

import bounded_runner as r

CTX=('12-16','2026-10-12','P','SYNTHETIC_ONLY')

@dataclass(frozen=True)
class Invocation:
    operation: str
    context: tuple[str,str,str,str]
    request_sha256: str
    bound_sha256: str
    deadline_utc: datetime
    deadline_monotonic: float
    original_receipts: tuple = ()


def fixture(root, containment='OWN_SESSION'):
    path=Path(sys.executable).resolve()
    command=r.Command('fixture',CTX,'1'*64,'2'*64,(str(path),'-I','-B','-'),b'print("FIXTURE_ONLY")\n',
        r.digest(b'print("FIXTURE_ONLY")\n'),r.digest(b'print("FIXTURE_ONLY")\n'),(),
        r.DirectoryPin(str(root),r.directory_identity(root.stat())),
        r.ExecutablePin(str(path),r.file_identity(path.stat()),r.digest(path.read_bytes())),
        (('synthetic_runtime','3'*64),),4096,4096,
        'FD_EXEC_LINUX' if sys.platform.startswith('linux') else 'NAMED_EXEC_POSIX')
    stages=('AUTHORITY','RUNTIME','CURRENT_PINS','RECEIPT_ABI','RECEIPT_PROVENANCE')
    def approve(stage):
        def callback(inv,cmd,sha,now):
            return r.Approval(stage,sha,r.digest(r.canonical(cmd.body())),cmd.context,cmd.current_pins,
                              now,now+timedelta(seconds=5))
        return callback
    def decode(transport,inv,cmd):
        return r.ReceiptView(transport.stdout,cmd.operation,cmd.context,'COMPLETE',transport.completed_at)
    callbacks=[approve(stages[0]),approve(stages[1]),approve(stages[2]),decode,
               lambda view,transport,*args:view.raw==transport.stdout==b'FIXTURE_ONLY\n']
    bindings=tuple(r.Binding('fixture:'+stage,'4'*64,fn) for stage,fn in zip(stages,callbacks))
    registry=r.Registry(os.getuid(),(command,),tuple((stage,b.identity,b.source_sha256)
                          for stage,b in zip(stages,bindings)),containment)
    runner=r.BoundedRunner(registry,r.digest(registry.raw()),authority_verifier=bindings[0],
        runtime_verifier=bindings[1],pins_verifier=bindings[2],receipt_decoder=bindings[3],receipt_verifier=bindings[4])
    inv=Invocation('fixture',CTX,'1'*64,'2'*64,datetime.now(timezone.utc)+timedelta(seconds=2),time.monotonic()+2)
    return runner,inv


class Hostile:
    def __hash__(self):raise AssertionError('must not hash before type guard')
    def __eq__(self,other):raise AssertionError('must not compare before type guard')


class NewR2DeltaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='codex-runner-r2-delta-fixture-')
        self.root=Path(self.temp.name).resolve();self.root.chmod(0o700)
        self.runner,self.inv=fixture(self.root)
    def tearDown(self):self.temp.cleanup()
    def guard(self,callback,code):
        with self.assertRaises(r.RunnerError) as caught:callback()
        self.assertEqual(caught.exception.code,code)
    def test_new_hostile_operation_guard_before_unique_hash(self):
        command=replace(self.runner.registry.commands[0],operation=Hostile())
        registry=replace(self.runner.registry,commands=(command,))
        self.guard(lambda:registry.validate('5'*64),'REGISTRY_OPERATION_INVALID')
        self.guard(registry.raw,'REGISTRY_OPERATION_INVALID')
    def test_new_hostile_argv_guard_before_prefix_equality(self):
        command=replace(self.runner.registry.commands[0],argv=(Hostile(),'-I','-B','-'))
        self.guard(command.validate,'REGISTRY_ARGV_INVALID')
    def test_new_hostile_source_pin_guard_before_digest_equality(self):
        for name in ('source_sha256','stdin_sha256'):
            command=replace(self.runner.registry.commands[0],**{name:Hostile()})
            self.guard(command.validate,'REGISTRY_SOURCE_INPUT_PIN_CHANGED')
    def test_new_invocation_with_descriptors_or_opaque_clock_is_rejected(self):
        class Evil:
            @property
            def operation(self):raise AssertionError('must not invoke property')
        self.guard(lambda:self.runner.run(Evil()),'FIXED_CORE_INVOCATION_REQUIRED')
        changed=replace(self.inv,deadline_utc=Hostile())
        self.guard(lambda:self.runner.run(changed),'INVOCATION_CLOCK_PRIMITIVES_REQUIRED')
    def test_new_inherited_mode_requires_real_outer_group_owner(self):
        read_fd,write_fd=os.pipe();pid=os.fork()
        if pid==0:
            os.close(read_fd)
            try:
                runner,inv=fixture(self.root,'INHERITED_OUTER_GROUP')
                runner.run(inv)
                result=b'UNEXPECTED_SUCCESS'
            except r.RunnerError as error:result=error.code.encode()
            os.write(write_fd,result);os.close(write_fd);os._exit(0)
        os.close(write_fd)
        try:
            ready,_,_=select.select([read_fd],[],[],2);self.assertTrue(ready)
            self.assertEqual(os.read(read_fd,4096),b'OUTER_GROUP_UNAVAILABLE')
        finally:
            os.close(read_fd)
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
            os.waitpid(pid,0)
    def test_new_containment_mode_is_part_of_registry_pin(self):
        object.__setattr__(self.runner.registry,'containment','INHERITED_OUTER_GROUP')
        self.guard(lambda:self.runner.run(self.inv),'REGISTRY_PIN_CHANGED')
    def test_new_outer_owned_session_retains_inner_group_until_outer_cleanup(self):
        probe=b'''import os,sys,signal,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from test_delta_r2 import fixture
root=Path(sys.argv[2]);runner,inv=fixture(root,'INHERITED_OUTER_GROUP')
view=runner.run(inv)
print(json.dumps({'raw':view.raw.decode(),'parent_pid':os.getpid(),'group':os.getpgrp(),'session':os.getsid(0)}),flush=True)
signal.pause()
'''
        process=subprocess.Popen((sys.executable,'-I','-B','-',str(Path(__file__).resolve().parent),str(self.root)),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            process.stdin.write(probe);process.stdin.close()
            ready,_,_=select.select([process.stdout],[],[],3)
            self.assertTrue(ready,'fixture outer proof absent')
            raw=process.stdout.readline()
            self.assertTrue(raw,'fixture outer exited before proof')
            proof=json.loads(raw)
            self.assertEqual(proof['raw'],'FIXTURE_ONLY\n')
            self.assertEqual(proof['parent_pid'],process.pid)
            self.assertEqual(proof['group'],process.pid)
            self.assertEqual(proof['session'],process.pid)
        finally:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait(timeout=1)
            for stream in (process.stdout,process.stderr):stream.close()


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NewR2DeltaTests))
    Path('DELTA_RESULT.json').write_bytes(r.canonical({'schema':'CODEX_BOUNDED_RUNNER_R2_DELTA_RESULT_V1',
        'methods':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'scope':'NEW_PRIMITIVE_GUARDS_AND_OUTER_INHERITANCE_FIXTURES_ONLY','r1_methods_repeated':0,
        'operational_commands':0,'app_imports':0,'sql_docker_ssh':0,'linux_runtime_proof':'PENDING'}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
