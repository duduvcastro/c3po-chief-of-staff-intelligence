"""v3.3g probe (Fable, Mac, offline, SYNTHETIC): the REAL writer of one family end to end, through its own CLI.

    python3 -I -B real_lots_probe.py lots    <family l12host dir> <new work dir> [<E plans dir of another run>]
    python3 -I -B real_lots_probe.py compare <summary F.json> <summary G.json>
    python3 -I -B real_lots_probe.py kill-diff <KILL record A> <KILL record B>

`lots`: the family's generator (fresh module from its bytes; TEST-ONLY `source_pins` = the pinned de96aee9 value, as the
lots suite does) makes the plans of grid D (and E when the generator offers it) with TEST-ONLY act B / GO bytes; the
family's build_specs makes the SYNTHETIC REAL K9 inputs of each run (synthetic_real_inputs) and its CLI `write`s the
REAL UP and the REAL DOWN (D-NET networks, --k9-* flags, values map as the lots suite's values_for) and `validate`s
both dirs. With a third argument (an E plans dir made by another family), the writer is also asked for an E UP from it
(to record the refusal of a family that does not elect E). Prints one JSON summary: statuses and the sha256 of every
written file (never contents). `compare`: the D outputs of two summaries, file by file; for a differing JSON file the
differing key paths.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import types

TEST_GO = b'{"schema":"TEST_ONLY_K9_GO_NOT_AN_AUTHORIZATION"}\n'
TEST_ACT_B = b"TEST ONLY act B bytes, not the ADENDO\n"
DEADLINE = {("UP", "C"): "2026-10-10T17:20:00Z", ("UP", "D"): "2026-10-10T18:20:00Z",
            ("UP", "E"): "2026-10-10T19:20:00Z", "DOWN": "2026-10-12T00:44:00Z"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def listing(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha(p.read_bytes()) for p in sorted(root.rglob("*")) if p.is_file()}


def run(main, argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


def lots(family, work, e_plans_other=None):
    family, work = Path(family).resolve(), Path(work)
    os.mkdir(str(work), 0o700)
    lots_dir = family / "lots"
    sys.path.insert(0, str(lots_dir))
    import build_specs as bs                                   # noqa: E402  (inserts the family's own paths)
    gen_path = lots_dir / "k9tools" / "gen_k9_plans04.py"
    gen = types.ModuleType("gen_k9_plans04_probe")
    gen.__file__ = str(gen_path)
    exec(compile(gen_path.read_bytes(), str(gen_path), "exec"), gen.__dict__)
    gen.source_pins = lambda tree: (gen.RISK_SOURCE_PINS_04, 190)          # TEST ONLY (as the lots suite)
    act_b, go = work / "act_b.TEST_ONLY.txt", work / "go.TEST_ONLY.json"
    act_b.write_bytes(TEST_ACT_B)
    go.write_bytes(TEST_GO)
    module, doc = work / "verifier.TEST_ONLY.py", work / "doc.TEST_ONLY.json"
    module.write_bytes(bs.SYNTHETIC_MODULE)
    doc.write_bytes(b'{"synthetic":true}')
    layout = str(lots_dir / "layout.e04.DRAFT.json")
    out = {"schema": "L12HOST_V33G_REAL_LOTS_PROBE", "python": "%d.%d.%d" % sys.version_info[:3],
           "family": str(family), "work": str(work), "family_seal_sha256": sha((family / "SHA256SUMS").read_bytes()),
           "build_specs_sha256": sha((lots_dir / "build_specs.py").read_bytes()), "generator_sha256": sha(gen_path.read_bytes()),
           "elected_grids": list(bs.ELECTED_GRIDS), "electable": list(gen.ELECTABLE), "grids": {}}

    def values_for(spec):
        files = {local: rel for rel, local in spec["files"].items() if local.startswith("@P_")}
        named = {"@P_MANIFEST_DIRECTORY@": "/var/lib/c3po-capacity-e04/payload",
                 "@P_E6_DOCUMENT_PATH@": "/var/lib/c3po/r2d2-v2-k9-20261012/e6/E6_04.json",
                 "@P_J4_GENERAL_SOURCE_IDENTITY@": "SYNTHETIC_FILL_IN"}
        values = {}
        for name in bs.placeholders(spec):
            if name == bs.VERIFIERS_PLACEHOLDER:
                continue
            if name in files:
                values[name] = str(module if files[name].endswith(".py") else doc)
            else:
                values[name] = named.get(name, sha(name.encode("ascii")))
        return values

    def k9_argv(k9):
        argv = ["--k9-verifier", k9["verifier"], "--k9-verifier-sha256", k9["verifier_sha256"], "--k9-policy",
                k9["policy"], "--k9-review", k9["review"], "--k9-publication", k9["publication"]]
        for name, path in sorted(k9["originals"].items()):
            argv += ["--k9-original", name + "=" + path]
        return argv

    def write(lot, grid, plans, k9, up=None):
        spec = bs.build_up(plans=str(plans), go=str(go)) if lot == "UP" else bs.build_down(plans=str(plans), go=str(go))
        values = work / ("values-%s-%s.json" % (lot, grid))
        values.write_text(json.dumps(values_for(spec), sort_keys=True), "ascii")
        target = work / ("real-%s-%s" % (lot, grid))
        argv = ["write", "--out-dir", str(target), "--lot", lot, "--plans-dir", str(plans), "--go", str(go),
                "--layout", layout, "--secrets-root", bs.GEN_SECRETS_ROOT, "--network", "PROVIDER=bridge",
                "--network", "DATABASE=c3po_c3po_internal", "--network", "DATABASE_AND_PROVIDER=c3po_db_loopback",
                "--owner-deadline", DEADLINE[lot] if lot == "DOWN" else DEADLINE[lot, grid], "--values", str(values)]
        argv += k9_argv(k9[lot]) + (["--up-real-dir", str(up)] if up else [])
        code, text = run(bs.main, argv)
        result = json.loads(text)
        row = {"rc": code, "status": result.get("status"), "code": result.get("code"), "detail": result.get("detail"),
               "grid": result.get("grid"), "files": listing(target) if os.path.isdir(str(target)) else None}
        if code == 0:
            row.update(spec_sha256=result["spec_sha256"], sha256sums_sha256=result["sha256sums_sha256"],
                       start_windows_ok=all(r["ok"] for r in result["start_windows"]),
                       start_windows={r["slot"]: [r["at"], r["margin_seconds"]] for r in result["start_windows"]},
                       kill_record_sha256=result["kill_record"]["sha256"])
            if lot == "DOWN":
                cross = result["up_cross_check"]
                row["up_cross_check"] = {"grid": cross["grid"], "byte_identical": cross["byte_identical"]}
            vcode, vtext = run(bs.main, ["validate", "--out-dir", str(target), "--layout", layout])
            v = json.loads(vtext)
            row["validate"] = {"rc": vcode, "status": v.get("status"), "lot": v.get("lot"), "grid": v.get("grid"),
                               "code": v.get("code")}
        return target, row

    for grid in [g for g in ("D", "E") if g in gen.ELECTABLE]:
        plans = work / ("plans-%s" % grid)
        code, text = run(gen.main, ["plans", "--runner", str(lots_dir / "k9tools" / "k9_runner04.py"), "--grid", grid,
                                    "--app-tree", str(work), "--act-b", str(act_b),
                                    "--release", str(lots_dir / "up_inputs" / "release.CERTIFIED.04.json"),
                                    "--policy", str(lots_dir / "up_inputs" / "policy.04.json"), "--go", str(go),
                                    "--out", str(plans)])
        row = {"plans": {"rc": code, "stdout_sha256": sha(text.encode()), "ok": text.startswith("PLANS_OK"),
                         "files": listing(plans)}}
        k9 = bs.synthetic_real_inputs(work / ("real-k9-SYNTHETIC-%s" % grid), plans, act_b_raw=TEST_ACT_B)
        row["synthetic_real_inputs"] = listing(work / ("real-k9-SYNTHETIC-%s" % grid))
        up, row["UP"] = write("UP", grid, plans, k9)
        _, row["DOWN"] = write("DOWN", grid, plans, k9, up=up)
        out["grids"][grid] = row
    code, text = run(gen.main, ["check", "--runner", str(lots_dir / "k9tools" / "k9_runner04.py"), "--grid", "E"])
    out["check_grid_E"] = {"rc": code, "last_line": text.strip().splitlines()[-1] if text.strip() else ""}
    if e_plans_other:
        other = Path(e_plans_other)
        k9 = bs.synthetic_real_inputs(work / "real-k9-SYNTHETIC-E-other", other, act_b_raw=TEST_ACT_B)
        _, out["E_UP_from_other_plans"] = write("UP", "E", other, k9)
    out["family_seal_unchanged"] = sha((family / "SHA256SUMS").read_bytes()) == out["family_seal_sha256"]
    print(json.dumps(out, sort_keys=True, indent=1))
    return 0


def json_diff(a, b, path=""):
    if type(a) is not type(b):
        return [path or "/"]
    if isinstance(a, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(path + "/" + k)
            else:
                out += json_diff(a[k], b[k], path + "/" + k)
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [path + "[len]"]
        out = []
        for i, (x, y) in enumerate(zip(a, b)):
            out += json_diff(x, y, "%s[%d]" % (path, i))
        return out
    return [] if a == b else [path or "/"]


def compare(f_path, g_path):
    f, g = json.loads(Path(f_path).read_text()), json.loads(Path(g_path).read_text())
    rows = {}
    for part in ("plans", "synthetic_real_inputs", "UP", "DOWN"):
        a = f["grids"]["D"][part]
        b = g["grids"]["D"][part]
        fa = a.get("files") if part != "synthetic_real_inputs" else a
        fb = b.get("files") if part != "synthetic_real_inputs" else b
        differing = sorted(k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k))
        row = {"files": len(fb), "same_file_set": set(fa) == set(fb), "differing": differing}
        if part in ("UP", "DOWN"):
            row["validate"] = [a["validate"], b["validate"]]
        rows[part] = row
    print(json.dumps({"schema": "L12HOST_V33G_D_REAL_COMPARE", "f": {"family_seal": f["family_seal_sha256"],
                      "build_specs": f["build_specs_sha256"], "generator": f["generator_sha256"]},
                      "g": {"family_seal": g["family_seal_sha256"], "build_specs": g["build_specs_sha256"],
                            "generator": g["generator_sha256"]}, "D": rows}, sort_keys=True, indent=1))
    return 0


def kill_diff(a_file, b_file):
    a, b = json.loads(Path(a_file).read_bytes()), json.loads(Path(b_file).read_bytes())
    print(json.dumps({"a_sha256": sha(Path(a_file).read_bytes()), "b_sha256": sha(Path(b_file).read_bytes()),
                      "differing_paths": json_diff(a, b),
                      "row_sha256_equal": [r["row_sha256"] for r in a["rows"]] == [r["row_sha256"] for r in b["rows"]]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "lots":
        raise SystemExit(lots(*sys.argv[2:5]))
    if sys.argv[1] == "compare":
        raise SystemExit(compare(*sys.argv[2:4]))
    if sys.argv[1] == "kill-diff":
        raise SystemExit(kill_diff(*sys.argv[2:4]))
    raise SystemExit(2)
