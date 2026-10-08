"""F1 only: bounded provider GETs and ciphertext evidence; no application imports.

Import is inert. The CLI requires a reviewed, signed, exact request before any
claim, child or provider access. An accepted documentary record is not a
cryptographic human signature. Linux physical identity must be supplied by Fable.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
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

FAMILY = "F1_PROVIDER_DIAGNOSTIC_V1"
OPERATION = "GO_READ_PROVIDER_DIAGNOSTIC_EMENDA6_ONCE_01"
EPOCH = "R2D2-V2-SHADOW-2026-10-05"
AMENDMENT = "03c9dddd2858fde584a6ccb5dd2ad74caac0a366fa03782132a161774c061efd"
AMENDMENT_SIGNATURE_ORIGINAL = "a46011c1b27c0f16161bbda4fbc38de6e740c888c172c1de5f7540b63b70f58d"
AMENDMENT_SIGNATURE_COMMENT = 6064499368
AMENDMENT_SIGNATURE_BODY = "1e501d070cb8c3bd7cc8f33e86148705dccc93af3cdbb1f35f8c4f101e867643"
DESIGN = "5dcbe133d8e52ea339e7e24beefe10951eef7cf55e8c07f076a9bd9585632bae"
REFERENCE = "e50e2263ea07a5a31db43f3e2a6cb68dec769ffa1e808d6197f622c78020acd1"
RECIPIENT = "age1knekenhrh79x9xm0ghvhltwg075d33mljhu4y6u9zyz3cweszens2vr8x0"
AGE_SHA256 = "eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c"
PROVIDER_HOST = "eodhd.com"
REGISTRY_PATH = "/api/exchange-symbol-list/US"
BULK_PATH = "/api/eod-bulk-last-day/US"
BULK_DAY = "2026-10-07"
COMPARISON_SESSION = "2026-10-08"
PREVIOUS_CLOSE = "2026-10-07T20:00:00Z"
MAX_SECONDS = 120
NETWORK_SECONDS = 60
CIPHER_SECONDS = 60
SOCKET_SECONDS = 15
REGISTRY_LIMIT = 32 * 1024 * 1024
BULK_LIMIT = 64 * 1024 * 1024
PRIVATE_LIMIT = 128 * 1024 * 1024
CLAIM_NAME = "emenda6-provider-diagnostic-epoch03.claim"
CIPHER_NAME = "provider-diagnostic.age"
RECEIPT_NAME = "RESULT.public.json"
WINDOWS = {"2026-10-08": (17, 0, 18, 30), "2026-10-09": (14, 0, 17, 30)}
HEX = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_KEYS = {"schema", "operation", "epoch", "execution_date", "not_before", "not_after",
                "max_seconds", "session_date", "bulk_date", "previous_close", "recipient",
                "amendment_sha256", "design_sha256", "source_sha256", "reference_sha256",
                "seal_sha256", "election_sha256", "runtime_sha256", "review_sha256",
                "amendment_signature_sha256", "private_root", "parent_identities",
                "age_path", "age_sha256", "budget_seconds", "logical_fetch_limit", "retry_limit"}


class Hold(ValueError):
    """Only a fixed code is public."""


class QuietParser(argparse.ArgumentParser):
    def error(self, _message):
        raise Hold("CLI_ARGUMENTS_INVALID")


def need(condition, code):
    if not condition:
        raise Hold(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def strict(raw, limit=1024 * 1024):
    need(type(raw) is bytes and 0 < len(raw) <= limit, "DOCUMENT_SIZE_INVALID")
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, "DOCUMENT_DUPLICATE_KEY")
            result[key] = value
        return result
    def constant(value):
        raise Hold("DOCUMENT_NONFINITE_NUMBER")
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except Hold:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Hold("DOCUMENT_JSON_INVALID") from None
    need(type(result) is dict and canonical(result) == raw, "DOCUMENT_NOT_CANONICAL")
    return result


def stamp(value):
    need(type(value) is str and value.endswith("Z"), "TIME_NOT_UTC")
    try:
        found = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        raise Hold("TIME_INVALID") from None
    need(found.utcoffset() == timedelta(0), "TIME_NOT_UTC")
    return found


def iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def pin(value):
    return type(value) is str and HEX.fullmatch(value) and value != "0" * 64


def safe_code(error):
    if isinstance(error, Hold) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", str(error)):
        return str(error)
    return "DIAGNOSTIC_INTERNAL_FAILURE"


def allowed_start(moment):
    local = moment - timedelta(hours=3)
    second = local.minute * 60 + local.second + local.microsecond / 1e6
    return (0 <= second < 220 or 480 <= second < 520 or
            1560 <= second < 2020 or 2280 <= second < 3600)


def validate_window(request):
    day = request["execution_date"]
    need(day in WINDOWS, "EXECUTION_DATE_NOT_AUTHORIZED")
    start, end = stamp(request["not_before"]), stamp(request["not_after"])
    a, b, c, d = WINDOWS[day]
    lower = stamp(day + "T%02d:%02d:00Z" % (a + 3, b))
    upper = stamp(day + "T%02d:%02d:00Z" % (c + 3, d))
    need(lower <= start < end <= upper and start.date() == end.date(), "WINDOW_NOT_AUTHORIZED")
    need(MAX_SECONDS <= (end - start).total_seconds() <= 900, "WINDOW_DURATION_INVALID")
    need(allowed_start(start), "WINDOW_START_FORBIDDEN")
    return start, end


def paths_to_root(path):
    need(type(path) is str and re.fullmatch(r"/[A-Za-z0-9._/-]{1,220}", path), "PRIVATE_PATH_INVALID")
    p = Path(path)
    need(str(p) == path and ".." not in p.parts and "//" not in path and len(p.parts) <= 18,
         "PRIVATE_PATH_INVALID")
    return ["/"] + [str(Path(*p.parts[:i])) for i in range(2, len(p.parts) + 1)]


def directory_identity(path, info):
    return {"path": path, "device": info.st_dev, "inode": info.st_ino,
            "uid": info.st_uid, "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}


def open_private_root(request):
    """Walk each signed parent by held descriptors, rejecting links and replacement."""
    names = paths_to_root(request["private_root"])
    rows = request["parent_identities"]
    need(type(rows) is list and len(rows) == len(names), "PRIVATE_PARENTS_UNBOUND")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for i, (name, row) in enumerate(zip(names, rows)):
            need(type(row) is dict and set(row) == {"path", "device", "inode", "uid", "gid", "mode"},
                 "PRIVATE_PARENTS_UNBOUND")
            if i:
                child = os.open(Path(name).name, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            seen = directory_identity(name, os.fstat(fd))
            need(seen == row, "PRIVATE_DIRECTORY_IDENTITY_CHANGED")
            need(seen["uid"] in (0, os.geteuid()) and not seen["mode"] & 0o022,
                 "PRIVATE_PARENT_NOT_SAFE")
        need(rows[-1]["uid"] == os.geteuid() and rows[-1]["mode"] == 0o700,
             "PRIVATE_ROOT_NOT_EXCLUSIVE")
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_regular(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_size <= limit and info.st_nlink == 1,
             "INPUT_FILE_INVALID")
        parts, size = [], 0
        while True:
            block = os.read(fd, min(65536, limit + 1 - size))
            if not block:
                break
            parts.append(block)
            size += len(block)
            need(size <= limit, "INPUT_FILE_TOO_LARGE")
        after = os.fstat(fd)
        need((info.st_size, info.st_mtime_ns, info.st_ctime_ns) ==
             (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "INPUT_FILE_CHANGED")
        return b"".join(parts)
    finally:
        os.close(fd)


def load_reference():
    path = Path(__file__).resolve().with_name("reference_extract.py")
    raw = read_regular(str(path), 65536)
    need(sha(raw) == REFERENCE, "REFERENCE_BYTES_CHANGED")
    module = type(sys)("f1_pinned_reference")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def amendment_record(original_raw):
    """Preserve the real accepted record's original bytes; do not create an answer."""
    need(sha(original_raw) == AMENDMENT_SIGNATURE_ORIGINAL, "AMENDMENT_ORIGINAL_BYTES_CHANGED")
    original = json.loads(original_raw)
    need(set(original) == {"schema", "amendment", "revision", "document_file", "document_sha256", "answer",
                           "signed_at_utc", "channel"} and
         original["schema"] == "DUDU_AMENDMENT_SIGNATURE_V1" and original["amendment"] == "A2_EMENDA_06" and
         original["revision"] == 1 and original["document_sha256"] == AMENDMENT and
         original["answer"] == "Assino a emenda 6 da A2" and
         original["channel"] == "Claude Code (Fable), AskUserQuestion", "AMENDMENT_NOT_SIGNED")
    stamp(original["signed_at_utc"])
    return {"schema": "F1_AMENDMENT_SIGNATURE_V1", "amendment_sha256": AMENDMENT,
            "answer": original["answer"], "recorded_at_utc": original["signed_at_utc"], "channel": "REGISTRO_PELA_FABLE",
            "original_record_sha256": sha(original_raw), "original_record_base64": base64.b64encode(original_raw).decode("ascii"),
            "source_comment_id": AMENDMENT_SIGNATURE_COMMENT, "source_comment_body_sha256": AMENDMENT_SIGNATURE_BODY}


def validate_context(raws, now):
    """Unsigned leaf preflight. No fake owner record is used to prepare a question."""
    need(set(raws) == {"request", "amendment_signature", "election", "runtime", "review"},
         "CONTEXT_SET_INCOMPLETE")
    values = {k: strict(v) for k, v in raws.items()}
    q = values["request"]
    need(set(q) == REQUEST_KEYS and q["schema"] == "F1_REQUEST_V1" and q["operation"] == OPERATION,
         "REQUEST_SCHEMA_INVALID")
    need(q["epoch"] == EPOCH and q["session_date"] == COMPARISON_SESSION and q["bulk_date"] == BULK_DAY and
         q["previous_close"] == PREVIOUS_CLOSE, "OBSERVATION_SCOPE_CHANGED")
    need(q["amendment_sha256"] == AMENDMENT and q["design_sha256"] == DESIGN and
         q["reference_sha256"] == REFERENCE and q["recipient"] == RECIPIENT,
         "DOCUMENTARY_SCOPE_CHANGED")
    need(type(q["max_seconds"]) is int and type(q["logical_fetch_limit"]) is int and type(q["retry_limit"]) is int and
         q["max_seconds"] == MAX_SECONDS and q["budget_seconds"] == {"network": 60, "cipher": 60} and
         q["logical_fetch_limit"] == 2 and q["retry_limit"] == 0, "LIMITS_CHANGED")
    for key in ("source_sha256", "seal_sha256", "election_sha256", "runtime_sha256", "review_sha256",
                "amendment_signature_sha256", "age_sha256"):
        need(pin(q[key]), "PIN_INVALID")
    need(q["age_sha256"] == AGE_SHA256, "AGE_PIN_CHANGED")
    for name in ("election", "runtime", "review", "amendment_signature"):
        need(sha(raws[name]) == q[name + "_sha256"], "BOUND_INPUT_PIN_MISMATCH")
    start, end = validate_window(q)
    signature = values["amendment_signature"]
    try:
        original = base64.b64decode(signature["original_record_base64"], validate=True)
    except (KeyError, ValueError, TypeError):
        raise Hold("AMENDMENT_ORIGINAL_UNAVAILABLE") from None
    need(signature == amendment_record(original) and
         stamp(signature["recorded_at_utc"]) <= now, "AMENDMENT_NOT_SIGNED")
    election = values["election"]
    need(set(election) == {"schema", "epoch", "operation", "amendment_sha256", "private_root", "parent_identities", "claim_name"} and
         election["schema"] == "F1_SINGLE_ELECTION_V1" and election["epoch"] == EPOCH and
         election["operation"] == OPERATION and election["amendment_sha256"] == AMENDMENT and
         election["private_root"] == q["private_root"] and election["parent_identities"] == q["parent_identities"] and
         election["claim_name"] == CLAIM_NAME, "ELECTION_CHANGED")
    names = paths_to_root(q["private_root"])
    need(type(election["parent_identities"]) is list and len(election["parent_identities"]) == len(names),
         "PRIVATE_PARENTS_UNBOUND")
    for name, row in zip(names, election["parent_identities"]):
        need(type(row) is dict and set(row) == {"path", "device", "inode", "uid", "gid", "mode"} and
             row["path"] == name and all(type(row[k]) is int and row[k] >= 0 for k in ("device", "inode", "uid", "gid", "mode")),
             "PRIVATE_PARENTS_UNBOUND")
    runtime = values["runtime"]
    need(set(runtime) == {"schema", "source_sha256", "reference_sha256", "seal_sha256", "age_sha256", "python_version", "python_executable_sha256", "boot_id_sha256", "executor_uid", "platform", "measurement_record_sha256"} and
         runtime["schema"] == "F1_RUNTIME_IDENTITY_V1" and runtime["platform"] == "linux" and
         all(runtime[k] == q[k] for k in ("source_sha256", "reference_sha256", "seal_sha256", "age_sha256")) and
         type(runtime["executor_uid"]) is int and runtime["executor_uid"] >= 0 and
         type(runtime["python_version"]) is str and re.fullmatch(r"3\.(?:9|1[0-4])\.[0-9]+", runtime["python_version"]) and
         pin(runtime["boot_id_sha256"]) and pin(runtime["python_executable_sha256"]) and
         pin(runtime["measurement_record_sha256"]), "RUNTIME_UNBOUND")
    review = values["review"]
    need(set(review) == {"schema", "verdict", "source_sha256", "reference_sha256", "seal_sha256", "runtime_sha256", "election_sha256", "linux_result_sha256", "review_record_sha256"} and
         review["schema"] == "F1_CODEX_REVIEW_V1" and review["verdict"] == "ACCEPTED_OWN_BYTES_LINUX_AND_RUNTIME" and
         all(review[k] == q[k] for k in ("source_sha256", "reference_sha256", "seal_sha256", "runtime_sha256", "election_sha256")) and
         pin(review["linux_result_sha256"]) and pin(review["review_record_sha256"]), "REVIEW_NOT_ACCEPTED")
    paths_to_root(q["private_root"])
    need(type(q["age_path"]) is str and q["age_path"].startswith(q["private_root"] + "/") and
         re.fullmatch(r"[A-Za-z0-9._-]{1,80}", q["age_path"][len(q["private_root"]) + 1:]),
         "AGE_OUTSIDE_PRIVATE_ROOT")
    return values


def validate_documents(raws, now):
    need(set(raws) == {"request", "owner", "amendment_signature", "election", "runtime", "review"},
         "BOUND_SET_INCOMPLETE")
    values = validate_context({k: v for k, v in raws.items() if k != "owner"}, now)
    q, signature = values["request"], values["amendment_signature"]
    start, end = validate_window(q)
    need(start <= now and now + timedelta(seconds=MAX_SECONDS) <= end and allowed_start(now),
         "OUTSIDE_START_WINDOW")
    owner = values["owner"] = strict(raws["owner"])
    request_hash = sha(raws["request"])
    need(set(owner) == {"schema", "request_sha256", "question_sha256", "answer", "recorded_at_utc", "channel"} and
         owner["schema"] == "F1_OWNER_SIGNATURE_V1" and owner["request_sha256"] == request_hash and
         owner["question_sha256"] == sha(owner_question(raws["request"])) and owner["answer"] == "Assino" and
         owner["channel"] == "REGISTRO_PELA_FABLE" and
         stamp(signature["recorded_at_utc"]) <= stamp(owner["recorded_at_utc"]) <= now and
         stamp(owner["recorded_at_utc"]) <= stamp(q["execution_date"] + "T20:59:59Z") + timedelta(hours=3),
         "OWNER_NOT_SIGNED")
    return values


def owner_question(request_raw):
    q = strict(request_raw)
    return ("F1: uma leitura de diagnóstico, dois GETs, sem retry, bulk 07/10; NÃO é prontidão ou GO.\n"
            "REQUEST SHA256: " + sha(request_raw) + "\nEmenda 6 SHA256: " + AMENDMENT +
            "\nJanela UTC: " + q["not_before"] + " — " + q["not_after"] +
            "\nUma tentativa TOTAL entre quinta e sexta; eleição SHA256: " + q["election_sha256"] +
            "\nSaída completa privada cifrada; ausência/NÃO mantém HOLD. Resposta literal: Assino\n").encode("utf-8")


def analyze(registry_raw, bulk_raw, registry_at, bulk_at):
    ref = load_reference()
    previous = stamp(PREVIOUS_CLOSE)
    need(previous < registry_at <= bulk_at, "RECEIPT_TIME_INVALID")
    registry_response = ref.Response(registry_raw, registry_at, REGISTRY_PATH)
    registry, receipt = ref.build_registry(registry_response, previous_close=previous)
    raw_registry = registry_response.json()
    bulk_response = ref.Response(bulk_raw, bulk_at, BULK_PATH)
    rows = bulk_response.json()
    need(type(rows) is list, "BULK_INVALID")
    eligible = {x["symbol"] for x in registry["instruments"] if x["security_type"] in ref.DAILY_ELIGIBLE_TYPES}
    origins = {}
    skipped, registry_duplicates = [], []
    for i, row in enumerate(raw_registry):
        if type(row) is not dict or row.get("Exchange") not in ref.ALLOWED_EXCHANGES or not ref._symbol_ok(row.get("Code")):
            skipped.append({"pointer": "/" + str(i), "reason": "NORMALIZER_EXCLUDED_ROW"})
        elif row["Code"] in origins:
            registry_duplicates.append({"symbol": row["Code"], "pointer": "/" + str(i)})
        else:
            origins[row["Code"]] = "/" + str(i)
    grouped, ignored, dated = {}, [], 0
    for i, row in enumerate(rows):
        if type(row) is not dict or row.get("date") != BULK_DAY:
            ignored.append({"pointer": "/" + str(i), "reason": "ROW_NOT_OF_REQUESTED_DATE"})
            continue
        dated += 1
        code = row.get("code")
        if isinstance(code, str) and code in eligible:
            grouped.setdefault(code, []).append((i, row))
        else:
            ignored.append({"pointer": "/" + str(i), "reason": "ROW_NOT_OF_ELIGIBLE_SET"})
    duplicates = conflicts = 0
    usable, unusable = set(), []
    for symbol, pairs in sorted(grouped.items()):
        distinct = ref._distinct([x[1] for x in pairs])
        duplicates += len(pairs) - len(distinct)
        reasons = []
        if len(distinct) != 1:
            conflicts += 1
            reasons.append("CONFLICTING_DISTINCT_ROWS")
        elif ref._bar(distinct[0], date.fromisoformat(BULK_DAY), bulk_at) is not None:
            usable.add(symbol)
        else:
            row = distinct[0]
            for field in ("open", "high", "low", "close", "volume"):
                if field not in row:
                    reasons.append("MISSING_" + field.upper())
                elif ref._number(row[field]) is None:
                    reasons.append("INVALID_NUMBER_" + field.upper())
            if not reasons:
                if min(row[x] for x in ("open", "high", "low", "close")) <= 0:
                    reasons.append("NONPOSITIVE_PRICE")
                if row["volume"] < 0:
                    reasons.append("NEGATIVE_VOLUME")
                if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
                    reasons.append("OHLC_ORDER_INVALID")
        if reasons:
            unusable.append({"symbol": symbol, "registry_pointer": origins[symbol],
                             "bulk_pointers": ["/" + str(i) for i, _ in pairs], "reasons": reasons})
    missing = [{"symbol": s, "registry_pointer": origins[s], "reason": "ABSENT_FROM_DATED_BULK_NOT_PROVIDER_CAUSE"}
               for s in sorted(eligible - grouped.keys())]
    last_trade = [{"symbol": s, "registry_pointer": origins[s], "status": "UNKNOWN_NOT_PROVIDED",
                   "reason": "NO_PINNED_FIELD_WITH_CERTIFIED_LAST_TRADE_SEMANTICS"} for s in sorted(eligible)]
    counts = {"registry_symbols": len(registry["instruments"]), "eligible_symbols": len(eligible),
              "present_eligible_symbols": len(grouped), "usable_eligible_symbols": len(usable),
              "absent_eligible_symbols": len(missing), "present_unusable_symbols": len(unusable),
              "required_minimum": (95 * len(eligible) + 99) // 100, "minimum_eligible_rule": 4000,
              "conflicting_eligible_symbols": conflicts, "duplicate_eligible_rows": duplicates,
              "bulk_rows": len(rows), "dated_rows": dated, "ignored_bulk_rows": len(ignored),
              "last_trade_unknown_symbols": len(last_trade), "registry_duplicate_rows": len(registry_duplicates)}
    need(counts["present_eligible_symbols"] + counts["absent_eligible_symbols"] == counts["eligible_symbols"] and
         counts["usable_eligible_symbols"] + counts["present_unusable_symbols"] == counts["present_eligible_symbols"],
         "SET_COUNTS_INCONSISTENT")
    return {"schema": "F1_PRIVATE_ANALYSIS_V1", "status": "DIAGNOSTIC_COMPLETE_WITH_LAST_TRADE_UNKNOWN",
            "session_date": COMPARISON_SESSION, "bulk_date": BULK_DAY,
            "raw_sha256": {"registry": sha(registry_raw), "bulk": sha(bulk_raw)}, "counts": counts,
            "normalized_registry": registry, "registry_receipt": receipt, "eligible_absent": missing,
            "present_unusable": unusable, "last_trade": last_trade,
            "registry_ignored": skipped, "registry_duplicates": registry_duplicates, "bulk_ignored": ignored}


class Provider:
    def __init__(self, token, monotonic=time.monotonic, clock=lambda: datetime.now(timezone.utc)):
        need(type(token) is str and 0 < len(token) <= 4096 and not any(ord(x) < 33 for x in token),
             "PROVIDER_TOKEN_UNAVAILABLE")
        self.token, self.monotonic, self.clock = token, monotonic, clock
        self.calls = 0

    def fetch(self, kind, deadline):
        need(kind in ("registry", "bulk"), "PROVIDER_KIND_INVALID")
        path, limit = (REGISTRY_PATH, REGISTRY_LIMIT) if kind == "registry" else (BULK_PATH, BULK_LIMIT)
        begun = self.clock()
        need(self.monotonic() < deadline, "NETWORK_DEADLINE")
        params = {"api_token": self.token, "fmt": "json"}
        if kind == "bulk":
            params["date"] = BULK_DAY
        query = path + "?" + urlencode(params)
        raw, status, headers, complete, code = bytearray(), None, [], False, None
        conn = http.client.HTTPSConnection(PROVIDER_HOST, 443, timeout=min(SOCKET_SECONDS, deadline - self.monotonic()),
                                           context=ssl.create_default_context())
        self.calls += 1
        try:
            conn.request("GET", query, headers={"Accept": "application/json", "Accept-Encoding": "identity"})
            response = conn.getresponse()
            status, headers = response.status, response.getheaders()
            while True:
                remaining = deadline - self.monotonic()
                need(remaining > 0, "NETWORK_DEADLINE")
                if conn.sock:
                    conn.sock.settimeout(min(SOCKET_SECONDS, remaining))
                # read1 returns received partial blocks rather than losing a
                # short buffered block when a later socket read times out.
                block = response.read1(min(65536, limit + 1 - len(raw)))
                if not block:
                    need(response.length in (None, 0), "PROVIDER_BODY_PARTIAL")
                    complete = True
                    break
                raw.extend(block)
                need(len(raw) <= limit, "PROVIDER_BODY_TOO_LARGE")
            need(status == 200, "PROVIDER_HTTP_NOT_OK")
            need(response.getheader("Content-Encoding", "identity").lower() == "identity", "PROVIDER_ENCODING_NOT_IDENTITY")
        except http.client.IncompleteRead as error:
            raw.extend(error.partial[:max(0, limit + 1 - len(raw))])
            code = "PROVIDER_BODY_PARTIAL"
        except BaseException as error:
            code = safe_code(error) if isinstance(error, Hold) else "PROVIDER_TRANSPORT_FAILED"
        finally:
            conn.close()
        return bytes(raw), {"kind": kind, "path": path, "bulk_date": BULK_DAY if kind == "bulk" else None,
                            "started_at": iso(begun), "received_at": iso(self.clock()), "http_status": status,
                            "headers": headers, "body_sha256": sha(raw), "body_bytes": len(raw),
                            "body_complete": complete, "code": code}


def private_bundle(files):
    need(type(files) is dict and all(re.fullmatch(r"[a-z0-9_.-]{1,80}", name) and type(raw) is bytes
                                   for name, raw in files.items()), "PRIVATE_BUNDLE_MEMBER_INVALID")
    inventory = {name: {"sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(files.items())}
    manifest = canonical({"schema": "F1_PRIVATE_INVENTORY_V1", "files": inventory})
    need(sum(len(x) for x in files.values()) + len(manifest) + 1024 * (len(files) + 2) <= PRIVATE_LIMIT,
         "PRIVATE_BUNDLE_TOO_LARGE")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in sorted(dict(files, inventory=manifest).items()):
            member = tarfile.TarInfo("inventory.json" if name == "inventory" else name)
            member.size, member.mode, member.uid, member.gid, member.mtime = len(raw), 0o600, 0, 0, 0
            archive.addfile(member, io.BytesIO(raw))
    need(len(output.getvalue()) <= PRIVATE_LIMIT, "PRIVATE_BUNDLE_TOO_LARGE")
    return output.getvalue(), sha(manifest)


def cipher_to_fd(age_fd, output_fd, payload, seconds):
    """Execute only the held, hashed age binary. Plaintext travels only over stdin."""
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
    before = os.fstat(fd)
    raw = bytearray()
    while True:
        part = os.read(fd, 65536)
        if not part:
            break
        raw.extend(part)
        need(len(raw) <= limit, "CIPHER_TOO_LARGE")
    after = os.fstat(fd)
    need((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
         (after.st_size, after.st_mtime_ns, after.st_ctime_ns), "HELD_FILE_CHANGED")
    return bytes(raw)


def open_age(q):
    name = q["age_path"][len(q["private_root"]) + 1:]
    need(re.fullmatch(r"[A-Za-z0-9._-]{1,80}", name), "AGE_PATH_INVALID")
    root = open_private_root(q)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root)
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid in (0, os.geteuid()) and
             info.st_mode & 0o111 and not stat.S_IMODE(info.st_mode) & 0o022, "AGE_FILE_UNSAFE")
        need(sha(read_fd(fd, 32 * 1024 * 1024)) == q["age_sha256"], "AGE_BYTES_CHANGED")
        return fd
    except BaseException:
        if "fd" in locals():
            os.close(fd)
        raise
    finally:
        os.close(root)


def reserve(root, q, request_hash):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        fd = os.open(CLAIM_NAME, flags, 0o600, dir_fd=root)
    except FileExistsError:
        raise Hold("ATTEMPT_ALREADY_CONSUMED") from None
    try:
        os.write(fd, canonical({"schema": "F1_ATTEMPT_CLAIM_V1", "request_sha256": request_hash,
                                "election_sha256": q["election_sha256"], "operation": OPERATION,
                                "automatic_retry": False}))
        os.fsync(fd)
        os.fsync(root)
    finally:
        os.close(fd)


def run(raws, provider, *, clock=lambda: datetime.now(timezone.utc), monotonic=time.monotonic,
        cipher=cipher_to_fd, age_opener=open_age, physical=True):
    started, mark = clock(), monotonic()
    values = validate_documents(raws, started)
    q, runtime = values["request"], values["runtime"]
    request_hash = sha(raws["request"])
    if physical:
        need(sys.platform == "linux" and os.geteuid() == runtime["executor_uid"] and
             "%d.%d.%d" % sys.version_info[:3] == runtime["python_version"], "RUNTIME_CHANGED")
        need(sha(read_regular("/proc/sys/kernel/random/boot_id", 128)) == runtime["boot_id_sha256"], "BOOT_CHANGED")
        need(sha(read_regular(str(Path(sys.executable).resolve()), 64 * 1024 * 1024)) == runtime["python_executable_sha256"],
             "PYTHON_EXECUTABLE_CHANGED")
        need(sha(read_regular(str(Path(__file__)), 1024 * 1024)) == q["source_sha256"], "SOURCE_BYTES_CHANGED")
        need(sha(read_regular(str(Path(__file__).with_name("SHA256SUMS")), 1024 * 1024)) == q["seal_sha256"],
             "SEAL_BYTES_CHANGED")
    need(monotonic() - mark < MAX_SECONDS, "EXECUTION_DEADLINE")
    root = open_private_root(q)
    age_fd = None
    prior_handler = None
    def deadline_alarm(_signum, _frame):
        raise Hold("EXECUTION_DEADLINE")
    if physical:
        prior_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, deadline_alarm)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, mark + MAX_SECONDS - monotonic()))
    result = {"schema": "F1_PUBLIC_RESULT_V1", "operation": OPERATION, "status": "DIAGNOSTIC_HOLD",
              "code": None, "request_sha256": request_hash, "election_sha256": q["election_sha256"],
              "source_sha256": q["source_sha256"], "reference_sha256": REFERENCE, "seal_sha256": q["seal_sha256"],
              "runtime_sha256": q["runtime_sha256"], "started_at": iso(started), "completed_at": None,
              "logical_fetch_calls": 0, "counts": None, "raw_hashes": {}, "inventory_sha256": None,
              "cipher_sha256": None, "cipher_bytes": None, "provider_ready_granted": False,
              "capacity_or_E6_or_GO_granted": False, "attempt_consumed": False, "automatic_retry": False}
    try:
        # No provider call or child before immutable global reservation. A refusal
        # or uncertain attempt cannot be repeated under another dated request.
        reserve(root, q, request_hash)
        result["attempt_consumed"] = True
        age_fd = age_opener(q)
        private = {"request.json": raws["request"], "owner-signature.json": raws["owner"],
                   "amendment-signature.json": raws["amendment_signature"], "runtime.json": raws["runtime"],
                   "election.json": raws["election"], "review.json": raws["review"]}
        metadata, raw = {}, {}
        if physical:
            signal.setitimer(signal.ITIMER_REAL, max(0.001, mark + NETWORK_SECONDS - monotonic()))
        try:
            for kind in ("registry", "bulk"):
                deadline = min(mark + NETWORK_SECONDS, monotonic() + SOCKET_SECONDS)
                if physical:
                    signal.setitimer(signal.ITIMER_REAL, max(0.001, deadline - monotonic()))
                body, meta = provider.fetch(kind, deadline)
                if physical:
                    signal.setitimer(signal.ITIMER_REAL, max(0.001, mark + NETWORK_SECONDS - monotonic()))
                raw[kind], metadata[kind] = body, meta
                private[kind + ".raw"] = body
                private[kind + "-receipt.json"] = canonical(meta)
                result["raw_hashes"][kind] = sha(body)
                need(meta["code"] is None and meta["body_complete"] is True and meta["http_status"] == 200,
                     meta["code"] if meta["code"] else "PROVIDER_RESPONSE_INCOMPLETE")
                need(started <= stamp(meta["started_at"]) <= stamp(meta["received_at"]) <= clock(),
                     "RECEIPT_TIME_INVALID")
            analysis = analyze(raw["registry"], raw["bulk"], stamp(metadata["registry"]["received_at"]),
                               stamp(metadata["bulk"]["received_at"]))
            need(monotonic() <= mark + NETWORK_SECONDS, "NETWORK_AND_ANALYSIS_DEADLINE")
            analyzed = canonical(analysis)
            need(sum(len(v) for v in private.values()) + len(analyzed) + 65536 <= PRIVATE_LIMIT,
                 "DERIVED_EVIDENCE_TOO_LARGE")
            private["analysis.json"] = analyzed
            result["status"], result["counts"] = analysis["status"], analysis["counts"]
        except BaseException as error:
            result["status"], result["code"] = "DIAGNOSTIC_HOLD", safe_code(error)
            private["failure.json"] = canonical({"schema": "F1_PRIVATE_FAILURE_V1", "code": result["code"],
                                                  "partial_evidence": True, "retry_allowed": False})
        result["logical_fetch_calls"] = provider.calls
        need(provider.calls <= 2, "PROVIDER_CALL_LIMIT_EXCEEDED")
        if physical:
            signal.setitimer(signal.ITIMER_REAL, max(0.001, mark + MAX_SECONDS - monotonic()))
        bundle, inventory_hash = private_bundle(private)
        result["inventory_sha256"] = inventory_hash
        remaining = min(CIPHER_SECONDS, mark + MAX_SECONDS - monotonic(),
                        (stamp(q["not_after"]) - clock()).total_seconds())
        fd = os.open(CIPHER_NAME, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
        try:
            if physical:
                need(sha(read_fd(age_fd, 32 * 1024 * 1024)) == q["age_sha256"], "AGE_BYTES_CHANGED")
            cipher(age_fd, fd, bundle, remaining)
            os.fsync(fd)
            sealed = read_fd(fd, PRIVATE_LIMIT + 1024 * 1024)
            need(sealed.startswith(b"age-encryption.org/v1\n"), "CIPHER_FORMAT_INVALID")
            result["cipher_sha256"], result["cipher_bytes"] = sha(sealed), len(sealed)
        finally:
            os.close(fd)
        need(monotonic() <= mark + MAX_SECONDS and clock() <= stamp(q["not_after"]), "EXECUTION_DEADLINE")
    except BaseException as error:
        if result["code"] != "ATTEMPT_ALREADY_CONSUMED":
            result["code"] = safe_code(error)
        result["status"] = "DIAGNOSTIC_HOLD"
    finally:
        if age_fd is not None:
            os.close(age_fd)
        if physical:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, prior_handler)
        result["logical_fetch_calls"] = provider.calls
        result["completed_at"] = iso(clock())
        if result["attempt_consumed"]:
            # Never overwrite a receipt, claim, ciphertext or any previous bytes.
            try:
                fd = os.open(RECEIPT_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=root)
                try:
                    os.write(fd, canonical(result) + b"\n")
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.fsync(root)
            except BaseException:
                result["status"], result["code"] = "DIAGNOSTIC_HOLD", "PUBLIC_RECEIPT_UNAVAILABLE"
        os.close(root)
    return result


def main(argv=None):
    parser = QuietParser(description="F1 only. Requires own reviewed signed bytes. No retry.")
    parser.add_argument("--bound", required=True, help="Canonical F1_BOUND_V1; private, no symlink.")
    try:
        args = parser.parse_args(argv)
        bound = strict(read_regular(args.bound, 1024 * 1024))
        need(set(bound) == {"schema", "documents"} and bound["schema"] == "F1_BOUND_V1" and
             type(bound["documents"]) is dict, "BOUND_SCHEMA_INVALID")
        raws = {k: canonical(v) for k, v in bound["documents"].items()}
        # Authentication and identity first, before reading a token or making a claim.
        validate_documents(raws, datetime.now(timezone.utc))
        provider = Provider(os.environ.get("F1_PROVIDER_TOKEN", ""))
        result = run(raws, provider)
    except BaseException as error:
        result = {"schema": "F1_PUBLIC_REFUSAL_V1", "status": "DIAGNOSTIC_HOLD", "code": safe_code(error),
                  "logical_fetch_calls": 0, "provider_ready_granted": False, "automatic_retry": False,
                  "dispatch_invocation_retry_allowed": False}
    os.write(1, canonical(result) + b"\n")
    return 0 if result.get("status") == "DIAGNOSTIC_COMPLETE_WITH_LAST_TRADE_UNKNOWN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
