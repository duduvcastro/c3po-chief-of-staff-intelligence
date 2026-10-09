"""NEW parent-loss fixture; no closed 22-test suite imports or repeats."""
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import os,select,signal,tempfile,time,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class ParentLossDelta(unittest.TestCase):
    def test_new_parent_loss_stops_callback_at_hard_deadline_before_cleanup_gap(self):
        with tempfile.TemporaryDirectory(prefix="new-parent-loss-fixture-",dir=Path(__file__).parent) as directory:
            root=Path(directory);os.chmod(root,0o700)
            root.joinpath("attempts.ledger").write_bytes(b"");os.chmod(root/"attempts.ledger",0o600)
            ledger=c.DurableLedger(str(root),c.measure_local_ledger(str(root)));read_fd,write_fd=os.pipe()
            fixture=Fixture(root)
            def delayed_effect(*args):
                os.write(write_fd,b"CALLBACK_STARTED")
                time.sleep(.5)
                # Old watchdog deadline + cleanup(.6) + .1 allowed this write.
                root.joinpath("effects.synthetic").write_bytes(b"LATE_AFTER_PARENT_LOSS")
                time.sleep(10)
            batch=c.FiniteBatch(fixture.bundle,ledger,replace(fixture.services,authority=delayed_effect),
                                clock=fixture.clock,monotonic=time.monotonic)
            outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),
                                 hard_budget_seconds=.3,cleanup_budget_seconds=.6)
            parent_pid=os.fork()
            if parent_pid==0:
                os.close(read_fd)
                try:outer.run(batch,"prove")
                finally:os._exit(0)
            os.close(write_fd)
            try:
                ready,_,_=select.select([read_fd],[],[],2)
                self.assertTrue(ready,"fixture worker callback never started")
                self.assertEqual(os.read(read_fd,64),b"CALLBACK_STARTED")
                os.kill(parent_pid,signal.SIGKILL);os.waitpid(parent_pid,0);parent_pid=None
                time.sleep(.7)
                self.assertFalse(root.joinpath("effects.synthetic").exists())
                rows=[c.strict(raw) for raw in root.joinpath("attempts.ledger").read_bytes().splitlines()]
                self.assertEqual([row["kind"] for row in rows],["CLAIM"])
                self.assertTrue(root.joinpath("consume-"+rows[0]["attempt_key"]).is_file())
                with self.assertRaisesRegex(c.Hold,"ATTEMPT_ALREADY_CONSUMED"):
                    outer.run(batch,"prove")
            finally:
                os.close(read_fd)
                if parent_pid is not None:
                    os.kill(parent_pid,signal.SIGKILL);os.waitpid(parent_pid,0)
                ledger.close()

if __name__=="__main__":unittest.main(verbosity=2)
