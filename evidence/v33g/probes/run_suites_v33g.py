"""v3.3g suite runs (Fable, Mac, offline): ONE run of every suite on one interpreter, against the sealed family; the
family seal is read before and after every suite. Synthetic only. tests/test_grid_e.py runs twice: without
L12_ISSUED_D_DIR (as in CI: its issued-dir test skips) and with it (the issued D run directory, read only).

    python3 -I -B run_suites_v33g.py <family dir> <python> <issued D dir> <names out> [suite ...] > RUNS.json

With suite arguments only those run (each given as `tests/<file>` or `tests/test_grid_e.py+issued`). Derived from
evidence/v33f/probes/run_suites_v33f.py v2 (same parsing and bounded failure excerpt).
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SUITES = ("tests/test_l12host.py", "tests/test_lots_patch_v34.py", "tests/test_v33.py", "tests/test_v33f.py",
          "tests/test_grid_e.py", "tests/test_grid_e.py+issued")


def seal(family):
    return hashlib.sha256((Path(family) / "SHA256SUMS").read_bytes()).hexdigest()


def main(family, python, issued, names_out, *only):
    out = {"schema": "L12HOST_V33G_TEST_RUNS", "python": python, "family_seal_sha256": seal(family),
           "issued_d_dir": issued, "suites": {}}
    names = []
    for suite in (only or SUITES):
        file, _, flag = suite.partition("+")
        env = {k: v for k, v in os.environ.items() if k != "L12_ISSUED_D_DIR"}
        if flag == "issued":
            env["L12_ISSUED_D_DIR"] = issued
        before, t0 = seal(family), time.monotonic()
        began = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        proc = subprocess.run([python, "-I", "-S", "-B", str(Path(family) / file)], capture_output=True, timeout=3600,
                              env=env)
        try:
            summary = json.loads(proc.stdout.decode().strip().splitlines()[-1])
        except (ValueError, IndexError):
            summary = {"unparsed_stdout_sha256": hashlib.sha256(proc.stdout).hexdigest()}
        err = proc.stderr.decode("utf-8", "replace")
        all_lines = err.splitlines()
        lines = []
        for i, l in enumerate(all_lines):                  # a docstring test prints its name on the line before
            if l.endswith((" ... ok", " ... FAIL", " ... ERROR")) or " ... skipped" in l:
                lines.append(l if l.startswith("test") or i == 0 else all_lines[i - 1] + " | " + l)
            elif l in ("ok", "FAIL", "ERROR") and i > 0 and " ... " in all_lines[i - 1]:   # a test that wrote to stderr
                lines.append(all_lines[i - 1] + " | " + l)
        names += ["%s :: %s" % (suite, l) for l in lines]
        problems = [l for l in err.splitlines() if l.startswith(("FAIL: ", "ERROR: "))]
        first = err.find("\n" + "=" * 70)
        excerpt = err[first + 1:first + 6001] if problems and first >= 0 else ""
        out["suites"][suite] = {"rc": proc.returncode, "started_utc": began, "tests": summary.get("tests"),
                                "failures": summary.get("failures"), "errors": summary.get("errors"),
                                "skipped": summary.get("skipped"), "ok": summary.get("ok"),
                                "python": summary.get("python"), "temp_parent": summary.get("temp_parent"),
                                "issued_d_dir_given": summary.get("issued_d_dir_given"),
                                "seconds": round(time.monotonic() - t0, 1), "problems": problems[:10],
                                "failure_excerpt": excerpt, "family_seal_unchanged": before == seal(family)}
    Path(names_out).write_text("\n".join(names) + "\n", "utf-8")
    out["all_ok"] = all(s["ok"] is True and s["rc"] == 0 and s["family_seal_unchanged"] for s in out["suites"].values())
    out["family_seal_unchanged"] = seal(family) == out["family_seal_sha256"]
    print(json.dumps(out, sort_keys=True, indent=1))
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
