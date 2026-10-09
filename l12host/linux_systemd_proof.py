"""L12-HOST v3.1 Linux proof, CI ONLY (GitHub ubuntu-24.04 runner, root through sudo -n; refuses elsewhere).
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
5. v3.1: the effect engine's own gates refuse with nothing started: the SUPERVISOR while a ready file exists
   (READY_PRESENT_AT_SUPERVISOR_START) or while a veto entry exists; the READER while its supervisor is not running.
6. v3.1 (finding 9): a REAL-mode DOWN lot on the epoch-04 paths, PHYSICAL Shell, slots run by REAL systemd timers
   (slot services): R0 (ready_check, read-only) COMPLETE; S1 (session_start) in ONE claim: ready absent -> xpre ->
   supervisor unit copy started by the engine from inside the timer-run slot service -> the fake supervisor writes
   ready.json after 6 s -> READY wait -> recheck -> supervisor alive -> fresh ALLOW -> the engine starts the reader
   only with the same ready.json present and the supervisor alive -> hold to open + 30 s observing both units ->
   SESSION_START_V3 decode -> EXTENDED_COMPLETE; both units: Restart=no, NRestarts=0, running, no OnFailure.

Prints one JSON object; exit 1 if any check fails.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "tests"))
import kit                        # noqa: E402

rt, fx, inst, bind = kit.rt, kit.fx, kit.inst, kit.bind
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "SYSTEMD_PAGER": "", "SYSTEMD_COLORS": "0"}
PY = "/usr/bin/python3.12"
READY_DELAY_SECONDS = 6
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


def sh(argv, timeout=60):
    p = subprocess.run(argv, capture_output=True, timeout=timeout, env=ENV)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def show(unit, props):
    _, out, _ = sh(["/usr/bin/systemctl", "show", unit, "--no-pager", "-p", ",".join(props)])
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def safe_after(t, gap=0, span=100):
    """First instant >= t + gap such that every second of [t, t + span] passes the start-minute rules."""
    t = kit.allowed_after(t, gap)
    while any(fx.start_minute_violation(t + timedelta(seconds=k)) for k in range(0, span, 5)):
        t = kit.allowed_after(t + timedelta(seconds=20))
    return t


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
                doc = json.loads(path.read_bytes())
                results[slot] = {"status": doc.get("status"), "code": doc.get("code"),
                                 "result_class": doc.get("result_class"), "effect_calls": doc.get("effect_calls"),
                                 "diagnostics": doc.get("diagnostics")}
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


def main():
    assert sys.platform == "linux" and os.geteuid() == 0 and os.environ.get("GITHUB_ACTIONS") == "true", "CI_ONLY"
    assert not os.path.lexists(rt.EPOCH04_L12_ROOT), "EPOCH04_ROOT_ALREADY_PRESENT"
    os.umask(0o077)
    out = {"schema": "L12HOST_V31_LINUX_SYSTEMD_PROOF",
           "systemd_version": sh(["/usr/bin/systemctl", "--version"])[1].splitlines()[0],
           "real": ["procfs", "root", PY, "systemd timers/slot services/units", "installed runtime", "physical installer",
                    "physical DOWN Shell", "R6 core/outer/runner", "extended executor", "effect engine gates",
                    "runner04 bytes as signed file"],
           "fake": ["docker (root-owned python script)", "lots are REAL-mode SYNTHETIC",
                    "DOWN driver substitutions: open constant, capacity chain, C6 phases, J/post dependencies"]}
    checks = {}

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

    # 3. B2: REAL-mode synthetic UP lot, physical install, timers fire -----------------------------------------
    times, t = [], now + timedelta(seconds=240)
    for gap in (0, 155, 155, 155, 155):
        t = safe_after(t, gap)
        times.append(t)
    tasks, ops = [], []
    requires = {"prove": [], "collect": ["prove"], "commit_result": ["collect"], "publish_launch": ["commit_result"]}
    for i, core in enumerate(("prove", "collect", "commit_result", "publish_launch")):
        op = kit.CORE_RUNNER[core]
        ops.append(op)
        env.k9_plan(op, times[i], kit.CORE_K9_BUDGET, core=core)
        row = env.k9_row(op, 25)
        dec = env.k9_decoder(op, row)
        dec["mode"] = "REAL"
        tasks.append(env.task(core, [("P%d" % (i + 1), times[i])], requires[core], row, dec, budget=kit.CORE_K9_BUDGET))
    step = env.ext_step("components", times[4], 90, 90 - kit.EXT_KILL_MARGIN)
    step["slots"] = [{"slot": "X1", "at": kit.z(times[4])}]
    ops.append("components_launch")
    spec = env.spec("UP", "UPSTREAM_P", tasks, files=env.k9_files(ops), extended={"steps": [step]}, k9=env.k9_section(ops))
    spec["mode"] = "REAL"
    spec["decision_sha256"] = kit.sha(b"SYNTHETIC_PROOF_DECISION_NOT_D1")
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
    checks["physical_install_previews_and_timers"] = (installed.get("code") is None and installed["preview_stage"] == "PASS"
                                                      and installed["preview"] == "PASS"
                                                      and [r["installed"] for r in installed["timers"]] == [True] * 5)
    unit = inst.unit_name(layout, "UP", "P1")
    out["timer"] = show(unit + ".timer", ["LoadState", "ActiveState", "AccuracyUSec", "Persistent", "RandomizedDelayUSec"])
    out["service_before"] = show(unit + ".service", ["LoadState", "Type", "Restart", "TimeoutStartUSec", "KillMode"])
    checks["timer_accuracy_1s_not_persistent"] = (out["timer"].get("AccuracyUSec") == "1s"
                                                  and out["timer"].get("Persistent") == "no")
    checks["slot_service_oneshot_no_restart"] = (out["service_before"].get("Type") == "oneshot"
                                                 and out["service_before"].get("Restart") == "no")
    deadline = time.monotonic() + (times[4] - datetime.now(timezone.utc)).total_seconds() + 240
    results = wait_results(layout, "UP", ("P1", "P2", "P3", "P4", "X1"), deadline)
    out["slots"] = results
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
    r0 = safe_after(datetime.now(timezone.utc) + timedelta(seconds=240), 0, 180)
    down, opening, hold = proof_down_spec(env, reader, sup, t_sign, up_req, up_bound, initial, r0)
    down_out = stage / "lot-DOWN"
    spec_path = base / "spec-DOWN.json"
    spec_path.write_text(json.dumps(down))
    bind.lot(str(spec_path), str(layout_path), str(env.runtime_path), kit.z(t_sign - timedelta(minutes=30)), str(down_out))
    bind.owner(str(down_out), kit.z(t_sign - timedelta(minutes=1)), kit.z(t_sign))
    bind.bound(str(down_out), kit.z(t_sign + timedelta(seconds=30)))
    out["down_physical_without_substitution"] = physical_verdict(down_out)
    checks["down_physical_refuses_a_non_monday_open"] = out["down_physical_without_substitution"] == "SESSION_OPEN_NOT_THE_MONDAY_ONE"
    lot_dir = install_lot_dir(layout, "DOWN", down_out)
    main_tail(out, checks, env, layout, veto, bindir, down_out, lot_dir, opening, hold)
    out["checks"] = checks
    out["ok"] = all(checks.values())
    print(json.dumps(out, sort_keys=True))
    shutil.rmtree(str(veto), ignore_errors=True)
    return 0 if out["ok"] else 1


def proof_unit_rows(layout, docker, dockercfg):
    """The reviewed reader / supervisor references copied for the epoch-04 paths (fake docker path, layout DOCKER_CONFIG)."""
    dc_rename = lambda cfg_dir: ("DOCKER_CONFIG=" + cfg_dir + "/docker-cli", "DOCKER_CONFIG=" + str(dockercfg))
    renames = lambda name, ref, cfg_dir: [(ref, name), ("/usr/bin/docker", str(docker)), ("-/usr/bin/docker", "-" + str(docker)),
                                          dc_rename(cfg_dir)]
    reader, r_dropped, r_changed = bind.unit_row(str(HERE / "reference" / "c3po-reader.service"), {
        "@HOST_DATA_ROOT@": rt.DAY_D_DATA, "@HOST_JOURNAL_ROOT@": rt.EPOCH04_JOURNAL_ROOT,
        "@HOST_CAPACITY_ROOT@": rt.EPOCH04_CAPACITY_ROOT, "@HOST_CONFIG_DIR@": rt.EPOCH04_READER_CONFIG,
        "@IMAGE_ID@": kit.IMAGE, "@NETWORK@": "c3po_default", "@CONTAINER_JOURNAL_ROOT@": rt.CONTAINER_JOURNAL_ROOT},
        rt.READER_NAME, "SESSION_READER", layout, renames(rt.READER_NAME, "c3po-reader", rt.EPOCH04_READER_CONFIG))
    sup, s_dropped, s_changed = bind.unit_row(str(HERE / "reference" / "c3po-massive.service"), {
        "@HOST_JOURNAL_ROOT@": rt.EPOCH04_JOURNAL_ROOT, "@HOST_STATE_ROOT@": rt.EPOCH04_SUPERVISOR_STATE,
        "@HOST_CONFIG_DIR@": rt.EPOCH04_SUPERVISOR_CONFIG, "@IMAGE_ID@": kit.IMAGE, "@NETWORK@": "c3po_default",
        "@CONTAINER_JOURNAL_ROOT@": rt.CONTAINER_JOURNAL_ROOT},
        rt.SUPERVISOR_NAME, "SUPERVISOR", layout, renames(rt.SUPERVISOR_NAME, "c3po-massive", rt.EPOCH04_SUPERVISOR_CONFIG))
    return reader, sup, {"reader": {"dropped": r_dropped, "changed": r_changed},
                         "supervisor": {"dropped": s_dropped, "changed": s_changed}}


def physical_verdict(lot_out):
    """The DOWN proof lot through the PHYSICAL shell ABI without the proof's open substitution (expected refusal)."""
    fam = inst.family_core()
    try:
        rt.validate_authority(json.loads((Path(lot_out) / "authority.json").read_bytes()),
                              fam.fb.validate_plan((Path(lot_out) / "request.json").read_bytes()), fam, rt.Hold, physical=True)
        return "ACCEPTED"
    except rt.Hold as error:
        return str(error)


def proof_down_spec(env, reader, sup, t_sign, up_req, up_bound, initial, r0):
    """The REAL-mode synthetic DOWN lot of the proof on the epoch-04 paths: E6/J1/PO in the past (never fired), R0 and
    S1 in the future (fired by timers). Returns (spec, open, hold_until)."""
    e6_doc = env.docs / "e6.json"
    if not e6_doc.exists():
        write_private(e6_doc, kit.canonical({"synthetic_e6_document": 0}))
    rule = env.assets / "bounded_rule.json"
    rule.write_bytes(kit.canonical({"synthetic": "BOUNDED_READBACK_RULE_PLACEHOLDER"}))
    hot = (HERE / "vendor" / "j4_hot_worker.py")
    s1 = r0 + timedelta(seconds=60)
    s_nb = s1 - timedelta(seconds=32)                      # 13:28:30Z analog: open - 90 s
    opening = s_nb + timedelta(seconds=90)                 # 13:30:00Z analog
    hold = opening + timedelta(seconds=30)                 # 13:30:30Z analog
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


def main_tail(out, checks, env, layout, veto, bindir, down_out, lot_dir, opening, hold):
    # 5. the engine's own gates refuse with nothing started (before any DOWN timer fires) -------------------------
    installed_fx = (Path(rt.child(layout, "src")) / "l12host_effect.py").read_bytes()
    checks["engine_bytes_are_the_installed_ones"] = installed_fx == (HERE / "l12host_effect.py").read_bytes()
    a_sha, q_sha = kit.sha((down_out / "authority.json").read_bytes()), kit.sha((down_out / "request.json").read_bytes())
    key = env.xkey("session_start")

    def engine(kind, ready_sha=None, pid=None):
        until = kit.z(datetime.now(timezone.utc) + timedelta(seconds=10))
        return fx.run(fx.engine_argv(lot_dir, kind, "session_start", a_sha, q_sha, key, "d" * 64, until, ready_sha, pid))
    ready_path = Path(rt.EPOCH04_READY_PATH)
    write_private(ready_path, kit.canonical({"epoch": kit.EPOCH, "session": kit.DAY}))
    negatives = {"supervisor_with_ready_present": engine("EXTENDED_PRE")[1]["code"]}
    ready_sha = kit.sha(ready_path.read_bytes())
    negatives["reader_without_running_supervisor"] = engine("EXTENDED", ready_sha, "4242")[1]["code"]
    ready_path.unlink()
    (veto / "STOP").write_text("x")
    negatives["supervisor_with_veto_present"] = engine("EXTENDED_PRE")[1]["code"]
    (veto / "STOP").unlink()
    out["engine_negatives"] = negatives
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
    for row in authority["slots"]:
        if row["slot"] not in ("R0", "S1"):
            continue
        argv = inst.slot_command(layout, "DOWN", row)
        argv = argv[:argv.index(PY)] + [PY, "-I", "-S", "-B", str(driver), "--root", layout["root"], "--lot-dir", lot_dir,
                                         "--slot", row["slot"], "--open", kit.z(opening)]
        timers[row["slot"]] = sh(argv)[0]
    checks["down_timers_installed"] = timers == {"R0": 0, "S1": 0}
    deadline = time.monotonic() + (hold - datetime.now(timezone.utc)).total_seconds() + 240
    down_results = wait_results(layout, "DOWN", ("R0", "S1"), deadline)
    out["down_slots"] = down_results
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
        session = {"ready_observed_at": record["ready_observed_at"], "supervisor_ack_observed_at": sup_ack["observed_at"],
                   "reader_held": rdr_ack["held"], "reader_polls": rdr_ack["polls"], "supervisor": rdr_ack["supervisor"],
                   "gates": record["gates"],
                   "xpre_marker": (Path(layout["root"]) / "extended" / ("xpre-" + key)).exists()}
        checks["ready_was_waited_after_the_supervisor_start"] = (
            rt.stamp(record["ready_observed_at"]) > rt.stamp(sup_ack["observed_at"]))
        checks["reader_held_with_supervisor_alive"] = (rdr_ack["held"] is True and rdr_ack["polls"] >= 3
                                                       and rdr_ack["supervisor"]["running_through_hold"] is True
                                                       and rdr_ack["supervisor"]["main_pid"] == sup_ack["properties"]["MainPID"])
    except (OSError, ValueError, KeyError) as error:
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
    except (OSError, ValueError, KeyError):
        checks["s1_ran_from_its_timer_in_its_slot_window"] = False

    # cleanup of everything this disposable runner got
    for name in (rt.READER_NAME, rt.SUPERVISOR_NAME):
        sh(["/usr/bin/systemctl", "stop", name + ".service"], timeout=90)
        sh(["/usr/bin/systemctl", "reset-failed", name + ".service"])
    for lot, slots in (("UP", ("P1", "P2", "P3", "P4", "X1")), ("DOWN", ("R0", "S1"))):
        for slot in slots:
            sh(["/usr/bin/systemctl", "stop", inst.unit_name(layout, lot, slot) + ".timer"])


if __name__ == "__main__":
    raise SystemExit(main())
