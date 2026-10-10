"""SYNTHETIC host program (tests only): prints one FIXTURE_STEP_RECEIPT_V1 line. argv: --role R [--sleep S]."""
import json, os, sys, time
from datetime import datetime, timezone
args = sys.argv[1:]
role = args[args.index("--role") + 1]
if "--sleep" in args:
    time.sleep(float(args[args.index("--sleep") + 1]))
assert os.getpgrp() == os.getsid(0) != os.getpid(), "NOT_IN_OUTER_GROUP"
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
print(json.dumps({"schema": "FIXTURE_STEP_RECEIPT_V1", "role": role, "status": "COMPLETE", "completed_at": now},
                 sort_keys=True, separators=(",", ":")))
