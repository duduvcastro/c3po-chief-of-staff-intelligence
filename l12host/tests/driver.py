"""Subprocess driver for crash/kill and two-process contention fixtures (SYNTHETIC; tests only).

run   <lot_dir> <slot> <slot_at Z> [--crash-after-start]   one slot through rt.main (FIXTURE lot, fake probe)
claim <ledger_root> <pins.json> <tag> <count>               direct core claims on distinct scopes (R6 ledger race)
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit  # noqa: E402

rt = kit.rt


def run(lot_dir, slot, slot_at, crash_after_start):
    at = rt.stamp(slot_at)
    if crash_after_start:
        def crash(self):
            os._exit(9)
        rt.Shell.open_ledger = crash

    def factory(d):
        shell = rt.Shell(d, probe=kit.FakeProbe(), physical=False, slot_clock=lambda: at)
        shell.fam.fx.start_minute_violation = lambda t: None
        return shell
    out = []
    code = rt.main(["run", "--lot-dir", lot_dir, "--slot", slot], shell_factory=factory, emit=out.append)
    sys.stdout.write(out[0].decode("ascii") if out else "{}\n")
    return code


def claim(root, pins_path, tag, count):
    import finite_batch as fb
    pins = json.loads(Path(pins_path).read_text())
    native = (tuple((row[0], tuple(row[1])) for row in pins[0]), tuple(pins[1]))
    ledger = fb.DurableLedger(root, native, lock_budget_seconds=1.0, finish_budget_seconds=5)
    codes = []
    try:
        for i in range(count):
            scope = (fb.EPOCH, fb.DAY, fb.PREVIOUS, "RACE", "%s-%d" % (tag, i))
            permit = fb._TerminalPermit(os.urandom(32), "OUTER")
            try:
                ledger.claim(scope, "aa" * 32, "bb" * 32, None, worker_nonce_sha256=fb.sha(os.urandom(32)),
                             terminal_permit=permit)
                codes.append("CLAIMED")
            except fb.ReservationFailure as error:
                codes.append(fb.code(error))
    finally:
        ledger.close()
    sys.stdout.write(json.dumps(codes) + "\n")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "run":
        raise SystemExit(run(sys.argv[2], sys.argv[3], sys.argv[4], "--crash-after-start" in sys.argv))
    raise SystemExit(claim(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])))
