"""L12-HOST lots patch v3.4 suite: L-01 (closed P/X grid choice of gen_k9_plans04), L-06 (REAL specs written by
build_specs OUTSIDE the sealed family) and L-02 (DOWN draft PO off the 40 s edge). SYNTHETIC only: no host, network,
provider, image, container or secret; every output goes to a temporary directory and the family is checked unchanged.

Run: python -I -S -B tests/test_lots_patch_v34.py   (one JSON summary on stdout, test names on stderr; exit 1 on failure)

v3.3 merge (review F1): `real("DOWN", ...)` first writes the REAL UP of the same plans run and passes it as
`up_real_dir` (the DOWN writer now requires it); the F1 accept/mismatch tests are in tests/test_v33.py.

Uses the suite's kit unchanged (kit.FAMILY, kit.fx = the family's l12host_effect, kit.safe_temp_parent). One TEST-ONLY
substitution, in a fresh copy of the generator module per call: `source_pins` returns the pinned de96aee9 value
(RISK_SOURCE_PINS_04, 190 files), because the de96aee9 app tree is not part of the family. Plans made here carry
TEST-ONLY act B / GO bytes and are never signed data.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import types
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402

rt, fx, bind = kit.rt, kit.fx, kit.bind
LOTS = kit.FAMILY / "lots"
sys.path.insert(0, str(LOTS))
import build_specs as bs  # noqa: E402

GEN_PATH = LOTS / "k9tools" / "gen_k9_plans04.py"
RUNNER = LOTS / "k9tools" / "k9_runner04.py"
LAYOUT = LOTS / "layout.e04.DRAFT.json"
SIX = ("prove_launch", "collect_launch", "commit_launch", "publish_launch", "components_launch", "sources_launch")
FIXED_OPS = ("bind", "preflight", "acquire_launch", "execute_launch", "stage", "capture_launch")
TEST_GO = b'{"schema":"TEST_ONLY_K9_GO_NOT_AN_AUTHORIZATION"}\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_generator():
    """A fresh module from the family generator's bytes (no bytecode cache, no shared state between tests)."""
    module = types.ModuleType("gen_k9_plans04_under_test")
    module.__file__ = str(GEN_PATH)
    exec(compile(GEN_PATH.read_bytes(), str(GEN_PATH), "exec"), module.__dict__)
    return module


GEN = load_generator()


def run_main(main, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


def family_listing():
    """(relative name, sha256) of every family file: the family must be byte-identical after every test here."""
    rows = []
    for p in sorted(kit.FAMILY.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            rows.append((p.relative_to(kit.FAMILY).as_posix(), sha(p.read_bytes())))
    return rows


class Base(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="lotspatch34-", dir=kit.safe_temp_parent())))
        os.chmod(str(self.base), 0o700)
        self.before = family_listing()
        self.count = 0

    def tearDown(self):
        try:
            self.assertEqual(family_listing(), self.before, "the family changed")
        finally:
            shutil.rmtree(str(self.base), ignore_errors=True)

    def plans(self, grid, *, synthetic=False):
        """gen_k9_plans04 `plans` of `grid` into the temp dir (TEST-ONLY source pins, act B and GO)."""
        self.count += 1
        gen = load_generator()
        gen.source_pins = lambda tree: (gen.RISK_SOURCE_PINS_04, 190)      # TEST ONLY (module docstring)
        tag = "%s-%d" % (grid, self.count)
        if synthetic:
            out = self.base / ("plans-%s-SYNTHETIC" % tag)
            argv = ["plans", "--runner", str(RUNNER), "--grid", grid, "--app-tree", str(self.base), "--synthetic",
                    "--out", str(out)]
            go = None
        else:
            out = self.base / ("plans-%s" % tag)
            act_b, go = self.base / ("act_b-%s.TEST_ONLY.txt" % tag), self.base / ("go-%s.TEST_ONLY.json" % tag)
            act_b.write_bytes(b"TEST ONLY act B bytes, not the ADENDO\n")
            go.write_bytes(TEST_GO)
            argv = ["plans", "--runner", str(RUNNER), "--grid", grid, "--app-tree", str(self.base), "--act-b", str(act_b),
                    "--release", str(LOTS / "up_inputs" / "release.CERTIFIED.04.json"),
                    "--policy", str(LOTS / "up_inputs" / "policy.04.json"), "--go", str(go), "--out", str(out)]
        code, text = run_main(gen.main, argv)
        self.assertEqual(code, 0, text)
        self.assertIn("PLANS_OK", text)
        return out, go

    def module_file(self, name="verifier.TEST_ONLY.py"):
        path = self.base / name
        if not path.exists():
            path.write_bytes(bs.SYNTHETIC_MODULE)
        return path

    def values_for(self, spec):
        """A REAL-writer values map for every placeholder of `spec`: the same synthetic fill-ins as build_specs.fill."""
        doc = self.base / "doc.TEST_ONLY.json"
        doc.write_bytes(b'{"synthetic":true}')
        files = {local: rel for rel, local in spec["files"].items() if local.startswith("@P_")}
        named = {"@P_MANIFEST_DIRECTORY@": "/var/lib/c3po-capacity-e04/payload",
                 "@P_E6_DOCUMENT_PATH@": "/var/lib/c3po/r2d2-v2-k9-20261012/e6/E6_04.json",
                 "@P_J4_GENERAL_SOURCE_IDENTITY@": "SYNTHETIC_FILL_IN"}
        values = {}
        for name in bs.placeholders(spec):
            if name in files:
                values[name] = str(self.module_file() if files[name].endswith(".py") else doc)
            else:
                values[name] = named.get(name, sha(name.encode("ascii")))
        return values

    def write_values(self, values, name="values.json"):
        path = self.base / name
        path.write_text(json.dumps(values, sort_keys=True), "ascii")
        return path

    def real(self, lot, grid="C", *, out=None, plans=None, go=None, values=None, owner_deadline=None, up_real_dir=None):
        if plans is None:
            plans, go = self.plans(grid)
        if lot == "DOWN" and up_real_dir is None:      # v3.3 (F1): the DOWN needs the REAL UP dir of the same plans run
            up_real_dir = self.base / ("real-UP-for-DOWN-%d" % time.monotonic_ns())
            self.real("UP", out=up_real_dir, plans=plans, go=go)
        spec = bs.build_up(plans=str(plans), go=str(go)) if lot == "UP" else bs.build_down(plans=str(plans), go=str(go))
        values = self.values_for(spec) if values is None else values
        deadline = owner_deadline or ("2026-10-10T17:20:00Z" if lot == "UP" else "2026-10-12T00:44:00Z")
        return bs.write_real(lot, out or (self.base / ("real-%s" % lot)), plans_dir=str(plans), go=str(go),
                             layout_path=str(LAYOUT), secrets_root=bs.GEN_SECRETS_ROOT, networks=dict(bs.NETWORKS),
                             owner_deadline=deadline, values_path=str(self.write_values(values, "values-%s.json" % lot)),
                             up_real_dir=str(up_real_dir) if up_real_dir is not None else None)

    def refused(self, code, fn, *args, **kwargs):
        with self.assertRaises(rt.Hold) as caught:
            fn(*args, **kwargs)
        self.assertEqual(str(caught.exception), code)
        return caught.exception


# ====================================================================== L-01: the closed grid choice
class GridChoice(Base):
    def test_grid_tables_are_the_ruled_literals(self):
        self.assertEqual(GEN.ELECTABLE, ("C", "D"))
        self.assertEqual(set(GEN.GRIDS), {"C", "D", "DRAFT3_REJECTED"})
        c = {"prove_launch": "14:26:00", "collect_launch": "14:38:00", "commit_launch": "14:53:00",
             "publish_launch": "15:26:00", "components_launch": "15:38:00", "sources_launch": "16:26:00"}
        self.assertEqual(GEN.GRIDS["C"], {op: "2026-10-10 " + t for op, t in c.items()})
        for op in SIX:                                            # D = C one hour later, P1..X2 only
            self.assertEqual(GEN.brt(GEN.GRIDS["D"][op]) - GEN.brt(GEN.GRIDS["C"][op]), timedelta(hours=1))
        self.assertEqual(GEN.GRIDS["DRAFT3_REJECTED"]["publish_launch"], "2026-10-10 12:03:00")
        self.assertEqual(GEN.FIXED, {"bind": "2026-10-10 21:26:00", "preflight": "2026-10-10 21:28:00",
                                     "acquire_launch": "2026-10-10 21:38:00", "execute_launch": "2026-10-10 22:48:00",
                                     "stage": "2026-10-10 23:26:00", "capture_launch": "2026-10-12 10:52:00"})
        utc = {g: {r["slot"]: r["starts_at_utc"] for r in GEN.grid_block(g)["slots"]} for g in ("C", "D")}
        self.assertEqual((utc["C"]["P1"], utc["C"]["P4"], utc["D"]["P1"], utc["D"]["X2"]),
                         ("2026-10-10T17:26:00+00:00", "2026-10-10T18:26:00+00:00", "2026-10-10T18:26:00+00:00",
                          "2026-10-10T20:26:00+00:00"))
        for g in GEN.GRIDS:
            self.assertEqual(list(GEN.schedule(g)), list(GEN.STEPS))
            self.assertEqual([r["slot"] for r in GEN.grid_block(g)["slots"]],
                             ["P1", "P2", "P3", "P4", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "C1"])

    def test_check_validates_c_and_d_with_the_family_engine(self):
        engine = sha((kit.FAMILY / "l12host_effect.py").read_bytes())
        for grid in ("C", "D"):
            code, text = run_main(GEN.main, ["check", "--runner", str(RUNNER), "--grid", grid])
            self.assertEqual(code, 0, text)
            self.assertIn("SCHEDULE_OK runner_sha256=%s grid=%s engine_sha256=%s" % (sha(RUNNER.read_bytes()), grid, engine),
                          text)

    def test_check_refuses_draft3_by_the_engine_start_window(self):
        code, text = run_main(GEN.main, ["check", "--runner", str(RUNNER), "--grid", "DRAFT3_REJECTED"])
        self.assertEqual((code, text.strip()), (2, "REFUSED START_WINDOW_NOT_ALLOWED:publish_launch"))

    def test_plans_refuses_draft3_rejected_and_writes_nothing(self):
        out = self.base / "plans-DRAFT3-SYNTHETIC"
        for argv in (["plans", "--runner", str(RUNNER), "--grid", "DRAFT3_REJECTED", "--app-tree", str(self.base),
                      "--synthetic", "--out", str(out)],
                     ["plans", "--runner", str(RUNNER), "--grid", "DRAFT3_REJECTED", "--app-tree", str(self.base),
                      "--act-b", str(RUNNER), "--release", str(RUNNER), "--policy", str(RUNNER), "--go", str(RUNNER),
                      "--out", str(self.base / "plans-DRAFT3")]):
            code, text = run_main(GEN.main, argv)
            self.assertEqual((code, text.strip()), (2, "REFUSED GRID_REJECTED_BY_CODEX:DRAFT3_REJECTED"))
        self.assertFalse(out.exists() or (self.base / "plans-DRAFT3").exists())
        with self.assertRaisesRegex(GEN.Refused, "GRID_REJECTED_BY_CODEX:DRAFT3_REJECTED"):
            GEN.build(RUNNER.read_bytes(), str(self.base), "a1" * 32, "fc" * 32, "d2" * 32, GEN.SYNTHETIC_GO, True,
                      "DRAFT3_REJECTED")

    def test_grid_is_explicit_and_closed(self):
        base = ["plans", "--runner", str(RUNNER), "--app-tree", str(self.base), "--synthetic",
                "--out", str(self.base / "x-SYNTHETIC")]
        for extra, code in (([], "GRID_REQUIRED"), (["--grid", "A"], "GRID_NOT_IN_THE_CLOSED_CHOICE"),
                            (["--grid", "c"], "GRID_NOT_IN_THE_CLOSED_CHOICE"),
                            (["--grid", "B"], "GRID_NOT_IN_THE_CLOSED_CHOICE")):
            self.assertEqual(run_main(GEN.main, base + extra), (2, "REFUSED %s\n" % code))
        self.assertEqual(run_main(GEN.main, ["check", "--runner", str(RUNNER)]), (2, "REFUSED GRID_REQUIRED\n"))
        self.assertFalse((self.base / "x-SYNTHETIC").exists())

    def test_every_start_window_is_allowed_by_the_engine_itself(self):
        """Independent of the generator's own check: kit.fx (the family's l12host_effect) on every second of
        [at, at + 60 s] + 45 s of every start of C and D; DRAFT3's P4 is refused 40 s after its instant."""
        margins = {}
        for grid in ("C", "D", "DRAFT3_REJECTED"):
            for op, (start, *_rest) in GEN.schedule(grid).items():
                at = GEN.brt(start)
                bad = [k for k in range(0, 60 + 45 + 1) if fx.start_minute_violation(at + timedelta(seconds=k))]
                margins[grid, op] = bad[0] if bad else None
        for grid in ("C", "D"):
            self.assertEqual([op for op in GEN.STEPS if margins[grid, op] is not None], [], grid)
        self.assertEqual([op for op in GEN.STEPS if margins["DRAFT3_REJECTED", op] is not None], ["publish_launch"])
        self.assertEqual(margins["DRAFT3_REJECTED", "publish_launch"], 40)
        rule, _ = GEN.engine_rule()
        expect = {"C": [460, 1540, 640, 460, 1540, 460], "D": [460, 1540, 640, 460, 1540, 460]}
        for grid in ("C", "D"):
            got = [GEN.start_margin(GEN.brt(GEN.GRIDS[grid][op]), rule) for op in SIX]
            self.assertEqual(got, expect[grid])
        self.assertEqual([GEN.start_margin(GEN.brt(GEN.FIXED[op]), rule) for op in FIXED_OPS], [460, 340, 1540, 940, 460, 700])

    def test_generator_rule_is_the_engine_function(self):
        rule, digest = GEN.engine_rule()
        self.assertEqual(digest, sha((kit.FAMILY / "l12host_effect.py").read_bytes()))
        day0 = datetime(2026, 10, 10, 3, 0, tzinfo=GEN.UTC)                 # 00:00 BRT
        for s in range(0, 2 * 86400, 7):
            t = day0 + timedelta(seconds=s)
            self.assertEqual(rule(t), fx.start_minute_violation(t))
        # the engine's late tolerance is read from the runtime next to it and must be the ruled 60 s
        fake = self.base / "engine"
        fake.mkdir()
        shutil.copyfile(str(kit.FAMILY / "l12host_effect.py"), str(fake / "l12host_effect.py"))
        (fake / "l12host_runtime.py").write_text("EARLY_SECONDS, LATE_SECONDS = 2, 90\n", "ascii")
        with self.assertRaisesRegex(GEN.Refused, "ENGINE_LATE_TOLERANCE_NOT_THE_RULED_ONE"):
            GEN.engine_rule(str(fake / "l12host_effect.py"))
        with self.assertRaisesRegex(GEN.Refused, "ENGINE_RULE_UNAVAILABLE"):
            GEN.engine_rule(str(self.base / "absent" / "l12host_effect.py"))

    def test_plans_carry_the_grid_and_keep_every_fixed_instant(self):
        draft = json.loads((LOTS / bs.PLANS / "K9_04_STEP_SET_MANIFEST.json").read_bytes())
        plan_keys = GEN.runner_literals(RUNNER.read_bytes())["PLAN_KEYS"]
        outs = {}
        for grid in ("C", "D"):
            out, _ = self.plans(grid, synthetic=True)
            outs[grid] = out
            block = GEN.grid_block(grid)
            request = json.loads((out / "K9_04_STEP_SET_REQUEST.json").read_bytes())
            manifest = json.loads((out / "K9_04_STEP_SET_MANIFEST.json").read_bytes())
            self.assertEqual((request["grid"], manifest["grid"]), (block, block))
            self.assertEqual(manifest["engine_rule"]["sha256"], sha((kit.FAMILY / "l12host_effect.py").read_bytes()))
            self.assertEqual(manifest["request_sha256"], sha((out / "K9_04_STEP_SET_REQUEST.json").read_bytes()))
            table = {r["operation"]: r for r in block["slots"]}
            for op, step in manifest["steps"].items():
                raw = (out / "plans" / (op + ".json")).read_bytes()
                plan = json.loads(raw)
                self.assertEqual(set(plan), plan_keys)                     # the runner's validate(): PLAN_KEYS exact
                self.assertIsInstance(plan["step_row"], dict)
                self.assertEqual(plan["step_row"]["grid"], block)
                self.assertEqual(plan["step_row"]["starts_at"], table[op]["starts_at_utc"])
                self.assertEqual((step["plan_sha256"], step["starts_at_utc"], step["slot"]),
                                 (sha(raw), table[op]["starts_at_utc"], table[op]["slot"]))
                self.assertGreater(step["start_margin_seconds"], 105)
                if op in FIXED_OPS:                                        # unchanged by the grid choice
                    old = draft["steps"][op]
                    for key in ("starts_at_utc", "starts_at_brt", "budget_seconds", "run_not_after", "runner_stops_at",
                                "kill_seconds", "requires", "packaged_phase", "mode", "network_class", "l12_task"):
                        self.assertEqual(step[key], old[key], (grid, op, key))
            cap = manifest["steps"]["capture_launch"]
            self.assertEqual((cap["starts_at_brt"], cap["run_not_after"], cap["kill_seconds"]),
                             ("2026-10-12 10:52:00", "2026-10-12T14:03:00+00:00", 655))
        c = json.loads((outs["C"] / "K9_04_STEP_SET_MANIFEST.json").read_bytes())["steps"]
        d = json.loads((outs["D"] / "K9_04_STEP_SET_MANIFEST.json").read_bytes())["steps"]
        for op in SIX:
            self.assertEqual(GEN.utc(d[op]["starts_at_utc"]) - GEN.utc(c[op]["starts_at_utc"]), timedelta(hours=1))
        for op in FIXED_OPS:
            self.assertEqual(c[op]["starts_at_utc"], d[op]["starts_at_utc"])


# ====================================================================== L-06: REAL specs outside the family
class RealSpecs(Base):
    def test_out_dir_inside_the_family_is_refused_before_anything(self):
        def attempt(out):
            return bs.write_real("UP", out, plans_dir="/nonexistent", go="/nonexistent", layout_path=str(LAYOUT),
                                 secrets_root=bs.GEN_SECRETS_ROOT, networks=dict(bs.NETWORKS),
                                 owner_deadline="2026-10-10T17:20:00Z", values_path="/nonexistent")
        cases = [LOTS / "REAL_UP", kit.FAMILY / "real" / "deeper" / "UP", kit.FAMILY, LOTS]
        link = self.base / "link-into-the-family"
        os.symlink(str(LOTS), str(link))
        cases.append(link / "REAL_UP")
        variant = Path(str(kit.FAMILY).upper())
        if variant != kit.FAMILY and os.path.exists(str(variant)):       # case-insensitive file system (macOS default)
            cases.append(variant / "lots" / "REAL_UP")
        top = kit.FAMILY.parent / "SHA256SUMS"
        if top.exists() and ("  %s/SHA256SUMS" % kit.FAMILY.name) in top.read_text("ascii"):
            cases.append(kit.FAMILY.parent / "real-specs" / "UP")     # the sealed delivery around the family
        for out in cases:
            with self.subTest(out=str(out)):
                self.refused("REAL_SPEC_OUT_DIR_INSIDE_FAMILY", attempt, out)
                self.assertFalse(os.path.lexists(str(out)) and out not in (kit.FAMILY, LOTS))
        existing = self.base / "already-there"
        existing.mkdir()
        self.refused("REAL_SPEC_OUT_DIR_EXISTS", attempt, existing)

    def test_real_up_is_written_outside_validated_and_binds(self):
        out = self.base / "real-UP"
        result = self.real("UP", "C", out=out)
        self.assertEqual((result["status"], result["lot"], result["grid"], result["spec"]),
                         ("REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY", "UP", "C", "UP.SPEC.json"))
        windows = {r["slot"]: r for r in result["start_windows"]}
        self.assertEqual({s: windows[s]["at"] for s in ("P1", "P4", "X2", "X7")},
                         {"P1": "2026-10-10T17:26:00Z", "P4": "2026-10-10T18:26:00Z", "X2": "2026-10-10T19:26:00Z",
                          "X7": "2026-10-11T02:26:00Z"})
        self.assertTrue(all(r["ok"] for r in result["start_windows"]))
        self.assertEqual(windows["P4"]["margin_seconds"], 460)
        sums = (out / "SHA256SUMS").read_bytes()
        self.assertEqual(sha(sums), result["sha256sums_sha256"])
        listed = {rel: digest for digest, rel in (line.split("  ", 1) for line in sums.decode("ascii").splitlines())}
        present = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()} - {"SHA256SUMS"}
        self.assertEqual(set(listed), present)
        self.assertEqual(len(listed), result["files"])
        for rel, digest in listed.items():
            self.assertEqual(sha((out / rel).read_bytes()), digest)
            self.assertEqual(os.stat(str(out / rel)).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(str(out)).st_mode & 0o777, 0o700)
        spec = json.loads((out / "UP.SPEC.json").read_bytes())
        self.assertEqual(set(spec), bind.SPEC_KEYS)                       # the bare spec `bind lot --spec` reads
        self.assertEqual(spec["files"], {rel: rel for rel in spec["files"]})
        self.assertEqual(bs.placeholders(spec), set())
        self.assertEqual(bs.check_real(str(out), str(LAYOUT))["status"], "REAL_SPEC_DIR_VALID")
        # bind_l12host lot reads the written dir as is (physical mode)
        lay = bind.loose_json(LAYOUT)
        runtime = self.base / "runtime.json"
        runtime.write_bytes(bs.runtime_stub(lay))
        stage = self.base / "stage-UP"
        umask = os.umask(0o077)
        try:                                                              # bind_l12host.write_out sets umask 077
            written = bind.lot(str(out / "UP.SPEC.json"), str(LAYOUT), str(runtime), "2026-10-10T17:00:00Z", str(stage),
                               physical=True)
        finally:
            os.umask(umask)
        self.assertTrue({"authority.json", "request.json", "question.txt", "k9/publish_launch.json"} <= set(written))
        authority = json.loads((stage / "authority.json").read_bytes())
        self.assertEqual({s["slot"]: s["at"] for s in authority["slots"]}["P4"], "2026-10-10T18:26:00Z")
        # a changed byte in the written dir is caught by `validate --out-dir`
        target = out / "k9" / "publish_launch.json"
        os.chmod(str(target), 0o600)
        target.write_bytes(target.read_bytes() + b" ")
        self.refused("REAL_DIR_BYTES_MISMATCH", bs.check_real, str(out), str(LAYOUT))

    def test_real_up_grid_d_through_the_command_line(self):
        plans, go = self.plans("D")
        spec = bs.build_up(plans=str(plans), go=str(go))
        values = self.write_values(self.values_for(spec))
        out = self.base / "real-UP-D"
        argv = ["write", "--out-dir", str(out), "--lot", "UP", "--plans-dir", str(plans), "--go", str(go),
                "--layout", str(LAYOUT), "--secrets-root", bs.GEN_SECRETS_ROOT, "--network", "PROVIDER=bridge",
                "--network", "DATABASE=c3po_default", "--network", "DATABASE_AND_PROVIDER=c3po_default",
                "--owner-deadline", "2026-10-10T18:20:00Z", "--values", str(values)]
        code, text = run_main(bs.main, argv)
        self.assertEqual(code, 0, text)
        result = json.loads(text)
        self.assertEqual((result["status"], result["grid"]), ("REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY", "D"))
        self.assertEqual({r["slot"]: r["at"] for r in result["start_windows"]}["P1"], "2026-10-10T18:26:00Z")
        code, text = run_main(bs.main, ["validate", "--out-dir", str(out), "--layout", str(LAYOUT)])
        self.assertEqual((code, json.loads(text)["status"]), (0, "REAL_SPEC_DIR_VALID"))
        code, text = run_main(bs.main, argv)                              # the same dir again: O_EXCL
        self.assertEqual((code, json.loads(text)["code"]), (2, "REAL_SPEC_OUT_DIR_EXISTS"))
        bad = list(argv)
        bad[bad.index(str(out))] = str(LOTS / "REAL")
        code, text = run_main(bs.main, bad)
        self.assertEqual((code, json.loads(text)["code"]), (2, "REAL_SPEC_OUT_DIR_INSIDE_FAMILY"))

    def test_real_down_is_written_outside_with_the_moved_po(self):
        out = self.base / "real-DOWN"
        result = self.real("DOWN", "C", out=out)
        self.assertEqual((result["status"], result["lot"], result["spec"]),
                         ("REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY", "DOWN", "DOWN.SPEC.json"))
        windows = {r["slot"]: r for r in result["start_windows"]}
        self.assertEqual((windows["PO"]["at"], windows["PO"]["margin_seconds"]), ("2026-10-12T09:01:30Z", 130))
        self.assertTrue(all(r["ok"] for r in result["start_windows"]))
        self.assertEqual(bs.check_real(str(out), str(LAYOUT))["status"], "REAL_SPEC_DIR_VALID")
        spec = json.loads((out / "DOWN.SPEC.json").read_bytes())
        self.assertEqual(bs.placeholders(spec), set())

    def test_real_writer_refusals_leave_nothing(self):
        plans, go = self.plans("C")
        spec = bs.build_up(plans=str(plans), go=str(go))
        values = self.values_for(spec)

        def attempt(code, name, **kw):
            out = self.base / name
            args = dict(plans=plans, go=go, values=values)
            args.update(kw)
            self.refused(code, self.real, "UP", out=out, **args)
            self.assertFalse(os.path.lexists(str(out)), name)
        attempt("REAL_PLANS_GRID_NOT_ELECTED", "r-draft", plans=LOTS / bs.PLANS)   # the in-family DRAFT3 plans
        syn, _ = self.plans("C", synthetic=True)
        attempt("REAL_PLANS_SYNTHETIC", "r-synthetic", plans=syn)
        other = self.base / "other-go.json"
        other.write_bytes(b'{"schema":"ANOTHER_TEST_ONLY_GO"}\n')
        attempt("REAL_GO_NOT_THE_MANIFEST_ONE", "r-go", go=other)
        missing = dict(values)
        missing.pop(bs.VERIFIERS_PLACEHOLDER)
        attempt("REAL_SPEC_PLACEHOLDER_UNFILLED", "r-missing", values=missing)
        attempt("REAL_VALUES_UNKNOWN_PLACEHOLDER", "r-extra", values=dict(values, **{"@P_NOT_OF_THIS_LOT@": "x"}))
        attempt("REAL_INPUT_NOT_A_REGULAR_FILE", "r-file", values={bs.VERIFIERS_PLACEHOLDER: str(self.base / "absent.py")})
        tampered = self.base / "plans-tampered"
        shutil.copytree(str(plans), str(tampered))
        victim = tampered / "plans" / "publish_launch.json"
        os.chmod(str(victim), 0o600)
        victim.write_bytes(victim.read_bytes().replace(b'"PRIMARY"', b'"SPARE"'))
        attempt("REAL_PLAN_NOT_THE_MANIFEST_ONE", "r-tampered", plans=tampered)
        # the owner deadline must precede every effect window (grid C: P1 window opens 17:25:30Z)
        attempt("OWNER_DEADLINE_AFTER_EFFECT_WINDOW", "r-deadline", owner_deadline="2026-10-10T17:26:00Z")
        # a slot whose start window is not wholly allowed is refused (the in-family DRAFT3 UP spec's P4)
        error = self.refused("REAL_SLOT_START_WINDOW_NOT_ALLOWED", bs.windows_or_refuse, bs.build_up())
        self.assertEqual(error.detail, ["P4"])

    def test_in_family_drafts_are_reproduced_by_write(self):
        self.assertEqual(bs.render(bs.build_up(), bs.UP_COMMENT), (LOTS / "UP.SPEC.json").read_bytes())
        self.assertEqual(bs.render(bs.build_down(), bs.DOWN_COMMENT), (LOTS / "DOWN.SPEC.DRAFT.json").read_bytes())


# ====================================================================== L-02: the DOWN draft's PO
class DownPost(Base):
    def test_po_is_off_the_40_s_edge_and_keeps_its_dependencies(self):
        result = bs.validate_down(physical=True)
        self.assertEqual((result["status"], result["post_at"]), ("DOWN_DRAFT_VALID_WITH_FILL_INS", "2026-10-12T09:01:30Z"))
        windows = {r["slot"]: r for r in result["start_windows"]}
        self.assertTrue(all(r["ok"] for r in result["start_windows"]), result["start_windows"])
        self.assertEqual({s: windows[s]["margin_seconds"] for s in windows},
                         {"E6": 160, "PO": 130, "J1": 1540, "J2": 1360, "J3": 1180, "R0": 220, "S1": 278, "C1": 700})
        order = [r["slot"] for r in result["start_windows"]]
        self.assertLess(order.index("E6"), order.index("PO"))
        self.assertLess(order.index("PO"), order.index("J1"))
        self.assertGreaterEqual((rt.stamp(windows["PO"]["at"]) - rt.stamp(windows["E6"]["at"])).total_seconds(),
                                rt.SLOT_SPACING_SECONDS)
        post = [t for t in bs.build_down()["tasks"] if t["operation"] == "post"][0]
        self.assertEqual((post["not_before"], post["not_after"], post["budget_seconds"], post["requires"]),
                         ("2026-10-12T09:01:00Z", "2026-10-12T09:03:30Z", 60, ["publish_launch"]))
        session = [s for s in bs.build_down()["extended"]["steps"] if s["step"] == "session_start"][0]
        self.assertIn(["core", "post"], session["requires"])
        at = rt.stamp("2026-10-12T09:01:30Z")
        self.assertEqual([k for k in range(0, 106) if fx.start_minute_violation(at + timedelta(seconds=k))], [])
        old = rt.stamp("2026-10-12T09:03:00Z")
        self.assertEqual(bs.start_margin(old), 40)
        draft = json.loads((LOTS / "DOWN.SPEC.DRAFT.json").read_bytes())["spec"]
        self.assertEqual([t["slots"] for t in draft["tasks"] if t["operation"] == "post"],
                         [[{"slot": "PO", "at": "2026-10-12T09:01:30Z"}]])

    def test_real_writer_refuses_the_former_po_instant(self):
        """The REAL writer refuses a slot whose [at, at + 60 s] + 45 s is not wholly allowed: the former PO 06:03:00."""
        plans, go = self.plans("C")
        saved = (bs.PO_AT, bs.PO_NOT_BEFORE, bs.PO_NOT_AFTER)
        bs.PO_AT, bs.PO_NOT_BEFORE, bs.PO_NOT_AFTER = "2026-10-12T09:03:00Z", "2026-10-12T09:02:30Z", "2026-10-12T09:05:00Z"
        try:
            out = self.base / "real-DOWN-former-po"
            error = self.refused("REAL_SLOT_START_WINDOW_NOT_ALLOWED", self.real, "DOWN", out=out, plans=plans, go=go)
            self.assertEqual(error.detail, ["PO"])
            self.assertFalse(os.path.lexists(str(out)))
        finally:
            bs.PO_AT, bs.PO_NOT_BEFORE, bs.PO_NOT_AFTER = saved

    def test_up_draft_keeps_the_rejected_p4_only_as_a_record(self):
        result = bs.validate_up(physical=True)
        windows = {r["slot"]: r for r in result["start_windows"]}
        self.assertEqual((windows["P4"]["at"], windows["P4"]["margin_seconds"], windows["P4"]["ok"]),
                         ("2026-10-10T15:03:00Z", 40, False))
        self.assertEqual([s for s, r in windows.items() if not r["ok"]], ["P4"])


def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for case in (GridChoice, RealSpecs, DownPost):
        suite.addTests(loader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    print(json.dumps({"schema": "L12HOST_LOTS_PATCH_V34_TEST_RESULT", "python": "%d.%d.%d" % sys.version_info[:3],
                      "platform": sys.platform, "tests": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "skipped": len(result.skipped), "ok": result.wasSuccessful(),
                      "temp_parent": dict(kit.TEMP_PARENT)}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
