"""NEW SYNTHETIC FIXTURES ONLY: no existing F2 suite, producer, host or signatures."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
import tempfile
import unittest

import finite_batch as f


BASE = datetime(2026, 10, 11, 19, 0, tzinfo=timezone.utc)
CTX = (f.EPOCH, f.DAY, f.PREVIOUS, "P")


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


class TestFiniteBatchCandidate(unittest.TestCase):
    def setUp(self):
        # A new local fixture under this candidate; no campaign/host roots.
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-ledger-", dir=Path(__file__).parent)
        self.root = self.temp.name
        os.chmod(self.root, 0o700)
        path = Path(self.root) / "attempts.ledger"
        path.write_bytes(b"")
        os.chmod(path, 0o600)
        self.pins = f.measure_local_ledger(self.root)
        self.ledger = f.DurableLedger(self.root, self.pins)

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def batch(self, fixture=None, services=None):
        fixture = fixture or Fixture()
        return f.FiniteBatch(fixture.bundle, self.ledger, services or fixture.services,
                             clock=lambda: fixture.now, monotonic=lambda: fixture.ticks), fixture

    def expect_consumed(self, batch, operation):
        with self.assertRaisesRegex(f.Hold, "ATTEMPT_ALREADY_CONSUMED"):
            batch.run(operation)

    def test_new_upstream_four_real_original_callbacks(self):
        b, x = self.batch(Fixture("UPSTREAM_P"))
        for op in f.UPSTREAM:
            self.assertEqual(b.run(op)["status"], "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE")
        self.assertEqual(len(x.effects), 4)
        self.assertEqual(x.capacity_phases, [])
        self.assertEqual(b.run.__self__.q["lane"], "UPSTREAM_P")

    def test_new_downstream_chain_with_pre_and_post_first_reader(self):
        b, x = self.batch()
        for op in f.DOWNSTREAM:
            self.assertEqual(b.run(op)["status"], "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE", op)
        self.assertEqual(x.capacity_phases, ["BEFORE_FIRST_READER", "AFTER_FIRST_CYCLE"])
        self.assertGreaterEqual(x.identity_calls, 3 * len(f.DOWNSTREAM))
        self.expect_consumed(b, "e6")

    def test_new_missing_executor_refusal_still_consumes(self):
        x = Fixture()
        b, _ = self.batch(x, replace(x.services, execute=None))
        result = b.run("e6")
        self.assertEqual((result["status"], result["code"], result["effect_calls"]),
                         ("REFUSED_CONSUMED", "REAL_EXECUTOR_UNAVAILABLE", 0))
        self.expect_consumed(b, "e6")

    def test_new_authority_boolean_is_not_attestation(self):
        x = Fixture()
        b, _ = self.batch(x, replace(x.services, authority=lambda *args: True))
        result = b.run("e6")
        self.assertEqual(result["code"], "ADAPTER_DID_NOT_ATTEST")
        self.assertEqual(x.effects, [])
        self.expect_consumed(b, "e6")

    def test_new_late_window_refusal_consumes(self):
        x = Fixture()
        x.advance(3601)
        b, _ = self.batch(x)
        self.assertEqual(b.run("e6")["code"], "OPERATION_DEADLINE")
        self.assertEqual(x.effects, [])
        self.expect_consumed(b, "e6")

    def test_new_future_initial_receipt_rejected_before_owner(self):
        x = Fixture()
        x.receipts["commit_result"] = x.original("commit_result", BASE - timedelta(minutes=30))
        x.q["initial_receipts"]["commit_result"] = f.sha(x.receipts["commit_result"].raw)
        x.rebuild()
        b, _ = self.batch(x)
        self.assertEqual(b.run("e6")["code"], "E6_RECEIPT_NOT_COMPLETE_BEFORE_REQUEST")
        self.assertEqual(x.effects, [])

    def test_new_pending_publish_is_not_complete(self):
        x = Fixture()
        x.receipts["publish_launch"] = x.original("publish_launch", status="PENDING")
        b, _ = self.batch(x)
        self.assertEqual(b.run("e6")["code"], "REAL_RECEIPT_INCOMPLETE")
        self.assertEqual(x.effects, [])

    def test_new_receipt_normalization_cannot_lie(self):
        x = Fixture()
        x.receipts["publish_launch"] = replace(x.receipts["publish_launch"], completed_at=BASE)
        b, _ = self.batch(x)
        self.assertEqual(b.run("e6")["code"], "FIXTURE_RECEIPT_VIEW_DIVERGED")

    def test_new_cross_context_receipt_refuses(self):
        x = Fixture()
        x.receipts["publish_launch"] = replace(x.receipts["publish_launch"], context=(f.EPOCH, f.DAY, f.PREVIOUS, "S"))
        b, _ = self.batch(x)
        self.assertEqual(b.run("e6")["code"], "REAL_RECEIPT_INCOMPLETE")

    def test_new_stale_veto_refuses_without_effect(self):
        x = Fixture()
        def veto(q, task, now):
            return replace(x.veto(q, task, now), observed_at=now - timedelta(seconds=6))
        b, _ = self.batch(x, replace(x.services, veto_read=veto))
        self.assertEqual(b.run("e6")["code"], "REAL_VETO_NOT_FRESH_ALLOW")
        self.assertEqual(x.effects, [])

    def test_new_veto_expiring_during_last_identity_refuses(self):
        x = Fixture()
        def identity(*args):
            x.identity(*args)
            if x.identity_calls == 3:
                x.advance(6)
        b, _ = self.batch(x, replace(x.services, identity=identity))
        self.assertEqual(b.run("e6")["code"], "REAL_VETO_NOT_FRESH_ALLOW")
        self.assertEqual(x.effects, [])

    def test_new_clock_rollback_refuses(self):
        x = Fixture()
        def identity(*args):
            x.now -= timedelta(seconds=3)
        b, _ = self.batch(x, replace(x.services, identity=identity))
        self.assertEqual(b.run("e6")["code"], "CLOCK_DISCONTINUITY")
        self.assertEqual(x.effects, [])

    def test_new_bound_mutated_by_callback_refuses(self):
        x = Fixture()
        def authority(bundle, *args):
            object.__setattr__(bundle, "bound", bundle.bound + b" ")
        b, _ = self.batch(x, replace(x.services, authority=authority))
        self.assertEqual(b.run("e6")["code"], "BOUND_BYTES_CHANGED")
        self.assertEqual(x.effects, [])

    def test_new_executor_throw_consumed_uncertain_no_retry(self):
        x = Fixture()
        def execute(invocation):
            x.effects.append(invocation)
            raise RuntimeError("SYNTHETIC_PARTIAL_EFFECT")
        b, _ = self.batch(x, replace(x.services, execute=execute))
        result = b.run("e6")
        self.assertEqual((result["status"], result["effect_calls"]), ("UNCERTAIN_CONSUMED", 1))
        self.expect_consumed(b, "e6")
        self.assertEqual(len(x.effects), 1)

    def test_new_executor_deadline_violation_never_complete(self):
        x = Fixture()
        def execute(invocation):
            x.advance(61)
            return x.original(invocation.operation)
        b, _ = self.batch(x, replace(x.services, execute=execute))
        result = b.run("e6")
        self.assertEqual((result["status"], result["code"]), ("UNCERTAIN_CONSUMED", "EFFECT_RETURNED_AFTER_DEADLINE"))
        self.expect_consumed(b, "e6")

    def test_new_final_identity_exhausts_budget_before_executor(self):
        x = Fixture()
        x.q["tasks"][0]["budget_seconds"] = 2
        x.rebuild()
        def identity(*args):
            x.identity(*args)
            if x.identity_calls == 3:
                x.advance(3)  # Veto remains <=5s, operation budget is already gone.
        b, _ = self.batch(x, replace(x.services, identity=identity))
        result = b.run("e6")
        self.assertEqual((result["code"], result["effect_calls"]), ("OPERATION_DEADLINE", 0))
        self.assertEqual(x.effects, [])
        self.expect_consumed(b, "e6")

    def test_new_final_authority_exhausts_budget_before_executor(self):
        x = Fixture()
        x.q["tasks"][0]["budget_seconds"] = 2
        x.rebuild()
        calls = []
        def authority(*args):
            calls.append(1)
            x.authority(*args)
            if len(calls) == 3:
                x.advance(3)
        b, _ = self.batch(x, replace(x.services, authority=authority))
        result = b.run("e6")
        self.assertEqual((result["code"], result["effect_calls"]), ("OPERATION_DEADLINE", 0))
        self.assertEqual(x.effects, [])
        self.expect_consumed(b, "e6")

    def test_new_plan_changed_does_not_reopen_logical_operation(self):
        b, x = self.batch()
        self.assertEqual(b.run("e6")["effect_calls"], 1)
        x.q["tasks"][0]["budget_seconds"] = 59
        x.rebuild()
        other, _ = self.batch(x)
        self.expect_consumed(other, "e6")
        self.assertEqual(len(x.effects), 1)

    def test_new_reopen_persisted_ledger_preserves_consume(self):
        b, x = self.batch()
        b.run("e6")
        self.ledger.close()
        self.ledger = f.DurableLedger(self.root, self.pins)
        other, _ = self.batch(x)
        self.expect_consumed(other, "e6")

    def test_new_ledger_rollback_orphan_marker_holds_all(self):
        b, x = self.batch()
        b.run("e6")
        (Path(self.root) / "attempts.ledger").write_bytes(b"")
        with self.assertRaisesRegex(f.Hold, "LEDGER_MARKER_MISMATCH"):
            b.run("admission_manifest")
        self.assertEqual(len(x.effects), 1)

    def test_new_partial_ledger_tail_is_not_recoverable_by_retry(self):
        b, x = self.batch()
        with open(Path(self.root) / "attempts.ledger", "ab") as stream:
            stream.write(b'{"partial":')
        with self.assertRaisesRegex(f.Hold, "LEDGER_PARTIAL_OR_FULL"):
            b.run("e6")
        self.assertEqual(x.effects, [])

    def test_new_ledger_replacement_refuses(self):
        b, x = self.batch()
        path = Path(self.root) / "attempts.ledger"
        path.rename(Path(self.root) / "old-ledger")
        path.write_bytes(b"")
        os.chmod(path, 0o600)
        with self.assertRaisesRegex(f.Hold, "LEDGER_FILE_CHANGED"):
            b.run("e6")
        self.assertEqual(x.effects, [])

    def test_new_mixed_generic_lane_not_accepted(self):
        x = Fixture("UPSTREAM_P")
        x.q["tasks"].append(Fixture().q["tasks"][0])
        x.rebuild()
        b, _ = self.batch(x)
        self.assertEqual(b.run("prove")["code"], "TASK_OPERATION_INVALID")
        self.assertEqual(x.effects, [])
        self.expect_consumed(b, "prove")

    def test_new_future_dependency_selector_before_predecessor_not_accepted(self):
        x = Fixture("UPSTREAM_P")
        x.q["tasks"][0]["requires"] = ["publish_launch"]
        x.rebuild()
        b, _ = self.batch(x)
        self.assertEqual(b.run("prove")["code"], "TASK_DEPENDENCIES_INVALID")
        self.assertEqual(x.effects, [])
        self.expect_consumed(b, "prove")

    def test_new_placeholder_authority_pin_rejected(self):
        x = Fixture()
        x.q["authority_sha256"] = "0f" + "0" * 62
        x.rebuild()
        b, _ = self.batch(x)
        self.assertEqual(b.run("e6")["code"], "PLAN_PIN_INVALID")
        self.assertEqual(x.effects, [])
        self.expect_consumed(b, "e6")

    def test_new_invalid_declared_time_consumes_identifiable_operation(self):
        x = Fixture()
        x.q["tasks"][0]["not_after"] = "SYNTHETIC_INVALID_TIMESTAMP"
        x.rebuild()
        b, _ = self.batch(x)
        self.assertEqual(b.run("e6")["code"], "CLOCK_UNBOUND")
        self.assertEqual(x.effects, [])
        self.expect_consumed(b, "e6")

    def test_new_torn_claim_marker_is_uncertain_and_never_reset(self):
        b, x = self.batch()
        original_append = self.ledger._append
        self.ledger._append = lambda *args: (_ for _ in ()).throw(f.Hold("SYNTHETIC_CLAIM_WRITE_UNCERTAIN"))
        with self.assertRaisesRegex(f.Hold, "SYNTHETIC_CLAIM_WRITE_UNCERTAIN"):
            b.run("e6")
        self.ledger._append = original_append
        with self.assertRaisesRegex(f.Hold, "ATTEMPT_ALREADY_CONSUMED"):
            b.run("e6")
        self.assertEqual(x.effects, [])

    def test_new_clock_unavailable_after_identification_still_consumes(self):
        b, x = self.batch()
        b.clock = lambda: None
        result = b.run("e6")
        self.assertEqual((result["status"], result["code"], result["effect_calls"]),
                         ("REFUSED_CONSUMED", "CLOCK_UNBOUND", 0))
        self.assertIsNone(result["completed_at"])
        self.expect_consumed(b, "e6")

    def test_new_busy_ledger_refusal_retains_the_consumed_marker(self):
        b, x = self.batch()
        other = os.open(Path(self.root) / "attempts.ledger", os.O_RDWR)
        try:
            f.fcntl.flock(other, f.fcntl.LOCK_EX | f.fcntl.LOCK_NB)
            with self.assertRaisesRegex(f.Hold, "LEDGER_BUSY_CONSUMED"):
                b.run("e6")
            f.fcntl.flock(other, f.fcntl.LOCK_UN)
            self.expect_consumed(b, "e6")
            self.assertEqual(x.effects, [])
        finally:
            os.close(other)

    def test_new_missing_first_cycle_binding_is_uncertain_after_effect(self):
        b, x = self.batch()
        for op in ("e6", "admission_manifest", "post", "reader_bound"):
            b.run(op)
        def capacity(q, phase, now):
            if phase == "AFTER_FIRST_CYCLE":
                raise f.Hold("DB_SESSION_BINDING_MISSING_OR_CHANGED")
        b.services = replace(x.services, capacity_path=capacity)
        result = b.run("reader_cycle")
        self.assertEqual((result["status"], result["effect_calls"], result["code"]),
                         ("UNCERTAIN_CONSUMED", 1, "DB_SESSION_BINDING_MISSING_OR_CHANGED"))
        self.expect_consumed(b, "reader_cycle")

    def test_new_reader_gate_runs_after_last_identity_changes_world(self):
        b, x = self.batch()
        for op in ("e6", "admission_manifest", "post", "reader_bound"):
            b.run(op)
        x.identity_calls = 0
        current = {"ready": True}
        def identity(*args):
            x.identity(*args)
            if x.identity_calls == 3:
                current["ready"] = False
        def capacity(q, phase, now):
            f.need(current["ready"], "READY_CHANGED_BEFORE_READER")
        b.services = replace(x.services, identity=identity, capacity_path=capacity)
        result = b.run("reader_cycle")
        self.assertEqual((result["code"], result["effect_calls"]), ("READY_CHANGED_BEFORE_READER", 0))
        self.expect_consumed(b, "reader_cycle")

    def test_new_slow_final_capacity_gate_cannot_start_reader_outside_budget(self):
        b, x = self.batch()
        for op in ("e6", "admission_manifest", "post", "reader_bound"):
            b.run(op)
        x.q["tasks"][4]["budget_seconds"] = 2
        x.rebuild()
        b, _ = self.batch(x)
        b.services = replace(x.services, capacity_path=lambda *args: x.advance(3))
        result = b.run("reader_cycle")
        self.assertEqual((result["code"], result["effect_calls"]), ("OPERATION_DEADLINE", 0))
        self.expect_consumed(b, "reader_cycle")

    def test_new_slow_post_cycle_gate_never_marks_complete_after_deadline(self):
        b, x = self.batch()
        for op in ("e6", "admission_manifest", "post", "reader_bound"):
            b.run(op)
        def capacity(q, phase, now):
            if phase == "AFTER_FIRST_CYCLE":
                x.advance(61)
        b.services = replace(x.services, capacity_path=capacity)
        result = b.run("reader_cycle")
        self.assertEqual((result["status"], result["code"], result["effect_calls"]),
                         ("UNCERTAIN_CONSUMED", "OPERATION_DEADLINE", 1))
        self.expect_consumed(b, "reader_cycle")


if __name__ == "__main__":
    unittest.main()
