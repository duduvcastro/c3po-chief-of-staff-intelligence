"""L12-HOST v3.1 effect engine. The bounded runner (Codex R6, INHERITED_OUTER_GROUP) feeds THESE pinned bytes on
stdin; the extended-step worker loads the same pinned bytes:

    <python> -I -B - --lot-dir <installed lot> --target-kind CORE|EXTENDED|EXTENDED_PRE --target <op|step>
                     --authority-sha256 <A> --request-sha256 <R> --attempt-key <K>
                     --veto-observation-sha256 <V> --veto-valid-until <Z> --expect-ready-sha256 <hex|NONE>
                     --expect-supervisor-mainpid <pid|NONE>

v3.1 (v3 review): the unit grammar admits ONLY the reference dependency values (Wants=network-online.target,
Requires=docker.service, After=network-online.target docker.service) and ONLY Environment=DOCKER_CONFIG=<layout
docker_config>; mounts of a PARENT of the L12 root, the veto folder or the docker-config folder are refused in every
mode, and /etc is mountable only under the reader's launcher and supervisor folders (never the folder holding the
reader's secret.env). The SUPERVISOR start requires the ready file ABSENT at the transport; the SESSION_READER start
requires the acknowledged supervisor still running with the same MainPID, and the hold observes both units.

v3.3 (S1 of the v3.2 Linux proof: UNIT_START_FAILED without a reason): when systemd-run of a UNIT_START returns
non-zero, the refusal (same code, same status and accounting) carries `unit_start_failure`: the child exit code, the
stdout/stderr sizes and sha256 and the first 300 bytes of systemd-run's OWN stderr as printable ASCII. That excerpt is
the only child output the engine ever returns; container output stays hashed and never printed.

Import is inert. The engine re-reads the installed AUTHORITY, REQUEST and RUNTIME by fixed name, requires their
SHA-256 to equal the argv/REQUEST pins, selects the ONE signed row of the target and runs exactly one effect of the
closed table. No shell, no PATH lookup, no generic command, no retry, no detached launch:

  CONTAINER       docker run --rm (ATTACHED only) of the signed IMAGE_ID; the engine builds every flag itself; the row
                  supplies only data (name, labels, network, env-file paths, non-secret env, mounts, command words,
                  inner `timeout -s KILL`). The original is the receipt FILE the program wrote, or its bounded STDOUT.
  UNIT_START      systemd-run of ONE transient unit copied from a reviewed unit (closed key list, Restart=no only,
                  closed docker-run flag table, explicit network). Only the late session start step uses it: the
                  SUPERVISOR copy (declared pre-effect) and the SESSION_READER copy, which the engine starts only when
                  the exact ready.json the shell verified is still present (READY_NOT_PRESENT_AT_READER_START otherwise),
                  and then holds and observes up to the signed hold instant (unit running, never restarted, same PID).
                  The original is a LAUNCH_ACK record, never an operational COMPLETE.
  READBACK        read-only: signed files (path, sha256, mode, uid) re-read; the original is the readback record.
  CHAIN_READBACK  read-only: durable extended-step claim/terminal/envelope files of the signed steps.

BEFORE_EFFECT (the last point before transport, inside the same ALLOW, never renewed): the veto folder is re-read by
its pinned identity (any entry = VETO), the ALLOW's valid_until must still be in the future. Secrets reach a container
only through root 0600 --env-file paths whose metadata is checked; the files are never opened. Child stdout/stderr are
bounded, hashed and never printed. Output: ONE canonical JSON line (L12HOST_EFFECT_OUTPUT_V3) with the original bytes in
base64. The engine never judges an original's semantic status: the parent's ABI decoder does. Exit 0 only when the
transport finished and an original was collected.
"""
import base64
import hashlib
import json
import os
import re
import selectors
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

OUTPUT_SCHEMA = "L12HOST_EFFECT_OUTPUT_V3"
ACK_SCHEMA = "L12HOST_UNIT_LAUNCH_ACK_V31"
KINDS = ("CONTAINER", "UNIT_START", "READBACK", "CHAIN_READBACK", "HOST_PROGRAM")
ENGINE_KINDS = ("CONTAINER", "UNIT_START", "READBACK", "CHAIN_READBACK")
LAUNCH_CLASSES = ("SESSION_READER", "SUPERVISOR")
MAX_ORIGINAL = 60000            # under the runner's 64 KiB ReceiptView limit
MAX_CHILD_OUTPUT = 1024 * 1024
MAX_DOCUMENT = 1024 * 1024
DOCKER_MARGIN_SECONDS = 20      # docker client/engine overhead around the inner timeout
MAX_INNER_TIMEOUT = 4800        # extended steps (sources 4465 s); core rows are bounded by their task budget
UNIT_FLOOR_SECONDS = 100        # show 20 + systemd-run 40 + settle 3 + show 20 + margin
MAX_HOLD_SECONDS = 600
UNIT_SHOW_KEYS = ("Id", "LoadState", "ActiveState", "SubState", "Result", "MainPID", "NRestarts", "Restart",
                  "ExecMainStartTimestamp", "ExecMainStatus")
# Closed: no RestartSec / RestartPreventExitStatus / StartLimit* (B4: no automatic restart of any kind).
UNIT_KEYS = ("Type", "Environment", "ExecCondition", "ExecStartPre", "ExecStop", "ExecStopPost", "Restart",
             "TimeoutStartSec", "TimeoutStopSec", "KillMode", "UMask", "NoNewPrivileges", "StandardOutput",
             "StandardError", "SyslogIdentifier", "Requires", "After", "Wants", "RequiresMountsFor",
             "WorkingDirectory", "LimitCORE")
SECRET_WORD = re.compile(r"(TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|APIKEY|DSN|DATABASE_URL|CREDENTIAL|PRIVATE_KEY|AUTH)")
CODE = re.compile(r"[A-Z][A-Z0-9_]{0,80}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-z0-9][a-z0-9_.-]{0,62}\Z")
UNIT = re.compile(r"[a-z0-9][a-z0-9_.@-]{0,80}\Z")
LABEL_KEY = re.compile(r"[a-z][a-z0-9._-]{0,62}\Z")
LABEL_VALUE = re.compile(r"[A-Za-z0-9._:/+-]{1,128}\Z")
NETWORK = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\Z")
ENV_KEY = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
ENV_VALUE = re.compile(r"[A-Za-z0-9._:/,+@-]{0,512}\Z")
PATH = re.compile(r"/[A-Za-z0-9._/@=-]{1,240}\Z")
FIELD = re.compile(r"[a-z][a-z0-9_]{0,40}\Z")
WORD = re.compile(r"[A-Za-z0-9._:/=,+@-]{1,512}\Z")
FIXED_RUN = ["--pull", "never", "--init", "--user", "0:0", "--read-only", "--cap-drop", "ALL",
             "--security-opt", "no-new-privileges", "--restart", "no", "--pids-limit", "512"]
TMPFS = "/tmp:rw,noexec,nosuid,nodev,size=256m"
CHILD_ENV_BASE = (("PATH", "/usr/bin:/bin"), ("LANG", "C.UTF-8"), ("TZ", "UTC"))
BRT = timezone(timedelta(hours=-3))               # Brazil has no DST since 2019
READER_CONFIG_ROOT = "/etc/c3po-reader-e04"
# v3.1: the ONLY /etc folders a unit may mount (read-only): the reader's launcher and the supervisor's own config.
# The reader's secret.env/pins.env/activation.env live directly in READER_CONFIG_ROOT and reach ONLY the reader, as
# --env-file (never opened here, never mounted).
ETC_MOUNT_ROOTS = (READER_CONFIG_ROOT + "/launcher", READER_CONFIG_ROOT + "/supervisor")
# v3.1: the reviewed references' dependency lines, verbatim; nothing else (no other unit can be pulled in).
UNIT_DEPENDENCY_VALUES = {"Wants": "network-online.target", "Requires": "docker.service",
                          "After": "network-online.target docker.service"}
FORBIDDEN_MOUNT_SOURCES = ("/", "/var/run/docker.sock", "/run/docker.sock", "/var/run", "/run", "/etc", "/var",
                           "/var/lib", "/var/lib/docker", "/root", "/home", "/usr", "/bin", "/sbin", "/lib", "/boot",
                           "/tmp", "/mnt", "/opt", "/srv")
FORBIDDEN_MOUNT_PREFIXES = ("/proc", "/sys", "/dev", "/boot", "/root/", "/var/lib/docker", "/var/lib/containerd",
                            "/var/lib/postgresql", "/var/lib/mysql", "/var/log", "/run/", "/var/run/", "/usr/",
                            "/bin/", "/sbin/", "/lib/", "/lib64/", "/snap")
FORBIDDEN_TARGETS = ("/", "/proc", "/sys", "/dev", "/etc", "/usr", "/bin", "/sbin", "/lib", "/app", "/var/run",
                     "/run", "/tmp")


class Hold(ValueError):
    """Only a fixed code is ever exposed."""


def need(ok, code):
    if not ok:
        raise Hold(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def safe_code(error):
    return str(error) if isinstance(error, Hold) and CODE.fullmatch(str(error)) else "EFFECT_INTERNAL_FAILURE"


def strict_json(raw, *, require_canonical=True, limit=MAX_DOCUMENT):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, "JSON_DUPLICATE_KEY")
            out[key] = value
        return out

    def constant(_value):
        raise Hold("JSON_NONFINITE")
    need(type(raw) is bytes and 0 < len(raw) <= limit, "JSON_BYTES_INVALID")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except Hold:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Hold("JSON_INVALID") from None
    need(type(value) is dict, "JSON_NOT_OBJECT")
    if require_canonical:
        need(canonical(value) == raw, "JSON_NOT_CANONICAL")
    return value


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def utcnow():
    return datetime.now(timezone.utc)


def instant(value):
    need(type(value) is str and value.endswith("Z") and len(value) <= 40, "TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise Hold("TIME_INVALID") from None
    return parsed.astimezone(timezone.utc)


def canonical_path(path):
    need(type(path) is str and PATH.fullmatch(path) is not None and "//" not in path
         and "/../" not in path + "/" and "/./" not in path + "/" and not path.endswith("/"), "PATH_NOT_CANONICAL")
    return path


def under(path, root):
    return path == root or path.startswith(root + "/")


def ancestors(path):
    parts = path.split("/")[1:]
    return ["/"] + ["/" + "/".join(parts[:i]) for i in range(1, len(parts))]


def safe_ancestors(path, euid):
    """Every ancestor a real directory (no symlink), owned by root or the executor, not group/other writable."""
    for name in ancestors(path):
        info = os.lstat(name)
        need(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), "ANCESTOR_NOT_DIRECTORY")
        need(info.st_uid in (0, euid) and not stat.S_IMODE(info.st_mode) & 0o022, "ANCESTOR_NOT_SAFE")


# ------------------------------------------------------------------ start-minute rules (order rev M3, section 5)
def start_minute_violation(at):
    """Code constant, not signed data. Returns a refusal code or None for a real start instant (any timezone).

    BRT exclusions HH:05:00-07:59, HH:10:00-25:59, HH:35:00-37:59; 80 s margin before HH:05, HH:10, HH:35
    (HH:03:40-04:59, HH:08:40-09:59, HH:33:40-34:59); critical 06:58:40-07:25:59, 12:58:40-13:25:59,
    18:58:40-19:25:59; silences 00:15:00-00:45:59 and 02:15:00-02:45:59."""
    local = at.astimezone(BRT)
    ms = local.minute * 60 + local.second
    tod = local.hour * 3600 + ms
    for low, high in ((5 * 60, 7 * 60 + 59), (10 * 60, 25 * 60 + 59), (35 * 60, 37 * 60 + 59),
                      (3 * 60 + 40, 4 * 60 + 59), (8 * 60 + 40, 9 * 60 + 59), (33 * 60 + 40, 34 * 60 + 59)):
        if low <= ms <= high:
            return "START_MINUTE_FORBIDDEN"
    for hour in (7, 13, 19):
        if (hour - 1) * 3600 + 58 * 60 + 40 <= tod <= hour * 3600 + 25 * 60 + 59:
            return "START_IN_CRITICAL_WINDOW"
    for hour in (0, 2):
        if hour * 3600 + 15 * 60 <= tod <= hour * 3600 + 45 * 60 + 59:
            return "START_IN_SILENCE_WINDOW"
    return None


def start_minute_guard(at):
    code = start_minute_violation(at)
    need(code is None, code or "START_MINUTE_FORBIDDEN")


# ------------------------------------------------------------------ file policy helpers
def check_secret_file(path, owner_uid):
    """Metadata only, the file is NEVER opened: regular, owner = executor (root on the host), mode 0600 or 0400,
    nlink 1, safe ancestors."""
    canonical_path(path)
    try:
        safe_ancestors(path, owner_uid)
        info = os.lstat(path)
    except OSError:
        raise Hold("SECRET_ENV_FILE_UNAVAILABLE") from None
    need(stat.S_ISREG(info.st_mode) and info.st_uid == owner_uid and stat.S_IMODE(info.st_mode) in (0o600, 0o400)
         and info.st_nlink == 1, "SECRET_ENV_FILE_NOT_PRIVATE")


def mount_source_policy(path, readonly, layout):
    """S3 denylist in every mode (the epoch-04 allowlist is the runtime's physical guard): no system root, no docker or
    database data, no /etc except the reader's launcher and the supervisor's config folders (v3.1), never the L12 root
    (ledger, starts, receipts) nor a PARENT of it, of the veto folder or of the docker-config folder (v3.1), never the
    docker-config folder, and the veto folder read-only only (a container can never delete a veto)."""
    canonical_path(path)
    need(path not in FORBIDDEN_MOUNT_SOURCES and not any(path.startswith(p) for p in FORBIDDEN_MOUNT_PREFIXES)
         and "docker.sock" not in path and "containerd" not in path, "MOUNT_SOURCE_FORBIDDEN")
    need(not path.startswith("/etc/") or any(under(path, root) for root in ETC_MOUNT_ROOTS), "MOUNT_SOURCE_FORBIDDEN")
    need(not under(path, layout["root"]), "MOUNT_L12_ROOT_FORBIDDEN")
    for protected in (layout["root"], layout["veto_dir"], layout["docker_config"]):
        need(not protected.startswith(path + "/"), "MOUNT_PARENT_OF_PROTECTED_FORBIDDEN")
    need(not under(path, layout["docker_config"]), "MOUNT_DOCKER_CONFIG_FORBIDDEN")
    need(readonly or not under(path, layout["veto_dir"]), "MOUNT_VETO_WRITABLE_FORBIDDEN")
    need(readonly or not under(path, READER_CONFIG_ROOT), "MOUNT_WRITABLE_CONFIG_FORBIDDEN")


def check_mount_source(path, owner_uid):
    try:
        safe_ancestors(path, owner_uid)
        info = os.lstat(path)
    except OSError:
        raise Hold("MOUNT_SOURCE_UNAVAILABLE") from None
    need((stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) and not stat.S_ISLNK(info.st_mode),
         "MOUNT_SOURCE_INVALID")


def check_docker_config(path, owner_uid):
    """The pinned, EMPTY DOCKER_CONFIG directory (no root ~/.docker/config.json leaks into the CLI)."""
    canonical_path(path)
    try:
        safe_ancestors(path, owner_uid)
        info = os.lstat(path)
        entries = os.listdir(path)
    except OSError:
        raise Hold("DOCKER_CONFIG_UNAVAILABLE") from None
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == owner_uid and stat.S_IMODE(info.st_mode) == 0o700
         and entries == [], "DOCKER_CONFIG_NOT_EMPTY_PRIVATE")


# ------------------------------------------------------------------ the closed grammar
def _env_pair(row):
    return (type(row) is list and len(row) == 2 and all(type(x) is str for x in row)
            and ENV_KEY.fullmatch(row[0]) is not None and ENV_VALUE.fullmatch(row[1]) is not None
            and not SECRET_WORD.search(row[0]) and row[0] not in ("DOCKER_CONFIG", "DOCKER_HOST", "PATH", "LD_PRELOAD"))


def _mounts(mounts, layout):
    need(type(mounts) is list and len(mounts) <= 8 and all(
        type(m) is dict and set(m) == {"source", "target", "readonly"} and type(m["readonly"]) is bool
        for m in mounts) and len({m["target"] for m in mounts}) == len(mounts), "EFFECT_MOUNTS_INVALID")
    for m in mounts:
        canonical_path(m["source"])
        canonical_path(m["target"])
        need("," not in m["source"] + m["target"] and "=" not in m["source"] + m["target"], "EFFECT_MOUNTS_INVALID")
        need(m["target"] not in FORBIDDEN_TARGETS and not m["target"].startswith(("/proc/", "/sys/", "/dev/")),
             "MOUNT_TARGET_FORBIDDEN")
        mount_source_policy(m["source"], m["readonly"], layout)


def _network(value, *, allow_bridge):
    return (type(value) is str and NETWORK.fullmatch(value) is not None and value not in ("host", "default")
            and not value.startswith("container") and (allow_bridge or value != "bridge"))


def validate_container(row, layout):
    need(set(row) == {"kind", "docker", "receipt"}, "EFFECT_ROW_INVALID")
    docker = row["docker"]
    need(type(docker) is dict and set(docker) == {"name", "labels", "network", "env_files", "env", "mounts", "tmpfs",
                                                  "workdir", "image_id", "command", "timeout_seconds"},
         "EFFECT_DOCKER_INVALID")
    need(type(docker["name"]) is str and NAME.fullmatch(docker["name"]) is not None, "EFFECT_NAME_INVALID")
    need(type(docker["image_id"]) is str and IMAGE.fullmatch(docker["image_id"]) is not None, "EFFECT_IMAGE_INVALID")
    labels = docker["labels"]
    need(type(labels) is list and len(labels) <= 8 and all(
        type(x) is list and len(x) == 2 and all(type(y) is str for y in x) and LABEL_KEY.fullmatch(x[0])
        and LABEL_VALUE.fullmatch(x[1]) and not x[0].startswith("c3po.l12.") for x in labels)
         and len({x[0] for x in labels}) == len(labels), "EFFECT_LABELS_INVALID")
    # "bridge" is grammar-legal ONLY for a K9 PROVIDER row; the runtime ties it to the signed network class.
    need(_network(docker["network"], allow_bridge=True), "EFFECT_NETWORK_INVALID")
    need(type(docker["env_files"]) is list and len(docker["env_files"]) <= 3
         and len(set(docker["env_files"])) == len(docker["env_files"]), "EFFECT_ENV_FILES_INVALID")
    for path in docker["env_files"]:
        canonical_path(path)
    need(type(docker["env"]) is list and len(docker["env"]) <= 8 and all(_env_pair(x) for x in docker["env"])
         and len({x[0] for x in docker["env"]}) == len(docker["env"]), "EFFECT_ENV_INVALID")
    _mounts(docker["mounts"], layout)
    need(type(docker["tmpfs"]) is bool and (docker["workdir"] is None or (
        type(docker["workdir"]) is str and canonical_path(docker["workdir"]))), "EFFECT_DOCKER_INVALID")
    command = docker["command"]
    need(type(command) is list and 0 < len(command) <= 64 and all(
        type(w) is str and WORD.fullmatch(w) is not None for w in command)
         and command[0] in ("python", "python3"), "EFFECT_COMMAND_INVALID")
    need(type(docker["timeout_seconds"]) is int and 1 <= docker["timeout_seconds"] <= MAX_INNER_TIMEOUT,
         "EFFECT_TIMEOUT_INVALID")
    spec = row["receipt"]
    need(type(spec) is dict and spec.get("source") in ("FILE", "STDOUT"), "EFFECT_RECEIPT_INVALID")
    if spec["source"] == "FILE":
        need(set(spec) == {"source", "path"}, "EFFECT_RECEIPT_INVALID")
        canonical_path(spec["path"])
        need(any(spec["path"].startswith(m["source"] + "/") and not m["readonly"] for m in docker["mounts"]),
             "EFFECT_RECEIPT_OUTSIDE_WRITABLE_MOUNT")
    else:
        need(set(spec) == {"source"} and all(m["readonly"] for m in docker["mounts"]), "EFFECT_RECEIPT_INVALID")


# The ONLY docker run flags a reviewed unit copy may carry, space separated (never the "=" spelling).
UNIT_FLAGS_NOVALUE = ("--rm", "--init", "--read-only")
UNIT_FLAGS_VALUE = ("--restart", "--name", "--pull", "--user", "--workdir", "--network", "--tmpfs", "--cap-drop",
                    "--security-opt", "--pids-limit", "--stop-timeout", "--env-file", "--mount", "--label")
UNIT_META = re.compile(r"[;$%`|&<>\\\"'*?!#~]")


def parse_unit_docker(words, docker_binary, layout=None):
    """ExecStart of a unit copy: `<docker> run <closed flags> <IMAGE> python ...`. Returns the parsed flags."""
    need(len(words) >= 4 and words[0] == docker_binary and words[1] == "run", "UNIT_EXEC_INVALID")
    i, flags = 2, []
    while i < len(words) and words[i].startswith("-"):
        word = words[i]
        need("=" not in word, "UNIT_DOCKER_EQUALS_SPELLING_FORBIDDEN")
        if word in UNIT_FLAGS_NOVALUE:
            flags.append((word, None))
            i += 1
        elif word in UNIT_FLAGS_VALUE:
            need(i + 1 < len(words) and not words[i + 1].startswith("-"), "UNIT_DOCKER_FLAG_VALUE_MISSING")
            flags.append((word, words[i + 1]))
            i += 2
        else:
            raise Hold("UNIT_DOCKER_FLAG_FORBIDDEN")
    need(i < len(words) and IMAGE.fullmatch(words[i]) is not None, "UNIT_DOCKER_IMAGE_INVALID")
    image, command = words[i], words[i + 1:]
    need(command and command[0] in ("python", "python3") and all(WORD.fullmatch(w) for w in command),
         "UNIT_DOCKER_COMMAND_INVALID")
    single = {}
    for flag, value in flags:
        if flag not in ("--env-file", "--mount", "--label"):
            need(flag not in single, "UNIT_DOCKER_FLAG_REPEATED")
            single[flag] = value
    for required, value in (("--rm", None), ("--init", None), ("--read-only", None), ("--restart", "no"),
                            ("--pull", "never"), ("--user", "0:0"), ("--cap-drop", "ALL"),
                            ("--security-opt", "no-new-privileges")):
        need(required in single and single[required] == value, "UNIT_DOCKER_NOT_CONSTRAINED")
    need("--name" in single and NAME.fullmatch(single["--name"]) is not None, "UNIT_DOCKER_NAME_INVALID")
    # v3: the network is explicit (no implicit default bridge) and never host/bridge/default/container:.
    need("--network" in single and _network(single["--network"], allow_bridge=False), "UNIT_DOCKER_NETWORK_INVALID")
    need("--tmpfs" not in single or single["--tmpfs"] == TMPFS, "UNIT_DOCKER_TMPFS_INVALID")
    for flag in ("--pids-limit", "--stop-timeout"):
        need(flag not in single or re.fullmatch(r"[1-9][0-9]{0,4}", single[flag]) is not None, "UNIT_DOCKER_LIMIT_INVALID")
    need("--workdir" not in single or canonical_path(single["--workdir"]), "UNIT_DOCKER_WORKDIR_INVALID")
    env_files, mounts = [], []
    for flag, value in flags:
        if flag == "--env-file":
            env_files.append(canonical_path(value))
        elif flag == "--mount":
            parts = value.split(",")
            need(len(parts) in (3, 4) and parts[0] == "type=bind" and parts[1].startswith("source=")
                 and parts[2].startswith("target=") and (len(parts) == 3 or parts[3] == "readonly"),
                 "UNIT_DOCKER_MOUNT_INVALID")
            mounts.append({"source": parts[1][7:], "target": parts[2][7:], "readonly": len(parts) == 4})
        elif flag == "--label":
            key, _, val = value.partition("=")
            need(LABEL_KEY.fullmatch(key) is not None and LABEL_VALUE.fullmatch(val) is not None
                 and not key.startswith("c3po.l12."), "UNIT_DOCKER_LABEL_INVALID")
    if layout is not None:
        _mounts(mounts, layout)
    return {"name": single["--name"], "image": image, "env_files": env_files, "mounts": mounts, "command": command,
            "network": single["--network"]}


def validate_unit(unit, layout):
    need(type(unit) is dict and set(unit) == {"name", "description", "properties", "exec"}, "UNIT_INVALID")
    suffix = layout["unit_name_suffix"]
    need(type(unit["name"]) is str and UNIT.fullmatch(unit["name"]) is not None and unit["name"].endswith(suffix)
         and not unit["name"].startswith(layout["unit_prefix"]), "UNIT_NAME_INVALID")
    need(type(unit["description"]) is str and 0 < len(unit["description"]) <= 200
         and all(32 <= ord(c) < 127 for c in unit["description"]) and UNIT_META.search(unit["description"]) is None,
         "UNIT_DESCRIPTION_INVALID")
    words = unit["exec"]
    need(type(words) is list and 0 < len(words) <= 120 and all(
        type(w) is str and 0 < len(w) <= 4096 and all(32 < ord(c) < 127 for c in w) and UNIT_META.search(w) is None
        for w in words), "UNIT_EXEC_INVALID")
    docker = layout["binaries"]["docker"]
    parsed = parse_unit_docker(words, docker, layout)
    need(parsed["name"].endswith(suffix), "UNIT_CONTAINER_NAME_INVALID")
    props = unit["properties"]
    need(type(props) is list and len(props) <= 40 and all(
        type(p) is list and len(p) == 2 and all(type(x) is str for x in p) and p[0] in UNIT_KEYS
        and 0 < len(p[1]) <= 4096 and all(32 <= ord(c) < 127 for c in p[1]) for p in props), "UNIT_PROPERTIES_INVALID")
    seen = {}
    for key, value in props:
        need(UNIT_META.search(value) is None, "UNIT_PROPERTY_METACHARACTER")
        seen.setdefault(key, []).append(value)
        if key == "Environment":
            # v3.1: the ONLY environment of a unit copy is the pinned, empty docker CLI config (no LD_PRELOAD,
            # DOCKER_HOST, DOCKER_CONTEXT or anything else reaches the docker CLI of a unit).
            need(value == "DOCKER_CONFIG=" + layout["docker_config"], "UNIT_ENVIRONMENT_INVALID")
        elif key == "ExecCondition":
            parts = value.split(" ")
            need(len(parts) == 3 and parts[:2] == ["/usr/bin/test", "-f"] and canonical_path(parts[2]),
                 "UNIT_EXEC_PROPERTY_INVALID")
        elif key == "ExecStartPre":
            parts = value.split(" ")
            need(parts == ["-" + docker, "rm", parsed["name"]]
                 or parts == [docker, "image", "inspect", "--format", "{{.Id}}", parsed["image"]],
                 "UNIT_EXEC_PROPERTY_INVALID")
        elif key in ("ExecStop", "ExecStopPost"):
            parts = value.split(" ")
            need(len(parts) == 5 and parts[0] == "-" + docker and parts[1:3] == ["stop", "-t"]
                 and re.fullmatch(r"[1-9][0-9]?", parts[3]) and parts[4] == parsed["name"], "UNIT_EXEC_PROPERTY_INVALID")
        elif key == "Restart":
            need(value == "no", "UNIT_RESTART_MUST_BE_NO")
        elif key == "KillMode":
            need(value == "control-group", "UNIT_KILLMODE_INVALID")
        elif key == "Type":
            need(value in ("exec", "simple"), "UNIT_TYPE_INVALID")
        elif key in UNIT_DEPENDENCY_VALUES:
            # v3.1: only the reference values; any other unit name (c3po-reader.service, an epoch-03 unit...) would
            # be started by systemd outside every gate.
            need(value == UNIT_DEPENDENCY_VALUES[key], "UNIT_DEPENDENCY_INVALID")
        elif key in ("RequiresMountsFor", "WorkingDirectory"):
            need(all(canonical_path(w) for w in value.split(" ")), "UNIT_PATH_PROPERTY_INVALID")
        elif key == "NoNewPrivileges":
            need(value in ("true", "yes"), "UNIT_NO_NEW_PRIVILEGES_REQUIRED")
        else:
            need(re.fullmatch(r"[A-Za-z0-9.:-]{1,40}", value) is not None, "UNIT_PROPERTY_VALUE_INVALID")
    for key in ("Type", "Restart", "KillMode", "NoNewPrivileges", "Environment"):
        need(len(seen.get(key, [])) == 1, "UNIT_REQUIRED_PROPERTY_MISSING")
    for key in UNIT_DEPENDENCY_VALUES:
        need(len(seen.get(key, [])) <= 1, "UNIT_DEPENDENCY_INVALID")
    return parsed


def validate_readback(row):
    need(set(row) == {"kind", "files"}, "EFFECT_ROW_INVALID")
    files = row["files"]
    need(type(files) is list and 0 < len(files) <= 64 and all(
        type(f) is dict and set(f) == {"path", "sha256", "mode", "uid"} and type(f["path"]) is str
        and type(f["sha256"]) is str and HEX.fullmatch(f["sha256"]) is not None
        and f["mode"] in (0o400, 0o600, 0o444, 0o644) and type(f["uid"]) is int and f["uid"] >= 0 for f in files)
         and len({f["path"] for f in files}) == len(files), "READBACK_ROW_INVALID")
    for f in files:
        canonical_path(f["path"])


def validate_chain_readback(row):
    need(set(row) == {"kind", "source_lot", "source_request_sha256", "source_bound_sha256", "steps"}
         and type(row["source_lot"]) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", row["source_lot"]) is not None
         and all(type(row[k]) is str and HEX.fullmatch(row[k]) for k in ("source_request_sha256", "source_bound_sha256"))
         and type(row["steps"]) is list and 0 < len(row["steps"]) <= 16
         and all(type(s) is str and FIELD.fullmatch(s) for s in row["steps"])
         and len(set(row["steps"])) == len(row["steps"]), "CHAIN_READBACK_ROW_INVALID")


def validate_host_program(row):
    need(set(row) == {"kind", "source", "argv"} and type(row["source"]) is str
         and re.fullmatch(r"ext/[a-z][a-z0-9_]{0,40}\.py", row["source"]) is not None
         and type(row["argv"]) is list and len(row["argv"]) <= 16
         and all(type(w) is str and WORD.fullmatch(w) for w in row["argv"]), "HOST_PROGRAM_ROW_INVALID")


def validate_row(row, layout):
    """The closed effect table. Returns the kind."""
    need(type(row) is dict and row.get("kind") in KINDS, "EFFECT_KIND_INVALID")
    kind = row["kind"]
    if kind == "CONTAINER":
        validate_container(row, layout)
    elif kind == "UNIT_START":
        need(set(row) == {"kind", "unit", "launch_class"} and row["launch_class"] in LAUNCH_CLASSES, "EFFECT_ROW_INVALID")
        validate_unit(row["unit"], layout)
    elif kind == "READBACK":
        validate_readback(row)
    elif kind == "CHAIN_READBACK":
        validate_chain_readback(row)
    else:
        validate_host_program(row)
    return kind


def row_env_files(row, layout):
    if row["kind"] == "UNIT_START":
        return parse_unit_docker(row["unit"]["exec"], layout["binaries"]["docker"])["env_files"]
    if row["kind"] == "CONTAINER":
        return list(row["docker"]["env_files"])
    return []


def row_mounts(row, layout):
    if row["kind"] == "UNIT_START":
        return parse_unit_docker(row["unit"]["exec"], layout["binaries"]["docker"])["mounts"]
    if row["kind"] == "CONTAINER":
        return list(row["docker"]["mounts"])
    return []


def row_budget_floor(row):
    """Minimum budget (seconds) so the deadline can never fall inside a child the engine still waits for. The caller
    adds the gate allowance, the READY wait and the hold."""
    if row["kind"] == "UNIT_START":
        return UNIT_FLOOR_SECONDS
    if row["kind"] == "CONTAINER":
        return row["docker"]["timeout_seconds"] + DOCKER_MARGIN_SECONDS
    if row["kind"] == "HOST_PROGRAM":
        return 15
    return 10


def docker_argv(row, layout, attempt_key, request_sha256):
    docker = row["docker"]
    words = [layout["binaries"]["docker"], "run", "--rm"] + FIXED_RUN
    if docker["tmpfs"]:
        words += ["--tmpfs", TMPFS]
    if docker["workdir"]:
        words += ["--workdir", docker["workdir"]]
    words += ["--name", docker["name"], "--label", "c3po.l12.attempt=" + attempt_key,
              "--label", "c3po.l12.request=" + request_sha256]
    for key, value in docker["labels"]:
        words += ["--label", key + "=" + value]
    words += ["--network", docker["network"]]
    for path in docker["env_files"]:
        words += ["--env-file", path]
    for key, value in docker["env"]:
        words += ["--env", key + "=" + value]
    for m in docker["mounts"]:
        words += ["--mount", "type=bind,source=%s,target=%s%s" % (m["source"], m["target"], ",readonly" if m["readonly"] else "")]
    words += [docker["image_id"], "timeout", "-s", "KILL", str(docker["timeout_seconds"])] + list(docker["command"])
    return words


def unit_argv(row, layout):
    unit = row["unit"]
    words = [layout["binaries"]["systemd_run"], "--unit=" + unit["name"], "--description=" + unit["description"]]
    for key, value in unit["properties"]:
        words.append("--property=" + key + "=" + value)
    return words + list(unit["exec"])


# ------------------------------------------------------------------ bounded child processes
def run_bounded(argv, timeout, limit, env, deadline_utc=None):
    """One child, no shell, no PATH lookup; stdout/stderr bounded; killed at the earlier of timeout/deadline."""
    if deadline_utc is not None:
        timeout = min(timeout, (deadline_utc - utcnow()).total_seconds())
        need(timeout > 0, "EFFECT_DEADLINE")
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=dict(env), shell=False, close_fds=True)
    out, err = bytearray(), bytearray()
    selector = selectors.DefaultSelector()
    try:
        for stream, label in ((process.stdout, "out"), (process.stderr, "err")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        while selector.get_map():
            left = deadline - time.monotonic()
            need(left > 0, "CHILD_DEADLINE")
            for key, _ in selector.select(min(0.05, left)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = out if key.data == "out" else err
                need(len(target) + len(chunk) <= limit, "CHILD_OUTPUT_LIMIT")
                target.extend(chunk)
        while process.poll() is None:
            left = deadline - time.monotonic()
            need(left > 0, "CHILD_DEADLINE")
            time.sleep(min(0.02, left))
        return process.returncode, bytes(out), bytes(err)
    finally:
        selector.close()
        for stream in (process.stdout, process.stderr):
            stream.close()
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass


def read_regular(path, limit, *, owner_uid=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and 0 < info.st_size <= limit, "FILE_INVALID")
        need(owner_uid is None or info.st_uid == owner_uid, "FILE_OWNER_INVALID")
        raw = bytearray()
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            raw.extend(chunk)
            need(len(raw) <= limit, "FILE_INVALID")
        after = os.fstat(fd)
        need((info.st_size, info.st_mtime_ns, info.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
             and len(raw) == info.st_size, "FILE_CHANGED")
        return bytes(raw), info
    finally:
        os.close(fd)


def exists(path):
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False


# ------------------------------------------------------------------ before_effect (the last point before transport)
def dir_identity(info):
    return [info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)]


def before_effect(veto_dir, veto_identity, valid_until, clock=utcnow, minute=True):
    """Same ALLOW, never renewed: pinned folder identity, zero entries, ALLOW still valid, start minute allowed.

    The shell calls it with minute=True in the runner's CURRENT_PINS approval (<= 5 s before the transport, inside
    the 80 s margin of the minute rules); the engine repeats the folder/ALLOW part right before the syscall."""
    fd = os.open(veto_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        need(dir_identity(os.fstat(fd)) == list(veto_identity), "VETO_DIRECTORY_CHANGED_BEFORE_EFFECT")
        entries = os.listdir(fd)
    finally:
        os.close(fd)
    need(entries == [], "VETO_PRESENT_BEFORE_EFFECT")
    now = clock()
    need(now < valid_until, "VETO_ALLOW_EXPIRED_BEFORE_EFFECT")
    if minute:
        start_minute_guard(now)
    return now


def ready_still_present(path, expected_sha256, owner_uid):
    """B3: the reader starts only while the exact ready.json the shell verified is still there."""
    need(type(expected_sha256) is str and HEX.fullmatch(expected_sha256) is not None, "READY_NOT_VERIFIED_BEFORE_READER")
    try:
        raw, _ = read_regular(path, 65536, owner_uid=owner_uid)
    except (OSError, Hold):
        raise Hold("READY_NOT_PRESENT_AT_READER_START") from None
    need(sha(raw) == expected_sha256, "READY_CHANGED_BEFORE_READER_START")


def ready_absent(path):
    """v3.1 (leftover ready.json): the supervisor starts only while NO ready file exists (any type: a leftover from a
    rehearsal would otherwise satisfy the READY wait before this supervisor is ready)."""
    try:
        os.lstat(path)
    except FileNotFoundError:
        return
    except OSError:
        raise Hold("READY_PRESENT_AT_SUPERVISOR_START") from None
    raise Hold("READY_PRESENT_AT_SUPERVISOR_START")


def show_unit(layout, env, unit, deadline_utc=None):
    show = [layout["binaries"]["systemctl"], "show", unit + ".service", "--no-pager", "-p", ",".join(UNIT_SHOW_KEYS)]
    rc, raw, _ = run_bounded(show, 20, 65536, env, deadline_utc)
    return rc, unit_props(raw)


def supervisor_alive(layout, env, unit, main_pid, deadline_utc=None):
    """v3.1: the acknowledged supervisor is still running once (Restart=no, NRestarts=0) with the SAME MainPID."""
    need(type(main_pid) is str and re.fullmatch(r"[1-9][0-9]{0,9}", main_pid) is not None, "SUPERVISOR_PID_UNKNOWN")
    rc, props = show_unit(layout, env, unit, deadline_utc)
    need(rc == 0 and running_once(props) and props.get("MainPID") == main_pid, "SUPERVISOR_NOT_RUNNING_AT_READER_START")
    return props


# ------------------------------------------------------------------ effects
def container_effect(row, layout, attempt_key, request_sha256, env, gate, deadline_utc):
    docker, spec = row["docker"], row["receipt"]
    if spec["source"] == "FILE":
        need(not exists(spec["path"]), "RECEIPT_DESTINATION_PRESENT")
    argv = docker_argv(row, layout, attempt_key, request_sha256)
    transport_at = gate()
    rc, out, err = run_bounded(argv, docker["timeout_seconds"] + DOCKER_MARGIN_SECONDS, MAX_CHILD_OUTPUT, env,
                               deadline_utc)
    meta = {"child_exit_code": rc, "child_stdout_sha256": sha(out), "child_stdout_bytes": len(out),
            "child_stderr_sha256": sha(err), "child_stderr_bytes": len(err), "transport_at": iso(transport_at)}
    need(rc == 0, "CHILD_NONZERO_EXIT")
    if spec["source"] == "STDOUT":
        need(0 < len(out) <= MAX_ORIGINAL, "STDOUT_ORIGINAL_SIZE")
        return out, meta
    original, _ = read_regular(spec["path"], MAX_ORIGINAL)
    return original, meta


def unit_props(raw):
    props = {}
    for line in raw.decode("utf-8", "replace").splitlines():
        key, _, value = line.partition("=")
        if key in UNIT_SHOW_KEYS:
            props[key] = value[:200]
    return props


def running_once(props):
    return (props.get("LoadState") == "loaded" and props.get("ActiveState") == "active"
            and props.get("SubState") == "running" and props.get("NRestarts") == "0"
            and props.get("Restart") == "no" and props.get("MainPID", "0") not in ("", "0"))


UNIT_FAILURE_SCHEMA = "L12HOST_UNIT_START_FAILURE_V33"
STDERR_EXCERPT_BYTES = 300


def stderr_excerpt(err):
    """v3.3: the first STDERR_EXCERPT_BYTES bytes of a failed systemd-run's stderr, printable ASCII only (tab, CR and
    LF become a space, every other byte outside 0x20-0x7e becomes '?'). Diagnostics only."""
    return "".join(chr(b) if 0x20 <= b <= 0x7e else (" " if b in (9, 10, 13) else "?")
                   for b in err[:STDERR_EXCERPT_BYTES])


def unit_start_failed(row, rc, out, err):
    """v3.3 (S1 proof: the reader's systemd-run returned non-zero and the RESULT carried no reason): the refusal keeps
    the fixed code UNIT_START_FAILED and carries the child exit code, the stdout/stderr sizes and sha256 and a bounded,
    sanitized stderr excerpt. Every status and effect-accounting rule is unchanged (the gate already marked UNCERTAIN)."""
    error = Hold("UNIT_START_FAILED")
    error.unit_start_failure = {"schema": UNIT_FAILURE_SCHEMA, "launch_class": row["launch_class"],
                                "unit": row["unit"]["name"], "child_exit_code": rc,
                                "child_stdout_sha256": sha(out), "child_stdout_bytes": len(out),
                                "child_stderr_sha256": sha(err), "child_stderr_bytes": len(err),
                                "child_stderr_excerpt": stderr_excerpt(err)}
    return error


def unit_effect(row, layout, env, gate, deadline_utc, hold_until=None, settle=3.0, poll=1.0, clock=utcnow,
                supervisor=None):
    """LAUNCH_ACK only: the unit started, is running, never restarted, effective Restart=no. With hold_until, the unit
    is observed until that instant: still running, same MainPID, no restart. v3.1: with `supervisor` = (unit, MainPID)
    (the reader), every observation also requires the acknowledged supervisor still running with the same MainPID;
    the ACK records it. Never an operational COMPLETE."""
    unit = row["unit"]
    rc, before = show_unit(layout, env, unit["name"], deadline_utc)
    need(rc == 0 and before.get("LoadState") == "not-found", "UNIT_ALREADY_PRESENT")
    transport_at = gate()
    rc, out, err = run_bounded(unit_argv(row, layout), 40, 65536, env, deadline_utc)
    meta = {"child_exit_code": rc, "child_stdout_sha256": sha(out), "child_stdout_bytes": len(out),
            "child_stderr_sha256": sha(err), "child_stderr_bytes": len(err), "transport_at": iso(transport_at)}
    if rc != 0:
        raise unit_start_failed(row, rc, out, err)
    time.sleep(settle)
    rc2, props = show_unit(layout, env, unit["name"], deadline_utc)
    need(rc2 == 0, "UNIT_SHOW_FAILED")
    polls, held = 1, False
    sup_record = None
    sup_ok = True
    if supervisor is not None:
        sup_rc, sup_props = show_unit(layout, env, supervisor[0], deadline_utc)
        sup_ok = sup_rc == 0 and running_once(sup_props) and sup_props.get("MainPID") == supervisor[1]
        sup_record = {"unit": supervisor[0], "main_pid": supervisor[1], "polls": 1, "running_through_hold": sup_ok}
    if hold_until is not None and running_once(props) and sup_ok:
        pid = props.get("MainPID")
        held = True
        while clock() < hold_until:
            time.sleep(min(poll, max(0.0, (hold_until - clock()).total_seconds())))
            rc3, seen = show_unit(layout, env, unit["name"], deadline_utc)
            polls += 1
            if rc3 != 0 or not running_once(seen) or seen.get("MainPID") != pid:
                props, held = seen, False
                break
            if supervisor is not None:
                sup_rc, sup_props = show_unit(layout, env, supervisor[0], deadline_utc)
                sup_record["polls"] += 1
                if sup_rc != 0 or not running_once(sup_props) or sup_props.get("MainPID") != supervisor[1]:
                    sup_record["running_through_hold"] = False
                    held = False
                    break
    original = canonical({"schema": ACK_SCHEMA, "result_class": "LAUNCH_ACK", "launch_class": row["launch_class"],
                          "unit": unit["name"], "systemd_run_rc": rc, "properties": props, "observed_at": iso(clock()),
                          "hold_until": iso(hold_until) if hold_until is not None else None, "held": held,
                          "polls": polls, "supervisor": sup_record, "operational_complete": False})
    return original, meta


def readback_effect(row, gate):
    gate()
    files = []
    for f in row["files"]:
        try:
            raw, info = read_regular(f["path"], MAX_DOCUMENT)
            seen = {"path": f["path"], "sha256": sha(raw), "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid,
                    "nlink": info.st_nlink, "size": info.st_size}
        except (OSError, Hold):
            seen = {"path": f["path"], "sha256": None, "mode": None, "uid": None, "nlink": None, "size": None}
        seen["match"] = (seen["sha256"] == f["sha256"] and seen["mode"] == f["mode"] and seen["uid"] == f["uid"]
                         and seen["nlink"] == 1)
        files.append(seen)
    original = canonical({"schema": "L12HOST_READBACK_V3", "files": files, "all_match": all(x["match"] for x in files),
                          "observed_at": iso(utcnow())})
    need(len(original) <= MAX_ORIGINAL, "ORIGINAL_SIZE_INVALID")
    return original, {"transport_at": None}


def chain_readback_effect(row, root, context, gate):
    """Durable extended-step state only: claim, terminal and envelope present, canonical and mutually bound."""
    gate()
    rows = []
    for step in row["steps"]:
        key = sha(canonical(list(context) + ["EXTENDED", step]))
        state = {"step": step, "attempt_key": key, "claim_sha256": None, "terminal_sha256": None, "status": None,
                 "original_sha256": None, "original_completed_at": None, "durable": False}
        try:
            claim_raw, _ = read_regular(root + "/extended/xclaim-" + key, 65536)
            term_raw, _ = read_regular(root + "/extended/xterm-" + key, 65536)
            claim, term = strict_json(claim_raw), strict_json(term_raw)
            need(claim.get("attempt_key") == key and term.get("attempt_key") == key
                 and claim.get("request_sha256") == row["source_request_sha256"]
                 and claim.get("bound_sha256") == row["source_bound_sha256"]
                 and term.get("claim_sha256") == sha(claim_raw), "CHAIN_STATE_UNBOUND")
            state.update(claim_sha256=sha(claim_raw), terminal_sha256=sha(term_raw), status=term.get("status"),
                         original_sha256=term.get("original_sha256"),
                         original_completed_at=term.get("original_completed_at"))
            if term.get("status") == "EXTENDED_COMPLETE":
                env_raw, _ = read_regular(root + "/receipts/" + key + ".json", 2 * MAX_DOCUMENT)
                env = strict_json(env_raw, limit=2 * MAX_DOCUMENT)
                original = base64.b64decode(env.get("original_b64", ""), validate=True)
                need(sha(original) == term.get("original_sha256") == env.get("original_sha256"), "CHAIN_ENVELOPE_UNBOUND")
            state["durable"] = True
        except (OSError, Hold, ValueError):
            state["durable"] = False
        rows.append(state)
    original = canonical({"schema": "L12HOST_CHAIN_READBACK_V3", "steps": rows, "observed_at": iso(utcnow()),
                          "all_complete": all(r["durable"] and r["status"] == "EXTENDED_COMPLETE" for r in rows)})
    need(len(original) <= MAX_ORIGINAL, "ORIGINAL_SIZE_INVALID")
    return original, {"transport_at": None}


ARG_NAMES = ["--lot-dir", "--target-kind", "--target", "--authority-sha256", "--request-sha256", "--attempt-key",
             "--veto-observation-sha256", "--veto-valid-until", "--expect-ready-sha256", "--expect-supervisor-mainpid"]


def engine_argv(lot_dir, target_kind, target, authority_sha256, request_sha256, attempt_key, veto_sha256, valid_until,
                ready_sha256, supervisor_mainpid=None):
    values = [lot_dir, target_kind, target, authority_sha256, request_sha256, attempt_key, veto_sha256, valid_until,
              ready_sha256 or "NONE", supervisor_mainpid or "NONE"]
    words = []
    for name, value in zip(ARG_NAMES, values):
        words += [name, value]
    return words


def parse_argv(argv):
    need(type(argv) is list and len(argv) == 20 and argv[0::2] == ARG_NAMES, "EFFECT_ARGV_INVALID")
    lot, kind, target, authority_sha, request_sha, key, veto_sha, until, ready, pid = argv[1::2]
    canonical_path(lot)
    need(kind in ("CORE", "EXTENDED", "EXTENDED_PRE") and FIELD.fullmatch(target) is not None
         and all(HEX.fullmatch(x) for x in (authority_sha, request_sha, key, veto_sha))
         and (ready == "NONE" or HEX.fullmatch(ready))
         and (pid == "NONE" or re.fullmatch(r"[1-9][0-9]{0,9}", pid) is not None), "EFFECT_ARGV_INVALID")
    return (lot, kind, target, authority_sha, request_sha, key, veto_sha, instant(until),
            (None if ready == "NONE" else ready), (None if pid == "NONE" else pid))


def select_row(authority, kind, target):
    if kind == "CORE":
        effects = authority.get("effects")
        need(type(effects) is dict and target in effects, "EFFECT_ROW_ABSENT")
        return effects[target], None
    steps = (authority.get("extended") or {}).get("steps")
    need(type(steps) is list, "EFFECT_ROW_ABSENT")
    rows = [s for s in steps if type(s) is dict and s.get("step") == target]
    need(len(rows) == 1, "EFFECT_ROW_ABSENT")
    row = rows[0]["pre_effect"] if kind == "EXTENDED_PRE" else rows[0]["effect"]
    need(type(row) is dict, "EFFECT_ROW_ABSENT")
    return row, rows[0]


def run(argv, *, clock=utcnow):
    """Returns (exit_code, output dict). Never raises."""
    out = {"schema": OUTPUT_SCHEMA, "status": "REFUSED", "code": None, "target_kind": None, "target": None,
           "context": None, "effect_kind": None, "started_at": iso(clock()), "transport_at": None,
           "completed_at": None, "original_sha256": None, "original_b64": None, "child_exit_code": None,
           "child_stdout_sha256": None, "child_stdout_bytes": None, "child_stderr_sha256": None,
           "child_stderr_bytes": None}
    try:
        (lot, target_kind, target, authority_sha, request_sha, key, veto_sha, valid_until, ready_sha,
         supervisor_pid) = parse_argv(argv)
        out["target_kind"], out["target"] = target_kind, target
        authority_raw, _ = read_regular(lot + "/authority.json", MAX_DOCUMENT)
        request_raw, _ = read_regular(lot + "/request.json", MAX_DOCUMENT)
        runtime_raw, _ = read_regular(lot + "/runtime.json", MAX_DOCUMENT)
        need(sha(authority_raw) == authority_sha and sha(request_raw) == request_sha, "EFFECT_PIN_CHANGED")
        authority, request, runtime = strict_json(authority_raw), strict_json(request_raw), strict_json(runtime_raw)
        need(request.get("authority_sha256") == authority_sha and request.get("runtime_sha256") == sha(runtime_raw),
             "EFFECT_PIN_CHANGED")
        context = [request["epoch"], request["session"], request["previous_session"], request["track"]]
        expected_key = sha(canonical(context + ([target] if target_kind == "CORE" else ["EXTENDED", target])))
        need(key == expected_key, "EFFECT_ATTEMPT_KEY_INVALID")
        out["context"] = context
        layout = authority["layout"]
        row, step = select_row(authority, target_kind, target)
        kind = validate_row(row, layout)
        need(kind in ENGINE_KINDS, "EFFECT_KIND_NOT_ENGINE")
        need(kind != "UNIT_START" or (step is not None and row["launch_class"] == (
            "SUPERVISOR" if target_kind == "EXTENDED_PRE" else "SESSION_READER")), "UNIT_START_OUTSIDE_SESSION_START")
        out["effect_kind"] = kind
        owner_uid = runtime["executor_uid"]
        need(type(owner_uid) is int and owner_uid == os.geteuid(), "EFFECT_EXECUTOR_CHANGED")
        for path in row_env_files(row, layout):
            check_secret_file(path, owner_uid)
        for m in row_mounts(row, layout):
            check_mount_source(m["source"], owner_uid)
        env = list(CHILD_ENV_BASE)
        if kind in ("CONTAINER", "UNIT_START"):
            check_docker_config(layout["docker_config"], owner_uid)
            env.append(("DOCKER_CONFIG", layout["docker_config"]))
        veto_identity = runtime["election"]["veto_chain"][-1][1]
        deadline_utc = valid_until + timedelta(seconds=MAX_INNER_TIMEOUT + 600)
        reader = kind == "UNIT_START" and row["launch_class"] == "SESSION_READER"
        supervisor = kind == "UNIT_START" and row["launch_class"] == "SUPERVISOR"
        # v3.1: the reader needs the waited READY and the acknowledged supervisor PID; nothing else carries them.
        need((ready_sha is not None and supervisor_pid is not None) if reader
             else (ready_sha is None and supervisor_pid is None), "EFFECT_ARGV_NOT_FOR_THIS_EFFECT")
        sup_unit = step["pre_effect"]["unit"]["name"] if reader else None

        def gate():
            if reader:
                supervisor_alive(layout, list(CHILD_ENV_BASE), sup_unit, supervisor_pid, deadline_utc)
            now = before_effect(layout["veto_dir"], veto_identity, valid_until, clock, minute=False)
            if supervisor:
                ready_absent(authority["ready"]["ready_path"])
            if reader:
                ready_still_present(authority["ready"]["ready_path"], ready_sha, owner_uid)
            out["status"] = "UNCERTAIN"            # from here on the transport may have happened
            return now
        if kind == "CONTAINER":
            original, meta = container_effect(row, layout, key, request_sha, env, gate, None)
        elif kind == "UNIT_START":
            hold = instant(step["hold_until"]) if reader else None
            need(hold is None or (hold - clock()).total_seconds() <= MAX_HOLD_SECONDS, "UNIT_HOLD_TOO_LONG")
            original, meta = unit_effect(row, layout, env, gate, deadline_utc, hold_until=hold, clock=clock,
                                         supervisor=(sup_unit, supervisor_pid) if reader else None)
        elif kind == "READBACK":
            original, meta = readback_effect(row, gate)
        else:
            original, meta = chain_readback_effect(row, layout["root"], context, gate)
        out.update({k: v for k, v in meta.items() if k in out})
        need(type(original) is bytes and 0 < len(original) <= MAX_ORIGINAL, "ORIGINAL_SIZE_INVALID")
        out["original_sha256"] = sha(original)
        out["original_b64"] = base64.b64encode(original).decode("ascii")
        out["status"] = "TRANSPORT_DONE"
    except BaseException as error:
        out["code"] = safe_code(error)
        # v3.3: a failed UNIT_START carries WHY (exit code, stderr sha256/size and a bounded printable excerpt) in one
        # extra key, present only on that refusal; status, code, transport_at and the child_* fields are as in v3.2.
        failure = getattr(error, "unit_start_failure", None)
        if out["code"] == "UNIT_START_FAILED" and type(failure) is dict:
            out["unit_start_failure"] = dict(failure)
    out["completed_at"] = iso(clock())
    return (0 if out["status"] == "TRANSPORT_DONE" else 2), out


def main():
    code, out = run(sys.argv[1:])
    try:
        os.write(1, canonical(out) + b"\n")
    except BaseException:
        code = 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
