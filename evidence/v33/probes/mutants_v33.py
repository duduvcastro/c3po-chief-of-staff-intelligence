"""Mutation checks of the v3.3 tests (scratch copies only; the delivery is never written).
argv: <delivery l12host dir> <scratch dir> <python>. Prints JSON {mutant: {applied, rc, failing tests}}."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

fam, scratch, py = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
MUTANTS = {
    "engine_no_failure_key": ("l12host_effect.py",
                              '            out["unit_start_failure"] = dict(failure)\n',
                              '            pass\n'),
    "engine_excerpt_unbounded": ("l12host_effect.py",
                                 "for b in err[:STDERR_EXCERPT_BYTES])", "for b in err)"),
    "fake_no_mount_refusal": ("tests/kit.py",
                              'if any(mounts.get(prefix) == "failed" for prefix in prefixes):',
                              'if False:'),
    "fake_only_exact_path": ("tests/kit.py",
                             'if any(mounts.get(prefix) == "failed" for prefix in prefixes):',
                             'if mounts.get(path) == "failed":'),
    "extended_no_unit_diag": ("l12host_extended.py",
                              '        s.unit_diag(key, out["unit_start_failure"])\n', '        pass\n'),
    "f1_no_cross_check": ("lots/build_specs.py",
                          "        cross = down_matches_up(up_real_dir, layout_path, extra, m)\n",
                          "        cross = None\n"),
    "f1_no_capture_compare": ("lots/build_specs.py",
                              '    refuse(up[UP_CAPTURE_ANCHOR] == extra[DOWN_CAPTURE_PLAN], "REAL_DOWN_CAPTURE_PLAN_NOT_THE_UP_ONE")\n',
                              ''),
    "low6_relative_not_absolute": ("lots/build_specs.py",
                                   '    target = Path(os.path.abspath(str(out_dir)))\n    refuse(target.is_dir()',
                                   '    target = Path(out_dir)\n    refuse(target.is_dir()'),
    "proof_dump_e04_only": ("linux_systemd_proof.py",
                            'if "e04" in row or layout["unit_prefix"] in row]', 'if "e04" in row]'),
    "proof_mirror_check_loaded_ok": ("linux_systemd_proof.py",
                                     '"mnt_mount_not_found_like_host": mnt.get("LoadState") == "not-found"',
                                     '"mnt_mount_not_found_like_host": mnt.get("LoadState") != "loaded" or mnt.get("ActiveState") != "failed"'),
}
out = {}
for name, (rel, old, new) in MUTANTS.items():
    root = scratch / name
    if root.exists():
        shutil.rmtree(str(root))
    shutil.copytree(str(fam), str(root / "l12host"), ignore=shutil.ignore_patterns("__pycache__"))
    path = root / "l12host" / rel
    os.chmod(str(path), 0o600)
    text = path.read_text()
    applied = text.count(old) == 1
    path.write_text(text.replace(old, new))
    tmp = root / "tmp"
    tmp.mkdir()
    p = subprocess.run([py, "-I", "-S", "-B", str(root / "l12host" / "tests" / "test_v33.py")], capture_output=True,
                       env={"PATH": "/usr/bin:/bin", "L12_TEST_TMP": str(tmp), "LANG": "C.UTF-8"}, timeout=1200)
    failing = sorted(set(re.findall(r"^(?:FAIL|ERROR): (test_\w+)", p.stderr.decode("utf-8", "replace"), re.M)))
    out[name] = {"applied": applied, "rc": p.returncode, "failing": failing}
    shutil.rmtree(str(root), ignore_errors=True)
print(json.dumps(out, indent=1, sort_keys=True))
