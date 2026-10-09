"""New isolated synthetic tests; no app imports, producer, DB, host or transport."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import image_path_adapter as a

ROOT = Path(__file__).resolve().parent
OPEN = datetime(2026, 10, 12, 13, 30, tzinfo=timezone.utc)
NOW = OPEN - timedelta(hours=2)


def scope():
    return a.Scope(build_sha="1" * 40, image_id="sha256:" + "2" * 64,
                   document_order_sha256="3" * 64, release_sha256="4" * 64,
                   package_sha256="5" * 64, capacity_config_sha256="6" * 64,
                   calendar_pin_sha256="7" * 64, runtime_authority_sha256="8" * 64,
                   finite_authority_sha256="9" * 64, owner_uid=os.geteuid(),
                   manifest_directory="/fixture-private-manifests", session_open=OPEN,
                   not_before=NOW - timedelta(seconds=1), not_after=NOW + timedelta(seconds=8),
                   view_opens_at=NOW, require_go_mode="DELEGATED_ACT_B")


def evidence(raw):
    return a.FileEvidence(raw, 1, 2, os.geteuid(), os.getegid(), 0o600, 1)


def fixture():
    s = scope()
    # Deliberately incomplete synthetic contract. It is only an adapter byte
    # fixture and is never sent through image authority/derive/prepare.
    doc = {"schema": "V2_DAILY_CAPACITY_BINDING_CANDIDATE_V1", "epoch": s.epoch,
           "day": s.day, "release_sha": s.release_sha256,
           "monitored_symbols": ["FIXA", "FIXB"], "contract": {"synthetic": True}}
    binding = {"sha": a.digest(doc), "document": doc}
    state = {"epoch": s.epoch, "release_sha": s.release_sha256,
             "daily_capacity": {s.day: binding}, "sessions": {}}
    payload = {"journal_key": "capacity-prepared:" + s.day, "type": "CAPACITY_DAY_PREPARED",
               "session": s.day, "plan_sha": binding["sha"], "payload": doc}
    record = {"epoch": s.epoch, "sequence": 1, "journal_key": payload["journal_key"],
              "recorded_at": NOW.isoformat(), "payload": payload, "previous_sha": ""}
    record["record_sha"] = a.digest(record)
    row = {"state": state, "state_sha": a.digest(state), "journal_head": record["record_sha"]}
    manifest = evidence(a.canonical({"epoch": s.epoch, "session": s.day,
                                     "symbols": doc["monitored_symbols"], "owner_uid": s.owner_uid}))
    receipt = {"schema": "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1", "status": "PUBLISHED_VERIFIED",
               "code": None, "mode": "PUBLISH", "epoch": s.epoch, "session": s.day,
               "owner_uid": s.owner_uid, "build_sha": s.build_sha,
               "release_sha256": s.release_sha256, "package_sha256": s.package_sha256,
               "capacity_config_sha256": s.capacity_config_sha256,
               "capacity_veto_mode": "DISPATCH_AND_DERIVATION_ONLY", "massive_bars_enabled": True,
               "cutoff_at": (OPEN - timedelta(minutes=10)).isoformat(),
               "go_mode": s.require_go_mode, "go_sha256": "a" * 64, "template_sha256": "b" * 64,
               "binding_sha256": binding["sha"], "manifest_sha256": a.sha(manifest.raw), "symbol_count": 2,
               "file": {"uid": manifest.uid, "gid": manifest.gid, "mode": "0600", "nlink": 1,
                        "device": manifest.device, "inode": manifest.inode, "size_within_limit": True},
               "view": {"observed_at": NOW.isoformat(), "valid_until": (NOW + timedelta(seconds=5)).isoformat()}}
    root = a.DirectoryPin(1, 44, s.owner_uid)
    ready = evidence(a.canonical({"epoch": s.epoch, "session": s.day}))
    session = evidence(a.canonical({"schema": "MASSIVE_SESSION_V1", "epoch": s.epoch,
                                    "session": s.day, "symbols": doc["monitored_symbols"],
                                    "device": root.device, "inode": root.inode}))
    return s, receipt, row, [record], manifest, ready, session, root


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.s = scope()
        self.source = (ROOT / "sources" / "manifest_writer.py").read_bytes()

    def assertHold(self, code, callback):
        with self.assertRaises(a.Hold) as error:
            callback()
        self.assertEqual(error.exception.args, (code,))

    def test_exact_existing_source_and_prepare_first_invocation(self):
        plan = a.invocation(self.s, self.source, now=NOW)
        self.assertIn("--prepare-first", plan.argv)
        self.assertNotIn("--prepare-capacity-day", plan.argv)
        self.assertNotIn("--verify-only", plan.argv)
        self.assertEqual(a.sha(plan.stdin), a.WRITER_SHA)

    def test_sunday_rejected_before_claim_or_transport(self):
        sunday = NOW - timedelta(days=1)
        self.assertHold("MANIFEST_DAY_NOT_TODAY", lambda: a.invocation(self.s, self.source, now=sunday))

    def test_window_and_cutoff_boundaries(self):
        for clock in (self.s.not_before - timedelta(microseconds=1), self.s.not_after,
                      OPEN - timedelta(minutes=10), OPEN):
            with self.subTest(clock=clock):
                self.assertHold("MANIFEST_WINDOW_CLOSED", lambda: a.invocation(self.s, self.source, now=clock))
        self.assertHold("VETO_VIEW_NOT_YET", lambda: a.invocation(self.s, self.source,
                                                                 now=NOW - timedelta(microseconds=1)))

    def test_source_and_final_order_pins_refuse_placeholders(self):
        self.assertHold("MANIFEST_WRITER_PIN", lambda: a.invocation(self.s, self.source + b"\n", now=NOW))
        for value in (a.PLACEHOLDER, "0" * 64, "3" * 63):
            with self.subTest(value=value):
                self.assertHold("IMAGE_INPUT_PIN", lambda: replace(self.s, document_order_sha256=value).validate())

    def test_wrong_epoch_day_and_unbounded_window(self):
        for s in (replace(self.s, day="2026-10-13"), replace(self.s, epoch="R2D2-V2-SHADOW-2026-10-05")):
            self.assertHold("IMAGE_SCOPE_MISMATCH", s.validate)
        self.assertHold("MANIFEST_EFFECT_WINDOW", lambda: replace(self.s, not_after=OPEN).validate())

    def test_no_effect_without_all_executor_hooks(self):
        plan = a.invocation(self.s, self.source, now=NOW)
        self.assertHold("EXECUTOR_UNBOUND", lambda: a.invoke_once(plan, clock=lambda: NOW,
                                                               immediate_gate=None, reserve=lambda *_: None,
                                                               execute=lambda *_: self.fail("effect")))

    def test_claim_precedes_single_transport_and_uncertainty_is_spent(self):
        plan = a.invocation(self.s, self.source, now=NOW)
        events = []
        def gate(s, phase, clock):
            events.append(phase)
        def reserve(key, scope_sha):
            events.append("CLAIM")
            self.assertEqual(key, a.ATTEMPT_KEY)
            self.assertEqual(scope_sha, self.s.scope_sha256)
        def run(*args):
            events.append("TRANSPORT")
            raise RuntimeError("fixture secret must never appear")
        self.assertHold("MANIFEST_TRANSPORT_UNCERTAIN", lambda: a.invoke_once(plan, clock=lambda: NOW,
                                          immediate_gate=gate, reserve=reserve, execute=run))
        self.assertEqual(events, ["BEFORE_CLAIM", "CLAIM", "BEFORE_WRITER", "TRANSPORT"])

    def test_gate_failure_after_claim_never_calls_transport(self):
        plan = a.invocation(self.s, self.source, now=NOW)
        events = []
        def gate(s, phase, clock):
            if phase == "BEFORE_WRITER":
                raise a.Hold("FIXTURE_AUTHORITY_REVOKED")
        self.assertHold("FIXTURE_AUTHORITY_REVOKED", lambda: a.invoke_once(plan, clock=lambda: NOW,
                                   immediate_gate=gate, reserve=lambda key, scope_sha: events.append(key),
                                   execute=lambda *_: self.fail("transport")))
        self.assertEqual(len(events), 1)

    def test_mutated_argv_never_reserves(self):
        plan = a.invocation(self.s, self.source, now=NOW)
        changed = replace(plan, argv=plan.argv + ("--preflight",))
        self.assertHold("MANIFEST_INVOCATION_CHANGED", lambda: a.invoke_once(changed, clock=lambda: NOW,
                                   immediate_gate=lambda *_: self.fail("gate"), reserve=lambda *_: self.fail("claim"),
                                   execute=lambda *_: self.fail("transport")))

    def test_success_requires_real_writer_pins_and_real_publish_receipt(self):
        s, receipt, *_ = fixture()
        for patch in ({"mode": "PREFLIGHT"}, {"status": "PREFLIGHT_OK"}, {"status": "PUBLISHED_UNVERIFIED"},
                      {"session": "2026-10-13"}, {"release_sha256": "e" * 64},
                      {"massive_bars_enabled": 1}, {"symbol_count": True}):
            altered = {**receipt, **patch}
            with self.subTest(patch=patch), self.assertRaises(a.Hold):
                a.check_receipt(s, altered, 0)
        self.assertHold("MANIFEST_RESULT_UNVERIFIED", lambda: a.check_receipt(s, receipt, 1))

    def test_receipt_cannot_substitute_future_or_expired_view(self):
        s, receipt, *_ = fixture()
        for view in ({"observed_at": (NOW + timedelta(seconds=1)).isoformat(), "valid_until": s.not_after.isoformat()},
                     {"observed_at": NOW.isoformat(), "valid_until": s.not_before.isoformat()},
                     {"observed_at": NOW.isoformat(), "valid_until": (s.not_after + timedelta(seconds=1)).isoformat()}):
            self.assertHold("MANIFEST_RESULT_VIEW", lambda: a.check_receipt(s, {**receipt, "view": view}, 0))

    def test_duplicate_json_and_extra_stdout_are_not_a_receipt(self):
        self.assertHold("JSON_DUPLICATE_KEY", lambda: a.strict_json(b'{"status":1,"status":2}'))
        self.assertHold("JSON_INVALID", lambda: a.strict_json(b'{}\n{}\n'))
        self.assertHold("JSON_NONFINITE", lambda: a.strict_json(b'{"status":NaN}'))

    def test_changed_scope_cannot_create_another_operation_key(self):
        s = replace(self.s, finite_authority_sha256="c" * 64)
        self.assertNotEqual(s.scope_sha256, self.s.scope_sha256)
        seen = []
        plan = a.invocation(s, self.source, now=NOW)
        def reserve(key, scope_sha):
            seen.append(key)
            raise a.Hold("FIXTURE_CLAIM_ALREADY_USED")
        self.assertHold("FIXTURE_CLAIM_ALREADY_USED", lambda: a.invoke_once(plan, clock=lambda: NOW,
                            immediate_gate=lambda *_: None, reserve=reserve,
                            execute=lambda *_: self.fail("transport")))
        self.assertEqual(seen, [a.ATTEMPT_KEY])

    def test_false_gate_result_cannot_silently_authorize(self):
        plan = a.invocation(self.s, self.source, now=NOW)
        self.assertHold("EXECUTOR_GATE_PROTOCOL", lambda: a.invoke_once(plan, clock=lambda: NOW,
                            immediate_gate=lambda *_: False, reserve=lambda *_: self.fail("claim"),
                            execute=lambda *_: self.fail("transport")))

    def test_exact_manifest_binding_and_full_journal_before_reader(self):
        s, receipt, row, records, manifest, *_ = fixture()
        result = a.check_capacity_manifest(s, receipt, row, records, manifest)
        self.assertEqual(result["symbol_count"], 2)
        self.assertFalse(result["session_binding_copied"])
        self.assertNotIn("symbols", result)
        self.assertHold("DB_SESSION_BINDING_MISSING_OR_CHANGED",
                        lambda: a.check_capacity_manifest(s, receipt, row, records, manifest, require_session_binding=True))

    def test_post_first_cycle_requires_exact_copied_binding(self):
        s, receipt, row, records, manifest, *_ = fixture()
        row["state"]["sessions"][s.day] = {"capacity_binding": deepcopy(row["state"]["daily_capacity"][s.day])}
        row["state_sha"] = a.digest(row["state"])
        self.assertTrue(a.check_capacity_manifest(s, receipt, row, records, manifest,
                                                  require_session_binding=True)["session_binding_copied"])
        row["state"]["sessions"][s.day]["capacity_admission_blocked"] = "fixture"
        row["state_sha"] = a.digest(row["state"])
        self.assertHold("DB_ADMISSION_BLOCKED", lambda: a.check_capacity_manifest(s, receipt, row, records, manifest))

    def test_changed_state_journal_and_noncanonical_manifest_fail(self):
        s, receipt, row, records, manifest, *_ = fixture()
        altered = deepcopy(row)
        altered["state"]["epoch"] = "fixture"
        self.assertHold("DB_STATE_HASH", lambda: a.check_capacity_manifest(s, receipt, altered, records, manifest))
        self.assertHold("DB_JOURNAL_HEAD", lambda: a.check_capacity_manifest(s, receipt, row, [], manifest))
        corrupted = deepcopy(records)
        corrupted[0]["payload"]["type"] = "fixture"
        self.assertHold("DB_JOURNAL_HASH", lambda: a.check_capacity_manifest(s, receipt, row, corrupted, manifest))
        self.assertHold("MANIFEST_READBACK_MISMATCH",
                        lambda: a.check_capacity_manifest(s, receipt, row, records,
                                                          replace(manifest, raw=manifest.raw + b"\n")))

    def test_prepare_journal_and_optional_session_copy_are_not_fabricated(self):
        s, receipt, row, records, manifest, *_ = fixture()
        altered = deepcopy(records)
        altered[0]["journal_key"] = "unrelated"
        altered[0]["payload"]["journal_key"] = "unrelated"
        altered[0]["record_sha"] = a.digest({k: v for k, v in altered[0].items() if k != "record_sha"})
        row["journal_head"] = altered[0]["record_sha"]
        self.assertHold("DB_PREPARE_RECEIPT_MISSING_OR_CHANGED",
                        lambda: a.check_capacity_manifest(s, receipt, row, altered, manifest))

    def test_same_bytes_replaced_inode_do_not_match_writer_readback(self):
        s, receipt, row, records, manifest, *_ = fixture()
        self.assertHold("MANIFEST_READBACK_IDENTITY_MISMATCH", lambda: a.check_capacity_manifest(
            s, receipt, row, records, replace(manifest, inode=manifest.inode + 1)))

    def test_ready_marker_requires_exact_scope_catalog_and_symbols(self):
        values = fixture()
        self.assertEqual(a.reader_gate(*values, now=NOW)["status"], "READER_PREREQUISITE_BYTES_RECONCILED")
        for index, raw in ((5, a.canonical({"epoch": values[0].epoch, "session": "2026-10-13"})),
                           (5, b'{}'), (6, b'{}')):
            changed = list(values)
            changed[index] = evidence(raw)
            with self.subTest(index=index, raw=raw), self.assertRaises(a.Hold):
                a.reader_gate(*changed, now=NOW)

    def test_reader_guard_stops_before_ten_seconds_and_wrong_day(self):
        values = fixture()
        for current in (OPEN - timedelta(seconds=10), OPEN, NOW - timedelta(days=1),
                        OPEN - timedelta(hours=6, microseconds=1)):
            self.assertHold("READER_READY_WINDOW_CLOSED", lambda: a.reader_gate(*values, now=current))
        a.reader_gate(*values, now=OPEN - timedelta(seconds=10, microseconds=1))

    def test_actual_read_only_file_reader_rejects_symlink_hardlink_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            root.chmod(0o700)
            path = root / "2026-10-12.json"
            path.write_bytes(b'{"fixture":true}')
            path.chmod(0o600)
            info = root.stat()
            pin = a.DirectoryPin(info.st_dev, info.st_ino, info.st_uid)
            self.assertEqual(a.read_private_file(str(root), pin, path.name).raw, b'{"fixture":true}')
            path.chmod(0o644)
            self.assertHold("READBACK_FILE_POLICY", lambda: a.read_private_file(str(root), pin, path.name))
            path.chmod(0o600)
            os.link(path, root / "alias.json")
            self.assertHold("READBACK_FILE_POLICY", lambda: a.read_private_file(str(root), pin, path.name))
            (root / "alias.json").unlink()
            (root / "link.json").symlink_to(path)
            self.assertHold("READBACK_FILE_UNAVAILABLE", lambda: a.read_private_file(str(root), pin, "link.json"))
            self.assertHold("READBACK_ROOT_PIN", lambda: a.read_private_file(str(root), replace(pin, inode=pin.inode + 1), path.name))

    def test_root_path_replacement_during_read_is_detected(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent).resolve() / "private"
            root.mkdir(mode=0o700)
            path = root / "ready.json"
            path.write_bytes(b'{}')
            path.chmod(0o600)
            info = root.stat()
            pin = a.DirectoryPin(info.st_dev, info.st_ino, info.st_uid)
            read = os.read
            swapped = False
            def changing_read(fd, maximum):
                nonlocal swapped
                if not swapped:
                    root.rename(root.with_name("old-private"))
                    root.mkdir(mode=0o700)
                    swapped = True
                return read(fd, maximum)
            with mock.patch.object(a.os, "read", side_effect=changing_read):
                self.assertHold("READBACK_ROOT_CHANGED", lambda: a.read_private_file(str(root), pin, "ready.json"))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(AdapterTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    public = {"schema": "CODEX_NEW_ISOLATED_TEST_RESULT_V1", "methods": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "scope": "NEW_ADAPTER_SYNTHETIC_ONLY", "app_imports": 0, "db_queries": 0,
              "producer_runs": 0, "transport_runs": 0, "host_operations": 0,
              "source_sha256": hashlib.sha256((ROOT / "image_path_adapter.py").read_bytes()).hexdigest()}
    (ROOT / "LOCAL_RESULT.json").write_bytes(a.canonical(public) + b"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
