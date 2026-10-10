"""L12-HOST v3.1 Linux proof ONLY (CI runner, root, run by a REAL systemd timer): the slot command of the proof's
DOWN lot. It loads the INSTALLED runtime (<root>/src/l12host_runtime.py) with the measured interpreter, so the Shell
is PHYSICAL (physical_guard: installed copy, /usr/bin/python3.12, root, Linux) and runs the slot through rt.main
exactly as the production timer command does, with these substitutions and NOTHING else (each one needs Monday 12/10
state that cannot exist on a CI runner today; the suite covers them in-process, Codex reviews the real gates):

  1. rt.SESSION_OPEN_UTC = --open          (the physical pin of the signed gate scope's open is 2026-10-12T13:30:00Z)
  2. StepGates.capacity_chain -> accept    (M3 -> J -> CAPACITY_MONDAY originals complete on 12/10 only)
  3. StepGates.image_phase -> for BEFORE_FIRST_READER only the READY_NOT_THE_WAITED_ONE rule (the snapshot's ready
     bytes equal the waited ones), re-read from the signed ready path; the C6 snapshot needs the Monday image state
  4. l12host_extended.dependencies -> none (J needs the Codex J4 hot worker in its Monday window; post is not run)

REAL here: the timer, the slot service, the start marker, the claim, the session-leader worker and its watchdog, the
fresh double ALLOW + BEFORE_EFFECT, the ready-absent check before the xpre marker, the engine (pinned bytes) with its
veto / ready-absent / supervisor-alive / ready-present gates, systemd-run of both unit copies, the READY wait on the
signed epoch-04 path (the fake supervisor container writes ready.json after a delay), the hold observing both units,
the SESSION_START_V3 decode with a REAL-mode pinned (synthetic) verifier, the terminal and the RESULT file.

    /usr/bin/python3.12 -I -S -B <driver> --root <L12 root> --lot-dir <root>/lots/DOWN --slot <SLOT> --open <Z>
"""
import sys


def main(argv):
    if len(argv) != 8 or argv[0::2] != ["--root", "--lot-dir", "--slot", "--open"]:
        return 3
    args = dict(zip(argv[0::2], argv[1::2]))
    sys.path.insert(0, args["--root"] + "/src")
    import l12host_runtime as rt
    rt.SESSION_OPEN_UTC = args["--open"]

    def factory(lot_dir):
        shell = rt.Shell(lot_dir)
        ext = shell.fam.ext
        gates = ext.StepGates
        gates.capacity_chain = lambda self, task: "00" * 32

        def image_phase(self, phase, task, ready_sha256=None):
            if phase == "BEFORE_FIRST_READER":
                raw = rt.read_path(shell.authority["ready"]["ready_path"], 65536, rt.Hold)
                rt.need(rt.pin(ready_sha256) and rt.sha(raw) == ready_sha256, "READY_NOT_THE_WAITED_ONE")
        gates.image_phase = image_phase
        ext.dependencies = lambda s, step: None
        return shell
    return rt.main(["run", "--lot-dir", args["--lot-dir"], "--slot", args["--slot"]], shell_factory=factory)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
