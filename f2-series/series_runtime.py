"""F2 only: one bounded GET of the provider's bulk for session 2026-10-08 per slot.

Import is inert. `run` requires a reviewed, owner-signed exact BOUND (REQUEST, owner record,
ORIGINAL Emenda 7 signature, measured runtime and election, review), a slot of the fixed list,
its clock window, an owner record strictly before the slot, and every measured pin (UID, boot,
Python, executable, own bytes, seal, reference, eligible set, age, physical identity of every
ancestor, both roots, the pre-created ledger) before any claim, child or provider access; the
same pins, REVOKED, wall-vs-monotonic clock and calendar are rechecked between claim and GET.
The eligible set is a FIXED private input pinned by hash; the provider's symbol list is never
called. Public output: counts, times, HTTP status, hashes. Private output: one age ciphertext.
"""
from __future__ import annotations

import argparse
import base64
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
FAMILY_DIR = "f2-series"
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
OWNER_DEADLINE = "2026-10-09T00:45:00Z"  # 21:45 BRT: owner record must be at or before
CLOCK_SKEW_SECONDS = 2     # |wall elapsed - monotonic elapsed| above this = HOLD before GET
MAX_SECONDS = 120
NETWORK_SECONDS = 75
SOCKET_SECONDS = 30
BULK_LIMIT = 64 * 1024 * 1024
PRIVATE_LIMIT = 128 * 1024 * 1024
ELIGIBLE_LIMIT = 4 * 1024 * 1024
EXECUTABLE_LIMIT = 64 * 1024 * 1024
RULE = {"numerator": 95, "denominator": 100, "minimum_eligible": 4000}
TYPES = ["COMMON_STOCK", "COMMON_STOCK_ADR"]
# Fixed own set (F1 cohort, NOT readiness_probe P): pinned by hash and count.
ELIGIBLE_SET_PIN = "b24ffe6fca52408d4330875d11eeff1e0535114c57ce74fdedcb505e8c8acda3"
ELIGIBLE_COUNT = 5784
F1_INVENTORY_SHA256 = "29a2eed769584709508b87484c5ee9726ab64c399a28399cbf4d2423072b9bd6"
F1_REGISTRY_RAW_SHA256 = "74ac3250f389dcc7421d0219e7c9eaa82f4407e851d5ceecc1c2cbc3d47c993d"
F1_REGISTRY_RECEIPT_SHA256 = "b8a8e040fd8edcb2b2bc5eb3d5cceb62ef1cbfa897ae7c72700a4b03208226d5"
F1_CIPHER_SHA256 = "2ca5366fe821a0693ba06b928665ba81d13f299cfece4d6da8269232c82744b3"
F1_PREVIOUS_CLOSE = "2026-10-07T20:00:00Z"
AMENDMENT7 = "A2_EMENDA_07"
AMENDMENT7_ANSWER = "Assino a emenda 7 da A2"
LEDGER_NAME = "campaign.ledger"
AGE_NAME = "age"
REVOKED_NAME = "REVOKED"
CLAIM_NAME = "slot.claim"
CIPHER_NAME = "bulk-series.age"
RECEIPT_NAME = "RESULT.public.json"
HEX = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_KEYS = {"schema", "family", "operation", "epoch", "bulk_date", "session_close", "slots", "early_seconds",
                "late_seconds", "start_cutoff", "receive_cutoff", "owner_deadline", "clock_skew_seconds",
                "max_seconds", "network_seconds", "socket_seconds",
                "logical_fetch_limit_per_slot", "retry_limit", "recipient", "age_sha256", "campaign_root",
                "source_root", "family_dir", "provider_env_path", "provider_env_key", "source_sha256", "seal_sha256",
                "reference_sha256", "eligible_set_sha256", "eligible_count", "eligible_provenance", "readiness_rule",
                "amendment7_sha256", "amendment7_signature_sha256", "runtime_sha256", "election_sha256",
                "review_sha256"}
RUNTIME_KEYS = {"schema", "platform", "python_version", "python_executable_path", "python_executable_sha256",
                "executor_uid", "boot_id_sha256", "source_sha256", "seal_sha256", "reference_sha256",
                "eligible_set_sha256", "age_sha256", "measurement_record_sha256"}
ELECTION_KEYS = {"schema", "epoch", "operation", "source_root", "campaign_root", "family_dir", "source_identities",
                 "campaign_identities", "ledger_identity", "age_identity", "revoked_name", "claim_name"}
DIR_KEYS = {"path", "device", "inode", "uid", "gid", "mode"}
FILE_KEYS = {"name", "device", "inode", "uid", "gid", "mode", "nlink", "size"}
AMENDMENT_KEYS = {"schema", "amendment", "revision", "document_file", "document_sha256", "answer",
                  "signed_at_utc", "channel"}
OWNER_KEYS = {"schema", "request_sha256", "question_sha256", "answer", "question_published_at_utc",
              "recorded_at_utc", "channel"}
BOUND_DOCUMENTS = {"request", "owner", "amendment_signature", "election", "runtime", "review"}


class Hold(ValueError):
    """Only a fixed code is public."""


class Refusal(Hold):
    """Refused before any write, claim, child or provider access."""


class ClaimUncertain(Hold):
    """The slot directory may exist but no descriptor to it is held: nothing more is written."""


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


def parse(raw, limit=1024 * 1024):
    """Strict JSON object: no duplicate key, no non-finite number. Canonical form NOT required."""
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
    need(type(result) is dict, "DOCUMENT_JSON_INVALID", Refusal)
    return result


def strict(raw, limit=1024 * 1024):
    result = parse(raw, limit)
    need(canonical(result) == raw, "DOCUMENT_NOT_CANONICAL", Refusal)
    return result


def stamp(value):
    need(type(value) is str and value.endswith("Z"), "TIME_NOT_UTC", Refusal)
    try:
        found = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise Refusal("TIME_INVALID") from None
    need(found.utcoffset() == timedelta(0), "TIME_NOT_UTC", Refusal)
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


# ------------------------------------------------------------------ clock guards (no effect on refusal)
def clock_guard(slot, now, kind=Refusal):
    need(slot in SLOTS, "SLOT_UNKNOWN", kind)
    scheduled = stamp(SLOTS[slot])
    need(now < stamp(START_CUTOFF), "START_AFTER_CUTOFF_0058_BRT", kind)
    need(now >= scheduled - timedelta(seconds=EARLY_SECONDS), "START_BEFORE_SLOT", kind)
    need(now <= scheduled + timedelta(seconds=LATE_SECONDS), "START_LATE_FOR_SLOT", kind)
    return scheduled


def owner_slot_guard(owner, slot, now, kind=Refusal):
    """B2: the owner's record must precede the slot's first effect (strict) and the present clock."""
    recorded = stamp(owner["recorded_at_utc"])
    need(recorded < stamp(SLOTS[slot]), "OWNER_SIGNED_AFTER_SLOT", kind)
    need(now > recorded, "CLOCK_NOT_AFTER_OWNER_SIGNATURE", kind)


def skew_guard(clock, monotonic, started, mark, kind=Hold):
    wall = (clock() - started).total_seconds()
    mono = monotonic() - mark
    need(abs(wall - mono) <= CLOCK_SKEW_SECONDS, "CLOCK_WALL_MONOTONIC_DIVERGED", kind)


# ------------------------------------------------------------------ documents
def eligible_provenance(eligible_set_sha256, eligible_count):
    return {"origin": "F1_PRIVATE_BUNDLE_REGISTRY_RAW", "cohort": "F1_OWN_FIXED_SET_NOT_READINESS_PROBE_P",
            "registry_raw_sha256": F1_REGISTRY_RAW_SHA256, "registry_receipt_sha256": F1_REGISTRY_RECEIPT_SHA256,
            "f1_inventory_sha256": F1_INVENTORY_SHA256, "f1_cipher_sha256": F1_CIPHER_SHA256,
            "normalizer": "reference_extract.build_registry", "normalizer_reference_sha256": REFERENCE,
            "previous_close": F1_PREVIOUS_CLOSE, "types": list(TYPES), "eligible_set_sha256": eligible_set_sha256,
            "eligible_count": eligible_count, "bulk_date": BULK_DAY, "readiness_rule": RULE, "calendar_utc": SLOTS}


def owner_question(request_raw):
    q = strict(request_raw)
    slots = ", ".join("%s BRT=%s" % (k, v) for k, v in sorted(q["slots"].items(), key=lambda x: x[1]))
    return ("F2-SERIES: no maximo 1 GET do bulk de 2026-10-08 por slot, sem retry; NAO e prontidao ou GO.\n"
            "REQUEST SHA256: " + sha(request_raw) + "\nEmenda 7 SHA256: " + q["amendment7_sha256"] +
            "\nAssinatura original da Emenda 7 SHA256: " + q["amendment7_signature_sha256"] +
            "\nRuntime medido SHA256: " + q["runtime_sha256"] + "\nEleicao/identidades SHA256: " + q["election_sha256"] +
            "\nConjunto elegivel FIXO SHA256: " + q["eligible_set_sha256"] + " (" + str(q["eligible_count"]) +
            " nomes, coorte propria F1, nao a P)" +
            "\nSlots UTC: " + slots + "\nAssino valido so ate 21:45 BRT e so para slots posteriores ao registro."
            "\nInicio recusado apos 00:58 BRT; recebimento ate 01:00 BRT."
            "\nSaida privada cifrada; ausencia/NAO mantem HOLD. Resposta literal: Assino\n").encode("utf-8")


def validate_request(q):
    need(type(q) is dict and set(q) == REQUEST_KEYS and q["schema"] == "F2_REQUEST_V2" and q["family"] == FAMILY and
         q["operation"] == OPERATION and q["epoch"] == EPOCH, "REQUEST_SCHEMA_INVALID", Refusal)
    need(q["bulk_date"] == BULK_DAY and q["session_close"] == SESSION_CLOSE and q["slots"] == SLOTS and
         q["early_seconds"] == EARLY_SECONDS and q["late_seconds"] == LATE_SECONDS and
         q["start_cutoff"] == START_CUTOFF and q["receive_cutoff"] == RECEIVE_CUTOFF and
         q["owner_deadline"] == OWNER_DEADLINE and q["clock_skew_seconds"] == CLOCK_SKEW_SECONDS,
         "OBSERVATION_SCOPE_CHANGED", Refusal)
    need(q["max_seconds"] == MAX_SECONDS and q["network_seconds"] == NETWORK_SECONDS and
         q["socket_seconds"] == SOCKET_SECONDS and q["logical_fetch_limit_per_slot"] == 1 and
         q["retry_limit"] == 0 and q["readiness_rule"] == RULE, "LIMITS_CHANGED", Refusal)
    need(q["recipient"] == RECIPIENT and q["age_sha256"] == AGE_SHA256 and q["reference_sha256"] == REFERENCE and
         q["campaign_root"] == CAMPAIGN_ROOT and q["source_root"] == SOURCE_ROOT and q["family_dir"] == FAMILY_DIR and
         q["provider_env_path"] == PROVIDER_ENV_PATH and q["provider_env_key"] == PROVIDER_ENV_KEY,
         "DOCUMENTARY_SCOPE_CHANGED", Refusal)
    for key in ("source_sha256", "seal_sha256", "eligible_set_sha256", "amendment7_sha256",
                "amendment7_signature_sha256", "runtime_sha256", "election_sha256", "review_sha256"):
        need(pin(q[key]), "PIN_INVALID", Refusal)
    need(q["eligible_set_sha256"] == ELIGIBLE_SET_PIN and q["eligible_count"] == ELIGIBLE_COUNT and
         type(q["eligible_count"]) is int and q["eligible_count"] >= RULE["minimum_eligible"],
         "ELIGIBLE_SET_NOT_THE_FIXED_ONE", Refusal)
    need(q["eligible_provenance"] == eligible_provenance(q["eligible_set_sha256"], q["eligible_count"]),
         "ELIGIBLE_PROVENANCE_CHANGED", Refusal)


def amendment_wrapper(original_raw):
    """The ORIGINAL signature file bytes, opaque, carried in base64. Its pin is sha256(original bytes)."""
    need(type(original_raw) is bytes and 0 < len(original_raw) <= 65536, "AMENDMENT_ORIGINAL_UNAVAILABLE", Refusal)
    return {"schema": "F2_AMENDMENT7_SIGNATURE_ORIGINAL_V1", "original_record_sha256": sha(original_raw),
            "original_record_base64": base64.b64encode(original_raw).decode("ascii")}


def validate_amendment(doc, q):
    need(type(doc) is dict and set(doc) == {"schema", "original_record_sha256", "original_record_base64"} and
         doc["schema"] == "F2_AMENDMENT7_SIGNATURE_ORIGINAL_V1" and type(doc["original_record_base64"]) is str,
         "AMENDMENT_RECORD_INVALID", Refusal)
    try:
        raw = base64.b64decode(doc["original_record_base64"].encode("ascii"), validate=True)
    except (ValueError, UnicodeError):
        raise Refusal("AMENDMENT_ORIGINAL_UNAVAILABLE") from None
    need(sha(raw) == doc["original_record_sha256"] == q["amendment7_signature_sha256"],
         "AMENDMENT_ORIGINAL_BYTES_CHANGED", Refusal)
    original = parse(raw, 65536)
    need(set(original) == AMENDMENT_KEYS and original["schema"] == "DUDU_AMENDMENT_SIGNATURE_V1" and
         original["amendment"] == AMENDMENT7 and type(original["revision"]) is int and original["revision"] >= 1 and
         type(original["document_file"]) is str and 0 < len(original["document_file"]) <= 256 and
         original["document_sha256"] == q["amendment7_sha256"] and original["answer"] == AMENDMENT7_ANSWER and
         type(original["channel"]) is str and 0 < len(original["channel"]) <= 200, "AMENDMENT_NOT_SIGNED", Refusal)
    signed = stamp(original["signed_at_utc"])
    need(signed <= stamp(OWNER_DEADLINE), "AMENDMENT_SIGNED_AFTER_DEADLINE", Refusal)
    return original, signed


def validate_identity_rows(rows, path):
    names = paths_to_root(path)
    need(type(rows) is list and len(rows) == len(names), "IDENTITY_CHAIN_UNBOUND", Refusal)
    for name, row in zip(names, rows):
        need(type(row) is dict and set(row) == DIR_KEYS and row["path"] == name and
             all(type(row[k]) is int and row[k] >= 0 for k in DIR_KEYS - {"path"}), "IDENTITY_CHAIN_UNBOUND", Refusal)


def validate_file_row(row, name):
    need(type(row) is dict and set(row) == FILE_KEYS and row["name"] == name and
         all(type(row[k]) is int and row[k] >= 0 for k in FILE_KEYS - {"name"}), "FILE_IDENTITY_UNBOUND", Refusal)


def validate_context(raws):
    """Everything except the owner record (used to build the question, never to fake an answer)."""
    need(type(raws) is dict and set(raws) == BOUND_DOCUMENTS - {"owner"}, "CONTEXT_SET_INCOMPLETE", Refusal)
    values = {k: strict(v) for k, v in raws.items()}
    q = values["request"]
    validate_request(q)
    for name in ("review", "runtime", "election"):
        need(sha(raws[name]) == q[name + "_sha256"], "BOUND_INPUT_PIN_MISMATCH", Refusal)
    values["amendment_original"], values["amendment_signed_at"] = validate_amendment(values["amendment_signature"], q)
    runtime = values["runtime"]
    need(set(runtime) == RUNTIME_KEYS and runtime["schema"] == "F2_RUNTIME_IDENTITY_V1" and
         runtime["platform"] == "linux" and
         all(runtime[k] == q[k] for k in ("source_sha256", "seal_sha256", "reference_sha256",
                                          "eligible_set_sha256", "age_sha256")) and
         type(runtime["executor_uid"]) is int and runtime["executor_uid"] >= 0 and
         type(runtime["python_version"]) is str and
         re.fullmatch(r"3\.(?:9|1[0-4])\.[0-9]+", runtime["python_version"]) is not None and
         type(runtime["python_executable_path"]) is str and
         re.fullmatch(r"/[A-Za-z0-9._/-]{1,200}", runtime["python_executable_path"]) is not None and
         pin(runtime["python_executable_sha256"]) and pin(runtime["boot_id_sha256"]) and
         pin(runtime["measurement_record_sha256"]), "RUNTIME_UNBOUND", Refusal)
    e = values["election"]
    need(set(e) == ELECTION_KEYS and e["schema"] == "F2_CAMPAIGN_ELECTION_V1" and e["epoch"] == EPOCH and
         e["operation"] == OPERATION and e["source_root"] == q["source_root"] and
         e["campaign_root"] == q["campaign_root"] and e["family_dir"] == FAMILY_DIR and
         e["revoked_name"] == REVOKED_NAME and e["claim_name"] == CLAIM_NAME, "ELECTION_CHANGED", Refusal)
    validate_identity_rows(e["source_identities"], q["source_root"] + "/" + FAMILY_DIR)
    validate_identity_rows(e["campaign_identities"], q["campaign_root"])
    validate_file_row(e["ledger_identity"], LEDGER_NAME)
    validate_file_row(e["age_identity"], AGE_NAME)
    uid = runtime["executor_uid"]
    for rows in (e["source_identities"], e["campaign_identities"]):
        need(rows[-1]["uid"] == uid and rows[-1]["mode"] == 0o700, "PRIVATE_ROOT_NOT_EXCLUSIVE", Refusal)
    need(e["source_identities"][-2]["uid"] == uid and e["source_identities"][-2]["mode"] == 0o700,
         "PRIVATE_ROOT_NOT_EXCLUSIVE", Refusal)
    led = e["ledger_identity"]
    need(led["uid"] == uid and led["mode"] == 0o600 and led["nlink"] == 1 and led["size"] == 0,
         "LEDGER_NOT_ELECTED_EMPTY", Refusal)
    age = e["age_identity"]
    need(age["nlink"] == 1 and age["uid"] in (0, uid) and age["mode"] & 0o111 and not age["mode"] & 0o022,
         "AGE_FILE_UNSAFE", Refusal)
    review = values["review"]
    need(set(review) == {"schema", "verdict", "source_sha256", "seal_sha256", "reference_sha256",
                         "eligible_set_sha256", "runtime_sha256", "election_sha256", "amendment7_signature_sha256",
                         "linux_result_sha256", "review_record_sha256"} and
         review["schema"] == "F2_CODEX_REVIEW_V2" and review["verdict"] == "ACCEPTED_OWN_BYTES_LINUX_AND_RUNTIME" and
         all(review[k] == q[k] for k in ("source_sha256", "seal_sha256", "reference_sha256", "eligible_set_sha256",
                                         "runtime_sha256", "election_sha256", "amendment7_signature_sha256")) and
         pin(review["linux_result_sha256"]) and pin(review["review_record_sha256"]), "REVIEW_NOT_ACCEPTED", Refusal)
    return values


def validate_documents(raws):
    """B2: question published <= owner record <= 21:45 BRT; Emenda 7 original signed <= owner record."""
    need(type(raws) is dict and set(raws) == BOUND_DOCUMENTS, "BOUND_SET_INCOMPLETE", Refusal)
    values = validate_context({k: v for k, v in raws.items() if k != "owner"})
    owner = values["owner"] = strict(raws["owner"])
    need(set(owner) == OWNER_KEYS and owner["schema"] == "F2_OWNER_SIGNATURE_V1" and
         owner["request_sha256"] == sha(raws["request"]) and
         owner["question_sha256"] == sha(owner_question(raws["request"])) and owner["answer"] == "Assino" and
         owner["channel"] == "REGISTRO_PELA_FABLE", "OWNER_NOT_SIGNED", Refusal)
    published, recorded = stamp(owner["question_published_at_utc"]), stamp(owner["recorded_at_utc"])
    need(published <= recorded, "OWNER_ANSWER_BEFORE_QUESTION", Refusal)
    need(recorded <= stamp(OWNER_DEADLINE), "OWNER_SIGNED_AFTER_2145_BRT", Refusal)
    need(values["amendment_signed_at"] <= recorded, "OWNER_SIGNED_BEFORE_AMENDMENT", Refusal)
    return values


def validate_eligible(raw, q):
    need(sha(raw) == q["eligible_set_sha256"], "ELIGIBLE_SET_CHANGED", Refusal)
    value = strict(raw, ELIGIBLE_LIMIT)
    need(set(value) == {"schema", "provenance", "types", "readiness_rule", "symbols"} and
         value["schema"] == "F2_ELIGIBLE_SET_V1" and value["readiness_rule"] == RULE and
         value["types"] == TYPES, "ELIGIBLE_SET_INVALID", Refusal)
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


def directory_identity(path, info):
    return {"path": path, "device": info.st_dev, "inode": info.st_ino,
            "uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}


def file_identity(name, info):
    return {"name": name, "device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid, "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode), "nlink": info.st_nlink, "size": info.st_size}


def open_dir(path, *, exclusive=True, physical=True):
    """Unpinned walk (token file and BOUND path only): ancestors owned by root/us, not group/other
    writable; the final directory, when exclusive, ours and mode 0700."""
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


def walk_pinned(path, rows):
    """F1 open_private_root generalized: every ancestor and the root by held descriptors (O_NOFOLLOW),
    each fstat identity (device, inode, uid, gid, mode) equal to its measured pin. Returns all fds."""
    names = paths_to_root(path)
    need(type(rows) is list and len(rows) == len(names), "IDENTITY_CHAIN_UNBOUND", Refusal)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fds = []
    try:
        fds.append(os.open("/", flags))
        for i, (name, row) in enumerate(zip(names, rows)):
            if i:
                try:
                    fds.append(os.open(Path(name).name, flags, dir_fd=fds[-1]))
                except OSError:
                    raise Refusal("PINNED_DIRECTORY_UNAVAILABLE") from None
            seen = directory_identity(name, os.fstat(fds[-1]))
            need(seen == row, "DIRECTORY_IDENTITY_CHANGED", Refusal)
            need(seen["uid"] in (0, os.geteuid()) and not seen["mode"] & 0o022, "PRIVATE_PARENT_NOT_SAFE", Refusal)
        return fds
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise


def open_pinned_file(dir_fd, row, flags, code, *, with_size):
    """Open WITHOUT O_CREAT: an absent or replaced file refuses; identity equal to its pin."""
    try:
        fd = os.open(row["name"], flags | os.O_NOFOLLOW, dir_fd=dir_fd)
    except OSError:
        raise Refusal(code + "_UNAVAILABLE") from None
    try:
        check_pinned_fd(fd, row, code, with_size=with_size)
        return fd
    except BaseException:
        os.close(fd)
        raise


def check_pinned_fd(fd, row, code, *, with_size):
    info = os.fstat(fd)
    seen = file_identity(row["name"], info)
    keys = FILE_KEYS if with_size else FILE_KEYS - {"size"}
    need(stat.S_ISREG(info.st_mode) and all(seen[k] == row[k] for k in keys), code + "_IDENTITY_CHANGED", Refusal)


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


def load_reference_raw(raw, path):
    """Execute exactly the reference bytes that were hashed (read by held descriptor)."""
    need(sha(raw) == REFERENCE, "REFERENCE_BYTES_CHANGED", Refusal)
    module = type(sys)("f2_pinned_reference")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def load_reference(physical=True):
    path = Path(__file__).resolve().with_name("reference_extract.py")
    return load_reference_raw(read_path(str(path), 65536, physical=physical), path)


# ------------------------------------------------------------------ runtime identity (B3)
class HostProbe:
    """The host's own identity, read by this process. Tests substitute a fixture probe."""

    def platform(self):
        return sys.platform

    def euid(self):
        return os.geteuid()

    def boot_id(self):
        return read_path("/proc/sys/kernel/random/boot_id", 128)

    def python_version(self):
        return "%d.%d.%d" % sys.version_info[:3]

    def executable(self):
        path = os.path.realpath(sys.executable)
        return path, read_path(path, EXECUTABLE_LIMIT)


class Held:
    """Descriptors held for the whole slot: every ancestor of the family directory and of the
    campaign root (pinned identities), the pre-created ledger (no O_CREAT) and the age file."""

    def __init__(self, source_root, campaign_root, election):
        self.source_path = source_root + "/" + FAMILY_DIR
        self.campaign_path = campaign_root
        self.e = election
        self.src = self.camp = []
        self.ledger = self.age = None
        try:
            self.src = walk_pinned(self.source_path, election["source_identities"])
            self.camp = walk_pinned(self.campaign_path, election["campaign_identities"])
            for fds in (self.src, self.camp):
                info = os.fstat(fds[-1])
                need(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
                     "PRIVATE_ROOT_NOT_EXCLUSIVE", Refusal)
            self.ledger = open_pinned_file(self.campaign_fd, election["ledger_identity"],
                                           os.O_RDWR | os.O_APPEND, "LEDGER", with_size=False)
            self.age = open_pinned_file(self.campaign_fd, election["age_identity"], os.O_RDONLY, "AGE", with_size=True)
        except BaseException:
            self.close()
            raise

    @property
    def family_fd(self):
        return self.src[-1]

    @property
    def source_fd(self):
        return self.src[-2]

    @property
    def campaign_fd(self):
        return self.camp[-1]

    def close(self):
        for fd in list(self.src) + list(self.camp) + [self.ledger, self.age]:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.src, self.camp, self.ledger, self.age = [], [], None, None

    def check(self, q, runtime, probe):
        """All pins. Called before the claim AND again immediately before the GET."""
        need(probe.platform() == runtime["platform"], "RUNTIME_NOT_LINUX", Refusal)
        need(probe.euid() == runtime["executor_uid"] == os.geteuid(), "EXECUTOR_UID_CHANGED", Refusal)
        need(sha(probe.boot_id()) == runtime["boot_id_sha256"], "BOOT_CHANGED", Refusal)
        need(probe.python_version() == runtime["python_version"], "PYTHON_VERSION_CHANGED", Refusal)
        path, raw = probe.executable()
        need(path == runtime["python_executable_path"] and sha(raw) == runtime["python_executable_sha256"],
             "PYTHON_EXECUTABLE_CHANGED", Refusal)
        # Held descriptors still carry the pinned identities (mode/owner changes)...
        for fds, rows in ((self.src, self.e["source_identities"]), (self.camp, self.e["campaign_identities"])):
            for fd, row in zip(fds, rows):
                need(directory_identity(row["path"], os.fstat(fd)) == row, "HELD_DIRECTORY_CHANGED", Refusal)
            # ...and the names still resolve to them (replacement/rename).
            for fd in walk_pinned(fds is self.src and self.source_path or self.campaign_path, rows):
                os.close(fd)
        check_pinned_fd(self.ledger, self.e["ledger_identity"], "LEDGER", with_size=False)
        os.close(open_pinned_file(self.campaign_fd, self.e["ledger_identity"], os.O_RDONLY, "LEDGER", with_size=False))
        check_pinned_fd(self.age, self.e["age_identity"], "AGE", with_size=True)
        os.close(open_pinned_file(self.campaign_fd, self.e["age_identity"], os.O_RDONLY, "AGE", with_size=True))
        need(sha(read_fd(self.age, 32 * 1024 * 1024)) == AGE_SHA256 == q["age_sha256"], "AGE_BYTES_CHANGED", Refusal)
        # Own installed bytes, read through the held family/source descriptors.
        need(sha(read_at(self.family_fd, "series_runtime.py", 1024 * 1024)) == q["source_sha256"],
             "SOURCE_BYTES_CHANGED", Refusal)
        need(sha(read_at(self.family_fd, "SHA256SUMS", 1024 * 1024)) == q["seal_sha256"], "SEAL_BYTES_CHANGED", Refusal)
        reference = read_at(self.family_fd, "reference_extract.py", 65536)
        need(sha(reference) == q["reference_sha256"] == REFERENCE, "REFERENCE_BYTES_CHANGED", Refusal)
        eligible = read_at(self.source_fd, "ELIGIBLE_SET.json", ELIGIBLE_LIMIT)
        need(sha(eligible) == q["eligible_set_sha256"], "ELIGIBLE_SET_CHANGED", Refusal)
        return {"reference": reference, "eligible": eligible}


def chain_identities(path):
    rows = []
    for name in paths_to_root(path):
        info = os.lstat(name)
        need(stat.S_ISDIR(info.st_mode), "MEASUREMENT_PARENT_NOT_DIRECTORY", Refusal)
        rows.append(directory_identity(name, info))
    return rows


def measure(probe, now):
    """Read-only (as F1 measure_runtime): no directory, token, claim, signature or provider."""
    election = {"schema": "F2_CAMPAIGN_ELECTION_V1", "epoch": EPOCH, "operation": OPERATION,
                "source_root": SOURCE_ROOT, "campaign_root": CAMPAIGN_ROOT, "family_dir": FAMILY_DIR,
                "source_identities": chain_identities(SOURCE_ROOT + "/" + FAMILY_DIR),
                "campaign_identities": chain_identities(CAMPAIGN_ROOT), "revoked_name": REVOKED_NAME,
                "claim_name": CLAIM_NAME}
    for name, key in ((LEDGER_NAME, "ledger_identity"), (AGE_NAME, "age_identity")):
        info = os.lstat(CAMPAIGN_ROOT + "/" + name)
        need(stat.S_ISREG(info.st_mode), "MEASUREMENT_FILE_NOT_REGULAR", Refusal)
        election[key] = file_identity(name, info)
    held = Held(SOURCE_ROOT, CAMPAIGN_ROOT, election)
    try:
        exe_path, exe_raw = probe.executable()
        pins = {"source_sha256": sha(read_at(held.family_fd, "series_runtime.py", 1024 * 1024)),
                "seal_sha256": sha(read_at(held.family_fd, "SHA256SUMS", 1024 * 1024)),
                "reference_sha256": sha(read_at(held.family_fd, "reference_extract.py", 65536)),
                "eligible_set_sha256": sha(read_at(held.source_fd, "ELIGIBLE_SET.json", ELIGIBLE_LIMIT)),
                "age_sha256": sha(read_fd(held.age, 32 * 1024 * 1024))}
        need(pins["age_sha256"] == AGE_SHA256 and pins["reference_sha256"] == REFERENCE and
             pins["eligible_set_sha256"] == ELIGIBLE_SET_PIN, "MEASURED_FIXED_BYTES_CHANGED", Refusal)
    finally:
        held.close()
    measurement = {"schema": "F2_RUNTIME_MEASUREMENT_V1", "measured_at_utc": iso(now), "platform": probe.platform(),
                   "python_version": probe.python_version(), "python_executable_path": exe_path,
                   "python_executable_sha256": sha(exe_raw), "executor_uid": probe.euid(),
                   "boot_id_sha256": sha(probe.boot_id()), "election": election,
                   "ready_or_GO": False, "owner_signature": False}
    measurement.update(pins)
    runtime = {k: measurement[k] for k in RUNTIME_KEYS - {"schema", "measurement_record_sha256"}}
    runtime.update(schema="F2_RUNTIME_IDENTITY_V1", measurement_record_sha256=sha(canonical(measurement)))
    return {"measurement": measurement, "runtime": runtime, "election": election}


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


def write_new(dir_fd, name, raw):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dir_fd)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


# ------------------------------------------------------------------ campaign ledger + per-slot claim
def claim_slot(held, slot, request_hash, now):
    """The ledger is the PRE-CREATED, pinned file (held without O_CREAT). One claim per slot:
    an existing entry or slot directory refuses. Absence of a claim never authorizes a new try."""
    root_fd, lfd = held.campaign_fd, held.ledger
    need(not _exists(root_fd, REVOKED_NAME), "CAMPAIGN_REVOKED", Refusal)
    check_pinned_fd(lfd, held.e["ledger_identity"], "LEDGER", with_size=False)
    os.close(open_pinned_file(root_fd, held.e["ledger_identity"], os.O_RDONLY, "LEDGER", with_size=False))
    try:
        fcntl.flock(lfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise Refusal("LEDGER_BUSY") from None
    try:
        existing = read_fd(lfd, 1024 * 1024)
        claimed = set()
        for line in existing.splitlines():
            row = strict(line)
            need(row.get("slot") != slot, "SLOT_ALREADY_CLAIMED", Refusal)
            claimed.add(row.get("slot"))
        # A slot directory without its ledger line (recreated/emptied ledger, or an earlier uncertain
        # claim) refuses: the ledger can never be reset to reopen an option.
        need({name for name in SLOTS if _exists(root_fd, name)} <= claimed, "LEDGER_SLOT_DIRECTORY_MISMATCH", Refusal)
        try:
            os.mkdir(slot, 0o700, dir_fd=root_fd)
        except FileExistsError:
            raise Refusal("SLOT_ALREADY_CLAIMED") from None
        # From here the slot is consumed: no path back to unclaimed. Any failure below is
        # ClaimUncertain, and nothing is ever written outside a held slot descriptor.
        sfd = None
        try:
            sfd = os.open(slot, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            line = canonical({"schema": "F2_SLOT_CLAIM_V1", "slot": slot, "scheduled_at": SLOTS[slot],
                              "request_sha256": request_hash, "claimed_at": iso(now), "automatic_retry": False})
            os.write(lfd, line + b"\n")
            os.fsync(lfd)
            os.fsync(root_fd)
            write_new(sfd, CLAIM_NAME, line)
            os.fsync(sfd)
        except BaseException:
            if sfd is not None:
                os.close(sfd)
            raise ClaimUncertain("SLOT_CLAIM_UNCERTAIN") from None
    finally:
        try:
            fcntl.flock(lfd, fcntl.LOCK_UN)
        except OSError:
            pass
    return sfd


def _exists(dir_fd, name):
    try:
        os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


# ------------------------------------------------------------------ one slot
def run(raws, slot, token_reader, *, clock=lambda: datetime.now(timezone.utc), monotonic=time.monotonic,
        cipher=cipher_to_fd, provider_factory=Provider, physical=True, probe=None, reference=None,
        between_claim_and_get=None):
    """`between_claim_and_get` exists only so synthetic tests can change the world at that point."""
    started, mark = clock(), monotonic()
    # 1. Clock, documents and owner-before-slot: refusal here has no effect at all.
    clock_guard(slot, started)
    values = validate_documents(raws)
    q, runtime, election, owner = values["request"], values["runtime"], values["election"], values["owner"]
    owner_slot_guard(owner, slot, started)
    request_hash = sha(raws["request"])
    probe = probe or HostProbe()
    if physical:
        need(sys.platform == "linux", "RUNTIME_NOT_LINUX", Refusal)
        need(Path(__file__).resolve() == Path(q["source_root"]) / FAMILY_DIR / "series_runtime.py",
             "RUNTIME_NOT_INSTALLED_COPY", Refusal)
    # 2. Held identities and every pin, before claim: any divergence refuses without effect.
    held = Held(q["source_root"], q["campaign_root"], election)
    provider = slot_fd = None
    try:
        snapshot = held.check(q, runtime, probe)
        eligible = validate_eligible(snapshot["eligible"], q)
        ref = reference or load_reference_raw(snapshot["reference"],
                                              Path(q["source_root"]) / FAMILY_DIR / "reference_extract.py")
        token = token_reader()
        provider = provider_factory(token, monotonic=monotonic, clock=clock)
        del token
        need(monotonic() - mark < 10, "START_LATE_FOR_SLOT", Refusal)
        now = clock()
        skew_guard(clock, monotonic, started, mark, Refusal)
        clock_guard(slot, now)
        owner_slot_guard(owner, slot, now)
        slot_fd = claim_slot(held, slot, request_hash, now)
    except ClaimUncertain:
        slot_fd = None
        result_code = "SLOT_CLAIM_UNCERTAIN"
    except BaseException as error:
        held.close()
        if isinstance(error, Refusal):
            raise
        # Any other failure before mkdir (I/O, reference load) had no slot effect.
        raise Refusal(safe_code(error)) from None
    else:
        result_code = None
    root = held.campaign_fd
    prior = None
    result = {"schema": "F2_PUBLIC_SLOT_RESULT_V1", "family": FAMILY, "operation": OPERATION, "slot": slot,
              "scheduled_at": SLOTS[slot], "status": "SLOT_HOLD", "code": result_code, "pass": None,
              "request_sha256": request_hash, "eligible_set_sha256": q["eligible_set_sha256"],
              "source_sha256": q["source_sha256"], "seal_sha256": q["seal_sha256"],
              "runtime_sha256": q["runtime_sha256"], "election_sha256": q["election_sha256"], "started_at": iso(started),
              "fetch_started_at": None, "received_at": None, "http_status": None, "body_sha256": None,
              "body_bytes": None, "completed_at": None, "logical_fetch_calls": 0, "counts": None,
              "inventory_sha256": None, "cipher_sha256": None, "cipher_bytes": None, "slot_consumed": True,
              "pre_get_recheck": None, "automatic_retry": False, "provider_ready_granted": False,
              "capacity_or_E6_or_GO_granted": False}
    if slot_fd is None:
        # Claim uncertain: no held slot descriptor, never write by name.
        result["completed_at"] = iso(clock())
        held.close()
        return result
    try:
        # 3. Between claim and GET: every pin again, then calendar/clock, then REVOKED last.
        try:
            if between_claim_and_get is not None:
                between_claim_and_get()
            held.check(q, runtime, probe)
            skew_guard(clock, monotonic, started, mark, Hold)
            now = clock()
            clock_guard(slot, now, Hold)
            owner_slot_guard(owner, slot, now, Hold)
            need(not _exists(root, REVOKED_NAME), "CAMPAIGN_REVOKED_BEFORE_GET")
            result["pre_get_recheck"] = "PASS"
        except BaseException as error:
            # Environment changed after the claim: HOLD, no GET and no child process.
            result["pre_get_recheck"] = "FAIL"
            raise Hold(safe_code(error)) from None
        if physical:
            prior = signal.getsignal(signal.SIGALRM)
            def alarm(_s, _f):
                raise Hold("EXECUTION_DEADLINE")
            signal.signal(signal.SIGALRM, alarm)
        private = {name.replace("_", "-") + ".json": raws[name] for name in sorted(BOUND_DOCUMENTS)}
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
            check_pinned_fd(held.age, election["age_identity"], "AGE", with_size=True)
            need(sha(read_fd(held.age, 32 * 1024 * 1024)) == AGE_SHA256, "AGE_BYTES_CHANGED")
            cipher(held.age, fd, bundle, remaining)
            os.fsync(fd)
            sealed = read_fd(fd, PRIVATE_LIMIT + 1024 * 1024)
            need(sealed.startswith(b"age-encryption.org/v1\n"), "CIPHER_FORMAT_INVALID")
            result["cipher_sha256"], result["cipher_bytes"] = sha(sealed), len(sealed)
        finally:
            os.close(fd)
        need(monotonic() <= mark + MAX_SECONDS, "EXECUTION_BUDGET_EXCEEDED")
    except BaseException as error:
        result["status"], result["code"] = "SLOT_HOLD", safe_code(error)
    finally:
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
        held.close()
    return result


def refusal_record(code):
    return {"schema": "F2_PUBLIC_REFUSAL_V1", "status": "SLOT_REFUSED_NO_EFFECT", "code": code,
            "logical_fetch_calls": 0, "slot_consumed": False, "automatic_retry": False,
            "at": iso(datetime.now(timezone.utc))}


def main(argv=None, runner=None):
    """Exit 0 observed; 3 only for a Refusal (no effect); 2 for any HOLD, including an unexpected
    exception escaping run() (slot_consumed then UNKNOWN). A failing final write never changes the code."""
    parser = QuietParser(description="F2 series slot. Requires own reviewed signed bytes. One GET, no retry.")
    parser.add_argument("command", choices=("run",))
    parser.add_argument("--bound", required=True)
    parser.add_argument("--slot", required=True)
    try:
        args = parser.parse_args(argv)
        # Clock first: a late or post-cutoff start is refused before reading anything.
        clock_guard(args.slot, datetime.now(timezone.utc))
        need(args.bound == SOURCE_ROOT + "/BOUND.json", "BOUND_PATH_NOT_PINNED", Refusal)
        bound = strict(read_path(args.bound, 2 * 1024 * 1024))
        need(set(bound) == {"schema", "documents"} and bound["schema"] == "F2_BOUND_V2" and
             type(bound["documents"]) is dict, "BOUND_SCHEMA_INVALID", Refusal)
        raws = {k: canonical(v) for k, v in bound["documents"].items()}
        q = validate_documents(raws)["request"]
        result = (runner or run)(raws, args.slot, lambda: read_token(q["provider_env_path"], q["provider_env_key"]))
    except Refusal as error:
        result = refusal_record(safe_code(error))
    except BaseException as error:
        result = {"schema": "F2_PUBLIC_SLOT_HOLD_V1", "status": "SLOT_HOLD", "code": safe_code(error),
                  "logical_fetch_calls": "UNKNOWN", "slot_consumed": "UNKNOWN", "automatic_retry": False,
                  "at": iso(datetime.now(timezone.utc))}
    if result.get("status") in ("SLOT_OBSERVED_PASS", "SLOT_OBSERVED_FAIL"):
        code = 0
    elif result.get("status") == "SLOT_REFUSED_NO_EFFECT":
        code = 3
    else:
        code = 2
    try:
        os.write(1, canonical(result) + b"\n")
    except BaseException:
        pass
    return code


if __name__ == "__main__":
    raise SystemExit(main())
