"""v3.3g mutation probe (Fable, Mac, offline, SYNTHETIC): is the flipped test of tests/test_grid_e.py sensitive to the
v3.3g writer change? Each mutant is ONE literal replacement in a scratch copy of the family's lots/build_specs.py (the
sealed family is only read); tests/test_grid_e.py of that copy then runs WITHOUT L12_ISSUED_D_DIR (as in CI). A control
copy without mutation must pass.

    python3 -I -B mutants_v33g.py <family l12host dir> <python> <new work dir> > MUTANTS.json
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

TARGET = "lots/build_specs.py"
MUTANTS = {
    "ELECTED_BACK_TO_C_D": ('ELECTED_GRIDS = ("C", "D", "E")', 'ELECTED_GRIDS = ("C", "D")'),
    "ELECTED_ADDS_DRAFT3": ('ELECTED_GRIDS = ("C", "D", "E")', 'ELECTED_GRIDS = ("C", "D", "E", "DRAFT3_REJECTED")'),
    "WRITE_ELECTS_ONLY_C_D": ('refuse(type(grid) is dict and grid.get("id") in ELECTED_GRIDS, "REAL_PLANS_GRID_NOT_ELECTED",',
                              'refuse(type(grid) is dict and grid.get("id") in ("C", "D"), "REAL_PLANS_GRID_NOT_ELECTED",'),
    "VALIDATE_ELECTS_ONLY_C_D": ('refuse(type(grid) is dict and grid.get("id") in ELECTED_GRIDS and grid == generator()',
                                 'refuse(type(grid) is dict and grid.get("id") in ("C", "D") and grid == generator()'),
    "F1_GRID_CHECK_DROPPED": ('refuse(up_grid_id == m["grid"]["id"], "REAL_DOWN_GRID_NOT_THE_UP_ONE"',
                              'refuse(True, "REAL_DOWN_GRID_NOT_THE_UP_ONE"'),
}


def run(family, python):
    env = {k: v for k, v in os.environ.items() if k != "L12_ISSUED_D_DIR"}
    proc = subprocess.run([python, "-I", "-S", "-B", str(family / "tests" / "test_grid_e.py")], capture_output=True,
                          timeout=1800, env=env)
    err = proc.stderr.decode("utf-8", "replace")
    try:
        summary = json.loads(proc.stdout.decode().strip().splitlines()[-1])
    except (ValueError, IndexError):
        summary = {}
    return {"rc": proc.returncode, "tests": summary.get("tests"), "failures": summary.get("failures"),
            "errors": summary.get("errors"), "skipped": summary.get("skipped"),
            "failed": [l for l in err.splitlines() if l.startswith(("FAIL: ", "ERROR: "))]}


def main(family, python, work):
    family, work = Path(family), Path(work)
    os.mkdir(str(work), 0o700)
    source = (family / TARGET).read_text("utf-8")
    out = {"schema": "L12HOST_V33G_MUTANTS", "python": python,
           "family_seal_sha256": hashlib.sha256((family / "SHA256SUMS").read_bytes()).hexdigest(),
           "target": TARGET, "target_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "mutants": {}}
    for name, pair in [("CONTROL", None)] + sorted(MUTANTS.items()):
        copy = work / name / "l12host"
        shutil.copytree(str(family), str(copy))
        if pair:
            assert source.count(pair[0]) == 1, name
            target = copy / TARGET
            os.chmod(str(target), 0o600)
            target.write_text(source.replace(pair[0], pair[1]), "utf-8")
        row = run(copy, python)
        row["killed"] = row["rc"] != 0 if pair else None
        out["mutants"][name] = row
    out["control_passes"] = out["mutants"]["CONTROL"]["rc"] == 0
    out["killed"] = sum(1 for n, r in out["mutants"].items() if n != "CONTROL" and r["killed"])
    out["total"] = len(MUTANTS)
    out["family_seal_unchanged"] = hashlib.sha256((family / "SHA256SUMS").read_bytes()).hexdigest() == out["family_seal_sha256"]
    print(json.dumps(out, sort_keys=True, indent=1))
    return 0 if out["control_passes"] and out["killed"] == out["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:4]))
