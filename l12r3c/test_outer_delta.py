"""NEW POSIX outer delta fixtures. No host/app/SQL/transport/timers/owner.
Callback writes are solely synthetic files inside this test's private temp dir.
"""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import os,time,tempfile,unittest
import finite_batch as c
import outer_limiter as o
import bounded_runner as inner
from synthetic_image_go_fixture import evidence as image_evidence

class Fixture:
    def __init__(self,root,bootstrap=False):
        self.root=Path(root);self.mark=time.monotonic()
        self.base=datetime(2026,10,12,4,0,tzinfo=timezone.utc) if bootstrap else o.now()
        self.context=(c.EPOCH,c.DAY,c.PREVIOUS,"BOOTSTRAP" if bootstrap else "P")
        authority=c.canonical({"fixture":"SYNTHETIC_NOT_REAL_AUTHORITY"});runtime=c.canonical({"fixture":"SYNTHETIC_NOT_RUNTIME"})
        operations=c.BOOTSTRAP if bootstrap else c.UPSTREAM
        lane="BOOTSTRAP_MONDAY" if bootstrap else "UPSTREAM_P"
        deadline=self.base-timedelta(hours=1)
        prepared=self.base-timedelta(hours=6 if bootstrap else 3)
        if bootstrap:deadline=datetime(2026,10,12,0,45,tzinfo=timezone.utc)
        self.q={"schema":"L12_FINITE_BATCH_REQUEST_CANDIDATE_V1","lane":lane,"epoch":c.EPOCH,"session":c.DAY,
                "previous_session":c.PREVIOUS,"track":self.context[-1],"prepared_at":c.iso(prepared),"owner_deadline":c.iso(deadline),
                "authority_sha256":c.sha(authority),"runtime_sha256":c.sha(runtime),"veto_authority_sha256":c.sha(b"SYNTHETIC_VETO_AUTH"),
                "initial_receipts":{},"tasks":[{"operation":op,"not_before":c.iso(self.base if bootstrap else self.base-timedelta(seconds=1)),
                "not_after":c.iso(self.base+timedelta(seconds=60)),"budget_seconds":1.0,"requires":list(c.MINIMUM_DEPENDENCIES[op])} for op in operations]}
        self.receipts={"prove":self.receipt("prove",self.base-timedelta(hours=4))}
        self.gos={}
        if bootstrap:
            self.receipts["epoch_pre"]=self.receipt("epoch_pre",prepared-timedelta(hours=1))
            self.q["initial_receipts"]={"epoch_pre":c.sha(self.receipts["epoch_pre"].raw)}
            for t in self.q["tasks"]:
                e=image_evidence(t["operation"],t);self.gos[t["operation"]]=e
                t.update(image_go_sha256=c.sha(e.go_raw),image_proposal_sha256=c.sha(e.proposal_raw))
        request=c.canonical(self.q)
        owner=c.canonical({"schema":"L12_OWNER_RECORD_CANDIDATE_V1","answer":"Assino","channel":"REGISTRO_PELA_FABLE",
            "request_sha256":c.sha(request),"question_sha256":c.sha(b"SYNTHETIC_QUESTION"),"question_published_at":c.iso(prepared+timedelta(seconds=1)),
            "signed_at":c.iso(prepared+timedelta(seconds=2))})
        docs=(("authority",authority),("owner",owner),("runtime",runtime))
        bound=c.canonical({"schema":"L12_BOUND_CANDIDATE_V1","request_sha256":c.sha(request),"documents_sha256":{k:c.sha(v) for k,v in docs},
                           "bound_at":c.iso(prepared+timedelta(seconds=3))})
        self.bundle=c.Bundle(request,bound,docs)
        self.services=c.Services(authority=self.authority,identity=lambda *a:None,receipt_read=lambda role,ctx:self.receipts.get(role),
                                 receipt_verify=lambda *a:None,operation_gate=lambda *a:None,veto_read=self.veto,veto_verify=lambda *a:None,
                                 image_go_read=lambda q,t,n:self.gos[t["operation"]],image_go_verify=lambda *a:None,execute=self.execute)
    def clock(self):return self.base+timedelta(seconds=time.monotonic()-self.mark)
    def receipt(self,role,at=None):
        at=at or self.clock();raw=c.canonical({"fixture":"SYNTHETIC_NOT_OPERATIONAL_RECEIPT","role":role,"at":c.iso(at)})
        return c.Receipt(raw,role,self.context,"COMPLETE",at)
    def authority(self,b,q,t,n):
        # Observe exact source-owned persisted marker/claim before ANY callback.
        key=c.sha(c.canonical(list(c.context(q)+(t["operation"],))))
        marker=c.strict(self.root.joinpath("consume-"+key).read_bytes())
        rows=[c.strict(line) for line in self.root.joinpath("attempts.ledger").read_bytes().splitlines()]
        c.need(marker["request_sha256"]==c.sha(b.request) and any(r["kind"]=="CLAIM" and r["attempt_key"]==key for r in rows),"FIXTURE_CLAIM_NOT_PERSISTED")
    def veto(self,q,t,n):return c.VetoView(b"SYNTHETIC_CURRENT_VETO",q["veto_authority_sha256"],"ALLOW",n,n+timedelta(seconds=5))
    def execute(self,call):
        with self.root.joinpath("effects.synthetic").open("ab") as s:s.write(b"1")
        return self.receipt(call.operation)

class TestOuterDelta(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="new-outer-fixture-",dir=Path(__file__).parent)
        os.chmod(self.temp.name,0o700);self.root=Path(self.temp.name);self.root.joinpath("attempts.ledger").write_bytes(b"");os.chmod(self.root/"attempts.ledger",0o600)
        self.ledger=c.DurableLedger(self.temp.name,c.measure_local_ledger(self.temp.name))
        self.outer=o.OuterLimiter(core_sha256=o.source_sha(c.__file__),outer_sha256=o.source_sha(o.__file__),hard_budget_seconds=.25)
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def batch(self,x=None,s=None,clock=None):
        x=x or Fixture(self.temp.name)
        return c.FiniteBatch(x.bundle,self.ledger,s or x.services,clock=clock or x.clock,monotonic=time.monotonic),x
    def effects(self):return self.root.joinpath("effects.synthetic").read_bytes() if self.root.joinpath("effects.synthetic").exists() else b""
    def consumed(self,b,op):
        with self.assertRaisesRegex(c.Hold,"ATTEMPT_ALREADY_CONSUMED"):self.outer.run(b,op)
    @staticmethod
    def hang(*a):time.sleep(10)
    def timeout(self,field,op="prove",bootstrap=False):
        x=Fixture(self.temp.name,bootstrap);b,_=self.batch(x,replace(x.services,**{field:self.hang}))
        begun=time.monotonic()
        with patch.object(o,"now",x.clock) if bootstrap else patch.object(o,"now",o.now):r=self.outer.run(b,op)
        self.assertLess(time.monotonic()-begun,1.25);self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(self.effects(),b"");self.consumed(b,op)
        rows=[c.strict(z) for z in self.root.joinpath("attempts.ledger").read_bytes().splitlines()]
        self.assertEqual([z["kind"] for z in rows],["CLAIM","TERMINAL"])
    def test_new_whole_invocation_exactly_once_after_parent_claim(self):
        b,x=self.batch();r=self.outer.run(b,"prove");self.assertEqual(r["status"],"ORIGINAL_COMPLETE_OBSERVED_CANDIDATE");self.assertEqual(self.effects(),b"1");self.consumed(b,"prove");self.assertEqual(self.effects(),b"1")
    def test_new_authority_callback_hang_bounded(self):self.timeout("authority")
    def test_new_identity_callback_hang_bounded(self):self.timeout("identity")
    def test_new_receipt_reader_hang_bounded(self):self.timeout("receipt_read","collect")
    def test_new_receipt_verifier_hang_bounded(self):self.timeout("receipt_verify","collect")
    def test_new_veto_reader_hang_bounded(self):self.timeout("veto_read")
    def test_new_veto_verifier_hang_bounded(self):self.timeout("veto_verify")
    def test_new_operation_gate_hang_bounded(self):self.timeout("operation_gate")
    def test_new_image_go_reader_hang_bounded(self):self.timeout("image_go_read","install_release",True)
    def test_new_image_go_verifier_hang_bounded(self):self.timeout("image_go_verify","install_release",True)
    def test_new_clock_callback_hang_bounded(self):
        b,x=self.batch(clock=self.hang);r=self.outer.run(b,"prove");self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(self.effects(),b"");self.consumed(b,"prove")
    def test_new_child_failure_consumed_no_effect(self):
        x=Fixture(self.temp.name);b,_=self.batch(x,replace(x.services,authority=lambda *a:os._exit(37)))
        r=self.outer.run(b,"prove");self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(self.effects(),b"");self.consumed(b,"prove")
    def test_new_late_cleanup_downgrades_after_effect(self):
        b,x=self.batch();original=self.outer._cleanup
        def late(pid):original(pid);time.sleep(.3)
        with patch.object(self.outer,"_cleanup",late):r=self.outer.run(b,"prove")
        self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(r["code"],"OUTER_DEADLINE_OR_WINDOW");self.assertEqual(self.effects(),b"1");self.consumed(b,"prove")
    def test_new_terminal_ledger_torn_remains_hold_consumed(self):
        b,x=self.batch();append=self.ledger._append
        def torn(rows,previous,key,kind,data):
            if kind=="TERMINAL":os.write(self.ledger.lfd,b'{"torn":');os.fsync(self.ledger.lfd);raise c.Hold("FIXTURE_TORN")
            return append(rows,previous,key,kind,data)
        with patch.object(self.ledger,"_append",torn):r=self.outer.run(b,"prove")
        self.assertEqual(r["code"],"TERMINAL_LEDGER_UNCERTAIN");self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.consumed(b,"prove")
        with self.assertRaisesRegex(c.Hold,"LEDGER_PARTIAL_OR_FULL"):self.outer.run(b,"collect")
        self.assertEqual(self.effects(),b"1")
    def test_new_direct_core_run_refuses_without_any_callback(self):
        x=Fixture(self.temp.name);b,_=self.batch(x,replace(x.services,authority=self.hang));begun=time.monotonic();r=b.run("prove")
        self.assertEqual(r["code"],"OUTER_LIMITER_REQUIRED");self.assertLess(time.monotonic()-begun,.2);self.assertEqual(self.effects(),b"");self.consumed(b,"prove")
    def test_new_changed_source_pin_consumed_before_fork(self):
        b,x=self.batch();self.outer.core_sha256=c.sha(b"OTHER_SOURCE");r=self.outer.run(b,"prove")
        self.assertEqual(r["code"],"OUTER_SOURCE_PIN_CHANGED");self.assertEqual(self.effects(),b"");self.consumed(b,"prove")
    def test_new_fork_failure_consumed_no_callback(self):
        b,x=self.batch()
        with patch.object(o.os,"fork",side_effect=OSError("SYNTHETIC_FORK_FAILURE")):r=self.outer.run(b,"prove")
        self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(self.effects(),b"");self.consumed(b,"prove")
    def test_new_forged_reservation_cannot_call_adapter(self):
        x=Fixture(self.temp.name);b,_=self.batch(x,replace(x.services,authority=self.hang));r=b.run_reserved("prove",c.sha(b"FORGED"))
        self.assertEqual(r["code"],"RESERVATION_SCOPE_INVALID");self.assertEqual(self.effects(),b"")
    def test_new_late_callback_cannot_continue_after_outer_timeout(self):
        x=Fixture(self.temp.name)
        def late(*a):time.sleep(.6);self.root.joinpath("effects.synthetic").write_bytes(b"LATE")
        b,_=self.batch(x,replace(x.services,authority=late));r=self.outer.run(b,"prove");time.sleep(.7)
        self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(self.effects(),b"");self.consumed(b,"prove")
    def test_new_uncertain_effect_once_then_hang_consumed(self):
        x=Fixture(self.temp.name)
        def issued(i):self.root.joinpath("effects.synthetic").write_bytes(b"1");time.sleep(10)
        b,_=self.batch(x,replace(x.services,execute=issued));r=self.outer.run(b,"prove")
        self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(self.effects(),b"1");self.consumed(b,"prove");self.assertEqual(self.effects(),b"1")
    def test_new_same_group_descendant_cannot_write_after_timeout(self):
        x=Fixture(self.temp.name)
        def descendant(*a):
            pid=os.fork()
            if pid==0:
                time.sleep(.7);self.root.joinpath("effects.synthetic").write_bytes(b"ESCAPED");os._exit(0)
            time.sleep(10)
        b,_=self.batch(x,replace(x.services,authority=descendant));r=self.outer.run(b,"prove");time.sleep(.8)
        self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(self.effects(),b"")
    def test_new_inherited_inner_runner_completes_in_outer_session(self):
        import sys
        x=Fixture(self.temp.name);path=Path(sys.executable).resolve()
        source=('from pathlib import Path\nPath('+repr(str(self.root/'effects.synthetic'))+').write_bytes(b"1")\nprint("SYNTHETIC_INNER_RECEIPT_ONLY")\n').encode()
        command=inner.Command('prove',x.context,c.sha(x.bundle.request),c.sha(x.bundle.bound),(str(path),'-I','-B','-'),source,
            inner.digest(source),inner.digest(source),(),inner.DirectoryPin(str(self.root),inner.directory_identity(self.root.stat())),
            inner.ExecutablePin(str(path),inner.file_identity(path.stat()),inner.digest(path.read_bytes())),
            (('SYNTHETIC_RUNTIME',c.sha(b'SYNTHETIC_RUNTIME')),),4096,4096,
            'FD_EXEC_LINUX' if sys.platform.startswith('linux') else 'NAMED_EXEC_POSIX')
        stages=('AUTHORITY','RUNTIME','CURRENT_PINS','RECEIPT_ABI','RECEIPT_PROVENANCE')
        def approval(stage):
            def callback(inv,cmd,sha,n):return inner.Approval(stage,sha,inner.digest(inner.canonical(cmd.body())),cmd.context,cmd.current_pins,n,n+timedelta(seconds=5))
            return callback
        def decode(transport,inv,cmd):return inner.ReceiptView(transport.stdout,cmd.operation,cmd.context,'COMPLETE',transport.completed_at)
        functions=[approval(stages[0]),approval(stages[1]),approval(stages[2]),decode,lambda v,t,*a:v.raw==t.stdout==b'SYNTHETIC_INNER_RECEIPT_ONLY\n']
        bindings=tuple(inner.Binding('SYNTHETIC:'+stage,c.sha(('SYNTHETIC_'+stage).encode()),fn) for stage,fn in zip(stages,functions))
        registry=inner.Registry(os.getuid(),(command,),tuple((stage,b.identity,b.source_sha256) for stage,b in zip(stages,bindings)),'INHERITED_OUTER_GROUP')
        runner=inner.BoundedRunner(registry,inner.digest(registry.raw()),authority_verifier=bindings[0],runtime_verifier=bindings[1],pins_verifier=bindings[2],receipt_decoder=bindings[3],receipt_verifier=bindings[4])
        b,_=self.batch(x,replace(x.services,execute=runner.service(c.Receipt)));self.outer.hard_budget=1.0
        r=self.outer.run(b,'prove');self.assertEqual(r['status'],'ORIGINAL_COMPLETE_OBSERVED_CANDIDATE',r);self.assertEqual(self.effects(),b'1');self.consumed(b,'prove')

if __name__=="__main__":unittest.main(verbosity=2)
