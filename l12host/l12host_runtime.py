"""L12-HOST v3.2 slot runtime: the install/timer shell around Codex's L-12 R6 core, entered ONLY through
OuterLimiter.run(batch, operation) with the R6 BoundedRunner as inner transport (containment INHERITED_OUTER_GROUP).
Every Codex module is vendored by SHA-256 and executed from its PINNED installed bytes.

One transient timer per signed slot runs, once, with no catch-up and no restart:

    <python> -I -S -B <root>/src/l12host_runtime.py run --lot-dir <root>/lots/<LOT> --slot <SLOT>

The installer never imports the runtime to judge the host: it runs the INSTALLED copy in a subprocess with a pinned,
bounded reply protocol (L12HOST_PREVIEW_V3):

    <python> -I -S -B <root>/src/l12host_runtime.py preview-stage --stage-lot <dir> --lot <LOT>   (before any write)
    <python> -I -S -B <root>/src/l12host_runtime.py preview --lot-dir <root>/lots/<LOT>          (after the copy)
    <python> -I -S -B <root>/src/l12host_runtime.py derived-check --lot-dir <..> --derived-file <f> [--installed]

Slot order (v3): lot bytes and pins (refusal, nothing consumed, exit 3) -> slot known -> REVOKED -> START MARKER (one
O_EXCL file per logical attempt; alternatives J1/J2/J3 share it) -> slot window and BRT start-minute rules. A slot that
fired outside its window or on a forbidden minute AFTER the marker is a consumed refusal: it never hands the attempt to
a later alternative (Codex ruling: no refusal authorizes J2/J3). There is no SKIP, catch-up, retry or second attempt.

Core target: OuterLimiter.run consumes in the root-owned ledger, then the R6 core runs every gate in the supervised
worker and calls Services.execute = BoundedRunner (INHERITED_OUTER_GROUP) exactly once. The runner's CURRENT_PINS
approval is the BEFORE_EFFECT hook (same ALLOW, never renewed, minute rules, remaining budget >= effect floor); the
effect engine repeats the folder/ALLOW check right before the transport syscall.

Extended target (UP runner04 post chain; DOWN late session start and capture): l12host_extended, the shell's own
finite executor, with a CLOSED step table per lane (fixed effect kind, command shape, decoder and dependency chain).

Every lot constant is SIGNED DATA (AUTHORITY pinned by the core REQUEST, under the owner's Assino). Code constants are
guards only: owner signature 07:00:00-21:45:00 BRT, slot window, start-minute rules, file and mount policy, closed
grammar, decoder and step tables, epoch-04 path guards.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timedelta, timezone

LAYOUT_SCHEMA = "L12HOST_LAYOUT_V3"
RUNTIME_SCHEMA = "L12HOST_RUNTIME_V3"
AUTHORITY_SCHEMA = "L12HOST_AUTHORITY_V3"
VETO_SCHEMA = "L12HOST_VETO_AUTHORITY_V3"
VETO_RULE = "EMPTY_DIRECTORY_IS_ALLOW_ANY_ENTRY_IS_VETO"
VETO_OBSERVATION_SCHEMA = "L12HOST_VETO_OBSERVATION_V3"
ENVELOPE_SCHEMA = "L12HOST_RECEIPT_ENVELOPE_V3"
RESULT_SCHEMA = "L12HOST_SLOT_RESULT_V3"
REFUSAL_SCHEMA = "L12HOST_SLOT_REFUSAL_V3"
START_SCHEMA = "L12HOST_START_MARKER_V3"
PREVIEW_SCHEMA = "L12HOST_PREVIEW_V3"
CHILDREN = ("src", "ledger", "starts", "extended", "receipts", "results", "work", "lots")
LEDGER_FILE = "attempts.ledger"
REVOKED = "REVOKED"
LOT_FILES = ("request.json", "bound.json", "owner.json", "authority.json", "runtime.json", "question.txt")
SHELL_SOURCES = ("l12host_runtime.py", "l12host_effect.py", "l12host_decode.py", "l12host_extended.py")
CORE_SOURCES = ("vendor/finite_batch.py", "vendor/verification_binding.py", "vendor/image_path_adapter.py",
                "vendor/image_capacity_gate.py", "vendor/bounded_readback.py", "vendor/bounded_image_capacity_gate.py",
                "vendor/outer_limiter.py",
                "vendor/bounded_runner.py", "vendor/capacity_monday_gate.py", "vendor/k9_receipt_adapter.py")
# The R6 core that owns the ledger (S5: the J4 program set must pin exactly this core).
FINITE_BATCH_SHA256 = "809a816d4179ee889531bfc2d270e193508f0d1a31d7a30a48159151f80dbeec"
# Codex J4 hot worker (codex-epoch04-hot-image10-20261009-r1, package ec04b7fc...): the only J program on the host.
J4_HOT_WORKER_SHA256 = "0edb64f45b8a4e31e64aa274e778566106e3549d7e8fe2ab8d746dd1b751d8fa"
BRT = timezone(timedelta(hours=-3))               # Brazil has no DST since 2019
OWNER_EARLIEST, OWNER_LATEST = (7, 0, 0, 0), (21, 45, 0, 0)
EARLY_SECONDS, LATE_SECONDS = 2, 60
APPROVAL_SECONDS = 5
CORE_TIMEOUT_MARGIN = 120          # systemd TimeoutStartSec = budget/ceiling + 120 (exact)
MAX_EXTENDED_CEILING = 4800
GATE_ALLOWANCE_SECONDS = 15        # gates/decoders before and after a container effect (inside the budget)
# v3.1 (finding 8): every budget/ceiling keeps >= 30 s beyond (effect floor + gate allowances), so a slot may reach
# BEFORE_EFFECT up to (budget - effect floor) >= 45 s after its instant (gate latency) before
# BUDGET_REMAINING_BELOW_EFFECT_FLOOR refuses and consumes it.
EFFECT_LATENESS_SLACK_SECONDS = 30
LEDGER_LOCK_BUDGET, LEDGER_FINISH_BUDGET = 1.0, 10
SLOT_SPACING_SECONDS = 30
J_EXCLUSION_SECONDS = 30           # no other slot of any lot runs within J's window +- this margin
CODE = re.compile(r"[A-Z][A-Z0-9_]{0,80}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
LOT = re.compile(r"[A-Z][A-Z0-9_]{0,31}\Z")
SLOT = re.compile(r"[A-Z][A-Z0-9]{0,7}\Z")
PREFIX = re.compile(r"[a-z][a-z0-9-]{0,30}-\Z")
SUFFIX = re.compile(r"-[a-z0-9]{1,8}\Z")
OP = re.compile(r"[a-z][a-z0-9_]{0,40}\Z")
REL = re.compile(r"(ext|k9|j|image_go|docs|cap)/[A-Za-z0-9_.:-]{1,80}\Z")
NETWORK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")
LIMIT = 1024 * 1024
EXE_LIMIT = 256 * 1024 * 1024
J4_PROGRAMS = ("hot_runtime", "hot_worker", "hot_watchdog", "finite_batch", "folder_veto", "veto_emitter",
               "config_finalizer", "consumer_codec", "j_slot", "authority_bridge")
J4_ORIGINALS = ("request", "bound", "owner", "authority", "runtime", "rule", "folder_spec", "folder_authority", "decision",
                "folder_owner", "config_base", "template", "veto_base", "config_authority", "act_b", "machine_order")
J4_LOT_ORIGINALS = {"request": "request.json", "bound": "bound.json", "owner": "owner.json", "authority": "authority.json",
                    "runtime": "runtime.json"}
J4_REGISTRY_TOKEN = "@DERIVED_J4_REGISTRY_RECORD@"
DERIVED_REGISTRY = "j4_registry.json"
# ---- epoch-04 host facts (R0 09/10; INSTALL_TREE04 rev 2): guards in physical mode only
DAY = "2026-10-12"
EPOCH04_L12_ROOT = "/var/lib/c3po-l12host-e04"     # v3.1: the L12 root is pinned in physical mode
EPOCH04_VETO_DIR = "/var/lib/c3po-veto-e04"
EPOCH04_K9_ROOT = "/var/lib/c3po/r2d2-v2-k9-20261012"
EPOCH04_K9_TOOLS = EPOCH04_K9_ROOT + "/tools"
EPOCH04_K9_DAY = EPOCH04_K9_ROOT + "/days/" + DAY
EPOCH04_SOURCE_ROOT = "/var/lib/c3po/r2d2-v2-source-20261012"
EPOCH04_JOURNAL_ROOT = "/var/lib/c3po-bar/journal-e04"
EPOCH04_SUPERVISOR_STATE = "/var/lib/c3po-bar/supervisor-e04"
EPOCH04_CAPACITY_ROOT = "/var/lib/c3po-capacity-e04"
EPOCH04_READER_CONFIG = "/etc/c3po-reader-e04"
EPOCH04_READER_LAUNCHER = EPOCH04_READER_CONFIG + "/launcher"
EPOCH04_SUPERVISOR_CONFIG = EPOCH04_READER_CONFIG + "/supervisor"
EPOCH03_SECRETS_ROOT = "/var/lib/c3po/r2d2-v2-k9-20261005/secrets"
EPOCH04_SECRETS_ROOTS = (EPOCH04_K9_ROOT + "/secrets", EPOCH03_SECRETS_ROOT)   # REQUEST parameter, decision pending
DAY_D_DATA = "/mnt/day-d-data"
EPOCH04_READY_PATH = EPOCH04_JOURNAL_ROOT + "/session_date=" + DAY + "/ready.json"
# v3.1: /etc/c3po-reader-e04 itself (it holds the reader's secret.env) is NOT mountable; only the launcher and the
# supervisor config folders are, read-only.
MOUNT_RO_ROOTS = (EPOCH04_K9_ROOT, EPOCH04_SOURCE_ROOT, EPOCH04_JOURNAL_ROOT, EPOCH04_SUPERVISOR_STATE,
                  EPOCH04_CAPACITY_ROOT, EPOCH04_READER_LAUNCHER, EPOCH04_SUPERVISOR_CONFIG, DAY_D_DATA,
                  EPOCH03_SECRETS_ROOT)
MOUNT_RW_ROOTS = (EPOCH04_K9_DAY, EPOCH04_SOURCE_ROOT, EPOCH04_JOURNAL_ROOT, EPOCH04_SUPERVISOR_STATE)
# v3.1 (finding 6): the regular 12/10 open (the Codex reader gate: open - 90 s <= not_before < not_after <= close +
# 20 min, close = open + 6 h 30). Physical mode pins the signed gate scope's session_open to this instant.
SESSION_OPEN_UTC = "2026-10-12T13:30:00Z"
SESSION_OPEN_LEAD_SECONDS = 90
SESSION_LATEST_AFTER_OPEN = timedelta(hours=6, minutes=50)
# v3.1 (finding 7): the K9 env files per network class (gen_k9_plans04 SCHEDULE), relative to the secrets root
K9_CLASS_ENV_LEAVES = {"NONE": (), "PROVIDER": ("provider.env",), "DATABASE": (),
                       "DATABASE_AND_PROVIDER": ("provider.env", "risk-db.env")}
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
# ---- K9 runner04 row shape (track F-E, gen_k9_plans04 2b08ee13)
K9_TOOLS_TARGET, K9_DAY_TARGET = "/c3po-k9-tools", "/c3po-k9-day"
K9_SOURCE_TARGET, K9_EMITTER_TARGET = "/c3po-source", "/c3po-k9-emitter"
K9_CONTAINER_PREFIX = "c3po-k9-e04-20261012-"
K9_NETWORK_CLASSES = ("PROVIDER", "DATABASE", "DATABASE_AND_PROVIDER")
K9_CORE_RUNNER_OPS = {"prove": "prove_launch", "collect": "collect_launch", "commit_result": "commit_launch",
                      "publish_launch": "publish_launch"}
# ---- v3.3f (Codex D-NET, #429 6097884984): the epoch-04 Docker networks, pinned in PHYSICAL mode. The three K9 classes
# (NONE stays "none") and the two session units, each its own constant; c3po_default does not exist on the host
# (#429 6097680267) and is never accepted there.
K9_NETWORKS_EPOCH04 = {"PROVIDER": "bridge", "DATABASE": "c3po_c3po_internal", "DATABASE_AND_PROVIDER": "c3po_db_loopback"}
READER_NETWORK_EPOCH04 = "c3po_c3po_internal"
SUPERVISOR_NETWORK_EPOCH04 = "c3po_db_loopback"
# ---- v3.3f (Codex K9 REAL verifiers R2, DELIVERY "Arquivos obrigatorios em cada lote"): the REAL files every PHYSICAL
# lot with a K9 section signs, besides runner / request / GO / plans. The eight originals live at the paths the lot's
# registry declares (`originals[name].file`); their names and hashes are the signed verifier's literal ORIGINAL_PINS.
K9_REAL_VERIFIER = "ext/k9_verifiers04.py"
K9_REAL_POLICY = "k9/VERIFIER_POLICY_04.json"
K9_REAL_REVIEW = "k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json"
K9_REAL_PUBLICATION = "k9/K9_GO_04.PUBLICATION.json"
K9_REAL_FIXED_FILES = (K9_REAL_VERIFIER, K9_REAL_POLICY, K9_REAL_REVIEW, K9_REAL_PUBLICATION)
K9_REAL_CALLBACKS = {"k9_approval": "verify_approval", "k9_original": "verify_original", "k9_step": "verify_step"}
K9_REAL_SOURCE_RELS = {"POLICY_REL": K9_REAL_POLICY, "PUBLICATION_REL": K9_REAL_PUBLICATION,
                       "CURRENT_REVIEW_REL": K9_REAL_REVIEW}
K9_REAL_POLICY_SCHEMA = "K9_REAL_VERIFIER_POLICY_04_V1"
K9_REAL_POLICY_KEYS = {"schema", "mode", "reviewer", "review_decision_sha256", "epoch", "day", "lot", "go_sha256",
                       "publication_sha256", "request_sha256", "grid", "originals", "operations"}
# a signed relative name both grammars accept: this runtime's REL and the verifier's own REL (no ':', alnum first)
K9_REAL_ORIGINAL_REL = re.compile(r"(ext|k9|j|image_go|docs|cap)/[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
# ---- the CLOSED extended step table per lane (S1): kind, runner operation, exact dependency chain
EXTENDED_TABLE = {
    "UPSTREAM_P": {
        "components": ("RUNNER", "components_launch", (("core", "publish_launch"),)),
        "sources": ("RUNNER", "sources_launch", (("core", "publish_launch"), ("step", "components"))),
        "bind": ("RUNNER", "bind", (("core", "publish_launch"), ("step", "sources"))),
        "preflight": ("RUNNER", "preflight", (("step", "bind"),)),
        "acquire": ("RUNNER", "acquire_launch", (("step", "preflight"),)),
        "execute": ("RUNNER", "execute_launch", (("step", "acquire"),)),
        "stage": ("RUNNER", "stage", (("core", "publish_launch"), ("step", "bind"), ("step", "execute"))),
    },
    "DOWNSTREAM_AFTER_E6": {
        # v3.1 (finding 2): an EARLY read-only check that the ready file is absent (a person can still clear a
        # leftover); no effect, no dependency, and the session start never depends on it (it re-checks itself).
        "ready_check": ("READY_CHECK", None, ()),
        "session_start": ("SESSION_START", None, (("core", "admission_manifest"), ("core", "post"))),
        "capture_launch": ("CAPTURE", "capture_launch", (("core", "post"), ("step", "session_start"))),
    },
}
READER_COMMAND = ["python", "-I", "-B", "/c3po-reader/reader_launcher.py"]
SUPERVISOR_MODULE = ["python", "-B", "-m", "app.r2d2_v2_massive_supervisor"]
SUPERVISOR_FLAGS = ("--journal-root", "--manifest-directory", "--token-file", "--state-root")
READER_NAME, SUPERVISOR_NAME = "c3po-reader-e04", "c3po-massive-e04"
# v3.1 (finding 1): the WHOLE session-start unit shape is pinned (exec words and property list), rebuilt from the
# reviewed references (c3po-reader.service 8d2ff7a9, c3po-massive.service 9e7de1c6) with only these variables:
# host data/journal/capacity/state/config folders, image, network and the layout's docker binary/config.
CONTAINER_JOURNAL_ROOT = "/var/lib/c3po-bar/journal-e04"
READER_ENV_LEAVES = ("secret.env", "pins.env", "activation.env")
READER_DESCRIPTION = "Day-bounded R2D2 V2 shadow reader"
SUPERVISOR_DESCRIPTION = "Bounded daily Massive minute producer"
UNIT_DOCKER_HEAD = ["--rm", "--init", "--restart", "no"]
UNIT_DOCKER_TAIL = ["--pull", "never", "--user", "0:0", "--workdir", "/app"]
UNIT_DOCKER_HARDENING = ["--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m", "--cap-drop", "ALL",
                         "--security-opt", "no-new-privileges", "--pids-limit", "512", "--stop-timeout", "25"]
BOOT_ID_PATH = "/proc/sys/kernel/random/boot_id"
BOOT_ID_FORMAT = re.compile(rb"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\n\Z")


class Hold(ValueError):
    """Only a fixed code is public."""


class Refusal(Hold):
    """Before the start marker: nothing consumed, nothing written."""


def need(ok, code, kind=Hold):
    if not ok:
        raise kind(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def native_utc():
    """The ONLY clock of this shell (monkeypatched in tests only, like the core's native_utc_now)."""
    return datetime.now(timezone.utc)


def safe_code(error):
    text = str(error)
    if isinstance(error, ValueError) and CODE.fullmatch(text):
        return text
    code = getattr(error, "code", None)
    return code if type(code) is str and CODE.fullmatch(code) else "SHELL_INTERNAL_FAILURE"


def strict(raw, limit=LIMIT, kind=Refusal):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, "JSON_DUPLICATE_KEY", kind)
            out[key] = value
        return out

    def constant(_v):
        raise kind("JSON_NONFINITE")
    need(type(raw) is bytes and 0 < len(raw) <= limit, "DOCUMENT_SIZE_INVALID", kind)
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except Hold:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise kind("DOCUMENT_JSON_INVALID") from None
    need(type(value) is dict and canonical(value) == raw, "DOCUMENT_NOT_CANONICAL", kind)
    return value


def stamp(value, kind=Refusal):
    need(type(value) is str and value.endswith("Z") and len(value) <= 40, "TIME_NOT_UTC", kind)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise kind("TIME_INVALID") from None
    return parsed.astimezone(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def pin(value):
    return type(value) is str and HEX.fullmatch(value) is not None and value not in ("0" * 64, "0f" + "0" * 62)


def owner_time_guard(signed_at, kind=Hold):
    """The owner signs only between 07:00:00 and 21:45:00 BRT."""
    local = stamp(signed_at, kind).astimezone(BRT)
    need(OWNER_EARLIEST <= (local.hour, local.minute, local.second, local.microsecond) <= OWNER_LATEST,
         "OWNER_SIGNED_OUTSIDE_0700_2145_BRT", kind)


def under(path, root):
    return path == root or path.startswith(root + "/")


def epoch04_path_violation(path, readonly):
    """Host facts R0 09/10 as guards (physical mode): epoch-04 K9 root on the root fs (the epoch-03 K9 root only for the
    read-only secrets material, Codex root closure CONDITIONAL_READONLY_REUSE_MATERIAL_ONLY), no write on
    /mnt/day-d-data (53 GB < runner FLOOR), only the epoch-04 journal/supervisor roots under /var/lib/c3po-bar."""
    if "r2d2-v2-k9-" in path and not under(path, EPOCH04_K9_ROOT):
        if not (readonly and under(path, EPOCH03_SECRETS_ROOT)):
            return "EPOCH03_K9_ROOT_FORBIDDEN"
    if under(path, DAY_D_DATA) and not readonly:
        return "DAY_D_DATA_WRITE_FORBIDDEN"
    if path.startswith("/var/lib/c3po-bar/") and not (under(path, EPOCH04_JOURNAL_ROOT)
                                                      or under(path, EPOCH04_SUPERVISOR_STATE)):
        return "EPOCH03_JOURNAL_ROOT_FORBIDDEN"
    return None


def epoch04_mount_violation(source, readonly, layout):
    """S3 (physical): the ONLY host roots a container may see. Read-only: the epoch-04 K9/source/journal/supervisor/
    capacity/reader-config roots, day-d-data, the (pending-decision) secret roots and the veto folder. Writable: the K9
    day, the source root, the journal and the supervisor state. Never the L12 root/ledger, never a writable veto or
    secret root, nothing else (containerd, postgresql, /etc/shadow, docker data ...)."""
    code = epoch04_path_violation(source, readonly)
    if code:
        return code
    if under(source, layout["root"]):
        return "MOUNT_L12_ROOT_FORBIDDEN"
    if any(p.startswith(source + "/") for p in (layout["root"], layout["veto_dir"], layout["docker_config"],
                                                EPOCH04_READER_CONFIG)):
        return "MOUNT_PARENT_OF_PROTECTED_FORBIDDEN"
    if under(source, layout["veto_dir"]):
        return None if readonly else "MOUNT_VETO_WRITABLE_FORBIDDEN"
    if any(under(source, root) for root in EPOCH04_SECRETS_ROOTS) and not readonly:
        return "MOUNT_SECRETS_WRITABLE_FORBIDDEN"
    roots = MOUNT_RO_ROOTS if readonly else MOUNT_RW_ROOTS
    return None if any(under(source, root) for root in roots) else "MOUNT_SOURCE_NOT_ALLOWLISTED"


# ------------------------------------------------------------------ files and identities
def dir_identity(info):
    return [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)]


def file_identity9(info):
    return [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def ledger_identity6(info):
    return [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink]


def canonical_path(path, kind=Refusal):
    need(type(path) is str and re.fullmatch(r"/[A-Za-z0-9._/@=-]{1,240}", path) is not None and "//" not in path
         and "/../" not in path + "/" and "/./" not in path + "/" and not path.endswith("/"), "PATH_NOT_CANONICAL", kind)
    return path


def chain(path):
    canonical_path(path)
    parts = path.split("/")[1:]
    return ["/"] + ["/" + "/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def chain_identities(path):
    rows = []
    for name in chain(path):
        info = os.lstat(name)
        need(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "CHAIN_NOT_DIRECTORY", Refusal)
        rows.append([name, dir_identity(info)])
    return rows


def open_chain(rows, kind=Hold):
    """Walk by held descriptors with O_NOFOLLOW; every identity equal to its pin. Returns the last fd."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for index, (name, row) in enumerate(rows):
            if index:
                try:
                    child_fd = os.open(name.rsplit("/", 1)[1], flags, dir_fd=fd)
                except OSError:
                    raise kind("PINNED_DIRECTORY_UNAVAILABLE") from None
                os.close(fd)
                fd = child_fd
            need(dir_identity(os.fstat(fd)) == list(row) and dir_identity(os.lstat(name)) == list(row),
                 "DIRECTORY_IDENTITY_CHANGED", kind)
        return fd
    except BaseException:
        os.close(fd)
        raise


# v3.2 (M1): INPUT_FILE_CHANGED names the file. The public code stays the fixed word; the refusal object carries the
# path and the changed fields (`input_file`, `changed`), the process keeps the last 16 in INPUT_CHANGES, and inside a
# slot (after its start marker) the shell's sink writes them as PRIVATE diagnostics that the slot RESULT lists as
# "INPUT_FILE_CHANGED:<path>:<fields>". Diagnostics only: the strict read itself is unchanged and never relaxed.
INPUT_CHANGES = []
_INPUT_SINK = None
_INPUT_COUNT = [0]


def set_input_sink(sink):
    global _INPUT_SINK
    _INPUT_SINK = sink


def report_input_changes(since):
    """One stderr line per input change recorded by THIS process after `since` (stdout protocols are untouched)."""
    for record in INPUT_CHANGES:
        if record["seq"] > since:
            try:
                os.write(2, ("L12HOST %s %s %s\n" % (record["code"], record["file"], ",".join(record["changed"])))
                         .encode("utf-8", "replace"))
            except BaseException:
                pass


def fd_path(fd):
    """Best-effort path of an open directory descriptor (diagnostics only; None when the platform cannot tell)."""
    try:
        if sys.platform.startswith("linux"):
            return os.readlink("/proc/self/fd/%d" % fd)
        if sys.platform == "darwin":
            import fcntl
            raw = fcntl.fcntl(fd, getattr(fcntl, "F_GETPATH", 50), bytes(1024))
            return raw.split(b"\0", 1)[0].decode("utf-8", "replace") or None
    except (OSError, ValueError, TypeError):
        return None
    return None


def input_changed(dir_fd, name, changed, kind):
    base = fd_path(dir_fd)
    _INPUT_COUNT[0] += 1
    record = {"code": "INPUT_FILE_CHANGED", "file": (base.rstrip("/") + "/" + name) if base else name,
              "changed": list(changed), "seq": _INPUT_COUNT[0]}
    INPUT_CHANGES.append(record)
    del INPUT_CHANGES[:-16]
    sink = _INPUT_SINK
    if sink is not None:
        try:
            sink(record)
        except BaseException:
            pass
    error = kind("INPUT_FILE_CHANGED")
    error.input_file, error.changed = record["file"], record["changed"]
    return error


def read_at(dir_fd, name, limit, kind=Refusal):
    """Regular-file original: size, non-empty, identity/mtime/ctime preserved while read (never relaxed; B1 has its own
    procfs reader). v3.2: a change names the file (input_changed)."""
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except OSError:
        raise kind("INPUT_FILE_UNAVAILABLE") from None
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit, "INPUT_FILE_INVALID", kind)
        parts, size = [], 0
        while True:
            block = os.read(fd, min(1024 * 1024, limit + 1 - size))
            if not block:
                break
            parts.append(block)
            size += len(block)
            need(size <= limit, "INPUT_FILE_TOO_LARGE", kind)
        after = os.fstat(fd)
        changed = [field for field, a, b in (("size", info.st_size, after.st_size),
                                             ("mtime_ns", info.st_mtime_ns, after.st_mtime_ns),
                                             ("ctime_ns", info.st_ctime_ns, after.st_ctime_ns)) if a != b]
        if size != info.st_size:
            changed.append("bytes_read")
        if changed:
            raise input_changed(dir_fd, name, changed, kind)
        need(size > 0, "INPUT_FILE_EMPTY", kind)
        return b"".join(parts)
    finally:
        os.close(fd)


def read_path(path, limit, kind=Refusal):
    canonical_path(path, kind)
    parent, name = path.rsplit("/", 1)
    try:
        fd = os.open(parent or "/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        raise kind("INPUT_FILE_UNAVAILABLE") from None
    try:
        return read_at(fd, name, limit, kind)
    finally:
        os.close(fd)


def read_rel(base_fd, rel, limit, kind=Refusal):
    """Read <base>/<sub>/<leaf> by held descriptors, no symlink anywhere."""
    parts = rel.split("/")
    fd = base_fd
    opened = []
    try:
        for sub in parts[:-1]:
            try:
                fd = os.open(sub, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError:
                raise kind("INPUT_FILE_UNAVAILABLE") from None
            opened.append(fd)
        return read_at(fd, parts[-1], limit, kind)
    finally:
        for x in opened:
            os.close(x)


def write_new_at(dir_fd, name, raw, mode=0o600):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    try:
        written = 0
        while written < len(raw):
            size = os.write(fd, raw[written:])
            need(size > 0, "WRITE_UNCERTAIN")
            written += size
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(dir_fd)


# ------------------------------------------------------------------ B1: the procfs boot id
def read_proc_bounded(path, limit, kind=Refusal):
    """procfs files report st_size 0: read to EOF under a hard bound, never trusting st_size. procfs only."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise kind("PROCFS_FILE_UNAVAILABLE") from None
    try:
        info = os.fstat(fd)
        raw = bytearray()
        while True:
            block = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
            need(len(raw) <= limit, "PROCFS_FILE_TOO_LARGE", kind)
        return bytes(raw), info
    finally:
        os.close(fd)


def proc_is_procfs(kind=Refusal):
    """The mount namespace of this process has procfs at /proc (/proc/self/mountinfo, field 5 = mount point, the
    field after '-' = fstype)."""
    raw, _ = read_proc_bounded("/proc/self/mountinfo", 4 * 1024 * 1024, kind)
    for line in raw.decode("ascii", "replace").splitlines():
        fields = line.split(" ")
        if "-" in fields:
            dash = fields.index("-")
            if len(fields) > dash + 1 and dash >= 5 and fields[4] == "/proc" and fields[dash + 1] == "proc":
                return True
    return False


def read_boot_id(path=BOOT_ID_PATH, *, owner_uid=0, require_procfs=True, kind=Refusal):
    """B1: dedicated reader of the FIXED boot_id path. Regular file owned by root (procfs), read to EOF, at most 128
    bytes, exact lowercase UUID + LF; the reported st_size (0 on procfs) is ignored ONLY here. The exact bytes are
    returned (never normalized): boot_id_sha256 pins what was read, and BOOT_CHANGED keeps refusing on every recheck."""
    if require_procfs:
        need(sys.platform == "linux" and path == BOOT_ID_PATH and proc_is_procfs(kind), "BOOT_ID_PROCFS_UNAVAILABLE", kind)
    raw, info = read_proc_bounded(path, 128, kind)
    need(stat.S_ISREG(info.st_mode) and info.st_uid == owner_uid, "BOOT_ID_NOT_REGULAR_ROOT", kind)
    need(BOOT_ID_FORMAT.fullmatch(raw) is not None, "BOOT_ID_FORMAT_INVALID", kind)
    return raw


def load_pinned(name, raw, expected, origin):
    """Execute exactly the bytes whose SHA-256 was checked (F2 load_reference_raw pattern)."""
    need(sha(raw) == expected, "PINNED_SOURCE_CHANGED", Refusal)
    module = type(sys)(name)
    module.__file__ = origin
    sys.modules[name] = module
    exec(compile(raw, origin, "exec"), module.__dict__)
    return module


MODULE_NAMES = {"vendor/finite_batch.py": "finite_batch", "vendor/verification_binding.py": "verification_binding",
                "vendor/image_path_adapter.py": "image_path_adapter", "vendor/image_capacity_gate.py": "image_capacity_gate",
                "vendor/bounded_readback.py": "bounded_readback",
                "vendor/bounded_image_capacity_gate.py": "bounded_image_capacity_gate", "vendor/outer_limiter.py": "outer_limiter",
                "vendor/bounded_runner.py": "bounded_runner", "vendor/capacity_monday_gate.py": "capacity_monday_gate",
                "vendor/k9_receipt_adapter.py": "k9_receipt_adapter", "l12host_effect.py": "l12host_effect",
                "l12host_decode.py": "l12host_decode", "l12host_extended.py": "l12host_extended"}


class Family:
    """The vendored R6 core/outer/runner/gates/adapters and the shell modules, loaded from pinned bytes of one held
    src directory, in dependency order, as ONE module identity (sys.modules), so OuterLimiter's own source pins
    (core_sha256/outer_sha256 of c.__file__/__file__) see exactly the installed bytes."""

    def __init__(self, src_fd, src_path, sources):
        need(type(sources) is dict, "RUNTIME_SOURCES_INVALID", Refusal)
        need(sources.get("vendor/finite_batch.py") == FINITE_BATCH_SHA256, "CORE_PIN_NOT_R6", Refusal)
        self.raw = {}
        for rel in SHELL_SOURCES + CORE_SOURCES:
            need(pin(sources.get(rel)), "RUNTIME_SOURCES_INVALID", Refusal)
            self.raw[rel] = read_rel(src_fd, rel, 2 * LIMIT)
            need(sha(self.raw[rel]) == sources[rel], "PINNED_SOURCE_CHANGED", Refusal)
        self.modules = {}
        for rel in CORE_SOURCES + ("l12host_effect.py", "l12host_decode.py", "l12host_extended.py"):
            self.modules[MODULE_NAMES[rel]] = load_pinned(MODULE_NAMES[rel], self.raw[rel], sources[rel],
                                                          src_path + "/" + rel)
        m = self.modules
        self.fb, self.vb, self.image, self.gate = m["finite_batch"], m["verification_binding"], m["image_path_adapter"], m["image_capacity_gate"]
        self.bounded, self.bgate = m["bounded_readback"], m["bounded_image_capacity_gate"]
        self.outer, self.br = m["outer_limiter"], m["bounded_runner"]
        self.cap, self.k9 = m["capacity_monday_gate"], m["k9_receipt_adapter"]
        self.fx, self.dec, self.ext = m["l12host_effect"], m["l12host_decode"], m["l12host_extended"]
        self.ext.RT = sys.modules[__name__]
        self.dec.RT = sys.modules[__name__]
        self.sources = dict(sources)


# ------------------------------------------------------------------ signed data validation
def validate_layout(layout, kind=Refusal):
    need(type(layout) is dict and set(layout) == {"schema", "root", "veto_dir", "unit_prefix", "unit_name_suffix",
                                                  "python", "binaries", "docker_config"}
         and layout["schema"] == LAYOUT_SCHEMA, "LAYOUT_INVALID", kind)
    for key in ("root", "veto_dir", "python", "docker_config"):
        canonical_path(layout[key], kind)
    need(not under(layout["veto_dir"], layout["root"]) and not under(layout["root"], layout["veto_dir"]),
         "LAYOUT_VETO_INSIDE_ROOT", kind)
    need(type(layout["unit_prefix"]) is str and PREFIX.fullmatch(layout["unit_prefix"]) is not None
         and type(layout["unit_name_suffix"]) is str and SUFFIX.fullmatch(layout["unit_name_suffix"]) is not None,
         "LAYOUT_UNIT_NAMES_INVALID", kind)
    binaries = layout["binaries"]
    need(type(binaries) is dict and set(binaries) == {"docker", "systemd_run", "systemctl"}, "LAYOUT_BINARIES_INVALID", kind)
    for path in binaries.values():
        canonical_path(path, kind)
    return layout


def child(layout, name):
    need(name in CHILDREN, "LAYOUT_CHILD_INVALID")
    return layout["root"] + "/" + name


def veto_authority(layout, decision_sha256, maximum_age_seconds=10):
    return {"schema": VETO_SCHEMA, "directory": layout["veto_dir"], "rule": VETO_RULE,
            "maximum_age_seconds": maximum_age_seconds, "decision_sha256": decision_sha256}


def target_key(fb, q, target_kind, target):
    scope = list(fb.context(q)) + ([target] if target_kind == "CORE" else ["EXTENDED", target])
    return sha(canonical(scope)), scope


def task_window(task, kind=Refusal):
    return stamp(task["not_before"], kind), stamp(task["not_after"], kind)


def validate_k9_section(a, files, files_raw, layout, kind, physical):
    """Returns {"plans": {op: plan}, "request": the signed K9 step-set request} or None."""
    k9 = a["k9"]
    if k9 is None:
        return None
    need(type(k9) is dict and set(k9) == {"runner_source", "request", "go", "plans", "networks", "secrets_root"}
         and all(k9[k] in files for k in ("runner_source", "request", "go")) and type(k9["plans"]) is dict
         and 0 < len(k9["plans"]) <= 16 and all(type(op) is str and OP.fullmatch(op) and rel in files
                                               and rel == "k9/" + op + ".json" for op, rel in k9["plans"].items()),
         "K9_SECTION_INVALID", kind)
    networks = k9["networks"]
    need(type(networks) is dict and set(networks) == set(K9_NETWORK_CLASSES) and all(
        type(v) is str and NETWORK.fullmatch(v) and v not in ("host", "default", "none") and not v.startswith("container")
        for v in networks.values()) and networks["DATABASE"] != "bridge"
         and networks["DATABASE_AND_PROVIDER"] != "bridge", "K9_NETWORKS_INVALID", kind)
    # v3.3f (D-NET): physical mode pins the three class networks (the rows are tied to them: K9_NETWORK_NOT_THE_CLASS_ONE)
    need(not physical or networks == K9_NETWORKS_EPOCH04, "K9_NETWORKS_NOT_DNET", kind)
    canonical_path(k9["secrets_root"], kind)
    need(not physical or k9["secrets_root"] in EPOCH04_SECRETS_ROOTS, "K9_SECRETS_ROOT_NOT_ALLOWED", kind)
    need(files_raw is not None, "K9_FILES_UNAVAILABLE", kind)
    runner = files_raw[k9["runner_source"]]
    plans = {}
    for op, rel in k9["plans"].items():
        plan = strict(files_raw[rel], kind=kind)
        need(plan.get("schema") == "K9_STEP_PLAN_V1" and plan.get("k9_operation") == op
             and type(plan.get("constants")) is dict and plan["constants"].get("runner_sha256") == sha(runner)
             and plan.get("request_sha256") == files[k9["request"]] and plan.get("go_sha256") == files[k9["go"]]
             and plan.get("network_class") in K9_NETWORK_CLASSES + ("NONE",) and type(plan.get("step_row")) is dict,
             "K9_PLAN_UNBOUND", kind)
        plans[op] = plan
    # v3.1 (finding 7): the signed K9 step-set request names the ONE image (id, revision, package) of every K9 row.
    request = strict(files_raw[k9["request"]], kind=kind)
    image = request.get("image")
    need(type(image) is dict and type(image.get("id")) is str and IMAGE_ID.fullmatch(image["id"]) is not None
         and all(p["constants"].get("code_revision") == image.get("revision")
                 and p["constants"].get("package_sha256") == image.get("package_sha256") for p in plans.values()),
         "K9_REQUEST_IMAGE_UNBOUND", kind)
    return {"plans": plans, "request": request}


def validate_k9_row(name, runner_op, row, budget, slots, k9, k9ctx, files, kind, physical, *, exact_budget=True):
    """S1/F-E: a K9 effect row is fully fixed by its signed plan and the k9 section: runner name with the FULL sha,
    plan path and sha, container name, network per class, the two fixed env words (C3PO_BUILD_SHA = the plan's
    code_revision), secret env files only from the secrets root, closed mount targets, the receipt file of the
    operation, inner KILL inside the plan window, the slot instant and budget of the plan's step_row. v3.1: the image
    is the signed K9 request's image.id and the env files are exactly the network class's ones."""
    need(k9 is not None and k9ctx is not None and runner_op in k9ctx["plans"], "K9_PLAN_ABSENT", kind)
    plans = k9ctx["plans"]
    plan, d = plans[runner_op], row["docker"]
    need(d["image_id"] == k9ctx["request"]["image"]["id"], "K9_IMAGE_NOT_THE_REQUEST_ONE", kind)
    runner_sha, plan_sha = files[k9["runner_source"]], files[k9["plans"][runner_op]]
    need(row["kind"] == "CONTAINER" and d["command"] == ["python", "-I",
                                                          K9_TOOLS_TARGET + "/k9_runner04-%s.py" % runner_sha,
                                                          "--plan", K9_DAY_TARGET + "/plans/%s.json" % runner_op,
                                                          "--plan-sha256", plan_sha], "K9_COMMAND_NOT_FIXED_SHAPE", kind)
    need(d["name"] == K9_CONTAINER_PREFIX + runner_op.replace("_", "-"), "K9_CONTAINER_NAME_INVALID", kind)
    cls = plan["network_class"]
    need(d["network"] == ("none" if cls == "NONE" else k9["networks"][cls]), "K9_NETWORK_NOT_THE_CLASS_ONE", kind)
    need(d["env"] == [["C3PO_R2D2_V2_PRODUCERS_ENABLED", "true"], ["C3PO_BUILD_SHA", plan["constants"]["code_revision"]]],
         "K9_ENV_NOT_FIXED", kind)
    root = k9["secrets_root"]
    need(all(p in (root + "/provider.env", root + "/risk-db.env") for p in d["env_files"]), "K9_ENV_FILE_NOT_SECRETS_ROOT", kind)
    need(d["env_files"] == [root + "/" + leaf for leaf in K9_CLASS_ENV_LEAVES[cls]], "K9_ENV_FILES_NOT_THE_CLASS_ONES", kind)
    targets = {m["target"]: m for m in d["mounts"]}
    need(set(targets) <= {K9_TOOLS_TARGET, K9_DAY_TARGET, K9_DAY_TARGET + "/receipts", K9_SOURCE_TARGET, K9_EMITTER_TARGET}
         and K9_TOOLS_TARGET in targets and K9_DAY_TARGET in targets and targets[K9_TOOLS_TARGET]["readonly"]
         and (K9_EMITTER_TARGET not in targets or (targets[K9_EMITTER_TARGET]["readonly"]
                                                   and targets[K9_EMITTER_TARGET]["source"] == root + "/emitter")),
         "K9_MOUNTS_NOT_CLOSED", kind)
    day = targets[K9_DAY_TARGET]["source"]
    need(K9_DAY_TARGET + "/receipts" not in targets or targets[K9_DAY_TARGET + "/receipts"]["source"] == day + "/receipts",
         "K9_MOUNTS_NOT_CLOSED", kind)
    if physical:
        need(targets[K9_TOOLS_TARGET]["source"] == EPOCH04_K9_TOOLS and day == EPOCH04_K9_DAY
             and (K9_SOURCE_TARGET not in targets or targets[K9_SOURCE_TARGET]["source"] == EPOCH04_SOURCE_ROOT),
             "K9_MOUNTS_NOT_EPOCH04", kind)
    need(row["receipt"] == {"source": "FILE", "path": day + "/receipts/" + runner_op + ".RECEIPT.json"},
         "K9_RECEIPT_PATH_INVALID", kind)
    step_row = plan["step_row"]
    starts = stamp(step_row.get("starts_at", "").replace("+00:00", "Z"), kind)
    rna = stamp(plan["run_not_after"].replace("+00:00", "Z"), kind)
    ats = sorted(stamp(x["at"], kind) for x in slots)
    # the FIRST alternative is the plan's start; later slots are alternatives of the same logical attempt
    plan_budget = step_row.get("budget_seconds")
    need(ats and ats[0] == starts and type(plan_budget) is int
         and (plan_budget == budget if exact_budget else plan_budget <= budget), "K9_SLOT_NOT_THE_PLAN_ONE", kind)
    need(d["timeout_seconds"] <= (rna - starts).total_seconds() - 5, "K9_KILL_OUTSIDE_PLAN_WINDOW", kind)
    return plan


def validate_authority(a, q, fam, kind=Refusal, *, physical=False, files_raw=None):
    """Shell-level ABI of the signed AUTHORITY against the core REQUEST (validated by the core)."""
    fb, fx, dec = fam.fb, fam.fx, fam.dec
    need(type(a) is dict and set(a) == {"schema", "lot", "lane", "mode", "layout", "veto", "delegated_named_selectors",
                                        "dependencies", "effects", "decoders", "files", "external", "imports", "slots",
                                        "k9", "extended", "bootstrap", "gate", "capacity", "ready", "j4"}
         and a["schema"] == AUTHORITY_SCHEMA, "AUTHORITY_ABI_INVALID", kind)
    need(type(a["lot"]) is str and LOT.fullmatch(a["lot"]) is not None and a["lane"] == q["lane"]
         and a["mode"] in ("REAL", "FIXTURE"), "AUTHORITY_LOT_INVALID", kind)
    need(not physical or a["mode"] == "REAL", "AUTHORITY_FIXTURE_REFUSED_ON_HOST", kind)
    layout = validate_layout(a["layout"], kind)
    need(not physical or layout["veto_dir"] == EPOCH04_VETO_DIR, "VETO_DIRECTORY_NOT_EPOCH04", kind)
    need(not physical or layout["root"] == EPOCH04_L12_ROOT, "L12_ROOT_NOT_EPOCH04", kind)
    veto = a["veto"]
    need(type(veto) is dict and type(veto.get("maximum_age_seconds")) is int and 5 <= veto["maximum_age_seconds"] <= 10
         and veto == veto_authority(layout, veto.get("decision_sha256"), veto["maximum_age_seconds"])
         and pin(veto["decision_sha256"]) and sha(canonical(veto)) == q["veto_authority_sha256"],
         "VETO_AUTHORITY_UNBOUND", kind)
    files = a["files"]
    need(type(files) is dict and len(files) <= 64 and all(type(k) is str and REL.fullmatch(k) and ".." not in k
                                                          and pin(v) for k, v in files.items()), "FILES_TABLE_INVALID", kind)
    need(files_raw is None or (set(files_raw) == set(files) and all(sha(files_raw[k]) == v for k, v in files.items())),
         "FILES_BYTES_UNBOUND", kind)
    external = a["external"]
    need(type(external) is dict and len(external) <= 32 and all(
        type(n) is str and OP.fullmatch(n) and type(e) is dict and set(e) == {"file", "identity"}
        and e["file"] in files and e["file"].startswith("ext/") and e["file"].endswith(".py")
        and type(e["identity"]) is str and e["identity"].isidentifier() for n, e in external.items()),
         "EXTERNAL_TABLE_INVALID", kind)
    tasks = {t["operation"]: t for t in q["tasks"]}
    need(a["delegated_named_selectors"] is True and type(a["dependencies"]) is dict
         and a["dependencies"] == {op: list(t["requires"]) for op, t in tasks.items()}, "DEPENDENCY_SELECTORS_NOT_DELEGATED", kind)
    effects, decoders = a["effects"], a["decoders"]
    need(type(effects) is dict and set(effects) == set(tasks) and type(decoders) is dict and set(decoders) == set(tasks),
         "EFFECT_TABLE_NOT_CLOSED", kind)
    slots_of = lambda kind_, target: [s for s in a["slots"] if type(s) is dict and s.get("target_kind") == kind_
                                     and s.get("target") == target] if type(a["slots"]) is list else []
    try:
        k9ctx = validate_k9_section(a, files, files_raw, layout, kind, physical)
        for op, row in effects.items():
            ekind = fx.validate_row(row, layout)
            need(ekind != "UNIT_START", "UNIT_START_ONLY_IN_THE_SESSION_START_STEP", kind)
            dec.validate_decoder_row(decoders[op], op, ekind, external=set(external), files=set(files))
            need(fx.row_budget_floor(row) + GATE_ALLOWANCE_SECONDS <= tasks[op]["budget_seconds"],
                 "EFFECT_BUDGET_EXCEEDS_TASK", kind)
            need(fx.row_budget_floor(row) + GATE_ALLOWANCE_SECONDS + EFFECT_LATENESS_SLACK_SECONDS
                 <= tasks[op]["budget_seconds"], "EFFECT_LATENESS_SLACK_BELOW_30S", kind)
            if ekind == "CONTAINER":
                need(op in K9_CORE_RUNNER_OPS or row["docker"]["network"] != "bridge", "EFFECT_NETWORK_INVALID", kind)
            if op in K9_CORE_RUNNER_OPS:
                runner_op = K9_CORE_RUNNER_OPS[op]
                validate_k9_row(op, runner_op, row, tasks[op]["budget_seconds"], slots_of("CORE", op), a["k9"], k9ctx,
                                files, kind, physical)
                d = decoders[op]
                nb, na = tasks[op]["not_before"], tasks[op]["not_after"]
                need(d["runner_source"] == a["k9"]["runner_source"] and d["k9_request"] == a["k9"]["request"]
                     and d["k9_go"] == a["k9"]["go"] and d["step_plan"] == a["k9"]["plans"][runner_op]
                     and d["provenance_binding_sha256"] == sha(canonical(row))
                     and d["phase_not_before"] == nb and d["phase_not_after"] == na and d["mode"] == a["mode"],
                     "K9_DECODER_ROW_NOT_DERIVED", kind)
            if ekind == "HOST_PROGRAM":
                need(row["source"] in files, "HOST_PROGRAM_SOURCE_UNPINNED", kind)
                need(op == "admission_manifest" or J4_REGISTRY_TOKEN not in row["argv"], "REGISTRY_TOKEN_OUTSIDE_J", kind)
                need(op != "admission_manifest" or (row["argv"].count(J4_REGISTRY_TOKEN) == 1 and a["j4"] is not None
                                                    and a["j4"].get("hot_worker_source") == row["source"]),
                     "J_PROGRAM_REGISTRY_TOKEN_REQUIRED", kind)
                need(op != "admission_manifest" or not physical or files[row["source"]] == J4_HOT_WORKER_SHA256,
                     "J_PROGRAM_NOT_CODEX_J4", kind)
            check_row_paths(row, layout, kind, physical, fx)
    except (fx.Hold, dec.DecodeHold) as error:
        raise kind(str(error)) from None
    imports, initial = a["imports"], q["initial_receipts"]
    need(type(imports) is dict and set(imports) == set(initial), "IMPORTS_TABLE_NOT_CLOSED", kind)
    for role, row in imports.items():
        if type(row) is dict and set(row) == {"source_lot", "request_sha256", "bound_sha256"}:
            need(LOT.fullmatch(row["source_lot"] or "") is not None and row["source_lot"] != a["lot"]
                 and pin(row["request_sha256"]) and pin(row["bound_sha256"]), "IMPORT_ROW_INVALID", kind)
        else:
            need(type(row) is dict and set(row) == {"external_file", "decoder"} and row["external_file"] in files,
                 "IMPORT_ROW_INVALID", kind)
            need(type(row["decoder"]) is dict and row["decoder"].get("kind") == "EXTERNAL_V1"
                 and set(row["decoder"]) == {"kind", "decoder", "verifier"}
                 and row["decoder"]["decoder"] in external and row["decoder"]["verifier"] in external,
                 "IMPORT_DECODER_INVALID", kind)
    for section, keys in (("gate", {"scope", "journal_directory", "snapshot_reader", "snapshot_verifier", "readback"}),
                          ("capacity", {"mode", "lots", "sources", "verifiers", "config_path"}),
                          ("ready", {"mode", "calendar_sha256", "not_before", "not_after", "max_wait_seconds",
                                     "poll_seconds", "ready_path", "verifiers"})):
        value = a[section]
        need(value is None or (type(value) is dict and set(value) == keys), "GATE_SECTION_INVALID", kind)
    validate_sections(a, external, files, kind, physical)
    steps = validate_extended(a, q, layout, fam, set(external), set(files), k9ctx, kind, physical)
    validate_slots(a, q, tasks, steps, fx, kind)
    boot = a["bootstrap"]
    if q["lane"] == "BOOTSTRAP_MONDAY":
        need(type(boot) is dict and set(boot) == {"image_go", "image_go_verifier"} and boot["image_go_verifier"] in external
             and type(boot["image_go"]) is dict and set(boot["image_go"]) == set(tasks), "BOOTSTRAP_TABLE_INVALID", kind)
        for op, row in boot["image_go"].items():
            need(type(row) is dict and set(row) == {"go", "proposal", "documents"} and row["go"] in files
                 and row["proposal"] in files and type(row["documents"]) is list and all(
                     type(d) is list and len(d) == 2 and type(d[0]) is str and d[1] in files for d in row["documents"]),
                 "BOOTSTRAP_TABLE_INVALID", kind)
    else:
        need(boot is None, "BOOTSTRAP_TABLE_INVALID", kind)
    j4 = a["j4"]
    need(j4 is None or (type(j4) is dict and set(j4) == {"protocol", "hot_worker_source", "programs", "originals", "bridge",
                                                         "general_authority_sha256", "general_source_identity"}
         and j4["protocol"] == "WARM_IMAGE10_ACTUAL_OBSERVATION" and j4["hot_worker_source"] in files
         and type(j4["programs"]) is dict and set(j4["programs"]) == set(J4_PROGRAMS)
         and all(pin(v) for v in j4["programs"].values())
         and j4["programs"]["hot_worker"] == files[j4["hot_worker_source"]]
         and type(j4["originals"]) is dict and set(j4["originals"]) == set(J4_ORIGINALS) - set(J4_LOT_ORIGINALS)
         and all(pin(v) for v in j4["originals"].values())
         and type(j4["bridge"]) is dict and set(j4["bridge"]) == {"bootstrap", "authorize", "general_read", "general_verify"}
         and all(type(v) is str and v.isidentifier() for v in j4["bridge"].values())
         and pin(j4["general_authority_sha256"]) and type(j4["general_source_identity"]) is str
         and 0 < len(j4["general_source_identity"]) <= 96 and "admission_manifest" in tasks), "J4_SECTION_INVALID", kind)
    need(j4 is None or j4["programs"]["finite_batch"] == FINITE_BATCH_SHA256, "J4_FINITE_BATCH_NOT_THE_LEDGER_CORE", kind)
    if physical and a["k9"] is not None:
        validate_k9_real(a, files, files_raw, q["lane"], kind)
    return a


def check_row_paths(row, layout, kind, physical, fx):
    """S3/S6: every mount of a row against the denylist (all modes) and the epoch-04 allowlist (physical); receipt
    files only under a writable allowlisted mount. v3.1: no mount of a PARENT of the L12 root / veto / docker-config
    folder (all modes); env files of a row are never under the L12 root, the veto or the docker-config folder, and
    in physical mode an env file under /etc/c3po-reader-e04 belongs ONLY to the session reader (its secret.env is
    never exposed to another unit or container)."""
    for m in fx.row_mounts(row, layout):
        need(not under(m["source"], layout["root"]), "MOUNT_L12_ROOT_FORBIDDEN", kind)
        need(not any(p.startswith(m["source"] + "/") for p in (layout["root"], layout["veto_dir"], layout["docker_config"])),
             "MOUNT_PARENT_OF_PROTECTED_FORBIDDEN", kind)
        need(m["readonly"] or not under(m["source"], layout["veto_dir"]), "MOUNT_VETO_WRITABLE_FORBIDDEN", kind)
        if physical:
            code = epoch04_mount_violation(m["source"], m["readonly"], layout)
            need(code is None, code or "MOUNT_SOURCE_NOT_ALLOWLISTED", kind)
    for path in fx.row_env_files(row, layout):
        need(not any(under(path, p) for p in (layout["root"], layout["veto_dir"], layout["docker_config"])),
             "ENV_FILE_PATH_FORBIDDEN", kind)
        if physical and under(path, EPOCH04_READER_CONFIG):
            need(row["kind"] == "UNIT_START" and row["launch_class"] == "SESSION_READER"
                 and path in [EPOCH04_READER_CONFIG + "/" + leaf for leaf in READER_ENV_LEAVES],
                 "READER_SECRET_ENV_OUTSIDE_THE_READER", kind)
    if physical and row["kind"] == "CONTAINER" and row["receipt"]["source"] == "FILE":
        need(epoch04_path_violation(row["receipt"]["path"], False) is None, "EPOCH04_PATH_GUARD", kind)


def validate_sections(a, external, files, kind, physical):
    """Gate/capacity/ready sections: closed shapes, pinned external verifiers and S6 epoch-04 path guards."""
    g, c, r = a["gate"], a["capacity"], a["ready"]
    if g is not None:
        rb = g["readback"]
        need(type(g["scope"]) is dict and g["snapshot_reader"] in external and g["snapshot_verifier"] in external
             and type(rb) is dict and set(rb) == {"rule", "rule_verifier", "readback_verifier"} and rb["rule"] in files
             and rb["rule_verifier"] in external and rb["readback_verifier"] in external, "GATE_SECTION_INVALID", kind)
        canonical_path(g["journal_directory"], kind)
        need(not physical or g["journal_directory"] == EPOCH04_JOURNAL_ROOT, "GATE_JOURNAL_NOT_EPOCH04", kind)
    if c is not None:
        need(type(c["verifiers"]) is dict and set(c["verifiers"]) == {"rule", "original", "config"}
             and all(v in external for v in c["verifiers"].values()) and type(c["lots"]) is dict
             and set(c["lots"]) == {"m3", "j", "activation"} and all(LOT.fullmatch(v or "") for v in c["lots"].values())
             and type(c["sources"]) is dict and set(c["sources"]) == {"m3", "j", "activation"}
             and all(pin(v) for v in c["sources"].values()) and c["mode"] == a["mode"], "CAPACITY_SECTION_INVALID", kind)
        canonical_path(c["config_path"], kind)
        need(not physical or under(c["config_path"], EPOCH04_CAPACITY_ROOT + "/config"), "CAPACITY_CONFIG_NOT_EPOCH04", kind)
    if r is not None:
        need(type(r["verifiers"]) is dict and set(r["verifiers"]) == {"rule", "ready"}
             and all(v in external for v in r["verifiers"].values()) and r["mode"] == a["mode"] and pin(r["calendar_sha256"])
             and type(r["max_wait_seconds"]) in (int, float) and 0 < r["max_wait_seconds"] <= 120
             and type(r["poll_seconds"]) in (int, float) and 0 < r["poll_seconds"] <= 1
             and stamp(r["not_before"], kind) < stamp(r["not_after"], kind), "READY_SECTION_INVALID", kind)
        canonical_path(r["ready_path"], kind)
        need(not physical or r["ready_path"] == EPOCH04_READY_PATH, "READY_PATH_NOT_EPOCH04", kind)


def validate_extended(a, q, layout, fam, external, files, k9ctx, kind, physical):
    fx, dec = fam.fx, fam.dec
    ext = a["extended"]
    if ext is None:
        return {}
    table = EXTENDED_TABLE.get(q["lane"], {})
    need(type(ext) is dict and set(ext) == {"steps"} and type(ext["steps"]) is list and 0 < len(ext["steps"]) <= 16
         and table, "EXTENDED_TABLE_INVALID", kind)
    steps = {}
    for s in ext["steps"]:
        need(type(s) is dict and set(s) == {"step", "not_before", "not_after", "ceiling_seconds", "requires", "effect",
                                            "decoder", "pre_effect", "hold_until"} and type(s["step"]) is str
             and s["step"] in table and s["step"] not in steps and s["step"] not in a["effects"],
             "EXTENDED_STEP_NOT_IN_CLOSED_TABLE", kind)
        step_kind, runner_op, requires = table[s["step"]]
        need(stamp(s["not_before"], kind) < stamp(s["not_after"], kind), "EXTENDED_WINDOW_INVALID", kind)
        need(type(s["ceiling_seconds"]) is int and 1 <= s["ceiling_seconds"] <= MAX_EXTENDED_CEILING
             and s["ceiling_seconds"] <= (stamp(s["not_after"]) - stamp(s["not_before"])).total_seconds(),
             "EXTENDED_CEILING_INVALID", kind)
        need(type(s["requires"]) is list and sorted(tuple(r) for r in s["requires"] if type(r) is list) == sorted(requires)
             and len(s["requires"]) == len(requires), "EXTENDED_REQUIRES_NOT_THE_CHAIN", kind)
        for kind_, dep in requires:
            need((kind_ == "core" and dep in a["effects"]) or (kind_ == "step" and dep in steps),
                 "EXTENDED_REQUIRES_NOT_DECLARED", kind)
        if step_kind == "READY_CHECK":
            # v3.1: read-only, no effect row, no pre-effect, no hold; needs the signed ready section (its path).
            try:
                dec.validate_decoder_row(s["decoder"], s["step"], None, extended=True, step_kind=step_kind,
                                         external=external, files=files)
            except dec.DecodeHold as error:
                raise kind(str(error)) from None
            need(s["effect"] is None and s["pre_effect"] is None and s["hold_until"] is None and a["ready"] is not None,
                 "EXTENDED_STEP_SHAPE_INVALID", kind)
            need(GATE_ALLOWANCE_SECONDS + EFFECT_LATENESS_SLACK_SECONDS <= s["ceiling_seconds"],
                 "EFFECT_LATENESS_SLACK_BELOW_30S", kind)
            steps[s["step"]] = s
            continue
        try:
            ekind = fx.validate_row(s["effect"], layout)
            dec.validate_decoder_row(s["decoder"], s["step"], ekind, extended=True, step_kind=step_kind,
                                     external=external, files=files)
            if step_kind in ("RUNNER", "CAPTURE"):
                need(ekind == "CONTAINER" and s["pre_effect"] is None and s["hold_until"] is None,
                     "EXTENDED_STEP_SHAPE_INVALID", kind)
                slots = [x for x in a["slots"] if x.get("target_kind") == "EXTENDED" and x.get("target") == s["step"]]
                # CAPTURE: the shell ceiling may exceed the plan budget (capacity chain + two C6 phases around the
                # container); the container KILL stays inside the plan's own run_not_after.
                validate_k9_row(s["step"], runner_op, s["effect"], s["ceiling_seconds"], slots, a["k9"], k9ctx,
                                a["files"], kind, physical, exact_budget=step_kind == "RUNNER")
                floor = fx.row_budget_floor(s["effect"]) + GATE_ALLOWANCE_SECONDS
                if step_kind == "CAPTURE":
                    need(a["gate"] is not None and a["capacity"] is not None, "CAPTURE_GATES_REQUIRED", kind)
                    need(type(a["gate"]["scope"]) is dict
                         and s["effect"]["docker"]["image_id"] == a["gate"]["scope"].get("image_id"),
                         "CAPTURE_IMAGE_NOT_THE_SCOPE_ONE", kind)
                    d = s["decoder"]
                    need(d["kind"] == "K9_STEP_V1" and d["runner_source"] == a["k9"]["runner_source"]
                         and d["k9_request"] == a["k9"]["request"] and d["k9_go"] == a["k9"]["go"]
                         and d["step_plan"] == a["k9"]["plans"][runner_op]
                         and d["provenance_binding_sha256"] == sha(canonical(s["effect"]))
                         and d["phase_not_before"] == s["not_before"] and d["phase_not_after"] == s["not_after"]
                         and d["mode"] == a["mode"], "K9_DECODER_ROW_NOT_DERIVED", kind)
                    floor += 2 * GATE_ALLOWANCE_SECONDS
            else:
                validate_session_start(a, s, layout, fx, kind, physical)
                hold = (stamp(s["hold_until"], kind) - stamp([x for x in a["slots"] if x.get("target") == s["step"]][0]["at"],
                                                              kind)).total_seconds()
                floor = (fx.row_budget_floor(s["pre_effect"]) + a["ready"]["max_wait_seconds"]
                         + fx.row_budget_floor(s["effect"]) + max(0, hold) + 3 * GATE_ALLOWANCE_SECONDS)
            need(floor <= s["ceiling_seconds"], "EXTENDED_CEILING_BELOW_EFFECT", kind)
            need(floor + EFFECT_LATENESS_SLACK_SECONDS <= s["ceiling_seconds"], "EFFECT_LATENESS_SLACK_BELOW_30S", kind)
            for row in (s["effect"], s["pre_effect"]):
                if row is not None:
                    check_row_paths(row, layout, kind, physical, fx)
        except (fx.Hold, dec.DecodeHold) as error:
            raise kind(str(error)) from None
        except IndexError:
            raise kind("EXTENDED_SLOT_ABSENT") from None
        steps[s["step"]] = s
    return steps


def session_unit_rows(layout, *, image, reader_network, supervisor_network, data, journal, capacity, config, state,
                      supervisor_config):
    """v3.1 (finding 1): the EXACT reader and supervisor unit copies (exec words and property list, in the reference
    order) for the given variables. Anything else in a signed session-start row is refused. v3.3f (D-NET): each unit
    has its own network variable (reader and supervisor differ on the host); nothing else of either row changed."""
    docker = layout["binaries"]["docker"]

    def mount(source, target, readonly):
        return ["--mount", "type=bind,source=%s,target=%s%s" % (source, target, ",readonly" if readonly else "")]

    def props(name, mounts_for, conditions):
        return ([["Wants", "network-online.target"], ["Requires", "docker.service"],
                 ["After", "network-online.target docker.service"], ["RequiresMountsFor", " ".join(mounts_for)],
                 ["Type", "exec"], ["Environment", "DOCKER_CONFIG=" + layout["docker_config"]]]
                + [["ExecCondition", "/usr/bin/test -f " + c] for c in conditions]
                + [["ExecStartPre", "-" + docker + " rm " + name],
                   ["ExecStartPre", docker + " image inspect --format {{.Id}} " + image],
                   ["ExecStop", "-" + docker + " stop -t 25 " + name], ["ExecStopPost", "-" + docker + " stop -t 25 " + name],
                   ["Restart", "no"], ["TimeoutStartSec", "60s"], ["TimeoutStopSec", "30s"], ["KillMode", "control-group"],
                   ["UMask", "0077"], ["NoNewPrivileges", "true"], ["StandardOutput", "journal"],
                   ["StandardError", "journal"], ["SyslogIdentifier", name]])
    env_files = [config + "/" + leaf for leaf in READER_ENV_LEAVES]
    reader_exec = ([docker, "run"] + UNIT_DOCKER_HEAD + ["--name", READER_NAME] + UNIT_DOCKER_TAIL
                   + ["--network", reader_network] + UNIT_DOCKER_HARDENING
                   + [w for f in env_files for w in ("--env-file", f)]
                   + mount(data, "/app/day-d-data", True) + mount(journal, CONTAINER_JOURNAL_ROOT, True)
                   + mount(capacity, "/c3po-capacity", True) + mount(config + "/launcher", "/c3po-reader", True)
                   + [image] + READER_COMMAND)
    sup_exec = ([docker, "run"] + UNIT_DOCKER_HEAD + ["--name", SUPERVISOR_NAME] + UNIT_DOCKER_TAIL
                + ["--network", supervisor_network] + UNIT_DOCKER_HARDENING
                + mount(journal, CONTAINER_JOURNAL_ROOT, False) + mount(state, "/var/lib/c3po-bar/supervisor", False)
                + mount(supervisor_config, "/etc/c3po-bar", True) + [image] + SUPERVISOR_MODULE
                + ["--journal-root", CONTAINER_JOURNAL_ROOT, "--manifest-directory", "/etc/c3po-bar/manifests",
                   "--token-file", "/etc/c3po-bar/token", "--state-root", "/var/lib/c3po-bar/supervisor"])
    reader = {"kind": "UNIT_START", "launch_class": "SESSION_READER",
              "unit": {"name": READER_NAME, "description": READER_DESCRIPTION, "exec": reader_exec,
                       "properties": props(READER_NAME, [data, journal, capacity, config], env_files)}}
    sup = {"kind": "UNIT_START", "launch_class": "SUPERVISOR",
           "unit": {"name": SUPERVISOR_NAME, "description": SUPERVISOR_DESCRIPTION, "exec": sup_exec,
                    "properties": props(SUPERVISOR_NAME, [journal, state, supervisor_config], [])}}
    return reader, sup


def validate_session_start(a, s, layout, fx, kind, physical=False):
    """B3: the ONLY reader start of v3. One claim: supervisor (declared pre-effect) -> READY wait (read-only) ->
    recheck -> BEFORE_FIRST_READER -> reader start -> first-cycle hold. v3.1: the WHOLE unit rows are pinned
    (session_unit_rows): exec words, the property list in order, env files (only the reader's three, in the reader's
    config folder, never mounted), mounts (the supervisor's config folder never holds the reader's secret.env), the
    image = the gate scope's image; the step window satisfies the Codex reader gate (open - 90 s <= not_before,
    not_after <= open + 6 h 50) with open = the signed gate scope's session_open, pinned to 13:30:00Z in physical mode."""
    need(a["ready"] is not None and a["gate"] is not None and a["capacity"] is not None, "SESSION_START_GATES_REQUIRED", kind)
    reader, sup = s["effect"], s["pre_effect"]
    need(type(reader) is dict and reader.get("kind") == "UNIT_START" and reader.get("launch_class") == "SESSION_READER"
         and type(sup) is dict and sup.get("kind") == "UNIT_START" and sup.get("launch_class") == "SUPERVISOR",
         "SESSION_START_EFFECTS_INVALID", kind)
    fx.validate_row(sup, layout)
    pr = fx.parse_unit_docker(reader["unit"]["exec"], layout["binaries"]["docker"])
    ps = fx.parse_unit_docker(sup["unit"]["exec"], layout["binaries"]["docker"])
    need(reader["unit"]["name"] == READER_NAME and pr["name"] == READER_NAME and pr["command"] == READER_COMMAND
         and all(m["readonly"] for m in pr["mounts"]), "SESSION_READER_NOT_FIXED_SHAPE", kind)
    cmd = ps["command"]
    need(sup["unit"]["name"] == SUPERVISOR_NAME and ps["name"] == SUPERVISOR_NAME and len(cmd) == 12
         and cmd[:4] == SUPERVISOR_MODULE and tuple(cmd[4::2]) == SUPERVISOR_FLAGS
         and all(canonical_path(p, kind) for p in cmd[5::2]), "SUPERVISOR_NOT_FIXED_SHAPE", kind)
    rm = {m["target"]: m["source"] for m in pr["mounts"]}
    sm = {m["target"]: m["source"] for m in ps["mounts"]}
    launcher = rm.get("/c3po-reader", "")
    need(len(rm) == 4 and len(sm) == 3 and launcher.endswith("/launcher") and "/app/day-d-data" in rm
         and "/c3po-capacity" in rm and CONTAINER_JOURNAL_ROOT in rm and CONTAINER_JOURNAL_ROOT in sm
         and "/var/lib/c3po-bar/supervisor" in sm and "/etc/c3po-bar" in sm and rm[CONTAINER_JOURNAL_ROOT] == sm[CONTAINER_JOURNAL_ROOT]
         and pr["image"] == ps["image"], "SESSION_UNIT_MOUNTS_NOT_PINNED", kind)
    # v3.3f (D-NET): the reader and the supervisor each carry their own network (no longer one shared variable)
    variables = {"image": pr["image"], "reader_network": pr["network"], "supervisor_network": ps["network"],
                 "data": rm["/app/day-d-data"], "journal": rm[CONTAINER_JOURNAL_ROOT], "capacity": rm["/c3po-capacity"],
                 "config": launcher[:-len("/launcher")], "state": sm["/var/lib/c3po-bar/supervisor"],
                 "supervisor_config": sm["/etc/c3po-bar"]}
    canonical_path(variables["config"], kind)
    if physical:
        need(variables == dict(variables, data=DAY_D_DATA, journal=EPOCH04_JOURNAL_ROOT, capacity=EPOCH04_CAPACITY_ROOT,
                               config=EPOCH04_READER_CONFIG, state=EPOCH04_SUPERVISOR_STATE,
                               supervisor_config=EPOCH04_SUPERVISOR_CONFIG), "SESSION_UNIT_PATHS_NOT_EPOCH04", kind)
        # v3.3f (review L2 + D-NET): each unit's --network is ITS constant; any other name (none, host, bridge,
        # default, container:..., c3po_default, the other unit's network) is refused before any effect
        need(variables["reader_network"] == READER_NETWORK_EPOCH04, "SESSION_READER_NETWORK_NOT_DNET", kind)
        need(variables["supervisor_network"] == SUPERVISOR_NETWORK_EPOCH04, "SUPERVISOR_NETWORK_NOT_DNET", kind)
    exp_reader, exp_sup = session_unit_rows(layout, **variables)
    need(reader == exp_reader, "SESSION_READER_UNIT_NOT_PINNED", kind)
    need(sup == exp_sup, "SUPERVISOR_UNIT_NOT_PINNED", kind)
    # the supervisor's own folders never contain the reader's env files (its secret.env reaches the reader only)
    need(not any(under(variables["config"] + "/" + leaf, m["source"]) for m in ps["mounts"] for leaf in READER_ENV_LEAVES),
         "UNIT_MOUNT_EXPOSES_READER_SECRET", kind)
    scope = a["gate"]["scope"]
    need(type(scope) is dict and pr["image"] == scope.get("image_id"), "SESSION_UNIT_IMAGE_NOT_THE_SCOPE_ONE", kind)
    need(not physical or scope.get("session_open") == SESSION_OPEN_UTC, "SESSION_OPEN_NOT_THE_MONDAY_ONE", kind)
    opening = stamp(scope.get("session_open"), kind)
    r = a["ready"]
    nb, na = stamp(s["not_before"], kind), stamp(s["not_after"], kind)
    hold = stamp(s["hold_until"], kind)
    need(opening - timedelta(seconds=SESSION_OPEN_LEAD_SECONDS) <= nb and na <= opening + SESSION_LATEST_AFTER_OPEN,
         "SESSION_START_WINDOW_BEFORE_OPEN_MINUS_90S", kind)
    need(nb <= stamp(r["not_before"], kind) < stamp(r["not_after"], kind) <= na and nb < hold < na,
         "SESSION_START_WINDOWS_INVALID", kind)


def k9_real_source(raw, kind=Hold):
    """v3.3f: the literals of a signed ext/k9_verifiers04.py read by AST (never imported or executed here): its three
    top-level callbacks, its relative names (must be this runtime's), ORIGINAL_PINS {name: sha256} and the Codex-sealed
    APPROVED_REGISTRY_PINS {lot: sha256 of that lot's VERIFIER_POLICY_04}. Each literal is assigned exactly once."""
    import ast
    try:
        tree = ast.parse(raw)
    except (SyntaxError, ValueError):
        raise kind("K9_REAL_VERIFIER_NOT_PYTHON") from None
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    need(set(K9_REAL_CALLBACKS.values()) <= functions, "K9_REAL_VERIFIER_CALLBACKS_ABSENT", kind)
    wanted = set(K9_REAL_SOURCE_RELS) | {"ORIGINAL_PINS", "APPROVED_REGISTRY_PINS"}
    # every binding of a wanted name anywhere in the module (store/del, def/class, import alias, global/nonlocal)
    stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id in wanted and not isinstance(n.ctx, ast.Load)]
    rebinds = [n for n in ast.walk(tree)
               if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name in wanted)
               or (isinstance(n, ast.alias) and (n.asname or n.name) in wanted)
               or (isinstance(n, (ast.Global, ast.Nonlocal)) and set(n.names) & wanted)]
    top = [n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
           and isinstance(n.targets[0], ast.Name) and n.targets[0].id in wanted]
    need(not rebinds and len(stores) == len(top) == len(wanted) and {n.targets[0].id for n in top} == wanted,
         "K9_REAL_VERIFIER_LITERAL_NOT_SINGLE", kind)
    found = {}
    for node in top:
        try:
            found[node.targets[0].id] = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError, RecursionError):
            raise kind("K9_REAL_VERIFIER_LITERAL_NOT_SINGLE") from None
    need(all(found[k] == v for k, v in K9_REAL_SOURCE_RELS.items()), "K9_REAL_VERIFIER_ABI_NOT_THE_DECLARED_ONE", kind)
    pins, allow = found["ORIGINAL_PINS"], found["APPROVED_REGISTRY_PINS"]
    need(type(pins) is dict and 0 < len(pins) <= 16
         and all(type(k) is str and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", k) and pin(v) for k, v in pins.items())
         and type(allow) is dict and all(k in ("UP", "DOWN") and pin(v) for k, v in allow.items()),
         "K9_REAL_VERIFIER_ABI_NOT_THE_DECLARED_ONE", kind)
    return found


def k9_effect_rows(a, lane):
    """{runner operation: its signed effect row} of a lot: core K9 tasks (a.effects) and RUNNER/CAPTURE extended steps."""
    rows = {runner_op: a["effects"][op] for op, runner_op in K9_CORE_RUNNER_OPS.items() if op in a["effects"]}
    for s in (a["extended"] or {}).get("steps", []):
        runner_op = EXTENDED_TABLE.get(lane, {}).get(s["step"], (None, None, None))[1]
        if runner_op is not None:
            rows[runner_op] = s["effect"]
    return rows


def validate_k9_real(a, files, files_raw, lane, kind):
    """v3.3f, PHYSICAL mode, a lot with a K9 section: its REAL files are signed and bound to each other before any
    effect. (1) ext/k9_verifiers04.py, k9/VERIFIER_POLICY_04.json, k9/CURRENT_CODEX_K9_VERIFIER_REVIEW.json and
    k9/K9_GO_04.PUBLICATION.json are signed files; (2) the K9 callbacks are the verifier's three functions and every K9
    decoder row names them; (3) the registry is canonical, of this lot, REAL, and sealed in the signed verifier's
    APPROVED_REGISTRY_PINS; (4) it registers this lot's signed review, publication, GO and K9 request; (5) its originals
    are the verifier's ORIGINAL_PINS, each a signed file at its declared path with that sha256; (6) it registers this
    lot's signed plans and effect rows. Authorship and the content of the originals are the verifier's (Codex) checks;
    a byte that differs from its AUTHORITY pin is refused by the file-pin checks (FILES_BYTES_UNBOUND, LOT_FILE_PIN_CHANGED)."""
    need(files_raw is not None and all(rel in files for rel in K9_REAL_FIXED_FILES), "K9_REAL_FILE_ABSENT", kind)
    external = a["external"]
    need(all(external.get(name) == {"file": K9_REAL_VERIFIER, "identity": identity}
             for name, identity in K9_REAL_CALLBACKS.items()), "K9_REAL_CALLBACK_NOT_THE_VERIFIER", kind)
    decoders = list(a["decoders"].values()) + [s["decoder"] for s in (a["extended"] or {}).get("steps", [])]
    need(all(d.get("verifiers") == {"approval": "k9_approval", "original": "k9_original"} for d in decoders
             if d.get("kind") == "K9_STEP_V1")
         and all(d.get("verifier") == "k9_step" for d in decoders if d.get("kind") == "K9_EXT_STEP_V3"),
         "K9_REAL_CALLBACK_NOT_THE_VERIFIER", kind)
    source = k9_real_source(files_raw[K9_REAL_VERIFIER], kind)
    policy_raw = files_raw[K9_REAL_POLICY]
    try:
        policy = strict(policy_raw, kind=kind)
    except Hold:
        raise kind("K9_REAL_REGISTRY_INVALID") from None
    need(set(policy) == K9_REAL_POLICY_KEYS and policy["schema"] == K9_REAL_POLICY_SCHEMA and policy["mode"] == "REAL"
         and policy["lot"] == a["lot"] and type(policy["originals"]) is dict and type(policy["operations"]) is dict,
         "K9_REAL_REGISTRY_INVALID", kind)
    need(source["APPROVED_REGISTRY_PINS"].get(a["lot"]) == sha(policy_raw), "K9_REAL_REGISTRY_NOT_SEALED_IN_THE_VERIFIER", kind)
    k9 = a["k9"]
    need(policy["review_decision_sha256"] == files[K9_REAL_REVIEW] and policy["publication_sha256"] == files[K9_REAL_PUBLICATION]
         and policy["go_sha256"] == files[k9["go"]] and policy["request_sha256"] == files[k9["request"]],
         "K9_REAL_REGISTRY_NOT_THE_SIGNED_FILES", kind)
    pins, originals = source["ORIGINAL_PINS"], policy["originals"]
    need(set(originals) == set(pins) and all(type(r) is dict and set(r) == {"file", "sha256"} and r["sha256"] == pins[n]
                                             for n, r in originals.items()), "K9_REAL_ORIGINALS_NOT_THE_VERIFIER_ONES", kind)
    reserved = set(K9_REAL_FIXED_FILES) | {k9["runner_source"], k9["request"], k9["go"]} | set(k9["plans"].values())
    paths = [r["file"] for r in originals.values()]
    need(all(type(p) is str and K9_REAL_ORIGINAL_REL.fullmatch(p) and p not in reserved for p in paths)
         and len(set(paths)) == len(paths), "K9_REAL_ORIGINAL_PATH_INVALID", kind)
    need(all(p in files for p in paths), "K9_REAL_ORIGINAL_ABSENT", kind)
    need(all(files[r["file"]] == r["sha256"] for r in originals.values()), "K9_REAL_ORIGINAL_NOT_THE_REGISTERED_ONE", kind)
    rows = k9_effect_rows(a, lane)
    registered = policy["operations"]
    need(all(type(registered.get(op)) is dict and registered[op].get("plan_sha256") == files[rel]
             and op in rows and registered[op].get("effect_sha256") == sha(canonical(rows[op]))
             for op, rel in k9["plans"].items()), "K9_REAL_REGISTRY_OPERATION_NOT_SIGNED", kind)


def validate_slots(a, q, tasks, steps, fx, kind):
    slots = a["slots"]
    need(type(slots) is list and 0 < len(slots) <= 32, "SLOT_TABLE_INVALID", kind)
    seen = set()
    covered = set()
    for s in slots:
        need(type(s) is dict and set(s) == {"slot", "at", "target_kind", "target", "timeout_start_seconds"}
             and type(s["slot"]) is str and SLOT.fullmatch(s["slot"]) is not None and s["slot"] not in seen
             and s["target_kind"] in ("CORE", "EXTENDED")
             and s["target"] in (tasks if s["target_kind"] == "CORE" else steps), "SLOT_TABLE_INVALID", kind)
        seen.add(s["slot"])
        covered.add((s["target_kind"], s["target"]))
        at = stamp(s["at"], kind)
        window, budget = target_window(s["target_kind"], s["target"], tasks, steps, kind)
        need(window[0] <= at - timedelta(seconds=EARLY_SECONDS) and at + timedelta(seconds=LATE_SECONDS) < window[1],
             "SLOT_OUTSIDE_TASK_WINDOW", kind)
        need(type(budget) in (int, float) and s["timeout_start_seconds"] == int(math_ceil(budget)) + CORE_TIMEOUT_MARGIN,
             "SLOT_TIMEOUT_INVALID", kind)
        code = fx.start_minute_violation(at)
        need(code is None, code or "START_MINUTE_FORBIDDEN", kind)
    need(covered == {("CORE", op) for op in tasks} | {("EXTENDED", st) for st in steps}, "SLOT_TABLE_NOT_COVERING", kind)
    times = sorted(stamp(s["at"], kind) for s in slots)
    need(all((b - a_).total_seconds() >= SLOT_SPACING_SECONDS for a_, b in zip(times, times[1:])),
         "SLOTS_TOO_CLOSE", kind)
    for s in slots:
        if s["target_kind"] == "CORE":
            deps = [("CORE", r) for r in tasks[s["target"]]["requires"] if r in tasks]
        else:
            deps = [("CORE" if r[0] == "core" else "EXTENDED", r[1]) for r in steps[s["target"]]["requires"]]
        for dep in deps:
            need(stamp(s["at"], kind) >= target_end(dep[0], dep[1], slots, tasks, steps, kind),
                 "DEPENDENT_SLOT_BEFORE_DEPENDENCY_END", kind)


def target_window(target_kind, target, tasks, steps, kind=Refusal):
    if target_kind == "CORE":
        t = tasks[target]
        return task_window(t, kind), t["budget_seconds"]
    st = steps[target]
    return (stamp(st["not_before"], kind), stamp(st["not_after"], kind)), st["ceiling_seconds"]


def target_end(target_kind, target, slots, tasks, steps, kind=Refusal):
    """The instant after which no alternative of a target can still be running. A slot starts at most LATE_SECONDS
    after its instant and its deadline is min(not_after, start + budget/ceiling), so the end is
    min(not_after, last alternative + LATE_SECONDS + budget). With the F-E plans (not_after = start + budget) this is
    exactly the window end the K9 grid chains on (successor start = predecessor start + budget)."""
    window, budget = target_window(target_kind, target, tasks, steps, kind)
    rows = [s for s in slots if s["target_kind"] == target_kind and s["target"] == target]
    last = max(stamp(s["at"], kind) for s in rows)
    return min(window[1], last + timedelta(seconds=LATE_SECONDS + budget))


def math_ceil(value):
    whole = int(value)
    return whole if whole == value else whole + 1


def validate_owner(owner_raw, request_raw, question_raw, kind=Refusal):
    owner = strict(owner_raw, kind=kind)
    need(set(owner) == {"schema", "answer", "channel", "request_sha256", "question_sha256", "question_published_at",
                        "signed_at"} and owner.get("schema") == "L12_OWNER_RECORD_CANDIDATE_V1"
         and owner.get("answer") == "Assino" and owner.get("channel") == "REGISTRO_PELA_FABLE"
         and owner.get("request_sha256") == sha(request_raw) and owner.get("question_sha256") == sha(question_raw),
         "OWNER_RECORD_UNBOUND", kind)
    owner_time_guard(owner["signed_at"], kind)
    need(stamp(owner["question_published_at"], kind) <= stamp(owner["signed_at"], kind), "OWNER_CHRONOLOGY_INVALID", kind)
    return owner


# ------------------------------------------------------------------ host probe (tests substitute it)
class HostProbe:
    def platform(self):
        return sys.platform

    def euid(self):
        return os.geteuid()

    def boot_id(self):
        return read_boot_id()

    def python_version(self):
        return "%d.%d.%d" % sys.version_info[:3]


def measure(layout, probe, now, execution_mode):
    """Read-only. The PRIVATE runtime document (paths, inodes): never published."""
    validate_layout(layout)
    sources = {}
    src = child(layout, "src")
    for rel in SHELL_SOURCES + CORE_SOURCES:
        sources[rel] = sha(read_path(src + "/" + rel, 2 * LIMIT))
    need(sources["vendor/finite_batch.py"] == FINITE_BATCH_SHA256, "CORE_PIN_NOT_R6", Refusal)
    python_info = os.lstat(layout["python"])
    need(stat.S_ISREG(python_info.st_mode), "PYTHON_NOT_REGULAR", Refusal)
    binaries = {}
    for name, path in sorted(layout["binaries"].items()):
        info = os.lstat(path)
        need(stat.S_ISREG(info.st_mode), "BINARY_NOT_REGULAR", Refusal)
        binaries[name] = {"path": path, "sha256": sha(read_path(path, EXE_LIMIT)), "identity": file_identity9(info)}
    ledger = os.lstat(child(layout, "ledger") + "/" + LEDGER_FILE)
    need(stat.S_ISREG(ledger.st_mode) and stat.S_IMODE(ledger.st_mode) == 0o600 and ledger.st_nlink == 1,
         "LEDGER_FILE_POLICY", Refusal)
    election = {"root_chain": chain_identities(layout["root"]),
                "children": {name: dir_identity(os.lstat(child(layout, name))) for name in CHILDREN},
                "vendor": dir_identity(os.lstat(src + "/vendor")),
                "ledger_file": ledger_identity6(ledger),
                "veto_chain": chain_identities(layout["veto_dir"]),
                "docker_config": chain_identities(layout["docker_config"])}
    for name, row in election["children"].items():
        need(row[2] == probe.euid() and row[4] == 0o700, "CHILD_NOT_PRIVATE", Refusal)
    need(election["root_chain"][-1][1][2] == probe.euid() and election["root_chain"][-1][1][4] == 0o700,
         "ROOT_NOT_PRIVATE", Refusal)
    need(election["veto_chain"][-1][1][2] == probe.euid() and not election["veto_chain"][-1][1][4] & 0o077,
         "VETO_DIRECTORY_NOT_PRIVATE", Refusal)
    need(election["docker_config"][-1][1][2] == probe.euid() and election["docker_config"][-1][1][4] == 0o700,
         "DOCKER_CONFIG_NOT_PRIVATE", Refusal)
    return {"schema": RUNTIME_SCHEMA, "measured_at": iso(now), "layout_sha256": sha(canonical(layout)),
            "platform": probe.platform(), "executor_uid": probe.euid(), "boot_id_sha256": sha(probe.boot_id()),
            "python": {"path": layout["python"], "version": probe.python_version(),
                       "sha256": sha(read_path(layout["python"], EXE_LIMIT)), "identity": file_identity9(python_info)},
            "execution_mode": execution_mode, "sources": sources, "binaries": binaries, "election": election}


def runtime_equal(a, b):
    return {k: v for k, v in a.items() if k != "measured_at"} == {k: v for k, v in b.items() if k != "measured_at"}


class Identity:
    """The installed runtime's own recheck of executor, boot, interpreter, binaries, pinned tree and sources."""

    def __init__(self, runtime, layout, probe, fam):
        self.runtime, self.layout, self.probe, self.fam = runtime, layout, probe, fam
        self._sha_cache = {}

    def binary_sha(self, path, identity):
        key = (path, tuple(identity))
        if key not in self._sha_cache:
            self._sha_cache[key] = sha(read_path(path, EXE_LIMIT, Hold))
        return self._sha_cache[key]

    def check(self):
        r, p = self.runtime, self.probe
        need(p.platform() == r["platform"] and p.euid() == r["executor_uid"] == os.geteuid(), "EXECUTOR_CHANGED")
        need(sha(p.boot_id()) == r["boot_id_sha256"], "BOOT_CHANGED")
        need(p.python_version() == r["python"]["version"], "PYTHON_VERSION_CHANGED")
        info = os.lstat(r["python"]["path"])
        need(file_identity9(info) == r["python"]["identity"]
             and self.binary_sha(r["python"]["path"], r["python"]["identity"]) == r["python"]["sha256"], "PYTHON_CHANGED")
        for name, row in r["binaries"].items():
            need(row["path"] == self.layout["binaries"][name], "BINARY_PATH_CHANGED")
            info = os.lstat(row["path"])
            need(file_identity9(info) == row["identity"] and self.binary_sha(row["path"], row["identity"]) == row["sha256"],
                 "BINARY_CHANGED")
        e = r["election"]
        for name in CHILDREN:
            os.close(open_chain(e["root_chain"] + [[child(self.layout, name), e["children"][name]]]))
        os.close(open_chain(e["veto_chain"]))
        os.close(open_chain(e["docker_config"]))
        src_fd = open_chain(e["root_chain"] + [[child(self.layout, "src"), e["children"]["src"]]])
        try:
            vfd = os.open("vendor", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=src_fd)
            try:
                need(dir_identity(os.fstat(vfd)) == e["vendor"], "VENDOR_DIRECTORY_CHANGED")
            finally:
                os.close(vfd)
            for rel, raw in self.fam.raw.items():
                current = read_rel(src_fd, rel, 2 * LIMIT, Hold)
                need(current == raw and sha(current) == r["sources"][rel], "SOURCE_BYTES_CHANGED")
        finally:
            os.close(src_fd)
        lst = os.lstat(child(self.layout, "ledger") + "/" + LEDGER_FILE)
        need(ledger_identity6(lst) == e["ledger_file"], "LEDGER_FILE_CHANGED")


# ------------------------------------------------------------------ J4 registry: a derived output after BOUND
def file_record(path):
    """{path, sha256, ancestors} of a held file, ancestors = live [name, [dev, ino, uid, gid, mode]] of its parents."""
    canonical_path(path, Hold)
    parent = path.rsplit("/", 1)[0] or "/"
    rows = [[name, dir_identity(os.lstat(name))] for name in (["/"] if parent == "/" else chain(parent))]
    for name, _ in rows:
        need(not os.path.islink(name), "RECORD_ANCESTOR_SYMLINK")
    return {"path": path, "sha256": sha(read_path(path, LIMIT, Hold)), "ancestors": rows}


def j4_registry_record(view):
    path = child(view.layout, "lots") + "/" + view.lot + "/derived/" + DERIVED_REGISTRY
    record = file_record(path)
    need(record["sha256"] == sha(view.derived(DERIVED_REGISTRY)), "J4_REGISTRY_CHANGED")
    return base64.b64encode(canonical(record)).decode("ascii")


def j4_registry_check(raw, view, ledger_pins):
    """Derivation rule of the J4 registry (Codex J4 contract: derived after REQUEST/BOUND, never signed inside them).
    Every field is fixed by the signed authority/j4 section or by the installed lot's own bytes and live identities."""
    j4, q = view.authority["j4"], view.q
    need(j4 is not None, "J4_SECTION_ABSENT")
    r = strict(raw, LIMIT, Hold)
    task = [t for t in q["tasks"] if t["operation"] == "admission_manifest"][0]
    need(set(r) == {"schema", "mode", "protocol", "epoch", "day", "programs", "originals", "bridge", "ledger", "outer_scope",
                    "authority_sha256", "general_authority_sha256", "general_source_identity", "not_before", "not_after"}
         and r["schema"] == "R2D2_HOT_IMAGE10_REGISTRY_CANDIDATE_V1" and r["mode"] == view.mode
         and r["protocol"] == j4["protocol"] and r["epoch"] == q["epoch"] and r["day"] == q["session"]
         and r["bridge"] == j4["bridge"] and r["authority_sha256"] == q["authority_sha256"]
         and r["general_authority_sha256"] == j4["general_authority_sha256"]
         and r["general_source_identity"] == j4["general_source_identity"]
         and r["outer_scope"] == list(view.context) + ["admission_manifest"]
         and r["not_before"] == task["not_before"] and r["not_after"] == task["not_after"], "J4_REGISTRY_NOT_DERIVED")
    need(r["ledger"] == {"root": child(view.layout, "ledger"),
                         "pins": [[[n, list(row)] for n, row in ledger_pins[0]], list(ledger_pins[1])]},
         "J4_REGISTRY_LEDGER_UNBOUND")
    need(type(r["programs"]) is dict and set(r["programs"]) == set(J4_PROGRAMS)
         and type(r["originals"]) is dict and set(r["originals"]) == set(J4_ORIGINALS), "J4_REGISTRY_SETS_INVALID")
    expected = dict(j4["programs"])
    for name, record in list(r["programs"].items()) + list(r["originals"].items()):
        need(type(record) is dict and set(record) == {"path", "sha256", "ancestors"}, "J4_REGISTRY_RECORD_INVALID")
        need(file_record(record["path"]) == record, "J4_REGISTRY_RECORD_NOT_LIVE")
    for name, record in r["programs"].items():
        need(record["sha256"] == expected[name], "J4_PROGRAM_PIN_CHANGED")
    lot_dir = child(view.layout, "lots") + "/" + view.lot
    for name, record in r["originals"].items():
        if name in J4_LOT_ORIGINALS:
            need(record["path"] == lot_dir + "/" + J4_LOT_ORIGINALS[name]
                 and record["sha256"] == sha(view.files[J4_LOT_ORIGINALS[name]]), "J4_LOT_ORIGINAL_UNBOUND")
        else:
            need(record["sha256"] == j4["originals"][name], "J4_ORIGINAL_PIN_CHANGED")
    return r


# ------------------------------------------------------------------ an installed (or staged) lot, read-only
class LotView:
    """One lot: its signed files (held, pinned) and its lazily loaded external modules. Used for the lot of the slot,
    read-only for the source lot of an imported original, and (preview-stage) for a staged lot before any write."""

    def __init__(self, fam, parent_fd, dirname, lot, layout, kind=Refusal, *, physical=False):
        self.fam, self.lot, self.layout, self.physical = fam, lot, layout, physical
        try:
            fd = os.open(dirname, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except OSError:
            raise kind("LOT_DIRECTORY_UNAVAILABLE") from None
        try:
            info = os.fstat(fd)
            need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, "LOT_DIRECTORY_NOT_PRIVATE", kind)
            self.identity = dir_identity(info)
            self.files = {name: read_at(fd, name, LIMIT, kind) for name in LOT_FILES}
            request = strict(self.files["request.json"], kind=kind)
            need(sha(self.files["authority.json"]) == request.get("authority_sha256")
                 and sha(self.files["runtime.json"]) == request.get("runtime_sha256"), "LOT_PINS_UNBOUND", kind)
            self.authority = strict(self.files["authority.json"], kind=kind)
            need(self.authority.get("lot") == lot, "LOT_DIRECTORY_NOT_SIGNED", kind)
            table = self.authority.get("files")
            need(type(table) is dict and len(table) <= 64, "FILES_TABLE_INVALID", kind)
            self.extra = {}
            for rel, digest in sorted(table.items()):
                need(type(rel) is str and REL.fullmatch(rel) is not None, "FILES_TABLE_INVALID", kind)
                raw = read_rel(fd, rel, LIMIT, kind)
                need(sha(raw) == digest, "LOT_FILE_PIN_CHANGED", kind)
                self.extra[rel] = raw
        finally:
            os.close(fd)
        fb = fam.fb
        try:
            self.q = fb.validate_plan(self.files["request.json"])
        except fb.Hold as error:
            raise kind(str(error)) from None
        validate_authority(self.authority, self.q, fam, kind, physical=physical, files_raw=self.extra)
        self.owner = validate_owner(self.files["owner.json"], self.files["request.json"], self.files["question.txt"], kind)
        self.bundle = fb.Bundle(self.files["request.json"], self.files["bound.json"],
                                (("authority", self.files["authority.json"]), ("owner", self.files["owner.json"]),
                                 ("runtime", self.files["runtime.json"])))
        try:
            self.bundle.validate(self.q)
        except fb.Hold as error:
            raise kind(str(error)) from None
        self.mode = self.authority["mode"]
        self.request_sha256, self.bound_sha256 = sha(self.files["request.json"]), sha(self.files["bound.json"])
        self.context = fb.context(self.q)
        self.modules = {}
        self.resolver = None
        self.decoders = fam.dec.Decoders(self, fb, fam.k9, fam.vb, fam.fx)

    def file(self, rel):
        need(rel in self.extra, "LOT_FILE_ABSENT")
        return self.extra[rel]

    def external(self, name):
        row = self.authority["external"].get(name)
        need(row is not None, "EXTERNAL_MODULE_NOT_SIGNED")
        if name not in self.modules:
            path = child(self.layout, "lots") + "/" + self.lot + "/" + row["file"]
            raw = self.file(row["file"])
            self.modules[name] = load_pinned("l12ext_%s_%s" % (self.lot.lower(), name), raw,
                                             self.authority["files"][row["file"]], path)
        return self.modules[name], row["identity"], self.authority["files"][row["file"]]

    def step(self, name):
        rows = [s for s in (self.authority["extended"] or {}).get("steps", []) if s["step"] == name]
        need(len(rows) == 1, "EXTENDED_STEP_ABSENT")
        return rows[0]

    def decoder_row(self, role, extended=False):
        if extended:
            return self.step(role)["decoder"]
        need(role in self.authority["decoders"], "DECODER_NOT_SIGNED")
        return self.authority["decoders"][role]

    def extended_effect(self, step):
        return self.step(step)["effect"]

    def extended_original(self, step, digest):
        key = sha(canonical(list(self.context) + ["EXTENDED", step]))
        env = read_envelope(self.layout, self.runtime_election(), key)
        need(sha(env["original"]) == digest and env["role"] == step and env["request_sha256"] == self.request_sha256
             and env["bound_sha256"] == self.bound_sha256, "EXTENDED_ORIGINAL_CHANGED")
        return env["original"]

    def derived(self, name):
        """A derived output installed AFTER BOUND (never a signed file): read by held descriptors, then re-checked by
        its derivation rule by the caller."""
        election = self.runtime_election()
        lots_fd = open_chain(election["root_chain"] + [[child(self.layout, "lots"), election["children"]["lots"]]])
        try:
            fd = os.open(self.lot, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=lots_fd)
            try:
                need(dir_identity(os.fstat(fd)) == self.identity, "LOT_DIRECTORY_CHANGED")
                return read_rel(fd, "derived/" + name, LIMIT, Hold)
            finally:
                os.close(fd)
        finally:
            os.close(lots_fd)

    def private_evidence(self, key, label):
        election = self.runtime_election()
        fd = open_chain(election["root_chain"] + [[child(self.layout, "receipts"), election["children"]["receipts"]]])
        try:
            return read_at(fd, "%s.%s" % (key, label), LIMIT, Hold)
        finally:
            os.close(fd)

    def resolve(self, lot):
        need(self.resolver is not None, "LOT_RESOLVER_ABSENT")
        return self.resolver(lot)

    def runtime_election(self):
        return strict(self.files["runtime.json"], kind=Hold)["election"]


def read_envelope(layout, election, key):
    fd = open_chain(election["root_chain"] + [[child(layout, "receipts"), election["children"]["receipts"]]])
    try:
        raw = read_at(fd, key + ".json", 2 * LIMIT, Hold)
    finally:
        os.close(fd)
    env = strict(raw, 2 * LIMIT, Hold)
    need(set(env) == {"schema", "origin", "attempt_key", "role", "context", "completed_at", "original_sha256",
                      "original_b64", "request_sha256", "bound_sha256"} and env["schema"] == ENVELOPE_SCHEMA
         and env["attempt_key"] == key, "RECEIPT_ENVELOPE_INVALID")
    original = base64.b64decode(env["original_b64"], validate=True)
    need(sha(original) == env["original_sha256"], "RECEIPT_ENVELOPE_INVALID")
    env["original"] = original
    return env


def make_envelope(origin, key, role, context, completed_at, original, request_sha256, bound_sha256):
    return canonical({"schema": ENVELOPE_SCHEMA, "origin": origin, "attempt_key": key, "role": role,
                      "context": list(context), "completed_at": iso(completed_at), "original_sha256": sha(original),
                      "original_b64": base64.b64encode(original).decode("ascii"),
                      "request_sha256": request_sha256, "bound_sha256": bound_sha256})


def physical_guard(runtime, layout, kind=Refusal):
    """The timer/preview runs the INSTALLED copy with the measured interpreter, as root, on the measured Linux host.
    Kept as is from v2 (Codex B2: never relaxed to make a preview pass)."""
    need(sys.platform == "linux" and os.geteuid() == 0 == runtime.get("executor_uid")
         and os.path.realpath(__file__) == child(layout, "src") + "/l12host_runtime.py"
         and os.path.realpath(sys.executable) == runtime["python"]["path"], "RUNTIME_NOT_INSTALLED_COPY", kind)


def load_family(runtime, layout):
    e = runtime["election"]
    src_fd = open_chain(e["root_chain"] + [[child(layout, "src"), e["children"]["src"]]], Refusal)
    try:
        return Family(src_fd, child(layout, "src"), runtime["sources"])
    finally:
        os.close(src_fd)


# ------------------------------------------------------------------ the shell around one lot
class Shell:
    def __init__(self, lot_dir, *, probe=None, physical=True, slot_clock=None):
        canonical_path(lot_dir)
        # slot_clock exists only for in-process fixtures (pre-start window of a synthetic schedule); never on host.
        need(slot_clock is None or not physical, "SLOT_CLOCK_INJECTION_FORBIDDEN", Refusal)
        self.slot_clock = slot_clock or native_utc
        self.lot_dir = lot_dir
        self.probe = probe or HostProbe()
        self.physical = physical
        self.entered = False
        self.last_veto = None
        self.ledger = None
        self.current = None
        self.invocation = None
        self.stored = {}
        fd = os.open(lot_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            runtime_raw = read_at(fd, "runtime.json", LIMIT)
            authority_raw = read_at(fd, "authority.json", LIMIT)
        finally:
            os.close(fd)
        self.runtime = strict(runtime_raw)
        layout = validate_layout(strict(authority_raw).get("layout"))
        need(self.runtime.get("schema") == RUNTIME_SCHEMA and self.runtime.get("layout_sha256") == sha(canonical(layout)),
             "RUNTIME_LAYOUT_UNBOUND", Refusal)
        self.layout = layout
        if physical:
            physical_guard(self.runtime, layout)
        lot = lot_dir.rsplit("/", 1)[1]
        need(LOT.fullmatch(lot) is not None and lot_dir == child(layout, "lots") + "/" + lot, "LOT_DIRECTORY_NOT_SIGNED", Refusal)
        e = self.runtime["election"]
        self.fam = load_family(self.runtime, layout)
        lots_fd = open_chain(e["root_chain"] + [[child(layout, "lots"), e["children"]["lots"]]], Refusal)
        try:
            self.view = LotView(self.fam, lots_fd, lot, lot, layout, Refusal, physical=physical)
        finally:
            os.close(lots_fd)
        need(self.view.files["runtime.json"] == runtime_raw and self.view.files["authority.json"] == authority_raw,
             "LOT_BYTES_CHANGED", Refusal)
        self.authority, self.q, self.bundle = self.view.authority, self.view.q, self.view.bundle
        self.context = self.view.context
        self.tasks = {t["operation"]: t for t in self.q["tasks"]}
        self.slots = {s["slot"]: s for s in self.authority["slots"]}
        self.request_sha256, self.bound_sha256 = self.view.request_sha256, self.view.bound_sha256
        self.import_views = {}
        self.view.resolver = self.import_view
        self.ident = Identity(self.runtime, layout, self.probe, self.fam)

    # ---------------------------------------------------------- pre-start
    def slot_window(self, slot, now, kind=Hold):
        at = stamp(self.slots[slot]["at"])
        need(at - timedelta(seconds=EARLY_SECONDS) <= now <= at + timedelta(seconds=LATE_SECONDS),
             "START_OUTSIDE_SLOT_WINDOW", kind)
        code = self.fam.fx.start_minute_violation(now)
        need(code is None, code or "START_MINUTE_FORBIDDEN", kind)
        return self.slots[slot]

    def revoked(self):
        return os.path.lexists(self.lot_dir + "/" + REVOKED)

    def start_marker(self, row, key, scope, now):
        """O_EXCL start marker of the LOGICAL attempt; any pre-existing marker refuses every alternative."""
        e = self.runtime["election"]
        fd = open_chain(e["root_chain"] + [[child(self.layout, "starts"), e["children"]["starts"]]])
        try:
            raw = canonical({"schema": START_SCHEMA, "attempt_key": key, "scope": scope, "lot": self.authority["lot"],
                             "slot": row["slot"], "target_kind": row["target_kind"], "target": row["target"],
                             "request_sha256": self.request_sha256, "bound_sha256": self.bound_sha256, "at": iso(now)})
            try:
                write_new_at(fd, "start-" + key, raw, 0o400)
            except FileExistsError:
                return "PRESENT"
            return "CREATED"
        finally:
            os.close(fd)

    def start_marker_present(self, key):
        e = self.runtime["election"]
        fd = open_chain(e["root_chain"] + [[child(self.layout, "starts"), e["children"]["starts"]]])
        try:
            raw = read_at(fd, "start-" + key, 4096, Hold)
        finally:
            os.close(fd)
        marker = strict(raw, 4096, Hold)
        need(marker.get("attempt_key") == key and marker.get("request_sha256") == self.request_sha256
             and marker.get("bound_sha256") == self.bound_sha256, "START_MARKER_NOT_THIS_ATTEMPT")

    # ---------------------------------------------------------- ledger
    def ledger_pins(self):
        e = self.runtime["election"]
        rows = [(name, tuple(row)) for name, row in e["root_chain"]] + [(child(self.layout, "ledger"),
                                                                       tuple(e["children"]["ledger"]))]
        return tuple(rows), tuple(e["ledger_file"])

    def open_ledger(self):
        return self.fam.fb.DurableLedger(child(self.layout, "ledger"), self.ledger_pins(),
                                         lock_budget_seconds=LEDGER_LOCK_BUDGET,
                                         finish_budget_seconds=LEDGER_FINISH_BUDGET)

    # ---------------------------------------------------------- Services callbacks (outer worker)
    def task_now(self, target_kind, target, now):
        if target_kind == "CORE":
            row = self.tasks[target]
        else:
            row = self.view.step(target)
        need(stamp(row["not_before"], Hold) <= now < stamp(row["not_after"], Hold), "SHELL_WINDOW_CLOSED")

    def authority_check(self, target_kind, target, now):
        """Re-read the installed bytes, the shell ABI, the owner guard and REVOKED."""
        fd = os.open(self.lot_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            need(dir_identity(os.fstat(fd)) == self.view.identity, "LOT_DIRECTORY_CHANGED")
            for name in LOT_FILES:
                need(read_at(fd, name, LIMIT, Hold) == self.view.files[name], "LOT_BYTES_CHANGED")
            for rel, raw in self.view.extra.items():
                need(read_rel(fd, rel, LIMIT, Hold) == raw, "LOT_BYTES_CHANGED")
        finally:
            os.close(fd)
        need(not self.revoked(), "LOT_REVOKED")
        validate_authority(self.authority, self.q, self.fam, Hold, physical=self.physical, files_raw=self.view.extra)
        validate_owner(self.view.files["owner.json"], self.view.files["request.json"], self.view.files["question.txt"], Hold)
        need(stamp(self.view.owner["signed_at"], Hold) < now, "CLOCK_NOT_AFTER_OWNER")
        if target_kind == "CORE":
            need(target in self.tasks and target in self.authority["effects"], "OPERATION_NOT_SIGNED")
        self.task_now(target_kind, target, now)

    def authority_service(self, bundle, q, task, now):
        need(bundle is self.bundle and q == self.q, "BUNDLE_CHANGED")
        self.authority_check("CORE", task["operation"], native_utc())

    def identity_check(self):
        self.ident.check()

    def identity(self, bundle, q, task, now):
        self.identity_check()

    def observe_veto(self, now):
        e = self.runtime["election"]
        fd = open_chain(e["veto_chain"])
        try:
            entries = sorted(os.listdir(fd))
            info = os.fstat(fd)
        finally:
            os.close(fd)
        identity = dir_identity(info)
        need(identity == e["veto_chain"][-1][1], "VETO_DIRECTORY_CHANGED")
        veto = self.authority["veto"]
        until = now + timedelta(seconds=veto["maximum_age_seconds"])
        verdict = "ALLOW" if not entries else "VETO"
        raw = canonical({"schema": VETO_OBSERVATION_SCHEMA, "directory": veto["directory"], "identity": identity,
                         "entries": len(entries), "entries_sha256": sha(canonical(entries)), "verdict": verdict,
                         "observed_at": iso(now), "valid_until": iso(until),
                         "veto_authority_sha256": sha(canonical(veto))})
        return raw, verdict, until

    def fresh_allow(self):
        """Two observations of the pinned folder, ALLOW both times, same identity; the first one is the ALLOW used."""
        observed = native_utc()
        raw, verdict, until = self.observe_veto(observed)
        need(verdict == "ALLOW", "VETO_PRESENT")
        raw2, verdict2, _ = self.observe_veto(native_utc())
        need(verdict2 == "ALLOW" and strict(raw2, kind=Hold)["identity"] == strict(raw, kind=Hold)["identity"],
             "VETO_PRESENT")
        self.last_veto = self.fam.fb.VetoView(raw, sha(canonical(self.authority["veto"])), verdict, observed, until)
        return self.last_veto

    def veto_read(self, q, task, now):
        observed = native_utc()
        raw, verdict, until = self.observe_veto(observed)
        view = self.fam.fb.VetoView(raw, sha(canonical(self.authority["veto"])), verdict, observed, until)
        self.last_veto = view
        return view

    def veto_verify(self, veto, q, task, now):
        need(veto is self.last_veto and veto.verdict == "ALLOW", "VETO_PRESENT")
        seen = strict(veto.raw, kind=Hold)
        need(seen["verdict"] == "ALLOW" and seen["veto_authority_sha256"] == q["veto_authority_sha256"]
             and seen["observed_at"] == iso(veto.observed_at) and seen["valid_until"] == iso(veto.valid_until),
             "VETO_OBSERVATION_INVALID")
        raw, verdict, _ = self.observe_veto(native_utc())
        need(verdict == "ALLOW" and strict(raw, kind=Hold)["identity"] == seen["identity"], "VETO_PRESENT")

    def before_effect(self, row=None, deadline_utc=None):
        """BEFORE_EFFECT hook: same ALLOW (never renewed), pinned folder identity, zero entries, start minute, and the
        remaining budget still covers the effect floor (gates and waits consumed real time)."""
        veto = self.last_veto
        need(veto is not None and veto.verdict == "ALLOW", "VETO_NOT_OBSERVED_BEFORE_EFFECT")
        try:
            now = self.fam.fx.before_effect(self.layout["veto_dir"], self.runtime["election"]["veto_chain"][-1][1],
                                            veto.valid_until, native_utc, minute=True)
        except self.fam.fx.Hold as error:
            raise Hold(str(error)) from None
        if row is not None and deadline_utc is not None:
            need((deadline_utc - now).total_seconds() >= self.fam.fx.row_budget_floor(row),
                 "BUDGET_REMAINING_BELOW_EFFECT_FLOOR")
        return now

    def operation_gate(self, bundle, q, task, dependencies, now):
        op = task["operation"]
        need(not self.revoked(), "LOT_REVOKED")
        need(self.current == op, "OPERATION_NOT_CURRENT_SLOT")
        self.start_marker_present(target_key(self.fam.fb, self.q, "CORE", op)[0])
        self.effect_preflight(self.authority["effects"][op])
        if op == "admission_manifest":
            j4_registry_check(self.view.derived(DERIVED_REGISTRY), self.view, self.ledger_pins())
        code = self.fam.fx.start_minute_violation(native_utc())
        need(code is None, code or "START_MINUTE_FORBIDDEN")

    def effect_preflight(self, row):
        fx = self.fam.fx
        uid = self.runtime["executor_uid"]
        try:
            fx.validate_row(row, self.layout)
            for path in fx.row_env_files(row, self.layout):
                fx.check_secret_file(path, uid)
            for m in fx.row_mounts(row, self.layout):
                fx.check_mount_source(m["source"], uid)
            if row["kind"] in ("CONTAINER", "UNIT_START"):
                fx.check_docker_config(self.layout["docker_config"], uid)
            if row["kind"] == "CONTAINER" and row["receipt"]["source"] == "FILE":
                need(not os.path.lexists(row["receipt"]["path"]), "RECEIPT_DESTINATION_PRESENT")
            if row["kind"] == "CONTAINER":
                self.k9_host_bytes(row)
        except fx.Hold as error:
            raise Hold(str(error)) from None

    def k9_host_bytes(self, row):
        """A K9 row runs the signed runner and plan only: the host copies under the mounted tools/day roots must be
        byte-equal to the lot's signed files right before the effect (nothing runs outside the declared table)."""
        k9 = self.authority["k9"]
        command = row["docker"]["command"]
        if k9 is None or len(command) != 7 or not command[2].startswith(K9_TOOLS_TARGET + "/k9_runner04-"):
            return
        targets = {m["target"]: m["source"] for m in row["docker"]["mounts"]}
        runner_name = command[2][len(K9_TOOLS_TARGET) + 1:]
        op = command[4][len(K9_DAY_TARGET + "/plans/"):-len(".json")]
        need(read_path(targets[K9_TOOLS_TARGET] + "/" + runner_name, 2 * LIMIT, Hold) == self.view.file(k9["runner_source"]),
             "K9_HOST_RUNNER_NOT_THE_SIGNED_ONE")
        need(read_path(targets[K9_DAY_TARGET] + "/plans/" + op + ".json", LIMIT, Hold) == self.view.file(k9["plans"][op]),
             "K9_HOST_PLAN_NOT_THE_SIGNED_ONE")

    # ---------------------------------------------------------- receipts: always decoded by their ABI
    def import_view(self, lot):
        if lot not in self.import_views:
            e = self.runtime["election"]
            lots_fd = open_chain(e["root_chain"] + [[child(self.layout, "lots"), e["children"]["lots"]]])
            try:
                view = LotView(self.fam, lots_fd, lot, lot, self.layout, Hold, physical=self.physical)
            finally:
                os.close(lots_fd)
            view.resolver = self.import_view
            self.import_views[lot] = view
        return self.import_views[lot]

    def verification_invocation(self, role, request_sha256, bound_sha256, seconds=60):
        fb = self.fam.fb
        return fb.Invocation(role, self.context, request_sha256, bound_sha256,
                             native_utc() + timedelta(seconds=seconds), time.monotonic() + seconds, ())

    def receipt_read(self, role, context):
        need(tuple(context) == self.context, "RECEIPT_CONTEXT_INVALID")
        key = sha(canonical(list(context) + [role]))
        if role in self.q["initial_receipts"]:
            row = self.authority["imports"][role]
            if "source_lot" in row:
                source = self.import_view(row["source_lot"])
                need(source.request_sha256 == row["request_sha256"] and source.bound_sha256 == row["bound_sha256"]
                     and source.context == self.context and role in source.authority["decoders"], "IMPORT_SOURCE_LOT_UNBOUND")
                env = read_envelope(self.layout, self.runtime["election"], key)
                need(env["request_sha256"] == row["request_sha256"] and env["bound_sha256"] == row["bound_sha256"]
                     and env["role"] == role, "IMPORT_ENVELOPE_UNBOUND")
                invocation = self.verification_invocation(role, row["request_sha256"], row["bound_sha256"])
                return source.decoders.decode(role, env["original"], invocation,
                                              effect_row=source.authority["effects"].get(role), stored=True)
            raw = self.view.file(row["external_file"])
            invocation = self.verification_invocation(role, self.request_sha256, self.bound_sha256)
            return self.view.decoders.external_decode(role, raw, invocation, row["decoder"])
        env = read_envelope(self.layout, self.runtime["election"], key)
        need(env["request_sha256"] == self.request_sha256 and env["bound_sha256"] == self.bound_sha256
             and env["role"] == role, "DEPENDENCY_ENVELOPE_UNBOUND")
        invocation = self.verification_invocation(role, self.request_sha256, self.bound_sha256)
        return self.view.decoders.decode(role, env["original"], invocation, effect_row=self.authority["effects"].get(role),
                                         stored=True)

    def receipt_verify(self, item, q, role, now):
        need(item.context == self.context and item.status == "COMPLETE", "RECEIPT_NOT_COMPLETE")
        if role == self.current:
            need(self.stored.get(role) == sha(item.raw), "RECEIPT_NOT_THIS_EFFECT")
            return None
        if role in q["initial_receipts"]:
            row = self.authority["imports"][role]
            if "source_lot" in row:
                # Provenance: the SOURCE lot's own durable OUTER COMPLETE terminal for this exact original.
                self.ledger.dependency(self.context + (role,), row["request_sha256"], row["bound_sha256"], item)
        return None

    # ---------------------------------------------------------- bounded execute (runner built at effect time)
    def command(self, op, row, veto):
        br, fb = self.fam.br, self.fam.fb
        r, e = self.runtime, self.runtime["election"]
        key = target_key(fb, self.q, "CORE", op)[0]
        if row["kind"] == "HOST_PROGRAM":
            source = self.view.file(row["source"])
            words = list(row["argv"])
            if op == "admission_manifest":
                words[words.index(J4_REGISTRY_TOKEN)] = j4_registry_record(self.view)
            argv = (r["python"]["path"], "-I", "-B", "-") + tuple(words)
        else:
            source = self.fam.raw["l12host_effect.py"]
            argv = (r["python"]["path"], "-I", "-B", "-") + tuple(self.fam.fx.engine_argv(
                self.lot_dir, "CORE", op, self.q["authority_sha256"], self.request_sha256, key, sha(veto.raw),
                iso(veto.valid_until), None))
        return br.Command(op, self.context, self.request_sha256, self.bound_sha256, argv, source, sha(source), sha(source),
                          (("PATH", "/usr/bin:/bin"), ("LANG", "C.UTF-8"), ("TZ", "UTC")),
                          br.DirectoryPin(child(self.layout, "work"), tuple(e["children"]["work"])),
                          br.ExecutablePin(r["python"]["path"], tuple(r["python"]["identity"]), r["python"]["sha256"]),
                          self.current_pins(op), 262144, 65536, r["execution_mode"])

    def current_pins(self, op):
        row = self.authority["effects"][op]
        source = self.view.file(row["source"]) if row["kind"] == "HOST_PROGRAM" else self.fam.raw["l12host_effect.py"]
        return (("authority", self.q["authority_sha256"]), ("bound", self.bound_sha256),
                ("decoder_row", sha(canonical(self.authority["decoders"][op]))),
                ("effect_row", sha(canonical(row))), ("effect_source", sha(source)),
                ("request", self.request_sha256), ("runtime", self.q["runtime_sha256"]))

    def approval(self, stage, command, registry_sha256, now):
        br = self.fam.br
        return br.Approval(stage, registry_sha256, br.digest(br.canonical(command.body())), command.context,
                           command.current_pins, now, now + timedelta(seconds=APPROVAL_SECONDS))

    def diag(self, key, stage, code):
        """Private diagnostic of a runner callback refusal (the runner maps it to a generic code)."""
        try:
            e = self.runtime["election"]
            fd = open_chain(e["root_chain"] + [[child(self.layout, "work"), e["children"]["work"]]])
            try:
                write_new_at(fd, "diag-%s-%s.json" % (key, stage.lower()),
                             canonical({"attempt_key": key, "stage": stage, "code": code}))
            finally:
                os.close(fd)
        except BaseException:
            pass

    def input_diag(self, key, record):
        """v3.2 (M1): the sink of input_changed inside a slot (any process of the slot: outer worker, runner, extended
        worker). Private, exclusive create, never raises."""
        try:
            self.input_seq = getattr(self, "input_seq", 0) + 1
            e = self.runtime["election"]
            fd = open_chain(e["root_chain"] + [[child(self.layout, "work"), e["children"]["work"]]])
            try:
                write_new_at(fd, "diag-%s-input-%d-%d.json" % (key, os.getpid(), self.input_seq),
                             canonical({"attempt_key": key, "stage": "INPUT", "code": record["code"],
                                        "file": record["file"][-2048:], "changed": record["changed"]}))
            finally:
                os.close(fd)
        except BaseException:
            pass

    def unit_diag(self, key, failure):
        """v3.3: the engine's `unit_start_failure` of a failed UNIT_START (exit code, stderr sha256/size, bounded
        printable excerpt) as a PRIVATE diagnostic of the slot (stage UNIT, one per launch class). Never raises."""
        try:
            cls = failure["launch_class"]
            need(cls in self.fam.fx.LAUNCH_CLASSES, "UNIT_DIAG_INVALID", Hold)
            excerpt = self.fam.fx.stderr_excerpt(str(failure["child_stderr_excerpt"]).encode("ascii", "replace"))
            body = {"attempt_key": key, "stage": "UNIT", "code": "UNIT_START_FAILED", "launch_class": cls,
                    "child_exit_code": int(failure["child_exit_code"]),
                    "child_stderr_sha256": str(failure["child_stderr_sha256"])[:64],
                    "child_stderr_bytes": int(failure["child_stderr_bytes"]), "child_stderr_excerpt": excerpt}
            e = self.runtime["election"]
            fd = open_chain(e["root_chain"] + [[child(self.layout, "work"), e["children"]["work"]]])
            try:
                write_new_at(fd, "diag-%s-unit-%s.json" % (key, cls.lower()), canonical(body))
            finally:
                os.close(fd)
        except BaseException:
            pass

    def runner(self, op, veto, invocation):
        br, fb = self.fam.br, self.fam.fb
        row = self.authority["effects"][op]
        command = self.command(op, row, veto)
        key = target_key(fb, self.q, "CORE", op)[0]
        identity = "l12host_runtime.Shell."
        source_sha = self.runtime["sources"]["l12host_runtime.py"]
        pins = (("AUTHORITY", identity + "authority_check", source_sha), ("RUNTIME", identity + "identity_check", source_sha),
                ("CURRENT_PINS", identity + "before_effect", source_sha), ("RECEIPT_ABI", identity + "decode", source_sha),
                ("RECEIPT_PROVENANCE", identity + "provenance", source_sha))
        registry = br.Registry(os.getuid(), (command,), pins, "INHERITED_OUTER_GROUP")
        registry_sha = br.digest(registry.raw())

        def guarded(stage, fn):
            def run(*args):
                try:
                    return fn(*args)
                except BaseException as error:
                    self.diag(key, stage, safe_code(error))
                    raise
            return run

        def stage_authority(inv, cmd, reg, now):
            self.authority_check("CORE", op, native_utc())
            return self.approval("AUTHORITY", cmd, reg, now)

        def stage_runtime(inv, cmd, reg, now):
            self.identity_check()
            return self.approval("RUNTIME", cmd, reg, now)

        def stage_before_effect(inv, cmd, reg, now):
            need(cmd.current_pins == self.current_pins(op) and sha(cmd.source) == cmd.source_sha256
                 and cmd.source_sha256 == dict(cmd.current_pins)["effect_source"], "CURRENT_PINS_CHANGED")
            self.effect_preflight(row)
            self.before_effect(row, invocation.deadline_utc)
            return self.approval("CURRENT_PINS", cmd, reg, now)

        def decode(transport, inv, cmd):
            if row["kind"] == "HOST_PROGRAM":
                raw = transport.stdout
            else:
                out = self.fam.fx.strict_json(transport.stdout.rstrip(b"\n"), limit=262144)
                need(transport.stdout.endswith(b"\n") and transport.stdout.count(b"\n") == 1, "EFFECT_OUTPUT_FRAMING")
                need(out.get("schema") == self.fam.fx.OUTPUT_SCHEMA and out.get("target") == op
                     and out.get("target_kind") == "CORE" and out.get("context") == list(cmd.context)
                     and out.get("status") == "TRANSPORT_DONE" and out.get("effect_kind") == row["kind"],
                     "EFFECT_OUTPUT_INVALID")
                raw = base64.b64decode(out["original_b64"], validate=True)
                need(sha(raw) == out["original_sha256"], "EFFECT_OUTPUT_INVALID")
            sink = lambda label, data: self.private_evidence(key, label, data)
            receipt = self.view.decoders.decode(op, raw, inv, effect_row=row, private_sink=sink)
            return br.ReceiptView(receipt.raw, cmd.operation, cmd.context, "COMPLETE", receipt.completed_at)

        def provenance(view, transport, inv, cmd):
            if row["kind"] == "CONTAINER" and row["receipt"]["source"] == "FILE":
                need(read_path(row["receipt"]["path"], self.fam.fx.MAX_ORIGINAL, Hold) == view.raw, "RECEIPT_FILE_MISMATCH")
            return True

        callbacks = (stage_authority, stage_runtime, stage_before_effect, decode, provenance)
        bindings = tuple(br.Binding(p[1], p[2], guarded(p[0], cb)) for p, cb in zip(pins, callbacks))
        runner = br.BoundedRunner(registry, registry_sha, authority_verifier=bindings[0], runtime_verifier=bindings[1],
                                  pins_verifier=bindings[2], receipt_decoder=bindings[3], receipt_verifier=bindings[4])
        return runner.service(fb.Receipt)

    def private_evidence(self, key, label, raw):
        e = self.runtime["election"]
        fd = open_chain(e["root_chain"] + [[child(self.layout, "receipts"), e["children"]["receipts"]]])
        try:
            write_new_at(fd, "%s.%s" % (key, label), raw)
        finally:
            os.close(fd)

    def execute(self, invocation):
        op = invocation.operation
        need(op == self.current and self.last_veto is not None, "EXECUTE_NOT_CURRENT")
        original = self.runner(op, self.last_veto, invocation)(invocation)
        key = target_key(self.fam.fb, self.q, "CORE", op)[0]
        # Persist the decoded original before the core's own post-checks; the core's TERMINAL row decides.
        envelope = make_envelope("LEDGER_EFFECT", key, op, original.context, original.completed_at, original.raw,
                                 invocation.request_sha256, invocation.bound_sha256)
        e = self.runtime["election"]
        fd = open_chain(e["root_chain"] + [[child(self.layout, "receipts"), e["children"]["receipts"]]])
        try:
            write_new_at(fd, key + ".json", envelope)
        finally:
            os.close(fd)
        self.stored[op] = sha(original.raw)
        return original

    # ---------------------------------------------------------- gates built from signed sections (or absent)
    def core_codes(self, fn):
        """Shell refusals reach the core's ledger/RESULT as fixed codes (not ADAPTER_OR_IO_FAILURE)."""
        fb, fx, dec, image, br = self.fam.fb, self.fam.fx, self.fam.dec, self.fam.image, self.fam.br

        def inner(*args):
            try:
                return fn(*args)
            except fb.Hold:
                raise
            except (Hold, fx.Hold, dec.DecodeHold, image.Hold, br.RunnerError) as error:
                raise fb.Hold(safe_code(error)) from None
        return inner

    def services(self):
        fb, gates = self.fam.fb, self.fam.ext.Gates(self)
        c = self.core_codes
        boot = self.q["lane"] == "BOOTSTRAP_MONDAY"
        # v3 core has no reader/capture operation: capacity_path and ready_wait stay None (the core refuses
        # REAL_ADAPTER_UNAVAILABLE if a phase operation ever appears); the late session start lives in EXTENDED.
        return fb.Services(authority=c(self.authority_service), identity=c(self.identity), veto_read=c(self.veto_read),
                           veto_verify=c(self.veto_verify), receipt_read=c(self.receipt_read),
                           receipt_verify=c(self.receipt_verify), operation_gate=c(self.operation_gate),
                           capacity_path=None, capacity_dependencies=gates.capacity_dependencies(), ready_wait=None,
                           image_go_read=c(gates.image_go_read) if boot else None,
                           image_go_verify=gates.image_go_verify() if boot else None,
                           execute=c(self.execute))

    # ---------------------------------------------------------- one slot
    def run_slot(self, slot):
        fb = self.fam.fb
        started = self.slot_clock()
        need(slot in self.slots, "SLOT_UNKNOWN", Refusal)
        need(not self.revoked(), "LOT_REVOKED", Refusal)
        row = self.slots[slot]
        key, scope = target_key(fb, self.q, row["target_kind"], row["target"])
        result = {"schema": RESULT_SCHEMA, "lot": self.authority["lot"], "slot": slot, "target_kind": row["target_kind"],
                  "target": row["target"], "scheduled_at": row["at"], "started_at": iso(started),
                  "request_sha256": self.request_sha256, "bound_sha256": self.bound_sha256, "attempt_key": key,
                  "start_marker": None, "status": None, "code": None, "result_class": None, "effect_calls": 0,
                  "recovery_required": None, "outer": None, "extended": None, "diagnostics": [], "completed_at": None,
                  "automatic_retry": False, "operational_GO_granted": False}
        self.entered = True
        try:
            marker = self.start_marker(row, key, scope, started)
        except BaseException as error:
            result.update(start_marker="UNCERTAIN", status="HOLD_START_MARKER_UNCERTAIN", code=safe_code(error),
                          recovery_required=True, completed_at=iso(native_utc()))
            return result
        result["start_marker"] = marker
        if marker == "PRESENT":
            result.update(status="REFUSED_START_CONSUMED", code="LOGICAL_ATTEMPT_ALREADY_STARTED",
                          recovery_required=False, completed_at=iso(native_utc()))
            return result
        # v3.2 (M1): from the marker on, a changed input file is named in the RESULT diagnostics (every branch).
        set_input_sink(lambda record: self.input_diag(key, record))
        try:
            self.run_marked(slot, row, key, scope, started, result)
        finally:
            set_input_sink(None)
        result["diagnostics"] = self.read_diagnostics(key)
        return result

    def run_marked(self, slot, row, key, scope, started, result):
        """The slot after its start marker was CREATED (v3.1 body of run_slot, unchanged)."""
        fb = self.fam.fb
        try:
            self.slot_window(slot, started)
        except Hold as error:
            # The marker exists: the slot fired; a late/early/forbidden-minute start consumes the logical attempt and
            # never hands it to a later alternative.
            result.update(status="REFUSED_CONSUMED_START", code=safe_code(error), recovery_required=False,
                          completed_at=iso(native_utc()))
            return result
        if row["target_kind"] == "EXTENDED":
            out = self.fam.ext.run_step(self, row, key, scope)
            result.update(extended=out, status=out["status"], code=out["code"], effect_calls=out["effect_calls"],
                          result_class=out.get("result_class"), recovery_required=out["recovery_required"],
                          completed_at=out["completed_at"])
            return result
        op = row["target"]
        try:
            self.ledger = self.open_ledger()
        except BaseException as error:
            result.update(status="START_CONSUMED_NO_CORE_CLAIM", code=safe_code(error), recovery_required=False,
                          completed_at=iso(native_utc()))
            return result
        try:
            self.current = op
            self.stored = {}
            outer = self.fam.outer.OuterLimiter(core_sha256=self.runtime["sources"]["vendor/finite_batch.py"],
                                                outer_sha256=self.runtime["sources"]["vendor/outer_limiter.py"],
                                                hard_budget_seconds=min(1200, self.tasks[op]["budget_seconds"]))
            try:
                batch = fb.FiniteBatch(self.bundle, self.ledger, self.services())
            except BaseException as error:
                result.update(status="START_CONSUMED_NO_CORE_CLAIM", code=safe_code(error), recovery_required=False,
                              completed_at=iso(native_utc()))
                return result
            core = outer.run(batch, op)
        finally:
            self.ledger.close()
        result.update(outer=core, status=core.get("status"), code=core.get("code"),
                      effect_calls=core.get("effect_calls"), recovery_required=core.get("recovery_required"),
                      completed_at=core.get("completed_at"),
                      result_class=self.fam.dec.result_class(self.authority["decoders"][op]["kind"])
                      if core.get("status") == "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE" else None)
        return result

    def read_diagnostics(self, key):
        """Codes of the runner-stage diagnostics; v3.2 (M1): an input change is listed as
        INPUT_FILE_CHANGED:<path>:<changed fields>; v3.3: a failed unit start as
        UNIT_START_FAILED:<launch class>:rc=<exit code>:stderr_sha256=<hex>:stderr_bytes=<n>:stderr=<excerpt>."""
        try:
            e = self.runtime["election"]
            fd = open_chain(e["root_chain"] + [[child(self.layout, "work"), e["children"]["work"]]])
            try:
                names = sorted(n for n in os.listdir(fd) if n.startswith("diag-" + key + "-"))
                docs = [strict(read_at(fd, n, 4096, Hold), 4096, Hold) for n in names]
            finally:
                os.close(fd)
            return [diagnostic_line(d) for d in docs]
        except BaseException:
            return ["DIAGNOSTICS_UNREADABLE"]


def diagnostic_line(d):
    """One RESULT diagnostics entry from a private diag document (stage RUNNER callbacks, INPUT, v3.3 UNIT)."""
    if d.get("stage") == "INPUT":
        return "%s:%s:%s" % (d.get("code"), d.get("file"), ",".join(d.get("changed") or []))
    if d.get("stage") == "UNIT":
        return "%s:%s:rc=%s:stderr_sha256=%s:stderr_bytes=%s:stderr=%s" % (
            d.get("code"), d.get("launch_class"), d.get("child_exit_code"), d.get("child_stderr_sha256"),
            d.get("child_stderr_bytes"), d.get("child_stderr_excerpt"))
    return d.get("code")


def write_result(shell, lot, slot, raw):
    """Public RESULT by held descriptor of the pinned results directory, exclusive create, never overwritten."""
    e = shell.runtime["election"]
    fd = open_chain(e["root_chain"] + [[child(shell.layout, "results"), e["children"]["results"]]])
    try:
        write_new_at(fd, "%s.%s.json" % (lot, slot), raw)
        return "WRITTEN"
    except FileExistsError:
        return "PRESENT"
    finally:
        os.close(fd)


def refusal_record(code, now):
    return {"schema": REFUSAL_SCHEMA, "status": "REFUSED_NO_EFFECT", "code": code, "effect_calls": 0,
            "attempt_consumed": False, "automatic_retry": False, "at": iso(now)}


# ------------------------------------------------------------------ preview (installer protocol, read-only)
def preview_record(command, status, code, view=None, runtime_raw=None, extra=None):
    body = {"schema": PREVIEW_SCHEMA, "command": command, "status": status, "code": code, "lot": None,
            "request_sha256": None, "bound_sha256": None, "authority_sha256": None, "runtime_sha256": None,
            "mode": None, "slots": None, "detail": extra}
    if view is not None:
        body.update(lot=view.lot, request_sha256=view.request_sha256, bound_sha256=view.bound_sha256,
                    authority_sha256=view.q["authority_sha256"], runtime_sha256=sha(runtime_raw), mode=view.mode,
                    slots=len(view.authority["slots"]))
    return body


def preview_installed(lot_dir, *, physical=True, probe=None):
    """The installed lot, read-only: the physical Shell (installed copy, interpreter, root, Linux), the identity
    recheck, REVOKED, and the shell ABI of every slot. No marker, claim, timer or effect."""
    shell = Shell(lot_dir, probe=probe, physical=physical)
    shell.identity_check()
    need(not shell.revoked(), "LOT_REVOKED", Refusal)
    return preview_record("preview", "PREVIEW_PASS", None, shell.view, shell.view.files["runtime.json"])


def preview_stage(stage_lot, lot, *, physical=True, probe=None):
    """A STAGED lot (before the installer writes anything), judged by the installed runtime: its runtime document must
    equal a fresh measurement of this host, the family loads from the installed src, every signed byte and the whole
    shell ABI validate in physical mode, and the identity recheck passes."""
    canonical_path(stage_lot)
    need(LOT.fullmatch(lot or "") is not None, "LOT_INVALID", Refusal)
    parent, name = stage_lot.rsplit("/", 1)
    fd = os.open(stage_lot, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        runtime_raw = read_at(fd, "runtime.json", LIMIT)
        authority_raw = read_at(fd, "authority.json", LIMIT)
    finally:
        os.close(fd)
    runtime = strict(runtime_raw)
    layout = validate_layout(strict(authority_raw).get("layout"))
    need(runtime.get("schema") == RUNTIME_SCHEMA and runtime.get("layout_sha256") == sha(canonical(layout)),
         "RUNTIME_LAYOUT_UNBOUND", Refusal)
    if physical:
        physical_guard(runtime, layout)
    probe = probe or HostProbe()
    seen = measure(layout, probe, native_utc(), runtime["execution_mode"])
    need(runtime_equal(seen, runtime), "REMEASURE_RUNTIME_DIVERGED", Refusal)
    fam = load_family(runtime, layout)
    pfd = os.open(parent or "/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        view = LotView(fam, pfd, name, lot, layout, Refusal, physical=physical)
    finally:
        os.close(pfd)
    need(view.files["runtime.json"] == runtime_raw and view.files["authority.json"] == authority_raw, "LOT_BYTES_CHANGED",
         Refusal)
    Identity(runtime, layout, probe, fam).check()
    need(not os.path.lexists(child(layout, "lots") + "/" + lot), "LOT_ALREADY_INSTALLED", Refusal)
    return preview_record("preview-stage", "PREVIEW_PASS", None, view, runtime_raw)


def derived_check(lot_dir, derived_file, *, installed=False, physical=True, probe=None):
    shell = Shell(lot_dir, probe=probe, physical=physical)
    shell.identity_check()
    need(not shell.revoked(), "LOT_REVOKED", Refusal)
    raw = shell.view.derived(DERIVED_REGISTRY) if installed else read_path(derived_file, LIMIT)
    j4_registry_check(raw, shell.view, shell.ledger_pins())
    return preview_record("derived-check", "DERIVED_PASS", None, shell.view, shell.view.files["runtime.json"],
                          {"derived_sha256": sha(raw), "installed": installed})


class QuietParser(argparse.ArgumentParser):
    def error(self, _message):
        raise Refusal("CLI_ARGUMENTS_INVALID")


COMPLETE_STATUSES = ("ORIGINAL_COMPLETE_OBSERVED_CANDIDATE", "EXTENDED_COMPLETE")


def main(argv=None, *, shell_factory=Shell, emit=None):
    """run: exit 0 COMPLETE (core or extended); 3 refused with nothing consumed, or alternative refused by the start
    marker of an earlier alternative; 2 anything else (consumed: refused, uncertain, hold).
    preview / preview-stage / derived-check: exit 0 PASS, 3 refusal (one canonical L12HOST_PREVIEW_V3 line).
    v3.2 (M1): every input change this process saw is also named on stderr (the stdout protocols are unchanged)."""
    since = _INPUT_COUNT[0]
    try:
        return main_body(argv, shell_factory=shell_factory, emit=emit)
    finally:
        report_input_changes(since)


def main_body(argv, *, shell_factory, emit):
    parser = QuietParser(add_help=False)
    parser.add_argument("command", choices=("run", "preview", "preview-stage", "derived-check"))
    parser.add_argument("--lot-dir")
    parser.add_argument("--slot")
    parser.add_argument("--stage-lot")
    parser.add_argument("--lot")
    parser.add_argument("--derived-file")
    parser.add_argument("--installed", action="store_true")
    out = emit or (lambda data: os.write(1, data))
    try:
        args = parser.parse_args(argv)
    except Refusal as error:
        raw = canonical(refusal_record(safe_code(error), native_utc())) + b"\n"
        try:
            out(raw)
        except BaseException:
            pass
        return 3
    if args.command != "run":
        try:
            if args.command == "preview":
                need(bool(args.lot_dir), "CLI_ARGUMENTS_INVALID", Refusal)
                record = preview_installed(args.lot_dir)
            elif args.command == "preview-stage":
                need(bool(args.stage_lot) and bool(args.lot), "CLI_ARGUMENTS_INVALID", Refusal)
                record = preview_stage(args.stage_lot, args.lot)
            else:
                need(bool(args.lot_dir) and (args.installed or bool(args.derived_file)), "CLI_ARGUMENTS_INVALID", Refusal)
                record = derived_check(args.lot_dir, args.derived_file, installed=args.installed)
            code = 0
        except BaseException as error:
            record, code = preview_record(args.command, "PREVIEW_REFUSED", safe_code(error)), 3
        try:
            out(canonical(record) + b"\n")
        except BaseException:
            return 3
        return code
    shell = None
    try:
        need(bool(args.lot_dir) and bool(args.slot) and SLOT.fullmatch(args.slot) is not None, "SLOT_INVALID", Refusal)
        shell = shell_factory(args.lot_dir)
        result = shell.run_slot(args.slot)
    except Refusal as error:
        result = refusal_record(safe_code(error), native_utc())
    except BaseException as error:
        if shell is None or not shell.entered:
            result = refusal_record(safe_code(error), native_utc())
        else:
            result = {"schema": RESULT_SCHEMA, "status": "UNCERTAIN_CONSUMED", "code": safe_code(error),
                      "attempt_consumed": "UNKNOWN", "automatic_retry": False, "at": iso(native_utc())}
    raw = canonical(result) + b"\n"
    if shell is not None and result.get("schema") == RESULT_SCHEMA and "lot" in result:
        try:
            result_file = write_result(shell, result["lot"], result["slot"], raw)
        except BaseException:
            result_file = "UNAVAILABLE"
        raw = canonical(dict(result, result_file=result_file)) + b"\n"
    try:
        out(raw)
    except BaseException:
        pass
    if result.get("status") in COMPLETE_STATUSES:
        return 0
    return 3 if result.get("status") in ("REFUSED_NO_EFFECT", "REFUSED_START_CONSUMED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
