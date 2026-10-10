"""UP_GRID_REALTIME_REHEARSAL (Fable v3.2 build, Darwin, synthetic, non-physical kit world, in-process): the v3.2 proof's
UP lot (proof.up_spec: F-E grid, task window [at - 30 s, at + 90 s], REAL-mode decoders with pinned synthetic verifiers)
run slot by slot AT THE REAL INSTANTS, with the wall-clock start-minute rules ON (minute_rule=True), so the tight
windows meet the real-time gates (task window, budget floor, K9 phase window, dependency receipts)."""
import json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
FAM = Path(sys.argv[1])
sys.path.insert(0, str(FAM / "tests")); sys.path.insert(0, str(FAM))
import kit
import linux_systemd_proof as proof
rt = kit.rt
e = kit.Env()
out = {"schema": "L12HOST_V32_UP_GRID_REALTIME_REHEARSAL_DARWIN", "python": "%d.%d.%d" % sys.version_info[:3]}
try:
    e.prepare()
    t0 = int(time.time())
    times = [proof.next_clear(t0 + 60, proof.SLOT_SPAN)]
    for _ in range(4):
        times.append(proof.next_clear(times[-1] + proof.UP_GAP_SECONDS, proof.SLOT_SPAN))
    spec, ops = proof.up_spec(e, times)
    e.install_spec(spec)
    e.up_fakes(ops)
    out["slots_planned"] = [rt.iso(proof.utc(t)) for t in times]
    out["results"] = {}
    for slot, t in zip(("P1", "P2", "P3", "P4", "X1"), times):
        while time.time() < t:
            time.sleep(min(0.2, max(0.0, t - time.time())))
        started = time.time()
        code, res = e.run("UP", slot, minute_rule=True)
        out["results"][slot] = {"exit": code, "status": res["status"], "code": res["code"],
                                "effect_calls": res["effect_calls"], "result_class": res.get("result_class"),
                                "diagnostics": res.get("diagnostics"), "late_seconds": round(started - t, 3),
                                "run_seconds": round(time.time() - started, 2)}
    want = {s: "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE" for s in ("P1", "P2", "P3", "P4")}
    want["X1"] = "EXTENDED_COMPLETE"
    out["ok"] = all(out["results"][s]["status"] == w for s, w in want.items())
finally:
    e.cleanup()
print(json.dumps(out, indent=1, sort_keys=True))
