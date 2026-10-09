"""Reused fixture utility only; no R1 tests copied or executed."""
from datetime import datetime,timedelta,timezone
import finite_batch as f
BASE=datetime(2026,10,11,19,0,tzinfo=timezone.utc)
CTX=(f.EPOCH,f.DAY,f.PREVIOUS,"BOOTSTRAP")
class Fixture:
    def __init__(self, lane="DOWNSTREAM_AFTER_E6"):
        self.now, self.ticks, self.effects = BASE, 100.0, []
        self.receipts = {}
        self.capacity_phases = []
        self.identity_calls = 0
        authority = f.canonical({"fixture": "SYNTHETIC_NOT_AUTHORITY", "lane": lane,
                                 "delegated_named_selectors": True})
        runtime = f.canonical({"fixture": "SYNTHETIC_NOT_RUNTIME"})
        initial = {}
        if lane == "DOWNSTREAM_AFTER_E6":
            for role in ("commit_result", "publish_launch"):
                receipt = self.original(role, BASE - timedelta(hours=3))
                self.receipts[role] = receipt
                initial[role] = f.sha(receipt.raw)
        operations = f.LANES[lane]
        self.q = {"schema": "L12_FINITE_BATCH_REQUEST_CANDIDATE_V1", "lane": lane,
                  "epoch": f.EPOCH, "session": f.DAY, "previous_session": f.PREVIOUS, "track": "P",
                  "prepared_at": f.iso(BASE - timedelta(hours=2)),
                  "owner_deadline": f.iso(BASE - timedelta(hours=1)),
                  "authority_sha256": f.sha(authority), "runtime_sha256": f.sha(runtime),
                  "veto_authority_sha256": f.sha(b"SYNTHETIC_VETO_AUTHORITY"), "initial_receipts": initial,
                  "tasks": [{"operation": op, "not_before": f.iso(BASE),
                             "not_after": f.iso(BASE + timedelta(hours=1)), "budget_seconds": 60,
                             "requires": list(f.MINIMUM_DEPENDENCIES[op])} for op in operations]}
        self.rebuild(authority, runtime)
        self.services = f.Services(authority=self.authority, identity=self.identity,
                                   veto_read=self.veto, veto_verify=self.veto_verify,
                                   receipt_read=self.read_receipt, receipt_verify=self.receipt_verify,
                                   operation_gate=self.gate, capacity_path=self.capacity, execute=self.execute)

    def rebuild(self, authority=None, runtime=None):
        if authority is None:
            docs = dict(self.bundle.documents)
            authority, runtime = docs["authority"], docs["runtime"]
        request = f.canonical(self.q)
        owner = f.canonical({"schema": "L12_OWNER_RECORD_CANDIDATE_V1", "answer": "Assino",
                             "channel": "REGISTRO_PELA_FABLE", "request_sha256": f.sha(request),
                             "question_sha256": f.sha(b"SYNTHETIC_QUESTION_NOT_OWNER_ACT"),
                             "question_published_at": f.iso(BASE - timedelta(minutes=119)),
                             "signed_at": f.iso(BASE - timedelta(minutes=118))})
        docs = (("authority", authority), ("owner", owner), ("runtime", runtime))
        bound = f.canonical({"schema": "L12_BOUND_CANDIDATE_V1", "request_sha256": f.sha(request),
                             "documents_sha256": {k: f.sha(v) for k, v in docs},
                             "bound_at": f.iso(BASE - timedelta(minutes=117))})
        self.bundle = f.Bundle(request, bound, docs)

    def original(self, role, at=None, status="COMPLETE"):
        at = at or self.now
        raw = f.canonical({"fixture": "SYNTHETIC_NOT_OPERATIONAL_RECEIPT", "role": role,
                           "context": list(CTX), "status": status, "completed_at": f.iso(at)})
        return f.Receipt(raw, role, CTX, status, at)

    def advance(self, seconds):
        self.now += timedelta(seconds=seconds)
        self.ticks += seconds

    def authority(self, bundle, q, task, now):
        # Only the explicitly labeled fixture ABI is accepted by this mock.
        f.need(f.strict(dict(bundle.documents)["authority"]).get("fixture") == "SYNTHETIC_NOT_AUTHORITY",
               "FIXTURE_AUTHORITY_INVALID")

    def identity(self, bundle, q, task, now):
        self.identity_calls += 1

    def veto(self, q, task, now):
        return f.VetoView(b"SYNTHETIC_CURRENT_VETO", q["veto_authority_sha256"], "ALLOW", now,
                          now + timedelta(seconds=5))

    def veto_verify(self, veto, q, task, now):
        f.need(veto.raw == b"SYNTHETIC_CURRENT_VETO", "FIXTURE_VETO_INVALID")

    def read_receipt(self, role, context):
        return self.receipts.get(role)

    def receipt_verify(self, receipt, q, role, now):
        view = f.strict(receipt.raw)
        f.need(view == {"fixture": "SYNTHETIC_NOT_OPERATIONAL_RECEIPT", "role": receipt.role,
                        "context": list(receipt.context), "status": receipt.status,
                        "completed_at": f.iso(receipt.completed_at)}, "FIXTURE_RECEIPT_VIEW_DIVERGED")

    def gate(self, bundle, q, task, dependencies, now):
        pass

    def capacity(self, q, phase, now):
        self.capacity_phases.append(phase)

    def execute(self, invocation):
        self.effects.append(invocation)
        self.advance(1)
        result = self.original(invocation.operation)
        self.receipts[invocation.operation] = result
        return result
