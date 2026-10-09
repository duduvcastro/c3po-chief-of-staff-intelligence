"""NEW R5b clock defect only. Module clock patches are SYNTHETIC fixtures.
No app imports, physical readback, real authority, operational execution or GO.
"""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import unittest
from unittest.mock import patch
import image_capacity_gate as b
import image_path_adapter as a
import finite_batch as c
from synthetic_gate_fixture import fixture, OPEN
from synthetic_bridge_plan import DownFixture

class NativeClockDelta(unittest.TestCase):
    def setUp(self):
        self.s,self.receipt,self.row,self.records,self.manifest,self.ready,self.catalog,self.directory=fixture()
        self.plan=DownFixture();self.s=replace(self.s,finite_authority_sha256=self.plan.q['authority_sha256'])
        self.at=OPEN-timedelta(minutes=29);self.observed=self.at;self.mono=100.
        self.task=self.plan.task('reader_bound');self.task['budget_seconds']=10
        self.root=a.DirectoryPin(1,99,0)
        self.epoch=a.FileEvidence(a.canonical({'schema':'MASSIVE_SESSION_ROOT_V1','epoch':a.EPOCH,'device':1,'inode':99}),1,5,0,0,0o600,1)
        self.calls=[]
    def snapshot(self):
        return b.Snapshot(a.canonical(self.receipt),a.canonical(self.row),a.canonical(self.records),self.manifest,self.observed,
                         self.epoch,self.root,'/synthetic-private-journal')
    def read(self,*args):
        self.calls.append(('reader',args[2]));return self.snapshot()
    def verify(self,*args):self.calls.append(('verifier',args[3]));return None
    def gate(self,read=None,verify=None,**kwargs):
        return b.ImageCapacityGate(self.s,read or self.read,verify or self.verify,
                                   journal_directory='/synthetic-private-journal',**kwargs)
    def call(self,gate):
        with patch.object(b,'_native_utc',lambda:self.at),patch.object(b.time,'monotonic',lambda:self.mono):
            return gate(self.plan.q,'BEFORE_READER_PROCESS_LAUNCH',OPEN-timedelta(minutes=30),self.task)
    def refuses(self,code,callback):
        with self.assertRaises(c.Hold) as error:callback()
        self.assertEqual(error.exception.args,(code,))
    def test_constructor_rejects_injected_clock_before_callbacks(self):
        self.refuses('IMAGE_CLOCK_INJECTION_FORBIDDEN',lambda:self.gate(clock=lambda:self.at))
        self.assertEqual(self.calls,[])
    def test_supplied_phase_timestamp_cannot_override_native_window(self):
        self.at=c.instant(self.task['not_after'])
        self.refuses('IMAGE_TASK_WINDOW_CLOSED',lambda:self.call(self.gate()))
        self.assertEqual(self.calls,[])
    def test_source_owned_native_clock_is_passed_to_reader_and_verifier(self):
        self.assertIsNone(self.call(self.gate()))
        self.assertEqual(self.calls,[('reader',self.at),('verifier',self.at)])
        self.assertFalse(hasattr(self.gate(),'clock'))
    def test_source_native_clock_refuses_stale_snapshot(self):
        self.observed=self.at-timedelta(seconds=5,microseconds=1)
        self.refuses('IMAGE_SNAPSHOT_NOT_FRESH',lambda:self.call(self.gate()))
        self.assertEqual([x[0]for x in self.calls],['reader'])
    def test_wall_regression_after_verifier_refuses(self):
        def verifier(*args):self.at-=timedelta(microseconds=1)
        self.refuses('IMAGE_CLOCK_REGRESSION',lambda:self.call(self.gate(verify=verifier)))
    def test_monotonic_budget_blocks_frozen_wall_during_verifier(self):
        self.task['budget_seconds']=1
        def verifier(*args):self.mono+=1.001
        self.refuses('IMAGE_GATE_DEADLINE',lambda:self.call(self.gate(verify=verifier)))
    def test_monotonic_freshness_blocks_frozen_wall_during_full_chain_hash(self):
        original=a._journal_records
        def parser(records):
            yield from original(records)
            self.mono+=5.001
        with patch.object(a,'_journal_records',parser):
            self.refuses('IMAGE_SNAPSHOT_NOT_FRESH',lambda:self.call(self.gate()))
    def test_task_window_rechecked_after_reader_before_verifier(self):
        def reader(*args):
            snapshot=self.snapshot();self.at=c.instant(self.task['not_after']);return snapshot
        self.refuses('IMAGE_TASK_WINDOW_CLOSED',lambda:self.call(self.gate(read=reader)))
        self.assertEqual(self.calls,[])
    def test_monotonic_regression_after_parser_refuses(self):
        original=a._journal_records
        def parser(records):
            yield from original(records)
            self.mono-=.001
        with patch.object(a,'_journal_records',parser):
            self.refuses('IMAGE_CLOCK_REGRESSION',lambda:self.call(self.gate()))

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(NativeClockDelta))
    root=Path(__file__).parent
    (root/'NEW_CLOCK_RESULT.json').write_bytes(a.canonical({'schema':'CODEX_GATE_R5B_NEW_CLOCK_DELTA_RESULT_V1',
      'new_methods':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
      'closed_methods_repeated':0,'bridge_sha256':a.sha((root/'image_capacity_gate.py').read_bytes()),
      'adapter_sha256':a.sha((root/'image_path_adapter.py').read_bytes()),'mode':'SYNTHETIC_ONLY',
      'clock_tests':'Source-module patches for explicit fixtures only; constructor injection is refused.',
      'app_imports':0,'host_sql_operations':0,'operational_GO':False,'linux_proof':'PENDING'})+b'\n')
    raise SystemExit(0 if result.wasSuccessful()else 1)
