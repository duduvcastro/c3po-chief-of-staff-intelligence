"""L12 finite batch OFFLINE CANDIDATE. No host executor, scheduler or authority issuer.

The request/owner format below is a proposed NEW ABI, not a historical F2 ABI.
An independent, pinned adapter must verify the actual authority, owner original,
receipt ABI, installation and runtime. Missing adapters fail closed. A callback
must raise on refusal and return None on acceptance; booleans are not evidence.

P and AFTER_E6 are separate requests. AFTER_E6 pins actual P commit/publish
originals present before the request and its owner answer. Named dependencies
inside each finite plan require explicit delegation in that plan's authority;
the authority callback must reject unapproved dependency selectors. There is no
future receipt hash, synthetic owner answer, retry, resume, or generic command.

R2 adds a distinct BOOTSTRAP_MONDAY request for install_release/readback/activate.
Exact image GO/proposal hashes and actual Sunday FULL PRE precede its owner
answer by Sunday 21:45 BRT. Monday M2 POST is selected only as an actual completed
receipt before M3; it is never a Sunday future hash. Typed image evidence and an
independent real verifier are required at each effect. Fresh veto and physical
identity are checked on Monday. Capacity-config emission/delivery/settings are
outside these three operations and require their own authority/program.

The local ledger records an attempt, never an operational COMPLETE/GO receipt.
It is an exclusive, pre-created file in an already elected directory. Identified
operations are consumed before gates, including refused and uncertain calls.
The fixture tests exercise only this core and the copied pure image gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import errno
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
from typing import Callable

EPOCH = "R2D2-V2-SHADOW-2026-10-12"
DAY = "2026-10-12"
PREVIOUS = "2026-10-09"
UPSTREAM = ("prove", "collect", "commit_result", "publish_launch")
DOWNSTREAM = ("e6", "admission_manifest", "post", "reader_bound", "reader_cycle",
              "policy_read", "capture_launch", "capture_result", "capture_cleanup")
BOOTSTRAP = ("install_release", "readback", "activate")
BOOTSTRAP_PHASES = {"install_release": "install_release", "readback": "readback", "activate": "activate"}
LANES = {"UPSTREAM_P": UPSTREAM, "DOWNSTREAM_AFTER_E6": DOWNSTREAM,
         "BOOTSTRAP_MONDAY": BOOTSTRAP}
MINIMUM_DEPENDENCIES = {
    "prove": (), "collect": ("prove",), "commit_result": ("collect",),
    "publish_launch": ("commit_result",), "e6": ("commit_result", "publish_launch"),
    "admission_manifest": ("e6",), "post": ("admission_manifest",),
    "reader_bound": ("admission_manifest",),
    "reader_cycle": ("admission_manifest", "post", "reader_bound"),
    "policy_read": ("reader_cycle",), "capture_launch": ("policy_read",),
    "capture_result": ("capture_launch",), "capture_cleanup": ("capture_result",),
    "install_release": ("epoch_pre",), "readback": ("install_release",),
    "activate": ("epoch_pre", "install_release", "readback"),
}
HEX = re.compile(r"[0-9a-f]{64}\Z")
CODE = re.compile(r"[A-Z][A-Z0-9_]{0,80}\Z")
LIMIT = 1024 * 1024


class Hold(ValueError):
    pass


class ReservationFailure(Hold):
    def __init__(self, reason, key, consumed, *, durable=False, closed=False,
                 previous_terminal_status=None, previous_terminal_sha256=None, recovery_required=None):
        super().__init__(reason);self.key,self.consumed=key,consumed
        self.durable,self.closed=durable,closed
        self.previous_terminal_status=previous_terminal_status
        self.previous_terminal_sha256=previous_terminal_sha256
        self.recovery_required=(bool(consumed) and not closed) if recovery_required is None else recovery_required


def reservation_result(error,operation,*,outer=False):
    # REFUSED_CONSUMED means an exact committed terminal is already present.
    # UNCERTAIN_CONSUMED is unresolved/orphan history. Neither permits retry.
    return {"schema":"L12_OUTER_RESERVATION_CANDIDATE_V1" if outer else "L12_LOCAL_RESERVATION_CANDIDATE_V1",
            "status":("REFUSED_CONSUMED" if error.closed else "UNCERTAIN_CONSUMED") if error.consumed else "REFUSED_NOT_RESERVED",
            "code":code(error),"inner_code":None,"operation":operation,"attempt_key":error.key,"effect_calls":0,
            "reservation_durable":error.durable,"recovery_required":error.recovery_required,
            "consumption_state":"TERMINAL_DURABLE" if error.closed else "UNRESOLVED_CONSUMED" if error.consumed else "NOT_RESERVED",
            "previous_terminal_status":error.previous_terminal_status,"previous_terminal_sha256":error.previous_terminal_sha256,
            "automatic_retry":False,"operational_GO_granted":False,"physical_host_certified":False,
            "worker_cleanup":"NOT_STARTED" if outer else None,
            "original_receipt_sha256":None,"original_receipt_completed_at":None,"completed_at":iso(datetime.now(timezone.utc))}


def need(condition, code):
    if not condition:
        raise Hold(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(value):
    return type(value) is str and HEX.fullmatch(value) is not None and value not in (
        "0" * 64, "0f" + "0" * 62)


def instant(value):
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00") if type(value) is str and value.endswith("Z") else value
        need(isinstance(parsed, datetime) and parsed.utcoffset() is not None, "CLOCK_UNBOUND")
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, AttributeError):
        raise Hold("CLOCK_UNBOUND") from None


def iso(value):
    return instant(value).isoformat().replace("+00:00", "Z")


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        need(type(raw) is bytes and 0 < len(raw) <= LIMIT, "DOCUMENT_BYTES_INVALID")
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Hold("JSON_NONFINITE")))
        need(type(value) is dict and canonical(value) == raw, "DOCUMENT_NOT_CANONICAL")
        return value
    except (UnicodeError, json.JSONDecodeError):
        raise Hold("DOCUMENT_INVALID") from None


def accepted(callback, *args):
    need(callable(callback), "REAL_ADAPTER_UNAVAILABLE")
    need(callback(*args) is None, "ADAPTER_DID_NOT_ATTEST")


def code(error):
    return str(error) if isinstance(error, Hold) and CODE.fullmatch(str(error)) else "ADAPTER_OR_IO_FAILURE"


def context(plan):
    return tuple(plan[name] for name in ("epoch", "session", "previous_session", "track"))


def identify_plan(raw):
    """Only enough canonical input to identify a stable logical attempt key.

    Full authority/time/pin/dependency checks happen after the durable claim.
    Unparseable input or a different epoch/day is unidentifiable and cannot
    authorize any invocation or retry; no effect is possible from that input.
    """
    q = strict(raw)
    need(q.get("epoch") == EPOCH and q.get("session") == DAY
         and q.get("previous_session") == PREVIOUS
         and q.get("track") == ("BOOTSTRAP" if q.get("lane") == "BOOTSTRAP_MONDAY" else "P"), "PLAN_CONTEXT_INVALID")
    tasks = q.get("tasks")
    need(type(tasks) is list and 0 < len(tasks) <= 16 and all(type(t) is dict and
         t.get("operation") in UPSTREAM + DOWNSTREAM + BOOTSTRAP for t in tasks), "PLAN_NOT_IDENTIFIABLE")
    need(len({t["operation"] for t in tasks}) == len(tasks), "PLAN_NOT_IDENTIFIABLE")
    return q


def validate_plan(raw):
    q = strict(raw)
    keys = {"schema", "lane", "epoch", "session", "previous_session", "track", "prepared_at",
            "owner_deadline", "authority_sha256", "runtime_sha256", "veto_authority_sha256",
            "initial_receipts", "tasks"}
    need(set(q) == keys and q["schema"] == "L12_FINITE_BATCH_REQUEST_CANDIDATE_V1", "PLAN_ABI_INVALID")
    need(q["lane"] in LANES and q["epoch"] == EPOCH and q["session"] == DAY
         and q["previous_session"] == PREVIOUS
         and q["track"] == ("BOOTSTRAP" if q["lane"] == "BOOTSTRAP_MONDAY" else "P"), "PLAN_CONTEXT_INVALID")
    need(all(pin(q[name]) for name in ("authority_sha256", "runtime_sha256", "veto_authority_sha256")),
         "PLAN_PIN_INVALID")
    need(instant(q["prepared_at"]) < instant(q["owner_deadline"]), "PLAN_AUTHORITY_WINDOW_INVALID")
    initial = q["initial_receipts"]
    need(type(initial) is dict and all(type(k) is str and re.fullmatch(r"[a-z][a-z0-9_]{0,48}", k)
         and pin(v) for k, v in initial.items()), "INITIAL_RECEIPTS_INVALID")
    tasks = q["tasks"]
    need(type(tasks) is list and 0 < len(tasks) <= 16, "PLAN_NOT_FINITE")
    seen = set(initial)
    order = []
    for task in tasks:
        task_keys = {"operation", "not_before", "not_after", "budget_seconds", "requires"}
        if q["lane"] == "BOOTSTRAP_MONDAY":
            task_keys |= {"image_go_sha256", "image_proposal_sha256"}
        need(type(task) is dict and set(task) == task_keys,
             "TASK_ABI_INVALID")
        op = task["operation"]
        need(op in LANES[q["lane"]] and op not in order and op not in initial, "TASK_OPERATION_INVALID")
        start, end = instant(task["not_before"]), instant(task["not_after"])
        budget = task["budget_seconds"]
        need(type(budget) in (int, float) and math.isfinite(budget) and 0 < budget <= 1200
             and start < end and budget <= (end - start).total_seconds(), "TASK_BUDGET_INVALID")
        need(instant(q["owner_deadline"]) < start, "OWNER_DEADLINE_AFTER_EFFECT_WINDOW")
        if q["lane"] == "BOOTSTRAP_MONDAY":
            need(all(pin(task[key]) for key in ("image_go_sha256", "image_proposal_sha256")), "IMAGE_GO_PIN_INVALID")
            need(instant("2026-10-12T04:00:00Z") <= start < end < instant("2026-10-13T00:00:00Z")
                 and (end-start).total_seconds() <= 900, "BOOTSTRAP_MONDAY_WINDOW_INVALID")
        required = task["requires"]
        need(type(required) is list and len(required) == len(set(required))
             and all(type(role) is str and role in seen for role in required)
             and set(MINIMUM_DEPENDENCIES[op]) <= set(required), "TASK_DEPENDENCIES_INVALID")
        order.append(op)
        seen.add(op)
    need(order == [op for op in LANES[q["lane"]] if op in order], "TASK_ORDER_INVALID")
    if q["lane"] == "UPSTREAM_P":
        need(tuple(order) == UPSTREAM, "P_CHAIN_INCOMPLETE")
    elif q["lane"] == "DOWNSTREAM_AFTER_E6":
        need({"commit_result", "publish_launch"} <= set(initial) and order[0] == "e6",
             "E6_PREBIND_RECEIPTS_ABSENT")
    else:
        need(tuple(order) == BOOTSTRAP and "epoch_pre" in initial, "BOOTSTRAP_CHAIN_INCOMPLETE")
        need(instant(q["owner_deadline"]) <= instant("2026-10-12T00:45:00Z"), "BOOTSTRAP_OWNER_DEADLINE_INVALID")
    return q


@dataclass(frozen=True)
class Bundle:
    request: bytes
    bound: bytes
    # Tuple instead of a caller-owned mutable mapping. Each raw original is bytes.
    documents: tuple[tuple[str, bytes], ...]

    def validate(self, plan):
        need(type(self.documents) is tuple and all(type(item) is tuple and len(item) == 2
             and type(item[0]) is str and type(item[1]) is bytes and 0 < len(item[1]) <= LIMIT
             for item in self.documents), "BOUND_DOCUMENT_SET_INVALID")
        docs = dict(self.documents)
        need(len(docs) == len(self.documents) and set(docs) == {"owner", "authority", "runtime"},
             "BOUND_DOCUMENT_SET_INVALID")
        b = strict(self.bound)
        need(set(b) == {"schema", "request_sha256", "documents_sha256", "bound_at"}
             and b["schema"] == "L12_BOUND_CANDIDATE_V1" and b["request_sha256"] == sha(self.request)
             and b["documents_sha256"] == {k: sha(v) for k, v in docs.items()}, "BOUND_BYTES_CHANGED")
        need(sha(docs["authority"]) == plan["authority_sha256"]
             and sha(docs["runtime"]) == plan["runtime_sha256"], "BOUND_PIN_CHANGED")
        owner = strict(docs["owner"])
        need(set(owner) == {"schema", "answer", "channel", "request_sha256", "question_sha256",
                            "question_published_at", "signed_at"}
             and owner["schema"] == "L12_OWNER_RECORD_CANDIDATE_V1" and owner["answer"] == "Assino"
             and owner["channel"] == "REGISTRO_PELA_FABLE" and owner["request_sha256"] == sha(self.request)
             and pin(owner["question_sha256"]), "OWNER_ORIGINAL_INVALID")
        prepared = instant(plan["prepared_at"])
        signed = instant(owner["signed_at"])
        need(prepared <= instant(owner["question_published_at"]) <= signed <= instant(plan["owner_deadline"])
             and signed <= instant(b["bound_at"]), "OWNER_CHRONOLOGY_INVALID")
        return signed, instant(b["bound_at"])


@dataclass(frozen=True)
class Receipt:
    """Original bytes + adapter's normalized ABI view, never a receipt issued here.

    receipt_verifier must reconcile every view field to these exact original
    bytes and their real authority/source/context. No default verifier exists.
    """
    raw: bytes
    role: str
    context: tuple[str, str, str, str]
    status: str
    completed_at: datetime


@dataclass(frozen=True)
class VetoView:
    raw: bytes
    authority_sha256: str
    verdict: str
    observed_at: datetime
    valid_until: datetime


@dataclass(frozen=True)
class Invocation:
    operation: str
    context: tuple[str, str, str, str]
    request_sha256: str
    bound_sha256: str
    deadline_utc: datetime
    deadline_monotonic: float
    original_receipts: tuple[Receipt, ...]


@dataclass(frozen=True)
class ImageGo:
    """Exact existing-image JSON GO/proposal plus documentary originals.

    This type is only a transport envelope. The mandatory independent callback
    must verify the actual Act A/B, Fable GO and DUDU OWNER_GO originals, source
    pins, release/BOOT evidence, K11 FULL PRE and Monday POST semantics. No
    production verifier, normalizer, owner answer or GO issuer is supplied.
    """
    go_raw: bytes
    proposal_raw: bytes
    documents: tuple[tuple[str, bytes], ...]


def image_json(raw):
    """Image assembler canonical JSON uses UTF-8 (not the local ledger ABI)."""
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "IMAGE_JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        need(type(raw) is bytes and 0 < len(raw) <= LIMIT, "IMAGE_DOCUMENT_BYTES_INVALID")
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Hold("IMAGE_JSON_NONFINITE")))
        need(type(value) is dict and image_canonical(value) == raw, "IMAGE_DOCUMENT_NOT_CANONICAL")
        return value
    except (UnicodeError, json.JSONDecodeError):
        raise Hold("IMAGE_DOCUMENT_INVALID") from None


def image_canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class Services:
    # All authority/runtime/receipt callbacks are supplied externally and pinned
    # in the independently reviewed operational package. None is provided here.
    authority: Callable | None = None
    identity: Callable | None = None
    veto_read: Callable | None = None
    veto_verify: Callable | None = None
    receipt_read: Callable | None = None
    receipt_verify: Callable | None = None
    operation_gate: Callable | None = None
    capacity_path: Callable | None = None
    image_go_read: Callable | None = None
    image_go_verify: Callable | None = None
    execute: Callable | None = None


def identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), info.st_nlink)


def directory_identity(info):
    # Directory nlink may change when an entry is created (including files on
    # APFS); pin only dev/inode/uid/gid/mode, as the original F2 directory ABI.
    return identity(info)[:5]


def measure_local_ledger(root):
    """Read-only identity helper. This is not a host/runtime measurement or prepare."""
    path = Path(root)
    need(path.is_absolute() and str(path) == root and ".." not in path.parts, "LEDGER_ROOT_INVALID")
    rows = [("/", directory_identity(os.lstat("/")))]
    for index in range(2, len(path.parts) + 1):
        name = str(Path(*path.parts[:index]))
        info = os.lstat(name)
        need(stat.S_ISDIR(info.st_mode), "LEDGER_ANCESTOR_NOT_DIRECTORY")
        rows.append((name, directory_identity(info)))
    ledger = os.lstat(path / "attempts.ledger")
    need(stat.S_ISREG(ledger.st_mode) and ledger.st_uid == os.geteuid()
         and stat.S_IMODE(ledger.st_mode) == 0o600 and ledger.st_nlink == 1, "LEDGER_FILE_POLICY")
    return tuple(rows), identity(ledger)


class DurableLedger:
    """Pinned held descriptors, exclusive consumed marker and append-only hash chain.

    No mkdir/ledger installer is provided. The root and ledger must already
    exist and be independently elected. No operation erases/resets an attempt.
    Same-disk commit proofs detect a retained marker against truncated ledger;
    rollback of the entire elected disk remains the explicit selected limit.
    A current process checks held names/inodes before every append.
    """
    def __init__(self, root, pins, *, lock_budget_seconds=.5):
        need(type(lock_budget_seconds) in (int,float) and math.isfinite(lock_budget_seconds)
             and 0<lock_budget_seconds<=1,"LEDGER_LOCK_BUDGET_INVALID")
        self.lock_budget_seconds=lock_budget_seconds
        self.root, self.pins = root, pins
        self.fds, self.lfd = [], None
        try:
            path = Path(root)
            expected = ["/"] + [str(Path(*path.parts[:i])) for i in range(2, len(path.parts) + 1)]
            need(path.is_absolute() and str(path) == root and ".." not in path.parts
                 and [name for name, _ in pins[0]] == expected, "LEDGER_ROOT_INVALID")
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            self.fds.append(fd)
            for index, (name, row) in enumerate(pins[0]):
                if index:
                    self.fds.append(os.open(Path(name).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                            dir_fd=self.fds[-1]))
                need(directory_identity(os.fstat(self.fds[-1])) == row, "LEDGER_DIRECTORY_CHANGED")
            need(pins[0][-1][0] == root and pins[0][-1][1][2] == os.geteuid()
                 and pins[0][-1][1][4] == 0o700, "LEDGER_ROOT_NOT_PRIVATE")
            self.lfd = os.open("attempts.ledger", os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK,
                               dir_fd=self.fds[-1])
            info = os.fstat(self.lfd)
            need(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1, "LEDGER_FILE_POLICY")
            self.check()
        except BaseException:
            self.close()
            raise

    def close(self):
        for fd in self.fds + ([self.lfd] if self.lfd is not None else []):
            os.close(fd)
        self.fds, self.lfd = [], None

    def check(self):
        for fd, (name, row) in zip(self.fds, self.pins[0]):
            need(directory_identity(os.fstat(fd)) == row and directory_identity(os.lstat(name)) == row,
                 "LEDGER_DIRECTORY_CHANGED")
        need(identity(os.fstat(self.lfd)) == self.pins[1]
             and identity(os.stat("attempts.ledger", dir_fd=self.fds[-1], follow_symlinks=False)) == self.pins[1],
             "LEDGER_FILE_CHANGED")

    @contextmanager
    def _lock(self):
        # A separate file description is required for each lock: inherited
        # descriptors share flock ownership across fork, defeating exclusion.
        fd=os.open("attempts.ledger",os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.fds[-1])
        acquired=False
        try:
            self.check();need(identity(os.fstat(fd))==self.pins[1],"LEDGER_FILE_CHANGED")
            deadline=time.monotonic()+self.lock_budget_seconds
            while True:
                try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);acquired=True;break
                except OSError as error:
                    if error.errno not in (errno.EAGAIN,errno.EACCES):raise
                    need(time.monotonic()<deadline,"LEDGER_LOCK_DEADLINE_NO_RESERVATION")
                    time.sleep(min(.005,max(.0001,deadline-time.monotonic())))
            self.check();yield
        finally:
            if acquired:fcntl.flock(fd,fcntl.LOCK_UN)
            os.close(fd)

    def _file(self,name):
        fd=None
        try:
            named=os.stat(name,dir_fd=self.fds[-1],follow_symlinks=False)
            need(stat.S_ISREG(named.st_mode) and named.st_uid==os.geteuid()
                 and stat.S_IMODE(named.st_mode)==0o600 and named.st_nlink==1,"LEDGER_PROOF_FILE_POLICY")
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=self.fds[-1])
            need(identity(os.fstat(fd))==identity(named),"LEDGER_PROOF_CHANGED")
            raw=os.read(fd,4097);need(0<len(raw)<=4096,"LEDGER_PROOF_INCOMPLETE")
            value=strict(raw)
            need(identity(os.fstat(fd))==identity(os.stat(name,dir_fd=self.fds[-1],follow_symlinks=False)),"LEDGER_PROOF_CHANGED")
            self.check();return value,sha(raw)
        finally:
            if fd is not None:os.close(fd)

    def _create(self,name,value):
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=self.fds[-1])
        try:
            raw=canonical(value);written=0
            while written<len(raw):
                size=os.write(fd,raw[written:]);need(size>0,"LEDGER_PROOF_WRITE_UNCERTAIN");written+=size
            os.fsync(fd)
        finally:os.close(fd)
        os.fsync(self.fds[-1]);self.check()

    def _rows(self, pending_marker=None):
        self.check();os.lseek(self.lfd,0,os.SEEK_SET);raw=os.read(self.lfd,LIMIT+1)
        need(len(raw)<=LIMIT and (not raw or raw.endswith(b"\n")),"LEDGER_PARTIAL_OR_FULL")
        rows,previous=[],"";claims={};terminals={}
        for number,line in enumerate(raw.splitlines(),1):
            row=strict(line)
            need(set(row)=={"schema","sequence","previous_sha256","attempt_key","kind","data"}
                 and row["schema"]=="L12_LOCAL_ATTEMPT_LEDGER_CANDIDATE_V1"
                 and row["sequence"]==number and row["previous_sha256"]==previous
                 and pin(row["attempt_key"]) and row["kind"] in ("CLAIM","TERMINAL"),"LEDGER_CHAIN_INVALID")
            key=row["attempt_key"]
            if row["kind"]=="CLAIM":need(key not in claims,"LEDGER_DUPLICATE_CLAIM");claims[key]=row
            else:need(key in claims and key not in terminals,"LEDGER_TERMINAL_CHAIN_INVALID");terminals[key]=row
            rows.append(row);previous=sha(line)
        names=os.listdir(self.fds[-1]);markers={n[8:] for n in names if n.startswith("consume-")}
        commits={n[9:] for n in names if n.startswith("reserved-")}
        terminal_commits={n[9:] for n in names if n.startswith("terminal-")}
        need(all(pin(k) for k in markers|commits|terminal_commits),"LEDGER_PROOF_NAME_INVALID")
        need(set(claims)<=markers and commits<=set(claims) and terminal_commits<=set(terminals),"LEDGER_COMMITTED_HISTORY_TRUNCATED")
        for key in markers:
            marker,digest=self._file("consume-"+key)
            need(set(marker)=={"schema","attempt_key","scope","request_sha256","bound_sha256","at","sequence","previous_sha256"}
                 and marker["schema"]=="L12_CONSUMED_SCOPE_CANDIDATE_V2" and marker["attempt_key"]==key
                 and type(marker["scope"]) is list and sha(canonical(marker["scope"]))==key
                 and pin(marker["request_sha256"]) and pin(marker["bound_sha256"])
                 and type(marker["sequence"]) is int and marker["sequence"]>0
                 and (marker["previous_sha256"]=="" or pin(marker["previous_sha256"]))
                 and instant(marker["at"])<=datetime.now(timezone.utc),"LEDGER_MARKER_INVALID")
            if key in claims:
                row=claims[key];data=row["data"]
                need(row["sequence"]==marker["sequence"] and row["previous_sha256"]==marker["previous_sha256"]
                     and type(data) is dict and data.get("marker_sha256")==digest
                     and data.get("request_sha256")==marker["request_sha256"] and data.get("bound_sha256")==marker["bound_sha256"]
                     and data.get("at")==marker["at"],"LEDGER_MARKER_CLAIM_CHANGED")
            else:
                need(marker["sequence"]==len(rows)+1 and marker["previous_sha256"]==previous,"LEDGER_ORPHAN_ANCHOR_CHANGED")
            if key in commits:
                proof,_=self._file("reserved-"+key)
                need(proof=={"schema":"L12_CLAIM_COMMIT_CANDIDATE_V1","attempt_key":key,
                     "claim_sha256":sha(canonical(claims[key])),"marker_sha256":digest},"LEDGER_CLAIM_COMMIT_CHANGED")
        for key in terminal_commits:
            proof,_=self._file("terminal-"+key)
            need((set(proof)=={"schema","attempt_key","terminal_sha256","committed_status"}
                  and proof["schema"]=="L12_TERMINAL_COMMIT_CANDIDATE_V1"
                  or set(proof)=={"schema","attempt_key","terminal_sha256","committed_status","recovered"}
                  and proof["schema"]=="L12_TERMINAL_COMMIT_CANDIDATE_V2" and type(proof["recovered"]) is bool)
                 and proof["attempt_key"]==key
                 and proof["terminal_sha256"]==sha(canonical(terminals[key]))
                 and proof["committed_status"] in (terminals[key]["data"]["status"],"UNCERTAIN_CONSUMED"),"LEDGER_TERMINAL_COMMIT_CHANGED")
        return rows,previous

    def _append(self,rows,previous,attempt_key,kind,data):
        row={"schema":"L12_LOCAL_ATTEMPT_LEDGER_CANDIDATE_V1","sequence":len(rows)+1,
             "previous_sha256":previous,"attempt_key":attempt_key,"kind":kind,"data":data}
        raw=canonical(row)+b"\n";self.check();written=0
        while written<len(raw):
            size=os.write(self.lfd,raw[written:]);need(size>0,"LEDGER_WRITE_UNCERTAIN");written+=size
        os.fsync(self.lfd);os.fsync(self.fds[-1]);return row

    def _commit_claim(self,key,claim,marker_sha):
        self._create("reserved-"+key,{"schema":"L12_CLAIM_COMMIT_CANDIDATE_V1","attempt_key":key,
                     "claim_sha256":sha(canonical(claim)),"marker_sha256":marker_sha})

    def _commit_terminal(self,key,terminal,status,*,recovered=False):
        self._create("terminal-"+key,{"schema":"L12_TERMINAL_COMMIT_CANDIDATE_V2","attempt_key":key,
                     "terminal_sha256":sha(canonical(terminal)),"committed_status":status,"recovered":recovered})

    def _recover(self):
        # Called only under the bounded exclusive lock. No effects run here.
        # A marker without a commit proof can only precede a first effect;
        # retained commit against absent/changed chain is rejected by _rows.
        rows,previous=self._rows();names=set(os.listdir(self.fds[-1]))
        claims={r["attempt_key"]:r for r in rows if r["kind"]=="CLAIM"}
        terminals={r["attempt_key"]:r for r in rows if r["kind"]=="TERMINAL"}
        markers={n[8:] for n in names if n.startswith("consume-")}
        need(len(markers-set(claims))<=1,"LEDGER_ORPHANS_AMBIGUOUS")
        for key in sorted(markers):
            marker,marker_sha=self._file("consume-"+key);adopt=False
            if key not in claims:
                claim=self._append(rows,previous,key,"CLAIM",{"at":marker["at"],"request_sha256":marker["request_sha256"],
                    "bound_sha256":marker["bound_sha256"],"automatic_retry":False,"marker_sha256":marker_sha})
                rows.append(claim);previous=sha(canonical(claim));claims[key]=claim;adopt=True
            if "reserved-"+key not in names:
                self._commit_claim(key,claims[key],marker_sha);adopt=True
            if adopt and key not in terminals:
                result={"status":"UNCERTAIN_CONSUMED","code":"ORPHAN_MARKER","inner_code":None,
                        "operation":marker["scope"][-1],"attempt_key":key,"effect_calls":None,
                        "original_receipt_sha256":None,"original_receipt_completed_at":None,
                        "automatic_retry":False,"operational_GO_granted":False,"physical_host_certified":False,
                        "completed_at":iso(datetime.now(timezone.utc))}
                terminal=self._append(rows,previous,key,"TERMINAL",result)
                rows.append(terminal);previous=sha(canonical(terminal));terminals[key]=terminal
            if key in terminals and "terminal-"+key not in names:
                # A crash before the parent committed a terminal cannot certify
                # a dependency, even if its lost result had looked complete.
                self._commit_terminal(key,terminals[key],"UNCERTAIN_CONSUMED",recovered=True)
        return self._rows()

    def claim(self,scope,request_hash,bound_hash,now):
        key=sha(canonical(list(scope)));consumed=False
        try:
            with self._lock():
                rows,previous=self._recover()
                if any(r["attempt_key"]==key for r in rows):
                    terminals=[r for r in rows if r["attempt_key"]==key and r["kind"]=="TERMINAL"]
                    previous=terminals[0] if terminals else None
                    proof=self._file("terminal-"+key)[0] if previous else None
                    data=previous["data"] if previous else None
                    exact=previous is not None and proof["committed_status"]==data["status"] and not proof.get("recovered",False) and data.get("code")!="ORPHAN_MARKER"
                    raise ReservationFailure("ATTEMPT_ALREADY_CONSUMED",key,True,durable=True,closed=exact,
                        previous_terminal_status=data.get("status") if data else None,
                        previous_terminal_sha256=sha(canonical(previous)) if previous else None)
                at=datetime.now(timezone.utc) # Real UTC native clock, no adapter.
                marker={"schema":"L12_CONSUMED_SCOPE_CANDIDATE_V2","attempt_key":key,"scope":list(scope),
                        "request_sha256":request_hash,"bound_sha256":bound_hash,"at":iso(at),
                        "sequence":len(rows)+1,"previous_sha256":previous}
                # Once exclusive marker creation starts, any uncertain error
                # remains consumed. No marker is written on a busy-lock refusal.
                consumed=True
                self._create("consume-"+key,marker)
                claim=self._append(rows,previous,key,"CLAIM",{"at":marker["at"],"request_sha256":request_hash,
                            "bound_sha256":bound_hash,"automatic_retry":False,"marker_sha256":sha(canonical(marker))})
                self._commit_claim(key,claim,sha(canonical(marker)))
            return key
        except ReservationFailure:raise
        except BaseException as error:
            # A retained same-key marker still consumes if chain parsing failed.
            # This read never repairs history or grants another logical slot.
            try:os.stat("consume-"+key,dir_fd=self.fds[-1],follow_symlinks=False);consumed=True
            except FileNotFoundError:pass
            except BaseException:consumed=True
            reason=code(error)
            raise ReservationFailure(reason,key,consumed,recovery_required=reason!="LEDGER_LOCK_DEADLINE_NO_RESERVATION") from None

    def check_reserved(self,scope,request_hash,bound_hash,key):
        need(key==sha(canonical(list(scope))),"RESERVATION_SCOPE_INVALID")
        with self._lock():
            rows,_=self._rows();claims=[r for r in rows if r["attempt_key"]==key and r["kind"]=="CLAIM"]
            need(len(claims)==1 and not any(r["attempt_key"]==key and r["kind"]=="TERMINAL" for r in rows),"RESERVATION_NOT_PENDING")
            need(claims[0]["data"]["request_sha256"]==request_hash and claims[0]["data"]["bound_sha256"]==bound_hash,"RESERVATION_PIN_CHANGED")
            need("reserved-"+key in os.listdir(self.fds[-1]),"RESERVATION_COMMIT_MISSING")
            self._file("reserved-"+key)

    def finish(self,key,result):
        with self._lock():
            rows,previous=self._recover()
            need(sum(r["attempt_key"]==key and r["kind"]=="CLAIM" for r in rows)==1
                 and not any(r["attempt_key"]==key and r["kind"]=="TERMINAL" for r in rows),"ATTEMPT_TERMINAL_INVALID")
            terminal=self._append(rows,previous,key,"TERMINAL",result)
            self._commit_terminal(key,terminal,result["status"])

    def dependency(self,scope,request_hash,bound_hash,receipt):
        key=sha(canonical(list(scope)))
        with self._lock():
            rows,_=self._rows()
            claims=[r for r in rows if r["attempt_key"]==key and r["kind"]=="CLAIM"]
            terminals=[r for r in rows if r["attempt_key"]==key and r["kind"]=="TERMINAL"]
            need(len(claims)==len(terminals)==1,"DEPENDENCY_TERMINAL_MISSING")
            need(claims[0]["data"]["request_sha256"]==request_hash and claims[0]["data"]["bound_sha256"]==bound_hash,"DEPENDENCY_OTHER_BOUND")
            data=terminals[0]["data"]
            need(data["status"]=="ORIGINAL_COMPLETE_OBSERVED_CANDIDATE" and data.get("original_receipt_sha256")==sha(receipt.raw)
                 and data.get("original_receipt_completed_at")==iso(receipt.completed_at),"DEPENDENCY_TERMINAL_NOT_COMPLETE_MATCH")
            proof,_=self._file("terminal-"+key)
            need(proof["committed_status"]=="ORIGINAL_COMPLETE_OBSERVED_CANDIDATE","DEPENDENCY_TERMINAL_NOT_DURABLE_COMPLETE")


class FiniteBatch:
    def __init__(self, bundle, ledger, services, *, clock=None, monotonic=None):
        need(isinstance(bundle, Bundle) and isinstance(services, Services), "BATCH_INPUT_INVALID")
        self.bundle, self.q = bundle, identify_plan(bundle.request)
        self.ledger, self.services = ledger, services
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.fingerprint = sha(bundle.request), sha(bundle.bound), tuple((k, sha(v)) for k, v in bundle.documents)

    def unchanged(self):
        need(self.fingerprint == (sha(self.bundle.request), sha(self.bundle.bound),
                                  tuple((k, sha(v)) for k, v in self.bundle.documents)), "BOUND_BYTES_CHANGED")
        need(validate_plan(self.bundle.request) == self.q, "PLAN_CHANGED")

    def receipt(self, role, now, *, before_request=False):
        s, q = self.services, self.q
        need(callable(s.receipt_read), "REAL_RECEIPT_READER_UNAVAILABLE")
        item = s.receipt_read(role, context(q))
        need(isinstance(item, Receipt) and type(item.raw) is bytes and 0 < len(item.raw) <= LIMIT
             and item.role == role and item.context == context(q) and item.status == "COMPLETE", "REAL_RECEIPT_INCOMPLETE")
        accepted(s.receipt_verify, item, q, role, now)
        completion = instant(item.completed_at)
        need(completion <= now, "REAL_RECEIPT_FROM_FUTURE")
        if role in q["initial_receipts"]:
            need(sha(item.raw) == q["initial_receipts"][role], "REAL_RECEIPT_PIN_CHANGED")
        if before_request:
            need(completion <= instant(q["prepared_at"]), "E6_RECEIPT_NOT_COMPLETE_BEFORE_REQUEST")
        elif role not in q["initial_receipts"]:
            need(role in [t["operation"] for t in q["tasks"]],"DEPENDENCY_NOT_IN_SIGNED_PLAN")
            _,bound_at=self.bundle.validate(q)
            need(completion>=bound_at,"DEPENDENCY_BEFORE_BOUND")
            self.ledger.dependency(context(q)+(role,),sha(self.bundle.request),sha(self.bundle.bound),item)
        return item

    def timing_guard(self, op, now, started, mark, deadline):
        wall_elapsed, mono_elapsed = (now - started).total_seconds(), self.monotonic() - mark
        need(mono_elapsed >= 0 and abs(wall_elapsed - mono_elapsed) <= 2, "CLOCK_DISCONTINUITY")
        need(now < deadline and self.monotonic() < mark + op["budget_seconds"], "OPERATION_DEADLINE")
        need(instant(op["not_before"]) <= now < instant(op["not_after"]), "OPERATION_WINDOW_CLOSED")

    def bootstrap_go(self, task, dependencies, now):
        if self.q["lane"] != "BOOTSTRAP_MONDAY":
            return None
        need(callable(self.services.image_go_read), "REAL_IMAGE_GO_READER_UNAVAILABLE")
        evidence = self.services.image_go_read(self.q, task, now)
        need(isinstance(evidence, ImageGo), "REAL_IMAGE_GO_TYPED_EVIDENCE_REQUIRED")
        need(sha(evidence.go_raw) == task["image_go_sha256"]
             and sha(evidence.proposal_raw) == task["image_proposal_sha256"], "IMAGE_GO_OR_PROPOSAL_PIN_CHANGED")
        go, proposed = image_json(evidence.go_raw), image_json(evidence.proposal_raw)
        required = {"decision", "epoch", "first_session", "day", "phase", "proposal_sha", "signed_order_sha",
                    "template_sha", "mode", "not_before", "not_after", "automatic_retry", "authority_receipts"}
        need(set(go) == required and go["decision"] == "GO" and go["mode"] == "INDIVIDUAL"
             and go["epoch"] == EPOCH and go["first_session"] == go["day"] == DAY
             and go["phase"] == BOOTSTRAP_PHASES[task["operation"]] and go["automatic_retry"] is False,
             "IMAGE_GO_SCOPE_INVALID")
        need(proposed.get("status") == "BOUND_FOR_REVIEW_ONLY" and proposed.get("execution_authorized") is False
             and proposed.get("missing_bindings") == [] and type(proposed.get("proposal")) is dict,
             "IMAGE_PROPOSAL_NOT_BOUND")
        p = proposed["proposal"]
        need(p.get("phase") == go["phase"] and type(p.get("identity")) is dict
             and p["identity"].get("epoch") == EPOCH and p["identity"].get("first_session") == DAY
             and type(p.get("daily")) is dict and p["daily"].get("day") == DAY,
             "IMAGE_PROPOSAL_SCOPE_INVALID")
        need(go["proposal_sha"] == proposed.get("proposal_sha") == sha(image_canonical(p)), "IMAGE_PROPOSAL_HASH_INVALID")
        bindings = p.get("bindings")
        need(type(bindings) is dict and bindings and all(pin(value) for value in bindings.values())
             and go["signed_order_sha"] == bindings.get("signed_epoch_order_sha")
             and go["template_sha"] == bindings.get("template_sha"), "IMAGE_BINDINGS_UNBOUND")
        need(instant(go["not_before"]) == instant(task["not_before"])
             and instant(go["not_after"]) == instant(task["not_after"])
             and instant(go["not_before"]) <= now < instant(go["not_after"]), "IMAGE_GO_WINDOW_INVALID")
        receipts = go["authority_receipts"]
        window = receipts.get("phase_window") if type(receipts) is dict else None
        need(type(window) is dict and set(window) == {"epoch", "day", "phase", "not_before", "not_after"}
             and window["epoch"] == EPOCH and window["day"] == DAY and window["phase"] == go["phase"]
             and instant(window["not_before"]) == instant(go["not_before"])
             and instant(window["not_after"]) == instant(go["not_after"])
             and sha(image_canonical(window)) == bindings.get("phase_window_sha"), "IMAGE_PHASE_WINDOW_UNBOUND")
        docs = evidence.documents
        need(type(docs) is tuple and all(type(item) is tuple and len(item) == 2 and type(item[0]) is str
             and type(item[1]) is bytes and 0 < len(item[1]) <= LIMIT for item in docs), "IMAGE_DOCUMENT_ORIGINALS_INVALID")
        labels = [item[0] for item in docs]
        expected = {"CODEX", "FABLE", "DUDU", "ACT_B", "B_CODEX", "B_FABLE", "B_DUDU", "TEMPLATE", "GO:" + go["phase"]}
        if task["operation"] in ("install_release", "activate"):
            expected.add("OWNER_GO:" + go["phase"])
        need(len(labels) == len(set(labels)) and expected <= set(labels), "IMAGE_OWNER_OR_AUTHORITY_ORIGINALS_MISSING")
        # A tuple of documentary bytes is not a signature. This callback must
        # independently reconcile real source ABI/pins, Act A/B, owner GO and
        # the actual K11 FULL PRE/Monday POST receipts. No default accepts it.
        accepted(self.services.image_go_verify, evidence, self.bundle, self.q, task, dependencies, now)
        return sha(evidence.go_raw), sha(evidence.proposal_raw), tuple((label, sha(raw)) for label, raw in docs)

    def runtime_guard(self, op, now, started, mark, deadline):
        self.unchanged()
        self.ledger.check()
        self.timing_guard(op, now, started, mark, deadline)
        accepted(self.services.authority, self.bundle, self.q, op, now)
        accepted(self.services.identity, self.bundle, self.q, op, now)

    def reserve(self, operation):
        matches = [task for task in self.q["tasks"] if task["operation"] == operation]
        need(len(matches) == 1, "OPERATION_NOT_IN_FINITE_PLAN")
        # A real invocation with identifiable logical scope consumes before any
        # authority/window/effect gate, including refusals and missing adapters.
        # No invented timestamp if the clock adapter itself is unavailable.
        key = self.ledger.claim(context(self.q) + (operation,), sha(self.bundle.request), sha(self.bundle.bound), None)
        return key

    def run(self, operation):
        """Unbounded dispatch is disabled; reservation failures return data."""
        try:key=self.reserve(operation)
        except ReservationFailure as error:
            return reservation_result(error,operation)
        result={"schema":"L12_LOCAL_ATTEMPT_CANDIDATE_V1","status":"REFUSED_CONSUMED","code":"OUTER_LIMITER_REQUIRED",
                "inner_code":None,"operation":operation,"attempt_key":key,"effect_calls":0,
                "original_receipt_sha256":None,"original_receipt_completed_at":None,"automatic_retry":False,
                "operational_GO_granted":False,"physical_host_certified":False,"completed_at":iso(datetime.now(timezone.utc))}
        try:self.ledger.finish(key,result)
        except BaseException:
            result["inner_code"]=result["code"]
            result["status"],result["code"]="UNCERTAIN_CONSUMED","TERMINAL_LEDGER_UNCERTAIN"
        return result

    def run_reserved(self, operation, key, *, terminal=False):
        matches = [task for task in self.q["tasks"] if task["operation"] == operation]
        need(len(matches) == 1, "OPERATION_NOT_IN_FINITE_PLAN")
        task = matches[0]
        result = {"schema": "L12_LOCAL_ATTEMPT_CANDIDATE_V1", "status": "REFUSED_CONSUMED",
                  "code": None, "inner_code":None, "operation": operation, "attempt_key": key, "effect_calls": 0,
                  "original_receipt_sha256": None, "original_receipt_completed_at":None, "automatic_retry": False,
                  "operational_GO_granted": False, "physical_host_certified": False}
        try:
            self.ledger.check_reserved(context(self.q) + (operation,), sha(self.bundle.request), sha(self.bundle.bound), key)
            started, mark = instant(self.clock()), self.monotonic()
            need(type(mark) in (int, float) and math.isfinite(mark), "MONOTONIC_CLOCK_UNBOUND")
            need(validate_plan(self.bundle.request) == self.q, "PLAN_CHANGED")
            deadline = min(instant(task["not_after"]), datetime.fromtimestamp(
                started.timestamp() + task["budget_seconds"], timezone.utc))
            signed, bound_at = self.bundle.validate(self.q)
            need(bound_at <= started and signed < instant(task["not_before"]), "BOUND_NOT_BEFORE_EFFECT")
            # Unlike an upstream future hash, these exact actual originals must
            # already be COMPLETE before the downstream REQUEST and Assino.
            for role in self.q["initial_receipts"]:
                self.receipt(role, started, before_request=True)
            dependencies = tuple(self.receipt(role, started) for role in task["requires"])
            self.runtime_guard(task, instant(self.clock()), started, mark, deadline)
            image_before = self.bootstrap_go(task, dependencies, instant(self.clock()))
            accepted(self.services.operation_gate, self.bundle, self.q, task, dependencies, instant(self.clock()))
            # Dependency evidence is fetched again, not only read at schedule/
            # install time. Pin and normalized original ABI must still agree.
            fresh = tuple(self.receipt(role, instant(self.clock())) for role in task["requires"])
            need(tuple(sha(r.raw) for r in fresh) == tuple(sha(r.raw) for r in dependencies),
                 "DEPENDENCY_CHANGED_BEFORE_EFFECT")
            self.runtime_guard(task, instant(self.clock()), started, mark, deadline)
            s = self.services
            need(callable(s.veto_read), "REAL_VETO_READER_UNAVAILABLE")
            veto = s.veto_read(self.q, task, instant(self.clock()))
            now = instant(self.clock())
            need(isinstance(veto, VetoView) and type(veto.raw) is bytes and 0 < len(veto.raw) <= LIMIT
                 and veto.authority_sha256 == self.q["veto_authority_sha256"] and veto.verdict == "ALLOW"
                 and instant(veto.observed_at) <= now < instant(veto.valid_until)
                 and (now - instant(veto.observed_at)).total_seconds() <= 5, "REAL_VETO_NOT_FRESH_ALLOW")
            accepted(s.veto_verify, veto, self.q, task, now)
            # Final authority/identity/window recheck follows veto validation;
            # no parked sleep, mutation, hidden fallback or default executor.
            self.runtime_guard(task, instant(self.clock()), started, mark, deadline)
            image_after = self.bootstrap_go(task, fresh, instant(self.clock()))
            need(image_before == image_after, "IMAGE_AUTHORITY_ORIGINALS_CHANGED_BEFORE_EFFECT")
            if operation == "reader_cycle":
                # Reconcile ready/manifest/session root after all other adapter
                # callbacks, immediately before the final pure time/pin guard.
                accepted(s.capacity_path, self.q, "BEFORE_FIRST_READER", instant(self.clock()))
            # The callbacks themselves consume time and may change inputs. This
            # last guard is pure; no callback runs between it and execute.
            self.unchanged()
            self.ledger.check()
            last = instant(self.clock())
            self.timing_guard(task, last, started, mark, deadline)
            need(instant(veto.observed_at) <= last < instant(veto.valid_until)
                 and (last - instant(veto.observed_at)).total_seconds() <= 5,
                 "REAL_VETO_NOT_FRESH_ALLOW")
            need(callable(s.execute), "REAL_EXECUTOR_UNAVAILABLE")
            invocation = Invocation(operation, context(self.q), sha(self.bundle.request), sha(self.bundle.bound),
                                    deadline, mark + task["budget_seconds"], fresh)
            result["effect_calls"] = 1
            result["status"] = "UNCERTAIN_CONSUMED"
            original = s.execute(invocation)
            now = instant(self.clock())
            self.unchanged()
            need(now < deadline and self.monotonic() < invocation.deadline_monotonic, "EFFECT_RETURNED_AFTER_DEADLINE")
            need(isinstance(original, Receipt) and type(original.raw) is bytes and 0 < len(original.raw) <= LIMIT
                 and original.role == operation and original.context == context(self.q)
                 and original.status == "COMPLETE" and started <= instant(original.completed_at) <= now,
                 "EFFECT_ORIGINAL_NOT_COMPLETE")
            accepted(s.receipt_verify, original, self.q, operation, now)
            result["original_receipt_sha256"] = sha(original.raw)
            result["original_receipt_completed_at"] = iso(original.completed_at)
            if operation == "reader_cycle":
                accepted(s.capacity_path, self.q, "AFTER_FIRST_CYCLE", now)
            self.unchanged()
            self.ledger.check()
            self.timing_guard(task, instant(self.clock()), started, mark, deadline)
            result["status"] = "ORIGINAL_COMPLETE_OBSERVED_CANDIDATE"
        except BaseException as error:
            result["code"] = code(error)
        try:
            result["completed_at"] = iso(self.clock())
        except BaseException:
            result["completed_at"] = None
        if terminal:
            try:
                self.ledger.finish(key, result)
            except BaseException:
                result["inner_code"]=result["code"]
                result["status"], result["code"] = "UNCERTAIN_CONSUMED", "TERMINAL_LEDGER_UNCERTAIN"
        return result
