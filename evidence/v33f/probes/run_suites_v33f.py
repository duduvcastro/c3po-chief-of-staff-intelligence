"""v3.3f suite runs (Fable, Mac, offline): N full runs, each = the four suites in sequence, on one interpreter, against
the sealed family; the family seal is read before and after every run. Synthetic only.

    python3 -I -B run_suites_v33f.py <family dir> <python> <runs> <names out> > RUNS.json

v2: a failing suite also keeps a bounded excerpt of its unittest failure blocks (`failure_excerpt`, <= 6000 chars).
v1 (sha256 eebc895988604a8897f0dbfb58ccfe63261f15bd28b2792815e378f33ccc3715, identical otherwise) produced
V33F_TEST_RUNS_PY312_DARWIN.json and V33F_TEST_RUNS_PY39_DARWIN.json; v2 produced V33F_TEST_RERUN_PY312_DARWIN.json.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

SUITES = ("tests/test_l12host.py", "tests/test_lots_patch_v34.py", "tests/test_v33.py", "tests/test_v33f.py")


def seal(family):
    return hashlib.sha256((Path(family) / "SHA256SUMS").read_bytes()).hexdigest()


def main(family, python, runs, names_out):
    out = {"schema": "L12HOST_V33F_TEST_RUNS", "python": python, "family_seal_sha256": seal(family), "runs": []}
    names = []
    for run in range(1, int(runs) + 1):
        before, began, mono = seal(family), datetime.now(timezone.utc), time.monotonic()
        row = {"run": run, "started_utc": began.isoformat().replace("+00:00", "Z"), "suites": {}}
        for suite in SUITES:
            t0 = time.monotonic()
            proc = subprocess.run([python, "-I", "-S", "-B", str(Path(family) / suite)], capture_output=True, timeout=3600)
            try:
                summary = json.loads(proc.stdout.decode().strip().splitlines()[-1])
            except (ValueError, IndexError):
                summary = {"unparsed_stdout_sha256": hashlib.sha256(proc.stdout).hexdigest()}
            lines = [l for l in proc.stderr.decode("utf-8", "replace").splitlines()
                     if l.endswith((" ... ok", " ... FAIL", " ... ERROR")) or " ... skipped" in l]
            if run == 1:
                names += ["%s :: %s" % (suite, l) for l in lines]
            err = proc.stderr.decode("utf-8", "replace")
            problems = [l for l in err.splitlines() if l.startswith(("FAIL: ", "ERROR: "))]
            first = err.find("\n" + "=" * 70)
            excerpt = err[first + 1:first + 6001] if problems and first >= 0 else ""
            row["suites"][suite] = {"rc": proc.returncode, "tests": summary.get("tests"),
                                    "failures": summary.get("failures"), "errors": summary.get("errors"),
                                    "skipped": summary.get("skipped"), "ok": summary.get("ok"),
                                    "python": summary.get("python"), "temp_parent": summary.get("temp_parent"),
                                    "seconds": round(time.monotonic() - t0, 1), "problems": problems[:10],
                                    "failure_excerpt": excerpt}
        row["seconds"] = round(time.monotonic() - mono, 1)
        row["family_seal_unchanged"] = before == seal(family) == out["family_seal_sha256"]
        out["runs"].append(row)
    Path(names_out).write_text("\n".join(names) + "\n", "utf-8")
    out["all_ok"] = all(r["family_seal_unchanged"] and all(s["ok"] is True and s["rc"] == 0 for s in r["suites"].values())
                        for r in out["runs"])
    print(json.dumps(out, sort_keys=True, indent=1))
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
