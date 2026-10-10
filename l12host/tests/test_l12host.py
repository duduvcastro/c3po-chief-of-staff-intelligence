"""L12-HOST v3.2 suite (unit, end-to-end, mutation, crash/kill points, two-process contention). SYNTHETIC only.

Run: python -I -S -B tests/test_l12host.py   (one JSON summary on stdout, test names on stderr; exit 1 on failure)
"""
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402

rt, fx, inst, bind = kit.rt, kit.fx, kit.inst, kit.bind
DRIVER = str(Path(__file__).resolve().parent / "driver.py")
UP_SLOTS = ("P1", "P2", "P3", "P4")
X_SLOTS = ("X1", "X2", "X3", "X4", "X5", "X6", "X7")


def walk_bytes(root):
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            if not os.path.islink(path):
                try:
                    yield path, Path(path).read_bytes()
                except OSError:
                    pass


def with_prove_alternative(env):
    """prove gets a second alternative slot P1B (31 s after P1, same plan: the plan names the FIRST alternative); the
    later core slots are re-laid so a dependent never starts before the dependency's last alternative could have ended
    (LATE 60 + budget 90)."""
    def hook(spec):
        first = rt.stamp(spec["tasks"][0]["slots"][0]["at"])
        alternative = kit.allowed_after(first, 31)
        spec["tasks"][0]["slots"].append({"slot": "P1B", "at": kit.z(alternative)})
        at = alternative
        for task in spec["tasks"][1:]:
            at = kit.allowed_after(at, 155)
            task["slots"][0]["at"] = kit.z(at)
            op = kit.CORE_RUNNER[task["operation"]]
            env.k9_plan(op, at, task["budget_seconds"], core=task["operation"])
            row = env.k9_row(op, 25)
            task["effect"], task["decoder"] = row, env.k9_decoder(op, row)
    return hook


class Base(unittest.TestCase):
    def setUp(self):
        self.env = kit.Env()

    def tearDown(self):
        self.env.cleanup()

    def up(self, *, extended=True, run=UP_SLOTS, spec_hook=None, steps=None, ceilings=None):
        e = self.env
        e.prepare()
        spec = e.up_spec(extended=extended, ceilings=ceilings, **({"steps": steps} if steps else {}))
        if spec_hook:
            spec_hook(spec)
        e.install_spec(spec)
        e.up_fakes()
        out = {}
        for slot in run:
            code, res = e.run("UP", slot)
            self.assertEqual((code, res["status"]), (0, "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE"), res)
            out[slot] = res
        return out

    def up_all(self):
        out = self.up()
        for slot in X_SLOTS:
            code, res = self.env.run("UP", slot)
            self.assertEqual((code, res["status"]), (0, "EXTENDED_COMPLETE"), res)
            out[slot] = res
        return out

    def down(self, **kw):
        e = self.env
        spec = kit.down_spec(e, **kw)
        bound, result = kit.sign_down(e, spec)
        self.assertNotIn("code", result, result)
        kit.wait_until(e.down_t0 + timedelta(seconds=7))
        return spec

    def docker_runs(self, name):
        return [r for r in self.env.log("docker") if r["argv"][:1] == ["run"] and r["argv"][r["argv"].index("--name") + 1] == name]

    def unit_starts(self):
        return [r for r in self.env.log("systemd-run") if not any(w.startswith("--on-calendar") for w in r["argv"])]

    def diag(self, res):
        return res.get("diagnostics") or []

    def bind_refuses(self, spec, code, physical=False, prepared_at=None):
        e = self.env
        out = e.stage / ("lot-" + spec["lot"] + "-x%d" % time.monotonic_ns())
        path = e.base / ("spec-x%d.json" % time.monotonic_ns())
        path.write_text(json.dumps(spec))
        with self.assertRaisesRegex(rt.Hold, code):
            bind.lot(str(path), str(e.layout_path), str(e.runtime_path),
                     kit.z(prepared_at or (e.t_sign - timedelta(minutes=30))), str(out), physical=physical)

    def session_shell(self, *, capacity=True, image=None):
        """TEST ONLY: the Monday capacity chain and the C6 snapshot cannot accept on a 09/10 wall clock; the READY
        wait, the declared supervisor start, the veto, BEFORE_EFFECT, the reader start and the hold are under test."""
        e = self.env
        original = e.shell

        def patched(d, at, probe=None, minute_rule=False):
            shell = original(d, at, probe, minute_rule)
            g = shell.fam.ext.StepGates
            if capacity:
                e.patched.append((g, "capacity_chain", g.capacity_chain))
                g.capacity_chain = lambda self, task: "00" * 32
            e.patched.append((g, "image_phase", g.image_phase))
            g.image_phase = image or (lambda self, phase, task, ready_sha256=None: None)
            return shell
        e.shell = patched

    def session_world(self, **kw):
        self.up_all()
        e = self.env
        self.down(session=True, **kw)
        for slot in ("E6", "J1", "PO"):
            self.assertEqual(e.run("DOWN", slot)[0], 0)

    def ready(self, body=None):
        """A ready file present BEFORE the run: a leftover (v3.1: HOLD before the supervisor)."""
        self.env.ready_path.write_bytes(kit.canonical(body or {"epoch": kit.EPOCH, "session": kit.DAY}))

    def ready_on_supervisor(self, body=None):
        """The (fake) supervisor publishes ready.json when its unit starts (atomic rename), as the real producer."""
        self.env.update_fake(unit_writes={rt.SUPERVISOR_NAME: [{"path": str(self.env.ready_path), "content": kit.canonical(
            body or {"epoch": kit.EPOCH, "session": kit.DAY}).decode("ascii")}]})


# ====================================================================== end to end
class EndToEnd(Base):
    def test_up_core_chain_enters_only_through_outer_limiter_with_k9_abi(self):
        out = self.up()
        e = self.env
        for slot, res in out.items():
            outer = res["outer"]
            self.assertEqual(outer["schema"], "L12_OUTER_ATTEMPT_CANDIDATE_V1")
            self.assertEqual((outer["reservation_durable"], outer["recovery_required"], outer["worker_cleanup"]),
                             (True, False, "GROUP_KILL_ISSUED_WORKER_REAPED"))
            self.assertEqual(outer["inner_result"]["schema"], "L12_LOCAL_ATTEMPT_CANDIDATE_V1")
            self.assertEqual((res["effect_calls"], res["start_marker"], res["result_class"]), (1, "CREATED", "K9_STEP_COMPLETE"))
        claims = [r for r in e.ledger_rows() if r["kind"] == "CLAIM"]
        self.assertEqual(len(claims), 4)
        terminals = [r for r in e.ledger_rows() if r["kind"] == "TERMINAL"]
        self.assertEqual({t["data"]["status"] for t in terminals}, {"ORIGINAL_COMPLETE_OBSERVED_CANDIDATE"})
        run = self.docker_runs(rt.K9_CONTAINER_PREFIX + "collect-launch")[0]["argv"]
        for flag in ("--rm", "--read-only", "--init"):
            self.assertIn(flag, run)
        self.assertIn("c3po.l12.attempt=" + e.key("collect"), run)
        self.assertIn("C3PO_BUILD_SHA=" + kit.LIT["REVISION"], run)
        self.assertEqual(run[run.index("--network") + 1], "bridge")
        self.assertIn(rt.K9_TOOLS_TARGET + "/k9_runner04-%s.py" % kit.RUNNER_SHA, run)
        self.assertNotIn("--detach", run)
        self.assertEqual(run[run.index("timeout"):run.index("timeout") + 4], ["timeout", "-s", "KILL", "25"])
        commit = self.docker_runs(rt.K9_CONTAINER_PREFIX + "commit-launch")[0]["argv"]
        self.assertEqual(commit[commit.index("--network") + 1], "c3po_default")
        self.assertTrue(any(w.endswith("target=/c3po-k9-emitter,readonly") for w in commit))
        for path, raw in walk_bytes(e.layout["root"]):
            self.assertNotIn(kit.CANARY.encode(), raw, path)
            self.assertNotIn(kit.STDOUT_MARKER.encode(), raw, path)
        for raw in e.outputs:
            self.assertNotIn(kit.CANARY.encode(), raw)
            self.assertNotIn(kit.STDOUT_MARKER.encode(), raw)

    def test_up_runner_steps_run_under_the_closed_table_with_k9_ext_decoder(self):
        out = self.up_all()
        e = self.env
        self.assertEqual(out["X5"]["extended"]["ceiling_seconds"], 90)
        self.assertEqual(out["X5"]["result_class"], "K9_STEP_COMPLETE")
        for step in kit.STEP_RUNNER:
            key = e.xkey(step)
            for name in ("xclaim-" + key, "xterm-" + key):
                self.assertTrue((Path(e.layout["root"]) / "extended" / name).exists(), name)
        self.assertEqual(len([r for r in e.ledger_rows() if r["kind"] == "CLAIM"]), 4)   # extended never in core
        run = self.docker_runs(rt.K9_CONTAINER_PREFIX + "bind")[0]["argv"]
        self.assertEqual(run[run.index("--network") + 1], "none")

    def test_down_e6_j_alternatives_post_chain(self):
        self.up_all()
        e = self.env
        self.down(j_slots=("J1", "J2", "J3"))
        code, res = e.run("DOWN", "E6")
        self.assertEqual((code, res["status"], res["result_class"]), (0, "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE",
                                                                      "READBACK_ALL_MATCH"), res)
        code, res = e.run("DOWN", "J1")
        self.assertEqual((code, res["status"], res["result_class"]), (0, "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE",
                                                                      "J_PUBLISHED_VERIFIED"), res)
        self.assertTrue((Path(e.layout["root"]) / "receipts" / (e.key("admission_manifest") + ".process")).exists())
        for slot in ("J2", "J3"):
            code, res = e.run("DOWN", slot)
            self.assertEqual((code, res["status"], res["effect_calls"]), (3, "REFUSED_START_CONSUMED", 0), res)
        code, res = e.run("DOWN", "PO")
        self.assertEqual((code, res["status"], res["result_class"]), (0, "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE",
                                                                      "CHAIN_ALL_COMPLETE"), res)
        self.assertEqual(self.unit_starts(), [])

    def test_j4_registry_is_derived_and_checked_through_the_runtime(self):
        self.up_all()
        e = self.env
        spec = kit.down_spec(e)
        t0 = e.down_t0
        saved = rt.owner_time_guard
        rt.owner_time_guard = lambda *a, **k: None
        try:
            bound = e.make_lot(spec, prepared=t0, published=t0 + timedelta(seconds=1), signed=kit.fixture_signed_at(e),
                               bound_at=t0 + timedelta(seconds=4))
            kit.wait_until(t0 + timedelta(seconds=5))
            self.assertNotIn("code", e.install("DOWN", bound, at=datetime.now(timezone.utc)))
            good = kit.j4_registry(e)
            bad = json.loads(good)
            bad["programs"]["j_slot"]["sha256"] = "d4" * 32
            with self.assertRaisesRegex(rt.Hold, "PREVIEW_REFUSED_J4_REGISTRY_RECORD_NOT_LIVE|PREVIEW_REFUSED_J4_PROGRAM_PIN_CHANGED"):
                kit.install_j4_registry(e, kit.canonical(bad))
            bad = json.loads(good)
            bad["outer_scope"][-1] = "post"
            with self.assertRaisesRegex(rt.Hold, "PREVIEW_REFUSED_J4_REGISTRY_NOT_DERIVED"):
                kit.install_j4_registry(e, kit.canonical(bad))
            self.assertFalse(os.path.lexists(e.lot_dir("DOWN") + "/derived/" + rt.DERIVED_REGISTRY))
            self.assertEqual(kit.install_j4_registry(e, good)["readback"], "EQUAL")
        finally:
            rt.owner_time_guard = saved
        kit.wait_until(t0 + timedelta(seconds=7))
        self.assertEqual(e.run("DOWN", "E6")[0], 0)
        (e.base / "j4" / "j_slot.py").write_bytes(b"# changed\n")
        code, res = e.run("DOWN", "J1")
        self.assertEqual((code, res["effect_calls"], res["code"]), (2, 0, "J4_REGISTRY_RECORD_NOT_LIVE"), res)


# ====================================================================== B3: the single late reader start
class SessionStart(Base):
    def test_one_claim_supervisor_ready_recheck_reader_held(self):
        self.session_world(hold_seconds=45, ready_check=True)
        e = self.env
        code, res = e.run("DOWN", "R0")             # v3.1: the early read-only absence check
        self.assertEqual((code, res["status"], res["result_class"], res["effect_calls"]),
                         (0, "EXTENDED_COMPLETE", "READY_ABSENT_OBSERVED", 0), res)
        self.assertEqual(self.unit_starts(), [])
        self.ready_on_supervisor()
        self.session_shell()
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["status"], res["result_class"], res["effect_calls"]),
                         (0, "EXTENDED_COMPLETE", "SESSION_START_FIRST_CYCLE_HELD", 2), res)
        self.assertEqual(res["extended"]["pre_effect"]["marker"], "WRITTEN")
        self.assertTrue((Path(e.layout["root"]) / "extended" / ("xpre-" + e.xkey("session_start"))).exists())
        starts = self.unit_starts()
        self.assertEqual([w for r in starts for w in r["argv"] if w.startswith("--unit=")],
                         ["--unit=" + rt.SUPERVISOR_NAME, "--unit=" + rt.READER_NAME])
        for r in starts:
            self.assertIn("--property=Restart=no", r["argv"])
            self.assertFalse(any(w.startswith(("--property=OnFailure", "--property=RestartSec", "--property=StartLimit"))
                                 for w in r["argv"]))
        envelope = json.loads((Path(e.layout["root"]) / "receipts" / (e.xkey("session_start") + ".json")).read_bytes())
        import base64
        record = json.loads(base64.b64decode(envelope["original_b64"]))
        self.assertEqual((record["result_class"], record["operational_GO"]), ("SESSION_START_FIRST_CYCLE_HELD", False))
        reader = json.loads(base64.b64decode(record["reader_ack_b64"]))
        self.assertEqual((reader["launch_class"], reader["held"], reader["operational_complete"]),
                         ("SESSION_READER", True, False))
        self.assertGreaterEqual(rt.stamp(reader["observed_at"]), rt.stamp(record["hold_until"]))
        self.assertEqual((reader["supervisor"]["unit"], reader["supervisor"]["main_pid"],
                          reader["supervisor"]["running_through_hold"]), (rt.SUPERVISOR_NAME, "4242", True))
        self.assertGreaterEqual(reader["supervisor"]["polls"], reader["polls"])
        self.assertIn("READY_ABSENT_BEFORE_SUPERVISOR", record["gates"])

    def test_refuses_before_any_effect_without_the_capacity_chain(self):
        self.session_world()
        e = self.env
        self.ready_on_supervisor()
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["status"], res["effect_calls"]), (2, "EXTENDED_REFUSED_CONSUMED", 0), res)
        self.assertEqual(self.unit_starts(), [])

    def test_ready_absent_holds_after_the_supervisor_and_never_starts_the_reader(self):
        self.session_world(ready_wait=2)
        e = self.env
        self.session_shell()
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["status"], res["code"], res["effect_calls"], res["recovery_required"]),
                         (2, "EXTENDED_UNCERTAIN_CONSUMED", "READY_WAIT_DEADLINE", 1, True), res)
        self.assertEqual([w for r in self.unit_starts() for w in r["argv"] if w.startswith("--unit=")],
                         ["--unit=" + rt.SUPERVISOR_NAME])

    def test_ready_divergent_fails_at_once(self):
        self.session_world()
        e = self.env
        self.ready_on_supervisor({"epoch": kit.EPOCH, "session": "2026-10-13"})
        self.session_shell()
        started = time.monotonic()
        code, res = e.run("DOWN", "S1")
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual((res["code"], res["effect_calls"]), ("READY_WAIT_ORIGINAL_DIVERGENT", 1), res)
        self.assertEqual(len(self.unit_starts()), 1)

    def test_veto_after_ready_blocks_the_reader(self):
        self.session_world()
        e = self.env
        self.ready_on_supervisor()
        veto = e.veto

        def image(self_, phase, task, ready_sha256=None):
            if phase == "BEFORE_FIRST_READER":
                (veto / "STOP").write_text("x")
        self.session_shell(image=image)
        code, res = e.run("DOWN", "S1")
        self.assertEqual((res["status"], res["code"], res["effect_calls"]), ("EXTENDED_UNCERTAIN_CONSUMED", "VETO_PRESENT", 1), res)
        self.assertEqual(len(self.unit_starts()), 1)

    def test_ready_removed_before_the_reader_start_is_refused_by_the_engine(self):
        self.session_world()
        e = self.env
        self.ready_on_supervisor()
        path = e.ready_path

        def image(self_, phase, task, ready_sha256=None):
            if phase == "BEFORE_FIRST_READER":
                path.unlink()
        self.session_shell(image=image)
        code, res = e.run("DOWN", "S1")
        self.assertEqual((res["code"], res["effect_calls"]), ("READY_NOT_PRESENT_AT_READER_START", 1), res)
        self.assertEqual(len(self.unit_starts()), 1)

    def test_no_reader_or_unit_start_anywhere_else(self):
        import l12host_decode as dec
        e = self.env
        for op in ("reader_bound", "reader_cycle", "policy_read", "capture_launch", "capture_result"):
            with self.assertRaisesRegex(dec.DecodeHold, "OPERATION_OR_DECODER_NOT_EXPRESSIBLE_V3"):
                dec.validate_decoder_row({"kind": "EXTERNAL_V1", "decoder": "a", "verifier": "b"}, op, "CONTAINER",
                                         external={"a", "b"})
        with self.assertRaisesRegex(dec.DecodeHold, "DECODER_NOT_ALLOWED_FOR_EXTENDED_STEP"):
            dec.validate_decoder_row({"kind": "SESSION_START_V3", "verifier": "b"}, "components", "CONTAINER",
                                     extended=True, step_kind="RUNNER", external={"b"})
        row, _, _ = kit.reader_row(e)
        lot = e.mk("lots/UP")
        authority = kit.canonical({"layout": e.layout, "effects": {"prove": row}, "extended": None})
        runtime = kit.canonical({"executor_uid": os.geteuid(), "election": {"veto_chain": [[str(e.veto), [0, 0, 0, 0, 0]]]}})
        request = kit.canonical({"authority_sha256": kit.sha(authority), "runtime_sha256": kit.sha(runtime),
                                 "epoch": kit.EPOCH, "session": kit.DAY, "previous_session": kit.PREVIOUS, "track": "P"})
        for name, raw in (("authority.json", authority), ("request.json", request), ("runtime.json", runtime)):
            (lot / name).write_bytes(raw)
        key = kit.sha(kit.canonical([kit.EPOCH, kit.DAY, kit.PREVIOUS, "P", "prove"]))
        argv = fx.engine_argv(str(lot), "CORE", "prove", kit.sha(authority), kit.sha(request), key, "d" * 64,
                              "2026-10-12T13:29:10Z", None)
        self.assertEqual(len(argv), 20)
        code, out = fx.run(argv)
        self.assertEqual((code, out["status"], out["code"]), (2, "REFUSED", "UNIT_START_OUTSIDE_SESSION_START"))
        self.assertEqual(self.unit_starts(), [])
        swapped = json.loads(json.dumps(row))
        swapped["launch_class"] = "PRE_OPEN_READER"
        with self.assertRaises(fx.Hold):
            fx.validate_row(swapped, e.layout)

    def test_ready_still_present_is_exact(self):
        e = self.env
        path = e.base / "ready.json"
        path.write_bytes(b'{"epoch":"x"}')
        fx.ready_still_present(str(path), kit.sha(b'{"epoch":"x"}'), os.geteuid())
        with self.assertRaisesRegex(fx.Hold, "READY_CHANGED_BEFORE_READER_START"):
            fx.ready_still_present(str(path), "ab" * 32, os.geteuid())
        with self.assertRaisesRegex(fx.Hold, "READY_NOT_VERIFIED_BEFORE_READER"):
            fx.ready_still_present(str(path), None, os.geteuid())
        path.unlink()
        with self.assertRaisesRegex(fx.Hold, "READY_NOT_PRESENT_AT_READER_START"):
            fx.ready_still_present(str(path), "ab" * 32, os.geteuid())


# ====================================================================== Monday lanes (wired, fail closed on this clock)
class MondayLanes(Base):
    def test_bootstrap_lane_installs_with_image_go_and_consumes_without_effect_off_monday(self):
        e = self.env
        e.prepare()
        spec, result = kit.monday_lot(e, "BOOT", "BOOTSTRAP_MONDAY", ("install_release", "readback", "activate"))
        self.assertNotIn("code", result, result)
        code, res = e.run("BOOT", "M1", at=kit.MONDAY)
        self.assertEqual((code, res["effect_calls"], res["outer"]["worker_cleanup"]), (2, None, "NOT_STARTED"), res)
        self.assertEqual(res["outer"]["status"], "UNCERTAIN_CONSUMED")
        self.assertEqual(res["outer"]["code"], "OUTER_DEADLINE_OR_WINDOW")
        self.assertTrue(res["outer"]["reservation_durable"])

    def test_capacity_chain_goes_for_the_actual_m3_original(self):
        self.up_all()
        e = self.env
        cap = kit.capacity_section(e)
        saved = inst.cross_lot_check
        inst.cross_lot_check = lambda lots: None       # TEST ONLY: Monday BOOT/CAP beside a today DOWN (S2 has its own test)
        try:
            _, r1 = kit.monday_lot(e, "BOOT", "BOOTSTRAP_MONDAY", ("install_release", "readback", "activate"), capacity=cap)
            _, r2 = kit.monday_lot(e, "CAP", "CAPACITY_MONDAY", ("capacity_activate",), capacity=cap,
                                   base=kit.MONDAY + timedelta(hours=2))
            self.assertNotIn("code", r1, r1)
            self.assertNotIn("code", r2, r2)
            self.down(session=True, capacity=cap)
        finally:
            inst.cross_lot_check = saved
        for slot in ("E6", "J1", "PO"):
            self.assertEqual(e.run("DOWN", slot)[0], 0)
        self.ready_on_supervisor()
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["effect_calls"], res["code"]), (2, 0, "INPUT_FILE_UNAVAILABLE"), res)
        self.assertEqual(self.unit_starts(), [])

    def test_s4_capacity_source_is_the_producing_lot_effect_source(self):
        self.up_all()
        e = self.env
        self.down()
        shell = rt.Shell(e.lot_dir("DOWN"), probe=e.probe, physical=False)
        gates = shell.fam.ext.Gates(shell)
        j_source = shell.authority["files"]["ext/fx_j_program.py"]
        self.assertEqual(gates.effect_source_sha256(shell.view, "admission_manifest"), j_source)
        with self.assertRaisesRegex(rt.Hold, "CAPACITY_PRODUCER_SOURCE_UNSIGNED"):
            gates.effect_source_sha256(shell.view, "post")


# ====================================================================== Codex #429 6085870117 (carried from v2)
class Corrections(Base):
    def test_c1_direct_core_run_is_never_called(self):
        e = self.env
        e.prepare()
        e.install_spec(e.up_spec(extended=False))
        e.up_fakes()
        original = e.shell

        def poisoned(d, at, probe=None, minute_rule=False):
            shell = original(d, at, probe, minute_rule)

            def boom(*a, **k):
                raise AssertionError("FiniteBatch.run must not be called")
            e.patched.append((shell.fam.fb.FiniteBatch, "run", shell.fam.fb.FiniteBatch.run))
            shell.fam.fb.FiniteBatch.run = boom
            return shell
        e.shell = poisoned
        code, res = e.run("UP", "P1")
        self.assertEqual((code, res["status"]), (0, "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE"), res)

    def test_c1_busy_lock_keeps_classification_and_burns_the_alternative(self):
        e = self.env
        self.up(extended=False, run=(), spec_hook=with_prove_alternative(e))
        fd = os.open(e.layout["root"] + "/ledger/" + rt.LEDGER_FILE, os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            code, res = e.run("UP", "P1")
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        outer = res["outer"]
        self.assertEqual((code, outer["status"], outer["refusal_class"], outer["consumption_state"], outer["effect_calls"]),
                         (2, "REFUSED_NOT_RESERVED", "LOCK_BUSY", "NOT_RESERVED", 0), res)
        code, res = e.run("UP", "P1B")
        self.assertEqual((code, res["status"]), (3, "REFUSED_START_CONSUMED"), res)
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "prove-launch"), [])

    def test_c2_no_skip_a_complete_operation_is_never_rerun_or_skipped(self):
        self.up(run=("P1",))
        code, res = self.env.run("UP", "P1")
        self.assertEqual((code, res["status"], res["result_file"]), (3, "REFUSED_START_CONSUMED", "PRESENT"), res)
        self.assertNotIn("SKIP", json.dumps(res))
        self.assertEqual(len(self.docker_runs(rt.K9_CONTAINER_PREFIX + "prove-launch")), 1)

    def test_c2_torn_ledger_is_a_hold_and_is_never_truncated(self):
        self.up(run=("P1",))
        e = self.env
        path = Path(e.layout["root"]) / "ledger" / rt.LEDGER_FILE
        with open(path, "ab") as f:
            f.write(b'{"schema":"L12_LOCAL_ATTEMPT_LEDGER_CANDIDATE_V1","seq')
        before = path.read_bytes()
        code, res = e.run("UP", "P2")
        self.assertEqual(code, 2)
        self.assertEqual((res["outer"]["code"], res["outer"]["effect_calls"], res["outer"]["recovery_required"]),
                         ("LEDGER_PARTIAL_OR_FULL", 0, True), res)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "collect-launch"), [])

    def test_c2_torn_dependency_envelope_is_a_hold(self):
        self.up(run=("P1",))
        e = self.env
        path = Path(e.layout["root"]) / "receipts" / (e.key("prove") + ".json")
        os.chmod(path, 0o600)
        with open(path, "ab") as f:
            f.write(b" ")
        code, res = e.run("UP", "P2")
        self.assertEqual((code, res["effect_calls"]), (2, 0), res)
        self.assertIn(res["code"], ("DOCUMENT_NOT_CANONICAL", "DOCUMENT_JSON_INVALID"), res)
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "collect-launch"), [])

    def test_c2_crash_after_start_marker_leaves_a_consumed_option_and_no_claim(self):
        e = self.env
        self.up(extended=False, run=(), spec_hook=with_prove_alternative(e))
        p = subprocess.run([kit.PY, "-I", "-S", "-B", DRIVER, "run", e.lot_dir("UP"), "P1", kit.z(e.slot_at("UP", "P1")),
                            "--crash-after-start"], capture_output=True, timeout=60)
        self.assertEqual(p.returncode, 9)
        self.assertTrue((Path(e.layout["root"]) / "starts" / ("start-" + e.key("prove"))).exists())
        self.assertEqual(e.ledger_raw(), b"")
        code, res = e.run("UP", "P1B")
        self.assertEqual((code, res["status"]), (3, "REFUSED_START_CONSUMED"), res)
        code, res = e.run("UP", "P2")
        self.assertEqual((code, res["effect_calls"]), (2, 0), res)

    def test_c3_k9_original_is_decoded_status_label_is_not_evidence(self):
        self.up(run=("P1",))
        e = self.env
        e.update_fake(**{rt.K9_CONTAINER_PREFIX + "collect-launch": {"writes": [
            {"path": str(e.receipts / "collect_launch.RECEIPT.json"),
             "content": e.k9_receipt_content("collect_launch", attempt_key="99" * 32)}]}})
        code, res = e.run("UP", "P2")
        self.assertEqual(code, 2)
        self.assertNotEqual(res["status"], "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE")
        self.assertIn("K9_ORIGINAL_NOT_EXACT_COMPLETE", self.diag(res), res)
        self.assertFalse((Path(e.layout["root"]) / "receipts" / (e.key("collect") + ".json")).exists())

    def test_c3_prove_receipt_must_be_the_actual_presence_complete(self):
        e = self.env
        self.up(run=())
        bad = json.loads(e.k9_receipt_content("prove_launch"))
        bad["counts"]["present_symbols"] = 4000          # 80 %: below the 95 % rule of the compiled PRESENCE
        bad["counts"]["absent_symbols"] = 1000
        e.update_fake(**{rt.K9_CONTAINER_PREFIX + "prove-launch": {"writes": [
            {"path": str(e.receipts / "prove_launch.RECEIPT.json"), "content": kit.canonical(bad).decode()}]}})
        code, res = e.run("UP", "P1")
        self.assertEqual(code, 2)
        self.assertIn("K9_PROVE_ACTUAL_COMPLETE_REQUIRED", self.diag(res), res)

    def test_c3_import_needs_the_source_lot_bound_and_its_ledger_terminal(self):
        self.up_all()
        e = self.env
        spec = kit.down_spec(e)
        for row in spec["imports"].values():
            row["bound_sha256"] = "12" * 32
        kit.sign_down(e, spec)
        kit.wait_until(e.down_t0 + timedelta(seconds=7))
        code, res = e.run("DOWN", "E6")
        self.assertEqual((code, res["effect_calls"], res["code"]), (2, 0, "IMPORT_SOURCE_LOT_UNBOUND"), res)

    def test_c4_veto_created_after_verify_is_seen_at_before_effect(self):
        self.up(run=("P1",))
        e = self.env
        veto = e.veto
        code, res = e.run("UP", "P2", probe=kit.FakeProbe(on_runner_worker=lambda: (veto / "VETO").write_text("x")))
        self.assertEqual(code, 2)
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "collect-launch"), [])
        self.assertIn("VETO_PRESENT_BEFORE_EFFECT", self.diag(res), res)

    def test_c4_the_same_allow_is_never_renewed(self):
        e = self.env

        def hook(spec):
            spec["veto_max_age_seconds"] = 5

        def outer(n):
            if n == 3:
                time.sleep(0.8)
        self.up(run=("P1",), spec_hook=hook)
        probe = kit.FakeProbe(on_runner_worker=lambda: time.sleep(4.6), on_outer_call=outer)
        code, res = e.run("UP", "P2", probe=probe)
        self.assertEqual(code, 2)
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "collect-launch"), [])
        self.assertIn("VETO_ALLOW_EXPIRED_BEFORE_EFFECT", self.diag(res), res)

    def test_c4_engine_rechecks_folder_and_allow_at_transport(self):
        e = self.env
        info = os.lstat(e.veto)
        identity = [info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode & 0o7777]
        now = datetime.now(timezone.utc)
        fx.before_effect(str(e.veto), identity, now + timedelta(seconds=5), minute=False)
        with self.assertRaisesRegex(fx.Hold, "VETO_ALLOW_EXPIRED_BEFORE_EFFECT"):
            fx.before_effect(str(e.veto), identity, now - timedelta(seconds=1), minute=False)
        with self.assertRaisesRegex(fx.Hold, "VETO_DIRECTORY_CHANGED_BEFORE_EFFECT"):
            fx.before_effect(str(e.veto), identity[:1] + [identity[1] + 1] + identity[2:], now + timedelta(seconds=5),
                             minute=False)
        (e.veto / "STOP").write_text("x")
        with self.assertRaisesRegex(fx.Hold, "VETO_PRESENT_BEFORE_EFFECT"):
            fx.before_effect(str(e.veto), identity, now + timedelta(seconds=5), minute=False)


# ====================================================================== v2 adversarial NO-GO: blockers and should-fix
class Blockers(Base):
    def test_b1_boot_id_reader_ignores_the_procfs_size_zero(self):
        e = self.env
        path = e.base / "boot_id"
        raw = b"0f1e2d3c-4b5a-4968-8776-655443322110\n"
        path.write_bytes(raw)
        real_fstat = os.fstat

        class Zero:
            def __init__(self, info):
                self.info = info

            def __getattr__(self, name):
                return 0 if name == "st_size" else getattr(self.info, name)
        rt.os.fstat = lambda fd: Zero(real_fstat(fd))
        try:
            self.assertEqual(rt.read_boot_id(str(path), owner_uid=os.geteuid(), require_procfs=False), raw)
            with self.assertRaisesRegex(rt.Refusal, "INPUT_FILE_INVALID|INPUT_FILE_CHANGED"):
                fd = os.open(str(e.base), os.O_RDONLY | os.O_DIRECTORY)
                try:
                    rt.read_at(fd, "boot_id", 128)
                finally:
                    os.close(fd)
        finally:
            rt.os.fstat = real_fstat
        for bad in (b"0F1E2D3C-4B5A-4968-8776-655443322110\n", raw[:-1], raw + b"x", b"x" * 129):
            path.write_bytes(bad)
            with self.assertRaises(rt.Refusal):
                rt.read_boot_id(str(path), owner_uid=os.geteuid(), require_procfs=False)
        path.write_bytes(raw)
        with self.assertRaisesRegex(rt.Refusal, "BOOT_ID_NOT_REGULAR_ROOT"):
            rt.read_boot_id(str(path), owner_uid=os.geteuid() + 1, require_procfs=False)
        if sys.platform != "linux":
            with self.assertRaisesRegex(rt.Refusal, "BOOT_ID_PROCFS_UNAVAILABLE"):
                rt.read_boot_id()

    @unittest.skipUnless(sys.platform == "linux", "Linux procfs only")
    def test_b1_boot_id_on_real_linux_procfs(self):
        raw = rt.HostProbe().boot_id()
        self.assertRegex(raw.decode("ascii"), r"\A[0-9a-f-]{36}\n\Z")
        self.assertEqual(rt.read_boot_id(), raw)
        self.assertTrue(rt.proc_is_procfs())
        with self.assertRaisesRegex(rt.Refusal, "INPUT_FILE_CHANGED|INPUT_FILE_EMPTY"):
            rt.read_path(rt.BOOT_ID_PATH, 128)        # the v2 generic reader: what B1 found

    def test_b2_installer_judges_the_host_only_through_the_installed_runtime(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(extended=False)
        bound = e.signed_lot(spec)
        seen = []

        def spy(command, argv):
            seen.append(argv)
            return inst.run_preview(argv)          # the REAL subprocess of the INSTALLED runtime (physical)
        result = None
        with self.assertRaisesRegex(rt.Hold, "PREVIEW_REFUSED_RUNTIME_NOT_INSTALLED_COPY"):
            result = e.install("UP", bound, preview=spy)
        self.assertIsNone(result)
        self.assertEqual(seen[0][:6], [e.layout["python"], "-I", "-S", "-B",
                                       e.layout["root"] + "/src/l12host_runtime.py", "preview-stage"])
        self.assertFalse(os.path.lexists(e.lot_dir("UP")))
        self.assertEqual(e.timers, [])
        with self.assertRaisesRegex(rt.Hold, "PREVIEW_OUTPUT_FRAMING"):
            inst.run_preview([kit.PY, "-I", "-c", "print('a'); print('b')"])

    def test_b2_refusal_after_the_copy_is_a_hold_without_timers(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(extended=False)
        bound = e.signed_lot(spec)

        def preview(command, argv):
            if command == "preview":
                return 3, kit.canonical(rt.preview_record("preview", "PREVIEW_REFUSED", "BOOT_CHANGED"))
            return e.preview(command, argv)
        result = e.install("UP", bound, preview=preview)
        self.assertEqual((result["code"], result["preview_stage"], result["preview"], result["detail"], result["timers"]),
                         ("PREVIEW_AFTER_COPY_HOLD", "PASS", "REFUSED", "PREVIEW_REFUSED_BOOT_CHANGED", []))
        self.assertTrue(os.path.lexists(e.lot_dir("UP")))
        self.assertEqual(e.timers, [])

    def test_b4_unit_copies_never_restart(self):
        e = self.env
        row, dropped, changed = kit.reader_row(e)
        self.assertEqual(sorted(dropped), sorted(["OnFailure", "RestartSec", "RestartPreventExitStatus",
                                                  "StartLimitIntervalSec", "StartLimitBurst"]))
        self.assertEqual(changed, [["Restart", "on-failure", "no"]])
        self.assertEqual([p for p in row["unit"]["properties"] if p[0] == "Restart"], [["Restart", "no"]])
        fx.validate_row(row, e.layout)
        sup, dropped, changed = kit.supervisor_row(e)
        self.assertEqual(changed, [["Restart", "on-failure", "no"]])
        fx.validate_row(sup, e.layout)
        for prop in (["Restart", "on-failure"], ["Restart", "always"], ["RestartSec", "5s"], ["StartLimitBurst", "40"],
                     ["RestartPreventExitStatus", "78"], ["OnFailure", "x.service"]):
            with self.subTest(prop):
                bad = json.loads(json.dumps(row))
                bad["unit"]["properties"] = [p for p in bad["unit"]["properties"] if p[0] != "Restart"] + [prop]
                if prop[0] != "Restart":
                    bad["unit"]["properties"].append(["Restart", "no"])
                with self.assertRaises(fx.Hold):
                    fx.validate_row(bad, e.layout)
        self.assertTrue(fx.running_once({"LoadState": "loaded", "ActiveState": "active", "SubState": "running",
                                         "NRestarts": "0", "Restart": "no", "MainPID": "9"}))
        self.assertFalse(fx.running_once({"LoadState": "loaded", "ActiveState": "active", "SubState": "running",
                                          "NRestarts": "0", "Restart": "on-failure", "MainPID": "9"}))

    def test_b4_unit_grammar_holes_are_closed(self):
        e = self.env
        row, _, _ = kit.reader_row(e)
        docker = e.layout["binaries"]["docker"]

        def exec_mut(fn):
            bad = json.loads(json.dumps(row))
            fn(bad["unit"]["exec"])
            return bad
        image_at = lambda w: [i for i, x in enumerate(w) if x.startswith("sha256:")][0]

        def drop_network(w):
            i = w.index("--network")
            del w[i:i + 2]
        cases = {
            "pid_equals": lambda w: w.insert(2, "--pid=host"),
            "privileged": lambda w: w.insert(2, "--privileged"),
            "cap_add": lambda w: w.__setitem__(slice(2, 2), ["--cap-add", "SYS_ADMIN"]),
            "docker_sock": lambda w: w.__setitem__(slice(2, 2), ["--mount", "type=bind,source=/var/run/docker.sock,target=/s"]),
            "root_mount": lambda w: w.__setitem__(slice(2, 2), ["--mount", "type=bind,source=/,target=/host"]),
            "net_host": lambda w: w.__setitem__(w.index("--network") + 1, "host"),
            "net_bridge": lambda w: w.__setitem__(w.index("--network") + 1, "bridge"),
            "net_container": lambda w: w.__setitem__(w.index("--network") + 1, "container:c3po-r2d2-worker-1"),
            "no_network": drop_network,
            "detach": lambda w: w.insert(2, "--detach"),
            "inline_secret": lambda w: w.insert(2, "--env=C3PO_EODHD_API_TOKEN=x"),
            "no_rm": lambda w: w.remove("--rm"),
            "shell_command": lambda w: w.__setitem__(image_at(w) + 1, "sh"),
            "veto_rw": lambda w: w.__setitem__(slice(2, 2), ["--mount", "type=bind,source=%s,target=/v" % e.veto]),
        }
        for name, fn in cases.items():
            with self.subTest(name):
                with self.assertRaises(fx.Hold):
                    fx.validate_row(exec_mut(fn), e.layout)
        for name, prop in {"prune": ["ExecStartPre", docker + " image prune -a"],
                           "stop_other": ["ExecStop", "-" + docker + " stop -t 25 c3po-r2d2-worker-1"],
                           "killmode_none": ["KillMode", "none"],
                           "env_secret": ["Environment", "C3PO_DATABASE_URL=x"]}.items():
            with self.subTest(name):
                bad = json.loads(json.dumps(row))
                bad["unit"]["properties"].append(prop)
                with self.assertRaises(fx.Hold):
                    fx.validate_row(bad, e.layout)


class ShouldFix(Base):
    def test_s1_extended_table_is_closed(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(steps=("components", "sources"))
        bad = json.loads(json.dumps(spec))
        bad["extended"]["steps"][0]["step"] = "anything"
        self.bind_refuses(bad, "EXTENDED_STEP_NOT_IN_CLOSED_TABLE")
        bad = json.loads(json.dumps(spec))
        bad["extended"]["steps"][1]["requires"] = [["core", "publish_launch"]]
        self.bind_refuses(bad, "EXTENDED_REQUIRES_NOT_THE_CHAIN")
        bad = json.loads(json.dumps(spec))
        bad["extended"]["steps"][0]["effect"]["docker"]["command"] = ["python", "-m", "app.anything", "publish"]
        self.bind_refuses(bad, "K9_COMMAND_NOT_FIXED_SHAPE")
        bad = json.loads(json.dumps(spec))
        cmd = bad["extended"]["steps"][0]["effect"]["docker"]["command"]
        cmd[2] = rt.K9_TOOLS_TARGET + "/k9_runner04-%s.py" % kit.RUNNER_SHA[:16]
        self.bind_refuses(bad, "K9_COMMAND_NOT_FIXED_SHAPE")
        bad = json.loads(json.dumps(spec))
        bad["extended"]["steps"][0]["decoder"] = {"kind": "EXTERNAL_V1", "decoder": "fx_decode", "verifier": "ok"}
        self.bind_refuses(bad, "DECODER_NOT_ALLOWED_FOR_EXTENDED_STEP")
        bad = json.loads(json.dumps(spec))
        bad["extended"]["steps"] = bad["extended"]["steps"][1:]
        self.bind_refuses(bad, "EXTENDED_REQUIRES_NOT_DECLARED")
        bad = json.loads(json.dumps(spec))
        bad["extended"]["steps"][0]["step"] = "session_start"
        self.bind_refuses(bad, "EXTENDED_STEP_NOT_IN_CLOSED_TABLE")

    def test_s2_cross_lot_order_is_refused_before_any_write(self):
        def Z(s):
            return s

        def lot(lane, tasks, slots, steps=None, effects=None):
            return ({"slots": slots, "extended": {"steps": steps} if steps else None, "effects": effects or {}},
                    {"lane": lane, "tasks": tasks})

        def task(op, nb, na, budget):
            return {"operation": op, "not_before": nb, "not_after": na, "budget_seconds": budget}

        def slot(name, at, target, kind="CORE"):
            return {"slot": name, "at": at, "target_kind": kind, "target": target}
        up = lot("UPSTREAM_P", [task("publish_launch", "2026-10-10T15:02:30Z", "2026-10-10T15:13:00Z", 600)],
                 [slot("P4", "2026-10-10T15:03:00Z", "publish_launch"), slot("X7", "2026-10-11T02:26:00Z", "stage", "EXTENDED")],
                 steps=[{"step": "stage", "not_before": "2026-10-11T02:25:30Z", "not_after": "2026-10-11T02:28:00Z",
                         "ceiling_seconds": 120}])
        boot = lot("BOOTSTRAP_MONDAY", [task("activate", "2026-10-12T09:47:30Z", "2026-10-12T09:58:00Z", 300)],
                   [slot("M3", "2026-10-12T09:48:00Z", "activate")])
        down_slots = [slot("E6", "2026-10-12T09:01:00Z", "e6"), slot("PO", "2026-10-12T09:02:00Z", "post"),
                      slot("J1", "2026-10-12T10:38:00Z", "admission_manifest"),
                      slot("J2", "2026-10-12T10:41:00Z", "admission_manifest"),
                      slot("S1", "2026-10-12T13:29:02Z", "session_start", "EXTENDED")]
        down_tasks = [task("e6", "2026-10-12T09:00:30Z", "2026-10-12T09:02:00Z", 60),
                      task("post", "2026-10-12T09:01:30Z", "2026-10-12T09:03:00Z", 60),
                      task("admission_manifest", "2026-10-12T10:37:30Z", "2026-10-12T11:00:00Z", 120)]
        down_steps = [{"step": "session_start", "not_before": "2026-10-12T13:28:30Z", "not_after": "2026-10-12T13:36:30Z",
                       "ceiling_seconds": 420}]
        down = lot("DOWNSTREAM_AFTER_E6", down_tasks, down_slots, down_steps, {"post": {"source_lot": "UP"}})
        cap = lot("CAPACITY_MONDAY", [task("capacity_activate", "2026-10-12T10:45:30Z", "2026-10-12T11:05:00Z", 300)],
                  [slot("C1", "2026-10-12T10:46:00Z", "capacity_activate")])
        inst.cross_lot_check({"UP": up, "BOOT": boot, "DOWN": down, "CAP": cap})
        bad = json.loads(json.dumps(cap))
        bad[0]["slots"][0]["at"] = "2026-10-12T10:44:10Z"
        with self.assertRaisesRegex(rt.Hold, "CAPACITY_BEFORE_J_END|SLOT_INSIDE_J_EXCLUSION_WINDOW"):
            inst.cross_lot_check({"UP": up, "BOOT": boot, "DOWN": down, "CAP": bad})
        bad = json.loads(json.dumps(down))
        bad[0]["slots"][-1]["at"] = "2026-10-12T10:52:00Z"
        bad[0]["extended"]["steps"][0]["not_before"] = "2026-10-12T10:50:00Z"
        with self.assertRaisesRegex(rt.Hold, "READER_OR_CAPTURE_BEFORE_CAPACITY_END"):
            inst.cross_lot_check({"UP": up, "BOOT": boot, "DOWN": bad, "CAP": cap})
        late_up = json.loads(json.dumps(up))
        late_up[0]["slots"][1]["at"] = "2026-10-12T09:00:30Z"
        late_up[0]["extended"]["steps"][0].update(not_before="2026-10-12T09:00:00Z", not_after="2026-10-12T09:03:00Z")
        with self.assertRaisesRegex(rt.Hold, "POST_BEFORE_UP_CHAIN_END|SLOTS_TOO_CLOSE_ACROSS_LOTS"):
            inst.cross_lot_check({"UP": late_up, "DOWN": down})
        bad = json.loads(json.dumps(boot))
        bad[0]["slots"][0]["at"] = "2026-10-12T10:36:00Z"
        bad[1]["tasks"][0].update(not_before="2026-10-12T10:35:30Z", not_after="2026-10-12T10:45:00Z")
        with self.assertRaisesRegex(rt.Hold, "J_BEFORE_M3_END|SLOT_INSIDE_J_EXCLUSION_WINDOW"):
            inst.cross_lot_check({"BOOT": bad, "DOWN": down})
        bad = json.loads(json.dumps(down))
        bad[0]["slots"][1]["at"] = "2026-10-12T10:39:00Z"
        bad[1]["tasks"][1].update(not_before="2026-10-12T10:38:30Z", not_after="2026-10-12T10:42:00Z")
        with self.assertRaisesRegex(rt.Hold, "SLOT_INSIDE_J_EXCLUSION_WINDOW"):
            inst.cross_lot_check({"DOWN": bad})
        with self.assertRaisesRegex(rt.Hold, "SLOTS_TOO_CLOSE_ACROSS_LOTS"):
            inst.cross_lot_check({"BOOT": boot, "X": lot("CAPACITY_MONDAY", [task("capacity_activate", "2026-10-12T09:47:00Z",
                                                                                   "2026-10-12T09:59:00Z", 60)],
                                                         [slot("C1", "2026-10-12T09:48:10Z", "capacity_activate")])})

    def test_s3_mount_policy_denylist_and_epoch04_allowlist(self):
        e = self.env
        layout = dict(e.layout, root="/var/lib/c3po-l12host-e04", veto_dir=rt.EPOCH04_VETO_DIR)
        for path, ro in (("/var/lib/containerd", True), ("/var/lib/postgresql/16", True), ("/etc/shadow", True),
                         ("/var/lib/docker/volumes", True), ("/var/lib/c3po-l12host-e04/ledger", True),
                         (rt.EPOCH04_VETO_DIR, False), ("/etc/c3po-reader-e04/launcher", False)):
            with self.subTest(path):
                with self.assertRaises(fx.Hold):
                    fx.mount_source_policy(path, ro, layout)
        fx.mount_source_policy(rt.EPOCH04_VETO_DIR, True, layout)
        for path, ro, code in (("/srv/anything", True, "MOUNT_SOURCE_NOT_ALLOWLISTED"),
                               ("/var/lib/c3po/other", False, "MOUNT_SOURCE_NOT_ALLOWLISTED"),
                               (rt.EPOCH03_SECRETS_ROOT + "/emitter", False, "EPOCH03_K9_ROOT_FORBIDDEN"),
                               (rt.EPOCH04_K9_ROOT + "/secrets/emitter", False, "MOUNT_SECRETS_WRITABLE_FORBIDDEN"),
                               ("/var/lib/c3po/r2d2-v2-k9-20261005/days", True, "EPOCH03_K9_ROOT_FORBIDDEN"),
                               ("/mnt/day-d-data/x", False, "DAY_D_DATA_WRITE_FORBIDDEN"),
                               ("/var/lib/c3po-bar/journal", True, "EPOCH03_JOURNAL_ROOT_FORBIDDEN"),
                               (rt.EPOCH04_VETO_DIR, False, "MOUNT_VETO_WRITABLE_FORBIDDEN"),
                               ("/var/lib/c3po-l12host-e04/ledger", True, "MOUNT_L12_ROOT_FORBIDDEN")):
            with self.subTest(path):
                self.assertEqual(rt.epoch04_mount_violation(path, ro, layout), code)
        for path, ro in ((rt.EPOCH03_SECRETS_ROOT + "/emitter", True), (rt.EPOCH04_K9_DAY, False),
                         (rt.EPOCH04_K9_TOOLS, True), (rt.EPOCH04_SOURCE_ROOT, False), (rt.EPOCH04_JOURNAL_ROOT, False),
                         ("/mnt/day-d-data/x", True), (rt.EPOCH04_READER_CONFIG + "/launcher", True)):
            with self.subTest(path):
                self.assertIsNone(rt.epoch04_mount_violation(path, ro, layout))

    def test_s5_j4_finite_batch_must_pin_the_ledger_core(self):
        self.up_all()
        e = self.env
        spec = kit.down_spec(e)
        (e.base / "j4" / "finite_batch.py").write_bytes(b"# not the core\n")
        spec["j4"]["programs"]["finite_batch"] = kit.sha(b"# not the core\n")
        self.bind_refuses(spec, "J4_FINITE_BATCH_NOT_THE_LEDGER_CORE")

    def test_s6_epoch04_path_guards_for_gate_capacity_ready(self):
        e = self.env
        fam = inst.family_core()
        base = {"gate": None, "capacity": None, "ready": None, "mode": "REAL"}
        ext = {"ok": {}}
        files = {"docs/r.json": "ab" * 32}
        gate = {"scope": {}, "journal_directory": "/var/lib/c3po-bar/journal", "snapshot_reader": "ok",
                "snapshot_verifier": "ok", "readback": {"rule": "docs/r.json", "rule_verifier": "ok", "readback_verifier": "ok"}}
        with self.assertRaisesRegex(rt.Hold, "GATE_JOURNAL_NOT_EPOCH04"):
            rt.validate_sections(dict(base, gate=gate), ext, files, rt.Hold, True)
        cap = {"mode": "REAL", "lots": {"m3": "BOOT", "j": "DOWN", "activation": "CAP"},
               "sources": {"m3": "a1" * 32, "j": "a2" * 32, "activation": "a3" * 32},
               "verifiers": {"rule": "ok", "original": "ok", "config": "ok"}, "config_path": "/etc/capacity.json"}
        with self.assertRaisesRegex(rt.Hold, "CAPACITY_CONFIG_NOT_EPOCH04"):
            rt.validate_sections(dict(base, capacity=cap), ext, files, rt.Hold, True)
        ready = {"mode": "REAL", "calendar_sha256": "c1" * 32, "not_before": "2026-10-12T13:29:00Z",
                 "not_after": "2026-10-12T13:29:50Z", "max_wait_seconds": 48, "poll_seconds": 0.25,
                 "ready_path": "/var/lib/c3po-bar/journal-e04/ready.json", "verifiers": {"rule": "ok", "ready": "ok"}}
        with self.assertRaisesRegex(rt.Hold, "READY_PATH_NOT_EPOCH04"):
            rt.validate_sections(dict(base, ready=ready), ext, files, rt.Hold, True)
        rt.validate_sections(dict(base, gate=dict(gate, journal_directory=rt.EPOCH04_JOURNAL_ROOT),
                                  capacity=dict(cap, config_path=rt.EPOCH04_CAPACITY_ROOT + "/config/final.json"),
                                  ready=dict(ready, ready_path=rt.EPOCH04_READY_PATH)), ext, files, rt.Hold, True)
        self.assertIsNotNone(fam)

    def test_j1_started_late_consumes_the_logical_attempt(self):
        self.up_all()
        e = self.env
        self.down(j_slots=("J1", "J2"))
        self.assertEqual(e.run("DOWN", "E6")[0], 0)
        code, res = e.run("DOWN", "J1", at=e.slot_at("DOWN", "J1") + timedelta(seconds=61))
        self.assertEqual((code, res["status"], res["code"], res["start_marker"], res["effect_calls"]),
                         (2, "REFUSED_CONSUMED_START", "START_OUTSIDE_SLOT_WINDOW", "CREATED", 0), res)
        code, res = e.run("DOWN", "J2")
        self.assertEqual((code, res["status"]), (3, "REFUSED_START_CONSUMED"), res)

    def test_budget_floor_and_remaining_budget_before_the_effect(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(extended=False)
        bad = json.loads(json.dumps(spec))
        bad["tasks"][0]["effect"]["docker"]["timeout_seconds"] = 56           # 56 + 20 + 15 > 90
        bad["tasks"][0]["decoder"]["provenance_binding_sha256"] = kit.sha(kit.canonical(bad["tasks"][0]["effect"]))
        self.bind_refuses(bad, "EFFECT_BUDGET_EXCEEDS_TASK")
        bad = json.loads(json.dumps(spec))
        bad["tasks"][0]["effect"]["docker"]["timeout_seconds"] = 26           # 26 + 20 + 15 + 30 > 90 (v3.1 slack)
        bad["tasks"][0]["decoder"]["provenance_binding_sha256"] = kit.sha(kit.canonical(bad["tasks"][0]["effect"]))
        self.bind_refuses(bad, "EFFECT_LATENESS_SLACK_BELOW_30S")
        e.install_spec(spec)
        shell = rt.Shell(e.lot_dir("UP"), probe=e.probe, physical=False)
        shell.fresh_allow()
        row = shell.authority["effects"]["prove"]
        saved = shell.fam.fx.start_minute_violation
        shell.fam.fx.start_minute_violation = lambda at: None
        try:
            with self.assertRaisesRegex(rt.Hold, "BUDGET_REMAINING_BELOW_EFFECT_FLOOR"):
                shell.before_effect(row, datetime.now(timezone.utc) + timedelta(seconds=30))
            # 90 s budget, floor 45 s: an effect reached up to 45 s after the instant still passes
            shell.before_effect(row, datetime.now(timezone.utc) + timedelta(seconds=46))
        finally:
            shell.fam.fx.start_minute_violation = saved

    def test_k9_rows_are_fixed_by_their_signed_plan(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(extended=False)

        def mutate(fn, code):
            bad = json.loads(json.dumps(spec))
            fn(bad["tasks"][2])
            bad["tasks"][2]["decoder"]["provenance_binding_sha256"] = kit.sha(kit.canonical(bad["tasks"][2]["effect"]))
            self.bind_refuses(bad, code)
        mutate(lambda t: t["effect"]["docker"]["command"].__setitem__(6, "ab" * 32), "K9_COMMAND_NOT_FIXED_SHAPE")
        mutate(lambda t: t["effect"]["docker"].__setitem__("name", "c3po-k9-commit"), "K9_CONTAINER_NAME_INVALID")
        mutate(lambda t: t["effect"]["docker"].__setitem__("network", "bridge"), "K9_NETWORK_NOT_THE_CLASS_ONE")
        mutate(lambda t: t["effect"]["docker"]["env"][1].__setitem__(1, "00" * 20), "K9_ENV_NOT_FIXED")
        mutate(lambda t: t["effect"]["docker"]["env_files"].append(str(e.docs / "x.env")), "K9_ENV_FILE_NOT_SECRETS_ROOT")
        mutate(lambda t: t["effect"]["docker"]["env_files"].append(str(e.env_file)), "K9_ENV_FILES_NOT_THE_CLASS_ONES")
        mutate(lambda t: t["effect"]["docker"].__setitem__("image_id", "sha256:" + "cd" * 32), "K9_IMAGE_NOT_THE_REQUEST_ONE")
        mutate(lambda t: t["effect"]["docker"]["mounts"][2].__setitem__("readonly", False), "K9_MOUNTS_NOT_CLOSED")
        mutate(lambda t: t["effect"]["receipt"].__setitem__("path", str(e.receipts / "other.json")), "K9_RECEIPT_PATH_INVALID")
        mutate(lambda t: t["slots"][0].__setitem__("at", kit.z(kit.allowed_after(rt.stamp(t["slots"][0]["at"]), 20))),
               "K9_SLOT_NOT_THE_PLAN_ONE")
        bad = json.loads(json.dumps(spec))
        bad["tasks"][0]["decoder"]["provenance_binding_sha256"] = "ee" * 32
        self.bind_refuses(bad, "K9_DECODER_ROW_NOT_DERIVED")

    def test_k9_host_bytes_must_equal_the_signed_runner_and_plan(self):
        self.up(run=("P1",))
        e = self.env
        plan = e.daydir / "plans" / "collect_launch.json"
        os.chmod(plan, 0o600)
        plan.write_bytes(plan.read_bytes() + b" ")
        code, res = e.run("UP", "P2")
        self.assertEqual((code, res["effect_calls"], res["code"]), (2, 0, "K9_HOST_PLAN_NOT_THE_SIGNED_ONE"), res)
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "collect-launch"), [])


# ====================================================================== carried v2 review tests
class Review(Base):
    def test_slot_spacing_dependency_order_and_minutes_are_checked(self):
        """v3.1 (finding 3): FIXED instants (Saturday 10/10 11:38:00 BRT and later), never the wall clock, so the
        outcome does not depend on the time of day the suite runs."""
        e = self.env
        e.prepare()
        base = datetime(2026, 10, 10, 14, 38, 0, tzinfo=timezone.utc)            # 11:38:00 BRT
        times = [base + timedelta(seconds=155 * i) for i in range(4)]
        second = base + timedelta(seconds=40)                                    # 11:38:40 BRT
        too_close = base + timedelta(seconds=10)                                 # 11:38:10 BRT
        for t in times + [second, too_close]:
            self.assertIsNone(fx.start_minute_violation(t), t)
        nb, na = base - timedelta(minutes=5), base + timedelta(hours=1)
        prepared, deadline = base - timedelta(hours=2), base - timedelta(hours=1)

        def fixed_spec(slot_times):
            tasks = []
            requires = {"prove": [], "collect": ["prove"], "commit_result": ["collect"], "publish_launch": ["commit_result"]}
            for i, core in enumerate(("prove", "collect", "commit_result", "publish_launch")):
                op = kit.CORE_RUNNER[core]
                e.k9_plan(op, slot_times[i], kit.CORE_K9_BUDGET, core=core, run_not_after=slot_times[i] + timedelta(seconds=60))
                row = e.k9_row(op, 25)
                tasks.append({"operation": core, "not_before": kit.z(nb), "not_after": kit.z(na),
                              "budget_seconds": kit.CORE_K9_BUDGET, "requires": requires[core],
                              "slots": [{"slot": "P%d" % (i + 1), "at": kit.z(slot_times[i])}], "effect": row,
                              "decoder": e.k9_decoder(op, row, nb, na), "image_go_sha256": None, "image_proposal_sha256": None})
            spec = e.spec("UP", "UPSTREAM_P", tasks, files=e.k9_files(list(kit.CORE_RUNNER.values())),
                          k9=e.k9_section(list(kit.CORE_RUNNER.values())))
            spec["owner_deadline"] = kit.z(deadline)
            return spec
        good = fixed_spec(times)
        out = e.stage / "lot-UP-fixed-good"
        path = e.base / "spec-fixed-good.json"
        path.write_text(json.dumps(good))
        bind.lot(str(path), str(e.layout_path), str(e.runtime_path), kit.z(prepared), str(out))   # the fixed base binds
        self.bind_refuses(fixed_spec([times[0], too_close] + times[2:]), "SLOTS_TOO_CLOSE", prepared_at=prepared)
        self.bind_refuses(fixed_spec([times[0], second] + times[2:]), "DEPENDENT_SLOT_BEFORE_DEPENDENCY_END",
                          prepared_at=prepared)

    def test_cross_lot_spacing_is_checked_at_install_before_any_write(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(extended=False)
        e.install_spec(spec)
        clash = json.loads(json.dumps(spec))
        clash["lot"] = "UPB"
        bound = e.signed_lot(clash)
        with self.assertRaisesRegex(rt.Hold, "SLOTS_TOO_CLOSE_ACROSS_LOTS"):
            e.install("UPB", bound)
        self.assertFalse(os.path.lexists(e.lot_dir("UPB")))

    def test_two_processes_on_two_alternatives_run_exactly_once(self):
        e = self.env
        self.up(extended=False, run=(), spec_hook=with_prove_alternative(e))
        procs = [subprocess.Popen([kit.PY, "-I", "-S", "-B", DRIVER, "run", e.lot_dir("UP"), slot,
                                   kit.z(e.slot_at("UP", slot))], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for slot in ("P1", "P1B")]
        outs = [json.loads(p.communicate(timeout=120)[0]) for p in procs]
        self.assertEqual(sorted(o["status"] for o in outs),
                         ["ORIGINAL_COMPLETE_OBSERVED_CANDIDATE", "REFUSED_START_CONSUMED"], outs)
        self.assertEqual(len(self.docker_runs(rt.K9_CONTAINER_PREFIX + "prove-launch")), 1)

    def test_core_ledger_two_process_race_never_poisons(self):
        e = self.env
        e.prepare()
        root = e.layout["root"] + "/ledger"
        pins = e.base / "pins.json"
        shell_like = rt.strict(e.runtime_raw)["election"]
        rows = [[n, r] for n, r in shell_like["root_chain"]] + [[root, shell_like["children"]["ledger"]]]
        pins.write_text(json.dumps([rows, shell_like["ledger_file"]]))
        procs = [subprocess.Popen([kit.PY, "-I", "-S", "-B", DRIVER, "claim", root, str(pins), tag, "15"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) for tag in ("a", "b")]
        outs = [json.loads(p.communicate(timeout=120)[0]) for p in procs]
        self.assertEqual([o.count("CLAIMED") for o in outs], [15, 15], outs)

    def test_kill_during_effect_consumes_and_never_runs_twice(self):
        e = self.env
        self.up(extended=False, run=(), spec_hook=with_prove_alternative(e))
        pid_file = e.base / "docker.pid"
        e.update_fake(**{rt.K9_CONTAINER_PREFIX + "prove-launch": {"sleep": 30, "pid_file": str(pid_file)}})
        p = subprocess.Popen([kit.PY, "-I", "-S", "-B", DRIVER, "run", e.lot_dir("UP"), "P1", kit.z(e.slot_at("UP", "P1"))],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 60
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(pid_file.exists())
        time.sleep(0.2)
        p.kill()
        p.communicate(timeout=30)
        docker_pid = int(pid_file.read_text())
        deadline = time.monotonic() + 20
        alive = True
        while alive and time.monotonic() < deadline:
            try:
                os.kill(docker_pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                alive = False
        self.assertFalse(alive, "the lifeline watchdog must kill the effect group when the parent dies")
        kinds = [r["kind"] for r in e.ledger_rows() if r["attempt_key"] == e.key("prove")]
        self.assertEqual(kinds, ["CLAIM"])
        code, res = e.run("UP", "P1B")
        self.assertEqual((code, res["status"]), (3, "REFUSED_START_CONSUMED"), res)

    def test_kill_during_extended_step_holds_its_dependents(self):
        self.up()
        e = self.env
        pid_file = e.base / "docker.pid"
        e.update_fake(**{rt.K9_CONTAINER_PREFIX + "components-launch": {"sleep": 30, "pid_file": str(pid_file)}})
        p = subprocess.Popen([kit.PY, "-I", "-S", "-B", DRIVER, "run", e.lot_dir("UP"), "X1", kit.z(e.slot_at("UP", "X1"))],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 60
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        p.kill()
        p.communicate(timeout=30)
        key = e.xkey("components")
        self.assertTrue((Path(e.layout["root"]) / "extended" / ("xclaim-" + key)).exists())
        self.assertFalse((Path(e.layout["root"]) / "extended" / ("xterm-" + key)).exists())
        code, res = e.run("UP", "X2")
        self.assertEqual((code, res["status"], res["effect_calls"]), (2, "EXTENDED_REFUSED_CONSUMED", 0), res)
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "sources-launch"), [])

    def test_extended_ceiling_kills_the_group_and_is_uncertain(self):
        e = self.env
        self.up(steps=("components",), ceilings={"components": 70})          # KILL 5 + 20 + 15 + 30 slack
        started = time.monotonic()
        hang = kit.FakeProbe(on_outer_call=lambda n: time.sleep(120))     # a gate that never returns, in the worker
        code, res = e.run("UP", "X1", probe=hang)
        self.assertLess(time.monotonic() - started, 100)
        self.assertEqual((code, res["status"], res["code"]), (2, "EXTENDED_UNCERTAIN_CONSUMED", "EXTENDED_CEILING_REACHED"), res)
        self.assertTrue(res["recovery_required"])
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "components-launch"), [])

    def test_extended_container_is_bounded_by_its_inner_timeout(self):
        e = self.env
        self.up(steps=("components",), ceilings={"components": 90})          # KILL 25: CHILD_DEADLINE at 45 s
        e.update_fake(**{rt.K9_CONTAINER_PREFIX + "components-launch": {"sleep": 120}})
        started = time.monotonic()
        code, res = e.run("UP", "X1")
        self.assertLess(time.monotonic() - started, 80)
        self.assertEqual((code, res["status"], res["code"], res["effect_calls"]),
                         (2, "EXTENDED_UNCERTAIN_CONSUMED", "CHILD_DEADLINE", 1), res)

    def test_extended_ceiling_cap_and_floor(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(steps=("components",), ceilings={"components": 4801})
        self.bind_refuses(spec, "EXTENDED_CEILING_INVALID")
        spec = e.up_spec(steps=("components",))
        spec["extended"]["steps"][0]["effect"]["docker"]["timeout_seconds"] = 56
        self.bind_refuses(spec, "EXTENDED_CEILING_BELOW_EFFECT")
        spec = e.up_spec(steps=("components",))
        spec["extended"]["steps"][0]["effect"]["docker"]["timeout_seconds"] = 26    # 26 + 20 + 15 + 30 > 90
        self.bind_refuses(spec, "EFFECT_LATENESS_SLACK_BELOW_30S")

    def test_installer_never_skips_a_signed_slot(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(extended=False)
        bound = e.signed_lot(spec)
        late = rt.stamp(spec["tasks"][0]["slots"][0]["at"]) - timedelta(seconds=100)
        with self.assertRaisesRegex(rt.Hold, "SLOT_MARGIN_LOST"):
            e.install("UP", bound, at=late)
        self.assertFalse(os.path.lexists(e.lot_dir("UP")))
        self.assertEqual(e.timers, [])

    def test_docker_config_must_be_pinned_empty(self):
        self.up(run=("P1",))
        e = self.env
        (e.dockercfg / "config.json").write_text("{}")
        code, res = e.run("UP", "P2")
        self.assertEqual((code, res["effect_calls"]), (2, 0), res)
        self.assertIn(res["code"], ("DOCKER_CONFIG_NOT_EMPTY_PRIVATE", "DIRECTORY_IDENTITY_CHANGED"), res)

    def test_secret_env_file_policy(self):
        self.up(run=("P1",))
        e = self.env
        os.chmod(e.env_file, 0o640)
        code, res = e.run("UP", "P2")
        self.assertEqual((code, res["code"], res["effect_calls"]), (2, "SECRET_ENV_FILE_NOT_PRIVATE", 0), res)

    def test_timer_properties_and_exact_timeout(self):
        e = self.env
        e.prepare()
        e.install_spec(e.up_spec(extended=False))
        argv = e.timers[0]
        for prop in ("--timer-property=AccuracySec=1s", "--timer-property=Persistent=false",
                     "--timer-property=RandomizedDelaySec=0", "--property=Type=oneshot", "--property=Restart=no",
                     "--property=TimeoutStartSec=210", "--property=KillMode=control-group"):
            self.assertIn(prop, argv)
        self.assertEqual(argv[-10:-6], [e.layout["python"], "-I", "-S", "-B"])

    def test_owner_signature_window_0700_2145_brt(self):
        for value in ["2026-10-10T10:00:00Z", "2026-10-11T00:45:00Z"]:
            rt.owner_time_guard(value)
        for value in ["2026-10-10T09:59:59Z", "2026-10-11T00:45:01Z", "2026-10-11T03:00:00Z"]:
            with self.assertRaisesRegex(rt.Hold, "OWNER_SIGNED_OUTSIDE_0700_2145_BRT"):
                rt.owner_time_guard(value)

    def test_start_minute_rules_table(self):
        def at(hhmmss):
            h, m, s = (int(x) for x in hhmmss.split(":"))
            return datetime(2026, 10, 12, h, m, s, tzinfo=rt.BRT)
        allowed = ["06:26:00", "06:38:00", "06:48:00", "07:38:00", "10:01:00", "10:29:02", "10:52:00", "11:26:00",
                   "13:26:00", "21:26:00", "21:28:00", "21:38:00", "22:48:00", "23:26:00", "10:03:39", "10:33:39"]
        refused = ["10:03:40", "10:05:00", "10:07:59", "10:08:40", "10:10:00", "10:25:59", "10:33:40", "10:35:00",
                   "10:37:59", "06:58:40", "07:25:59", "12:58:40", "13:20:00", "18:58:40", "19:25:59", "00:15:00",
                   "00:45:59", "02:15:00", "02:45:59", "00:30:00"]
        for value in allowed:
            self.assertIsNone(fx.start_minute_violation(at(value)), value)
        for value in refused:
            self.assertIsNotNone(fx.start_minute_violation(at(value)), value)

    def test_fixture_refused_on_host_and_no_clock_injection(self):
        e = self.env
        e.prepare()
        e.install_spec(e.up_spec(extended=False))
        fam = inst.family_core()
        lot_dir = Path(e.lot_dir("UP"))
        authority = json.loads((lot_dir / "authority.json").read_bytes())
        q = fam.fb.validate_plan((lot_dir / "request.json").read_bytes())
        with self.assertRaisesRegex(rt.Hold, "AUTHORITY_FIXTURE_REFUSED_ON_HOST"):
            rt.validate_authority(authority, q, fam, rt.Hold, physical=True)
        with self.assertRaisesRegex(rt.Refusal, "SLOT_CLOCK_INJECTION_FORBIDDEN"):
            rt.Shell(str(lot_dir), probe=e.probe, physical=True, slot_clock=lambda: None)

    def test_family_seal_and_vendor_pins(self):
        import verify_family
        if not (kit.FAMILY / "SHA256SUMS").exists():
            self.skipTest("family not sealed yet")
        result = verify_family.verify(kit.FAMILY)
        self.assertEqual((result["status"], result["vendor_pins"]), ("SEAL_EXACT", 15))


# ====================================================================== the lot specs of this delivery
class Specs(Base):
    def test_up_spec_real_values_pass_every_v3_rule_with_fill_ins(self):
        sys.path.insert(0, str(kit.FAMILY / "lots"))
        import build_specs
        result = build_specs.validate_up(physical=True)
        self.assertEqual(result["status"], "UP_SPEC_VALID_WITH_FILL_INS")
        self.assertEqual(result["image_id"], "sha256:bf37cec9f4f93e129543235a567a2de5daad0c8116086e2b176069e497defba3")
        self.assertEqual((result["code_revision"], result["package_sha256"], result["runner_sha256"],
                          result["release_sha256"], result["policy_sha256"]),
                         ("de96aee90a26e9587663ba7a1f6e55a592afcd20",
                          "43db2b969fe113594fafe4a9e0cabec1f80ada9f8ab9ee5852677d65e2ec716a",
                          "e9be2b301397586a35f592cae3a23a5bfa3e7fdc5b9d27996c590e4303be081a",
                          "5fd6eadbf8c1c899598e23c52e98599fe9cc990bd33a182cc363d2c05c5784ab",
                          "6757e79112770f948b73770f6b6b87f209930afe8cd00f9517d378055e0d2d92"))
        self.assertEqual(result["slots"], 11)
        # v3.1 (finding 8): every UP K9 row reaches its effect up to >= 45 s after its instant (30 s beyond the gate
        # allowance); LAUNCH rows: KILL = budget - 65
        self.assertEqual(len(result["slack"]), 11)
        for row in result["slack"]:
            self.assertGreaterEqual(row["slack_beyond_allowance"], 30, row)
            self.assertGreaterEqual(row["max_effect_lateness"], 45, row)
        kills = {r["target"]: r["kill"] for r in result["slack"]}
        self.assertEqual((kills["prove"], kills["collect"], kills["commit_result"], kills["publish_launch"], kills["bind"],
                          kills["stage"]), (535, 835, 535, 535, 35, 20))

    def test_down_spec_draft_passes_every_v3_rule_with_fill_ins(self):
        sys.path.insert(0, str(kit.FAMILY / "lots"))
        import build_specs
        result = build_specs.validate_down(physical=True)
        self.assertEqual(result["status"], "DOWN_DRAFT_VALID_WITH_FILL_INS")
        self.assertEqual(result["session_start_at"], "2026-10-12T13:29:02Z")
        self.assertEqual(result["ready_check_at"], "2026-10-12T12:30:00Z")
        self.assertTrue(all(r["slack_beyond_allowance"] >= 30 for r in result["slack"]), result["slack"])


class V31(Base):
    """The v3 adversarial review findings (V3_BUILD_AND_REVIEW_REPORTS.md), one test or more each."""

    # ---------------------------------------------------------------- finding 1: unit grammar
    def test_f1_unit_dependencies_and_environment_are_the_reference_ones(self):
        e = self.env
        for row_of in (kit.reader_row, kit.supervisor_row):
            row, _, _ = row_of(e)
            fx.validate_row(row, e.layout)
            for name, prop in {"wants_reader": ["Wants", "c3po-reader.service"],
                               "requires_reader": ["Requires", "c3po-reader.service"],
                               "after_extra": ["After", "network-online.target docker.service c3po-reader.service"],
                               "wants_twice": ["Wants", "network-online.target"],
                               "ld_preload": ["Environment", "LD_PRELOAD=/tmp/x.so"],
                               "docker_host": ["Environment", "DOCKER_HOST=tcp://10.0.0.1:2375"],
                               "docker_context": ["Environment", "DOCKER_CONTEXT=other"],
                               "docker_config_other": ["Environment", "DOCKER_CONFIG=/tmp"]}.items():
                with self.subTest(row_of.__name__ + ":" + name):
                    bad = json.loads(json.dumps(row))
                    bad["unit"]["properties"].append(prop)
                    with self.assertRaisesRegex(fx.Hold, "UNIT_DEPENDENCY_INVALID|UNIT_ENVIRONMENT_INVALID|"
                                                         "UNIT_REQUIRED_PROPERTY_MISSING"):
                        fx.validate_row(bad, e.layout)
            for key, value in (("Wants", "c3po-reader.service"), ("Requires", "c3po-reader.service")):
                with self.subTest(row_of.__name__ + ":replace:" + key):
                    bad = json.loads(json.dumps(row))
                    bad["unit"]["properties"] = [[k, value if k == key else v] for k, v in bad["unit"]["properties"]]
                    with self.assertRaisesRegex(fx.Hold, "UNIT_DEPENDENCY_INVALID"):
                        fx.validate_row(bad, e.layout)

    def test_f1_session_start_unit_rows_are_pinned_whole(self):
        """The reviewer's probe: a DOWN spec whose supervisor copy Wants/Requires c3po-reader.service bound in physical
        mode. Now every deviation of the property list or the exec words is refused at bind (physical)."""
        sys.path.insert(0, str(kit.FAMILY / "lots"))
        import build_specs
        lay = build_specs.layout()

        def refuses(mutate, code):
            spec = build_specs.build_down()
            mutate(spec["extended"]["steps"][1])
            with tempfile_dir() as tmp:
                filled = build_specs.fill(spec, tmp)
                with self.assertRaisesRegex(rt.Hold, code):
                    bind.build_lot(filled, lay, build_specs.runtime_stub(lay), "2026-10-11T23:00:00Z", build_specs.LOTS,
                                   physical=True)
        for key in ("Wants", "Requires"):
            refuses(lambda st, key=key: st["pre_effect"]["unit"]["properties"].__setitem__(
                [p[0] for p in st["pre_effect"]["unit"]["properties"]].index(key), [key, "c3po-reader.service"]),
                "UNIT_DEPENDENCY_INVALID")
        refuses(lambda st: st["effect"]["unit"]["properties"].append(["UMask", "0077"]), "SESSION_READER_UNIT_NOT_PINNED")
        refuses(lambda st: st["pre_effect"]["unit"]["properties"].__setitem__(-1, ["SyslogIdentifier", "c3po-reader-e04"]),
                "SUPERVISOR_UNIT_NOT_PINNED")
        refuses(lambda st: st["effect"]["unit"].__setitem__("description", "Another description"),
                "SESSION_READER_UNIT_NOT_PINNED")
        refuses(lambda st: st["effect"]["unit"]["exec"].__setitem__(st["effect"]["unit"]["exec"].index("--pids-limit") + 1,
                                                                   "4096"), "SESSION_READER_UNIT_NOT_PINNED")

        def sup_mount_reader_folder(st):
            words = st["pre_effect"]["unit"]["exec"]
            i = [k for k, w in enumerate(words) if w.endswith("target=/etc/c3po-bar,readonly")][0]
            words[i] = "type=bind,source=/etc/c3po-reader-e04,target=/etc/c3po-bar,readonly"
        refuses(sup_mount_reader_folder, "MOUNT_SOURCE_FORBIDDEN")

        def reader_env_k9_secret(st):
            words = st["effect"]["unit"]["exec"]
            i = words.index("--env-file")
            words[i + 1] = rt.EPOCH03_SECRETS_ROOT + "/provider.env"
        refuses(reader_env_k9_secret, "SESSION_READER_UNIT_NOT_PINNED|SESSION_UNIT")

    # ---------------------------------------------------------------- finding 2: leftover ready.json
    def test_f2_leftover_ready_is_a_hold_before_the_supervisor(self):
        self.session_world(ready_check=True)
        e = self.env
        self.ready()                                    # a leftover from a rehearsal
        code, res = e.run("DOWN", "R0")
        self.assertEqual((code, res["status"], res["code"], res["effect_calls"]),
                         (2, "EXTENDED_REFUSED_CONSUMED", "READY_LEFTOVER_PRESENT", 0), res)
        self.session_shell()
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["status"], res["code"], res["effect_calls"]),
                         (2, "EXTENDED_REFUSED_CONSUMED", "READY_LEFTOVER_PRESENT_BEFORE_SUPERVISOR", 0), res)
        self.assertEqual(self.unit_starts(), [])
        self.assertFalse((Path(e.layout["root"]) / "extended" / ("xpre-" + e.xkey("session_start"))).exists())

    def test_f2_engine_refuses_the_supervisor_while_a_ready_file_exists(self):
        self.session_world()
        e = self.env
        self.ready()
        lot = e.lot_dir("DOWN")
        authority = Path(lot, "authority.json").read_bytes()
        request = Path(lot, "request.json").read_bytes()
        until = kit.z(datetime.now(timezone.utc) + timedelta(seconds=10))
        argv = fx.engine_argv(lot, "EXTENDED_PRE", "session_start", kit.sha(authority), kit.sha(request),
                              e.xkey("session_start"), "d" * 64, until, None)
        code, out = fx.run(argv)
        self.assertEqual((code, out["status"], out["code"]), (2, "REFUSED", "READY_PRESENT_AT_SUPERVISOR_START"), out)
        argv = fx.engine_argv(lot, "EXTENDED", "session_start", kit.sha(authority), kit.sha(request),
                              e.xkey("session_start"), "d" * 64, until, kit.sha(e.ready_path.read_bytes()))
        code, out = fx.run(argv)                        # the reader without the acknowledged supervisor PID
        self.assertEqual((code, out["code"]), (2, "EFFECT_ARGV_NOT_FOR_THIS_EFFECT"), out)
        self.assertEqual(self.unit_starts(), [])

    # ---------------------------------------------------------------- finding 4: mount policy
    def test_f4_parents_of_protected_folders_and_the_reader_secret_folder(self):
        e = self.env
        layout = dict(e.layout, root=rt.EPOCH04_L12_ROOT, veto_dir=rt.EPOCH04_VETO_DIR,
                      docker_config=rt.EPOCH04_READER_CONFIG + "/docker-cli")
        for path, ro in (("/var/lib/c3po-bar", False), (rt.EPOCH04_JOURNAL_ROOT, False)):
            fx.mount_source_policy(path, ro, layout)        # not a parent of anything protected here
        nested = dict(layout, root=rt.EPOCH04_JOURNAL_ROOT + "/l12root")
        with self.assertRaisesRegex(fx.Hold, "MOUNT_PARENT_OF_PROTECTED_FORBIDDEN"):
            fx.mount_source_policy(rt.EPOCH04_JOURNAL_ROOT, False, nested)   # the reviewer's probe
        with self.assertRaisesRegex(fx.Hold, "MOUNT_PARENT_OF_PROTECTED_FORBIDDEN"):
            fx.mount_source_policy(str(Path(e.veto).parent), True, e.layout)
        with self.assertRaisesRegex(fx.Hold, "MOUNT_DOCKER_CONFIG_FORBIDDEN"):
            fx.mount_source_policy(str(e.dockercfg), True, e.layout)
        for path in (rt.EPOCH04_READER_CONFIG, rt.EPOCH04_READER_CONFIG + "/secret.env",
                     rt.EPOCH04_READER_CONFIG + "/docker-cli"):
            with self.subTest(path):
                with self.assertRaises(fx.Hold):
                    fx.mount_source_policy(path, True, layout)
        for path in (rt.EPOCH04_READER_LAUNCHER, rt.EPOCH04_SUPERVISOR_CONFIG):
            fx.mount_source_policy(path, True, layout)
            self.assertIsNone(rt.epoch04_mount_violation(path, True, layout))
        self.assertEqual(rt.epoch04_mount_violation(rt.EPOCH04_READER_CONFIG, True, layout), "MOUNT_PARENT_OF_PROTECTED_FORBIDDEN")
        self.assertEqual(rt.epoch04_mount_violation("/var/lib", True, nested), "MOUNT_PARENT_OF_PROTECTED_FORBIDDEN")

    def test_f4_physical_root_is_pinned(self):
        sys.path.insert(0, str(kit.FAMILY / "lots"))
        import build_specs
        lay = dict(build_specs.layout(), root="/var/lib/c3po-bar/journal-e04/l12")
        with tempfile_dir() as tmp:
            filled = build_specs.fill(build_specs.build_up(), tmp)
            with self.assertRaisesRegex(rt.Hold, "L12_ROOT_NOT_EPOCH04"):
                bind.build_lot(filled, lay, build_specs.runtime_stub(lay), "2026-10-10T12:30:00Z", build_specs.LOTS,
                               physical=True)

    # ---------------------------------------------------------------- finding 5: supervisor liveness
    def test_f5_supervisor_dead_before_the_reader_holds_without_the_reader(self):
        self.session_world()
        e = self.env
        self.ready_on_supervisor()
        e.update_fake(die_after_shows={rt.SUPERVISOR_NAME + ".service": 1})    # dies right after its ACK
        self.session_shell()
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["status"], res["code"], res["effect_calls"]),
                         (2, "EXTENDED_UNCERTAIN_CONSUMED", "SUPERVISOR_NOT_RUNNING_BEFORE_READER", 1), res)
        self.assertEqual([w for r in self.unit_starts() for w in r["argv"] if w.startswith("--unit=")],
                         ["--unit=" + rt.SUPERVISOR_NAME])

    def test_f5_supervisor_dead_during_the_hold_is_not_a_complete(self):
        self.session_world(hold_seconds=40)
        e = self.env
        self.ready_on_supervisor()
        e.update_fake(die_after_shows={rt.SUPERVISOR_NAME + ".service": 4})    # alive at both checks, dies in the hold
        self.session_shell()
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["status"], res["effect_calls"]), (2, "EXTENDED_UNCERTAIN_CONSUMED", 2), res)
        self.assertIn(res["code"], ("LAUNCH_ACK_UNIT_NOT_RUNNING_ONCE", "SUPERVISOR_NOT_RUNNING_THROUGH_HOLD"), res)
        self.assertEqual(len(self.unit_starts()), 2)

    # ---------------------------------------------------------------- finding 6: session window vs open
    def test_f6_session_start_window_starts_at_or_after_open_minus_90s(self):
        sys.path.insert(0, str(kit.FAMILY / "lots"))
        import build_specs
        lay = build_specs.layout()

        def refuses(mutate, code):
            spec = build_specs.build_down()
            mutate(spec)
            with tempfile_dir() as tmp:
                filled = build_specs.fill(spec, tmp)
                with self.assertRaisesRegex(rt.Hold, code):
                    bind.build_lot(filled, lay, build_specs.runtime_stub(lay), "2026-10-11T23:00:00Z", build_specs.LOTS,
                                   physical=True)
        refuses(lambda sp: sp["extended"]["steps"][1].update(not_before="2026-10-12T13:28:29Z"),
                "SESSION_START_WINDOW_BEFORE_OPEN_MINUS_90S")
        refuses(lambda sp: sp["gate"]["scope"].update(session_open="2026-10-12T13:29:00Z"), "SESSION_OPEN_NOT_THE_MONDAY_ONE")
        self.up_all()
        e = self.env
        spec = kit.down_spec(e, session=True)
        spec["gate"]["scope"]["session_open"] = kit.z(rt.stamp(spec["extended"]["steps"][0]["not_before"])
                                                      + timedelta(seconds=91))
        with self.assertRaisesRegex(rt.Hold, "SESSION_START_WINDOW_BEFORE_OPEN_MINUS_90S"):
            kit.sign_down(e, spec)

    # ---------------------------------------------------------------- finding 7: image and env-file pins
    def test_f7_unit_env_file_identity_is_pinned_in_the_claim(self):
        self.session_world()
        e = self.env
        self.ready_on_supervisor()
        secret = e.base / "cfg" / "secret.env"

        def image(self_, phase, task, ready_sha256=None):
            if phase == "BEFORE_FIRST_READER":
                secret.unlink()
                secret.write_text("C3PO_FIXTURE_ONLY=2\n")
                os.chmod(secret, 0o600)
        self.session_shell(image=image)
        code, res = e.run("DOWN", "S1")
        self.assertEqual((code, res["code"], res["effect_calls"]), (2, "UNIT_ENV_FILE_IDENTITY_CHANGED", 1), res)
        self.assertEqual(len(self.unit_starts()), 1)

    def test_f7_k9_request_must_name_the_image(self):
        e = self.env
        e.prepare()
        spec = e.up_spec(extended=False)
        e.k9_request.write_bytes(kit.canonical({"schema": "K9_04_STEP_SET_REQUEST_V1", "synthetic": True}))
        for op in kit.CORE_RUNNER.values():
            plan = json.loads((e.assets / "k9" / (op + ".json")).read_bytes())
            plan["request_sha256"] = kit.sha(e.k9_request.read_bytes())
            (e.assets / "k9" / (op + ".json")).write_bytes(kit.canonical(plan))
        self.bind_refuses(spec, "K9_REQUEST_IMAGE_UNBOUND|K9_COMMAND_NOT_FIXED_SHAPE")

    # ---------------------------------------------------------------- finding 10: the W seal
    def test_f10_staged_w_seal_is_the_family_seal(self):
        e = self.env
        out = e.prepare()
        self.assertEqual(out["seal_sha256"], kit.sha(kit.family_sums()))
        sealed = kit.FAMILY / "SHA256SUMS"
        if sealed.exists() and sealed.read_bytes() == kit.family_sums():
            import verify_family
            self.assertEqual(out["seal_sha256"], verify_family.verify(kit.FAMILY)["seal_sha256"])

    # ---------------------------------------------------------------- finding 11: the image has `timeout`
    def test_f11_image_timeout_readback(self):
        e = self.env
        image = kit.IMAGE
        seen = []

        def runner(rcs):
            def run(argv, timeout):
                seen.append(argv)
                return rcs[len(seen) - 1], b"", b""
            return run
        result = inst.image_check(str(e.layout_path), image, require_root=False, runner=runner([0, 137]))
        self.assertEqual(result["status"], "IMAGE_TIMEOUT_KILL_PRESENT")
        self.assertNotIn("code", result)
        argv = seen[0]
        self.assertEqual(argv[argv.index(image) + 1:argv.index(image) + 5], ["timeout", "-s", "KILL", "10"])
        for flag in ("--rm", "--read-only", "--init"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--network") + 1], "none")
        self.assertFalse(any(w.startswith("--env-file") or w == "--mount" for w in argv))
        seen.clear()
        result = inst.image_check(str(e.layout_path), image, require_root=False, runner=runner([127, 127]))
        self.assertEqual((result["status"], result["code"]), ("IMAGE_TIMEOUT_CHECK_FAILED", "IMAGE_TIMEOUT_CHECK_FAILED"))
        with self.assertRaisesRegex(rt.Hold, "IMAGE_ID_INVALID"):
            inst.image_check(str(e.layout_path), "bf37cec9", require_root=False, runner=runner([0, 137]))


class V32(Base):
    """The v3.1 adversarial review findings H1 and M1 (PREV_BUILD_AND_REVIEW_REPORTS.md)."""

    # ---------------------------------------------------------------- M1: INPUT_FILE_CHANGED names the file
    def bump_on_read(self, target, once_flag):
        """os.read wrapper: the first read of `target` (any process of the run: the patch is inherited by forks)
        moves its mtime one second ahead, as a concurrent writer / a provider touching the file would."""
        real_read = os.read

        def read(fd, n):
            if not once_flag.exists() and rt.fd_path(fd) == target:
                once_flag.write_text("bumped")
                st = os.stat(target)
                os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9))
            return real_read(fd, n)
        return real_read, read

    def test_m1_strict_reader_names_the_changed_file(self):
        e = self.env
        path = e.base / "docs" / "changing.json"
        path.write_bytes(kit.canonical({"synthetic": 1}))
        target = os.path.realpath(str(path))
        real_read, read = self.bump_on_read(target, e.base / "bumped.flag")
        os.read = read
        try:
            with self.assertRaises(rt.Hold) as caught:
                rt.read_path(str(path), 4096, rt.Hold)
        finally:
            os.read = real_read
        error = caught.exception
        self.assertEqual(str(error), "INPUT_FILE_CHANGED")                  # the public code is unchanged
        self.assertEqual(error.input_file, target)
        self.assertIn("mtime_ns", error.changed)
        self.assertEqual({k: rt.INPUT_CHANGES[-1][k] for k in ("code", "file")},
                         {"code": "INPUT_FILE_CHANGED", "file": target})
        self.assertEqual(rt.read_path(str(path), 4096), kit.canonical({"synthetic": 1}))   # unchanged file: accepted

    def test_m1_slot_result_names_the_changed_file(self):
        e = self.env
        e.prepare()
        e.install_spec(e.up_spec(extended=False))
        e.up_fakes()
        target = os.path.realpath(str(e.daydir / "plans" / "prove_launch.json"))   # the K9 host plan copy
        real_read, read = self.bump_on_read(target, e.base / "bumped.flag")
        os.read = read
        try:
            code, res = e.run("UP", "P1")
        finally:
            os.read = real_read
        self.assertTrue((e.base / "bumped.flag").exists())
        self.assertEqual((code, res["status"], res["code"], res["effect_calls"]),
                         (2, "REFUSED_CONSUMED", "INPUT_FILE_CHANGED", 0), res)
        named = [d for d in res["diagnostics"] if d.startswith("INPUT_FILE_CHANGED:")]
        self.assertTrue(named and all(d.startswith("INPUT_FILE_CHANGED:" + target + ":") for d in named), res)
        self.assertEqual(self.docker_runs(rt.K9_CONTAINER_PREFIX + "prove-launch"), [])

    def test_m1_test_temp_parent_is_never_a_file_provider_domain(self):
        self.assertIsNone(kit.file_provider_domain(str(self.env.base)))
        self.assertIsNotNone(kit.TEMP_PARENT["source"])
        documents = Path.home() / "Documents"
        if sys.platform != "darwin" or kit.file_provider_domain(str(documents)) is None:
            self.skipTest("no macOS File Provider domain on this machine")
        self.assertEqual(kit.file_provider_domain(str(documents / "a" / "b")), os.path.realpath(str(documents)))
        saved, saved_parent = os.environ.get("L12_TEST_TMP"), dict(kit.TEMP_PARENT)
        os.environ["L12_TEST_TMP"] = str(documents)
        try:
            self.assertIsNone(kit.file_provider_domain(kit.safe_temp_parent()))
            self.assertEqual(kit.TEMP_PARENT["file_provider_candidates_skipped"], 1)
        finally:
            kit.TEMP_PARENT.update(saved_parent)
            if saved is None:
                os.environ.pop("L12_TEST_TMP")
            else:
                os.environ["L12_TEST_TMP"] = saved

    # ---------------------------------------------------------------- C1: extended cleanup vs the lifeline watchdog
    def test_c1_extended_cleanup_kills_the_live_group_before_its_lifeline_closes(self):
        """The parent kills the worker's group BEFORE it closes the lifeline: the watchdog never kills the group
        first, so the group is alive when killpg runs (macOS answers EPERM to killpg on a group whose members are
        all zombies, which v3.1 read as GROUP_CLEANUP_UNCERTAIN: a rare suite flake under load). The cleanup is
        delayed 0.3 s here, so the old order would lose the race deterministically on macOS."""
        e = self.env
        self.up(steps=("components",))
        original, seen = e.shell, []

        def patched(d, at, probe=None, minute_rule=False):
            shell = original(d, at, probe, minute_rule)
            ext = shell.fam.ext
            real = ext.cleanup

            def slow_cleanup(pid):
                time.sleep(0.3)
                seen.append(real(pid))
                return seen[-1]
            e.patched.append((ext, "cleanup", real))
            ext.cleanup = slow_cleanup
            return shell
        e.shell = patched
        code, res = e.run("UP", "X1")
        self.assertEqual((code, res["status"]), (0, "EXTENDED_COMPLETE"), res)
        self.assertEqual((seen, res["extended"]["worker_cleanup"]),
                         (["GROUP_KILL_ISSUED_WORKER_REAPED"], "GROUP_KILL_ISSUED_WORKER_REAPED"))

    # ---------------------------------------------------------------- N1: the suite at any wall hour
    def test_n1_only_the_registered_fixture_signature_is_exempt_from_the_owner_window(self):
        e = self.env
        night = "2026-10-11T03:00:00Z"                                  # 00:00 BRT, outside 07:00-21:45
        self.assertIs(rt.owner_time_guard, kit.owner_time_guard_except_fixtures)
        with self.assertRaisesRegex(rt.Hold, "OWNER_SIGNED_OUTSIDE_0700_2145_BRT"):
            rt.owner_time_guard(night)
        e.down_t0 = rt.stamp(night) - timedelta(seconds=3)
        self.assertEqual(kit.z(kit.fixture_signed_at(e)), night)
        rt.owner_time_guard(night)                                      # the registered fixture signature only
        with self.assertRaisesRegex(rt.Hold, "OWNER_SIGNED_OUTSIDE_0700_2145_BRT"):
            rt.owner_time_guard("2026-10-11T03:00:01Z")
        e.cleanup()
        self.assertIs(rt.owner_time_guard, kit.REAL_OWNER_TIME_GUARD)
        with self.assertRaisesRegex(rt.Hold, "OWNER_SIGNED_OUTSIDE_0700_2145_BRT"):
            rt.owner_time_guard(night)

    # ---------------------------------------------------------------- H1: the engine's hold check comes first
    def test_h1_engine_refuses_a_far_hold_before_its_supervisor_gate(self):
        self.session_world()
        e = self.env
        self.ready()
        lot = e.lot_dir("DOWN")
        authority = Path(lot, "authority.json").read_bytes()
        request = Path(lot, "request.json").read_bytes()
        step = [s for s in json.loads(authority)["extended"]["steps"] if s["step"] == "session_start"][0]
        hold = rt.stamp(step["hold_until"])
        seen = {}
        for offset in (fx.MAX_HOLD_SECONDS + 1, fx.MAX_HOLD_SECONDS - 60):
            now = hold - timedelta(seconds=offset)
            argv = fx.engine_argv(lot, "EXTENDED", "session_start", kit.sha(authority), kit.sha(request),
                                  e.xkey("session_start"), "d" * 64, kit.z(now + timedelta(seconds=10)),
                                  kit.sha(e.ready_path.read_bytes()), "4242")
            seen[offset] = fx.run(argv, clock=lambda now=now: now)[1]["code"]
        self.assertEqual(seen, {fx.MAX_HOLD_SECONDS + 1: "UNIT_HOLD_TOO_LONG",
                                fx.MAX_HOLD_SECONDS - 60: "SUPERVISOR_NOT_RUNNING_AT_READER_START"})
        self.assertEqual(self.unit_starts(), [])

    def test_h1_proof_schedule_keeps_the_reader_negative_inside_the_hold_window(self):
        """linux_systemd_proof's own planner and model over one whole BRT day (every 97 s), with the ENGINE's
        start-minute rule: the READER negative always runs with 0 < hold - now <= 540 s and ends >= 30 s before R0,
        every slot's whole start window is clear, and the timer-driven part ends within 65 minutes."""
        sys.path.insert(0, str(kit.FAMILY))
        import linux_systemd_proof as proof
        day0 = int(datetime(2026, 10, 12, 3, 0, tzinfo=timezone.utc).timestamp())      # 00:00 BRT
        table = [proof.engine_bad(day0 + s) for s in range(86400)]
        bad = lambda t: table[(t - day0) % 86400]
        worst = 0
        for s in range(0, 86400, 97):
            now = day0 + s
            m = proof.model(now, bad)
            self.assertTrue(0 < m["hold_minus_check"] <= proof.HOLD_CHECK_SECONDS <= fx.MAX_HOLD_SECONDS - 60, (s, m))
            self.assertGreaterEqual(m["r0_minus_negatives_end"], 30, (s, m))
            self.assertEqual([b - a >= proof.UP_GAP_SECONDS for a, b in zip(m["up"], m["up"][1:])], [True] * 4)
            if s % (97 * 25) == 0:                       # direct engine re-check of every instant's whole window
                for at in m["up"]:
                    self.assertFalse(any(proof.engine_bad(at + k) for k in range(proof.SLOT_SPAN[0], proof.SLOT_SPAN[1] + 1)))
                self.assertFalse(any(proof.engine_bad(m["down"]["r0"] + k)
                                     for k in range(proof.DOWN_SPAN[0], proof.DOWN_SPAN[1] + 1)))
            self.assertEqual(m["down"]["hold"] - m["down"]["r0"], 148)
            worst = max(worst, m["end"] - now)
        self.assertLessEqual(worst, 65 * 60)


class tempfile_dir:
    def __enter__(self):
        import tempfile
        self.d = tempfile.TemporaryDirectory()
        return self.d.name

    def __exit__(self, *exc):
        self.d.cleanup()


def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for case in (EndToEnd, SessionStart, MondayLanes, Corrections, Blockers, ShouldFix, Review, Specs, V31, V32):
        suite.addTests(loader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    print(json.dumps({"schema": "L12HOST_V32_TEST_RESULT", "python": "%d.%d.%d" % sys.version_info[:3],
                      "platform": sys.platform, "tests": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "skipped": len(result.skipped), "ok": result.wasSuccessful(),
                      "temp_parent": dict(kit.TEMP_PARENT)}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
