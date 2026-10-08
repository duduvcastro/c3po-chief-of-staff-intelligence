"""F2 only: one bounded GET of the provider's bulk for session 2026-10-08 per slot.

Import is inert. `run` requires a reviewed, owner-signed exact BOUND, a slot of the
fixed list, its clock window and an unclaimed slot before any claim, child or
provider access. The eligible set is a FIXED private input pinned by hash; the
provider's symbol list is never called. Public output: counts, times, HTTP status,
hashes. Private output: one age ciphertext for the Fable recipient.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import signal
import ssl
import stat
import subprocess
import sys
import tarfile
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

FAMILY = "F2_SERIES_V1"
OPERATION = "GO_READ_PROVIDER_BULK_SERIES_EMENDA7_20261008"
EPOCH = "R2D2-V2-SHADOW-2026-10-05"
REFERENCE = "e50e2263ea07a5a31db43f3e2a6cb68dec769ffa1e808d6197f622c78020acd1"
RECIPIENT = "age1knekenhrh79x9xm0ghvhltwg075d33mljhu4y6u9zyz3cweszens2vr8x0"
AGE_SHA256 = "eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c"
PROVIDER_HOST = "eodhd.com"
BULK_PATH = "/api/eod-bulk-last-day/US"
BULK_DAY = "2026-10-08"
SESSION_CLOSE = "2026-10-08T20:00:00Z"
CAMPAIGN_ROOT = "/var/lib/c3po/f2-series-20261008"
SOURCE_ROOT = "/var/lib/c3po/f2-series-src-20261008"
PROVIDER_ENV_PATH = "/var/lib/c3po/r2d2-v2-k9-20261005/secrets/provider.env"
PROVIDER_ENV_KEY = "C3PO_EODHD_API_TOKEN"
UNIT_PREFIX = "f2s-20261008-"
# Slot id (BRT wall clock HHMM) -> exact UTC instant. BRT = UTC-3 (no DST in 2026).
SLOTS = {"2126": "2026-10-09T00:26:00Z", "2156": "2026-10-09T00:56:00Z",
         "2226": "2026-10-09T01:26:00Z", "2256": "2026-10-09T01:56:00Z",
         "2326": "2026-10-09T02:26:00Z", "2356": "2026-10-09T02:56:00Z",
         "0026": "2026-10-09T03:26:00Z", "0056": "2026-10-09T03:56:00Z"}
EARLY_SECONDS = 2          # timer may not fire before its instant; tolerate clock jitter only
LATE_SECONDS = 60          # N: a start later than slot + N is refused without effect
START_CUTOFF = "2026-10-09T03:58:00Z"    # 00:58 BRT: no start at or after
RECEIVE_CUTOFF = "2026-10-09T04:00:00Z"  # 01:00 BRT: receipt must end before
MAX_SECONDS = 120
NETWORK_SECONDS = 75
SOCKET_SECONDS = 30
BULK_LIMIT = 64 * 1024 * 1024
PRIVATE_LIMIT = 128 * 1024 * 1024
ELIGIBLE_LIMIT = 4 * 1024 * 1024
RULE = {"numerator": 95, "denominator": 100, "minimum_eligible": 4000}
LEDGER_NAME = "campaign.ledger"
REVOKED_NAME = "REVOKED"
CLAIM_NAME = "slot.claim"
CIPHER_NAME = "bulk-series.age"
RECEIPT_NAME = "RESULT.public.json"
HEX = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_KEYS = {"schema", "family", "operation", "epoch", "bulk_date", "session_close", "slots", "early_seconds",
                "late_seconds", "start_cutoff", "receive_cutoff", "max_seconds", "network_seconds", "socket_seconds",
                "logical_fetch_limit_per_slot", "retry_limit", "recipient", "age_sha256", "campaign_root",
                "source_root", "provider_env_path", "provider_env_key", "source_sha256", "seal_sha256",
                "reference_sha256", "eligible_set_sha256", "eligible_count", "readiness_rule",
                "amendment7_sha256", "amendment7_signature_sha256", "review_sha256"}


class Hold(ValueError):
    """Only a fixed code is public."""


class Refusal(Hold):
    """Refused before any write, claim, child or provider access."""


class QuietParser(argparse.ArgumentParser):
    def error(self, _message):
        raise Refusal("CLI_ARGUMENTS_INVALID")


def need(condition, code, kind=Hold):
    if not condition:
        raise kind(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def strict(raw, limit=1024 * 1024):
    need(type(raw) is bytes and 0 < len(raw) <= limit, "DOCUMENT_SIZE_INVALID", Refusal)
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, "DOCUMENT_DUPLICATE_KEY", Refusal)
            result[key] = value
        return result
    def constant(_value):
        raise Refusal("DOCUMENT_NONFINITE_NUMBER")
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except Hold:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal("DOCUMENT_JSON_INVALID") from None
    need(type(result) is dict and canonical(result) == raw, "DOCUMENT_NOT_CANONICAL", Refusal)
    return result


def stamp(value):
    need(type(value) is str and value.endswith("Z"), "TIME_NOT_UTC", Refusal)
    try:
        found = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise Refusal("TIME_INVALID") from None
    return found


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def pin(value):
    return type(value) is str and HEX.fullmatch(value) is not None and value != "0" * 64


def safe_code(error):
    if isinstance(error, Hold) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", str(error)):
        return str(error)
    return "SERIES_INTERNAL_FAILURE"


def brt_label(slot):
    """Human label only: BRT = UTC-3."""
    return iso(stamp(SLOTS[slot]) - timedelta(hours=3)).replace("Z", "-03:00")


# ------------------------------------------------------------------ clock guard (no effect on refusal)
def clock_guard(slot, now):
    need(slot in SLOTS, "SLOT_UNKNOWN", Refusal)
    scheduled = stamp(SLOTS[slot])
    need(now < stamp(START_CUTOFF), "START_AFTER_CUTOFF_0058_BRT", Refusal)
    need(now >= scheduled - timedelta(seconds=EARLY_SECONDS), "START_BEFORE_SLOT", Refusal)
    need(now <= scheduled + timedelta(seconds=LATE_SECONDS), "START_LATE_FOR_SLOT", Refusal)
    return scheduled


# ------------------------------------------------------------------ documents
def owner_question(request_raw):
    q = strict(request_raw)
    slots = ", ".join("%s BRT=%s" % (k, v) for k, v in sorted(q["slots"].items(), key=lambda x: x[1]))
    return ("F2-SERIES: no maximo 1 GET do bulk de 2026-10-08 por slot, sem retry; NAO e prontidao ou GO.\n"
            "REQUEST SHA256: " + sha(request_raw) + "\nEmenda 7 SHA256: " + q["amendment7_sha256"] +
            "\nConjunto elegivel FIXO SHA256: " + q["eligible_set_sha256"] + " (" + str(q["eligible_count"]) + " nomes)" +
            "\nSlots UTC: " + slots + "\nInicio recusado apos 00:58 BRT; recebimento ate 01:00 BRT."
            "\nSaida privada cifrada; ausencia/NAO mantem HOLD. Resposta literal: Assino\n").encode("utf-8")


def validate_request(q):
    need(set(q) == REQUEST_KEYS and q["schema"] == "F2_REQUEST_V1" and q["family"] == FAMILY and
         q["operation"] == OPERATION and q["epoch"] == EPOCH, "REQUEST_SCHEMA_INVALID", Refusal)
    need(q["bulk_date"] == BULK_DAY and q["session_close"] == SESSION_CLOSE and q["slots"] == SLOTS and
         q["early_seconds"] == EARLY_SECONDS and q["late_seconds"] == LATE_SECONDS and
         q["start_cutoff"] == START_CUTOFF and q["receive_cutoff"] == RECEIVE_CUTOFF, "OBSERVATION_SCOPE_CHANGED", Refusal)
    need(q["max_seconds"] == MAX_SECONDS and q["network_seconds"] == NETWORK_SECONDS and
         q["socket_seconds"] == SOCKET_SECONDS and q["logical_fetch_limit_per_slot"] == 1 and
         q["retry_limit"] == 0 and q["readiness_rule"] == RULE, "LIMITS_CHANGED", Refusal)
    need(q["recipient"] == RECIPIENT and q["age_sha256"] == AGE_SHA256 and q["reference_sha256"] == REFERENCE and
         q["campaign_root"] == CAMPAIGN_ROOT and q["source_root"] == SOURCE_ROOT and
         q["provider_env_path"] == PROVIDER_ENV_PATH and q["provider_env_key"] == PROVIDER_ENV_KEY,
         "DOCUMENTARY_SCOPE_CHANGED", Refusal)
    for key in ("source_sha256", "seal_sha256", "eligible_set_sha256", "amendment7_sha256",
                "amendment7_signature_sha256", "review_sha256"):
        need(pin(q[key]), "PIN_INVALID", Refusal)
    need(type(q["eligible_count"]) is int and q["eligible_count"] >= RULE["minimum_eligible"],
         "ELIGIBLE_COUNT_INVALID", Refusal)


def validate_documents(raws):
    need(type(raws) is dict and set(raws) == {"request", "owner", "review"}, "BOUND_SET_INCOMPLETE", Refusal)
    values = {k: strict(v) for k, v in raws.items()}
    q = values["request"]
    validate_request(q)
    need(sha(raws["review"]) == q["review_sha256"], "BOUND_INPUT_PIN_MISMATCH", Refusal)
    review = values["review"]
    need(set(review) == {"schema", "verdict", "source_sha256", "seal_sha256", "eligible_set_sha256",
                         "linux_result_sha256", "review_record_sha256"} and
         review["schema"] == "F2_CODEX_REVIEW_V1" and review["verdict"] == "ACCEPTED_OWN_BYTES_LINUX" and
         all(review[k] == q[k] for k in ("source_sha256", "seal_sha256", "eligible_set_sha256")) and
         pin(review["linux_result_sha256"]) and pin(review["review_record_sha256"]), "REVIEW_NOT_ACCEPTED", Refusal)
    owner = values["owner"]
    need(set(owner) == {"schema", "request_sha256", "question_sha256", "answer", "recorded_at_utc", "channel"} and
         owner["schema"] == "F2_OWNER_SIGNATURE_V1" and owner["request_sha256"] == sha(raws["request"]) and
         owner["question_sha256"] == sha(owner_question(raws["request"])) and owner["answer"] == "Assino" and
         owner["channel"] == "REGISTRO_PELA_FABLE", "OWNER_NOT_SIGNED", Refusal)
    need(stamp(owner["recorded_at_utc"]) < stamp(START_CUTOFF), "OWNER_NOT_SIGNED", Refusal)
    return values


def validate_eligible(raw, q):
    need(sha(raw) == q["eligible_set_sha256"], "ELIGIBLE_SET_CHANGED", Refusal)
    value = strict(raw, ELIGIBLE_LIMIT)
    need(set(value) == {"schema", "provenance", "types", "readiness_rule", "symbols"} and
         value["schema"] == "F2_ELIGIBLE_SET_V1" and value["readiness_rule"] == RULE and
         value["types"] == ["COMMON_STOCK", "COMMON_STOCK_ADR"], "ELIGIBLE_SET_INVALID", Refusal)
    symbols = value["symbols"]
    need(type(symbols) is list and all(type(s) is str and 0 < len(s) <= 32 for s in symbols) and
         symbols == sorted(set(symbols)) and len(symbols) == q["eligible_count"], "ELIGIBLE_SET_INVALID", Refusal)
    return frozenset(symbols)


# ------------------------------------------------------------------ files by held descriptors
def paths_to_root(path):
    need(type(path) is str and re.fullmatch(r"/[A-Za-z0-9._/-]{1,220}", path) is not None, "PRIVATE_PATH_INVALID", Refusal)
    p = Path(path)
    need(str(p) == path and ".." not in p.parts and "//" not in path and len(p.parts) <= 18, "PRIVATE_PATH_INVALID", Refusal)
    return ["/"] + [str(Path(*p.parts[:i])) for i in range(2, len(p.parts) + 1)]


def open_dir(path, *, exclusive=True, physical=True):
    """Walk from / by held descriptors (O_NOFOLLOW): ancestors owned by root/us and not
    group/other writable; the final directory, when exclusive, ours and mode 0700."""
    names = paths_to_root(path)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for i, name in enumerate(names):
            if i:
                try:
                    child = os.open(Path(name).name, flags, dir_fd=fd)
                except OSError:
                    raise Refusal("PRIVATE_DIRECTORY_UNAVAILABLE") from None
                os.close(fd)
                fd = child
            info = os.fstat(fd)
            if physical:
                need(info.st_uid in (0, os.geteuid()) and not stat.S_IMODE(info.st_mode) & 0o022,
                     "PRIVATE_PARENT_NOT_SAFE", Refusal)
        if exclusive:
            info = os.fstat(fd)
            need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700, "PRIVATE_ROOT_NOT_EXCLUSIVE", Refusal)
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_at(dir_fd, name, limit, *, private=False):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
    except OSError:
        raise Refusal("INPUT_FILE_UNAVAILABLE") from None
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_size <= limit and info.st_nlink == 1, "INPUT_FILE_INVALID", Refusal)
        if private:
            need(info.st_uid == os.geteuid() and not stat.S_IMODE(info.st_mode) & 0o077, "SECRET_FILE_NOT_PRIVATE", Refusal)
        parts, size = [], 0
        while True:
            block = os.read(fd, min(65536, limit + 1 - size))
            if not block:
                break
            parts.append(block)
            size += len(block)
            need(size <= limit, "INPUT_FILE_TOO_LARGE", Refusal)
        after = os.fstat(fd)
        need((info.st_size, info.st_mtime_ns, info.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
             "INPUT_FILE_CHANGED", Refusal)
        return b"".join(parts)
    finally:
        os.close(fd)


def read_path(path, limit, *, physical=True, private=False):
    parent, name = os.path.split(path)
    d = open_dir(parent, exclusive=False, physical=physical)
    try:
        return read_at(d, name, limit, private=private)
    finally:
        os.close(d)


def read_token(path, key, *, physical=True):
    """Token read from the root-only env file by this process; never argv/env/log."""
    raw = read_path(path, 65536, physical=physical, private=True)
    found = [line[len(key) + 1:] for line in raw.decode("utf-8", "strict").splitlines() if line.startswith(key + "=")]
    need(len(found) == 1, "PROVIDER_TOKEN_UNAVAILABLE", Refusal)
    token = found[0].strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        token = token[1:-1]
    need(0 < len(token) <= 4096 and not any(ord(x) < 33 or ord(x) > 126 for x in token), "PROVIDER_TOKEN_UNAVAILABLE", Refusal)
    return token


def load_reference(physical=True):
    path = Path(__file__).resolve().with_name("reference_extract.py")
    raw = read_path(str(path), 65536, physical=physical)
    need(sha(raw) == REFERENCE, "REFERENCE_BYTES_CHANGED", Refusal)
    module = type(sys)("f2_pinned_reference")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


# ------------------------------------------------------------------ analysis (same counting as readiness_probe P)
def analyze(bulk_raw, received_at, eligible, ref):
    need(received_at > stamp(SESSION_CLOSE), "RECEIPT_TIME_INVALID")
    rows = ref.Response(bulk_raw, received_at, BULK_PATH).json()
    need(type(rows) is list, "BULK_INVALID")
    grouped, dated = {}, 0
    for i, row in enumerate(rows):
        if type(row) is not dict or row.get("date") != BULK_DAY:
            continue
        dated += 1
        code = row.get("code")
        if isinstance(code, str) and code in eligible:
            grouped.setdefault(code, []).append((i, row))
    usable = duplicates = conflicts = 0
    unusable = []
    for symbol, pairs in sorted(grouped.items()):
        distinct = ref._distinct([x[1] for x in pairs])
        duplicates += len(pairs) - len(distinct)
        if len(distinct) != 1:
            conflicts += 1
            unusable.append({"symbol": symbol, "bulk_pointers": ["/" + str(i) for i, _ in pairs], "reason": "CONFLICTING_DISTINCT_ROWS"})
        elif ref._bar(distinct[0], date.fromisoformat(BULK_DAY), received_at) is not None:
            usable += 1
        else:
            unusable.append({"symbol": symbol, "bulk_pointers": ["/" + str(i) for i, _ in pairs], "reason": "BAR_NOT_USABLE"})
    absent = sorted(eligible - grouped.keys())
    n, present = len(eligible), len(grouped)
    passed = n >= RULE["minimum_eligible"] and RULE["denominator"] * present >= RULE["numerator"] * n
    counts = {"eligible_symbols": n, "present_eligible_symbols": present, "absent_eligible_symbols": len(absent),
              "usable_eligible_symbols": usable, "present_unusable_symbols": len(unusable),
              "conflicting_eligible_symbols": conflicts, "duplicate_eligible_rows": duplicates,
              "required_minimum": (RULE["numerator"] * n + RULE["denominator"] - 1) // RULE["denominator"],
              "minimum_eligible_rule": RULE["minimum_eligible"], "bulk_rows": len(rows), "dated_rows": dated}
    need(present + len(absent) == n and usable + len(unusable) == present, "SET_COUNTS_INCONSISTENT")
    private = {"schema": "F2_PRIVATE_SLOT_ANALYSIS_V1", "bulk_date": BULK_DAY, "counts": counts, "pass": passed,
               "eligible_absent": absent, "present_unusable": unusable}
    return counts, passed, private


# ------------------------------------------------------------------ provider: exactly one GET
class Provider:
    def __init__(self, token, monotonic=time.monotonic, clock=lambda: datetime.now(timezone.utc)):
        need(type(token) is str and 0 < len(token) <= 4096, "PROVIDER_TOKEN_UNAVAILABLE", Refusal)
        self.token, self.monotonic, self.clock = token, monotonic, clock
        self.calls = 0

    def fetch(self, deadline):
        need(self.calls == 0, "PROVIDER_CALL_LIMIT_EXCEEDED")
        begun = self.clock()
        need(self.monotonic() < deadline, "NETWORK_DEADLINE")
        query = BULK_PATH + "?" + urlencode({"api_token": self.token, "fmt": "json", "date": BULK_DAY})
        raw, status, complete, code = bytearray(), None, False, None
        content_type = None
        conn = http.client.HTTPSConnection(PROVIDER_HOST, 443, timeout=min(SOCKET_SECONDS, deadline - self.monotonic()),
                                           context=ssl.create_default_context())
        self.calls += 1
        try:
            conn.request("GET", query, headers={"Accept": "application/json", "Accept-Encoding": "identity"})
            response = conn.getresponse()
            status = response.status
            content_type = response.getheader("Content-Type")
            while True:
                remaining = deadline - self.monotonic()
                need(remaining > 0, "NETWORK_DEADLINE")
                if conn.sock:
                    conn.sock.settimeout(min(SOCKET_SECONDS, remaining))
                block = response.read1(min(65536, BULK_LIMIT + 1 - len(raw)))
                if not block:
                    need(response.length in (None, 0), "PROVIDER_BODY_PARTIAL")
                    complete = True
                    break
                raw.extend(block)
                need(len(raw) <= BULK_LIMIT, "PROVIDER_BODY_TOO_LARGE")
            need(status == 200, "PROVIDER_HTTP_NOT_OK")
            need(response.getheader("Content-Encoding", "identity").lower() == "identity", "PROVIDER_ENCODING_NOT_IDENTITY")
        except http.client.IncompleteRead as error:
            raw.extend(error.partial[:max(0, BULK_LIMIT + 1 - len(raw))])
            code = "PROVIDER_BODY_PARTIAL"
        except BaseException as error:
            code = safe_code(error) if isinstance(error, Hold) else "PROVIDER_TRANSPORT_FAILED"
        finally:
            conn.close()
        # No URL, query or token in the receipt.
        return bytes(raw), {"path": BULK_PATH, "bulk_date": BULK_DAY, "started_at": iso(begun),
                            "received_at": iso(self.clock()), "http_status": status, "content_type": content_type,
                            "body_sha256": sha(raw), "body_bytes": len(raw), "body_complete": complete, "code": code}


# ------------------------------------------------------------------ private bundle + age (as F1)
def private_bundle(files):
    need(type(files) is dict and all(re.fullmatch(r"[a-z0-9_.-]{1,80}", n) and type(r) is bytes for n, r in files.items()),
         "PRIVATE_BUNDLE_MEMBER_INVALID")
    inventory = {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(files.items())}
    manifest = canonical({"schema": "F2_PRIVATE_INVENTORY_V1", "files": inventory})
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in sorted(dict(files, **{"inventory.json": manifest}).items()):
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.uid, member.gid, member.mtime = len(raw), 0o600, 0, 0, 0
            archive.addfile(member, io.BytesIO(raw))
    need(len(output.getvalue()) <= PRIVATE_LIMIT, "PRIVATE_BUNDLE_TOO_LARGE")
    return output.getvalue(), sha(manifest)


def cipher_to_fd(age_fd, output_fd, payload, seconds):
    need(seconds > 0, "CIPHER_DEADLINE")
    proc = subprocess.Popen(["/proc/self/fd/" + str(age_fd), "-r", RECIPIENT], stdin=subprocess.PIPE,
                            stdout=output_fd, stderr=subprocess.DEVNULL, pass_fds=(age_fd,),
                            env={"LANG": "C", "PATH": "/usr/bin:/bin"}, close_fds=True)
    try:
        proc.communicate(payload, timeout=seconds)
    except BaseException:
        proc.kill()
        proc.wait()
        raise Hold("CIPHER_FAILED_OR_DEADLINE") from None
    need(proc.returncode == 0, "CIPHER_FAILED_OR_DEADLINE")


def read_fd(fd, limit):
    os.lseek(fd, 0, os.SEEK_SET)
    raw = bytearray()
    while True:
        part = os.read(fd, 65536)
        if not part:
            break
        raw.extend(part)
        need(len(raw) <= limit, "CIPHER_TOO_LARGE")
    return bytes(raw)


def open_age(root_fd):
    fd = os.open("age", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid in (0, os.geteuid()) and
             info.st_mode & 0o111 and not stat.S_IMODE(info.st_mode) & 0o022, "AGE_FILE_UNSAFE", Refusal)
        need(sha(read_fd(fd, 32 * 1024 * 1024)) == AGE_SHA256, "AGE_BYTES_CHANGED", Refusal)
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_new(dir_fd, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


# ------------------------------------------------------------------ campaign ledger + per-slot claim
def claim_slot(root_fd, slot, request_hash, now):
    """Append-only ledger, one claim per slot. An existing entry or directory refuses."""
    need(not _exists(root_fd, REVOKED_NAME), "CAMPAIGN_REVOKED", Refusal)
    lfd = os.open(LEDGER_NAME, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600, dir_fd=root_fd)
    try:
        info = os.fstat(lfd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid() and
             not stat.S_IMODE(info.st_mode) & 0o077, "LEDGER_UNSAFE", Refusal)
        try:
            fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Refusal("LEDGER_BUSY") from None
        existing = read_fd(lfd, 1024 * 1024)
        for line in existing.splitlines():
            row = strict(line)
            need(row.get("slot") != slot, "SLOT_ALREADY_CLAIMED", Refusal)
        try:
            os.mkdir(slot, 0o700, dir_fd=root_fd)
        except FileExistsError:
            raise Refusal("SLOT_ALREADY_CLAIMED") from None
        # From here the slot is consumed: no path back to unclaimed.
        line = canonical({"schema": "F2_SLOT_CLAIM_V1", "slot": slot, "scheduled_at": SLOTS[slot],
                          "request_sha256": request_hash, "claimed_at": iso(now), "automatic_retry": False})
        os.write(lfd, line + b"\n")
        os.fsync(lfd)
        os.fsync(root_fd)
    finally:
        os.close(lfd)
    sfd = os.open(slot, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
    write_new(sfd, CLAIM_NAME, line)
    os.fsync(sfd)
    return sfd


def _exists(dir_fd, name):
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


# ------------------------------------------------------------------ one slot
def run(raws, slot, eligible_raw, token_reader, *, clock=lambda: datetime.now(timezone.utc), monotonic=time.monotonic,
        cipher=cipher_to_fd, provider_factory=Provider, physical=True, campaign_root=CAMPAIGN_ROOT, reference=None):
    started, mark = clock(), monotonic()
    # 1. Clock guard and documents: refusal here has no effect at all.
    clock_guard(slot, started)
    values = validate_documents(raws)
    q = values["request"]
    request_hash = sha(raws["request"])
    eligible = validate_eligible(eligible_raw, q)
    if physical:
        need(sys.platform == "linux", "RUNTIME_NOT_LINUX", Refusal)
        here = Path(__file__).resolve()
        need(sha(read_path(str(here), 1024 * 1024)) == q["source_sha256"], "SOURCE_BYTES_CHANGED", Refusal)
        need(sha(read_path(str(here.with_name("SHA256SUMS")), 1024 * 1024)) == q["seal_sha256"], "SEAL_BYTES_CHANGED", Refusal)
    ref = reference or load_reference(physical)
    token = token_reader()
    provider = provider_factory(token, monotonic=monotonic, clock=clock)
    del token
    root = open_dir(campaign_root, exclusive=True, physical=physical)
    age_fd = slot_fd = None
    prior = None
    result = {"schema": "F2_PUBLIC_SLOT_RESULT_V1", "family": FAMILY, "operation": OPERATION, "slot": slot,
              "scheduled_at": SLOTS[slot], "status": "SLOT_HOLD", "code": None, "pass": None,
              "request_sha256": request_hash, "eligible_set_sha256": q["eligible_set_sha256"],
              "source_sha256": q["source_sha256"], "seal_sha256": q["seal_sha256"], "started_at": iso(started),
              "fetch_started_at": None, "received_at": None, "http_status": None, "body_sha256": None,
              "body_bytes": None, "completed_at": None, "logical_fetch_calls": 0, "counts": None,
              "inventory_sha256": None, "cipher_sha256": None, "cipher_bytes": None, "slot_consumed": False,
              "automatic_retry": False, "provider_ready_granted": False, "capacity_or_E6_or_GO_granted": False}
    try:
        try:
            age_fd = open_age(root)
            need(monotonic() - mark < 10 and clock() <= stamp(SLOTS[slot]) + timedelta(seconds=LATE_SECONDS),
                 "START_LATE_FOR_SLOT", Refusal)
            slot_fd = claim_slot(root, slot, request_hash, clock())
        except BaseException:
            if age_fd is not None:
                os.close(age_fd)
                age_fd = None
            raise
        result["slot_consumed"] = True
        if physical:
            prior = signal.getsignal(signal.SIGALRM)
            def alarm(_s, _f):
                raise Hold("EXECUTION_DEADLINE")
            signal.signal(signal.SIGALRM, alarm)
        private = {"request.json": raws["request"], "owner-signature.json": raws["owner"], "review.json": raws["review"]}
        receive_cutoff = stamp(RECEIVE_CUTOFF)
        try:
            # Network deadline: 75 s of the 120 s budget and before 01:00 BRT on the wall clock.
            wall_left = (receive_cutoff - clock()).total_seconds()
            need(wall_left > 0, "RECEIVE_CUTOFF_PASSED")
            deadline = min(mark + NETWORK_SECONDS, mark + MAX_SECONDS, monotonic() + wall_left)
            if physical:
                signal.setitimer(signal.ITIMER_REAL, max(0.001, deadline - monotonic()))
            body, meta = provider.fetch(deadline)
            if physical:
                signal.setitimer(signal.ITIMER_REAL, max(0.001, mark + MAX_SECONDS - monotonic()))
            private["bulk.raw"] = body
            private["bulk-receipt.json"] = canonical(meta)
            result.update(fetch_started_at=meta["started_at"], received_at=meta["received_at"],
                          http_status=meta["http_status"], body_sha256=meta["body_sha256"], body_bytes=meta["body_bytes"])
            need(meta["code"] is None and meta["body_complete"] is True and meta["http_status"] == 200,
                 meta["code"] if meta["code"] else "PROVIDER_RESPONSE_INCOMPLETE")
            received = stamp(meta["received_at"])
            need(started <= stamp(meta["started_at"]) <= received, "RECEIPT_TIME_INVALID")
            need(received < receive_cutoff, "RECEIVED_AFTER_0100_BRT")
            need(monotonic() <= mark + NETWORK_SECONDS, "NETWORK_BUDGET_EXCEEDED")
            counts, passed, analysis = analyze(body, received, eligible, ref)
            need(monotonic() <= mark + NETWORK_SECONDS, "NETWORK_AND_ANALYSIS_BUDGET_EXCEEDED")
            private["analysis.json"] = canonical(analysis)
            result["counts"], result["pass"] = counts, passed
            result["status"] = "SLOT_OBSERVED_PASS" if passed else "SLOT_OBSERVED_FAIL"
        except BaseException as error:
            result["status"], result["code"] = "SLOT_HOLD", safe_code(error)
            result["counts"], result["pass"] = None, None
            private["failure.json"] = canonical({"schema": "F2_PRIVATE_FAILURE_V1", "code": result["code"],
                                                 "partial_evidence": True, "retry_allowed": False})
        result["logical_fetch_calls"] = provider.calls
        need(provider.calls <= 1, "PROVIDER_CALL_LIMIT_EXCEEDED")
        bundle, inventory_hash = private_bundle(private)
        result["inventory_sha256"] = inventory_hash
        remaining = mark + MAX_SECONDS - monotonic()
        need(remaining > 0, "EXECUTION_BUDGET_EXCEEDED")
        if physical:
            signal.setitimer(signal.ITIMER_REAL, max(0.001, remaining))
        fd = os.open(CIPHER_NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=slot_fd)
        try:
            if physical:
                need(sha(read_fd(age_fd, 32 * 1024 * 1024)) == AGE_SHA256, "AGE_BYTES_CHANGED")
            cipher(age_fd, fd, bundle, remaining)
            os.fsync(fd)
            sealed = read_fd(fd, PRIVATE_LIMIT + 1024 * 1024)
            need(sealed.startswith(b"age-encryption.org/v1\n"), "CIPHER_FORMAT_INVALID")
            result["cipher_sha256"], result["cipher_bytes"] = sha(sealed), len(sealed)
        finally:
            os.close(fd)
        need(monotonic() <= mark + MAX_SECONDS, "EXECUTION_BUDGET_EXCEEDED")
    except Refusal as error:
        if result["slot_consumed"]:
            result["status"], result["code"] = "SLOT_HOLD", safe_code(error)
        else:
            os.close(root)
            raise
    except BaseException as error:
        result["status"], result["code"] = "SLOT_HOLD", safe_code(error)
    finally:
        if age_fd is not None:
            os.close(age_fd)
        if physical and prior is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prior)
    if result["status"] == "SLOT_HOLD":
        result["pass"] = None
    result["logical_fetch_calls"] = provider.calls
    result["completed_at"] = iso(clock())
    try:
        write_new(slot_fd, RECEIPT_NAME, canonical(result) + b"\n")
        os.fsync(slot_fd)
    except BaseException:
        result["status"], result["code"], result["pass"] = "SLOT_HOLD", "PUBLIC_RECEIPT_UNAVAILABLE", None
    finally:
        os.close(slot_fd)
        os.close(root)
    return result


def main(argv=None):
    parser = QuietParser(description="F2 series slot. Requires own reviewed signed bytes. One GET, no retry.")
    parser.add_argument("command", choices=("run",))
    parser.add_argument("--bound", required=True)
    parser.add_argument("--slot", required=True)
    try:
        args = parser.parse_args(argv)
        # Clock first: a late or post-cutoff start is refused before reading anything.
        clock_guard(args.slot, datetime.now(timezone.utc))
        bound = strict(read_path(args.bound, 1024 * 1024))
        need(set(bound) == {"schema", "documents"} and bound["schema"] == "F2_BOUND_V1" and
             type(bound["documents"]) is dict, "BOUND_SCHEMA_INVALID", Refusal)
        raws = {k: canonical(v) for k, v in bound["documents"].items()}
        q = validate_documents(raws)["request"]
        eligible_raw = read_path(q["source_root"] + "/ELIGIBLE_SET.json", ELIGIBLE_LIMIT)
        result = run(raws, args.slot, eligible_raw,
                     lambda: read_token(q["provider_env_path"], q["provider_env_key"]))
    except BaseException as error:
        result = {"schema": "F2_PUBLIC_REFUSAL_V1", "status": "SLOT_REFUSED_NO_EFFECT", "code": safe_code(error),
                  "logical_fetch_calls": 0, "slot_consumed": False, "automatic_retry": False,
                  "at": iso(datetime.now(timezone.utc))}
    os.write(1, canonical(result) + b"\n")
    if result["status"] in ("SLOT_OBSERVED_PASS", "SLOT_OBSERVED_FAIL"):
        return 0
    return 3 if result["status"] == "SLOT_REFUSED_NO_EFFECT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
