"""L12-HOST v3.3f suite. SYNTHETIC only (TEST-ONLY act B / GO bytes, synthetic REAL K9 files, temporary directories;
the family is checked unchanged by the lots tests' base class). Nothing here is a Codex verifier, registry, review,
publication or original: every REAL K9 file made here is a SYNTHETIC stand-in (build_specs.SYNTHETIC_MARK) except the
certified in-family release / policy files and the suite's TEST-ONLY act B.

  D-NET / L2  the five network constants; the builder and the in-family drafts use them; physical bind refuses any
              other K9 class network (K9_NETWORKS_NOT_DNET) or unit network (SESSION_READER_NETWORK_NOT_DNET,
              SUPERVISOR_NETWORK_NOT_DNET; host/bridge/default/container:* already by the unit grammar); the session
              rows differ from the single-network shape ONLY in the --network word; FIXTURE (non-physical) unchanged.
  REAL        `write --out-dir` takes the REAL K9 files as explicit inputs, copies them byte for byte into the dir and
              SPEC.files, wires the three callbacks, and refuses a missing / unknown / unbound input before any write;
              the runtime's physical check (bind, preview, every slot) refuses absent or unbound REAL files; F1 extended.
  KILL        the changed-row record (all 12 rows) printed by `kill-record`, written by `write`, re-derived by `validate`.
  GO form     the installed paths of the GO, its publication and the registry.
  Codex R2    the delivered verifier is read READ-ONLY by AST when present on this machine (skipped elsewhere, e.g. CI):
              its three callbacks, its literal ABI, its empty allowlist (HOLD), and the writer's sha256 flag refusal.
  Proof       the Linux proof's synthetic UP / DOWN lots bind under the v3.3f pins (paths as on the runner, offline).

Run: python -I -S -B tests/test_v33f.py   (one JSON summary on stdout, test names on stderr; exit 1 on failure)
"""
import json
import os
from pathlib import Path
import shutil
import sys
import time
import unittest
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit                          # noqa: E402
import test_lots_patch_v34 as lots  # noqa: E402  (its Base: plans / real / real_k9 / k9_argv, family unchanged)

rt, fx, inst, bind = kit.rt, kit.fx, kit.inst, kit.bind
bs = lots.bs
sys.path.insert(0, str(kit.FAMILY))
import linux_systemd_proof as proof  # noqa: E402  (import is inert: main() refuses outside CI)

DNET = {"PROVIDER": "bridge", "DATABASE": "c3po_c3po_internal", "DATABASE_AND_PROVIDER": "c3po_db_loopback"}
CODEX_R2 = Path("/Users/eduardocastro/Documents/Codex/2026-09-04/va/work/codex-epoch04-k9-real-verifiers-20261010-r2"
                "/ext/k9_verifiers04.py")
CODEX_GO_FORM = Path("/Users/eduardocastro/Documents/Codex/2026-09-04/va/work/"
                     "codex-epoch04-saturday-go-grid-decisions-20261010-r1/GO_FORM_SPEC.private.json")
sha = lots.sha


def network_word(row, value=None):
    """The word after --network in a unit row's exec (set it when `value` is given)."""
    words = row["unit"]["exec"]
    i = words.index("--network") + 1
    if value is not None:
        words[i] = value
    return words[i]


class Base(lots.Base):
    def bind_filled(self, spec, physical=True, prepared="2026-10-10T12:30:00Z"):
        lay = bs.layout()
        return bind.build_lot(spec, lay, bs.runtime_stub(lay), prepared, bs.LOTS, physical=physical)

    def filled(self, lot="UP"):
        tmp = self.base / ("fill-%d" % time.monotonic_ns())
        tmp.mkdir()
        return bs.fill(bs.build_up() if lot == "UP" else bs.build_down(), str(tmp)), tmp

    def bind_refuses(self, spec, code, *, physical=True, prepared="2026-10-10T12:30:00Z"):
        with self.assertRaises(rt.Hold) as caught:
            self.bind_filled(spec, physical, prepared)
        self.assertRegex(str(caught.exception), code)
        return str(caught.exception)

    def chain(self, plans, *, lots_=("UP", "DOWN"), mutate=None, allow=None, pins=None, name=None):
        """A SYNTHETIC REAL input chain of one plans run with optional mutations (registry rows, publication, paths):
        build_specs.synthetic_real_inputs step by step. Returns {lot: real_k9}."""
        m = bs.manifest(str(plans))
        act = [p.read_bytes() for p in sorted(self.base.glob("act_b-*.TEST_ONLY.txt"))
               if sha(p.read_bytes()) == json.loads((Path(plans) / "plans" / "prove_launch.json").read_bytes())
               ["constants"]["act_b_sha256"]]
        d = self.base / (name or "chain-%d" % time.monotonic_ns())
        d.mkdir(mode=0o700)
        originals = bs.synthetic_originals(act[0] if act else None)
        review, publication = bs.synthetic_review_publication(m["go_sha256"])
        rows = bs.k9_rows(m, bs.GEN_SECRETS_ROOT, bs.NETWORKS)
        ops = {op: {"phase": bs.SYNTHETIC_MARK, "phase_row": {}, "plan_sha256": m["steps"][op]["plan_sha256"],
                    "effect_sha256": sha(rt.canonical(rows[op]["row"]))} for op in m["steps"]}
        state = {"originals": originals, "review": review, "publication": publication, "operations": ops}
        if mutate:
            mutate(state)
        policies = {lot: bs.synthetic_policy(lot, review=state["review"], publication=state["publication"],
                                             go_sha256=m["go_sha256"], request_sha256=m["request_sha256"],
                                             grid=m["grid"]["id"], originals=state["originals"],
                                             operations=state["operations"]) for lot in lots_}
        verifier = bs.synthetic_k9_verifier(pins or {n: sha(raw) for n, (_, raw) in state["originals"].items()},
                                            allow if allow is not None else {lot: sha(raw) for lot, raw in policies.items()})
        files = {"verifier": verifier, "review": state["review"], "publication": state["publication"]}
        files.update({"policy-" + lot: raw for lot, raw in policies.items()})
        files.update({"original." + n: raw for n, (_, raw) in state["originals"].items()})
        for key, raw in files.items():
            (d / key).write_bytes(raw)
        common = {"verifier": str(d / "verifier"), "verifier_sha256": sha(verifier), "review": str(d / "review"),
                  "publication": str(d / "publication"),
                  "originals": {n: str(d / ("original." + n)) for n in state["originals"]}}
        return {lot: dict(common, policy=str(d / ("policy-" + lot))) for lot in lots_}


# ====================================================================== D-NET and L2
class Networks(Base):
    def test_dnet_constants_builder_and_drafts(self):
        self.assertEqual((rt.K9_NETWORKS_EPOCH04, rt.READER_NETWORK_EPOCH04, rt.SUPERVISOR_NETWORK_EPOCH04),
                         (DNET, "c3po_c3po_internal", "c3po_db_loopback"))
        self.assertEqual((bs.NETWORKS, bs.UNIT_NETWORKS), (DNET, {"reader": "c3po_c3po_internal",
                                                                  "supervisor": "c3po_db_loopback"}))
        up = json.loads((bs.LOTS / "UP.SPEC.json").read_bytes())["spec"]
        down = json.loads((bs.LOTS / "DOWN.SPEC.DRAFT.json").read_bytes())["spec"]
        self.assertEqual((up["k9"]["networks"], down["k9"]["networks"]), (DNET, DNET))
        session = [s for s in down["extended"]["steps"] if s["step"] == "session_start"][0]
        self.assertEqual((network_word(session["effect"]), network_word(session["pre_effect"])),
                         ("c3po_c3po_internal", "c3po_db_loopback"))
        for spec in (up, down):
            for owner in list(spec["tasks"]) + list(spec["extended"]["steps"]):
                docker = (owner["effect"] or {}).get("docker")
                if docker:
                    plan = json.loads((bs.LOTS / spec["files"]["k9/" + docker["name"].split("20261012-")[1]
                                                               .replace("-", "_") + ".json"]).read_bytes())
                    self.assertEqual(docker["network"], "none" if plan["network_class"] == "NONE"
                                     else DNET[plan["network_class"]], docker["name"])
        for path in (bs.LOTS / "UP.SPEC.json", bs.LOTS / "DOWN.SPEC.DRAFT.json"):
            self.assertNotIn(b"c3po_default", path.read_bytes(), path.name)
        self.assertEqual(bs.render(bs.build_up(), bs.UP_COMMENT), (bs.LOTS / "UP.SPEC.json").read_bytes())
        self.assertEqual(bs.render(bs.build_down(), bs.DOWN_COMMENT), (bs.LOTS / "DOWN.SPEC.DRAFT.json").read_bytes())

    def test_physical_bind_pins_the_three_k9_class_networks(self):
        for cls, value in (("DATABASE", "c3po_default"), ("DATABASE_AND_PROVIDER", "c3po_c3po_internal"),
                           ("DATABASE", "c3po_db_loopback"), ("PROVIDER", "c3po_db_loopback")):
            with self.subTest(cls=cls, value=value):
                spec, _ = self.filled("UP")
                spec["k9"]["networks"][cls] = value
                self.bind_refuses(spec, r"\AK9_NETWORKS_NOT_DNET\Z")
        spec, _ = self.filled("DOWN")
        spec["k9"]["networks"]["DATABASE"] = "c3po_default"
        self.bind_refuses(spec, r"\AK9_NETWORKS_NOT_DNET\Z", prepared="2026-10-11T23:00:00Z")

    def test_physical_bind_pins_each_session_unit_network(self):
        cases = [("effect", v, "SESSION_READER_NETWORK_NOT_DNET") for v in
                 ("none", "c3po_default", "c3po_db_loopback", "c3po_internal")]
        cases += [("pre_effect", v, "SUPERVISOR_NETWORK_NOT_DNET") for v in
                  ("none", "c3po_default", "c3po_c3po_internal", "bridge2")]
        cases += [(row, v, "UNIT_DOCKER_NETWORK_INVALID") for row in ("effect", "pre_effect")
                  for v in ("host", "bridge", "default", "container:c3po-reader-e04")]
        for row, value, code in cases:
            with self.subTest(row=row, value=value):
                spec, _ = self.filled("DOWN")
                step = [s for s in spec["extended"]["steps"] if s["step"] == "session_start"][0]
                network_word(step[row], value)
                self.bind_refuses(spec, r"\A%s\Z" % code, prepared="2026-10-11T23:00:00Z")
        # FIXTURE / non-physical: the units may carry any grammar-legal names, equal or not (no host is touched)
        spec, _ = self.filled("DOWN")
        step = [s for s in spec["extended"]["steps"] if s["step"] == "session_start"][0]
        network_word(step["effect"], "c3po_default")
        network_word(step["pre_effect"], "c3po_default")
        self.bind_filled(spec, physical=False, prepared="2026-10-11T23:00:00Z")

    def test_session_rows_differ_from_the_single_network_shape_only_in_the_network_word(self):
        down = bs.build_down()
        step = [s for s in down["extended"]["steps"] if s["step"] == "session_start"][0]
        lay = bs.layout()
        variables = dict(image=bs.IMAGE, data=rt.DAY_D_DATA, journal=rt.EPOCH04_JOURNAL_ROOT,
                         capacity=rt.EPOCH04_CAPACITY_ROOT, config=rt.EPOCH04_READER_CONFIG,
                         state=rt.EPOCH04_SUPERVISOR_STATE, supervisor_config=rt.EPOCH04_SUPERVISOR_CONFIG)
        reader, sup = rt.session_unit_rows(lay, reader_network="c3po_c3po_internal",
                                           supervisor_network="c3po_db_loopback", **variables)
        self.assertEqual((reader, sup), (step["effect"], step["pre_effect"]))
        old_reader, old_sup = rt.session_unit_rows(lay, reader_network="c3po_default", supervisor_network="c3po_default",
                                                   **variables)
        for new, old in ((reader, old_reader), (sup, old_sup)):
            self.assertEqual(new["unit"]["properties"], old["unit"]["properties"])
            self.assertEqual({k: v for k, v in new.items() if k != "unit"}, {k: v for k, v in old.items() if k != "unit"})
            diff = [i for i, (a, b) in enumerate(zip(new["unit"]["exec"], old["unit"]["exec"])) if a != b]
            self.assertEqual(len(new["unit"]["exec"]), len(old["unit"]["exec"]))
            self.assertEqual(diff, [new["unit"]["exec"].index("--network") + 1])
        # the reviewed references (pinned bytes) still produce them through unit_row
        self.assertEqual(sha((kit.FAMILY / "reference" / "c3po-reader.service").read_bytes()),
                         "8d2ff7a91b94e39b8c7a0e91fae34b16dbc9d55f7af407b8464486a9bd064fab")


# ====================================================================== REAL K9 files: runtime (physical) check
class RuntimeReal(Base):
    def test_in_family_validation_binds_the_synthetic_real_fill_ins(self):
        for lot, prepared in (("UP", "2026-10-10T12:30:00Z"), ("DOWN", "2026-10-11T23:00:00Z")):
            spec, _ = self.filled(lot)
            self.assertTrue(set(rt.K9_REAL_FIXED_FILES) <= set(spec["files"]))
            authority = self.bind_filled(spec, prepared=prepared)[2]
            self.assertEqual({n: authority["external"][n] for n in rt.K9_REAL_CALLBACKS},
                             {n: {"file": "ext/k9_verifiers04.py", "identity": i} for n, i in rt.K9_REAL_CALLBACKS.items()})
            originals = [r for r in authority["files"] if r.startswith("k9/SYNTHETIC_ORIGINAL.")]
            self.assertEqual(len(originals), 8)
            for rel in list(rt.K9_REAL_FIXED_FILES[1:]) + originals:
                raw = Path(spec["files"][rel]).read_bytes()
                if not rel.endswith((".release.txt", ".policy.txt")):
                    self.assertIn(bs.SYNTHETIC_MARK.encode("ascii"), raw, rel)
            self.assertIn(bs.SYNTHETIC_MARK.encode("ascii"), Path(spec["files"]["ext/k9_verifiers04.py"]).read_bytes())

    def test_physical_bind_refuses_absent_or_unbound_real_files(self):
        def mutated(change, lot="UP"):
            spec, tmp = self.filled(lot)
            change(spec, tmp)
            return spec

        def drop(rel):
            return lambda s, t: s["files"].pop(rel)

        def other_bytes(rel, raw):
            def change(s, t):
                path = Path(t) / ("other-" + rel.replace("/", "_"))
                path.write_bytes(raw)
                s["files"][rel] = str(path)
            return change

        def rewrite_verifier(edit):
            def change(s, t):
                raw = Path(s["files"]["ext/k9_verifiers04.py"]).read_bytes()
                other_bytes("ext/k9_verifiers04.py", edit(raw))(s, t)
            return change

        def kill_minus_one(s, t):
            task = [x for x in s["tasks"] if x["operation"] == "prove"][0]
            task["effect"]["docker"]["timeout_seconds"] -= 1
            task["decoder"]["provenance_binding_sha256"] = sha(rt.canonical(task["effect"]))

        original = "k9/SYNTHETIC_ORIGINAL.B_CODEX.txt"
        cases = [("K9_REAL_FILE_ABSENT", drop("k9/VERIFIER_POLICY_04.json")),
                 ("K9_REAL_FILE_ABSENT", drop("k9/K9_GO_04.PUBLICATION.json")),
                 ("K9_REAL_FILE_ABSENT", drop("k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json")),
                 ("EXTERNAL_TABLE_INVALID|K9_REAL_FILE_ABSENT", drop("ext/k9_verifiers04.py")),
                 ("K9_REAL_CALLBACK_NOT_THE_VERIFIER",
                  lambda s, t: s["external"].__setitem__("k9_step", {"file": "ext/k9_verifiers04.py",
                                                                     "identity": "verify_approval"})),
                 ("K9_REAL_CALLBACK_NOT_THE_VERIFIER",
                  lambda s, t: s["extended"]["steps"][0]["decoder"].__setitem__("verifier", "k9_approval")),
                 ("K9_REAL_CALLBACK_NOT_THE_VERIFIER",
                  lambda s, t: s["tasks"][0]["decoder"]["verifiers"].__setitem__("original", "k9_approval")),
                 ("K9_REAL_VERIFIER_CALLBACKS_ABSENT", rewrite_verifier(lambda b: b.replace(b"def verify_step", b"def other"))),
                 ("K9_REAL_VERIFIER_LITERAL_NOT_SINGLE",
                  rewrite_verifier(lambda b: b + b"\nORIGINAL_PINS = {}\n")),
                 ("K9_REAL_VERIFIER_ABI_NOT_THE_DECLARED_ONE",
                  rewrite_verifier(lambda b: b.replace(b'POLICY_REL = "k9/VERIFIER_POLICY_04.json"',
                                                       b'POLICY_REL = "k9/OTHER.json"'))),
                 ("K9_REAL_REGISTRY_NOT_SEALED_IN_THE_VERIFIER",
                  rewrite_verifier(lambda b: b.split(b"APPROVED_REGISTRY_PINS = ")[0] + b"APPROVED_REGISTRY_PINS = {}"
                                   + b"\n\n\ndef verify_approval" + b.split(b"def verify_approval", 1)[1])),
                 ("K9_REAL_ORIGINAL_ABSENT", drop(original)),
                 ("K9_REAL_ORIGINAL_NOT_THE_REGISTERED_ONE", other_bytes(original, b"another original\n")),
                 ("K9_REAL_REGISTRY_NOT_THE_SIGNED_FILES",
                  other_bytes("k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json", rt.canonical({"another": "review"}))),
                 ("K9_REAL_REGISTRY_INVALID|K9_REAL_REGISTRY_NOT_SEALED_IN_THE_VERIFIER",
                  other_bytes("k9/VERIFIER_POLICY_04.json", b'{"a":1}')),
                 ("K9_REAL_REGISTRY_OPERATION_NOT_SIGNED", kill_minus_one)]
        for code, change in cases:
            with self.subTest(code=code):
                self.bind_refuses(mutated(change), r"\A(%s)\Z" % code)
        # the same mutations are invisible to a non-physical (FIXTURE / suite) bind: the check is physical only
        self.bind_filled(mutated(drop("k9/VERIFIER_POLICY_04.json")), physical=False)
        self.bind_filled(mutated(kill_minus_one), physical=False)

    def test_runtime_refuses_real_bytes_that_differ_from_the_authority_pins(self):
        spec, _ = self.filled("UP")
        authority_raw, request_raw, authority, q, extra = self.bind_filled(spec)
        fam = inst.family_core()
        rt.validate_authority(authority, q, fam, rt.Hold, physical=True, files_raw=extra)
        for rel in rt.K9_REAL_FIXED_FILES + ("k9/SYNTHETIC_ORIGINAL.act_b.txt",):
            with self.subTest(rel=rel):
                changed = dict(extra)
                changed[rel] = extra[rel] + b" "
                with self.assertRaisesRegex(rt.Hold, r"\AFILES_BYTES_UNBOUND\Z"):
                    rt.validate_authority(authority, q, fam, rt.Hold, physical=True, files_raw=changed)
                absent = dict(extra)
                absent.pop(rel)
                with self.assertRaisesRegex(rt.Hold, r"\AFILES_BYTES_UNBOUND\Z"):
                    rt.validate_authority(authority, q, fam, rt.Hold, physical=True, files_raw=absent)


# ====================================================================== REAL K9 files: the writer
class Writer(Base):
    def test_real_up_dir_carries_the_real_files_byte_for_byte(self):
        plans, go = self.plans("D")
        k9 = self.real_k9(plans, "UP")
        out = self.base / "real-UP"
        result = self.real("UP", out=out, plans=plans, go=go)
        spec = json.loads((out / "UP.SPEC.json").read_bytes())
        policy = json.loads(Path(k9["policy"]).read_bytes())
        expected = {"ext/k9_verifiers04.py": k9["verifier"], "k9/VERIFIER_POLICY_04.json": k9["policy"],
                    "k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json": k9["review"],
                    "k9/K9_GO_04.PUBLICATION.json": k9["publication"]}
        expected.update({policy["originals"][n]["file"]: p for n, p in k9["originals"].items()})
        self.assertEqual(len(expected), 12)
        for rel, src in expected.items():
            self.assertEqual((out / rel).read_bytes(), Path(src).read_bytes(), rel)
            self.assertEqual(spec["files"][rel], rel)
            self.assertEqual(result["k9_real"]["files"][rel], sha(Path(src).read_bytes()))
        self.assertEqual(result["k9_real"]["verifier_sha256"], k9["verifier_sha256"])
        self.assertFalse(result["k9_real"]["verifier_is_codex_r2_plus_seal"])
        self.assertEqual({n: spec["external"][n] for n in rt.K9_REAL_CALLBACKS},
                         {n: {"file": "ext/k9_verifiers04.py", "identity": i} for n, i in rt.K9_REAL_CALLBACKS.items()})
        decoders = [t["decoder"] for t in spec["tasks"]] + [s["decoder"] for s in spec["extended"]["steps"]]
        self.assertEqual({json.dumps(d.get("verifiers") or d.get("verifier")) for d in decoders},
                         {json.dumps({"approval": "k9_approval", "original": "k9_original"}), json.dumps("k9_step")})
        self.assertEqual((result["networks"], spec["k9"]["networks"]), (DNET, DNET))
        self.assertLessEqual(len(spec["files"]), 64)
        sums = {l.split("  ", 1)[1] for l in (out / "SHA256SUMS").read_text("ascii").splitlines()}
        self.assertTrue(set(expected) | {bs.KILL_RECORD, bs.MANIFEST_RECORD} <= sums)
        checked = bs.check_real(str(out), str(lots.LAYOUT))
        self.assertEqual((checked["status"], checked["k9_real"], checked["kill_record"]["sha256"]),
                         ("REAL_SPEC_DIR_VALID", result["k9_real"], result["kill_record"]["sha256"]))

    def test_real_down_dir_and_the_extended_f1(self):
        plans, go = self.plans("C")
        up = self.base / "real-UP-f1"
        self.real("UP", out=up, plans=plans, go=go)
        out = self.base / "real-DOWN-f1"
        result = self.real("DOWN", out=out, plans=plans, go=go, up_real_dir=up)
        cross = result["up_cross_check"]
        for rel, field in (("ext/k9_verifiers04.py", "k9_verifier_sha256"),
                           ("k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json", "k9_review_sha256"),
                           ("k9/K9_GO_04.PUBLICATION.json", "k9_publication_sha256"),
                           (bs.KILL_RECORD, "kill_record_sha256"), (bs.MANIFEST_RECORD, "manifest_record_sha256")):
            self.assertEqual((out / rel).read_bytes(), (up / rel).read_bytes(), rel)
            self.assertEqual(cross[field], sha((up / rel).read_bytes()), field)
        pu = json.loads((up / "k9/VERIFIER_POLICY_04.json").read_bytes())
        pd = json.loads((out / "k9/VERIFIER_POLICY_04.json").read_bytes())
        self.assertEqual((pu["lot"], pd["lot"], dict(pu, lot=None) == dict(pd, lot=None)), ("UP", "DOWN", True))
        for r in pd["originals"].values():
            self.assertEqual((out / r["file"]).read_bytes(), (up / r["file"]).read_bytes())
        spec = json.loads((out / "DOWN.SPEC.json").read_bytes())
        session = [s for s in spec["extended"]["steps"] if s["step"] == "session_start"][0]
        self.assertEqual((network_word(session["effect"]), network_word(session["pre_effect"])),
                         ("c3po_c3po_internal", "c3po_db_loopback"))
        capture = [s for s in spec["extended"]["steps"] if s["step"] == "capture_launch"][0]
        self.assertEqual(capture["decoder"]["verifiers"], {"approval": "k9_approval", "original": "k9_original"})
        self.assertEqual(bs.check_real(str(out), str(lots.LAYOUT))["status"], "REAL_SPEC_DIR_VALID")
        # the owner's question names both unit networks, the class networks and every REAL file (physical bind)
        runtime = self.base / "runtime-down.json"
        runtime.write_bytes(bs.runtime_stub(bind.loose_json(lots.LAYOUT)))
        stage = self.base / "stage-DOWN"
        umask = os.umask(0o077)
        try:
            bind.lot(str(out / "DOWN.SPEC.json"), str(lots.LAYOUT), str(runtime), "2026-10-11T23:00:00Z", str(stage),
                     physical=True)
        finally:
            os.umask(umask)
        question = (stage / "question.txt").read_text("ascii")
        self.assertIn("REDES DAS UNIDADES: leitor c3po_c3po_internal, supervisor c3po_db_loopback", question)
        self.assertIn("redes DATABASE=c3po_c3po_internal, DATABASE_AND_PROVIDER=c3po_db_loopback, PROVIDER=bridge",
                      question)
        for rel in list(rt.K9_REAL_FIXED_FILES) + [r["file"] for r in pd["originals"].values()]:
            self.assertIn("arquivo %s SHA256 %s" % (rel, sha((out / rel).read_bytes())), question)
        # each shared REAL input differing between the lots is refused before any write (one verifier seals both)
        def review(state):
            state["review"] = rt.canonical({"schema": bs.SYNTHETIC_MARK, "what": "another review"})

        def publication(state):
            raw = json.loads(state["publication"])
            raw["comment_id"] = 2
            state["publication"] = rt.canonical(raw)

        def phase_row(state):
            state["operations"]["capture_launch"]["phase_row"] = {"synthetic": 1}
        base = self.real_k9(plans, "UP")
        for code, mutate in (("REAL_DOWN_K9_REVIEW_NOT_THE_UP_ONE", review),
                             ("REAL_DOWN_K9_PUBLICATION_NOT_THE_UP_ONE", publication),
                             ("REAL_DOWN_K9_POLICY_NOT_THE_UP_ONE_BUT_LOT", phase_row)):
            with self.subTest(code=code):
                other = self.chain(plans, lots_=("DOWN",), mutate=mutate)["DOWN"]
                verifier = bs.synthetic_k9_verifier(
                    {n: sha(Path(p).read_bytes()) for n, p in base["originals"].items()},
                    {"UP": sha(Path(base["policy"]).read_bytes()), "DOWN": sha(Path(other["policy"]).read_bytes())})
                shared = self.base / ("shared-verifier-%s" % code)
                shared.write_bytes(verifier)
                up2 = self.base / ("up-" + code)
                self.real("UP", out=up2, plans=plans, go=go,
                          real_k9=dict(base, verifier=str(shared), verifier_sha256=sha(verifier)))
                target = self.base / ("down-" + code)
                self.refused(code, self.real, "DOWN", out=target, plans=plans, go=go, up_real_dir=up2,
                             real_k9=dict(other, verifier=str(shared), verifier_sha256=sha(verifier)))
                self.assertFalse(os.path.lexists(str(target)))
        other = self.chain(plans, lots_=("DOWN",), mutate=review)["DOWN"]
        target = self.base / "down-other-verifier"
        self.refused("REAL_DOWN_K9_VERIFIER_NOT_THE_UP_ONE", self.real, "DOWN", out=target, plans=plans, go=go,
                     up_real_dir=up, real_k9=other)
        self.assertFalse(os.path.lexists(str(target)))

    def test_writer_refuses_missing_unknown_or_unbound_real_inputs_before_any_write(self):
        plans, go = self.plans("C")
        k9 = self.real_k9(plans, "UP")
        down = self.real_k9(plans, "DOWN")

        def attempt(code, name, real_k9=None, detail=None, **kw):
            out = self.base / name
            error = self.refused(code, self.real, "UP", out=out, plans=plans, go=go,
                                 real_k9=real_k9 if real_k9 is not None else k9, **kw)
            self.assertFalse(os.path.lexists(str(out)), name)
            if detail is not None:
                self.assertEqual(error.detail, detail)

        def without(key):
            return {k: v for k, v in k9.items() if k != key}

        attempt("REAL_K9_INPUTS_REQUIRED", "r-none", real_k9={})
        attempt("REAL_K9_INPUTS_REQUIRED", "r-no-review", real_k9=without("review"), detail=["review"])
        attempt("REAL_K9_INPUTS_REQUIRED", "r-unknown", real_k9=dict(k9, extra="x"))
        attempt("REAL_K9_VERIFIER_NOT_THE_PINNED_ONE", "r-sha", real_k9=dict(k9, verifier_sha256="ab" * 32))
        attempt("REAL_K9_VERIFIER_SHA256_FLAG_INVALID", "r-sha-bad", real_k9=dict(k9, verifier_sha256="AB"))
        missing = dict(k9["originals"])
        missing.pop("B_FABLE")
        attempt("REAL_K9_ORIGINALS_NOT_THE_VERIFIER_ONES", "r-missing-original", real_k9=dict(k9, originals=missing),
                detail=["B_FABLE"])
        attempt("REAL_K9_ORIGINALS_NOT_THE_VERIFIER_ONES", "r-unknown-original",
                real_k9=dict(k9, originals=dict(k9["originals"], OTHER=k9["originals"]["act_b"])), detail=["OTHER"])
        swapped = dict(k9["originals"], B_CODEX=k9["originals"]["B_DUDU"])
        attempt("REAL_K9_ORIGINAL_NOT_THE_PINNED_ONE", "r-swapped", real_k9=dict(k9, originals=swapped), detail="B_CODEX")
        attempt("REAL_K9_POLICY_INVALID", "r-down-policy", real_k9=dict(k9, policy=down["policy"]))
        attempt("REAL_K9_REVIEW_NOT_THE_REGISTERED_ONE", "r-review", real_k9=dict(k9, review=k9["publication"]))
        attempt("REAL_K9_PUBLICATION_NOT_THE_REGISTERED_ONE", "r-publication",
                real_k9=dict(k9, publication=k9["review"]))
        attempt("REAL_INPUT_NOT_A_REGULAR_FILE", "r-absent", real_k9=dict(k9, policy=str(self.base / "absent.json")))
        out = self.base / "r-net"
        error = self.refused("REAL_NETWORKS_NOT_DNET", bs.write_real, "UP", out, plans_dir=str(plans), go=str(go),
                             layout_path=str(lots.LAYOUT), secrets_root=bs.GEN_SECRETS_ROOT,
                             networks=dict(DNET, DATABASE="c3po_default"), owner_deadline="2026-10-10T17:20:00Z",
                             values_path=str(self.write_values({})), real_k9=k9)
        self.assertEqual((error.detail, os.path.lexists(str(out))), (["DATABASE"], False))

        # a self-consistent chain whose verifier does not seal its registry (the delivered empty allowlist: HOLD)
        attempt("REAL_K9_POLICY_NOT_SEALED_IN_THE_VERIFIER", "r-unsealed",
                real_k9=self.chain(plans, lots_=("UP",), allow={})["UP"])

        def wrong_effect(state):        # the generator's KILL instead of the slack KILL: not the derived row
            m = bs.manifest(str(plans))
            state["operations"]["prove_launch"]["effect_sha256"] = sha(rt.canonical(
                bs.convert(m["steps"]["prove_launch"], bs.GEN_SECRETS_ROOT, bs.NETWORKS, slack=False)))
        attempt("REAL_K9_POLICY_EFFECT_NOT_THE_DERIVED_ROW", "r-effect",
                real_k9=self.chain(plans, lots_=("UP",), mutate=wrong_effect)["UP"], detail="prove_launch")

        def wrong_network_effect(state):    # a row with c3po_default registered
            m = bs.manifest(str(plans))
            state["operations"]["commit_launch"]["effect_sha256"] = sha(rt.canonical(
                bs.convert(m["steps"]["commit_launch"], bs.GEN_SECRETS_ROOT,
                           dict(DNET, DATABASE="c3po_default"))))
        attempt("REAL_K9_POLICY_EFFECT_NOT_THE_DERIVED_ROW", "r-effect-net",
                real_k9=self.chain(plans, lots_=("UP",), mutate=wrong_network_effect)["UP"], detail="commit_launch")

        def wrong_plan(state):
            state["operations"]["stage"]["plan_sha256"] = "cd" * 32
        attempt("REAL_K9_POLICY_PLAN_NOT_THE_MANIFEST_ONE", "r-plan",
                real_k9=self.chain(plans, lots_=("UP",), mutate=wrong_plan)["UP"], detail="stage")

        def eleven(state):
            state["operations"].pop("capture_launch")
        attempt("REAL_K9_POLICY_OPERATIONS_NOT_THE_TWELVE", "r-eleven",
                real_k9=self.chain(plans, lots_=("UP",), mutate=eleven)["UP"])

        def other_go(state):
            raw = json.loads(state["publication"])
            raw["original_sha256"] = "ef" * 32
            state["publication"] = rt.canonical(raw)
        attempt("REAL_K9_PUBLICATION_NOT_THE_GO_ONE", "r-pub-go",
                real_k9=self.chain(plans, lots_=("UP",), mutate=other_go)["UP"])

        for bad in ("k9/sub/x.txt", "secrets/provider.env", "k9/a:b", "k9/.hidden", "k9/VERIFIER_POLICY_04.json"):
            def path(state, bad=bad):
                rel, raw = state["originals"]["B_DUDU"]
                state["originals"]["B_DUDU"] = (bad, raw)
            with self.subTest(path=bad):
                attempt("REAL_K9_ORIGINAL_PATH_INVALID", "r-path-%d" % abs(hash(bad)),
                        real_k9=self.chain(plans, lots_=("UP",), mutate=path)["UP"])

        def collide(state):
            rel, raw = state["originals"]["B_DUDU"]
            state["originals"]["B_DUDU"] = ("k9/prove_launch.json", raw)
        attempt("REAL_K9_ORIGINAL_PATH_INVALID", "r-collide", real_k9=self.chain(plans, lots_=("UP",), mutate=collide)["UP"])

        pins = {n: sha(Path(p).read_bytes()) for n, p in k9["originals"].items()}
        act_b = self.base / "another-act-b.TEST_ONLY.txt"
        act_b.write_bytes(b"TEST ONLY another act B for the verifier pins\n")

        def act(state):
            state["originals"]["act_b"] = (state["originals"]["act_b"][0], act_b.read_bytes())
        attempt("REAL_K9_ORIGINAL_PINS_NOT_THE_PLANS_ONES", "r-act-b",
                real_k9=self.chain(plans, lots_=("UP",), mutate=act)["UP"])
        self.assertEqual(len(pins), 8)

    def test_validate_rederives_the_records_and_refuses_tampering(self):
        plans, go = self.plans("C")
        up = self.base / "real-UP-v"
        self.real("UP", out=up, plans=plans, go=go)

        def tampered(name, rel, change):
            d = self.base / name
            shutil.copytree(str(up), str(d))
            for p in d.rglob("*"):
                os.chmod(str(p), 0o700 if p.is_dir() else 0o600)
            (d / rel).write_bytes(change((d / rel).read_bytes()))
            rows = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
            (d / "SHA256SUMS").write_bytes("".join("%s  %s\n" % (sha((d / r).read_bytes()), r) for r in rows).encode())
            return d

        def edit_record(raw):
            doc = json.loads(raw)
            doc["rows"][0]["derivation"] = "something else"
            return rt.canonical(doc)
        for code, d in (("REAL_KILL_RECORD_NOT_THE_DERIVED_ONE", tampered("t-kill", bs.KILL_RECORD, edit_record)),
                        ("REAL_DIR_MANIFEST_RECORD_NOT_THIS_RUN",
                         tampered("t-manifest", bs.MANIFEST_RECORD, lambda b: b.replace(b'"UP"', b'"XX"', 1))),
                        ("REAL_K9_REVIEW_NOT_THE_REGISTERED_ONE",
                         tampered("t-review", "k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json", lambda b: rt.canonical({"x": 1})))):
            with self.subTest(code=code):
                self.refused(code, bs.check_real, str(d), str(lots.LAYOUT))
        gone = self.base / "t-gone"
        shutil.copytree(str(up), str(gone))
        for p in gone.rglob("*"):
            os.chmod(str(p), 0o700 if p.is_dir() else 0o600)
        shutil.rmtree(str(gone / "records"))
        rows = sorted(p.relative_to(gone).as_posix() for p in gone.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
        (gone / "SHA256SUMS").write_bytes("".join("%s  %s\n" % (sha((gone / r).read_bytes()), r) for r in rows).encode())
        self.refused("REAL_DIR_K9_REAL_FILES_ABSENT", bs.check_real, str(gone), str(lots.LAYOUT))


# ====================================================================== KILL changed-row record
class Kill(Base):
    def test_kill_record_enumerates_every_row(self):
        plans, go = self.plans("D")
        argv = ["kill-record", "--plans-dir", str(plans), "--go", str(go), "--layout", str(lots.LAYOUT),
                "--secrets-root", bs.GEN_SECRETS_ROOT, "--network", "PROVIDER=bridge", "--network",
                "DATABASE=c3po_c3po_internal", "--network", "DATABASE_AND_PROVIDER=c3po_db_loopback"]
        code, text = lots.run_main(bs.main, argv)
        self.assertEqual(code, 0, text)
        out = json.loads(text)
        record = out["record"]
        self.assertEqual((out["status"], record["schema"], len(record["rows"])),
                         ("KILL_RECORD_DERIVED_NOTHING_WRITTEN", "L12HOST_K9_KILL_CHANGED_ROWS_V1", 12))
        m = bs.manifest(str(plans))
        self.assertEqual(record["request"], {"k9_request_sha256": m["request_sha256"], "grid": "D",
                                             "grid_slots_sha256": m["grid"]["slots_sha256"]})
        self.assertEqual((record["go_sha256"], record["provenance"]["networks"], record["provenance"]["secrets_root"]),
                         (m["go_sha256"], DNET, bs.GEN_SECRETS_ROOT))
        self.assertEqual(record["provenance"]["generator_manifest_sha256"],
                         sha((Path(plans) / "K9_04_STEP_SET_MANIFEST.json").read_bytes()))
        kills = {r["operation"]: (r["generator_timeout_seconds"], r["timeout_seconds"]) for r in record["rows"]}
        self.assertEqual(kills, {"prove_launch": (565, 535), "collect_launch": (865, 835), "commit_launch": (565, 535),
                                 "publish_launch": (565, 535), "components_launch": (2365, 2335),
                                 "sources_launch": (4465, 4435), "bind": (35, 35), "preflight": (265, 235),
                                 "acquire_launch": (4165, 4135), "execute_launch": (1165, 1135), "stage": (20, 20),
                                 "capture_launch": (655, 655)})
        for r in record["rows"]:
            with self.subTest(op=r["operation"]):
                self.assertEqual(r["row_sha256"], sha(rt.canonical(r["row"])))
                self.assertEqual(r["generator_row_sha256"], sha(rt.canonical(r["generator_row"])))
                self.assertEqual(r["generator_row"], m["steps"][r["operation"]]["l12_effect"])
                self.assertEqual(r["plan_sha256"], m["steps"][r["operation"]]["plan_sha256"])
                if r["operation"] == "capture_launch":
                    self.assertEqual((r["timeout_rule"], r["lot"], r["budget_seconds"]),
                                     ("CAPTURE_GENERATOR_KILL_KEPT", "DOWN", 690))
                else:
                    self.assertEqual(r["timeout_rule"], "MIN_GENERATOR_BUDGET_MINUS_65")
                    self.assertEqual(r["timeout_seconds"], min(r["generator_timeout_seconds"], r["budget_seconds"] - 65))
                    self.assertIn("min(%d, %d - 65) = %d" % (r["generator_timeout_seconds"], r["budget_seconds"],
                                                            r["timeout_seconds"]), r["derivation"])
                changed = {c[0]: c[1:] for c in r["changes"]}
                cls = m["steps"][r["operation"]]["network_class"]
                self.assertEqual(changed["docker.network"], [None, "none" if cls == "NONE" else DNET[cls]])
                self.assertEqual("docker.timeout_seconds" in changed, r["timeout_changed"])
                argv_ = r["transport"]["argv"]
                i = argv_.index("timeout")
                self.assertEqual(argv_[i:i + 4], ["timeout", "-s", "KILL", str(r["timeout_seconds"])])
                self.assertEqual(argv_[argv_.index("--network") + 1], r["row"]["docker"]["network"])
                self.assertEqual(r["transport"]["engine_sha256"], sha((kit.FAMILY / "l12host_effect.py").read_bytes()))
        # `write` puts the same bytes into the REAL dir; the registry's effect_sha256 are these row hashes
        result = self.real("UP", out=self.base / "real-UP-k", plans=plans, go=go)
        self.assertEqual(result["kill_record"]["sha256"], out["sha256"])
        policy = json.loads(Path(self.real_k9(plans, "UP")["policy"]).read_bytes())
        self.assertEqual({op: row["effect_sha256"] for op, row in policy["operations"].items()},
                         {op: row["row_sha256"] for op, row in out["rows"].items()})
        for bad, code in ((["--network", "DATABASE=c3po_default"], "REAL_NETWORKS_NOT_DNET"),
                          (["--out-dir", str(self.base / "x")], "ARGUMENTS_INVALID")):
            argv2 = list(argv)
            if bad[0] == "--network":
                argv2[argv2.index("DATABASE=c3po_c3po_internal")] = bad[1]
            else:
                argv2 += bad
            code_, text = lots.run_main(bs.main, argv2)
            self.assertEqual((code_, json.loads(text)["code"]), (2, code))


# ====================================================================== GO form and Codex R2 (read-only)
class FormAndCodex(Base):
    def test_go_form_installed_paths(self):
        self.assertEqual((bs.K9_GO, rt.K9_REAL_PUBLICATION, rt.K9_REAL_POLICY, rt.K9_REAL_REVIEW, rt.K9_REAL_VERIFIER),
                         ("k9/K9_GO_04.json", "k9/K9_GO_04.PUBLICATION.json", "k9/VERIFIER_POLICY_04.json",
                          "k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json", "ext/k9_verifiers04.py"))
        self.assertEqual(len(bs.PUBLICATION_KEYS), 14)
        if not CODEX_GO_FORM.is_file():
            self.skipTest("the Codex GO form is not on this machine (read-only local input)")
        form = json.loads(CODEX_GO_FORM.read_bytes())
        self.assertEqual(form["required_installed_paths"], {"go": bs.K9_GO, "publication": rt.K9_REAL_PUBLICATION,
                                                            "reviewer_registry": rt.K9_REAL_POLICY})
        self.assertEqual(set(form["publication_keys"]), bs.PUBLICATION_KEYS)
        self.assertEqual(form["publication_schema"], "K9_GO_04_PUBLICATION_V1")

    def test_codex_r2_verifier_read_only_ast_and_the_sha256_flag(self):
        if not CODEX_R2.is_file():
            self.skipTest("the Codex R2 verifier is not on this machine (read-only local input)")
        raw = CODEX_R2.read_bytes()
        self.assertEqual(sha(raw), bs.CODEX_R2_UNSEALED_SHA256)
        found = rt.k9_real_source(raw)
        import ast
        functions = {n.name for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({"verify_approval", "verify_original", "verify_step"} <= functions)
        self.assertEqual(set(found["ORIGINAL_PINS"]), set(bs.ORIGINAL_NAMES))
        self.assertEqual((found["ORIGINAL_PINS"]["release"], found["ORIGINAL_PINS"]["policy"]), (bs.RELEASE, bs.POLICY))
        self.assertEqual(found["APPROVED_REGISTRY_PINS"], {})                       # delivered empty: HOLD
        self.assertEqual(bs.unsealed_sha256(raw), bs.CODEX_R2_UNSEALED_SHA256)
        sealed = raw.replace(b"APPROVED_REGISTRY_PINS = {}",
                             b'APPROVED_REGISTRY_PINS = {"DOWN": "' + b"d" * 64 + b'", "UP": "' + b"e" * 64 + b'"}', 1)
        self.assertEqual(bs.unsealed_sha256(sealed), bs.CODEX_R2_UNSEALED_SHA256)  # Codex's seal changes one line
        self.assertEqual(rt.k9_real_source(sealed)["APPROVED_REGISTRY_PINS"], {"DOWN": "d" * 64, "UP": "e" * 64})
        plans, go = self.plans("D")
        k9 = dict(self.real_k9(plans, "UP"), verifier=str(CODEX_R2))
        for flag, code in (("ab" * 32, "REAL_K9_VERIFIER_NOT_THE_PINNED_ONE"),
                           (sha(raw), "REAL_K9_ORIGINAL_PINS_NOT_THE_PLANS_ONES")):   # TEST-ONLY act B is not R2's
            out = self.base / ("r2-%s" % code)
            self.refused(code, self.real, "UP", out=out, plans=plans, go=go, real_k9=dict(k9, verifier_sha256=flag))
            self.assertFalse(os.path.lexists(str(out)))


# ====================================================================== the Linux proof's synthetic lots
class ProofEnv(kit.Env):
    """kit.Env with the proof's epoch-04 path strings; plan copies go to a shadow folder (the runner writes them under
    /var/lib/c3po/...; nothing is written there from here)."""

    def k9_plan(self, *args, **kwargs):
        real, self.daydir = self.daydir, self.shadow
        try:
            return kit.Env.k9_plan(self, *args, **kwargs)
        finally:
            self.daydir = real


class ProofLots(Base):
    def proof_env(self):
        from datetime import datetime, timezone
        env = ProofEnv.__new__(ProofEnv)
        stamp = "000000"
        base = self.base / "proof"
        base.mkdir()
        env.base, env.bin = base, Path("/usr/local/lib/l12proof-" + stamp)
        env.layout = {"schema": rt.LAYOUT_SCHEMA, "root": rt.EPOCH04_L12_ROOT, "veto_dir": rt.EPOCH04_VETO_DIR,
                      "unit_prefix": "l12proof-", "unit_name_suffix": "-e04", "python": proof.PY,
                      "binaries": {"docker": str(env.bin / "docker"), "systemd_run": "/usr/bin/systemd-run",
                                   "systemctl": "/usr/bin/systemctl"},
                      "docker_config": "/var/lib/l12proof-%s/docker-cli" % stamp}
        rt.validate_layout(env.layout, rt.Hold)
        now = datetime.now(timezone.utc)
        env.now0, env.t_sign = now, kit.past_signature_instant(now)
        env.nb, env.na = env.t_sign + timedelta(minutes=2), now + timedelta(hours=3)
        env.assets = base / "assets"
        (env.assets / "k9").mkdir(parents=True)
        for p in kit.ASSETS.glob("*.py"):
            (env.assets / p.name).write_bytes(p.read_bytes())
        env.docs = base / "docs"
        env.docs.mkdir()
        env.secrets = Path(rt.EPOCH04_K9_ROOT + "/secrets")
        env.env_file = env.secrets / "provider.env"
        env.tools, env.daydir = Path(rt.EPOCH04_K9_TOOLS), Path(rt.EPOCH04_K9_DAY)
        env.receipts = env.daydir / "receipts"
        env.shadow = base / "shadow-day"
        (env.shadow / "plans").mkdir(parents=True)
        env.k9_request = env.assets / "k9" / "K9_04_STEP_SET_REQUEST.json"
        env.k9_request.write_bytes(kit.canonical({"schema": "K9_04_STEP_SET_REQUEST_V1", "synthetic": True,
                                                  "image": {"id": kit.IMAGE, "revision": kit.LIT["REVISION"],
                                                            "package_sha256": kit.LIT["PACKAGE"]}}))
        env.k9_go = env.assets / "k9" / "K9_GO_04.json"
        env.k9_go.write_bytes(kit.canonical({"schema": "K9_04_SYNTHETIC_GO_NOT_AN_AUTHORIZATION"}))
        return env

    def test_proof_lots_bind_under_the_v33f_pins(self):
        env = self.proof_env()
        lay = env.layout
        stub = bs.runtime_stub(lay)
        prepared = kit.z(env.t_sign - timedelta(minutes=30))
        spec, ops = proof.up_spec(env, proof.plan_up(time.time()))
        up = bind.build_lot(spec, lay, stub, prepared, env.base, physical=True)[2]      # the physical install's ABI
        self.assertEqual(up["k9"]["networks"], DNET)
        self.assertTrue(set(rt.K9_REAL_FIXED_FILES) <= set(up["files"]))
        reader, sup, derivation = proof.proof_unit_rows(lay, lay["binaries"]["docker"], lay["docker_config"])
        down_spec, opening, hold = proof.proof_down_spec(env, reader, sup, env.t_sign, "ab" * 32, "cd" * 32,
                                                         {"commit_result": "ef" * 32, "publish_launch": "fe" * 32},
                                                         proof.plan_down(time.time()))
        _, _, down, q, extra = bind.build_lot(down_spec, lay, stub, prepared, env.base, physical=False)
        fam = inst.family_core()
        with self.assertRaisesRegex(rt.Hold, r"\ASESSION_OPEN_NOT_THE_MONDAY_ONE\Z"):  # the proof's expected verdict
            rt.validate_authority(down, q, fam, rt.Hold, physical=True, files_raw=extra)
        pins = proof.v33f_pins(up, down, lay)
        self.assertTrue(pins["ok"], pins)
        # the v3.3 proof rows (one shared network) would now be refused before the open check
        old = json.loads(json.dumps(down))
        step = [s for s in old["extended"]["steps"] if s["step"] == "session_start"][0]
        network_word(step["effect"], "c3po_default")
        network_word(step["pre_effect"], "c3po_default")
        with self.assertRaisesRegex(rt.Hold, r"\ASESSION_READER_NETWORK_NOT_DNET\Z"):
            rt.validate_authority(old, q, fam, rt.Hold, physical=True)
        # and the v3.3 UP lot's shared-default K9 networks would not bind physically
        legacy = json.loads(json.dumps(spec))
        legacy["k9"]["networks"] = {"PROVIDER": "bridge", "DATABASE": "c3po_default", "DATABASE_AND_PROVIDER": "c3po_default"}
        with self.assertRaisesRegex(rt.Hold, r"\AK9_NETWORKS_NOT_DNET\Z"):
            bind.build_lot(legacy, lay, stub, prepared, env.base, physical=True)
        self.assertEqual(sorted(ops), sorted(["prove_launch", "collect_launch", "commit_launch", "publish_launch",
                                              "components_launch"]))


def main():
    loader = unittest.TestLoader()
    tests = unittest.TestSuite()
    for case in (Networks, RuntimeReal, Writer, Kill, FormAndCodex, ProofLots):
        tests.addTests(loader.loadTestsFromTestCase(case))
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(tests)
    print(json.dumps({"schema": "L12HOST_V33F_TEST_RESULT", "python": "%d.%d.%d" % sys.version_info[:3],
                      "platform": sys.platform, "tests": result.testsRun, "failures": len(result.failures),
                      "errors": len(result.errors), "skipped": len(result.skipped), "ok": result.wasSuccessful(),
                      "temp_parent": dict(kit.TEMP_PARENT)}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
