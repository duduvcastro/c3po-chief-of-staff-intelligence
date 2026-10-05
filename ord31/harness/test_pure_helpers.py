"""Only standard-library and new pure helpers; no project application imports or Docker."""
import ast
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest

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

if __name__ == "__main__":
    unittest.main()
