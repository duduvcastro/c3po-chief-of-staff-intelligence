"""F2 host installer, readback and revocation. Run on the host as root by Fable, after the
owner's Assino. No shell: every command is an argv list. No token is read here.

plan     --now <UTC>         print the systemd-run argv of the slots that would be installed (no effect)
install  --stage <dir> --bound-sha256 <hex>
                             verify staged bytes, create the two private roots, copy family/BOUND/eligible
                             set/age, then ONE transient timer per future slot (margin >= 180 s)
readback                     list the f2s-20261008-* timers and their properties (read-only)
revoke                       write REVOKED in the campaign root (runtime refuses), then stop every timer
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import series_runtime as s

SYSTEMD_RUN = "/usr/bin/systemd-run"
SYSTEMCTL = "/usr/bin/systemctl"
PYTHON = "/usr/bin/python3"
F1_AGE = "/var/lib/c3po/f1-diagnostic-20261008/age"
MARGIN_SECONDS = 180
FAMILY_DIR = "f2-series"
FAMILY_FILES = ("CONTRACT.md", "REFERENCE_PROVENANCE.json", "RUNBOOK.md", "SHA256SUMS", "bind_series.py",
                "install_series.py", "linux-proof.yml", "reference_extract.py", "series_analyze.py",
                "series_runtime.py", "test_linux_crypto.py", "test_series.py", "verify_family.py")


def calendar(slot):
    """systemd OnCalendar in explicit UTC, e.g. '2026-10-09 00:26:00 UTC'."""
    at = s.stamp(s.SLOTS[slot])
    return at.strftime("%Y-%m-%d %H:%M:%S") + " UTC"


def unit(slot):
    return s.UNIT_PREFIX + slot


def slot_command(slot):
    runtime = s.SOURCE_ROOT + "/" + FAMILY_DIR + "/series_runtime.py"
    return [SYSTEMD_RUN, "--unit=" + unit(slot), "--description=F2 series slot " + slot + " (BRT)",
            "--on-calendar=" + calendar(slot), "--timer-property=AccuracySec=1s",
            "--property=Type=oneshot", "--property=TimeoutStartSec=170", "--property=UMask=0077",
            "--property=NoNewPrivileges=yes", "--property=PrivateTmp=yes",
            PYTHON, "-I", "-S", "-B", runtime, "run", "--bound", s.SOURCE_ROOT + "/BOUND.json", "--slot", slot]


def plan(now):
    """Only future slots with at least MARGIN_SECONDS of margin, in time order."""
    rows = []
    for slot, at in sorted(s.SLOTS.items(), key=lambda x: x[1]):
        margin = (s.stamp(at) - now).total_seconds()
        if margin >= MARGIN_SECONDS:
            rows.append({"slot": slot, "utc": at, "brt": s.brt_label(slot), "margin_seconds": int(margin),
                         "argv": slot_command(slot)})
    return rows


def _sha_file(path):
    return s.sha(Path(path).read_bytes())


def install(stage, bound_sha256, now=None):
    s.need(sys.platform == "linux" and os.geteuid() == 0, "INSTALL_REQUIRES_LINUX_ROOT")
    stage = Path(stage)
    fam = stage / FAMILY_DIR
    import verify_family  # the staged copy is verified, not this file's directory
    verify_family.verify(fam)
    for name in FAMILY_FILES:
        s.need((fam / name).is_file() and not (fam / name).is_symlink(), "STAGE_FAMILY_INCOMPLETE")
    s.need(_sha_file(stage / "BOUND.json") == bound_sha256, "STAGE_BOUND_MISMATCH")
    bound = s.strict((stage / "BOUND.json").read_bytes())
    raws = {k: s.canonical(v) for k, v in bound["documents"].items()}
    q = s.validate_documents(raws)["request"]
    s.need(_sha_file(fam / "series_runtime.py") == q["source_sha256"], "STAGE_SOURCE_MISMATCH")
    s.need(_sha_file(fam / "SHA256SUMS") == q["seal_sha256"], "STAGE_SEAL_MISMATCH")
    eligible_raw = (stage / "ELIGIBLE_SET.json").read_bytes()
    s.validate_eligible(eligible_raw, q)
    s.need(_sha_file(F1_AGE) == s.AGE_SHA256, "F1_AGE_MISMATCH")
    s.need(not os.path.lexists(s.SOURCE_ROOT) and not os.path.lexists(s.CAMPAIGN_ROOT), "ROOTS_ALREADY_EXIST")
    os.umask(0o077)
    os.mkdir(s.SOURCE_ROOT, 0o700)
    os.mkdir(s.SOURCE_ROOT + "/" + FAMILY_DIR, 0o700)
    for name in FAMILY_FILES:
        shutil.copyfile(fam / name, s.SOURCE_ROOT + "/" + FAMILY_DIR + "/" + name)
        os.chmod(s.SOURCE_ROOT + "/" + FAMILY_DIR + "/" + name, 0o400)
    for name in ("BOUND.json", "ELIGIBLE_SET.json"):
        shutil.copyfile(stage / name, s.SOURCE_ROOT + "/" + name)
        os.chmod(s.SOURCE_ROOT + "/" + name, 0o400)
    os.mkdir(s.CAMPAIGN_ROOT, 0o700)
    shutil.copyfile(F1_AGE, s.CAMPAIGN_ROOT + "/age")
    os.chmod(s.CAMPAIGN_ROOT + "/age", 0o500)
    # Re-verify installed copies byte for byte.
    verify_family.verify(Path(s.SOURCE_ROOT + "/" + FAMILY_DIR))
    s.need(_sha_file(s.SOURCE_ROOT + "/BOUND.json") == bound_sha256 and
           _sha_file(s.SOURCE_ROOT + "/ELIGIBLE_SET.json") == q["eligible_set_sha256"] and
           _sha_file(s.CAMPAIGN_ROOT + "/age") == s.AGE_SHA256 and
           _sha_file(s.SOURCE_ROOT + "/" + FAMILY_DIR + "/series_runtime.py") == q["source_sha256"] and
           _sha_file(s.SOURCE_ROOT + "/" + FAMILY_DIR + "/SHA256SUMS") == q["seal_sha256"], "INSTALLED_COPY_MISMATCH")
    rows = plan(now or datetime.now(timezone.utc))
    out = []
    for row in rows:
        # Re-check margin immediately before each unit: never install a slot with < 180 s left.
        if (s.stamp(row["utc"]) - datetime.now(timezone.utc)).total_seconds() < MARGIN_SECONDS:
            out.append({"slot": row["slot"], "installed": False, "reason": "MARGIN_LOST"})
            continue
        proc = subprocess.run(row["argv"], stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                              env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        out.append({"slot": row["slot"], "utc": row["utc"], "unit": unit(row["slot"]), "installed": proc.returncode == 0,
                    "rc": proc.returncode})
    return {"schema": "F2_INSTALL_RESULT_V1", "bound_sha256": bound_sha256, "eligible_set_sha256": q["eligible_set_sha256"],
            "source_sha256": q["source_sha256"], "seal_sha256": q["seal_sha256"], "timers": out,
            "skipped_slots": sorted(set(s.SLOTS) - {r["slot"] for r in rows})}


def readback():
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "SYSTEMD_PAGER": "", "SYSTEMD_COLORS": "0"}
    listing = subprocess.run([SYSTEMCTL, "list-timers", "--all", "--no-pager", "--no-legend", s.UNIT_PREFIX + "*"],
                             capture_output=True, timeout=30, env=env)
    rows = []
    for slot in sorted(s.SLOTS, key=lambda k: s.SLOTS[k]):
        proc = subprocess.run([SYSTEMCTL, "show", unit(slot) + ".timer", "--no-pager",
                               "-p", "Id,LoadState,ActiveState,TimersCalendar,NextElapseUSecRealtime,LastTriggerUSec,"
                               "AccuracyUSec,Persistent,RandomizedDelayUSec,Unit"],
                              capture_output=True, timeout=30, env=env)
        svc = subprocess.run([SYSTEMCTL, "show", unit(slot) + ".service", "--no-pager",
                              "-p", "LoadState,ActiveState,Result,ExecMainStatus,Restart,TimeoutStartUSec"],
                             capture_output=True, timeout=30, env=env)
        rows.append({"slot": slot, "utc": s.SLOTS[slot], "timer": proc.stdout.decode("utf-8", "replace").splitlines(),
                     "service": svc.stdout.decode("utf-8", "replace").splitlines()})
    return {"schema": "F2_READBACK_V1", "list_timers": listing.stdout.decode("utf-8", "replace").splitlines(),
            "units": rows, "revoked_marker": os.path.lexists(s.CAMPAIGN_ROOT + "/" + s.REVOKED_NAME)}


def revoke(now=None):
    s.need(sys.platform == "linux" and os.geteuid() == 0, "REVOKE_REQUIRES_LINUX_ROOT")
    at = s.iso(now or datetime.now(timezone.utc))
    marker = "absent_root"
    if os.path.isdir(s.CAMPAIGN_ROOT) and not os.path.islink(s.CAMPAIGN_ROOT):
        try:
            fd = os.open(s.CAMPAIGN_ROOT + "/" + s.REVOKED_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.write(fd, s.canonical({"schema": "F2_REVOKED_V1", "revoked_at": at}) + b"\n")
            os.fsync(fd)
            os.close(fd)
            marker = "written"
        except FileExistsError:
            marker = "already_present"
    rows = []
    for slot in sorted(s.SLOTS, key=lambda k: s.SLOTS[k]):
        # Stops the timer only. A service already running finishes its single bounded GET (<= 120 s).
        proc = subprocess.run([SYSTEMCTL, "stop", unit(slot) + ".timer"], capture_output=True, timeout=30,
                              env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        rows.append({"slot": slot, "stop_rc": proc.returncode})
    return {"schema": "F2_REVOKE_RESULT_V1", "revoked_at": at, "marker": marker, "timers": rows}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("plan", "install", "readback", "revoke"))
    p.add_argument("--now")
    p.add_argument("--stage")
    p.add_argument("--bound-sha256")
    a = p.parse_args(argv)
    try:
        if a.command == "plan":
            result = {"schema": "F2_PLAN_V1", "slots": plan(s.stamp(a.now) if a.now else datetime.now(timezone.utc))}
        elif a.command == "install":
            s.need(a.stage and a.bound_sha256 and s.pin(a.bound_sha256), "INSTALL_ARGUMENTS_INVALID")
            result = install(a.stage, a.bound_sha256)
        elif a.command == "readback":
            result = readback()
        else:
            result = revoke()
    except BaseException as error:
        # A partial install (roots created, some timers) is reported, never cleaned up automatically.
        result = {"schema": "F2_INSTALL_HOLD_V1", "code": s.safe_code(error),
                  "source_root_exists": os.path.lexists(s.SOURCE_ROOT), "campaign_root_exists": os.path.lexists(s.CAMPAIGN_ROOT)}
    print(json.dumps(result, sort_keys=True, indent=1))
    return 2 if "code" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
