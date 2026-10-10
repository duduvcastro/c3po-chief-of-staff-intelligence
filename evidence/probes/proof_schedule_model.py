"""PROOF_SCHEDULE_MODEL (Fable v3.2 build, offline): runs linux_systemd_proof.model() for EVERY start second of one
BRT day (the start-minute rules depend only on the BRT time of day; Brazil has no DST), with the ENGINE's own rule
(l12host_effect.start_minute_violation) tabulated per second. Reports the timer-driven part's duration distribution,
the H1 margins and the worst start instants. Pure computation, no effect."""
import json, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
FAM = Path(sys.argv[1])
sys.path.insert(0, str(FAM / "tests")); sys.path.insert(0, str(FAM))
import kit
import linux_systemd_proof as proof
fx, rt = kit.fx, kit.rt
day0 = int(datetime(2026, 10, 12, 3, 0, tzinfo=timezone.utc).timestamp())      # 00:00:00 BRT of Monday 12/10
BAD = [fx.start_minute_violation(datetime.fromtimestamp(day0 + s, timezone.utc)) is not None for s in range(86400)]
bad = lambda t: BAD[(t - day0) % 86400]
# the tabulated rule IS the engine rule (spot check every 7 s over two days)
assert all(bad(t) == proof.engine_bad(t) for t in range(day0 - 86400, day0 + 86400, 7))
step = int(sys.argv[2]) if len(sys.argv) > 2 else 1
durs, worst, min_hold, max_hold, min_lead, waits = [], [], 10**9, -10**9, 10**9, 0
t0 = time.time()
for s in range(0, 86400, step):
    now = day0 + s
    m = proof.model(now, bad)
    d = (m["end"] - now) / 60
    durs.append(d)
    worst.append((d, s))
    min_hold, max_hold = min(min_hold, m["hold_minus_check"]), max(max_hold, m["hold_minus_check"])
    min_lead = min(min_lead, m["r0_minus_negatives_end"])
    if m["reader_check_at"] > m["up"][-1] + proof.MODEL_SECONDS["x1_done"] + 2 + proof.MODEL_SECONDS["down_build"] + proof.MODEL_SECONDS["bind"]:
        waits += 1
srt = sorted(durs)
q = lambda p: round(srt[min(len(srt) - 1, int(p * len(srt)))], 1)
worst.sort(reverse=True)
hhmmss = lambda s: "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)
out = {"schema": "L12HOST_V32_PROOF_SCHEDULE_MODEL", "rule": "l12host_effect.start_minute_violation (tabulated, checked)",
       "start_points": len(durs), "step_seconds": step, "assumed_durations_seconds": proof.MODEL_SECONDS,
       "constants": {"UP_LEAD": proof.UP_LEAD_SECONDS, "UP_GAP": proof.UP_GAP_SECONDS, "SLOT_SPAN": list(proof.SLOT_SPAN),
                     "DOWN_LEAD": proof.DOWN_LEAD_SECONDS, "DOWN_SPAN": list(proof.DOWN_SPAN),
                     "HOLD_CHECK_SECONDS": proof.HOLD_CHECK_SECONDS, "MAX_HOLD_SECONDS": fx.MAX_HOLD_SECONDS},
       "timer_part_minutes": {"min": q(0), "median": q(0.5), "p90": q(0.9), "p99": q(0.99), "max": round(srt[-1], 1),
                              "over_45": round(sum(d > 45 for d in durs) / len(durs), 4),
                              "over_60": round(sum(d > 60 for d in durs) / len(durs), 4)},
       "worst_starts_BRT": [{"start_BRT": hhmmss(s), "minutes": round(d, 1)} for d, s in worst[:5]],
       "h1": {"reader_check_hold_minus_now_seconds_min": min_hold, "max": max_hold,
              "engine_limit_seconds": fx.MAX_HOLD_SECONDS, "false_red_start_points": None,
              "fraction_of_starts_where_the_reader_negative_waits": round(waits / len(durs), 4)},
       "r0_minus_negatives_end_seconds_min": min_lead, "compute_seconds": round(time.time() - t0, 1)}
out["h1"]["false_red_start_points"] = 0 if max_hold <= fx.MAX_HOLD_SECONDS and min_hold > 0 else "SEE_MARGINS"
print(json.dumps(out, indent=1, sort_keys=True))
