"""Only new r2 delta proofs. The sealed r1 suite is not imported or repeated."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import unittest

import image_path_adapter as a

ROOT = Path(__file__).resolve().parent
BASE = ROOT  # R3 packaging only: all exact public sources travel inside this archive.
NOW = datetime(2026, 10, 12, 11, 30, tzinfo=timezone.utc)
OPEN = NOW + timedelta(hours=2)


def scope():
    return a.Scope("1" * 40, "sha256:" + "2" * 64, "3" * 64, "4" * 64, "5" * 64,
                   "6" * 64, "7" * 64, "8" * 64, "9" * 64, os.geteuid(),
                   "/fixture-private-manifests", OPEN, NOW - timedelta(seconds=1),
                   NOW + timedelta(seconds=4), NOW, "DELEGATED_ACT_B")


def receipt(s):
    return {"schema": "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1", "status": "PUBLISHED_VERIFIED",
            "code": None, "mode": "PUBLISH", "epoch": s.epoch, "session": s.day,
            "owner_uid": s.owner_uid, "build_sha": s.build_sha, "release_sha256": s.release_sha256,
            "package_sha256": s.package_sha256, "capacity_config_sha256": s.capacity_config_sha256,
            "capacity_veto_mode": "DISPATCH_AND_DERIVATION_ONLY", "massive_bars_enabled": True,
            "cutoff_at": (OPEN - timedelta(minutes=10)).isoformat(), "go_mode": s.require_go_mode,
            "go_sha256": "a" * 64, "template_sha256": "b" * 64, "binding_sha256": "c" * 64,
            "manifest_sha256": "d" * 64, "symbol_count": 1,
            "view": {"observed_at": NOW.isoformat(), "valid_until": s.not_after.isoformat()}}


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.s = scope()
        self.source = (BASE / "sources" / "manifest_writer.py").read_bytes()
        self.plan = a.invocation(self.s, self.source, now=NOW)
        self.now = NOW
        self.events = []

    def reserve(self, key, sha):
        self.events.append(("CLAIM", key, sha))

    def exercise(self, gate, execute=None, plan=None):
        def transport(*_):
            self.events.append(("EFFECT",))
            return 0, a.canonical(receipt(self.s))
        return a.invoke_once(plan or self.plan, clock=lambda: self.now, reserve=self.reserve,
                             immediate_gate=gate, execute=execute or transport)

    def assertHold(self, expected, callback):
        with self.assertRaises(a.Hold) as error:
            callback()
        self.assertEqual(error.exception.args, (expected,))

    def test_late_before_writer_verifier_never_calls_transport(self):
        def gate(s, phase, now):
            if phase == "BEFORE_WRITER":
                self.now = s.not_after
        self.assertHold("MANIFEST_WINDOW_CLOSED", lambda: self.exercise(gate))
        self.assertEqual([e[0] for e in self.events], ["CLAIM"])

    def test_late_after_claim_verifier_never_calls_transport(self):
        def gate(s, phase, now):
            if phase == "AFTER_CLAIM":
                self.now = s.not_after + timedelta(seconds=1)
        self.assertHold("MANIFEST_WINDOW_CLOSED", lambda: self.exercise(gate))
        self.assertEqual([e[0] for e in self.events], ["CLAIM"])

    def test_refused_authority_is_already_consumed(self):
        def gate(s, phase, now):
            raise a.Hold("FIXTURE_AUTHORITY_REFUSED")
        self.assertHold("FIXTURE_AUTHORITY_REFUSED", lambda: self.exercise(gate))
        self.assertEqual([e[0] for e in self.events], ["CLAIM"])

    def test_identifiable_wrong_date_and_changed_argv_are_consumed(self):
        self.now = NOW - timedelta(days=1)
        self.assertHold("MANIFEST_DAY_NOT_TODAY", lambda: self.exercise(lambda *_: None))
        self.assertEqual([e[0] for e in self.events], ["CLAIM"])
        self.now = NOW
        self.events.clear()
        changed = replace(self.plan, argv=self.plan.argv + ("--preflight",))
        self.assertHold("MANIFEST_INVOCATION_CHANGED", lambda: self.exercise(lambda *_: None, plan=changed))
        self.assertEqual([e[0] for e in self.events], ["CLAIM"])

    def test_missing_executor_consumes_identifiable_operation(self):
        self.assertHold("EXECUTOR_UNBOUND", lambda: a.invoke_once(self.plan, clock=lambda: self.now,
                           reserve=self.reserve, immediate_gate=lambda *_: None, execute=None))
        self.assertEqual([e[0] for e in self.events], ["CLAIM"])

    def test_bad_supplied_time_is_consumed_before_time_parsing(self):
        for value in ("not-a-time", NOW.replace(tzinfo=None)):
            self.events.clear()
            changed = replace(self.plan, scope=replace(self.s, not_before=value))
            self.assertHold("CLOCK_UNBOUND", lambda: self.exercise(lambda *_: None, plan=changed))
            self.assertEqual([e[0] for e in self.events], ["CLAIM"])

    def test_transport_return_after_deadline_is_uncertain_not_complete(self):
        def transport(*_):
            self.events.append(("EFFECT",))
            self.now = self.s.not_after
            return 0, a.canonical(receipt(self.s))
        self.assertHold("MANIFEST_RESULT_AFTER_WINDOW", lambda: self.exercise(lambda *_: None, transport))
        self.assertEqual([e[0] for e in self.events], ["CLAIM", "EFFECT"])

    def test_slow_readback_callback_cannot_return_success_after_window(self):
        def gate(s, phase, now):
            if phase == "BEFORE_READBACK":
                self.now = s.not_after
        self.assertHold("MANIFEST_RESULT_AFTER_WINDOW", lambda: self.exercise(gate))
        self.assertEqual([e[0] for e in self.events], ["CLAIM", "EFFECT"])

    def test_valid_delta_protocol_orders_claim_before_gates(self):
        def gate(s, phase, now):
            self.events.append((phase,))
        observed = self.exercise(gate)
        self.assertEqual(observed["status"], "PUBLISHED_VERIFIED")
        self.assertEqual([e[0] for e in self.events],
                         ["CLAIM", "AFTER_CLAIM", "BEFORE_WRITER", "EFFECT", "BEFORE_READBACK"])
        self.assertEqual(self.events[0][1], a.ATTEMPT_KEY)

    def test_journal_snapshot_can_exceed_manifest_limit_with_explicit_db_limit(self):
        raw = a.canonical([{"synthetic_record": "x" * 70000}])
        self.assertGreater(len(raw), a.LIMIT)
        self.assertHold("JSON_BYTES_INVALID", lambda: a.strict_json(raw))
        parsed = a.strict_json(raw, limit=a.DB_READBACK_LIMIT)
        self.assertEqual(len(parsed), 1)

    def test_explicit_db_limit_is_bounded_and_keeps_strict_json(self):
        for limit in (True, 0, a.DB_READBACK_LIMIT + 1):
            self.assertHold("JSON_LIMIT_INVALID", lambda: a.strict_json(b'{}', limit=limit))
        self.assertHold("JSON_DUPLICATE_KEY", lambda: a.strict_json(
            b'{"journal":1,"journal":2}', limit=a.DB_READBACK_LIMIT))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DeltaTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raw = (ROOT / "image_path_adapter.py").read_bytes()
    record = {"schema": "CODEX_NEW_DELTA_RESULT_V1", "methods": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "scope": "R2_DELTA_ONLY_SYNTHETIC", "r1_tests_repeated": 0,
              "app_imports": 0, "db_queries": 0, "real_transport_runs": 0, "host_operations": 0,
              "source_sha256": hashlib.sha256(raw).hexdigest()}
    (ROOT / "DELTA_RESULT.json").write_bytes(a.canonical(record) + b"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
