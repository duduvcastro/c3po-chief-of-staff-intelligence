"""L12-HOST v3.3f Linux proof, CI ONLY (GitHub ubuntu-24.04 runner, root through sudo -n; refuses elsewhere).
Harmless by construction: no image, real container, network, credential, provider or SQL. What is REAL and what is
not is stated in the output (`real` / `fake` lists). It creates the epoch-04 host paths ON THE DISPOSABLE RUNNER only.

REAL: Linux procfs, root, /usr/bin/python3.12, systemd (systemd-run timers, transient slot services and units), the
installed runtime run by its timer, the installer's physical mode with the installed runtime's preview-stage /
preview / derived-check subprocesses, the R6 core/outer/runner, the extended executor (fork, setsid, lifeline
watchdog), the effect engine's gates, the runner04 bytes as signed file. FAKE: docker (a root-owned Python script:
`run` writes the signed receipt, or for the supervisor container writes ready.json after a delay and stays up, or
sleeps; `image inspect` echoes; everything else exits 9), the lots (REAL-mode but SYNTHETIC: synthetic decision,
plans, act B/GO pins and pinned synthetic verifiers), and the four Monday-only substitutions of the DOWN slot driver
(tests/proof_slot_driver.py: open constant, capacity chain, C6 phases, J/post dependencies).

1. B1: the real procfs boot_id (st_size 0) through the dedicated reader; the v2 generic reader refuses it.
2. W prepare (physical, root pinned to /var/lib/c3po-l12host-e04) of the WHOLE sealed family: its W seal must be
   sha256(l12host/SHA256SUMS) of the pushed tree (the seal Saturday's W signs); REAL measure twice (stable).
3. B2: a REAL-mode synthetic UP lot (the four core K9 operations + the components runner step, every K9 row with
   >= 30 s slack) installed in PHYSICAL mode; the timers fire and the INSTALLED runtime runs the slots as root:
   OuterLimiter -> BoundedRunner -> engine -> fake docker -> K9 adapter decode (REAL verifier binding) -> COMPLETE;
   then the extended runner step -> K9_EXT_STEP_V3 -> EXTENDED_COMPLETE.
4. B2: install-derived in physical mode reaches the derivation rule through the installed runtime.
5. The effect engine's own gates refuse with nothing started: the SUPERVISOR while a ready file exists
   (READY_PRESENT_AT_SUPERVISOR_START) or while a veto entry exists; the READER while its supervisor is not running.
6. A REAL-mode DOWN lot on the epoch-04 paths, PHYSICAL Shell, slots run by REAL systemd timers (slot services): R0
   (ready_check, read-only) COMPLETE; S1 (session_start) in ONE claim: ready absent -> xpre -> supervisor unit copy
   started by the engine from inside the timer-run slot service -> the fake supervisor writes ready.json after 8 s ->
   READY wait -> recheck -> supervisor alive -> fresh ALLOW -> the engine starts the reader only with the same
   ready.json present and the supervisor alive -> hold to open + 30 s observing both units -> SESSION_START_V3 decode
   -> EXTENDED_COMPLETE; both units: Restart=no, NRestarts=0, running, no OnFailure.

v3.2 (review of v3.1 and LINUX_DIAG_NOTE):
- H1: the engine refuses UNIT_HOLD_TOO_LONG (hold_until - now > 600 s) BEFORE its supervisor-alive gate, so the step-5
  READER negative now runs only once hold_until - now <= 540 s (it waits when the start-minute rules pushed R0 far),
  and records the margin it ran with. No false red whatever the start instant.
- L1 / LINUX_DIAG_NOTE: the timer instants are close to now: the UP core slots follow the F-E grid of the real UP lot
  (task window = [slot - 30 s, slot + budget], so a dependent starts one budget = 90 s later, not 155 s), the DOWN
  R0 is planned 90 s after the DOWN lot is built (was 240 s), and every slot's whole start window [at - 2 s, at + 60 s]
  (R0: through S1 + 120 s) passes the start-minute rules second by second. The timer-driven part over every start
  second of a day (evidence/PROOF_SCHEDULE_MODEL.json, assumed durations MODEL_SECONDS): min about 17, median about
  27, p90 about 44, max about 62 minutes (a start just before the 00:03:40-00:45:59 / 02:03:40-02:45:59 BRT blocks).
  Timestamped progress lines go to stderr; an exception still prints the JSON (check proof_ran_to_the_end).
- I1: `ready_was_waited_after_the_supervisor_start` now measures the wait (the READY observation and the ready file's
  mtime are >= 3 s after the supervisor's acknowledgement), instead of an order that held by construction.

v3.3 (v3.2 proof: S1 session_start UNIT_START_FAILED, reader unit not-found; root cause proven by the bisect, see
HOST MIRROR below): before any UP/DOWN work the runner mirrors the host's mount layout for the reader's
RequiresMountsFor paths (mnt.mount not-found, /mnt/day-d-data its own loaded/active fstab mount); the JSON records it
in `host_mirror` and the checks mnt_mount_not_found_like_host and day_d_data_mount_active_like_host keep the proof red
if either does not hold. On any failure the JSON carries bounded `failure_dumps` (systemctl show of both units and the
DOWN slot services, the epoch-04 unit files/units, the last 200 journal lines of the S1 slot service and both units).
The reviewed reader unit row does not change.

v3.3f (Codex D-NET, L2, K9 REAL files): the physical pins now apply to the proof's synthetic lots. The UP lot's K9
class networks are D-NET (PROVIDER bridge, DATABASE c3po_c3po_internal, DATABASE_AND_PROVIDER c3po_db_loopback) and
it signs SYNTHETIC REAL K9 files (lots/build_specs.synthetic_real_k9: a synthetic accepting ext/k9_verifiers04.py with
the R2 literal ABI, its registry, review, publication and 8 synthetic originals; the K9 callbacks are the verifier's
three functions); the DOWN unit copies take the reader / supervisor networks c3po_c3po_internal / c3po_db_loopback.
The fake docker ignores networks. Check `v33f_pins_signed_in_the_proof_lots` records what was signed.

Prints one JSON object; exit 1 if any check fails.
"""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tests"))
import kit                        # noqa: E402

rt, fx, inst, bind = kit.rt, kit.fx, kit.inst, kit.bind
sys.path.insert(0, str(HERE / "lots"))
import build_specs as bs          # noqa: E402  (v3.3f: synthetic REAL K9 files for the physical UP lot)
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "SYSTEMD_PAGER": "", "SYSTEMD_COLORS": "0"}
PY = "/usr/bin/python3.12"
READY_DELAY_SECONDS = 8
READY_WAIT_MIN_SECONDS = 3            # I1: READY observed >= 3 s after the supervisor ACK (expected about 5 s)

# ---------------------------------------------------------------------------------------------- v3.2 schedule
UP_LEAD_SECONDS = 240                 # the installer's plan_rows margin (180 s) + binding before it
UP_GAP_SECONDS = kit.CORE_K9_BUDGET   # 90: F-E grid, a dependent starts at the dependency's window end
TASK_LEAD_SECONDS = 30                # task not_before = slot - 30 s (as the real UP lot)
SLOT_SPAN = (-rt.EARLY_SECONDS, rt.LATE_SECONDS)       # every second a slot may start in passes the minute rules
DOWN_LEAD_SECONDS = 90                # DOWN bind + verdict + copy + engine negatives + timers, before R0
DOWN_SPAN = (-rt.EARLY_SECONDS, 180)  # R0's start window, S1 (R0 + 60 s) and the session start's gates (S1 + 120 s)
S1_AFTER_R0 = 60
S1_TO_STEP_NOT_BEFORE = 32            # the session-start step opens at S1 - 32 s (the 13:28:30Z analog of open - 90 s)
HOLD_AFTER_OPEN = 30                  # hold_until = open + 30 s (13:30:30Z analog)
HOLD_CHECK_SECONDS = fx.MAX_HOLD_SECONDS - 60          # H1: the READER negative only when hold - now <= 540 s
TIMER_MIN_LEAD_SECONDS = 15           # the DOWN timers are installed at least this long before R0
# Durations assumed by the schedule model (evidence/PROOF_SCHEDULE_MODEL.json); the proof itself measures real time.
MODEL_SECONDS = {"prepare": 60, "x1_done": 30, "down_build": 60, "bind": 20, "negatives": 20, "s1_finish": 25,
                 "cleanup": 20}

FAKE_DOCKER = kit.FAKE_COMMON + r'''
log("docker", argv)
if argv[:2] == ["image", "inspect"]:
    print(argv[-1])
    sys.exit(0)
if argv and argv[0] == "run":
    name = argv[argv.index("--name") + 1]
    b = cfg.get(name, {})
    for w in b.get("delayed_writes", []):
        time.sleep(w["after"])
        tmp = w["path"] + ".tmp%d" % os.getpid()
        with open(tmp, "w") as f:
            f.write(w["content"])
        os.replace(tmp, w["path"])
    time.sleep(b.get("sleep", 0))
    for w in b.get("writes", []):
        with open(w["path"], "w") as f:
            f.write(w["content"].replace("@NOW@", now()))
    sys.exit(b.get("exit", 0))
sys.exit(9)
'''


# ------------------------------------------------------------------------------- pure schedule (tests import it)
def engine_bad(t):
    """The ENGINE's own start-minute rule at whole second t (epoch seconds)."""
    return fx.start_minute_violation(datetime.fromtimestamp(t, timezone.utc)) is not None


def next_clear(t, span, bad=engine_bad):
    """First whole second >= t such that EVERY second of [t + span[0], t + span[1]] passes the start-minute rules."""
    t = int(math.ceil(t))
    while True:
        last = None
        for k in range(span[0], span[1] + 1):
            if bad(t + k):
                last = k
        if last is None:
            return t
        t += last - span[0] + 1


def plan_up(now, bad=engine_bad):
    """P1..P4 and X1 (epoch seconds): P1 >= now + 240 s, each next one >= the previous + 90 s, all clear."""
    times = [next_clear(now + UP_LEAD_SECONDS, SLOT_SPAN, bad)]
    for _ in range(4):
        times.append(next_clear(times[-1] + UP_GAP_SECONDS, SLOT_SPAN, bad))
    return times


def plan_down(now, bad=engine_bad):
    """R0 >= now + 90 s with R0's window, S1 and the session start's gates clear; the session-start instants."""
    r0 = next_clear(now + DOWN_LEAD_SECONDS, DOWN_SPAN, bad)
    s1 = r0 + S1_AFTER_R0
    step_nb = s1 - S1_TO_STEP_NOT_BEFORE
    opening = step_nb + rt.SESSION_OPEN_LEAD_SECONDS
    return {"r0": r0, "s1": s1, "step_not_before": step_nb, "open": opening, "hold": opening + HOLD_AFTER_OPEN}


def reader_check_not_before(down):
    """H1: the engine answers UNIT_HOLD_TOO_LONG while hold_until - now > 600 s; the READER negative waits until
    hold_until - now <= 540 s (never later than R0 - 392 s, so it always ends long before R0)."""
    return down["hold"] - HOLD_CHECK_SECONDS


def model(now, bad=engine_bad, d=None):
    """The proof's timeline for a start at `now` (epoch seconds) with the assumed durations: slot instants, the READER
    negative's instant and margins, and the end of the timer-driven part."""
    d = dict(MODEL_SECONDS, **(d or {}))
    up = plan_up(now + d["prepare"], bad)
    built = up[-1] + d["x1_done"] + 2 + d["down_build"]
    down = plan_down(built, bad)
    check = max(built + d["bind"], reader_check_not_before(down))
    negatives_end = check + d["negatives"]
    return {"up": up, "down": down, "reader_check_at": check, "hold_minus_check": down["hold"] - check,
            "r0_minus_negatives_end": down["r0"] - negatives_end, "end": down["hold"] + d["s1_finish"] + 2 + d["cleanup"]}


def utc(t):
    return datetime.fromtimestamp(t, timezone.utc)


def progress(message):
    """One timestamped line on stderr per phase (the workflow keeps it even if the step is stopped by its timeout)."""
    sys.stderr.write("[%s] %s\n" % (rt.iso(datetime.now(timezone.utc)), message))
    sys.stderr.flush()


# ------------------------------------------------------------------------------------------------------ helpers
def sh(argv, timeout=60):
    p = subprocess.run(argv, capture_output=True, timeout=timeout, env=ENV)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def show(unit, props):
    _, out, _ = sh(["/usr/bin/systemctl", "show", unit, "--no-pager", "-p", ",".join(props)])
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def mkdir(path, mode=0o700):
    Path(path).mkdir(mode=mode, parents=True, exist_ok=True)
    os.chmod(path, mode)
    return Path(path)


def write_private(path, raw, mode=0o600):
    Path(path).write_bytes(raw)
    os.chmod(path, mode)


def wait_results(layout, lot, slots, deadline):
    results = {}
    while time.monotonic() < deadline and len(results) < len(slots):
        for slot in slots:
            path = Path(layout["root"]) / "results" / ("%s.%s.json" % (lot, slot))
            if slot not in results and path.exists():
                try:
                    doc = json.loads(path.read_bytes())
                except ValueError:                         # created, not yet written (O_EXCL then write): next poll
                    continue
                results[slot] = {"status": doc.get("status"), "code": doc.get("code"),
                                 "result_class": doc.get("result_class"), "effect_calls": doc.get("effect_calls"),
                                 "diagnostics": doc.get("diagnostics"), "scheduled_at": doc.get("scheduled_at"),
                                 "started_at": doc.get("started_at"), "completed_at": doc.get("completed_at")}
        time.sleep(2)
    return results


def install_lot_dir(layout, lot, out_dir):
    """Copy a bound lot (stage dir) into <root>/lots/<LOT> exactly as the installer's first write does (0700 dirs,
    0400 files). Used for the DOWN proof lot, whose physical validation needs the proof's open substitution."""
    lot_dir = rt.child(layout, "lots") + "/" + lot
    inst.mkdir_private(lot_dir)
    for name in rt.LOT_FILES:
        inst.write_new(lot_dir + "/" + name, (Path(out_dir) / name).read_bytes(), 0o400)
    authority = json.loads((Path(out_dir) / "authority.json").read_bytes())
    for rel in sorted(authority["files"]):
        sub = lot_dir + "/" + rel.split("/")[0]
        if not os.path.lexists(sub):
            inst.mkdir_private(sub)
        inst.write_new(lot_dir + "/" + rel, (Path(out_dir) / rel).read_bytes(), 0o400)
    for sub in sorted({rel.split("/")[0] for rel in authority["files"]}):
        inst.fsync_dir(lot_dir + "/" + sub)
    inst.fsync_dir(lot_dir)
    return lot_dir


# ------------------------------------------------------------------------------------------ v3.3 HOST MIRROR
# Why (evidence fable-s1-bisect-20261010: bisect.sh 8b97db28d55e67c6..., env.txt 2eff33df5f2d864b..., results.txt
# 857b1332dfa1d80d..., s1bisect.yml d365271d71190724...): on ubuntu-24.04 / systemd 255.4 the reader's exact transient
# unit properties, run by systemd-run, answered rc=1 "A dependency job for <unit>.service failed" and the unit ended
# LoadState=not-found whenever RequiresMountsFor included /mnt/day-d-data (RequiresMountsFor=/mnt/day-d-data alone
# reproduced it); without that path it ran, and ExecCondition (1 or 3 lines, or ExecConditionEx) was no factor. On the
# runner /mnt has an fstab-generated mnt.mount (Azure resource disk) in ActiveState=failed and /mnt/day-d-data is a
# plain directory on /, so RequiresMountsFor pulls Requires=mnt.mount and its failed start fails the dependency job.
# The real host (read-only check 10/10/2026 09:34 BRT, systemd 255.4): /mnt/day-d-data is its own ext4 mount (fstab
# 'defaults,nofail'), mnt-day\x2dd\x2ddata.mount loaded/active/mounted, mnt.mount LoadState=not-found. The production
# reader unit is not affected; the harness now mirrors the host instead of changing the reviewed reader row:
#   - mnt.mount loaded and not active -> its /mnt line leaves /etc/fstab of this DISPOSABLE runner and a daemon-reload
#     (+ reset-failed) makes it not-found, exactly like the host (stop/mask would not do: Requires= on a masked unit
#     fails too). An ACTIVE mnt.mount is left as is and the check fails (the proof must not unmount a live disk).
#   - /mnt/day-d-data becomes its own fstab mount (a 64 MiB tmpfs, 'defaults,nofail', root 0755): its generated
#     mnt-day\x2dd\x2ddata.mount is loaded/active/mounted as on the host (tmpfs, not ext4: the dependency semantics
#     RequiresMountsFor sees are the same: a loaded, active, fstab-generated mount unit).
FSTAB = "/etc/fstab"
MNT_UNIT = "mnt.mount"
DAY_D_DATA_UNIT = "mnt-day\\x2dd\\x2ddata.mount"          # systemd-escape -p --suffix=mount /mnt/day-d-data
DAY_D_DATA_FSTAB_LINE = "tmpfs %s tmpfs defaults,nofail,size=64m,mode=0755,uid=0,gid=0 0 0" % rt.DAY_D_DATA
MOUNT_PROPS = ("Id", "LoadState", "ActiveState", "SubState", "Result", "FragmentPath", "SourcePath", "What", "Where",
               "Type", "Options")
BISECT_EVIDENCE = {"dir": "fable-s1-bisect-20261010",
                   "bisect.sh": "8b97db28d55e67c6ba2a2b66b85314316bb6b0cfbca2bc2812dab4327f660d87",
                   "env.txt": "2eff33df5f2d864bbd37c574c1d161a143465c9fbb11c7494fc436605fd5d0f9",
                   "results.txt": "857b1332dfa1d80d8769a3baf922b39f7df0037f81c96bcdd82fc2d72d00f723",
                   "s1bisect.yml": "d365271d71190724c23122e95a082c62fa1003815a4c7eba5c951a1d00fec0f1"}


def printable(text, limit=300):
    return "".join(c if " " <= c <= "~" else "?" for c in text[:limit])


def fstab_without(text, where):
    """(new fstab text, removed lines): every non-comment line whose mount point (2nd field) is exactly `where`."""
    kept, removed = [], []
    for line in text.splitlines(True):
        fields = line.split()
        if len(fields) >= 2 and not fields[0].startswith("#") and fields[1] == where:
            removed.append(line.rstrip("\n"))
        else:
            kept.append(line)
    return "".join(kept), removed


def fstab_has(text, where):
    return any(len(f) >= 2 and not f[0].startswith("#") and f[1] == where for f in (l.split() for l in text.splitlines()))


def findmnt(where, run=None):
    """findmnt of exactly `where` (not the file system containing it): {} when it is not a mount point."""
    rc, text, _ = (run or sh)(["/usr/bin/findmnt", "-J", "-o", "TARGET,SOURCE,FSTYPE,OPTIONS", "--mountpoint", where])
    rows = []
    if rc == 0:
        try:
            rows = json.loads(text).get("filesystems") or []
        except (ValueError, AttributeError):
            rows = []
    return {k: printable(str(v)) for k, v in rows[0].items()} if rows and type(rows[0]) is dict else {}


def mirror_checks(mirror):
    """The two host-mirror checks (pure; the tests call it)."""
    mnt, data, found = (mirror.get("mnt_mount") or {}), (mirror.get("day_d_data_mount") or {}), (mirror.get("findmnt") or {})
    return {"mnt_mount_not_found_like_host": mnt.get("LoadState") == "not-found",
            "day_d_data_mount_active_like_host": (data.get("Id") == DAY_D_DATA_UNIT and data.get("LoadState") == "loaded"
                                                  and data.get("ActiveState") == "active"
                                                  and data.get("SubState") == "mounted"
                                                  and found.get("target") == rt.DAY_D_DATA)}


def write_fstab(text):
    info = os.stat(FSTAB)
    tmp = FSTAB + ".l12proof-tmp"
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.chown(tmp, info.st_uid, info.st_gid)
    os.chmod(tmp, 0o644)
    os.replace(tmp, FSTAB)


def host_mirror():
    """Make THIS disposable runner's mount layout for the reader's RequiresMountsFor paths the host's (see above)."""
    rec = {"bisect_evidence": BISECT_EVIDENCE, "actions": []}
    rec["mnt_mount_before"] = show(MNT_UNIT, MOUNT_PROPS)
    rec["day_d_data_mount_before"] = show(DAY_D_DATA_UNIT, MOUNT_PROPS)
    raw = Path(FSTAB).read_bytes()
    rec["fstab_sha256_before"] = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", "replace")
    before = rec["mnt_mount_before"]
    if before.get("LoadState") == "loaded" and before.get("ActiveState") != "active":
        text, removed = fstab_without(text, "/mnt")
        rec["fstab_removed_lines"] = [printable(line) for line in removed]
        rec["actions"].append("FSTAB_MNT_LINE_REMOVED" if removed else "MNT_MOUNT_NOT_FROM_FSTAB")
    elif before.get("LoadState") == "loaded":
        rec["actions"].append("MNT_MOUNT_ACTIVE_LEFT_AS_IS")
    if not fstab_has(text, rt.DAY_D_DATA):
        text = text + ("" if text.endswith("\n") or not text else "\n") + DAY_D_DATA_FSTAB_LINE + "\n"
        rec["actions"].append("FSTAB_DAY_D_DATA_LINE_ADDED")
    if text.encode("utf-8") != raw:
        write_fstab(text)
    rec["fstab_sha256_after"] = hashlib.sha256(Path(FSTAB).read_bytes()).hexdigest()
    Path(rt.DAY_D_DATA).mkdir(mode=0o755, parents=True, exist_ok=True)
    rec["daemon_reload_rc"] = sh(["/usr/bin/systemctl", "daemon-reload"], timeout=90)[0]
    rec["reset_failed_mnt_rc"] = sh(["/usr/bin/systemctl", "reset-failed", MNT_UNIT])[0]
    rc, _, err = sh(["/usr/bin/systemctl", "start", DAY_D_DATA_UNIT], timeout=90)
    rec["start_day_d_data_rc"], rec["start_day_d_data_stderr"] = rc, printable(err)
    rec["escaped_unit_name"] = printable(sh(["/usr/bin/systemd-escape", "-p", "--suffix=mount", rt.DAY_D_DATA])[1].strip())
    rec["mnt_mount"] = show(MNT_UNIT, MOUNT_PROPS)
    rec["day_d_data_mount"] = show(DAY_D_DATA_UNIT, MOUNT_PROPS)
    rec["findmnt"] = findmnt(rt.DAY_D_DATA)
    return rec


# ------------------------------------------------------------------------------- v3.3 bounded failure dumps
DUMP_LINES = 200
DUMP_LINE_CHARS = 400
DUMP_SHOW_LINES = 400


def tail_lines(text, lines=DUMP_LINES, width=DUMP_LINE_CHARS):
    return [printable(row, width) for row in text.splitlines()[-lines:]]


def failure_dumps(layout, run=None):
    """On a failure: `systemctl show` of the supervisor and reader units and of the DOWN slot services, the epoch-04
    unit files and units, the last 200 journal lines of the S1 slot service and both units. Bounded (lines x chars),
    printable only; synthetic units only (no secret is ever in a unit property or this journal)."""
    run = run or sh
    units = (rt.SUPERVISOR_NAME, rt.READER_NAME)
    slots = {s: inst.unit_name(layout, "DOWN", s) for s in ("R0", "S1")}
    dumps = {"show": {}, "unit_files_e04": [], "units_e04": [], "journal": {}}
    for name in [u + ".service" for u in units] + [slots[s] + ".service" for s in ("R0", "S1")]:
        rc, text, _ = run(["/usr/bin/systemctl", "show", name, "--no-pager"])
        dumps["show"][name] = {"rc": rc, "lines": tail_lines(text, DUMP_SHOW_LINES)}
    for key, argv in (("unit_files_e04", ["/usr/bin/systemctl", "list-unit-files", "--no-pager", "--no-legend", "--all"]),
                      ("units_e04", ["/usr/bin/systemctl", "list-units", "--no-pager", "--no-legend", "--all"])):
        rc, text, _ = run(argv)                            # epoch-04 names: the *-e04 units and the slot units
        dumps[key] = [printable(row, DUMP_LINE_CHARS) for row in text.splitlines()
                      if "e04" in row or layout["unit_prefix"] in row][:DUMP_LINES]
    for name in [slots["S1"] + ".service"] + [u + ".service" for u in units]:
        rc, text, _ = run(["/usr/bin/journalctl", "--no-pager", "-o", "short-iso-precise", "-n", str(DUMP_LINES),
                           "-u", name])
        dumps["journal"][name] = {"rc": rc, "lines": tail_lines(text)}
    return dumps


CONTEXT = {}


def up_spec(env, times):
    """The REAL-mode synthetic UP lot on the F-E grid: core task k at times[k] with window [at - 30 s, at + 90 s] (the
    K9 decoder's phase window is the task window, as the bind rule requires); X1 at times[4]."""
    tasks, ops = [], []
    requires = {"prove": [], "collect": ["prove"], "commit_result": ["collect"], "publish_launch": ["commit_result"]}
    for i, core in enumerate(("prove", "collect", "commit_result", "publish_launch")):
        at = utc(times[i])
        nb, na = at - timedelta(seconds=TASK_LEAD_SECONDS), at + timedelta(seconds=kit.CORE_K9_BUDGET)
        op = kit.CORE_RUNNER[core]
        ops.append(op)
        env.k9_plan(op, at, kit.CORE_K9_BUDGET, core=core)
        row = env.k9_row(op, 25)
        dec = env.k9_decoder(op, row, nb=nb, na=na)
        dec["mode"] = "REAL"
        task = env.task(core, [("P%d" % (i + 1), at)], requires[core], row, dec, budget=kit.CORE_K9_BUDGET)
        task["not_before"], task["not_after"] = kit.z(nb), kit.z(na)
        tasks.append(task)
    step = env.ext_step("components", utc(times[4]), 90, 90 - kit.EXT_KILL_MARGIN)
    step["slots"] = [{"slot": "X1", "at": kit.z(utc(times[4]))}]
    ops.append("components_launch")
    spec = env.spec("UP", "UPSTREAM_P", tasks, files=env.k9_files(ops), extended={"steps": [step]}, k9=env.k9_section(ops))
    spec["mode"] = "REAL"
    spec["decision_sha256"] = kit.sha(b"SYNTHETIC_PROOF_DECISION_NOT_D1")
    return up_v33f(spec, env.assets), ops


def up_v33f(spec, assets):
    """v3.3f: the synthetic UP lot under the physical pins. D-NET class networks in the k9 section and every K9 row
    (the decoders' provenance follows the rows), then SYNTHETIC REAL K9 files bound to it (build_specs)."""
    spec["k9"]["networks"] = dict(rt.K9_NETWORKS_EPOCH04)
    for owner in list(spec["tasks"]) + list(spec["extended"]["steps"]):
        docker = owner["effect"]["docker"]
        op = docker["name"][len(rt.K9_CONTAINER_PREFIX):].replace("-", "_")
        cls = json.loads(Path(spec["files"]["k9/%s.json" % op]).read_bytes())["network_class"]
        docker["network"] = "none" if cls == "NONE" else rt.K9_NETWORKS_EPOCH04[cls]
        if owner["decoder"].get("kind") == "K9_STEP_V1":
            owner["decoder"]["provenance_binding_sha256"] = kit.sha(kit.canonical(owner["effect"]))
    real = Path(assets) / "k9-real-SYNTHETIC"
    real.mkdir(mode=0o700, exist_ok=True)
    return bs.synthetic_real_k9(spec, real, assets)


def main():
    assert sys.platform == "linux" and os.geteuid() == 0 and os.environ.get("GITHUB_ACTIONS") == "true", "CI_ONLY"
    assert not os.path.lexists(rt.EPOCH04_L12_ROOT), "EPOCH04_ROOT_ALREADY_PRESENT"
    os.umask(0o077)
    began, began_mono = time.time(), time.monotonic()
    CONTEXT.clear()
    out = {"schema": "L12HOST_V33F_LINUX_SYSTEMD_PROOF",
           "systemd_version": sh(["/usr/bin/systemctl", "--version"])[1].splitlines()[0],
           "real": ["procfs", "root", PY, "systemd timers/slot services/units", "installed runtime", "physical installer",
                    "physical DOWN Shell", "R6 core/outer/runner", "extended executor", "effect engine gates",
                    "runner04 bytes as signed file"],
           "fake": ["docker (root-owned python script)", "lots are REAL-mode SYNTHETIC",
                    "DOWN driver substitutions: open constant, capacity chain, C6 phases, J/post dependencies",
                    "host mirror: /mnt/day-d-data is a 64 MiB tmpfs fstab mount (host: ext4 fstab mount), the runner's "
                    "fstab /mnt line removed (host: no mnt.mount)"],
           "started_at": rt.iso(utc(began))}
    expected = model(began)
    out["model_expected"] = {"timer_part_end": rt.iso(utc(expected["end"])),
                             "timer_part_minutes": round((expected["end"] - began) / 60, 1),
                             "hold_minus_reader_check_seconds": expected["hold_minus_check"],
                             "r0_minus_negatives_end_seconds": expected["r0_minus_negatives_end"]}
    checks = {}
    progress("start; model: timer part ends about %s" % out["model_expected"]["timer_part_end"])
    try:
        body(out, checks)
        checks["proof_ran_to_the_end"] = True
    except Exception as error:                             # still print what was proven, then fail
        out["exception"] = "%s: %s" % (type(error).__name__, str(error)[:500])
        out["traceback_tail"] = traceback.format_exc()[-3000:]
        checks["proof_ran_to_the_end"] = False
        progress("EXCEPTION " + out["exception"])
    if not all(checks.values()) and "failure_dumps" not in out and CONTEXT.get("layout"):
        try:                                               # v3.3: bounded dumps on any failure (units still live)
            out["failure_dumps"] = failure_dumps(CONTEXT["layout"])
        except Exception as error:
            out["failure_dumps"] = {"error": "%s: %s" % (type(error).__name__, printable(str(error)))}
    out["elapsed_seconds"] = round(time.monotonic() - began_mono, 1)
    out["checks"] = checks
    out["ok"] = bool(checks) and all(checks.values())
    print(json.dumps(out, sort_keys=True))
    shutil.rmtree(rt.EPOCH04_VETO_DIR, ignore_errors=True)
    return 0 if out["ok"] else 1


def body(out, checks):
    # 0. v3.3: the host's mount layout for the reader's RequiresMountsFor paths, before any UP/DOWN work ----------
    try:
        out["host_mirror"] = host_mirror()
    except Exception as error:
        out["host_mirror"] = {"error": "%s: %s" % (type(error).__name__, printable(str(error)))}
    checks.update(mirror_checks(out["host_mirror"]))
    progress("host mirror: mnt.mount %s, %s %s/%s, findmnt %s" % (
        (out["host_mirror"].get("mnt_mount") or {}).get("LoadState"), DAY_D_DATA_UNIT,
        (out["host_mirror"].get("day_d_data_mount") or {}).get("LoadState"),
        (out["host_mirror"].get("day_d_data_mount") or {}).get("ActiveState"),
        (out["host_mirror"].get("findmnt") or {}).get("fstype")))

    # 1. B1 -------------------------------------------------------------------------------------------------------
    raw = rt.HostProbe().boot_id()
    st = os.stat(rt.BOOT_ID_PATH)
    try:
        rt.read_path(rt.BOOT_ID_PATH, 128)
        old = "ACCEPTED"
    except rt.Hold as error:
        old = str(error)
    out["b1"] = {"reported_st_size": st.st_size, "bytes": len(raw), "uuid": bool(rt.BOOT_ID_FORMAT.fullmatch(raw)),
                 "procfs": rt.proc_is_procfs(), "v2_generic_reader": old}
    checks["b1_boot_id_dedicated_reader"] = (out["b1"]["uuid"] and out["b1"]["procfs"] and len(raw) == 37
                                             and old in ("INPUT_FILE_CHANGED", "INPUT_FILE_EMPTY"))

    # 2. layout, fake docker, W prepare of the WHOLE family, measure ---------------------------------------------
    stamp = datetime.now(timezone.utc).strftime("%H%M%S")
    base = mkdir("/var/lib/l12proof-" + stamp)
    bindir = mkdir("/usr/local/lib/l12proof-" + stamp, 0o755)
    docker = bindir / "docker"
    docker.write_text("#!" + PY + " -I\n" + FAKE_DOCKER)
    os.chmod(docker, 0o755)
    (bindir / "fake.json").write_text("{}")
    veto = mkdir(rt.EPOCH04_VETO_DIR)
    dockercfg = mkdir(base / "docker-cli")
    for path in (rt.EPOCH04_K9_TOOLS, rt.EPOCH04_K9_DAY + "/plans", rt.EPOCH04_K9_DAY + "/receipts",
                 rt.EPOCH04_K9_ROOT + "/secrets/emitter"):
        mkdir(path)
    for p in ("/var/lib/c3po", rt.EPOCH04_K9_ROOT, rt.EPOCH04_K9_ROOT + "/days"):
        os.chmod(p, 0o700)
    secrets = Path(rt.EPOCH04_K9_ROOT + "/secrets")
    for leaf in ("provider.env", "risk-db.env"):
        write_private(secrets / leaf, b"C3PO_FIXTURE_ONLY=1\n")
    layout = {"schema": rt.LAYOUT_SCHEMA, "root": rt.EPOCH04_L12_ROOT, "veto_dir": str(veto), "unit_prefix": "l12proof-",
              "unit_name_suffix": "-e04", "python": PY,
              "binaries": {"docker": str(docker), "systemd_run": "/usr/bin/systemd-run", "systemctl": "/usr/bin/systemctl"},
              "docker_config": str(dockercfg)}
    rt.validate_layout(layout, rt.Hold)
    CONTEXT["layout"] = layout                             # v3.3: the unit names of the failure dumps
    stage = mkdir(base / "stage")
    fam = stage / "l12host"
    for name in kit.FAMILY_FILES:
        data = (kit.FAMILY / name).read_bytes()
        (fam / name).parent.mkdir(parents=True, exist_ok=True)
        (fam / name).write_bytes(data)
    (fam / "SHA256SUMS").write_bytes(kit.family_sums())
    layout_path = base / "layout.json"
    layout_path.write_bytes(rt.canonical(layout))
    env = kit.Env.__new__(kit.Env)
    now = datetime.now(timezone.utc)
    env.base, env.layout, env.layout_path, env.stage, env.bin = base, layout, layout_path, stage, bindir
    env.now0, env.t_sign = now, kit.past_signature_instant(now)
    env.nb, env.na = env.t_sign + timedelta(minutes=2), now + timedelta(hours=3)
    env.assets = mkdir(base / "assets")
    mkdir(env.assets / "k9")
    for p in kit.ASSETS.glob("*.py"):
        (env.assets / p.name).write_bytes(p.read_bytes())
    env.docs = mkdir(base / "docs")
    env.secrets, env.env_file = secrets, secrets / "provider.env"
    env.tools, env.daydir = Path(rt.EPOCH04_K9_TOOLS), Path(rt.EPOCH04_K9_DAY)
    env.receipts = env.daydir / "receipts"
    (env.tools / ("k9_runner04-%s.py" % kit.RUNNER_SHA)).write_bytes(kit.RUNNER_RAW)
    env.k9_request = env.assets / "k9" / "K9_04_STEP_SET_REQUEST.json"
    env.k9_request.write_bytes(kit.canonical({"schema": "K9_04_STEP_SET_REQUEST_V1", "synthetic": True,
                                              "image": {"id": kit.IMAGE, "revision": kit.LIT["REVISION"],
                                                        "package_sha256": kit.LIT["PACKAGE"]}}))
    env.k9_go = env.assets / "k9" / "K9_GO_04.json"
    env.k9_go.write_bytes(kit.canonical({"schema": "K9_04_SYNTHETIC_GO_NOT_AN_AUTHORIZATION"}))
    t_sign = env.t_sign
    bind.w_request(str(fam), str(layout_path), kit.z(t_sign - timedelta(minutes=40)), kit.z(t_sign + timedelta(minutes=30)),
                   str(stage))
    bind.owner(str(stage), kit.z(t_sign - timedelta(minutes=2)), kit.z(t_sign - timedelta(minutes=1)), w=True)
    prepared = inst.prepare(str(stage), require_root=True, physical=True)
    delivered = kit.FAMILY / "SHA256SUMS"
    out["w_seal"] = {"prepared": prepared["seal_sha256"],
                     "delivered_family_seal": hashlib.sha256(delivered.read_bytes()).hexdigest() if delivered.exists() else None}
    checks["w_seal_is_the_delivered_family_seal"] = out["w_seal"]["prepared"] == out["w_seal"]["delivered_family_seal"]
    m1 = inst.measure(str(layout_path))
    time.sleep(1)
    m2 = inst.measure(str(layout_path))
    out["measure"] = {"platform": m1["platform"], "executor_uid": m1["executor_uid"], "execution_mode": m1["execution_mode"],
                      "boot_id_sha256_pinned": rt.pin(m1["boot_id_sha256"]), "stable": rt.runtime_equal(m1, m2)}
    env.runtime_path = base / "runtime.json"
    env.runtime_path.write_bytes(rt.canonical(m1))
    checks["w_prepare_no_timer"] = prepared["status"] == "PREPARED_NO_TIMER" and prepared["timers"] == 0
    checks["real_measure_stable"] = (m1["platform"] == "linux" and m1["executor_uid"] == 0
                                     and m1["execution_mode"] == "FD_EXEC_LINUX" and out["measure"]["stable"])

    # 3. B2: REAL-mode synthetic UP lot (F-E grid), physical install, timers fire --------------------------------
    times = plan_up(time.time())
    progress("UP planned: " + " ".join(rt.iso(utc(t)) for t in times))
    spec, ops = up_spec(env, times)
    cfg = {}
    for op in ops:
        cfg[rt.K9_CONTAINER_PREFIX + op.replace("_", "-")] = {
            "writes": [{"path": str(env.receipts / (op + ".RECEIPT.json")), "content": env.k9_receipt_content(op)}]}
    cfg[rt.READER_NAME] = {"sleep": 900}
    cfg[rt.SUPERVISOR_NAME] = {"sleep": 900, "delayed_writes": [
        {"after": READY_DELAY_SECONDS, "path": rt.EPOCH04_READY_PATH,
         "content": kit.canonical({"epoch": kit.EPOCH, "session": kit.DAY}).decode("ascii")}]}
    (bindir / "fake.json").write_text(json.dumps(cfg))
    bound = env.signed_lot(spec)
    installed = inst.install(str(stage), "UP", bound, require_root=True, physical=True)
    out["install"] = {"code": installed.get("code"), "preview_stage": installed.get("preview_stage"),
                      "preview": installed.get("preview"), "detail": installed.get("detail"),
                      "timers": [{"slot": r["slot"], "installed": r["installed"]} for r in installed.get("timers", [])]}
    checks["physical_install_previews_and_timers"] = (installed.get("code") is None and installed.get("preview_stage") == "PASS"
                                                      and installed.get("preview") == "PASS"
                                                      and [r["installed"] for r in installed.get("timers", [])] == [True] * 5)
    unit = inst.unit_name(layout, "UP", "P1")
    out["timer"] = show(unit + ".timer", ["LoadState", "ActiveState", "AccuracyUSec", "Persistent", "RandomizedDelayUSec"])
    out["service_before"] = show(unit + ".service", ["LoadState", "Type", "Restart", "TimeoutStartUSec", "KillMode"])
    checks["timer_accuracy_1s_not_persistent"] = (out["timer"].get("AccuracyUSec") == "1s"
                                                  and out["timer"].get("Persistent") == "no")
    checks["slot_service_oneshot_no_restart"] = (out["service_before"].get("Type") == "oneshot"
                                                 and out["service_before"].get("Restart") == "no")
    progress("UP installed (%s); waiting for P1..X1" % (installed.get("code") or "no refusal"))
    deadline = time.monotonic() + (times[4] - time.time()) + 90 + 60      # X1 ceiling 90 s + polling margin
    results = wait_results(layout, "UP", ("P1", "P2", "P3", "P4", "X1"), deadline)
    out["slots"] = results
    progress("UP results: " + " ".join("%s=%s" % (k, v.get("status")) for k, v in sorted(results.items())))
    checks["installed_runtime_ran_core_slots_complete"] = all(
        results.get(s, {}).get("status") == "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE" for s in ("P1", "P2", "P3", "P4"))
    checks["installed_runtime_ran_extended_step_complete"] = results.get("X1", {}).get("status") == "EXTENDED_COMPLETE"

    # 4. B2: install-derived reaches the derivation rule through the installed runtime ---------------------------
    derived = base / "derived.json"
    derived.write_bytes(kit.canonical({"synthetic": "J4_REGISTRY_NOT_REAL"}))
    try:
        inst.install_derived(str(layout_path), "UP", str(derived), require_root=True)
        out["install_derived"] = "ACCEPTED"
    except rt.Hold as error:
        out["install_derived"] = str(error)
    checks["install_derived_physical_route_reaches_rule"] = out["install_derived"] == "PREVIEW_REFUSED_J4_SECTION_ABSENT"

    # 6a. DOWN: epoch-04 host paths on this runner, unit copies, the REAL-mode lot ---------------------------------
    mnt = os.lstat("/mnt")                                 # safe_ancestors: never group/other-writable (runner disk)
    if mnt.st_mode & 0o022:
        os.chmod("/mnt", mnt.st_mode & 0o7755)
    out["mnt_mode_before"] = oct(mnt.st_mode & 0o7777)
    for path, mode in (("/mnt/day-d-data", 0o755), ("/var/lib/c3po-bar", 0o755), (rt.EPOCH04_JOURNAL_ROOT, 0o700),
                       (str(Path(rt.EPOCH04_READY_PATH).parent), 0o700), (rt.EPOCH04_SUPERVISOR_STATE, 0o700),
                       (rt.EPOCH04_CAPACITY_ROOT, 0o700), (rt.EPOCH04_CAPACITY_ROOT + "/config", 0o700),
                       (rt.EPOCH04_READER_CONFIG, 0o700), (rt.EPOCH04_READER_LAUNCHER, 0o700),
                       (rt.EPOCH04_SUPERVISOR_CONFIG, 0o700)):
        mkdir(path, mode)
    for leaf in rt.READER_ENV_LEAVES:
        write_private(Path(rt.EPOCH04_READER_CONFIG) / leaf, b"C3PO_FIXTURE_ONLY=1\n")
    reader, sup, derivation = proof_unit_rows(layout, docker, dockercfg)
    out["unit_derivation"] = derivation
    checks["unit_derivation_reported"] = (derivation["reader"]["changed"] == [["Restart", "on-failure", "no"]]
                                          and derivation["supervisor"]["changed"] == [["Restart", "on-failure", "no"]]
                                          and "OnFailure" in derivation["reader"]["dropped"])
    up_dir = Path(rt.child(layout, "lots")) / "UP"
    up_req, up_bound = kit.sha((up_dir / "request.json").read_bytes()), kit.sha((up_dir / "bound.json").read_bytes())
    initial = {role: json.loads((Path(layout["root"]) / "receipts" / (env.key(role) + ".json")).read_bytes())["original_sha256"]
               for role in ("commit_result", "publish_launch")}
    down_plan = plan_down(time.time())
    out["schedule"] = {"up": [rt.iso(utc(t)) for t in times],
                       "down": {k: rt.iso(utc(v)) for k, v in down_plan.items()}}
    progress("DOWN planned: R0 %s S1 %s hold %s" % (out["schedule"]["down"]["r0"], out["schedule"]["down"]["s1"],
                                                     out["schedule"]["down"]["hold"]))
    down, opening, hold = proof_down_spec(env, reader, sup, t_sign, up_req, up_bound, initial, down_plan)
    down_out = stage / "lot-DOWN"
    spec_path = base / "spec-DOWN.json"
    spec_path.write_text(json.dumps(down))
    bind.lot(str(spec_path), str(layout_path), str(env.runtime_path), kit.z(t_sign - timedelta(minutes=30)), str(down_out))
    bind.owner(str(down_out), kit.z(t_sign - timedelta(minutes=1)), kit.z(t_sign))
    bind.bound(str(down_out), kit.z(t_sign + timedelta(seconds=30)))
    out["down_physical_without_substitution"] = physical_verdict(down_out)
    checks["down_physical_refuses_a_non_monday_open"] = out["down_physical_without_substitution"] == "SESSION_OPEN_NOT_THE_MONDAY_ONE"
    out["v33f"] = v33f_pins(json.loads((up_dir / "authority.json").read_bytes()),
                            json.loads((down_out / "authority.json").read_bytes()), layout)
    checks["v33f_pins_signed_in_the_proof_lots"] = out["v33f"]["ok"]
    lot_dir = install_lot_dir(layout, "DOWN", down_out)
    main_tail(out, checks, env, layout, veto, bindir, down_out, lot_dir, opening, hold, down_plan)


def proof_unit_rows(layout, docker, dockercfg):
    """The reviewed reader / supervisor references copied for the epoch-04 paths (fake docker path, layout DOCKER_CONFIG)."""
    dc_rename = lambda cfg_dir: ("DOCKER_CONFIG=" + cfg_dir + "/docker-cli", "DOCKER_CONFIG=" + str(dockercfg))
    renames = lambda name, ref, cfg_dir: [(ref, name), ("/usr/bin/docker", str(docker)), ("-/usr/bin/docker", "-" + str(docker)),
                                          dc_rename(cfg_dir)]
    reader, r_dropped, r_changed = bind.unit_row(str(HERE / "reference" / "c3po-reader.service"), {
        "@HOST_DATA_ROOT@": rt.DAY_D_DATA, "@HOST_JOURNAL_ROOT@": rt.EPOCH04_JOURNAL_ROOT,
        "@HOST_CAPACITY_ROOT@": rt.EPOCH04_CAPACITY_ROOT, "@HOST_CONFIG_DIR@": rt.EPOCH04_READER_CONFIG,
        "@IMAGE_ID@": kit.IMAGE, "@NETWORK@": rt.READER_NETWORK_EPOCH04,                       # v3.3f: D-NET pins
        "@CONTAINER_JOURNAL_ROOT@": rt.CONTAINER_JOURNAL_ROOT},
        rt.READER_NAME, "SESSION_READER", layout, renames(rt.READER_NAME, "c3po-reader", rt.EPOCH04_READER_CONFIG))
    sup, s_dropped, s_changed = bind.unit_row(str(HERE / "reference" / "c3po-massive.service"), {
        "@HOST_JOURNAL_ROOT@": rt.EPOCH04_JOURNAL_ROOT, "@HOST_STATE_ROOT@": rt.EPOCH04_SUPERVISOR_STATE,
        "@HOST_CONFIG_DIR@": rt.EPOCH04_SUPERVISOR_CONFIG, "@IMAGE_ID@": kit.IMAGE, "@NETWORK@": rt.SUPERVISOR_NETWORK_EPOCH04,
        "@CONTAINER_JOURNAL_ROOT@": rt.CONTAINER_JOURNAL_ROOT},
        rt.SUPERVISOR_NAME, "SUPERVISOR", layout, renames(rt.SUPERVISOR_NAME, "c3po-massive", rt.EPOCH04_SUPERVISOR_CONFIG))
    return reader, sup, {"reader": {"dropped": r_dropped, "changed": r_changed},
                         "supervisor": {"dropped": s_dropped, "changed": s_changed}}


def v33f_pins(up, down, layout):
    """v3.3f: what the installed UP lot and the DOWN lot signed: the K9 class networks, the REAL K9 files and callbacks,
    the two unit networks (hashes and names only)."""
    step = [s for s in down["extended"]["steps"] if s["step"] == "session_start"][0]
    units = {name: fx.parse_unit_docker(row["unit"]["exec"], layout["binaries"]["docker"])["network"]
             for name, row in (("reader", step["effect"]), ("supervisor", step["pre_effect"]))}
    callbacks = {n: up["external"].get(n) for n in rt.K9_REAL_CALLBACKS}
    record = {"up_k9_networks": up["k9"]["networks"], "down_unit_networks": units,
              "up_real_fixed_files": {rel: up["files"].get(rel) for rel in rt.K9_REAL_FIXED_FILES},
              "up_k9_callbacks": callbacks}
    record["ok"] = (up["k9"]["networks"] == rt.K9_NETWORKS_EPOCH04 and all(record["up_real_fixed_files"].values())
                    and callbacks == {n: {"file": rt.K9_REAL_VERIFIER, "identity": i} for n, i in rt.K9_REAL_CALLBACKS.items()}
                    and units == {"reader": rt.READER_NETWORK_EPOCH04, "supervisor": rt.SUPERVISOR_NETWORK_EPOCH04})
    return record


def physical_verdict(lot_out):
    """The DOWN proof lot through the PHYSICAL shell ABI without the proof's open substitution (expected refusal)."""
    fam = inst.family_core()
    try:
        rt.validate_authority(json.loads((Path(lot_out) / "authority.json").read_bytes()),
                              fam.fb.validate_plan((Path(lot_out) / "request.json").read_bytes()), fam, rt.Hold, physical=True)
        return "ACCEPTED"
    except rt.Hold as error:
        return str(error)


def proof_down_spec(env, reader, sup, t_sign, up_req, up_bound, initial, down_plan):
    """The REAL-mode synthetic DOWN lot of the proof on the epoch-04 paths: E6/J1/PO in the past (never fired), R0 and
    S1 in the future (fired by timers) at the instants of plan_down. Returns (spec, open, hold_until)."""
    e6_doc = env.docs / "e6.json"
    if not e6_doc.exists():
        write_private(e6_doc, kit.canonical({"synthetic_e6_document": 0}))
    rule = env.assets / "bounded_rule.json"
    rule.write_bytes(kit.canonical({"synthetic": "BOUNDED_READBACK_RULE_PLACEHOLDER"}))
    hot = (HERE / "vendor" / "j4_hot_worker.py")
    r0, s1 = utc(down_plan["r0"]), utc(down_plan["s1"])
    s_nb = utc(down_plan["step_not_before"])                # 13:28:30Z analog: open - 90 s
    opening = utc(down_plan["open"])                       # 13:30:00Z analog
    hold = utc(down_plan["hold"])                          # 13:30:30Z analog
    d_nb, d_na = t_sign + timedelta(minutes=2), datetime.now(timezone.utc) + timedelta(hours=3)
    e6_at = kit.allowed_after(t_sign + timedelta(minutes=10))
    j1_at = kit.allowed_after(e6_at, 151)
    po_at = kit.allowed_after(j1_at, 391)
    task = lambda op, slot, at, req, eff, dec, budget=60: {
        "operation": op, "not_before": kit.z(d_nb), "not_after": kit.z(d_na), "budget_seconds": budget, "requires": req,
        "slots": [{"slot": slot, "at": kit.z(at)}], "effect": eff, "decoder": dec, "image_go_sha256": None,
        "image_proposal_sha256": None}
    down_tasks = [
        task("e6", "E6", e6_at, ["commit_result", "publish_launch"],
             {"kind": "READBACK", "files": [{"path": str(e6_doc), "sha256": kit.sha(e6_doc.read_bytes()), "mode": 0o600,
                                             "uid": 0}]}, {"kind": "READBACK_V3"}),
        task("admission_manifest", "J1", j1_at, ["e6"],
             {"kind": "HOST_PROGRAM", "source": "ext/j4_hot_worker.py",
              "argv": ["--registry-record-base64", rt.J4_REGISTRY_TOKEN, "--mode", "REAL"]},
             {"kind": "HOT_J_V1", "verifier": "ok"}, budget=300),
        task("post", "PO", po_at, ["publish_launch"],
             {"kind": "CHAIN_READBACK", "source_lot": "UP", "source_request_sha256": up_req,
              "source_bound_sha256": up_bound, "steps": ["components"]}, {"kind": "CHAIN_READBACK_V3"})]
    gate = {"scope": {"build_sha": kit.LIT["REVISION"], "image_id": kit.IMAGE, "document_order_sha256": "70" * 32,
                      "release_sha256": "44" * 32, "package_sha256": kit.LIT["PACKAGE"], "calendar_pin_sha256": "c1" * 32,
                      "runtime_authority_sha256": "d1" * 32, "owner_uid": 0, "manifest_directory": str(env.docs),
                      "session_open": kit.z(opening), "not_before": kit.z(d_nb), "not_after": kit.z(d_na),
                      "view_opens_at": kit.z(d_nb), "require_go_mode": "INDIVIDUAL"},
            "journal_directory": rt.EPOCH04_JOURNAL_ROOT, "snapshot_reader": "ok", "snapshot_verifier": "ok",
            "readback": {"rule": "docs/bounded_rule.json", "rule_verifier": "ok", "readback_verifier": "ok"}}
    capacity = {"mode": "REAL", "lots": {"m3": "BOOT", "j": "DOWN", "activation": "CAP"},
                "sources": {"m3": "a1" * 32, "j": kit.sha(hot.read_bytes()), "activation": "a3" * 32},
                "verifiers": {"rule": "ok", "original": "ok", "config": "ok"},
                "config_path": rt.EPOCH04_CAPACITY_ROOT + "/config/capacity-final-2026-10-12.json"}
    ready = {"mode": "REAL", "calendar_sha256": "c1" * 32, "not_before": kit.z(s1 - timedelta(seconds=2)),
             "not_after": kit.z(s1 + timedelta(seconds=48)), "max_wait_seconds": 48, "poll_seconds": 0.25,
             "ready_path": rt.EPOCH04_READY_PATH, "verifiers": {"rule": "ok", "ready": "ok"}}
    extended = {"steps": [
        {"step": "ready_check", "not_before": kit.z(r0 - timedelta(seconds=30)), "not_after": kit.z(r0 + timedelta(seconds=120)),
         "ceiling_seconds": 60, "requires": [], "effect": None, "decoder": {"kind": "READY_ABSENT_V3"}, "pre_effect": None,
         "hold_until": None, "slots": [{"slot": "R0", "at": kit.z(r0)}]},
        {"step": "session_start", "not_before": kit.z(s_nb), "not_after": kit.z(s_nb + timedelta(seconds=480)),
         "ceiling_seconds": 420, "requires": [["core", "admission_manifest"], ["core", "post"]], "effect": reader,
         "decoder": {"kind": "SESSION_START_V3", "verifier": "ok"}, "pre_effect": sup, "hold_until": kit.z(hold),
         "slots": [{"slot": "S1", "at": kit.z(s1)}]}]}
    down = env.spec("DOWN", "DOWNSTREAM_AFTER_E6", down_tasks,
                    files={"ext/j4_hot_worker.py": str(hot), "docs/bounded_rule.json": str(rule)},
                    initial=initial, capacity=capacity, extended=extended, ready=ready, gate=gate,
                    imports={r: {"source_lot": "UP", "request_sha256": up_req, "bound_sha256": up_bound} for r in initial})
    down["mode"] = "REAL"
    down["decision_sha256"] = kit.sha(b"SYNTHETIC_PROOF_DECISION_NOT_D1")
    down["j4"] = {"protocol": "WARM_IMAGE10_ACTUAL_OBSERVATION", "hot_worker_source": "ext/j4_hot_worker.py",
                  "programs": {n: (rt.J4_HOT_WORKER_SHA256 if n == "hot_worker" else rt.FINITE_BATCH_SHA256
                                   if n == "finite_batch" else kit.sha(n.encode())) for n in rt.J4_PROGRAMS},
                  "originals": {n: kit.sha(("o-" + n).encode()) for n in set(rt.J4_ORIGINALS) - set(rt.J4_LOT_ORIGINALS)},
                  "bridge": {"bootstrap": "bootstrap", "authorize": "authorize", "general_read": "general_read",
                             "general_verify": "general_verify"},
                  "general_authority_sha256": "c1" * 32, "general_source_identity": "SYNTHETIC_GENERAL_SOURCE"}
    return down, opening, hold


def main_tail(out, checks, env, layout, veto, bindir, down_out, lot_dir, opening, hold, down_plan):
    # 5. the engine's own gates refuse with nothing started (before any DOWN timer exists) -----------------------
    installed_fx = (Path(rt.child(layout, "src")) / "l12host_effect.py").read_bytes()
    checks["engine_bytes_are_the_installed_ones"] = installed_fx == (HERE / "l12host_effect.py").read_bytes()
    a_sha, q_sha = kit.sha((down_out / "authority.json").read_bytes()), kit.sha((down_out / "request.json").read_bytes())
    key = env.xkey("session_start")

    def engine(kind, ready_sha=None, pid=None):
        until = kit.z(datetime.now(timezone.utc) + timedelta(seconds=10))
        return fx.run(fx.engine_argv(lot_dir, kind, "session_start", a_sha, q_sha, key, "d" * 64, until, ready_sha, pid))
    # H1: the engine checks hold_until - now <= 600 s BEFORE the supervisor-alive gate; wait (if the minute rules
    # pushed R0 far) until hold_until - now <= 540 s, so the READER negative reaches the gate under test.
    not_before = reader_check_not_before(down_plan)
    waited = max(0.0, not_before - time.time())
    if waited:
        progress("H1: waiting %.0f s so that hold_until - now <= %d s before the READER negative" % (waited, HOLD_CHECK_SECONDS))
    time.sleep(waited)
    ready_path = Path(rt.EPOCH04_READY_PATH)
    write_private(ready_path, kit.canonical({"epoch": kit.EPOCH, "session": kit.DAY}))
    negatives = {"supervisor_with_ready_present": engine("EXTENDED_PRE")[1]["code"]}
    ready_sha = kit.sha(ready_path.read_bytes())
    at_check = time.time()
    negatives["reader_without_running_supervisor"] = engine("EXTENDED", ready_sha, "4242")[1]["code"]
    ready_path.unlink()
    (veto / "STOP").write_text("x")
    negatives["supervisor_with_veto_present"] = engine("EXTENDED_PRE")[1]["code"]
    (veto / "STOP").unlink()
    out["engine_negatives"] = negatives
    out["reader_negative"] = {"waited_seconds": round(waited, 1),
                              "hold_minus_now_seconds": round(down_plan["hold"] - at_check, 1),
                              "r0_minus_now_seconds": round(down_plan["r0"] - time.time(), 1)}
    checks["reader_negative_inside_the_engine_hold_window"] = 0 < down_plan["hold"] - at_check <= HOLD_CHECK_SECONDS
    loaded = {u: show(u + ".service", ["LoadState"]).get("LoadState") for u in (rt.SUPERVISOR_NAME, rt.READER_NAME)}
    checks["engine_gates_refuse_with_nothing_started"] = (
        negatives == {"supervisor_with_ready_present": "READY_PRESENT_AT_SUPERVISOR_START",
                      "reader_without_running_supervisor": "SUPERVISOR_NOT_RUNNING_AT_READER_START",
                      "supervisor_with_veto_present": "VETO_PRESENT_BEFORE_EFFECT"}
        and set(loaded.values()) == {"not-found"})

    # 6b. DOWN slots R0 and S1 run by REAL timers through the physical driver ------------------------------------
    driver = bindir / "proof_slot_driver.py"
    driver.write_bytes((HERE / "tests" / "proof_slot_driver.py").read_bytes())
    os.chmod(driver, 0o500)
    authority = json.loads((down_out / "authority.json").read_bytes())
    timers = {}
    lead = down_plan["r0"] - time.time()
    out["down_timers_lead_seconds"] = round(lead, 1)
    for row in authority["slots"]:
        if row["slot"] not in ("R0", "S1"):
            continue
        argv = inst.slot_command(layout, "DOWN", row)
        argv = argv[:argv.index(PY)] + [PY, "-I", "-S", "-B", str(driver), "--root", layout["root"], "--lot-dir", lot_dir,
                                         "--slot", row["slot"], "--open", kit.z(opening)]
        timers[row["slot"]] = sh(argv)[0]
    checks["down_timers_installed_ahead_of_r0"] = timers == {"R0": 0, "S1": 0} and lead >= TIMER_MIN_LEAD_SECONDS
    progress("engine negatives %s; DOWN timers %s, %.0f s before R0" % (negatives, timers, lead))
    deadline = time.monotonic() + (hold - datetime.now(timezone.utc)).total_seconds() + 240
    down_results = wait_results(layout, "DOWN", ("R0", "S1"), deadline)
    out["down_slots"] = down_results
    progress("DOWN results: " + " ".join("%s=%s" % (k, v.get("status")) for k, v in sorted(down_results.items())))
    checks["timer_run_ready_check_complete"] = (down_results.get("R0", {}).get("status") == "EXTENDED_COMPLETE"
                                                and down_results["R0"].get("result_class") == "READY_ABSENT_OBSERVED")
    checks["timer_run_physical_session_start_complete"] = (
        down_results.get("S1", {}).get("status") == "EXTENDED_COMPLETE"
        and down_results["S1"].get("result_class") == "SESSION_START_FIRST_CYCLE_HELD"
        and down_results["S1"].get("effect_calls") == 2)
    session = {}
    try:
        envelope = json.loads((Path(layout["root"]) / "receipts" / (key + ".json")).read_bytes())
        record = json.loads(base64.b64decode(envelope["original_b64"]))
        sup_ack = json.loads(base64.b64decode(record["supervisor_ack_b64"]))
        rdr_ack = json.loads(base64.b64decode(record["reader_ack_b64"]))
        ack_at, ready_at = rt.stamp(sup_ack["observed_at"]), rt.stamp(record["ready_observed_at"])
        ready_mtime = datetime.fromtimestamp(os.stat(rt.EPOCH04_READY_PATH).st_mtime, timezone.utc)
        session = {"ready_observed_at": record["ready_observed_at"], "supervisor_ack_observed_at": sup_ack["observed_at"],
                   "ready_file_mtime": rt.iso(ready_mtime),
                   "ready_observed_after_ack_seconds": round((ready_at - ack_at).total_seconds(), 3),
                   "ready_written_after_ack_seconds": round((ready_mtime - ack_at).total_seconds(), 3),
                   "reader_held": rdr_ack["held"], "reader_polls": rdr_ack["polls"], "supervisor": rdr_ack["supervisor"],
                   "gates": record["gates"],
                   "xpre_marker": (Path(layout["root"]) / "extended" / ("xpre-" + key)).exists()}
        # I1 (v3.2): the READY wait really waited: the fake supervisor writes ready.json READY_DELAY_SECONDS after its
        # start, the engine acknowledges the unit about 3 s after the start, so the file appears and is observed
        # about 5 s after the ACK; a leftover or an unwaited READY would be observed within a poll of the ACK.
        checks["ready_was_waited_after_the_supervisor_start"] = (
            (ready_at - ack_at).total_seconds() >= READY_WAIT_MIN_SECONDS
            and (ready_mtime - ack_at).total_seconds() >= READY_WAIT_MIN_SECONDS - 1
            and ready_at >= ready_mtime)
        checks["reader_held_with_supervisor_alive"] = (rdr_ack["held"] is True and rdr_ack["polls"] >= 3
                                                       and rdr_ack["supervisor"]["running_through_hold"] is True
                                                       and rdr_ack["supervisor"]["main_pid"] == sup_ack["properties"]["MainPID"])
    except (OSError, ValueError, KeyError, rt.Hold) as error:
        session = {"error": type(error).__name__}
        checks["ready_was_waited_after_the_supervisor_start"] = False
        checks["reader_held_with_supervisor_alive"] = False
    out["session"] = session
    units = {}
    for name in (rt.SUPERVISOR_NAME, rt.READER_NAME):
        units[name] = show(name + ".service", ["LoadState", "ActiveState", "SubState", "Restart", "NRestarts", "KillMode",
                                               "OnFailure", "MainPID"])
    out["units"] = units
    checks["unit_copies_restart_no_running_once"] = all(
        fx.running_once(u) and u.get("Restart") == "no" and u.get("NRestarts") == "0"
        and u.get("KillMode") == "control-group" and not u.get("OnFailure") for u in units.values())
    # informational only (a transient oneshot may already be unloaded); the check is the RESULT written by the
    # timer-run slot command itself, started inside its slot window
    out["s1_slot_service"] = show(inst.unit_name(layout, "DOWN", "S1") + ".service",
                                  ["LoadState", "Type", "Restart", "Result", "ExecMainStatus"])
    try:
        doc = json.loads((Path(layout["root"]) / "results" / "DOWN.S1.json").read_bytes())
        lateness = (rt.stamp(doc["started_at"]) - rt.stamp(doc["scheduled_at"])).total_seconds()
        out["s1_started_after_its_instant_seconds"] = lateness
        checks["s1_ran_from_its_timer_in_its_slot_window"] = (-rt.EARLY_SECONDS <= lateness <= rt.LATE_SECONDS
                                                              and doc.get("start_marker") == "CREATED")
    except (OSError, ValueError, KeyError, rt.Hold):
        checks["s1_ran_from_its_timer_in_its_slot_window"] = False
    # v3.3 (informational): the reader copy's mount dependencies on this host-mirrored runner
    out.setdefault("host_mirror", {})["reader_dependencies"] = show(
        rt.READER_NAME + ".service", ["LoadState", "RequiresMountsFor", "Requires", "After"])
    # v3.3: bounded dumps while the units are still live (before the cleanup below), on any failure so far
    if not all(checks.values()):
        out["failure_dumps"] = failure_dumps(layout)

    # cleanup of everything this disposable runner got
    for name in (rt.READER_NAME, rt.SUPERVISOR_NAME):
        sh(["/usr/bin/systemctl", "stop", name + ".service"], timeout=90)
        sh(["/usr/bin/systemctl", "reset-failed", name + ".service"])
    for lot, slots in (("UP", ("P1", "P2", "P3", "P4", "X1")), ("DOWN", ("R0", "S1"))):
        for slot in slots:
            sh(["/usr/bin/systemctl", "stop", inst.unit_name(layout, lot, slot) + ".timer"])


if __name__ == "__main__":
    raise SystemExit(main())
