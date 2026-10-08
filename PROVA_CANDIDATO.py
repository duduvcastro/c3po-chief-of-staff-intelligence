"""Linux/macOS fixture proof entrypoint; not a server installation/dispatch."""
import ast
import hashlib
import json
import os
import platform
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).absolute().parent
os.chdir(ROOT)
manifest_data = (ROOT / "MANIFEST.json").read_bytes()
manifest = json.loads(manifest_data)
verified = []
for name, record in manifest["files"].items():
    if Path(name).name != name:
        raise SystemExit("INVALID_MANIFEST_MEMBER")
    data = (ROOT / name).read_bytes()
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise SystemExit("SOURCE_MANIFEST_DIVERGENCE")
    if name.endswith(".py"):
        ast.parse(data, filename=name)
    verified.append(name)
suite = unittest.defaultTestLoader.discover(str(ROOT), pattern="test_candidates.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
record = {"schema": "F2_F6_LOCAL_FIXTURE_RESULT_V1", "scope": "CONTROL_PLANE_AND_CONTRACT_FIXTURES_ONLY",
          "platform": platform.system(), "python": platform.python_version(),
          "manifest_sha256": hashlib.sha256(manifest_data).hexdigest(), "verified": sorted(verified),
          "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
          "status": "PASS_FIXTURE_ONLY" if result.wasSuccessful() else "FAIL_HOLD",
          "full_rev1_integration": False, "physical_runtime_accepted": False,
          "production_adapters_present": False, "operational_GO": False}
data = (json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
fd = os.open(ROOT / "RESULT.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    os.write(fd, data)
    os.fsync(fd)
finally:
    os.close(fd)
sys.exit(0 if result.wasSuccessful() else 1)
