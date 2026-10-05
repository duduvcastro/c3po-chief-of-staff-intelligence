"""Only standard-library and new pure helpers; no project application imports or Docker."""
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ord31_candidate_helpers", HERE / "run_ci.py")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

class PureChecks(unittest.TestCase):
    def test_all_candidate_python_syntax(self):
        for name in ("driver.py", "observe.py", "run_ci.py", "test_pure_helpers.py"):
            ast.parse((HERE / name).read_text(), filename=name)
        driver_tree = ast.parse((HERE / "driver.py").read_text())
        child = next(ast.literal_eval(node.value) for node in driver_tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "CHILD" for target in node.targets))
        ast.parse(child, filename="embedded-stand-in.py")

    def test_render_binds_source_at_top_level_and_preserves_launcher(self):
        image = "sha256:" + "a" * 64
        _, argv, _, stop, binds = helpers.render_unit((HERE / "reader.service.template").read_bytes(), image, Path("/synthetic-ci-root"))
        self.assertEqual(len(binds), 5)
        self.assertEqual(binds[3], ("/synthetic-ci-root/source", "/c3po-source"))
        self.assertEqual(argv[-4:], ["python", "-I", "-B", "/c3po-reader/reader_launcher.py"])
        self.assertEqual(stop[-4:], ["stop", "-t", "25", "c3po-reader"])

    def test_changed_template_is_refused(self):
        data = (HERE / "reader.service.template").read_bytes().replace(b"/c3po-reader/reader_launcher.py", b"/wrong.py")
        with self.assertRaises(RuntimeError):
            helpers.render_unit(data, "sha256:" + "a" * 64, Path("/synthetic-ci-root"))

    def test_engine_mounts_reject_writable_or_missing_source_bind(self):
        image = "sha256:" + "a" * 64
        _, _, _, _, binds = helpers.render_unit((HERE / "reader.service.template").read_bytes(), image, Path("/synthetic-ci-root"))
        container = {"Image": image, "HostConfig": {"Init": True, "ReadonlyRootfs": True, "NetworkMode": "none"},
                     "Mounts": [{"Type": "bind", "Source": source, "Destination": target, "RW": False} for source, target in binds]}
        helpers.check_mounts(container, binds, image)
        container["Mounts"][3]["RW"] = True
        with self.assertRaises(RuntimeError): helpers.check_mounts(container, binds, image)
        container["Mounts"].pop(3)
        with self.assertRaises(RuntimeError): helpers.check_mounts(container, binds, image)

    def term_records(self):
        pin, token, pid = "b" * 64, "c" * 32, 12345
        notices = [{"status": "STARTING", "launcher_sha256": pin, "launcher_pinned": True, "build_sha": helpers.SOURCE_REVISION},
                   {"status": "STATUS_WITHHELD"},
                   {"status": "STOPPED", "reason": "SIGNAL", "child_signal": "SIGTERM", "killed": False,
                    "status_lines": 1, "status_withheld": 3, "dropped_lines": 1}]
        proof = {"token": token, "launcher_sha256": pin, "launcher_main_exit": 0,
                 "children": [{"pid": pid, "index": 1}], "child_pids_absent_after_main": True,
                 "exclusive_lock_immediate_after_main": True, "real_worker_input_proof": "NOT_COVERED"}
        stdout = "\n".join(map(json.dumps, notices)) + "\nORD31_PROOF " + json.dumps(proof) + "\n"
        stderr = helpers.STATUS_PREFIX + json.dumps({"schema": "R2D2_V2_COLLECTOR_STATUS_V2", "child_pid": pid}) + "\n"
        return pin, token, stdout, stderr

    def test_directed_check_accepts_only_declared_scope(self):
        pin, token, stdout, stderr = self.term_records()
        result = helpers.check_directed("term", 0, stdout, stderr, pin, token)
        self.assertEqual(result["result"], "PASS_DIRECTED_ONLY")
        with self.assertRaises(RuntimeError):
            helpers.check_directed("term", 0, stdout.replace("NOT_COVERED", "COVERED"), stderr, pin, token)

    def test_duplicate_sentinel_reaching_output_fails(self):
        pin, token, stdout, stderr = self.term_records()
        leakage = helpers.STATUS_PREFIX + '{"schema":"R2D2_V2_COLLECTOR_STATUS_V2","note":"US:SYNTH","note":"SAFE_CODE"}\n'
        with self.assertRaises(RuntimeError):
            helpers.check_directed("term", 0, stdout, stderr + leakage, pin, token)

    def test_wrong_pid_or_missing_reap_fails(self):
        pin, token, stdout, stderr = self.term_records()
        with self.assertRaises(RuntimeError):
            helpers.check_directed("term", 0, stdout, stderr.replace("12345", "54321"), pin, token)
        with self.assertRaises(RuntimeError):
            helpers.check_directed("term", 0, stdout.replace('"child_pids_absent_after_main": true', '"child_pids_absent_after_main": false'), stderr, pin, token)

    def test_docker_environment_pins_local_socket_and_discards_remote_settings(self):
        inherited = {"DOCKER_HOST": "tcp://synthetic.invalid:2376", "DOCKER_CONFIG": "/inherited/config",
                     "DOCKER_CONTEXT": "inherited-remote", "DOCKER_TLS_VERIFY": "1", "DOCKER_CERT_PATH": "/inherited/certs",
                     "GITHUB_ACTIONS": "true"}
        looked = []
        def socket_only(path):
            looked.append(path)
            return SimpleNamespace(st_mode=stat.S_IFSOCK | 0o660)
        result = helpers.local_engine_environment(inherited, Path("/synthetic-ci-root/etc/docker-cli"), socket_stat=socket_only)
        self.assertEqual(looked, ["/var/run/docker.sock"])
        self.assertEqual(result["DOCKER_HOST"], "unix:///var/run/docker.sock")
        self.assertEqual(result["DOCKER_CONFIG"], "/synthetic-ci-root/etc/docker-cli")
        self.assertFalse({"DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"} & result.keys())
        self.assertEqual(result["GITHUB_ACTIONS"], "true")
        self.assertEqual(inherited["DOCKER_CONTEXT"], "inherited-remote")

    def test_missing_docker_socket_is_refused_without_real_socket_access(self):
        def absent(_path):
            raise FileNotFoundError("synthetic missing socket")
        with self.assertRaisesRegex(RuntimeError, "socket is absent"):
            helpers.local_engine_environment({}, Path("/synthetic/config"), socket_stat=absent)

    def test_regular_file_or_symlink_docker_socket_is_refused(self):
        for kind in (stat.S_IFREG, stat.S_IFLNK, stat.S_IFDIR):
            with self.subTest(kind=kind), self.assertRaisesRegex(RuntimeError, "not a socket"):
                helpers.local_engine_environment({}, Path("/synthetic/config"),
                                                 socket_stat=lambda _path, kind=kind: SimpleNamespace(st_mode=kind | 0o600))

class InputSealChecks(unittest.TestCase):
    """Synthetic files and callbacks only: never call run_engine or main."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=str(Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.harness = self.root / "delivery"
        self.harness.mkdir()
        names = helpers.parse_delivery_manifest((HERE / "SHA256SUMS").read_bytes())
        for name in names:
            (self.harness / name).write_bytes(("synthetic delivered bytes: " + name).encode("ascii"))
        self.launcher = self.root / "input-launcher.py"
        self.launcher.write_bytes(b"synthetic launcher bytes")
        self.archive = self.root / "source.tar"
        self.archive.write_bytes(b"synthetic archive bytes")
        self.bind = self.root / "bind"
        self.bind.mkdir()
        (self.bind / "reader_launcher.py").write_bytes(self.launcher.read_bytes())
        for name in ("driver.py", "observe.py"):
            (self.bind / name).write_bytes((self.harness / name).read_bytes())
        self.args = SimpleNamespace(launcher=self.launcher, source_archive=self.archive,
                                    expected_launcher_sha256=helpers.digest(self.launcher.read_bytes()),
                                    source_archive_sha256=helpers.digest(self.archive.read_bytes()))
        self.reseal()
        self.here_patch = mock.patch.object(helpers, "HERE", self.harness)
        self.archive_patch = mock.patch.object(helpers, "SOURCE_ARCHIVE_SHA256", self.args.source_archive_sha256)
        self.here_patch.start()
        self.archive_patch.start()
        self.addCleanup(self.here_patch.stop)
        self.addCleanup(self.archive_patch.stop)

    def reseal(self):
        lines = [helpers.digest(path.read_bytes()) + "  " + path.name for path in sorted(self.harness.iterdir())
                 if path.name != "SHA256SUMS"]
        manifest = ("\n".join(lines) + "\n").encode("ascii")
        (self.harness / "SHA256SUMS").write_bytes(manifest)
        self.args.expected_harness_manifest_sha256 = helpers.digest(manifest)

    def gate(self, action, label="evidence"):
        out = self.root / label
        out.mkdir()
        receipt = {"status": "PREPARED_NOT_EXECUTED"}
        helpers.run_with_input_integrity(self.args, receipt, self.bind, out,
                                         lambda: action(receipt))
        return receipt, out

    def test_positive_before_after_seals_cover_all_delivered_and_copied_files(self):
        before = helpers.snapshot_inputs(self.args, self.bind)
        self.assertEqual(before["errors"], [])
        names = set(helpers.parse_delivery_manifest((self.harness / "SHA256SUMS").read_bytes()))
        self.assertEqual(set(before["files"]), {"harness/SHA256SUMS", "launcher_input", "source_archive",
                         "bind/reader_launcher.py", "bind/driver.py", "bind/observe.py"} | {"harness/" + name for name in names})
        receipt, out = self.gate(lambda value: value.update(status="PASS_LAUNCHER_LIFECYCLE_SHAPES"))
        proof = json.loads((out / "input-integrity-before-after.json").read_text())
        self.assertEqual(proof["before"], proof["after"])
        self.assertEqual(proof["status"], "PASS_INPUT_INTEGRITY_BEFORE_AFTER")
        self.assertEqual(receipt["status"], "PASS_LAUNCHER_LIFECYCLE_SHAPES")
        self.assertEqual(receipt["input_integrity"]["proof_sha256"], helpers.digest((out / "input-integrity-before-after.json").read_bytes()))

    def test_archive_parser_pins_the_exact_consumed_buffer_before_reading_tar(self):
        def archive_bytes(body):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as archive:
                entry = tarfile.TarInfo("c3po/backend/app/synthetic_source.py")
                entry.size = len(body)
                archive.addfile(entry, io.BytesIO(body))
            return stream.getvalue()
        source = b"SYNTHETIC_VALUE = 1\n"
        certified = archive_bytes(source)
        self.archive.write_bytes(certified)
        with mock.patch.object(helpers, "SOURCE_ARCHIVE_SHA256", helpers.digest(certified)):
            self.assertEqual(helpers.archive_python_files(self.archive),
                             {"synthetic_source.py": helpers.digest(source)})
            # The replacement is also a well-formed tar; only the consumed byte pin rejects it.
            self.archive.write_bytes(archive_bytes(b"SYNTHETIC_VALUE = 2\n"))
            with self.assertRaisesRegex(RuntimeError, "archive bytes consumed differ"):
                helpers.archive_python_files(self.archive)

    def test_additional_manifest_file_is_sealed_without_a_frozen_file_count(self):
        extra = self.harness / "additional-evidence.json"
        extra.write_bytes(b"synthetic additional evidence")
        self.reseal()
        before = helpers.snapshot_inputs(self.args, self.bind)
        self.assertEqual(before["errors"], [])
        self.assertIn("harness/additional-evidence.json", before["files"])
        extra.write_bytes(b"mutated additional evidence")
        after = helpers.snapshot_inputs(self.args, self.bind, reference=before)
        self.assertTrue(after["errors"])

    def test_manifest_rejects_duplicate_unsafe_self_and_missing_required_names(self):
        valid = (self.harness / "SHA256SUMS").read_bytes()
        malformed = (valid + valid.splitlines(keepends=True)[0],
                     valid + b"0" * 64 + b"  ../escape.py\n",
                     valid + b"0" * 64 + b"  subdir/file.py\n",
                     valid + b"0" * 64 + b"  SHA256SUMS\n",
                     b"0" * 64 + b"  unrelated.py\n")
        for data in malformed:
            with self.subTest(data=data[-100:]), self.assertRaises(helpers.InputIntegrityError):
                helpers.parse_delivery_manifest(data)

    def test_manifest_rewrite_with_matching_file_hash_still_requires_external_pin(self):
        path = self.harness / "driver.py"
        path.write_bytes(b"rewritten synthetic helper")
        old_pin = self.args.expected_harness_manifest_sha256
        self.reseal()
        self.args.expected_harness_manifest_sha256 = old_pin
        snapshot = helpers.snapshot_inputs(self.args, self.bind)
        self.assertTrue(any("harness/SHA256SUMS" in error for error in snapshot["errors"]))

    def test_regular_reader_rejects_symlink_file_parent_nonregular_and_traversal(self):
        link = self.root / "linked.py"
        link.symlink_to(self.launcher)
        directory_link = self.root / "linked-dir"
        directory_link.symlink_to(self.harness, target_is_directory=True)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for path in (link, directory_link / "driver.py", self.harness, fifo,
                     self.harness / ".." / "input-launcher.py"):
            with self.subTest(path=path.name), self.assertRaises(helpers.InputIntegrityError):
                helpers.regular_bytes(path)

    def test_after_mutations_deletion_and_link_always_block_pass(self):
        targets = [("archive", self.archive), ("launcher", self.launcher),
                   ("helper", self.harness / "driver.py"),
                   ("bind-launcher", self.bind / "reader_launcher.py"),
                   ("bind-helper", self.bind / "observe.py"),
                   ("manifest", self.harness / "SHA256SUMS"),
                   ("deletion", self.harness / "ROOT_REVIEW.json"),
                   ("link", self.harness / "README.md")]
        for label, path in targets:
            original = path.read_bytes()
            out = self.root / label
            out.mkdir()
            receipt = {"status": "PREPARED_NOT_EXECUTED"}
            def action():
                receipt["status"] = "PASS_LAUNCHER_LIFECYCLE_SHAPES"
                if label == "deletion":
                    path.unlink()
                elif label == "link":
                    path.unlink()
                    path.symlink_to(self.launcher)
                else:
                    path.write_bytes(original + b"\nmutation")
            with self.subTest(label=label), self.assertRaises(helpers.InputIntegrityError):
                helpers.run_with_input_integrity(self.args, receipt, self.bind, out, action)
            self.assertEqual(receipt["status"], "FAILED_INPUT_INTEGRITY")
            proof = json.loads((out / "input-integrity-before-after.json").read_text())
            self.assertEqual(proof["status"], "FAILED_INPUT_INTEGRITY")
            self.assertTrue(proof["after"]["errors"])
            # A damaged after-manifest cannot omit any before-listed file.
            self.assertTrue(set(proof["before"]["files"]) <= set(proof["after"]["files"]))
            if path.is_symlink():
                path.unlink()
            path.write_bytes(original)

    def test_before_integrity_failure_skips_execution_and_still_runs_after_snapshot(self):
        self.archive.write_bytes(b"changed before")
        called = []
        with self.assertRaises(helpers.InputIntegrityError):
            self.gate(lambda value: called.append(value))
        self.assertEqual(called, [])
        proof = json.loads((self.root / "evidence" / "input-integrity-before-after.json").read_text())
        self.assertIsNotNone(proof["before"])
        self.assertIsNotNone(proof["after"])
        self.assertEqual(proof["status"], "FAILED_INPUT_INTEGRITY")

    def test_engine_exception_remains_original_when_after_seals_pass(self):
        original = ValueError("synthetic engine failure")
        def action(_receipt):
            raise original
        with self.assertRaises(ValueError) as caught:
            self.gate(action)
        self.assertIs(caught.exception, original)
        receipt = json.loads((self.root / "evidence" / "receipt.json").read_text())
        self.assertEqual(receipt["status"], "FAILED_CI_SCOPE")
        self.assertEqual(receipt["input_integrity"]["status"], "PASS_INPUT_INTEGRITY_BEFORE_AFTER")

    def test_after_failure_retains_original_engine_exception_in_cause_and_receipt(self):
        original = ValueError("synthetic original engine failure")
        def action(_receipt):
            self.archive.write_bytes(b"changed during failed synthetic action")
            raise original
        with self.assertRaises(helpers.InputIntegrityError) as caught:
            self.gate(action)
        self.assertIs(caught.exception.__cause__, original)
        receipt = json.loads((self.root / "evidence" / "receipt.json").read_text())
        self.assertEqual(receipt["status"], "FAILED_INPUT_INTEGRITY")
        self.assertEqual(receipt["original_failure_class"], "ValueError")
        self.assertEqual(receipt["original_failure"], str(original))

    def test_unexpected_after_snapshot_error_blocks_pass(self):
        before = helpers.snapshot_inputs(self.args, self.bind)
        with mock.patch.object(helpers, "snapshot_inputs", side_effect=[before, RuntimeError("synthetic after read failure")]):
            with self.assertRaises(helpers.InputIntegrityError):
                self.gate(lambda value: value.update(status="PASS_LAUNCHER_LIFECYCLE_SHAPES"))
        receipt = json.loads((self.root / "evidence" / "receipt.json").read_text())
        self.assertEqual(receipt["status"], "FAILED_INPUT_INTEGRITY")

if __name__ == "__main__":
    unittest.main()
