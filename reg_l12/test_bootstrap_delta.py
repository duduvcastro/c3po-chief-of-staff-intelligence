"""NEW synthetic bootstrap delta only. No actual GO, owner, receipt or host."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import os,tempfile,unittest
import finite_batch as f
from bootstrap_fixtures import Fixture as Utility,BASE,CTX
MON=datetime(2026,10,12,4,0,tzinfo=timezone.utc)

class Fixture(Utility):
    def __init__(self):
        super().__init__("UPSTREAM_P")
        self.now=MON;self.reads=self.verifies=0;self.gos={}
        self.receipts["epoch_pre"]=self.original("epoch_pre",BASE-timedelta(hours=3),kind="K11_FULL_PRE")
        self.q.update(lane="BOOTSTRAP_MONDAY",track="BOOTSTRAP",owner_deadline="2026-10-12T00:45:00Z",
                      initial_receipts={"epoch_pre":f.sha(self.receipts["epoch_pre"].raw)},tasks=[])
        for op in f.BOOTSTRAP:
            t={"operation":op,"not_before":f.iso(MON),"not_after":f.iso(MON+timedelta(minutes=10)),
               "budget_seconds":60,"requires":list(f.MINIMUM_DEPENDENCIES[op])}
            e=self.evidence(op,t);self.gos[op]=e
            t.update(image_go_sha256=f.sha(e.go_raw),image_proposal_sha256=f.sha(e.proposal_raw));self.q["tasks"].append(t)
        self.rebuild()
        self.services=replace(self.services,image_go_read=self.go_read,image_go_verify=self.go_verify)
    def original(self,role,at=None,status="COMPLETE",kind=None):
        at=at or self.now
        raw=f.canonical({"fixture":"SYNTHETIC_NOT_OPERATIONAL_RECEIPT","role":role,"context":list(CTX),"status":status,
                         "completed_at":f.iso(at),"kind":kind or ("K11_POST" if role=="readback" else role)})
        return f.Receipt(raw,role,CTX,status,at)
    def receipt_verify(self,r,q,role,now):
        v=f.strict(r.raw)
        f.need(v["fixture"]=="SYNTHETIC_NOT_OPERATIONAL_RECEIPT" and v["role"]==r.role and tuple(v["context"])==r.context
               and v["status"]==r.status and v["completed_at"]==f.iso(r.completed_at),"FIXTURE_RECEIPT_VIEW_DIVERGED")
    def evidence(self,op,t):
        w={"epoch":f.EPOCH,"day":f.DAY,"phase":op,"not_before":t["not_before"],"not_after":t["not_after"]}
        names=("signed_epoch_order_sha","release_sha","policy_sha","package_sha","calendar_pin_sha",
               "recertification_receipt_sha","wind_down_28_receipt_sha","template_sha","input_receipts_sha","phase_window_sha")
        b={k:f.sha(("SYNTHETIC_"+k).encode()) for k in names};b["phase_window_sha"]=f.sha(f.image_canonical(w))
        p={"identity":{"epoch":f.EPOCH,"first_session":f.DAY},"daily":{"day":f.DAY},"phase":op,"bindings":b,
           "consumer_capacity_binding":"UNBOUND","automatic_retry":False}
        proposed={"status":"BOUND_FOR_REVIEW_ONLY","execution_authorized":False,"missing_bindings":[],"proposal":p,
                  "proposal_sha":f.sha(f.image_canonical(p)),"diff":[{"fixture":"avaliação sintética"}]}
        go={"decision":"GO","epoch":f.EPOCH,"first_session":f.DAY,"day":f.DAY,"phase":op,"proposal_sha":proposed["proposal_sha"],
            "signed_order_sha":b["signed_epoch_order_sha"],"template_sha":b["template_sha"],"mode":"INDIVIDUAL",
            "not_before":t["not_before"],"not_after":t["not_after"],"automatic_retry":False,"authority_receipts":{"phase_window":w}}
        labels=["CODEX","FABLE","DUDU","ACT_B","B_CODEX","B_FABLE","B_DUDU","TEMPLATE","GO:"+op]
        if op in ("install_release","activate"):labels.append("OWNER_GO:"+op)
        docs=tuple((k,f.canonical({"fixture":"SYNTHETIC_NOT_SIGNATURE","label":k,"go_sha":f.sha(f.image_canonical(go)),
                                   "role":"DUDU" if k.startswith("OWNER_GO:") else "FABLE"})) for k in labels)
        return f.ImageGo(f.image_canonical(go),f.image_canonical(proposed),docs)
    def go_read(self,q,t,n):self.reads+=1;return self.gos[t["operation"]]
    def go_verify(self,e,b,q,t,deps,n):
        self.verifies+=1
        for label,raw in e.documents:
            v=f.strict(raw);f.need(v["fixture"]=="SYNTHETIC_NOT_SIGNATURE" and v["label"]==label
                                and v["go_sha"]==f.sha(e.go_raw),"FIXTURE_OWNER_GO_DIVERGED")
            if label.startswith("OWNER_GO:"):f.need(v["role"]=="DUDU","FIXTURE_OWNER_GO_ROLE")
        for r in deps:
            if r.role=="epoch_pre":f.need(r.status=="COMPLETE" and f.strict(r.raw)["kind"]=="K11_FULL_PRE","FIXTURE_FULL_PRE_REQUIRED")
            if r.role=="readback":f.need(r.status=="COMPLETE" and f.strict(r.raw)["kind"]=="K11_POST","FIXTURE_POST_REQUIRED")

class TestDelta(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="new-bootstrap-fixture-",dir=Path(__file__).parent)
        os.chmod(self.temp.name,0o700);p=Path(self.temp.name)/"attempts.ledger";p.write_bytes(b"");os.chmod(p,0o600)
        self.ledger=f.DurableLedger(self.temp.name,f.measure_local_ledger(self.temp.name))
    def tearDown(self):self.ledger.close();self.temp.cleanup()
    def batch(self,x=None,s=None):
        x=x or Fixture();return f.FiniteBatch(x.bundle,self.ledger,s or x.services,clock=lambda:x.now,monotonic=lambda:x.ticks),x
    def consumed(self,b,op):
        with self.assertRaisesRegex(f.Hold,"ATTEMPT_ALREADY_CONSUMED"):b.run(op)
    def fails(self,x,s,op,c):
        b,_=self.batch(x,s);r=b.run(op);self.assertEqual(r["code"],c);self.assertEqual(x.effects,[]);self.consumed(b,op)
    def test_new_sunday_owner_monday_three_ops(self):
        b,x=self.batch()
        for op in f.BOOTSTRAP:self.assertEqual(b.run(op)["status"],"ORIGINAL_COMPLETE_OBSERVED_CANDIDATE",op)
        self.assertEqual([r.operation for r in x.effects],list(f.BOOTSTRAP));self.assertEqual(x.verifies,6)
    def test_new_missing_image_verifier_consumes(self):
        x=Fixture();self.fails(x,replace(x.services,image_go_verify=None),"install_release","REAL_ADAPTER_UNAVAILABLE")
    def test_new_reader_must_return_typed_originals(self):
        x=Fixture();self.fails(x,replace(x.services,image_go_read=lambda *a:{}),"install_release","REAL_IMAGE_GO_TYPED_EVIDENCE_REQUIRED")
    def test_new_missing_m1_owner_original(self):
        x=Fixture();e=x.gos["install_release"];x.gos["install_release"]=replace(e,documents=tuple((k,v) for k,v in e.documents if not k.startswith("OWNER_GO:")))
        self.fails(x,x.services,"install_release","IMAGE_OWNER_OR_AUTHORITY_ORIGINALS_MISSING")
    def test_new_missing_m3_owner_after_dependencies(self):
        b,x=self.batch();b.run("install_release");b.run("readback");e=x.gos["activate"]
        x.gos["activate"]=replace(e,documents=tuple((k,v) for k,v in e.documents if not k.startswith("OWNER_GO:")))
        self.assertEqual(b.run("activate")["code"],"IMAGE_OWNER_OR_AUTHORITY_ORIGINALS_MISSING");self.assertEqual(len(x.effects),2)
    def test_new_m2_cannot_run_before_real_m1(self):
        x=Fixture();self.fails(x,x.services,"readback","REAL_RECEIPT_INCOMPLETE")
    def test_new_m3_cannot_run_before_real_m2(self):
        b,x=self.batch();b.run("install_release");self.assertEqual(b.run("activate")["code"],"REAL_RECEIPT_INCOMPLETE");self.assertEqual(len(x.effects),1)
    def test_new_m2_pre_cannot_masquerade_as_post_for_m3(self):
        b,x=self.batch();b.run("install_release");b.run("readback");x.receipts["readback"]=x.original("readback",kind="K11_FULL_PRE")
        self.assertEqual(b.run("activate")["code"],"FIXTURE_POST_REQUIRED");self.assertEqual(len(x.effects),2)
    def test_new_sunday_reduced_pre_is_not_full_pre(self):
        x=Fixture();x.receipts["epoch_pre"]=x.original("epoch_pre",BASE-timedelta(hours=3),kind="K11_REDUCED_PRE")
        x.q["initial_receipts"]["epoch_pre"]=f.sha(x.receipts["epoch_pre"].raw);x.rebuild()
        self.fails(x,x.services,"install_release","FIXTURE_FULL_PRE_REQUIRED")
    def test_new_initial_pre_must_exist_before_sunday_request(self):
        x=Fixture();x.receipts["epoch_pre"]=x.original("epoch_pre",BASE);x.q["initial_receipts"]["epoch_pre"]=f.sha(x.receipts["epoch_pre"].raw);x.rebuild()
        self.fails(x,x.services,"install_release","E6_RECEIPT_NOT_COMPLETE_BEFORE_REQUEST")
    def test_new_go_cannot_change_after_sunday_pin(self):
        x=Fixture();e=x.gos["install_release"];g=f.image_json(e.go_raw);g["template_sha"]=f.sha(b"CHANGED");x.gos["install_release"]=replace(e,go_raw=f.image_canonical(g))
        self.fails(x,x.services,"install_release","IMAGE_GO_OR_PROPOSAL_PIN_CHANGED")
    def test_new_bootstrap_go_cannot_be_delegated(self):
        x=Fixture();e=x.gos["install_release"];g=f.image_json(e.go_raw);g["mode"]="DELEGATED_ACT_B";e=replace(e,go_raw=f.image_canonical(g));x.gos["install_release"]=e
        x.q["tasks"][0]["image_go_sha256"]=f.sha(e.go_raw);x.rebuild();self.fails(x,x.services,"install_release","IMAGE_GO_SCOPE_INVALID")
    def test_new_owner_original_go_digest_must_match(self):
        x=Fixture();e=x.gos["install_release"];docs=[]
        for k,v in e.documents:
            row=f.strict(v)
            if k.startswith("OWNER_GO:"):row["go_sha"]=f.sha(b"OTHER_GO")
            docs.append((k,f.canonical(row)))
        x.gos["install_release"]=replace(e,documents=tuple(docs));self.fails(x,x.services,"install_release","FIXTURE_OWNER_GO_DIVERGED")
    def test_new_sunday_invocation_future_window_refuses_consumed(self):
        x=Fixture();x.now=BASE;self.fails(x,x.services,"install_release","OPERATION_WINDOW_CLOSED")
    def test_new_before_monday_nyday_refuses(self):
        x=Fixture();x.q["tasks"][0]["not_before"]="2026-10-12T03:59:59Z";x.rebuild();self.fails(x,x.services,"install_release","BOOTSTRAP_MONDAY_WINDOW_INVALID")
    def test_new_owner_deadline_after_sunday_2145_refuses(self):
        x=Fixture();x.q["owner_deadline"]="2026-10-12T00:45:01Z";x.rebuild();self.fails(x,x.services,"install_release","BOOTSTRAP_OWNER_DEADLINE_INVALID")
    def test_new_slow_last_image_verifier_exhausts_budget(self):
        x=Fixture()
        def slow(*a):
            x.go_verify(*a)
            if x.verifies==2:x.advance(61)
        self.fails(x,replace(x.services,image_go_verify=slow),"install_release","OPERATION_DEADLINE")
    def test_new_overnight_veto_does_not_survive(self):
        x=Fixture()
        def old(q,t,n):return f.VetoView(b"SYNTHETIC_OLD_VETO",q["veto_authority_sha256"],"ALLOW",BASE,MON+timedelta(hours=1))
        self.fails(x,replace(x.services,veto_read=old),"install_release","REAL_VETO_NOT_FRESH_ALLOW")
    def test_new_owner_change_during_other_callbacks_refuses(self):
        x=Fixture()
        def ident(*a):
            if x.verifies==1:
                e=x.gos["install_release"];x.gos["install_release"]=replace(e,documents=tuple((k,v) for k,v in e.documents if not k.startswith("OWNER_GO:")))
        self.fails(x,replace(x.services,identity=ident),"install_release","IMAGE_OWNER_OR_AUTHORITY_ORIGINALS_MISSING")
    def test_new_uncertain_executor_consumed_once(self):
        x=Fixture()
        def execute(i):x.effects.append(i);raise OSError("SYNTHETIC_UNCERTAIN")
        b,_=self.batch(x,replace(x.services,execute=execute));r=b.run("install_release");self.assertEqual(r["status"],"UNCERTAIN_CONSUMED");self.assertEqual(len(x.effects),1);self.consumed(b,"install_release")

if __name__=="__main__":unittest.main(verbosity=2)
