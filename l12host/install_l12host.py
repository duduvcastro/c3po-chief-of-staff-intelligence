"""L12-HOST v3.1 installer (F2 install_series pattern: measurement, validation of EVERYTHING before the first write,
readback, revocation). Root on the host, by Fable. No shell: every command is an argv list. Env-files never opened.

The installer never judges the host with its own (staged) import of the runtime: the INSTALLED runtime does, in a
subprocess, with a pinned bounded protocol (one canonical L12HOST_PREVIEW_V3 line, 64 KiB, 120 s). B2.

prepare  --stage <dir>                 lot W: the owner's W Assino (W_REQUEST/W_OWNER/W_QUESTION in <dir>) is checked
                                       BEFORE the first effect; then the root 0700, its children 0700 (src, ledger,
                                       starts, extended, receipts, results, work, lots), the runtime family 0400 and the
                                       EMPTY ledger 0600 (O_EXCL). No timer. The veto and docker-config directories are
                                       created by INSTALL_TREE04, never here.
measure  --layout <layout.json>        read-only: the PRIVATE runtime document on stdout (paths, inodes)
plan     --stage <dir> --lot <LOT> --now <UTC>   the systemd-run argv that install would use (no effect)
install  --stage <dir> --lot <LOT> --bound-sha256 <hex>
                                       after the owner's Assino of the lot REQUEST, with every check BEFORE the first
                                       write: lot bytes + core plan + shell ABI + owner record + BOUND; re-measure equal
                                       to the signed runtime; EVERY signed slot schedulable (margin >= 180 s, after the
                                       signature, start-minute rules); cross-lot spacing and ORDER (S2) against every
                                       installed lot; then the INSTALLED runtime's preview-stage of the staged lot. Then
                                       copy the lot (0400), the installed runtime's preview of the installed lot, and ONE
                                       transient timer per signed slot (AccuracySec=1s, Persistent=false, oneshot,
                                       Restart=no). A refusal after the copy is a HOLD: nothing is deleted or retried.
install-derived --layout <layout.json> --lot <LOT> --derived <file>
                                       a DERIVED output installed AFTER the lot's BOUND (today only the J4 registry):
                                       the installed runtime checks its derivation rule BEFORE the write, then O_EXCL
                                       0400 in <lot>/derived/, then the installed runtime re-checks the installed bytes.
readback --layout <layout.json> --lot <LOT>
revoke   --layout <layout.json> --lot <LOT>   REVOKED marker in the lot (runtime refuses), timers stopped
image-check --layout <layout.json> --image <sha256:...>
                                       v3.1 HOST READBACK HR-1 (finding 11): every K9 row runs
                                       `IMAGE timeout -s KILL <n> python ...`. Two bounded, network-less, read-only
                                       containers of the pinned image (same hardening as the engine, no mount, no env
                                       file, no secret): `timeout -s KILL 10 python -I -c pass` must exit 0, and
                                       `timeout -s KILL 2 python -I -c <sleep 30>` must be KILLED (exit 137) in < 15 s.
                                       Prints IMAGE_TIMEOUT_KILL_PRESENT or a HOLD. Run by Fable on the host only with
                                       its own authorization (it starts two short containers); never by a timer.
"""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))
sys.path.insert(0, str(HERE))
import l12host_runtime as rt          # noqa: E402
import verify_family                  # noqa: E402

MARGIN_SECONDS = 180
PREVIEW_TIMEOUT_SECONDS = 120
PREVIEW_OUTPUT_LIMIT = 65536
SUBPROCESS_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "SYSTEMD_PAGER": "", "SYSTEMD_COLORS": "0"}
RUNTIME_FAMILY = rt.SHELL_SOURCES + rt.CORE_SOURCES
need = rt.need


def need_root(require_root, code):
    if require_root:
        need(sys.platform == "linux" and os.geteuid() == 0, code)


def read_stage(path, limit=rt.LIMIT):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= limit, "STAGE_FILE_INVALID")
        raw = b""
        while True:
            part = os.read(fd, 65536)
            if not part:
                break
            raw += part
            need(len(raw) <= limit, "STAGE_FILE_INVALID")
        return raw
    finally:
        os.close(fd)


def write_new(path, raw, mode):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        written = 0
        while written < len(raw):
            written += os.write(fd, raw[written:])
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)


def mkdir_private(path):
    os.mkdir(path, 0o700)
    os.chmod(path, 0o700)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def family_core():
    """The family's own modules loaded once from this checkout (for validation only, never for a slot or a host
    judgement: that is the installed runtime's preview)."""
    class Fam:
        pass
    import finite_batch, verification_binding, image_path_adapter, image_capacity_gate, outer_limiter  # noqa
    import bounded_readback, bounded_image_capacity_gate  # noqa
    import bounded_runner, capacity_monday_gate, k9_receipt_adapter  # noqa
    import l12host_effect, l12host_decode, l12host_extended  # noqa
    f = Fam()
    f.fb, f.vb, f.image, f.gate = finite_batch, verification_binding, image_path_adapter, image_capacity_gate
    f.bounded, f.bgate = bounded_readback, bounded_image_capacity_gate
    f.outer, f.br, f.cap = outer_limiter, bounded_runner, capacity_monday_gate
    f.k9, f.fx, f.dec, f.ext = k9_receipt_adapter, l12host_effect, l12host_decode, l12host_extended
    l12host_extended.RT = rt
    l12host_decode.RT = rt
    return f


# ------------------------------------------------------------------ lot W: prepare
W_REQUEST_SCHEMA = "L12HOST_W_REQUEST_V3"


def w_gate(stage, family_seal, layout, now):
    """The owner's Assino of the W REQUEST precedes the first effect."""
    request_raw = read_stage(stage / "W_REQUEST.json")
    question_raw = read_stage(stage / "W_QUESTION.txt")
    owner_raw = read_stage(stage / "W_OWNER.json")
    request = rt.strict(request_raw, kind=rt.Hold)
    need(set(request) == {"schema", "seal_sha256", "layout_sha256", "prepared_at", "owner_deadline"}
         and request["schema"] == W_REQUEST_SCHEMA and request["seal_sha256"] == family_seal
         and request["layout_sha256"] == rt.sha(rt.canonical(layout)), "W_REQUEST_UNBOUND")
    owner = rt.validate_owner(owner_raw, request_raw, question_raw, rt.Hold)
    need(rt.stamp(request["prepared_at"], rt.Hold) <= rt.stamp(owner["question_published_at"], rt.Hold)
         and rt.stamp(owner["signed_at"], rt.Hold) <= rt.stamp(request["owner_deadline"], rt.Hold), "W_OWNER_CHRONOLOGY_INVALID")
    need(now > rt.stamp(owner["signed_at"], rt.Hold), "PREPARE_BEFORE_W_SIGNATURE")
    return request_raw, owner_raw, question_raw


def family_files(family_dir):
    """The family exactly as sealed (verify_family refuses any extra/missing/changed file); the runtime subset."""
    result = verify_family.verify(family_dir)
    files = {name: read_stage(family_dir / name, 4 * 1024 * 1024) for name in RUNTIME_FAMILY}
    return files, result["seal_sha256"]


def prepare(stage, *, require_root=True, clock=None, physical=True):
    need_root(require_root, "PREPARE_REQUIRES_LINUX_ROOT")
    clock = clock or rt.native_utc
    stage = Path(stage)
    layout = rt.validate_layout(rt.strict(read_stage(stage / "layout.json"), kind=rt.Hold), rt.Hold)
    need(not physical or layout["veto_dir"] == rt.EPOCH04_VETO_DIR, "VETO_DIRECTORY_NOT_EPOCH04")
    need(not physical or layout["root"] == rt.EPOCH04_L12_ROOT, "L12_ROOT_NOT_EPOCH04")
    files, seal_sha = family_files(stage / "l12host")
    w_request, w_owner, w_question = w_gate(stage, seal_sha, layout, clock())
    root = layout["root"]
    need(not os.path.lexists(root), "ROOT_ALREADY_EXISTS")
    parent = root.rsplit("/", 1)[0] or "/"
    import l12host_effect as fx
    fx.safe_ancestors(root, os.geteuid())
    need(os.path.isdir(parent) and not os.path.islink(parent), "ROOT_PARENT_INVALID")
    for path in (layout["veto_dir"], layout["docker_config"]):
        info = os.lstat(path)
        need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
             "PRECREATED_DIRECTORY_INVALID")
    need(os.listdir(layout["veto_dir"]) == [] and os.listdir(layout["docker_config"]) == [], "PRECREATED_DIRECTORY_NOT_EMPTY")
    os.umask(0o077)
    mkdir_private(root)
    for name in rt.CHILDREN:
        mkdir_private(rt.child(layout, name))
    src = rt.child(layout, "src")
    mkdir_private(src + "/vendor")
    for name, raw in files.items():
        write_new(src + "/" + name, raw, 0o400)
    write_new(rt.child(layout, "ledger") + "/" + rt.LEDGER_FILE, b"", 0o600)
    for name, raw in (("W_REQUEST.json", w_request), ("W_OWNER.json", w_owner), ("W_QUESTION.txt", w_question),
                      ("layout.json", rt.canonical(layout))):
        write_new(root + "/" + name, raw, 0o400)
    for path in [src + "/vendor", src] + [rt.child(layout, n) for n in rt.CHILDREN] + [root]:
        fsync_dir(path)
    for name, raw in files.items():
        need(read_stage(Path(src + "/" + name), 4 * 1024 * 1024) == raw, "PREPARE_READBACK_MISMATCH")
    return {"schema": "L12HOST_PREPARE_RESULT_V3", "status": "PREPARED_NO_TIMER", "timers": 0, "seal_sha256": seal_sha,
            "runtime_files": len(files), "layout_sha256": rt.sha(rt.canonical(layout)),
            "w_request_sha256": rt.sha(w_request), "w_owner_sha256": rt.sha(w_owner), "prepared_at": rt.iso(clock()),
            "ledger_bytes": 0}


def execution_mode():
    return "FD_EXEC_LINUX" if sys.platform == "linux" else "NAMED_EXEC_POSIX"


def measure(layout_path, *, probe=None, now=None, mode=None):
    layout = rt.validate_layout(rt.strict(read_stage(Path(layout_path)), kind=rt.Hold), rt.Hold)
    return rt.measure(layout, probe or rt.HostProbe(), now or rt.native_utc(), mode or execution_mode())


# ------------------------------------------------------------------ the installed runtime's preview protocol (B2)
def runtime_argv(layout, command, *words):
    return [layout["python"], "-I", "-S", "-B", rt.child(layout, "src") + "/l12host_runtime.py", command] + list(words)


def run_preview(argv, *, timeout=PREVIEW_TIMEOUT_SECONDS):
    """Bounded subprocess of the INSTALLED runtime: exit code, ONE canonical line <= 64 KiB, nothing else on stdout."""
    try:
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, env=SUBPROCESS_ENV)
    except subprocess.TimeoutExpired:
        raise rt.Hold("PREVIEW_TIMEOUT") from None
    out = proc.stdout
    need(0 < len(out) <= PREVIEW_OUTPUT_LIMIT and out.endswith(b"\n") and out.count(b"\n") == 1, "PREVIEW_OUTPUT_FRAMING")
    return proc.returncode, out[:-1]


def preview_check(reply, expected_command, expected, *, status="PREVIEW_PASS"):
    code, raw = reply
    record = rt.strict(raw, kind=rt.Hold)
    need(set(record) == {"schema", "command", "status", "code", "lot", "request_sha256", "bound_sha256",
                         "authority_sha256", "runtime_sha256", "mode", "slots", "detail"}
         and record["schema"] == rt.PREVIEW_SCHEMA and record["command"] == expected_command, "PREVIEW_PROTOCOL_INVALID")
    if record["status"] != status or code != 0:
        raise rt.Hold("PREVIEW_REFUSED_" + (record["code"] or "UNKNOWN"))
    need(all(record[k] == v for k, v in expected.items()), "PREVIEW_NOT_THIS_LOT")
    return record


# ------------------------------------------------------------------ lots: plan / install
def unit_name(layout, lot, slot):
    return layout["unit_prefix"] + lot.lower().replace("_", "-") + "-" + slot.lower()


def calendar(at):
    return rt.stamp(at).strftime("%Y-%m-%d %H:%M:%S") + " UTC"


def slot_command(layout, lot, slot_row):
    lot_dir = rt.child(layout, "lots") + "/" + lot
    return [layout["binaries"]["systemd_run"], "--unit=" + unit_name(layout, lot, slot_row["slot"]),
            "--description=L12-HOST lot " + lot + " slot " + slot_row["slot"],
            "--on-calendar=" + calendar(slot_row["at"]), "--timer-property=AccuracySec=1s",
            "--timer-property=Persistent=false", "--timer-property=RandomizedDelaySec=0",
            "--property=Type=oneshot", "--property=Restart=no",
            "--property=TimeoutStartSec=" + str(slot_row["timeout_start_seconds"]), "--property=UMask=0077",
            "--property=NoNewPrivileges=yes", "--property=PrivateTmp=yes", "--property=KillMode=control-group",
            "--property=WorkingDirectory=" + rt.child(layout, "work"), "--property=LimitCORE=0",
            layout["python"], "-I", "-S", "-B", rt.child(layout, "src") + "/l12host_runtime.py", "run",
            "--lot-dir", lot_dir, "--slot", slot_row["slot"]]


def plan_rows(authority, now, owner_signed):
    """EVERY signed slot, or a refusal: no silent skip (a lot is installed whole or not at all)."""
    rows = []
    for row in sorted(authority["slots"], key=lambda r: r["at"]):
        at = rt.stamp(row["at"], rt.Hold)
        margin = (at - now).total_seconds()
        need(margin >= MARGIN_SECONDS, "SLOT_MARGIN_LOST")
        need(owner_signed < at, "SLOT_NOT_AFTER_OWNER_SIGNATURE")
        rows.append({"slot": row["slot"], "at": row["at"], "target_kind": row["target_kind"], "target": row["target"],
                     "margin_seconds": int(margin), "argv": slot_command(authority["layout"], authority["lot"], row)})
    return rows


def lot_stage(stage, lot):
    need(rt.LOT.fullmatch(lot or "") is not None, "LOT_INVALID")
    base = Path(stage) / ("lot-" + lot)
    files = {name: read_stage(base / name) for name in rt.LOT_FILES}
    authority = rt.strict(files["authority.json"], kind=rt.Hold)
    table = authority.get("files")
    need(type(table) is dict, "FILES_TABLE_INVALID")
    extra = {}
    for rel, digest in table.items():
        need(type(rel) is str and rt.REL.fullmatch(rel) is not None, "FILES_TABLE_INVALID")
        raw = read_stage(base / rel)
        need(rt.sha(raw) == digest, "STAGE_LOT_FILE_PIN_CHANGED")
        extra[rel] = raw
    return files, extra


def validate_lot(files, extra, lot, fam, physical):
    fb = fam.fb
    request = files["request.json"]
    try:
        q = fb.validate_plan(request)
    except fb.Hold as error:
        raise rt.Hold(str(error)) from None
    need(rt.sha(files["authority.json"]) == q["authority_sha256"] and rt.sha(files["runtime.json"]) == q["runtime_sha256"],
         "LOT_PINS_UNBOUND")
    authority = rt.strict(files["authority.json"], kind=rt.Hold)
    rt.validate_authority(authority, q, fam, rt.Hold, physical=physical, files_raw=extra)
    need(authority["lot"] == lot, "LOT_NAME_MISMATCH")
    owner = rt.validate_owner(files["owner.json"], request, files["question.txt"], rt.Hold)
    bundle = fb.Bundle(request, files["bound.json"], (("authority", files["authority.json"]), ("owner", files["owner.json"]),
                                                     ("runtime", files["runtime.json"])))
    try:
        bundle.validate(q)
    except fb.Hold as error:
        raise rt.Hold(str(error)) from None
    return q, authority, owner


# ------------------------------------------------------------------ S2: cross-lot spacing and order (before any write)
def installed_lots(layout, exclude):
    """Every installed, non-revoked lot: {name: (authority, request)}."""
    lots_dir = rt.child(layout, "lots")
    out = {}
    for name in sorted(os.listdir(lots_dir)):
        if name == exclude or name.startswith(".") or os.path.lexists(Path(lots_dir) / name / rt.REVOKED):
            continue
        authority = rt.strict(read_stage(Path(lots_dir) / name / "authority.json"), kind=rt.Hold)
        request = rt.strict(read_stage(Path(lots_dir) / name / "request.json"), kind=rt.Hold)
        out[name] = (authority, request)
    return out


def lot_targets(authority, request):
    """[(target_kind, target, [slot instants], end)] of one lot (end = rt.target_end)."""
    tasks = {t["operation"]: t for t in request["tasks"]}
    steps = {s["step"]: s for s in (authority["extended"] or {}).get("steps", [])}
    rows = {}
    for s in authority["slots"]:
        rows.setdefault((s["target_kind"], s["target"]), []).append(rt.stamp(s["at"], rt.Hold))
    return [(k, t, sorted(ats), rt.target_end(k, t, authority["slots"], tasks, steps, rt.Hold))
            for (k, t), ats in sorted(rows.items())]


def cross_lot_check(lots):
    """S2, refused BEFORE the first write of the lot being installed:
    - no two slots of different lots within 30 s;
    - J (admission_manifest of a DOWN lot) after the end of every BOOTSTRAP activate (+30 s);
    - an exclusion window around J (first alternative - 30 s .. last alternative + J budget + 30 s): no slot of any
      other target of any lot may run inside it (the J4 child takes the ledger lock with a 0.5 s budget);
    - CAPACITY_MONDAY capacity_activate after J's last alternative + budget (+30 s);
    - the DOWN session start and capture after the end of every capacity_activate (+30 s);
    - the DOWN post after the end of the UP chain it reads back (+30 s)."""
    margin = timedelta(seconds=rt.J_EXCLUSION_SECONDS)
    targets = {name: lot_targets(a, q) for name, (a, q) in lots.items()}
    flat = [(name, k, t, at, end) for name, rows in targets.items() for k, t, ats, end in rows for at in ats]
    for i, (n1, _, _, at1, _) in enumerate(flat):
        for n2, _, _, at2, _ in flat[i + 1:]:
            need(n1 == n2 or abs((at1 - at2).total_seconds()) >= rt.SLOT_SPACING_SECONDS, "SLOTS_TOO_CLOSE_ACROSS_LOTS")
    by_lane = {}
    for name, (a, q) in lots.items():
        by_lane.setdefault(q["lane"], []).append(name)

    def find(name, kind, target):
        rows = [r for r in targets[name] if r[0] == kind and r[1] == target]
        return rows[0] if rows else None
    for down in by_lane.get("DOWNSTREAM_AFTER_E6", []):
        j = find(down, "CORE", "admission_manifest")
        if j is None:
            continue
        j_first, j_end = j[2][0], j[3]
        for boot in by_lane.get("BOOTSTRAP_MONDAY", []):
            m3 = find(boot, "CORE", "activate")
            need(m3 is None or j_first >= m3[3] + margin, "J_BEFORE_M3_END")
        window = (j_first - margin, j_end + margin)
        for name, k, t, at, end in flat:
            if (name, k, t) == (down, "CORE", "admission_manifest"):
                continue
            need(end <= window[0] or at >= window[1], "SLOT_INSIDE_J_EXCLUSION_WINDOW")
        for cap in by_lane.get("CAPACITY_MONDAY", []):
            act = find(cap, "CORE", "capacity_activate")
            if act is None:
                continue
            need(act[2][0] >= j_end + margin, "CAPACITY_BEFORE_J_END")
            for step in ("session_start", "capture_launch"):
                row = find(down, "EXTENDED", step)
                need(row is None or row[2][0] >= act[3] + margin, "READER_OR_CAPTURE_BEFORE_CAPACITY_END")
    for down in by_lane.get("DOWNSTREAM_AFTER_E6", []):
        post = find(down, "CORE", "post")
        if post is None:
            continue
        source = lots[down][0]["effects"]["post"]["source_lot"]
        if source in targets:
            need(post[2][0] >= max(r[3] for r in targets[source]) + margin, "POST_BEFORE_UP_CHAIN_END")


def run_argv(argv, timeout=30):
    proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, env=SUBPROCESS_ENV)
    return proc.returncode


def install(stage, lot, bound_sha256, *, require_root=True, probe=None, clock=None, runner=None, mode=None,
            physical=True, preview=None):
    """`preview(command, argv)` returns (exit_code, line) of the INSTALLED runtime; tests inject an in-process one
    (non-physical, synthetic); the default is the bounded subprocess."""
    need_root(require_root, "INSTALL_REQUIRES_LINUX_ROOT")
    clock = clock or rt.native_utc
    preview = preview or (lambda command, argv: run_preview(argv))
    fam = family_core()
    files, extra = lot_stage(stage, lot)
    need(rt.sha(files["bound.json"]) == bound_sha256, "STAGE_BOUND_MISMATCH")
    q, authority, owner = validate_lot(files, extra, lot, fam, physical)
    signed = rt.stamp(owner["signed_at"], rt.Hold)
    need(clock() > signed, "INSTALL_BEFORE_OWNER_SIGNATURE")
    layout = authority["layout"]
    runtime = rt.strict(files["runtime.json"], kind=rt.Hold)
    seen = rt.measure(layout, probe or rt.HostProbe(), clock(), mode or execution_mode())
    need(rt.runtime_equal(seen, runtime), "REMEASURE_RUNTIME_DIVERGED")
    lot_dir = rt.child(layout, "lots") + "/" + lot
    need(not os.path.lexists(lot_dir), "LOT_ALREADY_INSTALLED")
    rows = plan_rows(authority, clock(), signed)
    lots = installed_lots(layout, lot)
    lots[lot] = (authority, q)
    cross_lot_check(lots)
    expected = {"lot": lot, "request_sha256": rt.sha(files["request.json"]), "bound_sha256": bound_sha256,
                "authority_sha256": q["authority_sha256"], "runtime_sha256": rt.sha(files["runtime.json"]),
                "mode": authority["mode"], "slots": len(authority["slots"])}
    stage_lot = str(Path(stage).resolve() / ("lot-" + lot))
    preview_check(preview("preview-stage", runtime_argv(layout, "preview-stage", "--stage-lot", stage_lot, "--lot", lot)),
                  "preview-stage", expected)
    # ---- first write
    os.umask(0o077)
    mkdir_private(lot_dir)
    for name, raw in files.items():
        write_new(lot_dir + "/" + name, raw, 0o400)
    for rel, raw in sorted(extra.items()):
        sub = lot_dir + "/" + rel.split("/")[0]
        if not os.path.lexists(sub):
            mkdir_private(sub)
        write_new(lot_dir + "/" + rel, raw, 0o400)
    for sub in sorted({rel.split("/")[0] for rel in extra}):
        fsync_dir(lot_dir + "/" + sub)
    fsync_dir(lot_dir)
    result = {"schema": "L12HOST_INSTALL_RESULT_V3", "lot": lot, "lane": q["lane"], "bound_sha256": bound_sha256,
              "request_sha256": expected["request_sha256"], "authority_sha256": q["authority_sha256"],
              "runtime_sha256": q["runtime_sha256"], "remeasure": "EQUAL", "preview_stage": "PASS", "preview": None,
              "timers": [], "signed_slots": len(authority["slots"])}
    try:
        preview_check(preview("preview", runtime_argv(layout, "preview", "--lot-dir", lot_dir)), "preview", expected)
        result["preview"] = "PASS"
    except BaseException as error:
        # HOLD: the lot is copied, no timer exists; nothing is deleted, nothing is retried automatically.
        result.update(preview="REFUSED", code="PREVIEW_AFTER_COPY_HOLD", detail=rt.safe_code(error))
        return result
    out = []
    for row in rows:
        if (rt.stamp(row["at"], rt.Hold) - clock()).total_seconds() < MARGIN_SECONDS:
            out.append({"slot": row["slot"], "installed": False, "code": "SLOT_MARGIN_LOST_DURING_INSTALL"})
            continue
        try:
            rc = (runner or run_argv)(row["argv"])
        except BaseException as error:
            out.append({"slot": row["slot"], "unit": unit_name(layout, lot, row["slot"]), "installed": "UNCERTAIN",
                        "code": rt.safe_code(error)})
            break
        out.append({"slot": row["slot"], "at": row["at"], "unit": unit_name(layout, lot, row["slot"]),
                    "installed": rc == 0, "rc": rc, "code": None if rc == 0 else "TIMER_INSTALL_RC_NONZERO"})
    result["timers"] = out
    if any(r.get("installed") == "UNCERTAIN" for r in out):
        result["code"] = "TIMER_INSTALL_UNCERTAIN"
    elif len(out) != len(authority["slots"]) or any(r.get("installed") is not True for r in out):
        result["code"] = "TIMER_NOT_INSTALLED"
    return result


def install_derived(layout_path, lot, derived_path, *, require_root=True, preview=None):
    need_root(require_root, "INSTALL_REQUIRES_LINUX_ROOT")
    preview = preview or (lambda command, argv: run_preview(argv))
    layout = rt.validate_layout(rt.strict(read_stage(Path(layout_path)), kind=rt.Hold), rt.Hold)
    need(rt.LOT.fullmatch(lot or "") is not None, "LOT_INVALID")
    lot_dir = rt.child(layout, "lots") + "/" + lot
    derived_path = str(Path(derived_path).resolve())
    raw = read_stage(Path(derived_path))
    first = preview_check(preview("derived-check", runtime_argv(layout, "derived-check", "--lot-dir", lot_dir,
                                                                "--derived-file", derived_path)),
                          "derived-check", {"lot": lot}, status="DERIVED_PASS")
    need(first["detail"] == {"derived_sha256": rt.sha(raw), "installed": False}, "DERIVED_PREVIEW_NOT_THIS_FILE")
    sub = lot_dir + "/derived"
    if not os.path.lexists(sub):
        mkdir_private(sub)
    write_new(sub + "/" + rt.DERIVED_REGISTRY, raw, 0o400)
    fsync_dir(sub)
    fsync_dir(lot_dir)
    second = preview_check(preview("derived-check", runtime_argv(layout, "derived-check", "--lot-dir", lot_dir,
                                                                 "--installed")),
                           "derived-check", {"lot": lot}, status="DERIVED_PASS")
    need(second["detail"] == {"derived_sha256": rt.sha(raw), "installed": True}, "DERIVED_READBACK_MISMATCH")
    return {"schema": "L12HOST_INSTALL_DERIVED_RESULT_V3", "lot": lot, "derived": rt.DERIVED_REGISTRY,
            "sha256": rt.sha(raw), "rule": "J4_REGISTRY_DERIVATION_V3", "readback": "EQUAL"}


def installed_authority(layout_path, lot):
    layout = rt.validate_layout(rt.strict(read_stage(Path(layout_path)), kind=rt.Hold), rt.Hold)
    need(rt.LOT.fullmatch(lot or "") is not None, "LOT_INVALID")
    lot_dir = rt.child(layout, "lots") + "/" + lot
    return layout, lot_dir, rt.strict(read_stage(Path(lot_dir) / "authority.json"), kind=rt.Hold)


def readback(layout_path, lot, *, runner=None):
    layout, lot_dir, authority = installed_authority(layout_path, lot)
    show = runner or (lambda argv: subprocess.run(argv, capture_output=True, timeout=30, env=SUBPROCESS_ENV).stdout)
    systemctl = layout["binaries"]["systemctl"]
    rows = []
    for row in sorted(authority["slots"], key=lambda r: r["at"]):
        unit = unit_name(layout, lot, row["slot"])
        timer = show([systemctl, "show", unit + ".timer", "--no-pager", "-p",
                      "Id,LoadState,ActiveState,TimersCalendar,NextElapseUSecRealtime,LastTriggerUSec,AccuracyUSec,"
                      "Persistent,RandomizedDelayUSec,Unit"])
        service = show([systemctl, "show", unit + ".service", "--no-pager", "-p",
                        "LoadState,ActiveState,Result,ExecMainStatus,Restart,TimeoutStartUSec,Type"])
        rows.append({"slot": row["slot"], "at": row["at"], "unit": unit,
                     "timer": timer.decode("utf-8", "replace").splitlines(),
                     "service": service.decode("utf-8", "replace").splitlines()})
    return {"schema": "L12HOST_READBACK_V3", "lot": lot, "units": rows,
            "revoked_marker": os.path.lexists(lot_dir + "/" + rt.REVOKED)}


def revoke(layout_path, lot, *, require_root=True, runner=None, now=None):
    need_root(require_root, "REVOKE_REQUIRES_LINUX_ROOT")
    layout, lot_dir, authority = installed_authority(layout_path, lot)
    at = rt.iso(now or rt.native_utc())
    try:
        write_new(lot_dir + "/" + rt.REVOKED, rt.canonical({"schema": "L12HOST_REVOKED_V3", "lot": lot, "revoked_at": at}), 0o400)
        marker = "written"
    except FileExistsError:
        marker = "already_present"
    rows = []
    for row in authority["slots"]:
        rc = (runner or run_argv)([layout["binaries"]["systemctl"], "stop", unit_name(layout, lot, row["slot"]) + ".timer"])
        rows.append({"slot": row["slot"], "stop_rc": rc})
    return {"schema": "L12HOST_REVOKE_RESULT_V3", "lot": lot, "revoked_at": at, "marker": marker, "timers": rows}


IMAGE_CHECK_NAME = "l12h-e04-image-timeout-check"
IMAGE_CHECK_SCHEMA = "L12HOST_IMAGE_TIMEOUT_READBACK_V31"


def image_check_argv(layout, image, seconds, program):
    return [layout["binaries"]["docker"], "run", "--rm", "--pull", "never", "--init", "--user", "0:0", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--restart", "no", "--pids-limit", "64",
            "--network", "none", "--name", IMAGE_CHECK_NAME, "--label", "c3po.l12.readback=image-timeout", image,
            "timeout", "-s", "KILL", str(seconds), "python", "-I", "-c", program]


def image_check(layout_path, image, *, require_root=True, runner=None, clock=None):
    """HR-1 (v3.1 finding 11): the pinned image has a `timeout` that accepts `-s KILL <n>` and really KILLs. Output:
    exit codes, durations and hashes only (never the child output)."""
    need_root(require_root, "IMAGE_CHECK_REQUIRES_LINUX_ROOT")
    layout = rt.validate_layout(rt.strict(read_stage(Path(layout_path)), kind=rt.Hold), rt.Hold)
    need(type(image) is str and rt.IMAGE_ID.fullmatch(image) is not None, "IMAGE_ID_INVALID")
    import l12host_effect as fx
    fx.check_docker_config(layout["docker_config"], os.geteuid())
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "DOCKER_CONFIG": layout["docker_config"]}
    run = runner or (lambda argv, timeout: fx.run_bounded(argv, timeout, 65536, env))
    mono = clock or __import__("time").monotonic
    rows = {}
    for label, seconds, program, limit in (("positive", 10, "pass", 60),
                                           ("kill", 2, "import time; time.sleep(30)", 60)):
        started = mono()
        try:
            rc, out, err = run(image_check_argv(layout, image, seconds, program), limit)
            rows[label] = {"rc": rc, "seconds": round(mono() - started, 3), "stdout_sha256": rt.sha(out),
                           "stderr_sha256": rt.sha(err)}
        except BaseException as error:
            rows[label] = {"rc": None, "seconds": round(mono() - started, 3), "code": rt.safe_code(error)}
    ok = (rows["positive"].get("rc") == 0 and rows["kill"].get("rc") == 137 and rows["kill"]["seconds"] < 15)
    result = {"schema": IMAGE_CHECK_SCHEMA, "image_id": image, "checks": rows,
              "status": "IMAGE_TIMEOUT_KILL_PRESENT" if ok else "IMAGE_TIMEOUT_CHECK_FAILED"}
    if not ok:
        result["code"] = "IMAGE_TIMEOUT_CHECK_FAILED"
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("prepare", "measure", "plan", "install", "install-derived", "readback", "revoke",
                                       "image-check"))
    p.add_argument("--image")
    p.add_argument("--derived")
    p.add_argument("--stage")
    p.add_argument("--layout")
    p.add_argument("--lot")
    p.add_argument("--now")
    p.add_argument("--bound-sha256")
    a = p.parse_args(argv)
    try:
        if a.command == "prepare":
            need(bool(a.stage), "ARGUMENTS_INVALID")
            result = prepare(a.stage)
        elif a.command == "measure":
            need(bool(a.layout), "ARGUMENTS_INVALID")
            os.write(1, rt.canonical(measure(a.layout)))
            return 0
        elif a.command == "plan":
            need(a.stage and a.lot and a.now, "ARGUMENTS_INVALID")
            files, _ = lot_stage(a.stage, a.lot)
            authority = rt.strict(files["authority.json"], kind=rt.Hold)
            owner = rt.strict(files["owner.json"], kind=rt.Hold)
            result = {"schema": "L12HOST_PLAN_V3", "slots": plan_rows(authority, rt.stamp(a.now, rt.Hold),
                                                                      rt.stamp(owner["signed_at"], rt.Hold))}
        elif a.command == "install":
            need(a.stage and a.lot and a.bound_sha256 and rt.pin(a.bound_sha256), "ARGUMENTS_INVALID")
            result = install(a.stage, a.lot, a.bound_sha256)
        elif a.command == "install-derived":
            need(a.layout and a.lot and a.derived, "ARGUMENTS_INVALID")
            result = install_derived(a.layout, a.lot, a.derived)
        elif a.command == "readback":
            need(a.layout and a.lot, "ARGUMENTS_INVALID")
            result = readback(a.layout, a.lot)
        elif a.command == "image-check":
            need(a.layout and a.image, "ARGUMENTS_INVALID")
            result = image_check(a.layout, a.image)
        else:
            need(a.layout and a.lot, "ARGUMENTS_INVALID")
            result = revoke(a.layout, a.lot)
    except BaseException as error:
        result = {"schema": "L12HOST_INSTALL_HOLD_V3", "command": a.command, "code": rt.safe_code(error)}
    print(json.dumps(result, sort_keys=True, indent=1))
    return 2 if "code" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
