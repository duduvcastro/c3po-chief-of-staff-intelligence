"""L12-HOST v3.2 test kit. SYNTHETIC only: fake docker / systemd-run / systemctl (Python scripts), FIXTURE-mode lots,
fixture external modules, the REAL vendored Codex modules, the REAL shell modules and the REAL runner04 bytes (as a
signed file only; never executed: the fake docker writes the receipts). No network, host, provider, SQL, image,
container or secret. FIXTURE mode is refused on the host by construction.

Temporary roots go under $L12_TEST_TMP when set (its ancestors must not be group/other writable).
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

TESTS = Path(__file__).resolve().parent
FAMILY = TESTS.parent
ASSETS = TESTS / "assets"
sys.path.insert(0, str(FAMILY / "vendor"))
sys.path.insert(0, str(FAMILY))
import l12host_runtime as rt      # noqa: E402
import l12host_effect as fx       # noqa: E402
import install_l12host as inst    # noqa: E402
import bind_l12host as bind       # noqa: E402

PY = os.path.realpath(sys.executable)
CANARY = "CANARY-NOT-A-SECRET-7f3a91"
STDOUT_MARKER = "STDOUT-MARKER-NEVER-PUBLIC-55e1"
D1 = "09de76e5a2ee54fdcdfa477b0f8df101fcda761b7f416e4308e29c0235e51c2a"
IMAGE = "sha256:" + "ab" * 32
MODE = "FD_EXEC_LINUX" if sys.platform == "linux" else "NAMED_EXEC_POSIX"
EPOCH, DAY, PREVIOUS = "R2D2-V2-SHADOW-2026-10-12", "2026-10-12", "2026-10-09"
RUNNER_RAW = (FAMILY / "lots" / "k9tools" / "k9_runner04.py").read_bytes()
RUNNER_SHA = hashlib.sha256(RUNNER_RAW).hexdigest()
# v3.1 (finding 10): the staged family is the WHOLE sealed family (tests/ included), so the W seal of a staging (and
# of the Linux proof) is exactly sha256(l12host/SHA256SUMS) of this delivery: the seal Saturday's W signs.
FAMILY_FILES = sorted(p.relative_to(FAMILY).as_posix() for p in FAMILY.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts and p.relative_to(FAMILY).as_posix() != "SHA256SUMS")


def family_sums(root=FAMILY, names=None):
    """The family SHA256SUMS bytes (the exact format verify_family parses and the seal step writes)."""
    lines = []
    for name in names or FAMILY_FILES:
        lines.append(hashlib.sha256((Path(root) / name).read_bytes()).hexdigest() + "  " + name)
    return ("\n".join(sorted(lines, key=lambda l: l.split("  ")[1])) + "\n").encode("ascii")


def runner_literals(raw=RUNNER_RAW):
    wanted = {"EPOCH", "DAYS", "PACKAGE", "REVISION", "OPS", "LIMITS", "FLOOR", "DB", "PRESENCE"}
    found = {}
    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in wanted:
            found[node.targets[0].id] = ast.literal_eval(node.value)
    return found


LIT = runner_literals()
# v3.1 (finding 8): K9 rows keep >= 30 s slack: budget >= KILL + 20 (docker margin) + 15 (gate allowance) + 30.
CORE_K9_BUDGET = 90
EXT_KILL_MARGIN = 65
CORE_RUNNER = dict(rt.K9_CORE_RUNNER_OPS)
STEP_RUNNER = {name: row[1] for name, row in rt.EXTENDED_TABLE["UPSTREAM_P"].items()}

FAKE_COMMON = r'''
import hashlib, json, os, sys, time
from datetime import datetime, timezone
HERE = os.path.dirname(os.path.abspath(__file__))
def load(name, default):
    try:
        with open(os.path.join(HERE, name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return default
def save(name, value):
    tmp = os.path.join(HERE, name + ".tmp%d" % os.getpid())
    with open(tmp, "w") as f:
        json.dump(value, f)
    os.replace(tmp, os.path.join(HERE, name))
def log(tool, argv):
    if argv[:1] == ["--warm"]:
        return
    with open(os.path.join(HERE, "log.jsonl"), "a") as f:
        f.write(json.dumps({"tool": tool, "argv": argv, "env": sorted(os.environ)}) + "\n")
def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
cfg = load("fake.json", {})
state = load("state.json", {"units": {}})
argv = sys.argv[1:]
if argv[:1] == ["--warm"]:
    sys.exit(0)
'''
FAKE_DOCKER = FAKE_COMMON + r'''
log("docker", argv)
def value(flag):
    return argv[argv.index(flag) + 1]
if argv and argv[0] == "run":
    name = value("--name")
    b = cfg.get(name, {})
    if "pid_file" in b:
        with open(b["pid_file"], "w") as f:
            f.write(str(os.getpid()))
    time.sleep(b.get("sleep", 0))
    for w in b.get("writes", []):
        with open(w["path"], "w") as f:
            f.write(w["content"].replace("@NOW@", now()))
    sys.stdout.write(b.get("stdout", "") + "%s\n" % "STDOUT-MARKER-NEVER-PUBLIC-55e1")
    if "stdout_bytes" in b:
        sys.stdout.write("x" * b["stdout_bytes"])
    sys.exit(b.get("exit", 0))
sys.exit(9)
'''
FAKE_SYSTEMD_RUN = FAKE_COMMON + r'''
log("systemd-run", argv)
if not any(w.startswith("--on-calendar=") for w in argv):
    unit = [w for w in argv if w.startswith("--unit=")][0][7:]
    states = cfg.get("unit_states", {})
    state["units"][unit + ".service"] = states.get(unit, cfg.get("unit_state", {"ActiveState": "active",
        "SubState": "running", "NRestarts": "0", "Result": "success", "MainPID": "4242", "Restart": "no"}))
    save("state.json", state)
    for w in cfg.get("unit_writes", {}).get(unit, []):
        tmp = w["path"] + ".tmp%d" % os.getpid()
        with open(tmp, "w") as f:
            f.write(w["content"])
        os.replace(tmp, w["path"])
sys.exit(cfg.get("systemd_run_rc", 0))
'''
FAKE_SYSTEMCTL = FAKE_COMMON + r'''
log("systemctl", argv)
if argv and argv[0] == "show":
    unit = argv[1]
    print("Id=" + unit)
    if unit in state["units"]:
        print("LoadState=loaded")
        shows = state.setdefault("shows", {})
        shows[unit] = shows.get(unit, 0) + 1
        save("state.json", state)
        die = cfg.get("die_after_shows", {}).get(unit)
        current = dict(state["units"][unit])
        if die is not None and shows[unit] > die:
            current.update(ActiveState="failed", SubState="failed", MainPID="0")
        for k, v in current.items():
            print(k + "=" + v)
    else:
        print("LoadState=not-found"); print("ActiveState=inactive"); print("SubState=dead"); print("NRestarts=0")
sys.exit(0)
'''


class FakeProbe:
    """boot_id may trigger a side effect in the RUNNER worker (pid != pgrp: not the outer session leader) or on the
    n-th call inside the OUTER worker (pid == pgrp == sid, after its setsid)."""

    def __init__(self, on_runner_worker=None, on_outer_call=None):
        self.boot = b"0f1e2d3c-4b5a-4968-8776-655443322110\n"
        self.on_runner_worker = on_runner_worker
        self.on_outer_call = on_outer_call
        self.outer_calls = 0

    def platform(self):
        return sys.platform

    def euid(self):
        return os.geteuid()

    def boot_id(self):
        if self.on_runner_worker is not None and os.getpid() != os.getpgrp():
            self.on_runner_worker()
        if self.on_outer_call is not None and os.getpid() == os.getpgrp() == os.getsid(0):
            self.outer_calls += 1
            self.on_outer_call(self.outer_calls)
        return self.boot

    def python_version(self):
        return "%d.%d.%d" % sys.version_info[:3]


class JumpClock:
    """Real wall clock plus an offset: ONLY for steps without an effect (W prepare, install)."""

    def __init__(self):
        self.offset = timedelta(0)

    def __call__(self):
        return datetime.now(timezone.utc) + self.offset

    def jump(self, to):
        self.offset = to - datetime.now(timezone.utc)

    def real(self):
        self.offset = timedelta(0)


def past_signature_instant(now):
    """Latest instant <= now - 1 h whose BRT time of day is inside 07:30-21:30."""
    local = (now - timedelta(hours=1)).astimezone(rt.BRT)
    if (local.hour, local.minute) > (21, 30):
        local = local.replace(hour=21, minute=0, second=0, microsecond=0)
    elif (local.hour, local.minute) < (7, 30):
        local = (local - timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0)
    return local.replace(microsecond=0).astimezone(timezone.utc)


def allowed_after(t, gap=0):
    """First instant >= t + gap allowed by the code start-minute rules (whole seconds)."""
    t = (t + timedelta(seconds=gap)).replace(microsecond=0)
    while fx.start_minute_violation(t) is not None:
        t += timedelta(seconds=20)
    return t


def z(value):
    return rt.iso(value)


def plus(value):
    return value.astimezone(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return rt.canonical(value)


# v3.2 (night-independent suite): the DOWN fixtures are signed at real now + 3 s (their REQUEST must follow the UP
# originals), so between 21:45 and 07:00 BRT their owner record is outside the 07:00-21:45 BRT window, and the runtime
# re-validates the owner record in EVERY Shell / LotView / preview, not only at signing (v3.1's sign_down bypassed it
# only while signing: 16 failures + 2 errors at 22:00 BRT). The kit exempts EXACTLY the signatures it registers in
# fixture_signed_at, in every in-process path, for the life of an Env; every other signature (UP lots, Monday lots,
# the guard's own table test) meets the real guard. The Linux proof never builds an Env (its lots are signed in the
# daytime window and judged by the installed runtime in subprocesses).
REAL_OWNER_TIME_GUARD = rt.owner_time_guard
FIXTURE_SIGNED_AT = set()


def owner_time_guard_except_fixtures(signed_at, kind=rt.Hold):
    if signed_at in FIXTURE_SIGNED_AT:
        return None
    return REAL_OWNER_TIME_GUARD(signed_at, kind)


def fixture_signed_at(env):
    """The DOWN fixture's signature instant (real now + 3 s), registered for the exemption above."""
    signed = env.down_t0 + timedelta(seconds=3)
    FIXTURE_SIGNED_AT.add(z(signed))
    return signed


FILE_PROVIDER_XATTR = b"com.apple.file-provider-domain-id"
TEMP_PARENT = {"source": None, "file_provider_candidates_skipped": 0}


def file_provider_domain(path):
    """v3.2 (M1, root cause of the v3.1 3.12 flake): on macOS a folder synced by a File Provider (iCloud Drive
    "Desktop & Documents", ~/Library/Mobile Documents, ...) gets the ctime of every newly written file changed by the
    provider a fraction of a second to a few seconds after the write (measured here: evidence/M1_ROOT_CAUSE_PROBE_DARWIN
    .json), which the runtime's strict reader rightly refuses as INPUT_FILE_CHANGED. Returns the first ancestor that
    carries the provider's domain attribute, or None (always None off macOS)."""
    if sys.platform != "darwin":
        return None
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        getxattr = libc.getxattr
        getxattr.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32,
                             ctypes.c_int]
        getxattr.restype = ctypes.c_ssize_t
    except (OSError, AttributeError):
        return None
    path = Path(os.path.realpath(path))
    for candidate in [path] + list(path.parents):
        if getxattr(str(candidate).encode("utf-8"), FILE_PROVIDER_XATTR, None, 0, 0, 1) >= 0:   # XATTR_NOFOLLOW
            return str(candidate)
    return None


def safe_temp_parent():
    """$L12_TEST_TMP, else the system temp dir, else home: the first whose ancestors are not group/other writable and
    that is NOT inside a macOS File Provider domain (v3.2, M1)."""
    skipped = []
    for source, candidate in (("L12_TEST_TMP", os.environ.get("L12_TEST_TMP")), ("tempfile", tempfile.gettempdir()),
                              ("home", str(Path.home()))):
        if not candidate:
            continue
        real = os.path.realpath(candidate)
        domain = file_provider_domain(real)
        if domain is not None:
            skipped.append((source, domain))
            continue
        try:
            fx.safe_ancestors(real + "/x", os.geteuid())
        except Exception:
            continue
        if skipped and TEMP_PARENT["source"] is None:
            sys.stderr.write("kit: temp parent(s) %s skipped: inside a macOS File Provider domain; using %s\n"
                             % (", ".join("%s (%s)" % row for row in skipped), source))
        TEMP_PARENT.update(source=source, file_provider_candidates_skipped=len(skipped))
        return real
    raise SystemExit("NO_SAFE_TEMP_PARENT")


def network_of(cls):
    return {"NONE": "none", "PROVIDER": "bridge", "DATABASE": "c3po_default", "DATABASE_AND_PROVIDER": "c3po_default"}[cls]


class Env:
    def __init__(self):
        rt.owner_time_guard = owner_time_guard_except_fixtures
        base = tempfile.mkdtemp(prefix="l12v3-", dir=safe_temp_parent())
        self.base = Path(os.path.realpath(base))
        os.chmod(self.base, 0o700)
        self.clock = JumpClock()
        self.now0 = datetime.now(timezone.utc)
        self.t_sign = past_signature_instant(self.now0)
        self.probe = FakeProbe()
        self.bin = self.mk("bin")
        for name, source in (("docker", FAKE_DOCKER), ("systemd-run", FAKE_SYSTEMD_RUN), ("systemctl", FAKE_SYSTEMCTL)):
            path = self.bin / name
            path.write_text("#!" + PY + " -I\n" + source)
            os.chmod(path, 0o700)
        self.set_fake({})
        self.warm()
        self.secrets = self.mk("secrets")
        self.env_file = self.secrets / "provider.env"
        self.env_file.write_text("C3PO_EODHD_API_TOKEN=" + CANARY + "\n")
        os.chmod(self.env_file, 0o600)
        (self.secrets / "risk-db.env").write_text("C3PO_FIXTURE_ONLY=1\n")
        os.chmod(self.secrets / "risk-db.env", 0o600)
        self.mk("secrets/emitter")
        self.veto = self.mk("veto")
        self.dockercfg = self.mk("docker-cli")
        self.tools = self.mk("k9/tools")
        self.daydir = self.mk("k9/day")
        self.receipts = self.mk("k9/day/receipts")
        self.mk("k9/day/plans")
        self.source = self.mk("source")
        self.docs = self.mk("docs")
        (self.tools / ("k9_runner04-%s.py" % RUNNER_SHA)).write_bytes(RUNNER_RAW)
        self.layout = {"schema": rt.LAYOUT_SCHEMA, "root": str(self.base / "l12root"), "veto_dir": str(self.veto),
                       "unit_prefix": "l12h-e04-", "unit_name_suffix": "-e04", "python": PY,
                       "binaries": {"docker": str(self.bin / "docker"), "systemd_run": str(self.bin / "systemd-run"),
                                    "systemctl": str(self.bin / "systemctl")}, "docker_config": str(self.dockercfg)}
        self.stage = self.mk("stage")
        fam = self.stage / "l12host"
        for name in FAMILY_FILES:
            raw = (FAMILY / name).read_bytes()
            (fam / name).parent.mkdir(parents=True, exist_ok=True)
            (fam / name).write_bytes(raw)
        (fam / "SHA256SUMS").write_bytes(family_sums())
        self.layout_path = self.base / "layout.json"
        self.layout_path.write_bytes(rt.canonical(self.layout))
        self.assets = self.mk("assets")
        self.mk("assets/k9")
        for p in ASSETS.glob("*.py"):
            (self.assets / p.name).write_bytes(p.read_bytes())
        self.k9_request = self.assets / "k9" / "K9_04_STEP_SET_REQUEST.json"
        self.k9_request.write_bytes(canonical({"schema": "K9_04_STEP_SET_REQUEST_V1", "synthetic": True,
                                               "image": {"id": IMAGE, "revision": LIT["REVISION"],
                                                         "package_sha256": LIT["PACKAGE"]}}))
        self.k9_go = self.assets / "k9" / "K9_GO_04.json"
        self.k9_go.write_bytes(canonical({"schema": "K9_04_SYNTHETIC_GO_NOT_AN_AUTHORIZATION"}))
        self.timers = []
        self.outputs = []
        self.shells = []
        self.patched = []
        self.nb = self.t_sign + timedelta(minutes=2)
        self.na = self.now0 + timedelta(hours=3)

    def mk(self, rel):
        path = self.base / rel
        path.mkdir(mode=0o700, parents=True)
        os.chmod(path, 0o700)
        return path

    def warm(self):
        """S7: run every fake binary once BEFORE any measurement (macOS adds com.apple.provenance on the first run of
        a new script, which changes its ctime and would read as BINARY_CHANGED)."""
        for name in ("docker", "systemd-run", "systemctl"):
            subprocess.run([str(self.bin / name), "--warm"], capture_output=True, timeout=30, check=True)

    def set_fake(self, cfg):
        (self.bin / "fake.json").write_text(json.dumps(cfg))

    def update_fake(self, **cfg):
        current = json.loads((self.bin / "fake.json").read_text())
        current.update(cfg)
        self.set_fake(current)

    def log(self, tool=None):
        path = self.bin / "log.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if tool is None or r["tool"] == tool]

    # ---------------------------------------------------------- W + prepare + measure
    def prepare(self):
        s = self.t_sign
        bind.w_request(str(self.stage / "l12host"), str(self.layout_path), z(s - timedelta(minutes=40)),
                       z(s + timedelta(minutes=30)), str(self.stage))
        bind.owner(str(self.stage), z(s - timedelta(minutes=2)), z(s - timedelta(minutes=1)), w=True)
        self.clock.jump(s + timedelta(minutes=1))
        out = inst.prepare(str(self.stage), require_root=False, clock=self.clock, physical=False)
        self.clock.real()
        assert out["status"] == "PREPARED_NO_TIMER", out
        self.runtime_raw = rt.canonical(rt.measure(self.layout, self.probe, datetime.now(timezone.utc), MODE))
        self.runtime_path = self.base / "runtime.json"
        self.runtime_path.write_bytes(self.runtime_raw)
        return out

    # ---------------------------------------------------------- K9 plans and rows (fixed shape)
    def k9_plan(self, op, at, budget, *, run_not_after=None, core=None, lot="UP"):
        phase, network, attached = LIT["OPS"][op]
        constants = {"package_sha256": LIT["PACKAGE"], "code_revision": LIT["REVISION"], "act_b_sha256": "33" * 32,
                     "release_sha256": "44" * 32, "policy_sha256": "55" * 32, "runner_sha256": RUNNER_SHA,
                     "risk_source_pins_sha256": "66" * 32, "risk_limits": LIT["LIMITS"], "disk_floor_bytes": LIT["FLOOR"]}
        key = sha(json.dumps([EPOCH, DAY, phase, op], separators=(",", ":"), ensure_ascii=True).encode("ascii"))
        plan = {"schema": "K9_STEP_PLAN_V1", "epoch": EPOCH, "day": DAY, "k9_phase": phase, "k9_operation": op,
                "slot": "PRIMARY", "attempt_key": key, "request_sha256": sha(self.k9_request.read_bytes()),
                "go_sha256": sha(self.k9_go.read_bytes()),
                "run_not_after": plus(run_not_after or (self.na + timedelta(hours=1))), "constants": constants,
                "network_class": network, "database": LIT["DB"] if op in ("commit_launch", "publish_launch") else None,
                "risk": None, "step_row": {"operation": op, "lot": lot, "core_operation": core,
                                           "mode": "ATTACHED" if attached else "LAUNCH", "starts_at": plus(at),
                                           "budget_seconds": budget}}
        raw = canonical(plan)
        (self.assets / "k9" / (op + ".json")).write_bytes(raw)
        target = self.daydir / "plans" / (op + ".json")
        if target.exists():
            os.chmod(target, 0o600)
            target.unlink()
        target.write_bytes(raw)
        return plan, raw

    def k9_files(self, ops):
        files = {"ext/k9_runner04.py": str(FAMILY / "lots" / "k9tools" / "k9_runner04.py"),
                 "k9/K9_04_STEP_SET_REQUEST.json": str(self.k9_request), "k9/K9_GO_04.json": str(self.k9_go)}
        for op in ops:
            files["k9/%s.json" % op] = str(self.assets / "k9" / (op + ".json"))
        return files

    def k9_section(self, ops):
        return {"runner_source": "ext/k9_runner04.py", "request": "k9/K9_04_STEP_SET_REQUEST.json",
                "go": "k9/K9_GO_04.json", "plans": {op: "k9/%s.json" % op for op in ops},
                "networks": {"PROVIDER": "bridge", "DATABASE": "c3po_default", "DATABASE_AND_PROVIDER": "c3po_default"},
                "secrets_root": str(self.secrets)}

    def k9_row(self, op, timeout):
        plan_sha = sha((self.assets / "k9" / (op + ".json")).read_bytes())
        cls = LIT["OPS"][op][1]
        env_files = {"PROVIDER": [str(self.env_file)], "DATABASE_AND_PROVIDER": [str(self.env_file),
                                                                                 str(self.secrets / "risk-db.env")]}.get(cls, [])
        mounts = [{"source": str(self.tools), "target": rt.K9_TOOLS_TARGET, "readonly": True},
                  {"source": str(self.daydir), "target": rt.K9_DAY_TARGET, "readonly": False}]
        if cls == "DATABASE":
            mounts.append({"source": str(self.secrets / "emitter"), "target": rt.K9_EMITTER_TARGET, "readonly": True})
        return {"kind": "CONTAINER", "docker": {
            "name": rt.K9_CONTAINER_PREFIX + op.replace("_", "-"), "labels": [["c3po.k9.operation", op]],
            "network": network_of(cls), "env_files": env_files,
            "env": [["C3PO_R2D2_V2_PRODUCERS_ENABLED", "true"], ["C3PO_BUILD_SHA", LIT["REVISION"]]],
            "mounts": mounts, "tmpfs": False, "workdir": None, "image_id": IMAGE,
            "command": ["python", "-I", rt.K9_TOOLS_TARGET + "/k9_runner04-%s.py" % RUNNER_SHA, "--plan",
                        rt.K9_DAY_TARGET + "/plans/%s.json" % op, "--plan-sha256", plan_sha],
            "timeout_seconds": timeout},
            "receipt": {"source": "FILE", "path": str(self.receipts / (op + ".RECEIPT.json"))}}

    def k9_decoder(self, op, row, nb=None, na=None):
        return {"kind": "K9_STEP_V1", "mode": "FIXTURE", "runner_source": "ext/k9_runner04.py",
                "step_plan": "k9/%s.json" % op, "k9_request": "k9/K9_04_STEP_SET_REQUEST.json", "k9_go": "k9/K9_GO_04.json",
                "provenance_binding_sha256": sha(canonical(row)), "phase_not_before": z(nb or self.nb),
                "phase_not_after": z(na or self.na), "verifiers": {"approval": "k9_approval", "original": "k9_original"}}

    def k9_receipt_content(self, op, *, status="COMPLETE", attempt_key=None):
        raw = (self.assets / "k9" / (op + ".json")).read_bytes()
        plan = json.loads(raw)
        counts, outputs = {"symbols_total": 3}, {"day/%s/out.json" % op.replace("_launch", ""): "77" * 32}
        if op == "prove_launch":
            counts = {"eligible_symbols": 5000, "present_symbols": 4900, "absent_symbols": 100, "usable_symbols": 4800,
                      "conflicting_symbols": 10, "bulk_rows": 45000, "dated_rows": 4900, "required_minimum": 4750,
                      "presence_pass": 1, "logical_fetch_calls": 2}
            outputs = {"day/prove/bulk_presence.json": "78" * 32}
        doc = {"schema": "K9_STEP_RECEIPT_V1", "status": status, "code": None, "epoch": EPOCH, "day": DAY,
               "phase": plan["k9_phase"], "operation": op, "attempt_key": attempt_key or plan["attempt_key"],
               "step_plan_sha256": sha(raw), "started_at": "@NOW@", "completed_at": "@NOW@",
               "package_sha256": LIT["PACKAGE"], "build_sha": LIT["REVISION"], "outputs": outputs, "aggregates": {},
               "counts": counts}
        return canonical(doc).decode("ascii")

    def common_external(self):
        return {"k9_approval": {"file": "ext/fx_verifier.py", "identity": "accept"},
                "k9_original": {"file": "ext/fx_verifier.py", "identity": "accept"},
                "ok": {"file": "ext/fx_verifier.py", "identity": "accept"},
                "no": {"file": "ext/fx_verifier.py", "identity": "refuse"},
                "fx_decode": {"file": "ext/fx_decoder.py", "identity": "decode"}}

    def common_files(self):
        return {"ext/fx_verifier.py": str(self.assets / "fx_verifier.py"),
                "ext/fx_decoder.py": str(self.assets / "fx_decoder.py")}

    def external_decoder(self, verifier="ok"):
        return {"kind": "EXTERNAL_V1", "decoder": "fx_decode", "verifier": verifier}

    def fixture_receipt(self, role):
        return rt.canonical({"schema": "FIXTURE_STEP_RECEIPT_V1", "role": role, "status": "COMPLETE",
                             "completed_at": "@NOW@"}).decode("ascii")

    # ---------------------------------------------------------- lot specs
    def schedule(self, n, gap):
        """n allowed instants, the first >= signature + 10 min, each >= previous + gap."""
        out, t = [], allowed_after(self.t_sign + timedelta(minutes=10))
        for _ in range(n):
            out.append(t)
            t = allowed_after(t, gap)
        return out

    def task(self, op, slots, requires, effect, decoder, budget=60):
        return {"operation": op, "not_before": z(self.nb), "not_after": z(self.na), "budget_seconds": budget,
                "requires": list(requires), "slots": [{"slot": s, "at": z(at)} for s, at in slots],
                "effect": effect, "decoder": decoder, "image_go_sha256": None, "image_proposal_sha256": None}

    def spec(self, lot, lane, tasks, *, files=None, external=None, initial=None, imports=None, extended=None, k9=None,
             capacity=None, gate=None, ready=None, veto_age=10):
        f, e = self.common_files(), self.common_external()
        f.update(files or {})
        e.update(external or {})
        return {"schema": bind.SPEC_SCHEMA, "lot": lot, "lane": lane, "mode": "FIXTURE",
                "owner_deadline": z(self.t_sign + timedelta(minutes=1)), "decision_sha256": D1,
                "veto_max_age_seconds": veto_age, "initial_receipts": initial or {}, "imports": imports or {},
                "files": f, "external": e, "k9": k9, "tasks": tasks, "extended": extended, "bootstrap": None,
                "gate": gate, "capacity": capacity, "ready": ready, "j4": None}

    def ext_step(self, name, at, ceiling, timeout):
        op = STEP_RUNNER[name]
        self.k9_plan(op, at, ceiling)
        row = self.k9_row(op, timeout)
        return {"step": name, "not_before": z(self.nb), "not_after": z(self.na), "ceiling_seconds": ceiling,
                "requires": [list(r) for r in rt.EXTENDED_TABLE["UPSTREAM_P"][name][2]], "effect": row,
                "decoder": {"kind": "K9_EXT_STEP_V3", "verifier": "ok"}, "pre_effect": None, "hold_until": None,
                "slots": [{"slot": "X%d" % (list(STEP_RUNNER).index(name) + 1), "at": z(at)}]}

    def up_spec(self, *, extended=True, steps=("components", "sources", "bind", "preflight", "acquire", "execute", "stage"),
                prove_verifier="ok", ceilings=None):
        times = self.schedule(4 + (len(steps) if extended else 0), 155)
        self.up_times = times
        tasks, ops = [], []
        requires = {"prove": [], "collect": ["prove"], "commit_result": ["collect"], "publish_launch": ["commit_result"]}
        for i, core in enumerate(("prove", "collect", "commit_result", "publish_launch")):
            op = CORE_RUNNER[core]
            ops.append(op)
            self.k9_plan(op, times[i], CORE_K9_BUDGET, core=core)
            row = self.k9_row(op, 25)
            dec = self.k9_decoder(op, row)
            if core == "prove":
                dec["verifiers"]["original"] = "k9_original" if prove_verifier == "ok" else prove_verifier
            tasks.append(self.task(core, [("P%d" % (i + 1), times[i])], requires[core], row, dec, budget=CORE_K9_BUDGET))
        ext = None
        if extended:
            ceilings = ceilings or {}
            rows = []
            for j, name in enumerate(steps):
                ceiling = ceilings.get(name, 90)
                rows.append(self.ext_step(name, times[4 + j], ceiling, ceiling - EXT_KILL_MARGIN))
                ops.append(STEP_RUNNER[name])
            ext = {"steps": rows}
        return self.spec("UP", "UPSTREAM_P", tasks, files=self.k9_files(ops), extended=ext, k9=self.k9_section(ops))

    def up_fakes(self, ops=None):
        cfg = {}
        for op in ops or list(CORE_RUNNER.values()) + list(STEP_RUNNER.values()):
            if (self.assets / "k9" / (op + ".json")).exists():
                cfg[rt.K9_CONTAINER_PREFIX + op.replace("_", "-")] = {
                    "writes": [{"path": str(self.receipts / (op + ".RECEIPT.json")), "content": self.k9_receipt_content(op)}]}
        self.update_fake(**cfg)

    def make_lot(self, spec, *, prepared, published, signed, bound_at):
        out = self.stage / ("lot-" + spec["lot"])
        spec_path = self.base / ("spec-%s.json" % spec["lot"])
        spec_path.write_text(json.dumps(spec))
        bind.lot(str(spec_path), str(self.layout_path), str(self.runtime_path), z(prepared), str(out))
        bind.owner(str(out), z(published), z(signed))
        bind.bound(str(out), z(bound_at))
        return sha((out / "bound.json").read_bytes())

    def signed_lot(self, spec):
        s = self.t_sign
        return self.make_lot(spec, prepared=s - timedelta(minutes=30), published=s - timedelta(minutes=1), signed=s,
                             bound_at=s + timedelta(seconds=30))

    def preview(self, command, argv):
        """In-process stand-in of the INSTALLED runtime subprocess (non-physical, FakeProbe). The real subprocess
        route is exercised on Linux as root by linux_systemd_proof.py."""
        args = dict(zip(argv[6::2], argv[7::2]))
        try:
            if command == "preview-stage":
                record = rt.preview_stage(args["--stage-lot"], args["--lot"], physical=False, probe=self.probe)
            elif command == "preview":
                record = rt.preview_installed(args["--lot-dir"], physical=False, probe=self.probe)
            else:
                record = rt.derived_check(args["--lot-dir"], args.get("--derived-file"), installed="--installed" in argv,
                                          physical=False, probe=self.probe)
            return 0, canonical(record)
        except BaseException as error:
            return 3, canonical(rt.preview_record(command, "PREVIEW_REFUSED", rt.safe_code(error)))

    def install(self, lot, bound_sha, at=None, preview=None):
        self.clock.jump(at or (self.t_sign + timedelta(minutes=3)))
        try:
            return inst.install(str(self.stage), lot, bound_sha, require_root=False, probe=self.probe, clock=self.clock,
                                runner=lambda argv: (self.timers.append(argv), 0)[1], mode=MODE, physical=False,
                                preview=preview or self.preview)
        finally:
            self.clock.real()

    def install_spec(self, spec):
        result = self.install(spec["lot"], self.signed_lot(spec))
        assert "code" not in result, result
        return result

    def lot_dir(self, lot):
        return self.layout["root"] + "/lots/" + lot

    def authority(self, lot):
        return json.loads(Path(self.lot_dir(lot), "authority.json").read_bytes())

    def slot_at(self, lot, slot):
        return rt.stamp([s for s in self.authority(lot)["slots"] if s["slot"] == slot][0]["at"])

    def shell(self, lot_dir, slot_at, probe=None, minute_rule=False):
        shell = rt.Shell(lot_dir, probe=probe or self.probe, physical=False, slot_clock=lambda: slot_at)
        if not minute_rule:
            # The real wall minute is not under test here (its own tests patch nothing). Restored after the run so
            # the pinned module copy left in sys.modules never weakens a later validation in this process.
            self.patched.append((shell.fam.fx, "start_minute_violation", shell.fam.fx.start_minute_violation))
            shell.fam.fx.start_minute_violation = lambda at: None
        self.shells.append(shell)
        return shell

    def run(self, lot, slot, probe=None, minute_rule=False, at=None):
        captured = []
        slot_at = at or self.slot_at(lot, slot)
        self.patched = []
        try:
            code = rt.main(["run", "--lot-dir", self.lot_dir(lot), "--slot", slot],
                           shell_factory=lambda d: self.shell(d, slot_at, probe, minute_rule), emit=captured.append)
        finally:
            for owner, name, value in reversed(self.patched):
                setattr(owner, name, value)
            self.patched = []
        self.outputs.extend(captured)
        return code, json.loads(captured[0])

    def ledger_rows(self):
        raw = (Path(self.layout["root"]) / "ledger" / rt.LEDGER_FILE).read_bytes()
        return [json.loads(l) for l in raw.splitlines()]

    def ledger_raw(self):
        return (Path(self.layout["root"]) / "ledger" / rt.LEDGER_FILE).read_bytes()

    def key(self, op, track="P"):
        return sha(canonical([EPOCH, DAY, PREVIOUS, track, op]))

    def xkey(self, step):
        return sha(canonical([EPOCH, DAY, PREVIOUS, "P", "EXTENDED", step]))

    def cleanup(self):
        rt.owner_time_guard = REAL_OWNER_TIME_GUARD
        FIXTURE_SIGNED_AT.clear()
        for dirpath, dirnames, filenames in os.walk(self.base):
            for d in dirnames:
                try:
                    os.chmod(os.path.join(dirpath, d), 0o700)
                except OSError:
                    pass
            for f in filenames:
                p = os.path.join(dirpath, f)
                if not os.path.islink(p):
                    try:
                        os.chmod(p, 0o600)
                    except OSError:
                        pass
        shutil.rmtree(self.base, ignore_errors=True)


# ====================================================================== units copied from the reviewed references
def config_dir(env):
    for rel in ("cfg", "cfg/launcher", "cfg/supervisor", "data", "journal", "capacity", "state"):
        if not (env.base / rel).exists():
            env.mk(rel)
    for leaf in ("secret.env", "pins.env", "activation.env"):
        path = env.base / "cfg" / leaf
        if not path.exists():
            path.write_text("C3PO_FIXTURE_ONLY=1\n")
            os.chmod(path, 0o600)
    return str(env.base / "cfg")


def reader_row(env):
    cfg_dir = config_dir(env)
    subst = {"@HOST_DATA_ROOT@": str(env.base / "data"), "@HOST_JOURNAL_ROOT@": str(env.base / "journal"),
             "@HOST_CAPACITY_ROOT@": str(env.base / "capacity"), "@HOST_CONFIG_DIR@": cfg_dir,
             "@IMAGE_ID@": IMAGE, "@NETWORK@": "c3po_default", "@CONTAINER_JOURNAL_ROOT@": "/var/lib/c3po-bar/journal-e04"}
    docker = env.layout["binaries"]["docker"]
    renames = [("c3po-reader", rt.READER_NAME), ("/usr/bin/docker", docker), ("-/usr/bin/docker", "-" + docker),
               ("DOCKER_CONFIG=" + cfg_dir + "/docker-cli", "DOCKER_CONFIG=" + str(env.dockercfg))]
    return bind.unit_row(str(FAMILY / "reference" / "c3po-reader.service"), subst, rt.READER_NAME, "SESSION_READER",
                         env.layout, renames)


def supervisor_row(env):
    cfg_dir = config_dir(env) + "/supervisor"     # v3.1: never the reader's folder (it holds secret.env)
    subst = {"@HOST_JOURNAL_ROOT@": str(env.base / "journal"), "@HOST_STATE_ROOT@": str(env.base / "state"),
             "@HOST_CONFIG_DIR@": cfg_dir, "@IMAGE_ID@": IMAGE, "@NETWORK@": "c3po_default",
             "@CONTAINER_JOURNAL_ROOT@": "/var/lib/c3po-bar/journal-e04"}
    docker = env.layout["binaries"]["docker"]
    renames = [("c3po-massive", rt.SUPERVISOR_NAME), ("/usr/bin/docker", docker), ("-/usr/bin/docker", "-" + docker),
               ("DOCKER_CONFIG=" + cfg_dir + "/docker-cli", "DOCKER_CONFIG=" + str(env.dockercfg))]
    return bind.unit_row(str(FAMILY / "reference" / "c3po-massive.service"), subst, rt.SUPERVISOR_NAME, "SUPERVISOR",
                         env.layout, renames)


# ====================================================================== DOWN (after UP COMPLETE, real time)
def capacity_section(env):
    return {"mode": "FIXTURE", "lots": {"m3": "BOOT", "j": "DOWN", "activation": "CAP"},
            "sources": {"m3": sha((env.assets / "fx_program.py").read_bytes()),
                        "j": sha((env.assets / "fx_j_program.py").read_bytes()),
                        "activation": sha((env.assets / "fx_program.py").read_bytes())},
            "verifiers": {"rule": "ok", "original": "ok", "config": "ok"},
            "config_path": str(env.docs / "final-config.json")}


def gate_section(env, session_open="2026-10-12T13:30:00Z"):
    rule = env.assets / "bounded_rule.json"
    rule.write_bytes(canonical({"synthetic": "BOUNDED_READBACK_RULE_PLACEHOLDER"}))
    return {"scope": {"build_sha": LIT["REVISION"], "image_id": IMAGE, "document_order_sha256": "70" * 32,
                      "release_sha256": "44" * 32, "package_sha256": LIT["PACKAGE"], "calendar_pin_sha256": "c1" * 32,
                      "runtime_authority_sha256": "d1" * 32, "owner_uid": 0, "manifest_directory": str(env.docs),
                      "session_open": session_open, "not_before": "2026-10-12T12:30:00Z",
                      "not_after": "2026-10-12T13:20:00Z", "view_opens_at": "2026-10-12T12:31:00Z",
                      "require_go_mode": "INDIVIDUAL"},
            "journal_directory": "/var/lib/c3po-bar/journal-e04", "snapshot_reader": "ok", "snapshot_verifier": "ok",
            "readback": {"rule": "docs/bounded_rule.json", "rule_verifier": "ok", "readback_verifier": "ok"}}


def down_spec(env, *, j_slots=("J1",), up_lot="UP", capacity=None, session=False, hold_seconds=60,
              e6_docs=None, ready_wait=30, ready_check=False):
    """DOWN lot prepared AFTER the UP originals exist (the core requires initial receipts COMPLETE before the
    REQUEST). Times: prepared/published/signed/bound a few seconds after real now; tasks open right after."""
    up_req = sha(Path(env.lot_dir(up_lot), "request.json").read_bytes())
    up_bound = sha(Path(env.lot_dir(up_lot), "bound.json").read_bytes())
    up_auth = json.loads(Path(env.lot_dir(up_lot), "authority.json").read_bytes())
    initial = {}
    for role in ("commit_result", "publish_launch"):
        envelope = json.loads(Path(env.layout["root"], "receipts", env.key(role) + ".json").read_bytes())
        initial[role] = envelope["original_sha256"]
    t0 = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=1)
    env.down_t0 = t0
    docs = e6_docs or []
    if not docs:
        for i in range(2):
            p = env.docs / ("e6_%d.json" % i)
            p.write_bytes(canonical({"synthetic_e6_document": i}))
            os.chmod(p, 0o600)
            docs.append(p)
    e6_row = {"kind": "READBACK", "files": [{"path": str(p), "sha256": sha(p.read_bytes()), "mode": 0o600,
                                             "uid": os.geteuid()} for p in docs]}
    e6_at = allowed_after(t0 + timedelta(minutes=20))
    j_times, t = [], allowed_after(e6_at, 60 + 60 + 31)
    for _ in j_slots:
        j_times.append(t)
        t = allowed_after(t, 35)
    nb, na = t0 + timedelta(seconds=6), t0 + timedelta(hours=3)
    task = lambda op, slots, req, eff, dec, budget=60: {
        "operation": op, "not_before": z(nb), "not_after": z(na), "budget_seconds": budget, "requires": req,
        "slots": [{"slot": s, "at": z(a)} for s, a in slots], "effect": eff, "decoder": dec,
        "image_go_sha256": None, "image_proposal_sha256": None}
    j_end = j_times[-1] + timedelta(seconds=60 + 60)
    post_at = allowed_after(j_end + timedelta(seconds=31))
    up_steps = [s["step"] for s in (up_auth["extended"] or {}).get("steps", [])]
    tasks = [task("e6", [("E6", e6_at)], ["commit_result", "publish_launch"], e6_row, {"kind": "READBACK_V3"}),
             task("admission_manifest", list(zip(j_slots, j_times)), ["e6"],
                  {"kind": "HOST_PROGRAM", "source": "ext/fx_j_program.py",
                   "argv": ["--registry-record-base64", rt.J4_REGISTRY_TOKEN, "--mode", "FIXTURE"]},
                  {"kind": "HOT_J_V1", "verifier": "ok"}),
             task("post", [("PO", post_at)], ["publish_launch"],
                  {"kind": "CHAIN_READBACK", "source_lot": up_lot, "source_request_sha256": up_req,
                   "source_bound_sha256": up_bound, "steps": up_steps}, {"kind": "CHAIN_READBACK_V3"})]
    files = {"ext/fx_j_program.py": str(env.assets / "fx_j_program.py")}
    extended = ready = gate = None
    if session:
        sup, _, _ = supervisor_row(env)
        rdr, _, _ = reader_row(env)
        s_at = allowed_after(post_at + timedelta(seconds=121))
        env.ready_path = env.base / "journal" / "ready.json"
        ready = {"mode": "FIXTURE", "calendar_sha256": "c1" * 32, "not_before": z(nb), "not_after": z(na - timedelta(minutes=5)),
                 "max_wait_seconds": ready_wait, "poll_seconds": 0.2, "ready_path": str(env.ready_path),
                 "verifiers": {"rule": "ok", "ready": "ok"}}
        # v3.1 (finding 6): the step window starts exactly at the signed open - 90 s (the fixture's open is today)
        gate = gate_section(env, session_open=z(nb + timedelta(seconds=90)))
        files["docs/bounded_rule.json"] = str(env.assets / "bounded_rule.json")
        capacity = capacity or capacity_section(env)
        extended = {"steps": [{"step": "session_start", "not_before": z(nb), "not_after": z(na), "ceiling_seconds": 420,
                               "requires": [["core", "admission_manifest"], ["core", "post"]], "effect": rdr,
                               "decoder": {"kind": "SESSION_START_V3", "verifier": "ok"}, "pre_effect": sup,
                               "hold_until": z(t0 + timedelta(seconds=hold_seconds)),
                               "slots": [{"slot": "S1", "at": z(s_at)}]}]}
        if ready_check:
            env.r0_at = allowed_after(s_at + timedelta(seconds=31))
            extended["steps"].insert(0, {"step": "ready_check", "not_before": z(nb), "not_after": z(na),
                                         "ceiling_seconds": 60, "requires": [], "effect": None,
                                         "decoder": {"kind": "READY_ABSENT_V3"}, "pre_effect": None, "hold_until": None,
                                         "slots": [{"slot": "R0", "at": z(env.r0_at)}]})
    spec = env.spec("DOWN", "DOWNSTREAM_AFTER_E6", tasks, files=files, initial=initial, capacity=capacity,
                    imports={r: {"source_lot": up_lot, "request_sha256": up_req, "bound_sha256": up_bound}
                             for r in initial}, extended=extended, ready=ready, gate=gate)
    spec["owner_deadline"] = z(t0 + timedelta(seconds=4))
    j4dir = env.base / "j4"
    if not j4dir.exists():
        env.mk("j4")
        for name in rt.J4_PROGRAMS:
            if name not in ("hot_worker", "finite_batch"):
                (j4dir / (name + ".py")).write_bytes(("# SYNTHETIC J4 program placeholder %s\n" % name).encode())
        (j4dir / "finite_batch.py").write_bytes((FAMILY / "vendor" / "finite_batch.py").read_bytes())
        for name in set(rt.J4_ORIGINALS) - set(rt.J4_LOT_ORIGINALS):
            (j4dir / (name + ".orig")).write_bytes(canonical({"synthetic_j4_original": name}))
    hot = sha((env.assets / "fx_j_program.py").read_bytes())
    spec["j4"] = {"protocol": "WARM_IMAGE10_ACTUAL_OBSERVATION", "hot_worker_source": "ext/fx_j_program.py",
                  "programs": {n: (hot if n == "hot_worker" else sha((j4dir / (n + ".py")).read_bytes())) for n in rt.J4_PROGRAMS},
                  "originals": {n: sha((j4dir / (n + ".orig")).read_bytes())
                                for n in set(rt.J4_ORIGINALS) - set(rt.J4_LOT_ORIGINALS)},
                  "bridge": {"bootstrap": "bootstrap", "authorize": "authorize", "general_read": "general_read",
                             "general_verify": "general_verify"},
                  "general_authority_sha256": "c1" * 32, "general_source_identity": "SYNTHETIC_GENERAL_SOURCE"}
    return spec


def j4_registry(env, lot="DOWN"):
    """The DERIVED J4 registry of an installed DOWN lot (what Fable derives Sunday after BOUND)."""
    lot_dir = env.lot_dir(lot)
    authority = json.loads(Path(lot_dir, "authority.json").read_bytes())
    request = json.loads(Path(lot_dir, "request.json").read_bytes())
    runtime = json.loads(Path(lot_dir, "runtime.json").read_bytes())
    task = [t for t in request["tasks"] if t["operation"] == "admission_manifest"][0]
    e = runtime["election"]
    pins = [[[n, r] for n, r in e["root_chain"]] + [[env.layout["root"] + "/ledger", e["children"]["ledger"]]], e["ledger_file"]]
    programs = {n: rt.file_record(lot_dir + "/ext/fx_j_program.py" if n == "hot_worker" else str(env.base / "j4" / (n + ".py")))
                for n in rt.J4_PROGRAMS}
    originals = {n: rt.file_record(lot_dir + "/" + rt.J4_LOT_ORIGINALS[n] if n in rt.J4_LOT_ORIGINALS
                                   else str(env.base / "j4" / (n + ".orig"))) for n in rt.J4_ORIGINALS}
    j4 = authority["j4"]
    return canonical({"schema": "R2D2_HOT_IMAGE10_REGISTRY_CANDIDATE_V1", "mode": authority["mode"], "protocol": j4["protocol"],
                      "epoch": request["epoch"], "day": request["session"], "programs": programs, "originals": originals,
                      "bridge": j4["bridge"], "ledger": {"root": env.layout["root"] + "/ledger", "pins": pins},
                      "outer_scope": [request["epoch"], request["session"], request["previous_session"], request["track"],
                                      "admission_manifest"],
                      "authority_sha256": request["authority_sha256"], "general_authority_sha256": j4["general_authority_sha256"],
                      "general_source_identity": j4["general_source_identity"], "not_before": task["not_before"],
                      "not_after": task["not_after"]})


def install_j4_registry(env, raw=None, lot="DOWN"):
    path = env.base / ("derived-%s.json" % lot)
    if path.exists():
        path.unlink()
    path.write_bytes(raw if raw is not None else j4_registry(env, lot))
    return inst.install_derived(str(env.layout_path), lot, str(path), require_root=False, preview=env.preview)


def sign_down(env, spec):
    """Owner-time guard: tests may run at any wall hour, so the DOWN signature at real now+3 s is recorded with the
    07:00-21:45 BRT guard bypassed ONLY in this in-process fixture (the guard has its own dedicated tests); v3.2: the
    signature is registered (fixture_signed_at) so the runtime's later re-validations exempt it too."""
    t0 = env.down_t0
    saved = rt.owner_time_guard
    rt.owner_time_guard = lambda *a, **k: None
    try:
        bound = env.make_lot(spec, prepared=t0, published=t0 + timedelta(seconds=1), signed=fixture_signed_at(env),
                             bound_at=t0 + timedelta(seconds=4))
        wait_until(t0 + timedelta(seconds=5))
        result = env.install("DOWN", bound, at=datetime.now(timezone.utc))
        if "code" not in result:
            result["derived"] = install_j4_registry(env)
    finally:
        rt.owner_time_guard = saved
    return bound, result


def wait_until(t):
    import time as _time
    while datetime.now(timezone.utc) < t:
        _time.sleep(0.1)


# ====================================================================== Monday lanes (fail-closed wiring on a 09/10 clock)
MONDAY = datetime(2026, 10, 12, 9, 26, tzinfo=timezone.utc)


def monday_lot(env, lot, lane, ops, *, capacity=None, base=MONDAY):
    """BOOTSTRAP_MONDAY / CAPACITY_MONDAY lot on 12/10 windows, signed Sunday 11/10 18:00 BRT (synthetic)."""
    signed = datetime(2026, 10, 11, 21, 0, tzinfo=timezone.utc)
    files, tasks = {"ext/fx_program.py": str(env.assets / "fx_program.py")}, []
    boot = lane == "BOOTSTRAP_MONDAY"
    image_go = {}
    t = base
    for i, op in enumerate(ops):
        go = env.assets / ("go_%s.json" % op)
        prop = env.assets / ("proposal_%s.json" % op)
        go.write_bytes(canonical({"synthetic_go": op}))
        prop.write_bytes(canonical({"synthetic_proposal": op}))
        nb = t + timedelta(minutes=12 * i)
        task = {"operation": op, "not_before": z(nb - timedelta(minutes=1)), "not_after": z(nb + timedelta(minutes=10)),
                "budget_seconds": 300, "requires": [],
                "slots": [{"slot": "M%d" % (i + 1), "at": z(nb)}],
                "effect": {"kind": "HOST_PROGRAM", "source": "ext/fx_program.py", "argv": ["--role", op]},
                "decoder": env.external_decoder(), "image_go_sha256": sha(go.read_bytes()) if boot else None,
                "image_proposal_sha256": sha(prop.read_bytes()) if boot else None}
        tasks.append(task)
        if boot:
            files["image_go/go_%s.json" % op] = str(go)
            files["image_go/proposal_%s.json" % op] = str(prop)
            image_go[op] = {"go": "image_go/go_%s.json" % op, "proposal": "image_go/proposal_%s.json" % op, "documents": []}
    if boot:
        deps = {"install_release": ["epoch_pre"], "readback": ["install_release"],
                "activate": ["epoch_pre", "install_release", "readback"]}
        for task in tasks:
            task["requires"] = deps[task["operation"]]
        pre = env.assets / "epoch_pre.json"
        pre.write_bytes(canonical({"schema": "FIXTURE_STEP_RECEIPT_V1", "role": "epoch_pre", "status": "COMPLETE",
                                   "completed_at": z(signed - timedelta(hours=3))}))
        files["docs/epoch_pre.json"] = str(pre)
    spec = env.spec(lot, lane, tasks, files=files, capacity=capacity,
                    initial={"epoch_pre": sha((env.assets / "epoch_pre.json").read_bytes())} if boot else {},
                    imports={"epoch_pre": {"external_file": "docs/epoch_pre.json", "decoder": env.external_decoder()}} if boot else {})
    spec["owner_deadline"] = "2026-10-12T00:45:00Z"
    if boot:
        spec["bootstrap"] = {"image_go": image_go, "image_go_verifier": "ok"}
    bound = env.make_lot(spec, prepared=signed - timedelta(hours=2), published=signed - timedelta(minutes=1),
                         signed=signed, bound_at=signed + timedelta(minutes=1))
    result = env.install(lot, bound, at=signed + timedelta(minutes=5))
    return spec, result
