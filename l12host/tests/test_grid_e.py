"""L12-HOST grid-E patch suite: grid E of gen_k9_plans04 as a literal capability and documentary reserve (Codex #429
6098340344), with D (elected; own GO 757c3096... over request efb94cf2...) byte-preserved. SYNTHETIC only: no host,
network, provider, image, container or secret; every output goes to a temporary directory and the family is checked
unchanged (the lots suite's base class).

    E  P1 16:26  P2 16:38  P3 16:53  P4 17:26  X1 17:38  X2 18:26 BRT (Saturday 10/10); X3-X7 and Monday's capture fixed

Run: python -I -S -B tests/test_grid_e.py   (one JSON summary on stdout, test names on stderr; exit 1 on failure)

Same TEST-ONLY substitution as tests/test_lots_patch_v34.py (`source_pins` returns the pinned de96aee9 value, the app
tree is not part of the family). The D request is rebuilt from the PUBLIC pins of the issued D chain (act B, release,
policy, runner, risk pins: hashes only, no document) and must be byte-identical to the issued request; the 12 D plans
are rebuilt over the issued GO's sha256 and must be the issued ones. With L12_ISSUED_D_DIR naming the issued D run
directory (k9/K9_GO_04.json, K9_04_STEP_SET_REQUEST.json, final-plans/), the originals themselves are re-read, pinned
and reproduced byte for byte (that one test is skipped without it: the issued run is not part of the family). Nothing
here elects E, issues or signs anything; E plans made here carry TEST-ONLY GO bytes and are never signed data.

v3.3g (root decision on this patch's review, finding 2): build_specs.ELECTED_GRIDS = C/D/E. The one test that asserted
the old C/D tuple (the REAL writer refused E plans) now asserts C/D/E and builds and validates a REAL UP and a REAL DOWN
lot of grid E end to end (SYNTHETIC REAL K9 inputs, as the lots suite does), and an E DOWN over a D UP stays refused.
"""
import json
import os
from pathlib import Path
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit                          # noqa: E402
import test_lots_patch_v34 as lots  # noqa: E402  (its Base: temp dir, plans, real; family unchanged)

fx, bs = kit.fx, lots.bs
SIX, FIXED_OPS, RUNNER, LOTS = lots.SIX, lots.FIXED_OPS, lots.RUNNER, lots.LOTS
E_BRT = {"prove_launch": "16:26:00", "collect_launch": "16:38:00", "commit_launch": "16:53:00",
         "publish_launch": "17:26:00", "components_launch": "17:38:00", "sources_launch": "18:26:00"}
SLOTS_SHA256 = {"C": "8da175aebf14fc1dac941c33de0f3c05b9b2bf0c436842619db3b4d9f88d9fc3",
                "D": "4497a1ec3ae026036b112a72678c3cb4a3597a236058b90b6c39b889d32ec536",
                "E": "65839e19ed2756abf96d9d68898b21f452505de07e4f006db5ca4258d20d96fb"}
# the issued D chain (fable-k9go04-issued-20261010; hashes only)
ACT_B_SHA256 = "23d5099e5b008bff63f07e5d1d3b170167540f27046c40d868593efa835020f9"
REQUEST_D_SHA256 = "efb94cf20ae8dccd2d2a6c7d258d0577ff6eb9b8fd1b0f235328d8256296822f"
REQUEST_C_SHA256 = "80bf912ce72ab4d2ccd7f951c37490ff51a78a991dc43b78719633b25c0216bd"       # k9go04 tests' grid-C request (same constants)
GO_D_SHA256 = "757c30963061ef80572dc89bcbaafb679f1249b96dd6840ce7993d80a545f136"
MANIFEST_D_SHA256 = "974eb8aa100798b856c5f1246d88e37705336a4a7550bc6a28b108f86af91b50"     # recorded with the v3.2 engine below
ENGINE_V32_SHA256 = "46948fca9ebe25220c6035e1d3266ea814610793cb58255b77efed399eecaac3"
PLANS_D_SHA256 = {
    "acquire_launch": "536efcbac46473207d92c62d3a0347a099bde7b5bbeb5683d253ea7fed6c0a74",
    "bind": "48f6b1080ede75ba37720a54ebba1326e46e751b592fee212e5784a2587deb19",
    "capture_launch": "5599c105f3717ca969aca52a2bf598eb34c829d195d16219400ffd0c09cd7c20",
    "collect_launch": "f9fb049e01834c41b1673a88c49b29e8906bf79d5f6d915aa98b77b08b871ff5",
    "commit_launch": "27f64f4abb547b92fae58a19580f03d826fd7827c0484a62d4501233739bd7ec",
    "components_launch": "5393c57b5dd38542886d1678f478737abfeb3843c7503683ca6cf32171462617",
    "execute_launch": "41c414c14d2f3d10365329ae0ae3c439cc7a9503d4d053bc2b16851115bdac6b",
    "preflight": "6b0fa9b6e3cccab2f2cb74abb527056ef0908b7e8959f7dc0e414fd4b18561c2",
    "prove_launch": "01e7781edeb2a840b05f27113e330b8f3a8390df22fbc502996f716590dcd5af",
    "publish_launch": "50007483887249d9be6f372aed2793df1d33b76b08b4128e39a8d856890e54c8",
    "sources_launch": "ede7064f2263d3f75d50175aebc2d09559b086ed44df17f9cf1c4b409e32359c",
    "stage": "f7fc042b8947ded3e9f344cf36b09fb364df14460e938acb20b812775b791829"}
ISSUED_D_DIR = os.environ.get("L12_ISSUED_D_DIR")


def sha(raw):
    return lots.sha(raw)


def generator():
    """A fresh generator module with the TEST-ONLY source pins (module docstring)."""
    gen = lots.load_generator()
    gen.source_pins = lambda tree: (gen.RISK_SOURCE_PINS_04, 190)
    return gen


def certified():
    """(act B, release, policy) sha256 of the issued D chain; release/policy are the family's certified inputs."""
    release = sha((LOTS / "up_inputs" / "release.CERTIFIED.04.json").read_bytes())
    policy = sha((LOTS / "up_inputs" / "policy.04.json").read_bytes())
    assert (release, policy) == (bs.RELEASE, bs.POLICY)
    return ACT_B_SHA256, release, policy


def composed_plans(gen, grid, go_sha256):
    """build()'s own steps up to the plans, over a GO given by its sha256 (the plans pin the GO only by sha256)."""
    raw = RUNNER.read_bytes()
    rule, _ = gen.engine_rule()
    literals = gen.runner_literals(raw)
    rows = gen.timeline(literals, grid, rule)
    constants = gen.constants_of(literals, sha(raw), gen.RISK_SOURCE_PINS_04, *certified())
    request = gen.request_doc(literals, rows, constants, False, grid)
    return request, {op: gen.plan_doc(op, literals, rows, constants, sha(request), go_sha256, grid) for op in gen.STEPS}


class GridE(lots.Base):
    def test_e_is_the_accepted_literal_table(self):
        gen = generator()
        self.assertEqual(gen.ELECTABLE, ("C", "D", "E"))
        self.assertEqual(set(gen.GRIDS), {"C", "D", "E", "DRAFT3_REJECTED"})
        self.assertEqual(gen.GRIDS["E"], {op: "2026-10-10 " + t for op, t in E_BRT.items()})
        for op in SIX:                                            # E = D + 1 h = C + 2 h, P1..X2 only
            self.assertEqual(gen.brt(gen.GRIDS["E"][op]) - gen.brt(gen.GRIDS["D"][op]), timedelta(hours=1))
            self.assertEqual(gen.brt(gen.GRIDS["E"][op]) - gen.brt(gen.GRIDS["C"][op]), timedelta(hours=2))
        self.assertEqual(list(gen.schedule("E")), list(gen.STEPS))
        block = gen.grid_block("E")
        self.assertEqual([r["slot"] for r in block["slots"]], ["P1", "P2", "P3", "P4", "X1", "X2", "X3", "X4", "X5",
                                                               "X6", "X7", "C1"])
        utc = {r["slot"]: r["starts_at_utc"] for r in block["slots"]}
        self.assertEqual((utc["P1"], utc["P4"], utc["X2"], utc["X3"], utc["C1"]),
                         ("2026-10-10T19:26:00+00:00", "2026-10-10T20:26:00+00:00", "2026-10-10T21:26:00+00:00",
                          "2026-10-11T00:26:00+00:00", "2026-10-12T13:52:00+00:00"))
        d = {r["operation"]: r for r in gen.grid_block("D")["slots"]}
        for row in block["slots"]:
            if row["operation"] in FIXED_OPS:
                self.assertEqual(row, d[row["operation"]])
        self.assertEqual({g: gen.grid_block(g)["slots_sha256"] for g in ("C", "D", "E")}, SLOTS_SHA256)

    def test_check_validates_e_with_the_family_engine(self):
        gen = generator()
        engine = sha((kit.FAMILY / "l12host_effect.py").read_bytes())
        code, text = lots.run_main(gen.main, ["check", "--runner", str(RUNNER), "--grid", "E"])
        self.assertEqual(code, 0, text)
        self.assertIn("GRID E slots_sha256=%s start_window=[at, at+60 s]+45 s" % SLOTS_SHA256["E"], text)
        self.assertIn("SCHEDULE_OK runner_sha256=%s grid=E engine_sha256=%s" % (sha(RUNNER.read_bytes()), engine), text)
        sys.stderr.write("GRID_E_SLOTS_SHA256 %s\n" % SLOTS_SHA256["E"])

    def test_e_start_windows_margins_and_the_critical_window(self):
        """Independent of the generator: kit.fx (the family's engine) on every second of [at, at + 60 s] + 45 s of every
        E start. The critical 18:58:40-19:25:59 BRT refuses STARTS only: X2 starts 18:26 (window ends 18:27:45) and its
        budget ends 19:41 BRT, before X3 21:26."""
        gen = generator()
        for op, (start, *_rest) in gen.schedule("E").items():
            at = gen.brt(start)
            self.assertEqual([k for k in range(0, 60 + 45 + 1) if fx.start_minute_violation(at + timedelta(seconds=k))],
                             [], op)
        rule, _ = gen.engine_rule()
        self.assertEqual([gen.start_margin(gen.brt(gen.GRIDS["E"][op]), rule) for op in SIX],
                         [460, 1540, 640, 460, 1540, 460])
        self.assertEqual([gen.start_margin(gen.brt(gen.FIXED[op]), rule) for op in FIXED_OPS], [460, 340, 1540, 940, 460, 700])
        x2 = gen.brt(gen.GRIDS["E"]["sources_launch"])
        end = x2 + timedelta(seconds=gen.STEPS["sources_launch"][0])
        self.assertEqual(end.strftime("%H:%M:%S"), "19:41:00")
        self.assertLess(end, gen.brt(gen.FIXED["bind"]))
        self.assertEqual(fx.start_minute_violation(gen.brt("2026-10-10 18:58:40")), "START_IN_CRITICAL_WINDOW")
        self.assertEqual(fx.start_minute_violation(gen.brt("2026-10-10 19:00:00")), "START_IN_CRITICAL_WINDOW")
        self.assertIsNone(fx.start_minute_violation(gen.brt("2026-10-10 18:58:39")))
        self.assertIsNone(fx.start_minute_violation(gen.brt("2026-10-10 19:26:00")))
        rows = gen.timeline(gen.runner_literals(RUNNER.read_bytes()), "E", rule)
        self.assertLess(rows["sources_launch"]["at"], gen.brt("2026-10-10 18:58:40"))
        self.assertGreater(rows["sources_launch"]["run_not_after"], gen.brt("2026-10-10 19:25:59"))
        self.assertEqual(gen.iso(rows["sources_launch"]["run_not_after"]), "2026-10-10T22:40:30+00:00")
        self.assertEqual((rows["bind"]["at"] - rows["sources_launch"]["run_not_after"]).total_seconds(), 6330)
        self.assertEqual({op: r["margin"] for op, r in rows.items() if op in SIX},
                         dict(zip(SIX, [460, 1540, 640, 460, 1540, 460])))

    def test_e_plans_carry_e_and_keep_every_fixed_instant(self):
        outs = {}
        for grid in ("D", "E"):
            out, _ = self.plans(grid, synthetic=True)
            outs[grid] = json.loads((out / "K9_04_STEP_SET_MANIFEST.json").read_bytes())
            request = json.loads((out / "K9_04_STEP_SET_REQUEST.json").read_bytes())
            self.assertEqual((request["grid"]["id"], outs[grid]["grid"]["id"]), (grid, grid))
            self.assertEqual(request["grid"]["slots_sha256"], SLOTS_SHA256[grid])
        d, e = outs["D"]["steps"], outs["E"]["steps"]
        for op in SIX:
            self.assertEqual(lots.GEN.utc(e[op]["starts_at_utc"]) - lots.GEN.utc(d[op]["starts_at_utc"]), timedelta(hours=1))
            for key in ("budget_seconds", "kill_seconds", "mode", "network_class", "requires", "start_margin_seconds"):
                self.assertEqual(e[op][key], d[op][key], (op, key))
        for op in FIXED_OPS:
            for key in ("starts_at_utc", "starts_at_brt", "budget_seconds", "run_not_after", "runner_stops_at",
                        "kill_seconds", "requires", "packaged_phase", "mode", "network_class", "l12_task"):
                self.assertEqual(e[op][key], d[op][key], (op, key))
        self.assertEqual(e["capture_launch"]["kill_seconds"], 655)

    def test_e_plans_with_a_test_only_go(self):
        out, go = self.plans("E")
        manifest = json.loads((out / "K9_04_STEP_SET_MANIFEST.json").read_bytes())
        request = json.loads((out / "K9_04_STEP_SET_REQUEST.json").read_bytes())
        self.assertIs(request["synthetic"], False)
        self.assertEqual(manifest["go_sha256"], sha(go.read_bytes()))
        self.assertEqual(manifest["grid"], lots.GEN.grid_block("E"))
        for op, step in manifest["steps"].items():
            plan = json.loads((out / "plans" / (op + ".json")).read_bytes())
            self.assertEqual(plan["step_row"]["grid"]["id"], "E")
            self.assertGreater(step["start_margin_seconds"], 105)

    def test_c_still_validates_and_draft3_still_refused(self):
        gen = generator()
        code, text = lots.run_main(gen.main, ["check", "--runner", str(RUNNER), "--grid", "C"])
        self.assertEqual(code, 0, text)
        self.assertIn("GRID C slots_sha256=%s" % SLOTS_SHA256["C"], text)
        code, text = lots.run_main(gen.main, ["check", "--runner", str(RUNNER), "--grid", "DRAFT3_REJECTED"])
        self.assertEqual((code, text.strip()), (2, "REFUSED START_WINDOW_NOT_ALLOWED:publish_launch"))
        out = self.base / "plans-DRAFT3-SYNTHETIC"
        code, text = lots.run_main(gen.main, ["plans", "--runner", str(RUNNER), "--grid", "DRAFT3_REJECTED", "--app-tree",
                                              str(self.base), "--synthetic", "--out", str(out)])
        self.assertEqual((code, text.strip()), (2, "REFUSED GRID_REJECTED_BY_CODEX:DRAFT3_REJECTED"))
        self.assertFalse(os.path.lexists(str(out)))
        for bad in ("e", "F", "E ", "DE"):
            code, text = lots.run_main(gen.main, ["check", "--runner", str(RUNNER), "--grid", bad])
            self.assertEqual((code, text.strip()), (2, "REFUSED GRID_NOT_IN_THE_CLOSED_CHOICE"), bad)

    def test_real_writer_builds_and_validates_e_up_and_down_lots(self):
        """v3.3g (root decision on this patch's review, finding 2): build_specs' REAL writer elects C/D/E, so a plans
        run of grid E becomes a REAL UP and a REAL DOWN lot end to end (SYNTHETIC REAL K9 inputs of the run, TEST-ONLY
        GO; physical build_lot before and after each write; `validate --out-dir` on both dirs). No automatic migration:
        an E DOWN never pairs with a D UP (F1 grid check, nothing written)."""
        self.assertEqual(bs.ELECTED_GRIDS, ("C", "D", "E"))
        plans, go = self.plans("E")
        up = self.base / "real-UP-E"
        result = self.real("UP", out=up, plans=plans, go=go, owner_deadline="2026-10-10T19:20:00Z")
        self.assertEqual((result["status"], result["lot"], result["grid"], result["grid_slots_sha256"]),
                         ("REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY", "UP", "E", SLOTS_SHA256["E"]))
        windows = {r["slot"]: r for r in result["start_windows"]}
        self.assertTrue(all(r["ok"] for r in result["start_windows"]), result["start_windows"])
        self.assertEqual({s: windows[s]["at"] for s in ("P1", "P4", "X1", "X2", "X3", "X7")},
                         {"P1": "2026-10-10T19:26:00Z", "P4": "2026-10-10T20:26:00Z", "X1": "2026-10-10T20:38:00Z",
                          "X2": "2026-10-10T21:26:00Z", "X3": "2026-10-11T00:26:00Z", "X7": "2026-10-11T02:26:00Z"})
        self.assertEqual([windows[s]["margin_seconds"] for s in ("P1", "P2", "P3", "P4", "X1", "X2")],
                         [460, 1540, 640, 460, 1540, 460])
        self.assertEqual(json.loads((up / bs.KILL_RECORD).read_bytes())["request"]["grid"], "E")
        code, text = lots.run_main(bs.main, ["validate", "--out-dir", str(up), "--layout", str(lots.LAYOUT)])
        self.assertEqual(code, 0, text)
        self.assertEqual(tuple(json.loads(text)[k] for k in ("status", "lot", "grid")), ("REAL_SPEC_DIR_VALID", "UP", "E"))
        down = self.base / "real-DOWN-E"
        result = self.real("DOWN", out=down, plans=plans, go=go, up_real_dir=up)
        self.assertEqual((result["status"], result["lot"], result["grid"]),
                         ("REAL_SPEC_WRITTEN_OUTSIDE_THE_FAMILY", "DOWN", "E"))
        self.assertTrue(all(r["ok"] for r in result["start_windows"]), result["start_windows"])
        cross = result["up_cross_check"]
        self.assertEqual((cross["grid"], cross["byte_identical"], cross["up_real_dir"]), ("E", True, str(up)))
        code, text = lots.run_main(bs.main, ["validate", "--out-dir", str(down), "--layout", str(lots.LAYOUT)])
        self.assertEqual(code, 0, text)
        self.assertEqual(tuple(json.loads(text)[k] for k in ("status", "lot", "grid")), ("REAL_SPEC_DIR_VALID", "DOWN", "E"))
        d_plans, d_go = self.plans("D")
        d_up = self.base / "real-UP-D"
        self.assertEqual(self.real("UP", out=d_up, plans=d_plans, go=d_go, owner_deadline="2026-10-10T18:20:00Z")["grid"], "D")
        mixed = self.base / "real-DOWN-E-over-UP-D"
        error = self.refused("REAL_DOWN_GRID_NOT_THE_UP_ONE", self.real, "DOWN", out=mixed, plans=plans, go=go,
                             up_real_dir=d_up)
        self.assertEqual(error.detail, ["D", "E"])
        self.assertFalse(os.path.lexists(str(mixed)))


class IssuedD(lots.Base):
    def test_d_and_c_request_bytes_are_the_issued_ones(self):
        gen = generator()
        act_b, release, policy = certified()
        for grid, expected in (("D", REQUEST_D_SHA256), ("C", REQUEST_C_SHA256)):
            result = gen.build(RUNNER.read_bytes(), str(self.base), act_b, release, policy, lots.TEST_GO, False, grid)
            self.assertEqual(sha(result["request"]), expected, grid)
            self.assertNotIn(b"go_sha256", result["request"])
        e = gen.build(RUNNER.read_bytes(), str(self.base), act_b, release, policy, lots.TEST_GO, False, "E")
        self.assertNotIn(sha(e["request"]), (REQUEST_D_SHA256, REQUEST_C_SHA256))

    def test_e_request_differs_from_d_only_in_the_six_minutes(self):
        gen = generator()
        act_b, release, policy = certified()
        d, e = (json.loads(gen.build(RUNNER.read_bytes(), str(self.base), act_b, release, policy, lots.TEST_GO, False,
                                     g)["request"]) for g in ("D", "E"))
        self.assertEqual({k: v for k, v in d.items() if k not in ("grid", "steps")},
                         {k: v for k, v in e.items() if k not in ("grid", "steps")})
        steps_d, steps_e = ({s["operation"]: s for s in x["steps"]} for x in (d, e))
        for op in gen.STEPS:
            if op in FIXED_OPS:
                self.assertEqual(steps_e[op], steps_d[op], op)
            else:
                for key in ("starts_at", "run_not_after"):
                    self.assertEqual(gen.utc(steps_e[op][key]) - gen.utc(steps_d[op][key]), timedelta(hours=1), (op, key))

    def test_d_plans_over_the_issued_go_sha256_are_the_issued_ones(self):
        gen = generator()
        act_b, release, policy = certified()
        built = gen.build(RUNNER.read_bytes(), str(self.base), act_b, release, policy, lots.TEST_GO, False, "D")
        request, plans = composed_plans(gen, "D", sha(lots.TEST_GO))       # the composition is build()'s own
        self.assertEqual((request, plans), (built["request"], built["plans"]))
        request, plans = composed_plans(gen, "D", GO_D_SHA256)
        self.assertEqual(sha(request), REQUEST_D_SHA256)
        self.assertEqual({op: sha(raw) for op, raw in plans.items()}, PLANS_D_SHA256)

    @unittest.skipUnless(ISSUED_D_DIR, "L12_ISSUED_D_DIR not set: the issued D run is not part of the family")
    def test_d_originals_reproduced_from_the_issued_dir(self):
        root = Path(ISSUED_D_DIR)
        go_raw = (root / "k9" / "K9_GO_04.json").read_bytes()
        request_raw = (root / "K9_04_STEP_SET_REQUEST.json").read_bytes()
        final = root / "final-plans"
        self.assertEqual((sha(go_raw), sha(request_raw)), (GO_D_SHA256, REQUEST_D_SHA256))
        go = json.loads(go_raw)
        gen = generator()
        self.assertEqual((go["request_sha256"], go["grid"]), (REQUEST_D_SHA256, {"id": "D", "slots_sha256":
                                                                               gen.grid_block("D")["slots_sha256"]}))
        result = gen.build(RUNNER.read_bytes(), str(self.base), *certified(), go_raw, False, "D")
        self.assertEqual(result["request"], request_raw)
        self.assertEqual((final / "K9_04_STEP_SET_REQUEST.json").read_bytes(), request_raw)
        for op, raw in result["plans"].items():
            self.assertEqual((final / "plans" / (op + ".json")).read_bytes(), raw, op)
            self.assertEqual(go["operation_rows"][op]["starts_at"], json.loads(raw)["step_row"]["starts_at"], op)
        self.assertEqual(sorted(p.name for p in (final / "plans").iterdir()), sorted(op + ".json" for op in gen.STEPS))
        self.assertEqual((final / "tools" / result["runner_name"]).read_bytes(), RUNNER.read_bytes())
        issued_raw = (final / "K9_04_STEP_SET_MANIFEST.json").read_bytes()
        self.assertEqual(sha(issued_raw), MANIFEST_D_SHA256)
        issued, mine = json.loads(issued_raw), json.loads(result["manifest"])
        self.assertEqual((issued["engine_rule"]["sha256"], mine["engine_rule"]["sha256"]),
                         (ENGINE_V32_SHA256, sha((kit.FAMILY / "l12host_effect.py").read_bytes())))
        mine["engine_rule"]["sha256"] = ENGINE_V32_SHA256              # the only byte difference: the engine file
        self.assertEqual(gen.canon(mine), issued_raw)


def main():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for case in (GridE, IssuedD):
        suite.addTests(loader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(suite)
    print(json.dumps({"schema": "L12HOST_GRID_E_TEST_RESULT", "python": "%d.%d.%d" % sys.version_info[:3],
                      "platform": sys.platform, "tests": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "skipped": len(result.skipped), "ok": result.wasSuccessful(),
                      "grid_e_slots_sha256": SLOTS_SHA256["E"], "issued_d_dir_given": bool(ISSUED_D_DIR),
                      "temp_parent": dict(kit.TEMP_PARENT)}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
