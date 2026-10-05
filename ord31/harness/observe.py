"""Read-only CI observation while the directed child holds the shared lock."""
import json
import os
from pathlib import Path
import sys

token = sys.argv[1]
sys.path.insert(0, "/app")
from app.r2d2_v2_massive_maintenance import journal_access
from app.r2d2_v2_sources import SourceUnavailable

directory = Path("/tmp") / ("ord31-" + token)
children = list(directory.glob("child-*.json"))
if not children:
    raise SystemExit(2)
child = json.loads(sorted(children)[-1].read_text())
os.kill(child["pid"], 0)
try:
    with journal_access(Path(os.environ["C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR"]), exclusive=True):
        pass
except SourceUnavailable as error:
    if str(error) != "MASSIVE_MAINTENANCE_BUSY":
        raise
else:
    raise SystemExit("exclusive lock was not blocked by the live shared-lock child")
print(json.dumps({"token": token, "child_pid": child["pid"], "live_child": True,
                  "exclusive_lock_blocked_by_shared_child": True}, sort_keys=True))
