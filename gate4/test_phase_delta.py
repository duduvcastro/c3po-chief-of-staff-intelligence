"""New C6b phase tests only; no historical suites or app imports."""
import ast
import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import image_path_adapter as a

OPEN = datetime(2026, 10, 12, 13, 30, tzinfo=timezone.utc)
PREPARED = OPEN - timedelta(hours=2)
CAPTURE_OPEN = datetime(2026, 10, 12, 14, 0, tzinfo=timezone.utc)
CAPTURE_CLOSE = CAPTURE_OPEN + timedelta(minutes=1)


def fixture():
    uid, gid = 0, 0
    s = a.Scope("1" * 40, "sha256:" + "2" * 64, "3" * 64, "4" * 64,
                "5" * 64, "6" * 64, "7" * 64, "8" * 64, "9" * 64,
                uid, "/fixture-private-manifests", OPEN,
                PREPARED - timedelta(seconds=1), PREPARED + timedelta(seconds=12),
                PREPARED, "DELEGATED_ACT_B")
    document = {"schema": "V2_DAILY_CAPACITY_BINDING_CANDIDATE_V1", "epoch": s.epoch,
                "day": s.day, "release_sha": s.release_sha256,
                "monitored_symbols": ["FIXA", "FIXB"], "contract": {"synthetic": True}}
    binding = {"sha": a.digest(document), "document": document}
    state = {"epoch": s.epoch, "release_sha": s.release_sha256,
             "daily_capacity": {s.day: binding}, "sessions": {}}
    payload = {"journal_key": "capacity-prepared:" + s.day, "type": "CAPACITY_DAY_PREPARED",
               "session": s.day, "plan_sha": binding["sha"], "payload": document}
    record = {"epoch": s.epoch, "sequence": 1, "journal_key": payload["journal_key"],
              "recorded_at": PREPARED.isoformat(), "payload": payload, "previous_sha": ""}
    record["record_sha"] = a.digest(record)
    row = {"state": state, "state_sha": a.digest(state), "journal_head": record["record_sha"]}
    manifest = a.FileEvidence(a.canonical({"epoch": s.epoch, "session": s.day,
                         "symbols": document["monitored_symbols"], "owner_uid": uid}),
                              1, 2, uid, gid, 0o600, 1)
    receipt = {"schema": "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1", "status": "PUBLISHED_VERIFIED",
               "code": None, "mode": "PUBLISH", "epoch": s.epoch, "session": s.day,
               "owner_uid": uid, "build_sha": s.build_sha, "release_sha256": s.release_sha256,
               "package_sha256": s.package_sha256, "capacity_config_sha256": s.capacity_config_sha256,
               "capacity_veto_mode": "DISPATCH_AND_DERIVATION_ONLY", "massive_bars_enabled": True,
               "cutoff_at": (OPEN - timedelta(minutes=10)).isoformat(), "go_mode": s.require_go_mode,
               "go_sha256": "a" * 64, "template_sha256": "b" * 64,
               "binding_sha256": binding["sha"], "manifest_sha256": a.sha(manifest.raw),
               "symbol_count": 2, "file": {"uid": uid, "gid": gid, "mode": "0600", "nlink": 1,
                         "device": 1, "inode": 2, "size_within_limit": True},
               "view": {"observed_at": PREPARED.isoformat(),
                        "valid_until": (PREPARED + timedelta(seconds=10)).isoformat()}}
    ready = a.FileEvidence(a.canonical({"epoch": s.epoch, "session": s.day}),
                           1, 3, uid, gid, 0o600, 1)
    directory = a.DirectoryPin(1, 44, uid)
    catalog = a.FileEvidence(a.canonical({"schema": "MASSIVE_SESSION_V1", "epoch": s.epoch,
                              "session": s.day, "symbols": document["monitored_symbols"],
                              "device": 1, "inode": 44}), 1, 4, uid, gid, 0o600, 1)
    return s, receipt, row, [record], manifest, ready, catalog, directory


class NewPhaseTests(unittest.TestCase):
    def setUp(self):
        self.s, self.receipt, self.row, self.records, self.manifest, self.ready, self.catalog, self.directory = fixture()
        self.args = self.s, self.receipt, self.row, self.records, self.manifest

    def assertHold(self, code, callback):
        with self.assertRaises(a.Hold) as error:
            callback()
        self.assertEqual(error.exception.args, (code,))

    def copy_binding(self):
        state = self.row["state"]
        state["sessions"][self.s.day] = {"capacity_binding": copy.deepcopy(state["daily_capacity"][self.s.day])}
        self.row["state_sha"] = a.digest(state)

    def launch(self, now, **kwargs):
        return a.capture_launch_gate(*self.args, now=now,
                        not_before=kwargs.get("not_before", OPEN + timedelta(minutes=20)),
                        not_after=kwargs.get("not_after", CAPTURE_CLOSE + timedelta(minutes=2)))

    def test_process_launch_accepts_preopen_case_b_without_ready_or_session_copy(self):
        out = a.reader_process_launch_gate(*self.args, now=OPEN - timedelta(minutes=29))
        self.assertFalse(out["session_binding_copied"])
        self.assertFalse(out["session_consumer_authorized"])
        self.assertEqual(out["phase"], "PRE_OPEN")

    def test_first_cycle_does_not_require_copy_that_capture_has_not_made(self):
        out = a.after_first_cycle_gate(*self.args, now=OPEN - timedelta(seconds=1))
        self.assertFalse(out["session_binding_copied"])
        self.assertFalse(out["cycle_result_verified"])

    def test_capture_process_can_launch_after_writer_window_without_preexisting_session_copy(self):
        out = self.launch(OPEN + timedelta(minutes=22))
        self.assertFalse(out["session_binding_copied"])
        self.assertEqual(out["capture_open"], CAPTURE_OPEN.isoformat())
        self.assertEqual(out["effective_launch_not_after"], CAPTURE_CLOSE.isoformat())

    def test_post_capture_requires_exact_copy_and_does_not_claim_capture_result(self):
        self.copy_binding()
        out = a.after_capture_gate(*self.args, now=CAPTURE_CLOSE)
        self.assertTrue(out["session_binding_copied"])
        self.assertFalse(out["capture_result_verified"])

    def test_missing_post_capture_copy_refuses(self):
        self.assertHold("DB_SESSION_BINDING_MISSING_OR_CHANGED",
                        lambda: a.after_capture_gate(*self.args, now=CAPTURE_CLOSE))

    def test_even_an_equal_copy_cannot_be_promoted_before_capture_opens(self):
        self.copy_binding()
        self.assertHold("CAPTURE_COPY_CHECK_TOO_EARLY", lambda: a.after_capture_gate(
                          *self.args, now=CAPTURE_OPEN - timedelta(microseconds=1)))

    def test_changed_optional_copy_refuses_every_phase(self):
        self.copy_binding()
        self.row["state"]["sessions"][self.s.day]["capacity_binding"]["sha"] = "f" * 64
        self.row["state_sha"] = a.digest(self.row["state"])
        for callback in (lambda: a.reader_process_launch_gate(*self.args, now=PREPARED),
                         lambda: a.after_first_cycle_gate(*self.args, now=OPEN),
                         lambda: self.launch(CAPTURE_OPEN),
                         lambda: a.after_capture_gate(*self.args, now=CAPTURE_CLOSE)):
            self.assertHold("DB_SESSION_BINDING_MISSING_OR_CHANGED", callback)

    def test_process_launch_stops_at_exact_handover_and_wrong_day(self):
        for now in (OPEN - timedelta(seconds=90), OPEN - timedelta(hours=6, microseconds=1)):
            self.assertHold("READER_PROCESS_WINDOW_CLOSED",
                       lambda: a.reader_process_launch_gate(*self.args, now=now))
        self.assertHold("IMAGE_PHASE_DAY_MISMATCH", lambda: a.reader_process_launch_gate(
                          *self.args, now=PREPARED - timedelta(days=1)))

    def test_cleanup_deadline_cannot_extend_capture_launch_or_its_signed_effect_window(self):
        self.assertHold("CAPTURE_LAUNCH_WINDOW_CLOSED", lambda: self.launch(CAPTURE_CLOSE))
        self.assertHold("CAPTURE_LAUNCH_WINDOW_CLOSED", lambda: self.launch(
                        CAPTURE_OPEN, not_after=CAPTURE_OPEN))
        self.assertHold("CAPTURE_EFFECT_WINDOW_INVALID", lambda: self.launch(
                        CAPTURE_OPEN, not_before=CAPTURE_OPEN, not_after=CAPTURE_OPEN))

    def test_process_permission_does_not_bypass_ready_before_first_consumer(self):
        a.reader_process_launch_gate(*self.args, now=OPEN - timedelta(minutes=29))
        wrong = a.FileEvidence(a.canonical({"epoch": self.s.epoch, "session": "2026-10-13"}),
                         1, 3, self.s.owner_uid, os.getegid(), 0o600, 1)
        self.assertHold("READER_READY_MISMATCH", lambda: a.reader_gate(
             *self.args, wrong, self.catalog, self.directory, now=OPEN - timedelta(seconds=11),
             not_before=OPEN - timedelta(seconds=90), not_after=OPEN + timedelta(minutes=2),
             session_close=OPEN + timedelta(hours=6, minutes=30)))
        self.assertHold("READER_SESSION_WINDOW_CLOSED", lambda: a.reader_gate(
             *self.args, self.ready, self.catalog, self.directory, now=OPEN + timedelta(minutes=2),
             not_before=OPEN - timedelta(seconds=90), not_after=OPEN + timedelta(minutes=2),
             session_close=OPEN + timedelta(hours=6, minutes=30)))

    def test_capacity_copy_is_inside_available_causal_capture_in_exact_image_source(self):
        tree = ast.parse((ROOT / "sources" / "r2d2_v2_capacity_bound.py").read_bytes())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CapacityBoundCollector")
        capture = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_capture")
        self.assertIsInstance(capture.body[0], ast.If)
        self.assertIn("AVAILABLE", ast.unparse(capture.body[0].test))
        self.assertIn("super()._capture", ast.unparse(capture.body[0].body[0]))
        self.assertIn("self._capacity", ast.unparse(capture.body[1]))
        capacity = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_capacity")
        self.assertIn("session['capacity_binding'] = deepcopy(prior)", ast.unparse(capacity))

    def test_source_handover_and_calendar_windows_are_not_inferred_from_paper_times(self):
        calendar = ast.parse((ROOT / "sources" / "r2d2_v2_calendar.py").read_bytes())
        text = ast.unparse(calendar)
        self.assertIn("time(10)", text)
        self.assertIn("time(10, 1)", text)
        launcher = ast.parse((ROOT / "sources" / "reader_launcher.py").read_bytes())
        functions = [n for n in ast.walk(launcher) if isinstance(n, ast.FunctionDef)]
        run = next(n for n in functions if n.name == "supervise")
        text = ast.unparse(run)
        self.assertIn("'READY_OBSERVED' if observed else 'READY_NOT_OBSERVED'", text)
        self.assertIn("run_phase('SESSION', stop_at)", text)
        # Source finding only: this is why an independent transition guard
        # remains mandatory rather than a promise made by the process gate.

    def test_real_ten_second_view_needs_explicit_positive_readback_margin(self):
        self.assertHold("MANIFEST_VIEW_READBACK_MARGIN", lambda: replace(
                      self.s, not_after=PREPARED + timedelta(seconds=10)).validate())
        for value in (0, -1, True, float("inf"), float("nan")):
            self.assertHold("MANIFEST_READBACK_MARGIN_INVALID", lambda: replace(
                           self.s, readback_margin_seconds=value).validate())
        tight = replace(self.s, not_after=PREPARED + timedelta(seconds=11))
        a.check_receipt(tight, self.receipt, 0)

    def test_uid_zero_and_veto_mode_are_explicit_scope_constraints(self):
        self.assertHold("IMAGE_OWNER_PIN", lambda: replace(self.s, owner_uid=1000).validate())
        self.assertHold("IMAGE_VETO_MODE_PIN", lambda: replace(self.s, capacity_veto_mode="UNKNOWN").validate())
        changed = replace(self.s, capacity_veto_mode="CONTINUOUS")
        self.assertNotEqual(changed.scope_sha256, self.s.scope_sha256)
        self.assertHold("MANIFEST_RESULT_PIN_MISMATCH", lambda: a.check_receipt(changed, self.receipt, 0))
        r = dict(self.receipt, capacity_veto_mode="CONTINUOUS")
        a.check_receipt(changed, r, 0)

    def test_epoch_root_is_separate_from_session_root_and_settings_path(self):
        root = a.DirectoryPin(1, 99, 0)
        raw = a.canonical({"schema": "MASSIVE_SESSION_ROOT_V1", "epoch": self.s.epoch,
                           "device": 1, "inode": 99})
        epoch = a.FileEvidence(raw, 1, 100, 0, 0, 0o600, 1)
        kw = {"settings_journal_directory": "/fixture-epoch-root",
              "expected_journal_directory": "/fixture-epoch-root"}
        out = a.journal_root_gate(self.s, epoch, root, **kw)
        self.assertFalse(out["physical_namespace_verified"])
        self.assertHold("JOURNAL_EPOCH_ROOT_MISMATCH", lambda: a.journal_root_gate(
                         self.s, epoch, self.directory, **kw))
        self.assertHold("JOURNAL_SETTINGS_ROOT_MISMATCH", lambda: a.journal_root_gate(
                         self.s, epoch, root, **dict(kw, settings_journal_directory="/fixture-wrong")))
        wrong = a.FileEvidence(a.canonical(dict(a.strict_json(raw), epoch="EPOCH03")),
                               1, 100, 0, 0, 0o600, 1)
        self.assertHold("JOURNAL_EPOCH_ROOT_MISMATCH", lambda: a.journal_root_gate(self.s, wrong, root, **kw))

    def test_early_already_published_outcome_is_not_a_fresh_publish_receipt(self):
        early = {"schema": self.receipt["schema"], "status": "ALREADY_PUBLISHED_VERIFIED",
                 "mode": "PUBLISH", "code": None}
        self.assertHold("MANIFEST_RESULT_UNVERIFIED", lambda: a.check_receipt(self.s, early, 0))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
                 unittest.defaultTestLoader.loadTestsFromTestCase(NewPhaseTests))
    record = {"schema": "CODEX_PHASE_DELTA_RESULT_V1", "methods": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors),
              "old_methods_repeated": 0, "app_imports": 0, "db_queries": 0,
              "host_operations": 0, "scope": "NEW_SYNTHETIC_PHASE_GATES_ONLY",
              "source_sha256": hashlib.sha256((ROOT / "image_path_adapter.py").read_bytes()).hexdigest()}
    (ROOT / "DELTA_RESULT.json").write_bytes(a.canonical(record) + b"\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
