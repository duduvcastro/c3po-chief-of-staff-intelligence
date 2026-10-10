"""SYNTHETIC J4-shaped host program (tests only). It is NOT the Codex J4 hot worker: it takes the J4 argv
(--registry-record-base64 <b64> --mode FIXTURE), reads the DERIVED registry it points to, and prints a process receipt
with the J4 ABI so the shell's HOT_J_V1 decoder and the outer-group containment are exercised."""
import base64, hashlib, json, os, sys
from datetime import datetime, timezone
def c(v): return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
def h(b): return hashlib.sha256(b).hexdigest()
args = sys.argv[1:]
assert len(args) == 4 and args[0] == "--registry-record-base64" and args[2] == "--mode" and args[3] == "FIXTURE", "ARGV"
record = json.loads(base64.b64decode(args[1], validate=True))
registry = open(record["path"], "rb").read()
assert h(registry) == record["sha256"], "REGISTRY_RECORD"
r = json.loads(registry)
request = open(r["originals"]["request"]["path"], "rb").read()
bound = open(r["originals"]["bound"]["path"], "rb").read()
q = json.loads(request)
scope = [q["epoch"], q["session"], q["previous_session"], q["track"], "admission_manifest"]
assert r["outer_scope"] == scope, "SCOPE"
assert os.getpgrp() == os.getsid(0) != os.getpid(), "NOT_IN_OUTER_GROUP"
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
config = h(b"SYNTHETIC_FINAL_CONFIG")
writer = c({"schema": "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1", "status": "PUBLISHED_VERIFIED", "mode": "PUBLISH",
            "code": None, "epoch": q["epoch"], "session": q["session"], "capacity_config_sha256": config,
            "massive_bars_enabled": True, "published_at": now}) + b"\n"
slot = {"status": "COMPLETE", "code": "J_COMPLETE", "attempt_key": h(c([q["epoch"], q["session"], "J_ADMISSION_FAMILY_V1"])),
        "observation_sha256": h(b"obs"), "veto_sha256": h(b"veto"), "config_sha256": config, "manifest_sha256": h(b"m"),
        "operational_GO": False, "writer_receipt_base64": base64.b64encode(writer).decode("ascii"),
        "writer_receipt_sha256": h(writer), "writer_exit_code": 0, "mode": "FIXTURE"}
print(c({"schema": "R2D2_HOT_IMAGE10_PROCESS_RECEIPT_CANDIDATE_V1", "mode": "FIXTURE", "protocol": r["protocol"],
         "registry_sha256": h(registry), "request_sha256": h(request), "bound_sha256": h(bound),
         "outer_attempt_key": h(c(scope)), "pid": os.getpid(), "parent_pid": os.getppid(), "process_group": os.getpgrp(),
         "warm_at": now, "image_observed_at": now, "image_valid_until": now, "general_observation_base64": None,
         "slot_result": slot, "actual_installation_certified": False, "operational_GO": False}).decode("ascii"))
