"""Fable diagnostic: what does the second OuterLimiter.run return on Linux after a consumed attempt?"""
import json, os, sys, threading, time, traceback
from dataclasses import replace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unittest
import test_outer_delta as t
c, o = t.c, t.o
out = []
for name in ("test_new_child_failure_consumed_no_effect", "test_new_fork_failure_consumed_no_callback", "test_new_changed_source_pin_consumed_before_fork"):
    case = t.TestOuterDelta(name); case.setUp()
    try:
        b, x = case.batch()
        if name == "test_new_child_failure_consumed_no_effect":
            b, _ = case.batch(x, replace(x.services, authority=lambda *a: os._exit(37)))
        if name == "test_new_changed_source_pin_consumed_before_fork":
            case.outer.core_sha256 = c.sha(b"OTHER_SOURCE")
            first = case.outer.run(b, "prove")
        elif name == "test_new_fork_failure_consumed_no_callback":
            from unittest.mock import patch
            with patch.object(o.os, "fork", side_effect=OSError("SYNTHETIC_FORK_FAILURE")):
                first = case.outer.run(b, "prove")
        else:
            first = case.outer.run(b, "prove")
        try:
            second = case.outer.run(b, "prove"); second_exc = None
        except Exception as e:
            second = None; second_exc = f"{type(e).__name__}: {e}"
        ledger = (case.root / "attempts.ledger").read_bytes().decode(errors="replace").splitlines()
        markers = sorted(p.name[:20] for p in case.root.iterdir() if p.name.startswith("consume-"))
        out.append({"test": name, "first": first, "second": second, "second_exc": second_exc,
                    "ledger_kinds": [json.loads(l).get("kind") for l in ledger if l.startswith("{")],
                    "markers": markers, "threads": threading.active_count()})
    except Exception:
        out.append({"test": name, "diag_error": traceback.format_exc()[-1500:]})
    finally:
        case.tearDown()
print(json.dumps(out, indent=1, default=str))
