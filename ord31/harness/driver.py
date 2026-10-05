"""CI-only directed driver. Imports the exact mounted launcher without changing it.

main's documented clock/child_argv seams are the only seams used. Stand-in child
and synthetic shared catalog lock do not prove certified worker intake.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from datetime import date, timedelta

CASE, TOKEN, EXPECTED_PIN = sys.argv[1:]
if CASE not in {"term", "kill", "handover", "exit1", "exit0"}:
    raise SystemExit("unknown directed case")
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ord31_exact_reader_launcher", HERE / "reader_launcher.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
sys.path.insert(0, launcher.APP_ROOT)
from app.r2d2_v2_calendar import ShadowCalendar
from app.r2d2_v2_epoch_assembler import SESSIONS
from app.r2d2_v2_massive_maintenance import journal_access

if launcher.own_sha256() != EXPECTED_PIN or os.environ.get(launcher.LAUNCHER_PIN_ENV) != EXPECTED_PIN:
    raise SystemExit("mounted launcher or environment pin mismatch")
details = ShadowCalendar().details(date.fromisoformat(sorted(SESSIONS)[0]))
directory = Path("/tmp") / ("ord31-" + TOKEN)
directory.mkdir(mode=0o700)

# The child acquires the packaged real flock helper on the journal read-only bind.
# Every output string below is synthetic; the forbidden strings must be withheld.
CHILD = r'''
import json, os, signal, sys, time
from pathlib import Path
sys.path.insert(0, '/app')
from app.r2d2_v2_massive_maintenance import journal_access
case, root, directory, marker = sys.argv[1:]
directory = Path(directory)
index = len(list(directory.glob('child-*.json'))) + 1
if case == 'kill':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
with journal_access(Path(root)):
    print('US:SYNTH PRIVATE FREE TEXT', file=sys.stderr, flush=True)
    print('INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","note":"US:SYNTH"}', file=sys.stderr, flush=True)
    print('INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","note":"US:SYNTH","note":"SAFE_CODE"}', file=sys.stderr, flush=True)
    print('INFO:__main__:V2 status {"schema":"R2D2_V2_COLLECTOR_STATUS_V2","nested":{"note":"US:SYNTH","note":"SAFE_CODE"}}', file=sys.stderr, flush=True)
    public = {'schema':'R2D2_V2_COLLECTOR_STATUS_V2', 'mode':'CERTIFIED', 'child_pid':os.getpid(), 'child_index':index}
    print('INFO:__main__:V2 status ' + json.dumps(public, sort_keys=True), file=sys.stderr, flush=True)
    pending = directory / ('pending-%d.json' % index)
    with pending.open('x') as output:
        json.dump({'pid':os.getpid(), 'ready_monotonic':time.monotonic(), 'index':index, 'marker':marker}, output)
    os.replace(pending, directory / ('child-%d.json' % index))
    if case == 'exit0':
        print('{"status":"OFF","collection":false}', flush=True)
        raise SystemExit(0)
    if case == 'exit1':
        from app.r2d2_v2_sources import SourceUnavailable
        raise SourceUnavailable('RAW_DIRECTED_TEST_FAILURE')
    time.sleep(3600)
'''

frozen = details["open"] - timedelta(hours=1)

def clock():
    if CASE != "handover":
        return frozen
    first = directory / "child-1.json"
    second = directory / "child-2.json"
    if second.exists():
        ready = json.loads(second.read_text())["ready_monotonic"]
        return details["close"] + timedelta(minutes=20) if time.monotonic() - ready >= 1 else details["open"]
    if first.exists():
        first_event = json.loads(first.read_text())
        try:
            os.kill(first_event["pid"], 0)
        except ProcessLookupError:
            return details["open"] - timedelta(seconds=10)
        if time.monotonic() - first_event["ready_monotonic"] >= 1:
            return details["open"] - timedelta(seconds=90)
    return details["open"] - timedelta(seconds=120)

stand_in = [sys.executable, "-I", "-B", "-c", CHILD, CASE,
            os.environ["C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR"], str(directory), "ord31-stand-in-" + TOKEN]
result = launcher.main([], utcnow=clock, child_argv=stand_in)
children = [json.loads(path.read_text()) for path in sorted(directory.glob("child-*.json"))]
if len(children) != (2 if CASE == "handover" else 1):
    raise SystemExit("wrong number of observed real children")
for child in children:
    try:
        os.kill(child["pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise SystemExit("a child PID is still present after main returned")
# One immediate request, no retry: actual read-only bind and packaged helper.
with journal_access(Path(os.environ["C3PO_R2D2_V2_MASSIVE_JOURNAL_DIR"]), exclusive=True):
    pass
proof = {"case": CASE, "token": TOKEN, "launcher_sha256": EXPECTED_PIN,
         "children": [{"pid": item["pid"], "index": item["index"]} for item in children],
         "child_pids_absent_after_main": True, "exclusive_lock_immediate_after_main": True,
         "launcher_main_exit": result, "worker_kind": "SYNTHETIC_STAND_IN",
         "clock_kind": "DIRECTED_SEAM" if CASE == "handover" else "FROZEN_SEAM",
         "real_worker_input_proof": "NOT_COVERED"}
print("ORD31_PROOF " + json.dumps(proof, sort_keys=True), flush=True)
raise SystemExit(result)
