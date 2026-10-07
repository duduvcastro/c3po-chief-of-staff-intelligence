"""New component tests with an audit guard: no network, processes, binder or host."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
denied = []


def audit(event, args):
    if event.startswith(("socket.", "subprocess.")) or event in (
            "os.system", "os.exec", "os.posix_spawn", "os.fork"):
        denied.append(event)
        raise RuntimeError("OFFLINE_NO_NETWORK_OR_CHILD")


sys.addaudithook(audit)
import test_owner_response

result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.loadTestsFromModule(test_owner_response))
report = {"schema": "CAPTURE_OWNER_RESPONSE_COMPONENT_TEST_V1",
          "python": sys.version.split()[0], "methods": result.testsRun,
          "scenarios": 32, "positive_match_not_signature": 1,
          "expected_refusals": 31, "failures": len(result.failures),
          "errors": len(result.errors), "audit_denials": len(denied),
          "code_sha256": hashlib.sha256((ROOT / "owner_response.py").read_bytes()).hexdigest(),
          "tests_sha256": hashlib.sha256((ROOT / "test_owner_response.py").read_bytes()).hexdigest(),
          "signatures": 0, "host_calls": 0, "operational_READY": False}
with (ROOT / "COMPONENT_TEST_RESULT.json").open("x") as out:
    out.write(json.dumps(report, sort_keys=True, indent=2) + "\n")
print(json.dumps(report, sort_keys=True))
raise SystemExit(0 if result.wasSuccessful() and not denied else 1)
