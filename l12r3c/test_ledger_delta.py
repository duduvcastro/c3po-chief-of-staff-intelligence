"""NEW crossaudit corrections only; closed 43/20/22/1 methods not imported/run."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import fcntl,os,signal,tempfile,time,unittest
import finite_batch as c
import outer_limiter as o
from synthetic_outer_fixture import Fixture

class LedgerDelta(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="new-ledger-delta-",dir=Path(__file__).parent)
        self.root=Path(self.temp.name);os.chmod(self.root,0o700)
        self.root.joinpath("attempts.ledger").write_bytes(b"");os.chmod(self.root/"attempts.ledger",0o600)
        self.ledger=c.DurableLedger(str(self.root),c.measure_local_ledger(str(self.root)),lock_budget_seconds=.08)
        self.outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=1)
        self.x=Fixture(self.root)
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def scope(self,op):return self.x.context+(op,)
    def claim(self,op):return self.ledger.claim(self.scope(op),c.sha(self.x.bundle.request),c.sha(self.x.bundle.bound),None)
    def rows(self):return [c.strict(z) for z in self.root.joinpath("attempts.ledger").read_bytes().splitlines()]
    def files(self,prefix):return sorted(p.name for p in self.root.iterdir() if p.name.startswith(prefix))
    def batch(self,services=None,bundle=None):return c.FiniteBatch(bundle or self.x.bundle,self.ledger,services or self.x.services,clock=self.x.clock,monotonic=time.monotonic)
    def effects(self):return self.root.joinpath("effects.synthetic").read_bytes() if self.root.joinpath("effects.synthetic").exists() else b""
    def real_fixture_execute(self,inv):
        receipt=self.x.receipt(inv.operation)
        self.root.joinpath("fixture-receipt-"+inv.operation).write_bytes(receipt.raw)
        with self.root.joinpath("effects.synthetic").open("ab") as file:file.write(inv.operation.encode()+b";")
        return receipt
    def load_receipt(self,op):
        raw=self.root.joinpath("fixture-receipt-"+op).read_bytes();at=c.instant(c.strict(raw)["at"])
        self.x.receipts[op]=c.Receipt(raw,op,self.x.context,"COMPLETE",at)
        return self.x.receipts[op]
    def complete_prove(self):
        batch=self.batch(replace(self.x.services,execute=self.real_fixture_execute));result=self.outer.run(batch,"prove")
        self.assertEqual(result["status"],"ORIGINAL_COMPLETE_OBSERVED_CANDIDATE",result)
        return batch,self.load_receipt("prove")
    def test_new_busy_lock_returns_no_reservation_without_orphan(self):
        fd=os.open(self.root/"attempts.ledger",os.O_RDWR)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);begin=time.monotonic()
            result=self.outer.run(self.batch(),"prove")
            self.assertLess(time.monotonic()-begin,.4)
            self.assertEqual(result["status"],"REFUSED_NOT_RESERVED");self.assertEqual(result["code"],"LEDGER_LOCK_DEADLINE_NO_RESERVATION")
            self.assertEqual(self.files("consume-"),[]);self.assertEqual(self.rows(),[])
        finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
        self.assertTrue(self.claim("prove"));self.assertEqual(len(self.rows()),1)
    def test_new_inherited_flock_description_cannot_bypass_parent_lock(self):
        read_fd,write_fd=os.pipe()
        with self.ledger._lock():
            pid=os.fork()
            if pid==0:
                os.close(read_fd)
                try:
                    try:self.claim("prove");raw=b"BYPASSED"
                    except c.ReservationFailure as error:raw=str(error).encode()
                    os.write(write_fd,raw)
                finally:os._exit(0)
            os.close(write_fd);raw=os.read(read_fd,512);os.waitpid(pid,0);os.close(read_fd)
            self.assertEqual(raw,b"LEDGER_LOCK_DEADLINE_NO_RESERVATION")
        self.assertEqual(self.files("consume-"),[])
    def test_new_different_scope_concurrent_claims_preserve_marker_equality(self):
        pids=[]
        for op in ("prove","collect"):
            pid=os.fork()
            if pid==0:
                try:self.claim(op)
                except BaseException:os._exit(2)
                os._exit(0)
            pids.append(pid)
        self.assertEqual([os.waitpid(pid,0)[1] for pid in pids],[0,0])
        self.assertEqual(len(self.rows()),2);self.assertEqual(len(self.files("consume-")),2);self.assertEqual(len(self.files("reserved-")),2)
        self.ledger._rows()
    def test_new_same_scope_concurrency_has_one_durable_claim(self):
        pids=[]
        for index in range(2):
            pid=os.fork()
            if pid==0:
                try:self.claim("prove");os._exit(0)
                except c.ReservationFailure as error:os._exit(3 if error.consumed and str(error)=="ATTEMPT_ALREADY_CONSUMED" else 4)
            pids.append(pid)
        self.assertEqual(sorted(os.waitpid(pid,0)[1]>>8 for pid in pids),[0,3])
        self.assertEqual(len(self.rows()),1);self.assertEqual(len(self.files("consume-")),1)
    def test_new_orphan_before_claim_adopted_uncertain_and_next_scope_lives(self):
        with patch.object(self.ledger,"_append",side_effect=c.Hold("SYNTHETIC_CRASH_BEFORE_CLAIM")):
            with self.assertRaises(c.ReservationFailure):self.claim("prove")
        self.assertEqual(self.rows(),[]);self.assertEqual(len(self.files("consume-")),1)
        self.claim("collect");rows=self.rows()
        self.assertEqual([r["kind"] for r in rows],["CLAIM","TERMINAL","CLAIM"])
        self.assertEqual(rows[1]["data"]["status"],"UNCERTAIN_CONSUMED");self.assertEqual(rows[1]["data"]["code"],"ORPHAN_MARKER")
        self.assertEqual(self.effects(),b"")
        with self.assertRaisesRegex(c.ReservationFailure,"ATTEMPT_ALREADY_CONSUMED"):self.claim("prove")
    def test_new_claim_without_commit_proof_cannot_effect_and_is_adopted(self):
        with patch.object(self.ledger,"_commit_claim",side_effect=c.Hold("SYNTHETIC_CRASH_BEFORE_COMMIT")):
            with self.assertRaises(c.ReservationFailure):self.claim("prove")
        key=self.rows()[0]["attempt_key"]
        with self.assertRaisesRegex(c.Hold,"RESERVATION_COMMIT_MISSING"):
            self.ledger.check_reserved(self.scope("prove"),c.sha(self.x.bundle.request),c.sha(self.x.bundle.bound),key)
        self.claim("collect");self.assertEqual(self.rows()[1]["data"]["code"],"ORPHAN_MARKER");self.assertEqual(self.effects(),b"")
    def test_new_committed_claim_retained_marker_detects_ledger_truncation(self):
        self.claim("prove");os.ftruncate(self.ledger.lfd,0);os.fsync(self.ledger.lfd)
        result=self.outer.run(self.batch(),"collect")
        self.assertEqual(result["code"],"LEDGER_COMMITTED_HISTORY_TRUNCATED");self.assertEqual(result["status"],"REFUSED_NOT_RESERVED")
        self.assertEqual(len(self.files("consume-")),1);self.assertEqual(self.effects(),b"")
    def test_new_committed_terminal_detects_terminal_history_truncation(self):
        self.complete_prove();raw=c.canonical(self.rows()[0])+b"\n";os.ftruncate(self.ledger.lfd,0);os.write(self.ledger.lfd,raw);os.fsync(self.ledger.lfd)
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"LEDGER_COMMITTED_HISTORY_TRUNCATED")
        self.assertEqual(len(self.files("consume-")),1)
    def test_new_orphan_wrong_anchor_refuses_without_silent_superset(self):
        with patch.object(self.ledger,"_append",side_effect=c.Hold("SYNTHETIC_CRASH")):
            with self.assertRaises(c.ReservationFailure):self.claim("prove")
        path=next(self.root.glob("consume-*"));marker=c.strict(path.read_bytes());marker["previous_sha256"]=c.sha(b"WRONG_ANCHOR");path.write_bytes(c.canonical(marker))
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"LEDGER_ORPHAN_ANCHOR_CHANGED");self.assertEqual(self.rows(),[])
    def test_new_partial_marker_refuses_recovery_and_next_effect(self):
        key=c.sha(c.canonical(list(self.scope("prove"))));path=self.root/("consume-"+key);path.write_bytes(b'{"partial":');os.chmod(path,0o600)
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["status"],"REFUSED_NOT_RESERVED");self.assertEqual(self.effects(),b"")
    def test_new_partial_terminal_keeps_explicit_global_hold(self):
        self.claim("prove");os.write(self.ledger.lfd,b'{"torn":');os.fsync(self.ledger.lfd)
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"LEDGER_PARTIAL_OR_FULL");self.assertEqual(len(self.files("consume-")),1)
    def test_new_claim_timestamp_native_utc_ignores_supplied_future(self):
        before=datetime.now(timezone.utc);self.ledger.claim(self.scope("prove"),c.sha(self.x.bundle.request),c.sha(self.x.bundle.bound),datetime(2099,1,1,tzinfo=timezone.utc));after=datetime.now(timezone.utc)
        self.assertTrue(before<=c.instant(self.rows()[0]["data"]["at"])<=after)
    def test_new_finish_waits_bounded_lock_release_then_commits(self):
        key=self.claim("prove");read_fd,write_fd=os.pipe();pid=os.fork()
        if pid==0:
            os.close(read_fd);fd=os.open(self.root/"attempts.ledger",os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX);os.write(write_fd,b"LOCKED");time.sleep(.03);os.close(fd);os._exit(0)
        os.close(write_fd);self.assertEqual(os.read(read_fd,64),b"LOCKED");os.close(read_fd)
        self.ledger.finish(key,{"status":"REFUSED_CONSUMED","code":"SYNTHETIC_REFUSAL"});os.waitpid(pid,0)
        self.assertEqual(len(self.rows()),2);self.assertEqual(len(self.files("terminal-")),1)
    def test_new_terminal_error_preserves_internal_refusal_code(self):
        def refuse(*a):raise c.Hold("SYNTHETIC_AUTHORITY_REFUSED")
        with patch.object(self.ledger,"finish",side_effect=c.Hold("SYNTHETIC_STORAGE_UNCERTAIN")):
            result=self.outer.run(self.batch(replace(self.x.services,authority=refuse)),"prove")
        self.assertEqual(result["status"],"UNCERTAIN_CONSUMED");self.assertEqual(result["code"],"TERMINAL_LEDGER_UNCERTAIN")
        self.assertEqual(result["inner_code"],"SYNTHETIC_AUTHORITY_REFUSED");self.assertEqual(result["inner_result"]["code"],"SYNTHETIC_AUTHORITY_REFUSED")
    def test_new_dependency_from_before_bound_refuses_without_effect(self):
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"DEPENDENCY_BEFORE_BOUND");self.assertEqual(self.effects(),b"")
    def test_new_unanchored_fresh_dependency_is_refused(self):
        self.x.receipts["prove"]=self.x.receipt("prove")
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"DEPENDENCY_TERMINAL_MISSING");self.assertEqual(self.effects(),b"")
    def test_new_refused_predecessor_cannot_be_replaced_by_fresh_fixture(self):
        def refuse(*a):raise c.Hold("SYNTHETIC_PROVE_REFUSED")
        self.outer.run(self.batch(replace(self.x.services,authority=refuse)),"prove");self.x.receipts["prove"]=self.x.receipt("prove")
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"DEPENDENCY_TERMINAL_NOT_COMPLETE_MATCH");self.assertEqual(self.effects(),b"")
    def test_new_durable_complete_dependency_advances_one_next_effect(self):
        self.complete_prove();result=self.outer.run(self.batch(replace(self.x.services,execute=self.real_fixture_execute)),"collect")
        self.assertEqual(result["status"],"ORIGINAL_COMPLETE_OBSERVED_CANDIDATE",result);self.assertEqual(self.effects(),b"prove;collect;")
    def test_new_dependency_replaced_bytes_refused_against_terminal_hash(self):
        _,receipt=self.complete_prove();self.x.receipts["prove"]=replace(receipt,raw=c.canonical({"fixture":"DIFFERENT_SYNTHETIC_BYTES"}))
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"DEPENDENCY_TERMINAL_NOT_COMPLETE_MATCH");self.assertEqual(self.effects(),b"prove;")
    def test_new_dependency_completion_time_must_match_original_terminal(self):
        _,receipt=self.complete_prove();self.x.receipts["prove"]=replace(receipt,completed_at=receipt.completed_at-timedelta(seconds=.1))
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"DEPENDENCY_TERMINAL_NOT_COMPLETE_MATCH")
    def test_new_terminal_not_committed_before_crash_cannot_certify_dependency(self):
        with patch.object(self.ledger,"_commit_terminal",side_effect=c.Hold("SYNTHETIC_TERMINAL_COMMIT_LOSS")):
            result=self.outer.run(self.batch(replace(self.x.services,execute=self.real_fixture_execute)),"prove")
        self.assertEqual(result["status"],"UNCERTAIN_CONSUMED");self.load_receipt("prove")
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"DEPENDENCY_TERMINAL_NOT_DURABLE_COMPLETE");self.assertEqual(self.effects(),b"prove;")
    def test_new_direct_run_claim_failure_returns_data_without_callbacks(self):
        fd=os.open(self.root/"attempts.ledger",os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX)
        try:result=self.batch().run("prove")
        finally:os.close(fd)
        self.assertEqual(result["status"],"REFUSED_NOT_RESERVED");self.assertEqual(result["effect_calls"],0);self.assertEqual(self.files("consume-"),[])
    def test_new_sigkill_after_durable_marker_recovers_only_uncertain(self):
        create=self.ledger._create;pid=os.fork()
        if pid==0:
            def crash(name,value):
                create(name,value)
                if name.startswith("consume-"):os.kill(os.getpid(),signal.SIGKILL)
            with patch.object(self.ledger,"_create",crash):self.claim("prove")
            os._exit(2)
        self.assertEqual(os.waitpid(pid,0)[1]&0x7f,signal.SIGKILL)
        self.claim("collect");self.assertEqual(self.rows()[1]["data"]["code"],"ORPHAN_MARKER");self.assertEqual(self.effects(),b"")
    def test_new_sigkill_after_claim_commit_preserves_consume_without_global_brick(self):
        commit=self.ledger._commit_claim;pid=os.fork()
        if pid==0:
            def crash(*args):commit(*args);os.kill(os.getpid(),signal.SIGKILL)
            with patch.object(self.ledger,"_commit_claim",crash):self.claim("prove")
            os._exit(2)
        self.assertEqual(os.waitpid(pid,0)[1]&0x7f,signal.SIGKILL)
        self.claim("collect");self.assertEqual([r["kind"] for r in self.rows()],["CLAIM","CLAIM"])
        result=self.outer.run(self.batch(),"prove");self.assertEqual(result["code"],"ATTEMPT_ALREADY_CONSUMED");self.assertEqual(self.effects(),b"")
    def test_new_sigkill_terminal_before_commit_recovers_uncertain_proof(self):
        key=self.claim("prove");append=self.ledger._append;pid=os.fork()
        if pid==0:
            def crash(*args):
                row=append(*args)
                if args[3]=="TERMINAL":os.kill(os.getpid(),signal.SIGKILL)
                return row
            with patch.object(self.ledger,"_append",crash):self.ledger.finish(key,{"status":"REFUSED_CONSUMED","code":"SYNTHETIC_REFUSAL"})
            os._exit(2)
        self.assertEqual(os.waitpid(pid,0)[1]&0x7f,signal.SIGKILL)
        self.claim("collect");proof,_=self.ledger._file("terminal-"+key)
        self.assertEqual(proof["committed_status"],"UNCERTAIN_CONSUMED");self.assertEqual(len(self.rows()),3)
    def test_new_sigkill_torn_claim_tail_is_explicit_hold_without_new_markers(self):
        pid=os.fork()
        if pid==0:
            def crash(*args):os.write(self.ledger.lfd,b'{"torn":');os.fsync(self.ledger.lfd);os.kill(os.getpid(),signal.SIGKILL)
            with patch.object(self.ledger,"_append",crash):self.claim("prove")
            os._exit(2)
        self.assertEqual(os.waitpid(pid,0)[1]&0x7f,signal.SIGKILL)
        result=self.outer.run(self.batch(),"collect");self.assertEqual(result["code"],"LEDGER_PARTIAL_OR_FULL");self.assertEqual(len(self.files("consume-")),1)

if __name__=="__main__":unittest.main(verbosity=2)
