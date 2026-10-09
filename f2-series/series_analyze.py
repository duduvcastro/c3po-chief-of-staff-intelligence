"""Offline F2 series analyzer over PUBLIC slot results only. No network, no host, no symbols.

Usage: python3 -I -S -B series_analyze.py RESULT_2126.json RESULT_2156.json ...
Emits: first observed PASS, last FAIL before it, gaps (missing/HOLD/refused slots),
regressions (PASS->FAIL, or present count falling between observed slots) and timings.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import series_runtime as s

OBSERVED = ("SLOT_OBSERVED_PASS", "SLOT_OBSERVED_FAIL")


def load(raw):
    value = json.loads(raw)
    s.need(type(value) is dict and value.get("schema") == "F2_PUBLIC_SLOT_RESULT_V1" and
           value.get("family") == s.FAMILY and value.get("slot") in s.SLOTS and
           value.get("scheduled_at") == s.SLOTS[value["slot"]], "RESULT_SCHEMA_INVALID")
    if value["status"] in OBSERVED:
        c = value["counts"]
        s.need(type(c) is dict and value["pass"] is (value["status"] == "SLOT_OBSERVED_PASS") and
               value["pass"] == (c["eligible_symbols"] >= s.RULE["minimum_eligible"] and
                                 s.RULE["denominator"] * c["present_eligible_symbols"] >= s.RULE["numerator"] * c["eligible_symbols"]),
               "RESULT_PASS_INCONSISTENT")
        s.need(value["logical_fetch_calls"] == 1 and value["http_status"] == 200, "RESULT_FETCH_INCONSISTENT")
    else:
        s.need(value["status"] == "SLOT_HOLD", "RESULT_STATUS_INVALID")
    return value


def seconds(a, b):
    if a is None or b is None:
        return None
    return round((s.stamp(b) - s.stamp(a)).total_seconds(), 3)


def analyze(results):
    by_slot = {}
    for r in results:
        s.need(r["slot"] not in by_slot, "DUPLICATE_SLOT_RESULT")
        by_slot[r["slot"]] = r
    order = sorted(s.SLOTS, key=lambda k: s.SLOTS[k])
    eligible_hashes = {r["eligible_set_sha256"] for r in results}
    request_hashes = {r["request_sha256"] for r in results}
    rows, gaps, regressions = [], [], []
    first_pass = last_fail_before = None
    previous = None
    for slot in order:
        r = by_slot.get(slot)
        if r is None:
            gaps.append({"slot": slot, "reason": "NO_RESULT"})
            rows.append({"slot": slot, "scheduled_at": s.SLOTS[slot], "status": "MISSING"})
            continue
        row = {"slot": slot, "scheduled_at": s.SLOTS[slot], "status": r["status"], "code": r["code"], "pass": r["pass"],
               "present": (r["counts"] or {}).get("present_eligible_symbols") if r["status"] in OBSERVED else None,
               "eligible": (r["counts"] or {}).get("eligible_symbols") if r["status"] in OBSERVED else None,
               "required_minimum": (r["counts"] or {}).get("required_minimum") if r["status"] in OBSERVED else None,
               "start_lateness_seconds": seconds(r["scheduled_at"], r["started_at"]),
               "fetch_seconds": seconds(r["fetch_started_at"], r["received_at"]),
               "received_at": r["received_at"], "http_status": r["http_status"], "body_sha256": r["body_sha256"]}
        rows.append(row)
        if r["status"] not in OBSERVED:
            gaps.append({"slot": slot, "reason": "HOLD", "code": r["code"]})
            continue
        if first_pass is None:
            if r["pass"]:
                first_pass = row
            else:
                last_fail_before = row
        if previous is not None:
            if previous["pass"] and not r["pass"]:
                regressions.append({"from": previous["slot"], "to": slot, "kind": "PASS_TO_FAIL"})
            if row["present"] < previous["present"]:
                regressions.append({"from": previous["slot"], "to": slot, "kind": "PRESENT_DECREASED",
                                    "delta": row["present"] - previous["present"]})
        previous = row
    return {"schema": "F2_SERIES_ANALYSIS_V1", "slots": rows,
            "first_pass": None if first_pass is None else {k: first_pass[k] for k in ("slot", "scheduled_at", "received_at", "present", "required_minimum")},
            "last_fail_before_first_pass": None if last_fail_before is None else
                {k: last_fail_before[k] for k in ("slot", "scheduled_at", "received_at", "present", "required_minimum")},
            "gaps": gaps, "regressions": regressions,
            "eligible_set_consistent": len(eligible_hashes) <= 1, "request_consistent": len(request_hashes) <= 1,
            "observed_slots": sum(1 for r in results if r["status"] in OBSERVED),
            "readiness_or_GO_granted": False}


def main(paths):
    results = [load(Path(p).read_bytes()) for p in paths]
    print(json.dumps(analyze(results), sort_keys=True, indent=1))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except s.Hold as e:
        print(json.dumps({"schema": "F2_SERIES_ANALYSIS_HOLD_V1", "code": s.safe_code(e)}))
        raise SystemExit(2)
