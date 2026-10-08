"""New integration proofs: exact historical receipt reader, new epoch and engine fixtures."""
import ast
import base64
import copy
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from common import Hold, PinnedDirectory, canonical, digest, instant, need, strict
import k12


def h(text): return digest(text.encode())


class Engine:
    def __init__(self, row, stdout): self.row, self.stdout, self.calls = row, stdout, []
    def call(self, command, *args, limit):
        self.calls.append(command)
        if command == "inspect": return {"returncode": 0, "stdout": canonical(self.row)}
        if command == "logs": return {"returncode": 0, "stdout": self.stdout}
        if command == "stop":
            self.row.update(state="exited", running=False, exit_code=143, finished_at="2026-10-12T10:40:32Z")
            return {"returncode": 0, "stdout": b"id\n"}
        raise AssertionError(command)


class Manifests:
    def recheck(self): pass
    def state(self, day): return {"manifest_present": False, "temporaries": 0}


def example(mode="PERSIST"):
    ctx = {"model": "SERVER_EPOCH_V2", "epoch": "TEST_NEW_EPOCH_20261012", "session": "2026-10-12",
           "lane": "CAPACITY", "release_sha256": h("new release")}
    cap = {"schema": "R2D2_CAPACITY_DAY_ONCE_REQUEST_V2", "context": ctx, "window": "primary", "window_slot": 1,
           "view_UTC": "2026-10-12T10:45:00Z", "image_id": "sha256:" + h("image"),
           "capacity_config_sha256": h("config"), "writer_argv": ["python", "-I", "-B", "/new-config/writer.py"],
           "network": "fixture-network", "mounts": [{"source": "/fixture-source", "destination": "/fixture-config", "rw": False}]}
    cap_raw = canonical(cap)
    payload = {"mode": mode, "window": "primary", "window_slot": 1, "view_UTC": cap["view_UTC"],
               "launch_request_sha256": h("launch request"), "launch_receipt_sha256": None,
               "capacity_request_sha256": digest(cap_raw), "persist_name": "k12-2026-10-12-w1.writer.json", "container_id": "a" * 64}
    detail = {**{k: payload[k] for k in ("container_id", "capacity_request_sha256", "window", "window_slot", "view_UTC")},
              "image_id": cap["image_id"]}
    launch = {"schema": "SERVER_FAMILY_RECEIPT_V2", "context": ctx, "status": "COMPLETE", "operation": "F4_K12_LAUNCH",
              "request_sha256": payload["launch_request_sha256"], "started_UTC": "2026-10-12T10:39:58Z",
              "finished_UTC": "2026-10-12T10:40:00Z", "detail": detail}
    launch_raw = canonical(launch); payload["launch_receipt_sha256"] = digest(launch_raw)
    now = "2026-10-12T10:46:01Z" if mode != "STOP" else "2026-10-12T10:40:31Z"
    request = {"schema": "SERVER_FAMILY_REQUEST_V2", "context": ctx, "operation": "F4_K12_" + mode, "payload": payload,
               "required_gates": ["OWN_LAUNCH_COMPLETE", "OWN_CAPACITY_REQUEST"], "start_UTC": now,
               "end_UTC": "2026-10-12T10:48:32Z" if mode != "STOP" else "2026-10-12T10:42:00Z", "budget_seconds": 60}
    row = {"id": "a" * 64, "name": "/c3po-k12-2026-10-12-w1", "image_id": cap["image_id"],
           "state": "exited" if mode != "STOP" else "running", "running": mode == "STOP", "exit_code": 0, "oom_killed": False,
           "started_at": "2026-10-12T10:40:00Z", "finished_at": "2026-10-12T10:45:30Z", "request_label": payload["launch_request_sha256"],
           "capacity_label": digest(cap_raw), "read_only_root": True, "auto_remove": False, "restart_policy": "no",
           "cmd": cap["writer_argv"], "network_mode": cap["network"],
           "mounts": [{"Type": "bind", "Source": "/fixture-source", "Destination": "/fixture-config", "RW": False}]}
    stdout = canonical({"schema": k12.WRITER_SCHEMA, "status": "PUBLISHED_VERIFIED", "code": None,
                        "session": ctx["session"], "epoch": ctx["epoch"], "release_sha256": ctx["release_sha256"],
                        "mode": "PUBLISH", "capacity_config_sha256": cap["capacity_config_sha256"], "prepare_status": "COMMITTED"})
    return request, launch_raw, cap_raw, Engine(row, stdout), now


class TestK12(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="k12-new-fixture-", dir=str(Path(tempfile.gettempdir()).resolve()))
        os.chmod(self.tmp.name, 0o700); self.root = PinnedDirectory(self.tmp.name)
    def tearDown(self): self.root.close(); self.tmp.cleanup()
    def run_case(self, request, launch, cap, engine, now, recheck=lambda: None):
        return k12.execute(request, launch, cap, engine=engine, receipts=self.root, manifests=Manifests(), clock=lambda: now, recheck=recheck)
    def test_c34_pending_then_exact_persist_then_final_collection(self):
        args = example(); collect = copy.deepcopy(args[0]); collect["payload"]["mode"] = "COLLECT"; collect["operation"] = "F4_K12_COLLECT"
        self.assertEqual(self.run_case(collect, *args[1:])["collection"], "PENDING_PERSIST")
        result = self.run_case(*args); raw = self.root.read(args[0]["payload"]["persist_name"])
        self.assertEqual(digest(raw), result["persisted_sha256"])
        self.assertEqual(self.run_case(collect, *args[1:])["collection"], "WRITER_PUBLISHED_BYTES_ONLY")
        self.assertEqual(args[3].calls, ["inspect", "logs", "inspect"])
        from k12_reader_reference import k12_persisted
        parsed, stdout = k12_persisted(raw, {"epoch": args[0]["context"]["epoch"], "container_id": "a" * 64})
        self.assertEqual(stdout, args[3].stdout); self.assertEqual(set(parsed), k12.PERSIST_KEYS)
    def test_c34_future_collection_dependency_refused(self):
        args = example(); args[0]["required_gates"].append("K12_COLLECT_COMPLETE")
        with self.assertRaisesRegex(Hold, "C34_DEPENDENCY_CYCLE"): self.run_case(*args)
        self.assertEqual(args[3].calls, [])
    def test_c34_early_refused(self):
        args = example(); args[0]["start_UTC"] = "2026-10-12T10:45:59Z"
        with self.assertRaisesRegex(Hold, "C34_PERSIST_EARLY"): self.run_case(*args)
    def test_c34_duplicate_persist_is_not_a_second_write(self):
        args = example(); self.run_case(*args)
        with self.assertRaisesRegex(Hold, "K12_PERSIST_ALREADY_EXISTS"): self.run_case(*args)
    def test_c34_duplicated_truncated_or_exit_inconsistent_logs(self):
        for broken in (b'{"schema":', b'{}\n{}\n', b'{}', b'NaN\n'):
            with self.subTest(stdout=broken):
                args = example(); args[3].stdout = broken
                with self.assertRaises(Hold): self.run_case(*args)
                self.assertFalse(self.root.exists(args[0]["payload"]["persist_name"]))
        args = example(); args[3].row["exit_code"] = 3
        with self.assertRaisesRegex(Hold, "WRITER_EXIT_STATUS"): self.run_case(*args)
    def test_wrong_container_command_mount_label_and_image_refused(self):
        for key, bad in (("id", "b"*64), ("cmd", ["arbitrary"]), ("mounts", []), ("capacity_label", h("wrong")), ("image_id", "sha256:"+h("wrong"))):
            args = example(); args[3].row[key] = bad
            with self.subTest(key=key), self.assertRaises(Hold): self.run_case(*args)
            self.assertNotIn("logs", args[3].calls)
    def test_c35_distinct_window_positive_floor_and_one_stop(self):
        args = example("STOP"); self.assertEqual(self.run_case(*args)["effects"], 1)
        self.assertEqual(args[3].calls, ["inspect", "stop", "inspect"])
    def test_c35_same_window_floor_zero_refused(self):
        args = example("STOP"); args[0]["start_UTC"] = "2026-10-12T10:40:00Z"
        with self.assertRaisesRegex(Hold, "C35_NO_POSITIVE_FLOOR"): self.run_case(*args)
        self.assertEqual(args[3].calls, [])
    def test_c35_no_margin_or_budget_refused(self):
        for key, bad in (("end_UTC", "2026-10-12T10:40:50Z"), ("budget_seconds", 27)):
            args = example("STOP"); args[0][key] = bad
            with self.assertRaises(Hold): self.run_case(*args)
    def test_runtime_recheck_failure_precedes_first_effect(self):
        args = example("STOP")
        def refused(): raise Hold("RUNTIME_CHANGED")
        with self.assertRaisesRegex(Hold, "RUNTIME_CHANGED"): self.run_case(*args, recheck=refused)
        self.assertEqual(args[3].calls, [])
    def test_private_receipt_symlink_and_root_replacement_refused(self):
        args = example(); name = args[0]["payload"]["persist_name"]
        os.symlink("/no-target", Path(self.tmp.name) / name)
        with self.assertRaisesRegex(Hold, "K12_PERSIST_ALREADY_EXISTS"): self.run_case(*args)
    def test_old_session_and_wrong_context_refused(self):
        args = example(); args[0]["context"]["session"] = "2026-10-09"
        with self.assertRaises(Hold): self.run_case(*args)


if __name__ == "__main__": unittest.main()
