"""F2 host installer in two phases, measurement, readback and revocation. Run on the host as root
by Fable. No shell: every command is an argv list. The provider token file is opened only to check
that the key is present (value discarded, never printed, stored or passed on).

plan     --now <UTC>         print the systemd-run argv of the slots that would be installed (no effect)
prepare  --stage <dir>       phase A (authority: the owner's AUTORIZACAO_MEDICAO_F2_20261009, no BOUND):
                             guards first (staged seal, authorization gate, fixed ELIGIBLE_SET
                             hash, F1 age hash, token key presence, roots absent), then
                             SOURCE_ROOT 0700 (family + ELIGIBLE_SET 0400) and CAMPAIGN_ROOT 0700
                             (age 0500 + EMPTY ledger 0600 created O_EXCL). No timer.
measure                      read-only; prints the PRIVATE canonical measurement/runtime/election JSON
install  --stage <dir> --bound-sha256 <hex>
                             phase B (after the owner's Assino): copy ONLY BOUND.json (0400), re-measure,
                             require runtime+election equal to the signed pins, preview the runtime's
                             own guards, then ONE transient timer per future slot (margin >= 180 s and
                             owner record strictly before the slot). Any difference: zero timers, HOLD.
readback                     list the f2s-20261009-* timers and their properties (read-only)
revoke                       write REVOKED in the campaign root (runtime refuses), then stop every timer
"""
import argparse
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import series_runtime as s

SYSTEMD_RUN = "/usr/bin/systemd-run"
SYSTEMCTL = "/usr/bin/systemctl"
PYTHON = "/usr/bin/python3"
F1_AGE = "/var/lib/c3po/f1-diagnostic-20261008/age"
MARGIN_SECONDS = 180
FAMILY_DIR = s.FAMILY_DIR
FAMILY_FILES = ("CONTRACT.md", "REFERENCE_PROVENANCE.json", "RUNBOOK.md", "SHA256SUMS", "bind_series.py",
                "install_series.py", "linux-proof.yml", "reference_extract.py", "series_analyze.py",
                "series_runtime.py", "test_linux_crypto.py", "test_series.py", "verify_family.py")


def calendar(slot):
    """systemd OnCalendar in explicit UTC, e.g. '2026-10-09 22:26:00 UTC'."""
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
            "--property=WorkingDirectory=" + s.CAMPAIGN_ROOT, "--property=LimitCORE=0",
            PYTHON, "-I", "-S", "-B", runtime, "run", "--bound", s.SOURCE_ROOT + "/BOUND.json", "--slot", slot]


def plan(now, owner_recorded=None):
    """Only future slots with at least MARGIN_SECONDS of margin (and, when given, strictly after the
    owner's record), in time order."""
    rows = []
    for slot, at in sorted(s.SLOTS.items(), key=lambda x: x[1]):
        margin = (s.stamp(at) - now).total_seconds()
        if margin >= MARGIN_SECONDS and (owner_recorded is None or owner_recorded < s.stamp(at)):
            rows.append({"slot": slot, "utc": at, "brt": s.brt_label(slot), "margin_seconds": int(margin),
                         "argv": slot_command(slot)})
    return rows


def read_regular(path, limit):
    """No symlink, regular, nlink 1 (staging and F1 age)."""
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        s.need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit, "STAGE_FILE_INVALID")
        raw = b""
        while True:
            part = os.read(fd, 65536)
            if not part:
                break
            raw += part
            s.need(len(raw) <= limit, "STAGE_FILE_INVALID")
        return raw
    finally:
        os.close(fd)


def write_new(path, raw, mode):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, raw)
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)


def need_root(require_root, code):
    if require_root:
        s.need(sys.platform == "linux" and os.geteuid() == 0, code)


PREPARE_RECEIPT = "PREPARE_RECEIPT.json"
# Variant 09/10: the authority is the owner's own AUTORIZACAO_MEDICAO_F2_20261009 (not the A2 Emenda 7).
AMENDMENT_ORIGINAL = "AUTORIZACAO_MEDICAO_ORIGINAL.json"
AMENDMENT_DOCUMENT = "AUTORIZACAO_MEDICAO_F2_20261009.md"
LEAF_CONFIG = "config.json"


def amendment_gate(stage, seal_sha256, now):
    """The owner's authorization is the authority of phase A: its ORIGINAL Assino (opaque bytes), its
    document and the leaf config are staged and checked here, and the signature precedes the first effect."""
    config_raw = read_regular(stage / LEAF_CONFIG, 4096)
    config = s.strict(config_raw)
    s.need(set(config) == {"schema", "amendment7_sha256", "amendment7_signature_sha256"} and
           config["schema"] == "F2_LEAF_CONFIG_V1" and s.pin(config["amendment7_sha256"]) and
           s.pin(config["amendment7_signature_sha256"]), "LEAF_CONFIG_INVALID")
    document = read_regular(stage / AMENDMENT_DOCUMENT, 65536)
    s.need(s.sha(document) == config["amendment7_sha256"], "AMENDMENT7_DOCUMENT_MISMATCH")
    # The signed document must name exactly one seal, in its labelled form, and it must be this
    # family's own (a document of another revision that merely mentions this seal is refused).
    seals = re.findall(rb"selo `([0-9a-f]{64})`", document)
    s.need(seals == [seal_sha256.encode("ascii")], "AMENDMENT7_DOES_NOT_NAME_THIS_SEAL")
    original = read_regular(stage / AMENDMENT_ORIGINAL, 65536)
    _, signed = s.validate_amendment(s.amendment_wrapper(original), config)
    s.need(now > signed, "PREPARE_BEFORE_AMENDMENT7_SIGNATURE")
    return config, config_raw, document, original, signed


def prepare(stage, *, f1_age=F1_AGE, require_root=True, token_check=None, clock=None):
    """Phase A. Every guard that does not depend on the roots runs BEFORE any root is created,
    including the authorization gate (original Assino before the first effect)."""
    need_root(require_root, "PREPARE_REQUIRES_LINUX_ROOT")
    clock = clock or (lambda: datetime.now(timezone.utc))
    stage = Path(stage)
    fam = stage / FAMILY_DIR
    import verify_family  # the staged copy is verified, not this file's directory
    verify_family.verify(fam)
    family = {}
    for name in FAMILY_FILES:
        family[name] = read_regular(fam / name, 4 * 1024 * 1024)
    s.need(s.sha(family["reference_extract.py"]) == s.REFERENCE, "STAGE_REFERENCE_MISMATCH")
    gate_checked_at = clock()
    config, config_raw, document, original, signed = amendment_gate(stage, s.sha(family["SHA256SUMS"]), gate_checked_at)
    eligible_raw = read_regular(stage / "ELIGIBLE_SET.json", s.ELIGIBLE_LIMIT)
    s.need(s.sha(eligible_raw) == s.ELIGIBLE_SET_PIN, "STAGE_ELIGIBLE_SET_NOT_FIXED")
    s.validate_eligible(eligible_raw, {"eligible_set_sha256": s.ELIGIBLE_SET_PIN, "eligible_count": s.ELIGIBLE_COUNT})
    age_raw = read_regular(f1_age, 32 * 1024 * 1024)
    s.need(s.sha(age_raw) == s.AGE_SHA256, "F1_AGE_MISMATCH")
    (token_check or (lambda: s.read_token(s.PROVIDER_ENV_PATH, s.PROVIDER_ENV_KEY)))()  # presence only
    s.need(not os.path.lexists(s.SOURCE_ROOT) and not os.path.lexists(s.CAMPAIGN_ROOT), "ROOTS_ALREADY_EXIST")
    os.umask(0o077)
    os.mkdir(s.SOURCE_ROOT, 0o700)
    os.chmod(s.SOURCE_ROOT, 0o700)
    os.mkdir(s.SOURCE_ROOT + "/" + FAMILY_DIR, 0o700)
    os.chmod(s.SOURCE_ROOT + "/" + FAMILY_DIR, 0o700)
    for name, raw in family.items():
        write_new(s.SOURCE_ROOT + "/" + FAMILY_DIR + "/" + name, raw, 0o400)
    write_new(s.SOURCE_ROOT + "/ELIGIBLE_SET.json", eligible_raw, 0o400)
    write_new(s.SOURCE_ROOT + "/" + LEAF_CONFIG, config_raw, 0o400)
    write_new(s.SOURCE_ROOT + "/" + AMENDMENT_DOCUMENT, document, 0o400)
    write_new(s.SOURCE_ROOT + "/" + AMENDMENT_ORIGINAL, original, 0o400)
    os.mkdir(s.CAMPAIGN_ROOT, 0o700)
    os.chmod(s.CAMPAIGN_ROOT, 0o700)
    write_new(s.CAMPAIGN_ROOT + "/" + s.AGE_NAME, age_raw, 0o500)
    write_new(s.CAMPAIGN_ROOT + "/" + s.LEDGER_NAME, b"", 0o600)   # EMPTY ledger, O_EXCL, pinned by measure
    fd = os.open(s.CAMPAIGN_ROOT, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    verify_family.verify(Path(s.SOURCE_ROOT + "/" + FAMILY_DIR))
    receipt = {"schema": "F2_PREPARE_RECEIPT_V1", "status": "PREPARED_NO_TIMER", "timers": 0,
               "gate_checked_at_utc": s.iso(gate_checked_at), "prepared_at_utc": s.iso(clock()),
               "amendment7_sha256": config["amendment7_sha256"],
               "amendment7_signature_sha256": config["amendment7_signature_sha256"],
               "amendment7_signed_at_utc": s.iso(signed),
               "eligible_set_sha256": s.ELIGIBLE_SET_PIN, "age_sha256": s.AGE_SHA256,
               "source_sha256": s.sha(family["series_runtime.py"]), "seal_sha256": s.sha(family["SHA256SUMS"]),
               "ledger_bytes": 0}
    raw = s.canonical(receipt)
    write_new(s.SOURCE_ROOT + "/" + PREPARE_RECEIPT, raw, 0o400)
    return dict(receipt, prepare_receipt_sha256=s.sha(raw))


def measure(probe=None, now=None, physical=True):
    if physical:
        s.need(sys.platform == "linux", "MEASUREMENT_REQUIRES_LINUX")
        s.need(os.path.realpath(sys.executable) == os.path.realpath(PYTHON), "MEASUREMENT_PYTHON_NOT_HOST")
    out = s.measure(probe or s.HostProbe(), now or datetime.now(timezone.utc))
    # Bind the measurement to the original preparation receipt (and through it to the authorization Assino).
    raw = read_regular(Path(s.SOURCE_ROOT) / PREPARE_RECEIPT, 4096)
    receipt = s.strict(raw)
    s.need(receipt.get("schema") == "F2_PREPARE_RECEIPT_V1", "PREPARE_RECEIPT_INVALID")
    m = dict(out["measurement"], prepare_receipt=receipt, prepare_receipt_sha256=s.sha(raw))
    runtime = dict(out["runtime"], measurement_record_sha256=s.sha(s.canonical(m)))
    return {"measurement": m, "runtime": runtime, "election": out["election"]}


def _runner(argv):
    proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=30,
                          env={"PATH": "/usr/bin:/bin", "LANG": "C"})
    return proc.returncode


def install(stage, bound_sha256, *, probe=None, runner=None, now=None, clock=None, require_root=True,
            token_check=None, physical=True):
    """Phase B. Zero timers unless the re-measurement equals the signed pins exactly."""
    need_root(require_root, "INSTALL_REQUIRES_LINUX_ROOT")
    clock = clock or (lambda: datetime.now(timezone.utc))
    raw = read_regular(Path(stage) / "BOUND.json", 2 * 1024 * 1024)
    s.need(s.sha(raw) == bound_sha256, "STAGE_BOUND_MISMATCH")
    bound = s.strict(raw, 2 * 1024 * 1024)
    s.need(set(bound) == {"schema", "documents"} and bound["schema"] == "F2_BOUND_V2", "BOUND_SCHEMA_INVALID")
    raws = {k: s.canonical(v) for k, v in bound["documents"].items()}
    values = s.validate_documents(raws)
    q, owner = values["request"], values["owner"]
    # No retroactivity: the owner's Assino precedes the first effect of phase B (BOUND copy, timers).
    s.need(clock() > s.stamp(owner["recorded_at_utc"]), "INSTALL_BEFORE_OWNER_RECORD")
    s.need(os.path.isdir(s.SOURCE_ROOT) and os.path.isdir(s.CAMPAIGN_ROOT), "ROOTS_NOT_PREPARED")
    s.need(not os.path.lexists(s.SOURCE_ROOT + "/BOUND.json"), "BOUND_ALREADY_INSTALLED")
    write_new(s.SOURCE_ROOT + "/BOUND.json", raw, 0o400)
    s.need(s.sha(read_regular(s.SOURCE_ROOT + "/BOUND.json", 2 * 1024 * 1024)) == bound_sha256, "INSTALLED_BOUND_MISMATCH")
    # Re-measure and require total equality with the signed pins (measured_at/record hash excluded).
    seen = measure(probe, clock(), physical)
    signed_runtime = {k: v for k, v in values["runtime"].items() if k != "measurement_record_sha256"}
    s.need({k: v for k, v in seen["runtime"].items() if k != "measurement_record_sha256"} == signed_runtime,
           "REMEASURE_RUNTIME_DIVERGED")
    s.need(seen["election"] == values["election"], "REMEASURE_ELECTION_DIVERGED")
    # Preview with the runtime's own guards (held identities, all pins, ledger empty, not revoked, token key).
    held = s.Held(q["source_root"], q["campaign_root"], values["election"])
    try:
        held.check(q, values["runtime"], probe or s.HostProbe())
        s.need(os.fstat(held.ledger).st_size == 0, "LEDGER_NOT_EMPTY")
        s.need(not s._exists(held.campaign_fd, s.REVOKED_NAME), "CAMPAIGN_REVOKED")
    finally:
        held.close()
    (token_check or (lambda: s.read_token(q["provider_env_path"], q["provider_env_key"])))()
    rows = plan(now or clock(), s.stamp(owner["recorded_at_utc"]))
    out = []
    for row in rows:
        # Re-check margin immediately before each unit: never install a slot with < 180 s left.
        if (s.stamp(row["utc"]) - clock()).total_seconds() < MARGIN_SECONDS:
            out.append({"slot": row["slot"], "installed": False, "reason": "MARGIN_LOST"})
            continue
        try:
            rc = (runner or _runner)(row["argv"])
        except BaseException as error:
            # Timeout or OS error: this unit may or may not exist. Stop here; readback decides.
            out.append({"slot": row["slot"], "utc": row["utc"], "unit": unit(row["slot"]), "installed": "UNCERTAIN",
                        "reason": s.safe_code(error)})
            break
        out.append({"slot": row["slot"], "utc": row["utc"], "unit": unit(row["slot"]), "installed": rc == 0, "rc": rc})
    result = {"schema": "F2_INSTALL_RESULT_V2", "bound_sha256": bound_sha256, "eligible_set_sha256": q["eligible_set_sha256"],
              "source_sha256": q["source_sha256"], "seal_sha256": q["seal_sha256"], "runtime_sha256": q["runtime_sha256"],
              "election_sha256": q["election_sha256"], "timers": out, "remeasure": "EQUAL", "preflight": "PASS",
              "skipped_slots": sorted(set(s.SLOTS) - {r["slot"] for r in rows})}
    if any(r.get("installed") == "UNCERTAIN" for r in out):
        result["code"] = "TIMER_INSTALL_UNCERTAIN"  # exit 2: stopped at an uncertain unit; timers listed above
    elif any(r.get("installed") is False and r.get("reason") != "MARGIN_LOST" for r in out) or not any(r.get("installed") is True for r in out):
        result["code"] = "TIMER_NOT_INSTALLED"  # exit 2: some timer failed, or none installed
    return result


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
        # Stops the timer only. A service already running rechecks REVOKED immediately before its GET.
        proc = subprocess.run([SYSTEMCTL, "stop", unit(slot) + ".timer"], capture_output=True, timeout=30,
                              env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        rows.append({"slot": slot, "stop_rc": proc.returncode})
    return {"schema": "F2_REVOKE_RESULT_V1", "revoked_at": at, "marker": marker, "timers": rows}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("plan", "prepare", "measure", "install", "readback", "revoke"))
    p.add_argument("--now")
    p.add_argument("--stage")
    p.add_argument("--bound-sha256")
    a = p.parse_args(argv)
    try:
        if a.command == "plan":
            result = {"schema": "F2_PLAN_V1", "slots": plan(s.stamp(a.now) if a.now else datetime.now(timezone.utc))}
        elif a.command == "prepare":
            s.need(bool(a.stage), "PREPARE_ARGUMENTS_INVALID")
            result = prepare(a.stage)
        elif a.command == "measure":
            # PRIVATE canonical JSON on stdout, no LF (as F1 measure_runtime). Redirect under umask 077.
            os.write(1, s.canonical(measure()))
            return 0
        elif a.command == "install":
            s.need(a.stage and a.bound_sha256 and s.pin(a.bound_sha256), "INSTALL_ARGUMENTS_INVALID")
            result = install(a.stage, a.bound_sha256)
        elif a.command == "readback":
            result = readback()
        else:
            result = revoke()
    except BaseException as error:
        # A partial install is reported, never cleaned up automatically. Timers are created only
        # after every guard, and runner failures are caught per unit, so a HOLD here left zero timers.
        result = {"schema": "F2_INSTALL_HOLD_V1", "command": a.command, "code": s.safe_code(error),
                  "source_root_exists": os.path.lexists(s.SOURCE_ROOT), "campaign_root_exists": os.path.lexists(s.CAMPAIGN_ROOT),
                  "bound_installed": os.path.lexists(s.SOURCE_ROOT + "/BOUND.json")}
    print(json.dumps(result, sort_keys=True, indent=1))
    return 2 if "code" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
