"""L12-HOST v3.3 suite. SYNTHETIC only (fake docker / systemd-run / systemctl, TEST-ONLY act B / GO bytes, temporary
directories; the family is checked unchanged by the lots tests' base class).

  Mounts     the suite's fake systemd-run refuses like systemd 255 did on the GitHub runner (bisect evidence,
             CHANGES_V33.md): rc 1 "A dependency job for <unit>.service failed" when a RequiresMountsFor path (or a
             prefix of it) has a configured FAILED mount unit; the reader start fails under that state and runs under
             the host-like one.
  Engine     a failed UNIT_START carries `unit_start_failure` (exit code, stderr sha256/size, a bounded printable
             excerpt), same code / status / accounting; the slot RESULT diagnostics name it.
  Proof      the host-mirror helpers of linux_systemd_proof (fstab edit, the two checks) and its bounded failure dumps.
  F1 / LOW6  build_specs `write --lot DOWN` needs the REAL UP dir and refuses each mismatch (grid, K9 request, GO,
             runner, capture_launch plan); `validate --out-dir` takes a relative DIR.

Run: python -I -S -B tests/test_v33.py   (one JSON summary on stdout, test names on stderr; exit 1 on failure)
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit                      # noqa: E402
import test_l12host as suite    # noqa: E402  (its Base: up_all / down / session_shell)
import test_lots_patch_v34 as lots  # noqa: E402  (its Base: plans / values_for / real, family unchanged)

rt, fx, inst, bind = kit.rt, kit.fx, kit.inst, kit.bind
bs = lots.bs
sys.path.insert(0, str(kit.FAMILY))
import linux_systemd_proof as proof  # noqa: E402  (import is inert: main() refuses outside CI)

DEPENDENCY = "A dependency job for %s.service failed. See 'journalctl -xe' for details.\n"
V32_OUTPUT_KEYS = {"schema", "status", "code", "target_kind", "target", "context", "effect_kind", "started_at",
                   "transport_at", "completed_at", "original_sha256", "original_b64", "child_exit_code",
                   "child_stdout_sha256", "child_stdout_bytes", "child_stderr_sha256", "child_stderr_bytes"}


def unit_row(env, cls, data_root=None):
    """The reviewed reader / supervisor references copied as kit.reader_row / kit.supervisor_row do; the reader's
    @HOST_DATA_ROOT@ may be another folder (here <base>/mnt/day-d-data, the runner's /mnt/day-d-data analog)."""
    if cls == "SUPERVISOR":
        return kit.supervisor_row(env)[0]
    cfg_dir = kit.config_dir(env)
    subst = {"@HOST_DATA_ROOT@": data_root or str(env.base / "data"), "@HOST_JOURNAL_ROOT@": str(env.base / "journal"),
             "@HOST_CAPACITY_ROOT@": str(env.base / "capacity"), "@HOST_CONFIG_DIR@": cfg_dir, "@IMAGE_ID@": kit.IMAGE,
             "@NETWORK@": "c3po_default", "@CONTAINER_JOURNAL_ROOT@": "/var/lib/c3po-bar/journal-e04"}
    docker = env.layout["binaries"]["docker"]
    renames = [("c3po-reader", rt.READER_NAME), ("/usr/bin/docker", docker), ("-/usr/bin/docker", "-" + docker),
               ("DOCKER_CONFIG=" + cfg_dir + "/docker-cli", "DOCKER_CONFIG=" + str(env.dockercfg))]
    return bind.unit_row(str(kit.FAMILY / "reference" / "c3po-reader.service"), subst, rt.READER_NAME, "SESSION_READER",
                         env.layout, renames)[0]


class SessionLot:
    """A minimal installed-lot directory the ENGINE reads (authority / request / runtime by fixed name): one
    session_start step with the supervisor pre-effect and the reader effect. Drives fx.run directly."""

    def __init__(self, env, reader, hold_seconds=10):
        self.env = env
        self.ready = env.base / "journal" / "ready.json"
        self.hold = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=hold_seconds)
        supervisor = unit_row(env, "SUPERVISOR")
        self.authority = kit.canonical({"layout": env.layout, "effects": {}, "ready": {"ready_path": str(self.ready)},
                                        "extended": {"steps": [{"step": "session_start", "pre_effect": supervisor,
                                                                "effect": reader, "hold_until": kit.z(self.hold)}]}})
        self.runtime = kit.canonical({"executor_uid": os.geteuid(), "election": {
            "veto_chain": [[str(env.veto), fx.dir_identity(os.stat(str(env.veto)))]]}})
        self.request = kit.canonical({"authority_sha256": kit.sha(self.authority), "runtime_sha256": kit.sha(self.runtime),
                                      "epoch": kit.EPOCH, "session": kit.DAY, "previous_session": kit.PREVIOUS,
                                      "track": "P"})
        self.dir = env.base / ("lot-%d" % time.monotonic_ns())
        self.dir.mkdir(mode=0o700)
        for name, raw in (("authority.json", self.authority), ("request.json", self.request),
                          ("runtime.json", self.runtime)):
            (self.dir / name).write_bytes(raw)
        self.key = kit.sha(kit.canonical([kit.EPOCH, kit.DAY, kit.PREVIOUS, "P", "EXTENDED", "session_start"]))

    def run(self, kind, ready_sha=None, pid=None):
        until = kit.z(datetime.now(timezone.utc) + timedelta(seconds=60))
        return fx.run(fx.engine_argv(str(self.dir), kind, "session_start", kit.sha(self.authority),
                                     kit.sha(self.request), self.key, "d" * 64, until, ready_sha, pid))

    def publish_ready(self):
        self.ready.write_bytes(kit.canonical({"epoch": kit.EPOCH, "session": kit.DAY}))
        return kit.sha(self.ready.read_bytes())


def shown(env, unit):
    """The fake systemctl's view of a unit (LoadState not-found when systemd-run never loaded it)."""
    p = subprocess.run([env.layout["binaries"]["systemctl"], "show", unit + ".service"], capture_output=True, timeout=30)
    return dict(line.split("=", 1) for line in p.stdout.decode().splitlines() if "=" in line)


# ====================================================================== fake systemd-run vs mount units, engine
class Mounts(suite.Base):
    def fake_run(self, unit, requires_mounts_for):
        argv = [str(self.env.bin / "systemd-run"), "--unit=" + unit, "--description=x"]
        argv += ["--property=RequiresMountsFor=" + v for v in requires_mounts_for] + ["/bin/true"]
        p = subprocess.run(argv, capture_output=True, timeout=30)
        return p.returncode, p.stderr.decode("ascii")

    def test_fake_systemd_run_refuses_a_failed_mount_unit_like_systemd_255(self):
        e = self.env
        mnt, data = str(e.base / "mnt"), str(e.base / "mnt" / "day-d-data")
        other = str(e.base / "journal")
        self.assertEqual(self.fake_run("u-none", [data, other]), (0, ""))                  # no mount units: v3.2 fake
        e.update_fake(mount_units={mnt: "failed"})                                         # the runner: /mnt failed
        for unit, paths in (("u-full", [data + " " + other]), ("u-only", [data]), ("u-two", [other, data])):
            self.assertEqual(self.fake_run(unit, paths), (1, DEPENDENCY % unit), unit)
            self.assertEqual(shown(e, unit)["LoadState"], "not-found", unit)               # never loaded
        self.assertEqual(self.fake_run("u-elsewhere", [other]), (0, ""))                   # the bisect's b-nomnt
        self.assertEqual(shown(e, "u-elsewhere")["LoadState"], "loaded")
        e.update_fake(mount_units={data: "active"})                                        # the host: own mount, active
        self.assertEqual(self.fake_run("u-host", [data + " " + other]), (0, ""))
        e.update_fake(mount_units={data: "failed"})                                        # the path itself failed
        self.assertEqual(self.fake_run("u-self", [data]), (1, DEPENDENCY % "u-self"))

    def test_reader_start_fails_runner_like_and_runs_host_like_with_the_reason(self):
        """The engine (fx.run, the bytes the slot runs) on the reviewed rows: the supervisor's paths do not reach
        <base>/mnt, so it starts in both states (bisect: only the reader failed); the reader fails while <base>/mnt is a
        FAILED mount unit and its data root a plain folder, and runs once the data root is its own active mount unit and
        <base>/mnt has none (the host)."""
        e = self.env
        data = e.base / "mnt" / "day-d-data"
        data.mkdir(mode=0o700, parents=True)
        lot = SessionLot(e, unit_row(e, "SESSION_READER", str(data)), hold_seconds=12)
        e.update_fake(mount_units={str(e.base / "mnt"): "failed"})
        code, out = lot.run("EXTENDED_PRE")
        self.assertEqual((code, out["status"], out["effect_kind"]), (0, "TRANSPORT_DONE", "UNIT_START"), out)
        self.assertNotIn("unit_start_failure", out)
        pid = json.loads(__import__("base64").b64decode(out["original_b64"]))["properties"]["MainPID"]
        ready_sha = lot.publish_ready()
        code, out = lot.run("EXTENDED", ready_sha, pid)
        err = (DEPENDENCY % rt.READER_NAME).encode("ascii")
        self.assertEqual((code, out["status"], out["code"], out["transport_at"], out["original_b64"]),
                         (2, "UNCERTAIN", "UNIT_START_FAILED", None, None), out)
        self.assertEqual(set(out), V32_OUTPUT_KEYS | {"unit_start_failure"})
        self.assertEqual(out["unit_start_failure"], {
            "schema": "L12HOST_UNIT_START_FAILURE_V33", "launch_class": "SESSION_READER", "unit": rt.READER_NAME,
            "child_exit_code": 1, "child_stdout_sha256": kit.sha(b""), "child_stdout_bytes": 0,
            "child_stderr_sha256": kit.sha(err), "child_stderr_bytes": len(err),
            "child_stderr_excerpt": err.decode("ascii").replace("\n", " ")})
        self.assertEqual(shown(e, rt.READER_NAME)["LoadState"], "not-found")
        e.update_fake(mount_units={str(data): "active"})                                   # host-like
        code, out = lot.run("EXTENDED", ready_sha, pid)
        self.assertEqual((code, out["status"], out["code"]), (0, "TRANSPORT_DONE", None), out)
        self.assertEqual(set(out), V32_OUTPUT_KEYS)                                        # success: v3.2 shape
        ack = json.loads(__import__("base64").b64decode(out["original_b64"]))
        self.assertEqual((ack["launch_class"], ack["held"], ack["supervisor"]["running_through_hold"]),
                         ("SESSION_READER", True, True))
        self.assertEqual([w for r in self.unit_starts() for w in r["argv"] if w.startswith("--unit=")],
                         ["--unit=" + rt.SUPERVISOR_NAME, "--unit=" + rt.READER_NAME, "--unit=" + rt.READER_NAME])

    def test_unit_start_failure_excerpt_is_bounded_and_printable(self):
        e = self.env
        noisy = (b"Failed to start transient service unit: \x00\x1b[31mbad\xff\xfe\ttab\r\n" * 40)[:1000]
        e.update_fake(systemd_run_fail={rt.SUPERVISOR_NAME: {"rc": 4, "stderr_hex": noisy.hex()}})
        lot = SessionLot(e, unit_row(e, "SESSION_READER"))
        code, out = lot.run("EXTENDED_PRE")
        failure = out["unit_start_failure"]
        self.assertEqual((code, out["status"], out["code"], out["child_exit_code"]), (2, "UNCERTAIN", "UNIT_START_FAILED", None))
        self.assertEqual((failure["launch_class"], failure["child_exit_code"], failure["child_stderr_bytes"],
                          failure["child_stderr_sha256"]), ("SUPERVISOR", 4, 1000, kit.sha(noisy)))
        excerpt = failure["child_stderr_excerpt"]
        self.assertEqual(len(excerpt), fx.STDERR_EXCERPT_BYTES)
        self.assertTrue(all(" " <= c <= "~" for c in excerpt))
        self.assertEqual(excerpt[:58], "Failed to start transient service unit: ??[31mbad?? tab  F")
        self.assertEqual(fx.stderr_excerpt(b""), "")

    def test_slot_result_names_why_the_reader_start_failed(self):
        """End to end through the timer-run slot path (Shell.run_slot -> extended worker -> engine): S1 with the
        reader's data root a FAILED mount unit: same status / code / accounting as v3.2, and the RESULT diagnostics
        now say why."""
        self.session_world()
        e = self.env
        self.ready_on_supervisor()
        self.session_shell()
        e.update_fake(mount_units={str(e.base / "data"): "failed"})
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["status"], res["code"], res["effect_calls"], res["recovery_required"]),
                         (2, "EXTENDED_UNCERTAIN_CONSUMED", "UNIT_START_FAILED", 2, True), res)
        err = (DEPENDENCY % rt.READER_NAME).encode("ascii")
        expected = "UNIT_START_FAILED:SESSION_READER:rc=1:stderr_sha256=%s:stderr_bytes=%d:stderr=%s" % (
            kit.sha(err), len(err), fx.stderr_excerpt(err))
        self.assertEqual([d for d in res["diagnostics"] if d.startswith("UNIT_START_FAILED")], [expected], res)
        self.assertEqual(res["extended"]["pre_effect"]["status"], "TRANSPORT_DONE")
        self.assertEqual([w for r in self.unit_starts() for w in r["argv"] if w.startswith("--unit=")],
                         ["--unit=" + rt.SUPERVISOR_NAME, "--unit=" + rt.READER_NAME])
        self.assertEqual(shown(e, rt.READER_NAME)["LoadState"], "not-found")


# ====================================================================== the proof's host mirror and dumps (pure)
FSTAB_RUNNER = ("# /etc/fstab: static file system information.\n"
                "LABEL=cloudimg-rootfs\t/\t ext4\tdiscard,commit=30,errors=remount-ro\t0 1\n"
                "LABEL=UEFI\t/boot/efi\tvfat\tumask=0077\t0 1\n"
                "/dev/disk/cloud/azure_resource-part1\t/mnt\tauto\tdefaults,nofail,x-systemd.after=cloud-init.service,"
                "_netdev,comment=cloudconfig\t0\t2\n"
                "#/dev/sdb1 /mnt ext4 defaults 0 0\n"
                "tmpfs /mnt/other tmpfs defaults 0 0\n")


class ProofHarness(unittest.TestCase):
    def test_fstab_mirror_removes_only_the_mnt_line(self):
        text, removed = proof.fstab_without(FSTAB_RUNNER, "/mnt")
        self.assertEqual(len(removed), 1)
        self.assertTrue(removed[0].startswith("/dev/disk/cloud/azure_resource-part1\t/mnt\t"))
        self.assertEqual(text, FSTAB_RUNNER.replace(FSTAB_RUNNER.splitlines(True)[3], ""))
        self.assertIn("#/dev/sdb1 /mnt ext4", text)                                        # comments untouched
        self.assertTrue(proof.fstab_has(text, "/mnt/other") and not proof.fstab_has(text, "/mnt"))
        self.assertFalse(proof.fstab_has(text, rt.DAY_D_DATA))
        self.assertEqual(proof.fstab_without(text, "/mnt"), (text, []))                    # idempotent
        line = proof.DAY_D_DATA_FSTAB_LINE.split()
        self.assertEqual((line[0], line[1], line[2]), ("tmpfs", rt.DAY_D_DATA, "tmpfs"))
        self.assertIn("nofail", line[3].split(","))

    def test_day_d_data_unit_name_is_the_systemd_escape(self):
        def escape(path):                                  # systemd-escape -p: '/' -> '-', '-' -> \x2d
            return "".join("\\x2d" if c == "-" else "-" if c == "/" else c for c in path.strip("/")) + ".mount"
        self.assertEqual(proof.DAY_D_DATA_UNIT, escape(rt.DAY_D_DATA))
        self.assertEqual(proof.DAY_D_DATA_UNIT, "mnt-day\\x2dd\\x2ddata.mount")

    def test_mirror_checks_are_red_on_the_runner_and_green_like_the_host(self):
        runner = {"mnt_mount": {"Id": "mnt.mount", "LoadState": "loaded", "ActiveState": "failed"},
                  "day_d_data_mount": {"Id": proof.DAY_D_DATA_UNIT, "LoadState": "not-found", "ActiveState": "inactive"},
                  "findmnt": {}}
        host = {"mnt_mount": {"Id": "mnt.mount", "LoadState": "not-found", "ActiveState": "inactive"},
                "day_d_data_mount": {"Id": proof.DAY_D_DATA_UNIT, "LoadState": "loaded", "ActiveState": "active",
                                     "SubState": "mounted"},
                "findmnt": {"target": rt.DAY_D_DATA, "fstype": "tmpfs"}}
        self.assertEqual(proof.mirror_checks(runner), {"mnt_mount_not_found_like_host": False,
                                                       "day_d_data_mount_active_like_host": False})
        self.assertEqual(proof.mirror_checks(host), {"mnt_mount_not_found_like_host": True,
                                                     "day_d_data_mount_active_like_host": True})
        for broken in ({"findmnt": {"target": "/"}}, {"day_d_data_mount": dict(host["day_d_data_mount"], ActiveState="failed")},
                       {"mnt_mount": {"LoadState": "loaded", "ActiveState": "active"}}):
            self.assertFalse(all(proof.mirror_checks(dict(host, **broken)).values()), broken)
        self.assertEqual(proof.mirror_checks({"error": "OSError: x"}), {"mnt_mount_not_found_like_host": False,
                                                                       "day_d_data_mount_active_like_host": False})

    def test_failure_dumps_are_bounded_printable_and_name_the_units(self):
        layout = {"unit_prefix": "l12proof-", "unit_name_suffix": "-e04"}
        calls = []
        noisy = "\n".join(("line %d \x1b[0m e04 " % i) + "x" * 900 for i in range(1000))
        listing = "\n".join(["c3po-reader-e04.service transient -", "l12proof-down-s1.timer transient -",
                             "ssh.service enabled enabled", "c3po-massive-e04.service transient -"])

        def run(argv, timeout=60):
            calls.append(argv)
            return 0, (listing if argv[1].startswith("list-") else noisy), ""
        dumps = proof.failure_dumps(layout, run)
        units = [rt.SUPERVISOR_NAME + ".service", rt.READER_NAME + ".service", "l12proof-down-r0.service",
                 "l12proof-down-s1.service"]
        self.assertEqual(sorted(dumps["show"]), sorted(units))
        self.assertEqual(sorted(dumps["journal"]), sorted(["l12proof-down-s1.service", rt.SUPERVISOR_NAME + ".service",
                                                           rt.READER_NAME + ".service"]))
        for row in list(dumps["show"].values()) + list(dumps["journal"].values()):
            self.assertLessEqual(len(row["lines"]), proof.DUMP_SHOW_LINES)
            self.assertTrue(all(len(l) <= proof.DUMP_LINE_CHARS and all(" " <= c <= "~" for c in l) for l in row["lines"]))
        for row in dumps["journal"].values():
            self.assertEqual(len(row["lines"]), proof.DUMP_LINES)
            self.assertTrue(row["lines"][-1].startswith("line 999 "))                      # the LAST lines
        self.assertEqual(dumps["unit_files_e04"], ["c3po-reader-e04.service transient -", "l12proof-down-s1.timer transient -",
                                                   "c3po-massive-e04.service transient -"])
        journal = [a for a in calls if a[0].endswith("journalctl")]
        self.assertTrue(all(a[a.index("-n") + 1] == "200" for a in journal) and len(journal) == 3)


# ====================================================================== F1 and LOW 6 (lots patch review)
TEST_ACT_B = b"TEST ONLY act B bytes, not the ADENDO\n"


class LotsReview(lots.Base):
    def plans_with(self, grid, *, act_b=TEST_ACT_B, go=lots.TEST_GO):
        """gen_k9_plans04 `plans` with the given TEST-ONLY act B / GO bytes (lots.Base.plans has fixed ones)."""
        self.count += 1
        gen = lots.load_generator()
        gen.source_pins = lambda tree: (gen.RISK_SOURCE_PINS_04, 190)      # TEST ONLY (lots module docstring)
        tag = "%s-%d" % (grid, self.count)
        out, a, g = self.base / ("plans-%s" % tag), self.base / ("act_b-%s.TEST_ONLY.txt" % tag), self.base / ("go-%s.TEST_ONLY.json" % tag)
        a.write_bytes(act_b)
        g.write_bytes(go)
        argv = ["plans", "--runner", str(lots.RUNNER), "--grid", grid, "--app-tree", str(self.base), "--act-b", str(a),
                "--release", str(lots.LOTS / "up_inputs" / "release.CERTIFIED.04.json"),
                "--policy", str(lots.LOTS / "up_inputs" / "policy.04.json"), "--go", str(g), "--out", str(out)]
        code, text = lots.run_main(gen.main, argv)
        self.assertEqual(code, 0, text)
        return out, g

    def up_dir(self, plans, go, name="real-UP"):
        out = self.base / name
        self.assertEqual(self.real("UP", out=out, plans=plans, go=go)["status"], "REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY")
        return out

    def down(self, plans, go, up, name):
        out = self.base / name
        return out, (lambda: self.real("DOWN", out=out, plans=plans, go=go, up_real_dir=up))

    def copy_dir(self, src, name):
        dst = self.base / name
        shutil.copytree(str(src), str(dst))
        for p in dst.rglob("*"):
            os.chmod(str(p), 0o700 if p.is_dir() else 0o600)
        return dst

    def resum(self, d):
        rows = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
        (d / "SHA256SUMS").write_bytes("".join("%s  %s\n" % (lots.sha((d / r).read_bytes()), r) for r in rows).encode())

    def test_f1_down_needs_the_up_real_dir_and_the_up_takes_none(self):
        def attempt(lot, up):
            return bs.write_real(lot, self.base / ("x-" + lot), plans_dir="/nonexistent", go="/nonexistent",
                                 layout_path=str(lots.LAYOUT), secrets_root=bs.GEN_SECRETS_ROOT,
                                 networks=dict(bs.NETWORKS), owner_deadline="2026-10-12T00:44:00Z",
                                 values_path="/nonexistent", up_real_dir=up)
        self.refused("REAL_DOWN_NEEDS_THE_UP_REAL_DIR", attempt, "DOWN", None)
        self.refused("REAL_UP_TAKES_NO_UP_REAL_DIR", attempt, "UP", str(self.base))
        self.assertFalse(os.path.lexists(str(self.base / "x-DOWN")) or os.path.lexists(str(self.base / "x-UP")))
        common = ["--layout", str(lots.LAYOUT), "--plans-dir", "/nonexistent", "--go", "/nonexistent", "--secrets-root",
                  bs.GEN_SECRETS_ROOT, "--network", "PROVIDER=bridge", "--network", "DATABASE=c3po_default",
                  "--network", "DATABASE_AND_PROVIDER=c3po_default", "--owner-deadline", "2026-10-12T00:44:00Z",
                  "--values", "/nonexistent"]
        code, text = lots.run_main(bs.main, ["write", "--out-dir", str(self.base / "y"), "--lot", "DOWN"] + common)
        self.assertEqual((code, json.loads(text)["code"]), (2, "REAL_DOWN_NEEDS_THE_UP_REAL_DIR"))
        code, text = lots.run_main(bs.main, ["validate", "--out-dir", str(self.base), "--layout", str(lots.LAYOUT),
                                             "--up-real-dir", str(self.base)])
        self.assertEqual((code, json.loads(text)["code"]), (2, "ARGUMENTS_INVALID"))

    def test_f1_down_of_the_up_plans_run_is_accepted_byte_identical(self):
        plans, go = self.plans_with("C")
        up = self.up_dir(plans, go)
        out, write = self.down(plans, go, up, "real-DOWN")
        result = write()
        self.assertEqual((result["status"], result["lot"], result["grid"]), ("REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY", "DOWN", "C"))
        cross = result["up_cross_check"]
        pairs = (("k9/K9_04_STEP_SET_REQUEST.json", "k9/K9_04_STEP_SET_REQUEST.json", "k9_request_sha256"),
                 ("k9/K9_GO_04.json", "k9/K9_GO_04.json", "go_sha256"), ("ext/k9_runner04.py", "ext/k9_runner04.py", "runner_sha256"),
                 ("cross_lot/capture_launch.json", "k9/capture_launch.json", "capture_launch_plan_sha256"))
        for up_rel, down_rel, field in pairs:
            raw = (up / up_rel).read_bytes()
            self.assertEqual(raw, (out / down_rel).read_bytes(), up_rel)
            self.assertEqual(cross[field], lots.sha(raw), field)
        self.assertEqual((cross["grid"], cross["byte_identical"], cross["up_real_dir"]), ("C", True, str(up)))
        self.assertEqual(cross["up_sha256sums_sha256"], lots.sha((up / "SHA256SUMS").read_bytes()))
        self.assertEqual(bs.check_real(str(up), str(lots.LAYOUT))["lot"], "UP")
        self.assertEqual(bs.check_real(str(out), str(lots.LAYOUT))["status"], "REAL_SPEC_DIR_VALID")
        spec = json.loads((up / "UP.SPEC.json").read_bytes())
        self.assertNotIn("cross_lot/capture_launch.json", spec["files"])                  # never bound into the UP lot

    def test_f1_another_grid_request_or_go_is_refused_before_any_write(self):
        plans, go = self.plans_with("C")
        up = self.up_dir(plans, go)
        cases = [("REAL_DOWN_GRID_NOT_THE_UP_ONE", self.plans_with("D")),
                 ("REAL_DOWN_K9_REQUEST_NOT_THE_UP_ONE", self.plans_with("C", act_b=b"TEST ONLY another act B\n")),
                 ("REAL_DOWN_K9_GO_NOT_THE_UP_ONE", self.plans_with("C", go=b'{"schema":"ANOTHER_TEST_ONLY_GO"}\n'))]
        for code, (p, g) in cases:
            with self.subTest(code=code):
                out, write = self.down(p, g, up, "d-" + code)
                error = self.refused(code, write)
                self.assertFalse(os.path.lexists(str(out)))
                if code == "REAL_DOWN_GRID_NOT_THE_UP_ONE":
                    self.assertEqual(error.detail, ["C", "D"])

    def test_f1_another_runner_capture_plan_or_up_dir_is_refused_before_any_write(self):
        plans, go = self.plans_with("C")
        up = self.up_dir(plans, go)

        def tampered(name, rel, change, resum=True):
            d = self.copy_dir(up, name)
            (d / rel).write_bytes(change((d / rel).read_bytes()))
            if resum:
                self.resum(d)
            return d
        runner = tampered("up-runner", "ext/k9_runner04.py", lambda b: b + b"\n# other runner bytes\n")
        capture = tampered("up-capture", "cross_lot/capture_launch.json", lambda b: b.replace(b'"PRIMARY"', b'"SPARE"'))
        unsealed = tampered("up-unsealed", "k9/K9_GO_04.json", lambda b: b, resum=False)
        (unsealed / "k9" / "extra.json").write_bytes(b"{}")
        moved = tampered("up-moved", "UP.SPEC.json", lambda b: b.replace(b'"2026-10-10T18:26:00Z"', b'"2026-10-10T15:03:00Z"'))
        down_dir, _ = self.down(plans, go, up, "real-DOWN-of-up")
        self.real("DOWN", out=down_dir, plans=plans, go=go, up_real_dir=up)
        for code, u in (("REAL_DOWN_RUNNER_NOT_THE_UP_ONE", runner), ("REAL_DOWN_CAPTURE_PLAN_NOT_THE_UP_ONE", capture),
                        ("REAL_DOWN_UP_DIR_INVALID", unsealed), ("REAL_DOWN_UP_DIR_INVALID", moved),
                        ("REAL_DOWN_UP_DIR_NOT_AN_UP_REAL_DIR", down_dir),
                        ("REAL_DOWN_UP_DIR_INVALID", self.base / "absent")):
            with self.subTest(code=code, up=u.name):
                out, write = self.down(plans, go, u, "d-%s-%s" % (code, u.name))
                error = self.refused(code, write)
                self.assertFalse(os.path.lexists(str(out)))
                if u is moved:
                    self.assertEqual(error.detail, "REAL_SLOT_START_WINDOW_NOT_ALLOWED")
                if u is unsealed:
                    self.assertEqual(error.detail, "REAL_DIR_FILE_SET_MISMATCH")

    def test_f1_validate_binds_the_up_capture_record_to_its_request_and_go(self):
        plans, go = self.plans_with("C")
        up = self.up_dir(plans, go)
        other, _ = self.plans_with("C", go=b'{"schema":"ANOTHER_TEST_ONLY_GO"}\n')
        swapped = self.copy_dir(up, "up-swapped")
        (swapped / "cross_lot" / "capture_launch.json").write_bytes((other / "plans" / "capture_launch.json").read_bytes())
        self.resum(swapped)
        self.refused("REAL_UP_CAPTURE_ANCHOR_INVALID", bs.check_real, str(swapped), str(lots.LAYOUT))
        missing = self.copy_dir(up, "up-missing")
        shutil.rmtree(str(missing / "cross_lot"))
        self.resum(missing)
        self.refused("REAL_UP_CAPTURE_ANCHOR_INVALID", bs.check_real, str(missing), str(lots.LAYOUT))

    def test_low6_validate_and_write_take_relative_dirs(self):
        plans, go = self.plans_with("D")
        up = self.up_dir(plans, go, "real-UP-D")
        spec = bs.build_down(plans=str(plans), go=str(go))
        values = self.write_values(self.values_for(spec), "values-DOWN-cli.json")
        here = os.getcwd()
        os.chdir(str(self.base))
        try:
            code, text = lots.run_main(bs.main, ["validate", "--out-dir", "real-UP-D", "--layout", str(lots.LAYOUT)])
            self.assertEqual((code, json.loads(text)["status"]), (0, "REAL_SPEC_DIR_VALID"), text)
            self.assertEqual(json.loads(text)["spec_sha256"], bs.check_real(str(up), str(lots.LAYOUT))["spec_sha256"])
            self.assertEqual(bs.check_real("real-UP-D", str(lots.LAYOUT))["status"], "REAL_SPEC_DIR_VALID")   # the review's probe
            self.refused("REAL_SPEC_DIR_NOT_A_DIRECTORY", bs.check_real, "absent-dir", str(lots.LAYOUT))
            for rel in ("absent-dir", "values-DOWN-cli.json"):
                code, text = lots.run_main(bs.main, ["validate", "--out-dir", rel, "--layout", str(lots.LAYOUT)])
                self.assertEqual((code, json.loads(text)["code"]), (2, "REAL_SPEC_DIR_NOT_A_DIRECTORY"), rel)
            argv = ["write", "--out-dir", "real-DOWN-D", "--lot", "DOWN", "--plans-dir", str(plans), "--go", str(go),
                    "--layout", str(lots.LAYOUT), "--secrets-root", bs.GEN_SECRETS_ROOT, "--network", "PROVIDER=bridge",
                    "--network", "DATABASE=c3po_default", "--network", "DATABASE_AND_PROVIDER=c3po_default",
                    "--owner-deadline", "2026-10-12T00:44:00Z", "--values", str(values), "--up-real-dir", "real-UP-D"]
            code, text = lots.run_main(bs.main, argv)
            self.assertEqual(code, 0, text)
            result = json.loads(text)
            self.assertEqual((result["status"], result["grid"], result["up_cross_check"]["up_real_dir"]),
                             ("REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY", "D", str(up)))
        finally:
            os.chdir(here)


def main():
    loader = unittest.TestLoader()
    tests = unittest.TestSuite()
    for case in (Mounts, ProofHarness, LotsReview):
        tests.addTests(loader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(tests)
    print(json.dumps({"schema": "L12HOST_V33_TEST_RESULT", "python": "%d.%d.%d" % sys.version_info[:3],
                      "platform": sys.platform, "tests": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "skipped": len(result.skipped), "ok": result.wasSuccessful(),
                      "temp_parent": dict(kit.TEMP_PARENT)}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
