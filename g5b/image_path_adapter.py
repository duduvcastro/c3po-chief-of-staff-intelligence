"""Offline candidate for the existing image writer; this module issues no authority.

The transport, current human authority/runtime gate and durable claim allocator
must be supplied by the finite-job executor. No default executor or DB fallback
exists. Pure checks may be used to reconcile copied evidence, which is not a
physical host observation. Filesystem reads below are explicit and read-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable
from zoneinfo import ZoneInfo

DAY = "2026-10-12"
EPOCH = "R2D2-V2-SHADOW-2026-10-12"
ATTEMPT_KEY = EPOCH + ":" + DAY + ":BAR_MANIFEST_PREPARE_FIRST"
WRITER_SHA = "aeda5b12d34a406b0d61e1e4696e3c535e89fa3dc680ce0d3b14bb4d60b1d387"
NY = ZoneInfo("America/New_York")
SHA = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.-]{0,19}\Z")
PLACEHOLDER = "0f" + "0" * 62
LIMIT = 65536
DB_READBACK_LIMIT = 64 * 1024 * 1024  # Finite candidate ceiling per state/journal; not image ABI.
DB_SNAPSHOT_LIMIT = 2 * DB_READBACK_LIMIT
# The writer's early ALREADY_PUBLISHED_VERIFIED receipt has no current view/GO
# originals. It is a distinct outcome and cannot satisfy this fresh publish ABI.
SUCCESS = {"PUBLISHED_VERIFIED"}


class Hold(ValueError):
    """A constant public code; input, paths and symbols never become an error."""


def need(condition, code):
    if not condition:
        raise Hold(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if type(value) is str else value
        need(isinstance(parsed, datetime) and parsed.utcoffset() is not None, "CLOCK_UNBOUND")
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, AttributeError):
        raise Hold("CLOCK_UNBOUND") from None


def strict_json(raw, *, limit=LIMIT):
    def pairs(items):
        obj = {}
        for key, value in items:
            need(key not in obj, "JSON_DUPLICATE_KEY")
            obj[key] = value
        return obj
    try:
        need(type(limit) is int and 0 < limit <= DB_READBACK_LIMIT, "JSON_LIMIT_INVALID")
        need(type(raw) is bytes and 0 < len(raw) <= limit, "JSON_BYTES_INVALID")
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Hold("JSON_NONFINITE")))
    except (UnicodeError, json.JSONDecodeError):
        raise Hold("JSON_INVALID") from None


@dataclass(frozen=True)
class JournalSnapshot:
    """Original bounded JSON array; records decoded incrementally, never truncated.

    The raw buffer and decoded UTF-8 text remain bounded and resident. This is
    record streaming, not a constant-memory DB transport. Origin, consistent
    read_with_journal and physical freshness still need the external verifier.
    """
    raw: bytes


def parse_journal(raw):
    need(type(raw) is bytes and 0 < len(raw) <= DB_READBACK_LIMIT, "JSON_BYTES_INVALID")
    return JournalSnapshot(raw)


def _journal_records(records):
    if type(records) is list:
        yield from records
        return
    need(type(records) is JournalSnapshot and type(records.raw) is bytes
         and 0 < len(records.raw) <= DB_READBACK_LIMIT, "DB_READBACK_UNAVAILABLE")
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    decoder = json.JSONDecoder(object_pairs_hook=pairs,
             parse_constant=lambda _: (_ for _ in ()).throw(Hold("JSON_NONFINITE")))
    try:
        text = records.raw.decode("utf-8")
        length, offset = len(text), 0
        def skip(position):
            while position < length and text[position] in " \t\r\n":
                position += 1
            return position
        offset = skip(offset)
        need(offset < length and text[offset] == "[", "JSON_INVALID")
        offset = skip(offset + 1)
        if offset < length and text[offset] == "]":
            need(skip(offset + 1) == length, "JSON_INVALID")
            return
        while True:
            value, offset = decoder.raw_decode(text, offset)
            need(type(value) is dict, "DB_JOURNAL_CHAIN")
            yield value
            offset = skip(offset)
            need(offset < length, "JSON_INVALID")
            if text[offset] == "]":
                need(skip(offset + 1) == length, "JSON_INVALID")
                return
            need(text[offset] == ",", "JSON_INVALID")
            offset = skip(offset + 1)
            need(offset < length and text[offset] != "]", "JSON_INVALID")
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise Hold("JSON_INVALID") from None


@dataclass(frozen=True)
class Scope:
    """Executor input pins, not an owner-response or GO schema.

    All hashes must come from exact accepted originals. session_open must come
    from the actual pinned image calendar. The executor gate verifies these
    pins, the signed order, real runtime, revocations and authority windows.
    """
    build_sha: str
    image_id: str
    document_order_sha256: str
    release_sha256: str
    package_sha256: str
    capacity_config_sha256: str
    calendar_pin_sha256: str
    runtime_authority_sha256: str
    finite_authority_sha256: str
    owner_uid: int
    manifest_directory: str
    session_open: datetime
    not_before: datetime
    not_after: datetime
    view_opens_at: datetime
    require_go_mode: str
    day: str = DAY
    epoch: str = EPOCH
    capacity_veto_mode: str = "DISPATCH_AND_DERIVATION_ONLY"
    readback_margin_seconds: float = 1.0

    def document(self):
        result = dict(self.__dict__)
        for name in ("session_open", "not_before", "not_after", "view_opens_at"):
            result[name] = instant(result[name]).isoformat()
        result["writer_sha256"] = WRITER_SHA
        return result

    @property
    def scope_sha256(self):
        # Consume an identifiable serialized invocation before interpreting its
        # timestamps. A malformed/naive supplied timestamp must not fail a time
        # parser before the stable epoch/day/operation claim is recorded.
        supplied = dict(self.__dict__)
        for key, value in tuple(supplied.items()):
            if isinstance(value, datetime):
                supplied[key] = value.isoformat()
        supplied["writer_sha256"] = WRITER_SHA
        return digest(supplied)

    def validate(self):
        need(self.day == DAY and self.epoch == EPOCH, "IMAGE_SCOPE_MISMATCH")
        need(type(self.build_sha) is str and GIT_SHA.fullmatch(self.build_sha), "IMAGE_BUILD_PIN")
        need(type(self.image_id) is str and self.image_id.startswith("sha256:")
             and SHA.fullmatch(self.image_id[7:]), "IMAGE_ID_PIN")
        for key in ("document_order_sha256", "release_sha256", "package_sha256",
                    "capacity_config_sha256", "calendar_pin_sha256", "runtime_authority_sha256",
                    "finite_authority_sha256"):
            value = getattr(self, key)
            need(type(value) is str and SHA.fullmatch(value) and value not in ("0" * 64, PLACEHOLDER),
                 "IMAGE_INPUT_PIN")
        # Reviewed OPS producer/reader/writer use uid 0. This is a source
        # constraint; the actual measured identity remains a mandatory gate.
        need(type(self.owner_uid) is int and self.owner_uid == 0, "IMAGE_OWNER_PIN")
        need(type(self.capacity_veto_mode) is str
             and self.capacity_veto_mode in ("DISPATCH_AND_DERIVATION_ONLY", "CONTINUOUS"),
             "IMAGE_VETO_MODE_PIN")
        need(type(self.readback_margin_seconds) in (int, float)
             and 0 < self.readback_margin_seconds <= 60,
             "MANIFEST_READBACK_MARGIN_INVALID")
        need(type(self.manifest_directory) is str, "MANIFEST_DIRECTORY_INVALID")
        path = Path(self.manifest_directory)
        need(path.is_absolute() and ".." not in path.parts
             and str(path) == self.manifest_directory, "MANIFEST_DIRECTORY_INVALID")
        need(self.require_go_mode in ("INDIVIDUAL", "DELEGATED_ACT_B"), "MANIFEST_GO_MODE")
        opening, before, after, view = map(instant, (self.session_open, self.not_before,
                                                   self.not_after, self.view_opens_at))
        need(opening.astimezone(NY).date() == date.fromisoformat(self.day), "CALENDAR_DAY_MISMATCH")
        need(before < after and before <= view < after <= opening - timedelta(minutes=10),
             "MANIFEST_EFFECT_WINDOW")
        need(after >= view + timedelta(seconds=10 + self.readback_margin_seconds),
             "MANIFEST_VIEW_READBACK_MARGIN")
        need(before.astimezone(NY).date() == date.fromisoformat(self.day)
             and (after - timedelta(microseconds=1)).astimezone(NY).date() == date.fromisoformat(self.day),
             "MANIFEST_EFFECT_DAY")
        return self


@dataclass(frozen=True)
class Invocation:
    scope: Scope
    argv: tuple[str, ...]
    stdin: bytes


def invocation(scope: Scope, writer_source: bytes, *, now: datetime):
    """Produce an argv vector for the reviewed source. This performs no effect."""
    scope.validate()
    need(type(writer_source) is bytes and sha(writer_source) == WRITER_SHA, "MANIFEST_WRITER_PIN")
    current = instant(now)
    need(current.astimezone(NY).date() == date.fromisoformat(scope.day), "MANIFEST_DAY_NOT_TODAY")
    need(instant(scope.not_before) <= current < instant(scope.not_after)
         and current < instant(scope.session_open) - timedelta(minutes=10), "MANIFEST_WINDOW_CLOSED")
    # No parked wait: the finite executor starts after the declared fresh view
    # instant. The writer still checks the real pinned view and both real GOs.
    need(instant(scope.view_opens_at) <= current, "VETO_VIEW_NOT_YET")
    argv = ("python", "-I", "-B", "-", "--day", scope.day,
            "--manifest-directory", scope.manifest_directory, "--prepare-first",
            "--view-opens-at", instant(scope.view_opens_at).isoformat(),
            "--max-wait-seconds", "0", "--require-go-mode", scope.require_go_mode)
    return Invocation(scope, argv, writer_source)


def check_receipt(scope: Scope, receipt: dict, exit_code: int):
    scope.validate()
    need(type(receipt) is dict and type(exit_code) is int and exit_code == 0,
         "MANIFEST_RESULT_UNVERIFIED")
    need(receipt.get("schema") == "R2D2_V2_BAR_MANIFEST_WRITER_RECEIPT_V1"
         and receipt.get("mode") == "PUBLISH" and receipt.get("status") in SUCCESS
         and receipt.get("code") is None, "MANIFEST_RESULT_UNVERIFIED")
    for key, expected in {
        "epoch": scope.epoch, "session": scope.day, "owner_uid": scope.owner_uid,
        "build_sha": scope.build_sha, "release_sha256": scope.release_sha256,
        "package_sha256": scope.package_sha256, "capacity_config_sha256": scope.capacity_config_sha256,
        "capacity_veto_mode": scope.capacity_veto_mode, "massive_bars_enabled": True,
    }.items():
        need(type(receipt.get(key)) is type(expected) and receipt[key] == expected,
             "MANIFEST_RESULT_PIN_MISMATCH")
    need(instant(receipt.get("cutoff_at")) == instant(scope.session_open) - timedelta(minutes=10),
         "MANIFEST_RESULT_CUTOFF")
    need(receipt.get("go_mode") == scope.require_go_mode, "MANIFEST_RESULT_GO_MODE")
    for key in ("binding_sha256", "manifest_sha256", "go_sha256", "template_sha256"):
        need(type(receipt.get(key)) is str and SHA.fullmatch(receipt[key]), "MANIFEST_RESULT_HASH")
    view = receipt.get("view")
    need(type(view) is dict and set(view) == {"observed_at", "valid_until"}, "MANIFEST_RESULT_VIEW")
    need(instant(view["observed_at"]) == instant(scope.view_opens_at)
         and instant(view["observed_at"]) < instant(view["valid_until"]) <= instant(scope.not_after),
         "MANIFEST_RESULT_VIEW")
    published = instant(receipt.get("published_at"))
    need(instant(view["observed_at"]) <= published < instant(view["valid_until"]),
         "MANIFEST_RESULT_PUBLISH_CLOCK")
    need(type(receipt.get("symbol_count")) is int and 0 < receipt["symbol_count"] <= 550,
         "MANIFEST_RESULT_COUNT")
    return receipt


def invoke_once(plan: Invocation, *, clock: Callable[[], datetime],
                immediate_gate: Callable[[Scope, str, datetime], None],
                reserve: Callable[[str, str], None],
                execute: Callable[[tuple[str, ...], bytes], tuple[int, bytes]]):
    """One transport call, with a durable consume-before-effect claim.

    An identifiable invocation consumes before all gates, including refusals.
    immediate_gate must raise unless the real finite authority, image/runtime,
    calendar, config, source roots, concurrency/revocation checks are accepted.
    reserve(attempt_key, scope_sha256) must use a persistent exclusive claim
    shared by all executor jobs. The stable epoch/day/operation key prevents a
    changed scope hash or new process from creating a second attempt.
    It must never erase the claim on refusal, crash or uncertainty. Callbacks
    are mandatory; their implementation/proof remains the executor's scope.
    """
    need(isinstance(plan, Invocation) and isinstance(plan.scope, Scope)
         and plan.scope.epoch == EPOCH and plan.scope.day == DAY, "IMAGE_SCOPE_MISMATCH")
    need(callable(reserve), "EXECUTOR_CLAIM_UNBOUND")
    # The stable logical scope is identifiable before authority/time/source
    # checks. The exact scope hash records the supplied input; it is not the key.
    need(reserve(ATTEMPT_KEY, plan.scope.scope_sha256) is None, "EXECUTOR_CLAIM_PROTOCOL")
    # After this point the option is consumed even if a subsequent gate refuses.
    need(all(callable(value) for value in (clock, immediate_gate, execute)), "EXECUTOR_UNBOUND")
    checked = invocation(plan.scope, plan.stdin, now=clock())
    need(plan.argv == checked.argv, "MANIFEST_INVOCATION_CHANGED")
    need(immediate_gate(plan.scope, "AFTER_CLAIM", instant(clock())) is None, "EXECUTOR_GATE_PROTOCOL")
    invocation(plan.scope, plan.stdin, now=clock())
    need(immediate_gate(plan.scope, "BEFORE_WRITER", instant(clock())) is None, "EXECUTOR_GATE_PROTOCOL")
    # The external verifier may perform slow reads. Recheck pure source/scope/
    # date/window predicates after it returns, immediately before the transport.
    invocation(plan.scope, plan.stdin, now=clock())
    try:
        exit_code, raw = execute(plan.argv, plan.stdin)
    except Exception:
        raise Hold("MANIFEST_TRANSPORT_UNCERTAIN") from None
    receipt = strict_json(raw)
    need(instant(clock()) < instant(plan.scope.not_after), "MANIFEST_RESULT_AFTER_WINDOW")
    check_receipt(plan.scope, receipt, exit_code)
    need(immediate_gate(plan.scope, "BEFORE_READBACK", instant(clock())) is None, "EXECUTOR_GATE_PROTOCOL")
    # A successful slow readback callback cannot turn a now-expired operation
    # into COMPLETE. Any effects already performed remain consumed/uncertain.
    need(instant(clock()) < instant(plan.scope.not_after), "MANIFEST_RESULT_AFTER_WINDOW")
    return receipt


@dataclass(frozen=True)
class FileEvidence:
    raw: bytes
    device: int
    inode: int
    uid: int
    gid: int
    mode: int
    nlink: int


@dataclass(frozen=True)
class DirectoryPin:
    device: int
    inode: int
    uid: int
    mode: int = 0o700


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_uid, info.st_gid,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_private_file(root: str, pin: DirectoryPin, name: str):
    """Explicit read-only read of a pinned directory leaf, no symlink traversal."""
    path = Path(root)
    need(path.is_absolute() and ".." not in path.parts and str(path) == root,
         "READBACK_ROOT_INVALID")
    need(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.=-]+", name)
         and name not in (".", ".."), "READBACK_NAME_INVALID")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    file_fd, nodes, descriptors = None, [], [fd]
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            info = os.fstat(next_fd)
            nodes.append((fd, part, next_fd, (info.st_dev, info.st_ino)))
            descriptors.append(next_fd)
            fd = next_fd
        def verify_ancestors():
            for parent, part, child, identity in nodes:
                observed = os.stat(part, dir_fd=parent, follow_symlinks=False)
                need(stat.S_ISDIR(observed.st_mode) and (observed.st_dev, observed.st_ino) == identity
                     and (os.fstat(child).st_dev, os.fstat(child).st_ino) == identity,
                     "READBACK_ROOT_CHANGED")
        verify_ancestors()
        info = os.fstat(fd)
        need((info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)) ==
             (pin.device, pin.inode, pin.uid, pin.mode) and pin.mode == 0o700,
             "READBACK_ROOT_PIN")
        file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        before = os.fstat(file_fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == pin.uid
             and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1
             and 0 < before.st_size <= LIMIT, "READBACK_FILE_POLICY")
        chunks, remaining = [], LIMIT + 1
        while remaining:
            part = os.read(file_fd, remaining)
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        raw = b"".join(chunks)
        after = os.fstat(file_fd)
        need(_identity(before) == _identity(after) and len(raw) == before.st_size,
             "READBACK_FILE_CHANGED")
        named = os.stat(name, dir_fd=fd, follow_symlinks=False)
        need(_identity(named) == _identity(after), "READBACK_FILE_CHANGED")
        verify_ancestors()
        need(_identity(info) == _identity(os.fstat(fd)), "READBACK_ROOT_CHANGED")
        return FileEvidence(raw, before.st_dev, before.st_ino, before.st_uid, before.st_gid,
                            stat.S_IMODE(before.st_mode), before.st_nlink)
    except OSError:
        raise Hold("READBACK_FILE_UNAVAILABLE") from None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        for opened in reversed(descriptors):
            os.close(opened)


def _file(evidence: FileEvidence, owner_uid: int):
    need(isinstance(evidence, FileEvidence) and type(evidence.raw) is bytes
         and evidence.uid == owner_uid and evidence.mode == 0o600 and evidence.nlink == 1
         and 0 < len(evidence.raw) <= LIMIT, "READBACK_FILE_POLICY")
    return strict_json(evidence.raw)


def _journal(row, records, *, day):
    need(type(row) is dict and type(row.get("state")) is dict
         and type(records) in (list, JournalSnapshot),
         "DB_READBACK_UNAVAILABLE")
    need(digest(row["state"]) == row.get("state_sha"), "DB_STATE_HASH")
    epoch, head, keys, selected = row["state"].get("epoch"), "", set(), {}
    for sequence, record in enumerate(_journal_records(records), 1):
        need(type(record) is dict and record.get("epoch") == epoch
             and type(record.get("sequence")) is int and record["sequence"] == sequence
             and record.get("previous_sha") == head and type(record.get("journal_key")) is str
             and record["journal_key"] not in keys and type(record.get("payload")) is dict
             and record["payload"].get("journal_key") == record["journal_key"], "DB_JOURNAL_CHAIN")
        need(digest({k: v for k, v in record.items() if k != "record_sha"}) == record.get("record_sha"),
             "DB_JOURNAL_HASH")
        head = record["record_sha"]
        keys.add(record["journal_key"])
        if record["journal_key"] in ("capacity-prepared:" + day, "universe:" + day):
            selected[record["journal_key"]] = record
    need(head == row.get("journal_head"), "DB_JOURNAL_HEAD")
    return selected


def _capacity_snapshot(scope: Scope, receipt: dict, row: dict, records,
                            manifest: FileEvidence, *, require_session_binding=False):
    """Reconcile bytes from one actual consistent image read_with_journal.

    Pre-reader and first pre-capture cycle: daily_capacity is required,
    sessions.binding is optional but if present must agree. After actual
    capture: require_session_binding=True. A prepared binding has
    capacity-prepared:D, not necessarily capacity:D.
    This verifies the transport/scope/hash chain; it does not replace the
    image's independent authority/binding verifier or recertify a host.
    """
    check_receipt(scope, receipt, 0)
    selected = _journal(row, records, day=scope.day)
    state = row["state"]
    need(state.get("epoch") == scope.epoch and state.get("release_sha") == scope.release_sha256,
         "DB_SCOPE_MISMATCH")
    persisted = state.get("daily_capacity", {}).get(scope.day)
    need(type(persisted) is dict and set(persisted) == {"sha", "document"}
         and type(persisted["document"]) is dict and digest(persisted["document"]) == persisted["sha"]
         and persisted["sha"] == receipt["binding_sha256"], "DB_BINDING_HASH")
    binding = persisted["document"]
    need(binding.get("schema") == "V2_DAILY_CAPACITY_BINDING_CANDIDATE_V1"
         and binding.get("epoch") == scope.epoch and binding.get("day") == scope.day
         and binding.get("release_sha") == scope.release_sha256, "DB_BINDING_SCOPE")
    names = binding.get("monitored_symbols")
    need(type(names) is list and 0 < len(names) <= 550
         and all(type(name) is str and SYMBOL.fullmatch(name) for name in names)
         and names == sorted(set(names)), "DB_BINDING_SYMBOLS")
    sessions = state.get("sessions", {})
    need(type(sessions) is dict, "DB_SESSION_INVALID")
    session = sessions.get(scope.day, {})
    need(type(session) is dict and not session.get("capacity_admission_blocked"), "DB_ADMISSION_BLOCKED")
    copied = session.get("capacity_binding")
    need((copied is None and not require_session_binding) or copied == persisted,
         "DB_SESSION_BINDING_MISSING_OR_CHANGED")
    prepared_record = selected.get("capacity-prepared:" + scope.day)
    prepared = prepared_record.get("payload") if type(prepared_record) is dict else None
    need(type(prepared) is dict and prepared.get("type") == "CAPACITY_DAY_PREPARED"
         and prepared.get("session") == scope.day and prepared.get("plan_sha") == persisted["sha"]
         and prepared.get("payload") == binding, "DB_PREPARE_RECEIPT_MISSING_OR_CHANGED")
    observed = _file(manifest, scope.owner_uid)
    file_pin = receipt.get("file")
    need(type(file_pin) is dict and file_pin == {
        "uid": manifest.uid, "gid": manifest.gid, "mode": "0600", "nlink": 1,
        "device": manifest.device, "inode": manifest.inode, "size_within_limit": True},
        "MANIFEST_READBACK_IDENTITY_MISMATCH")
    expected = {"epoch": scope.epoch, "session": scope.day, "symbols": names, "owner_uid": scope.owner_uid}
    need(observed == expected and manifest.raw == canonical(expected)
         and sha(manifest.raw) == receipt["manifest_sha256"] and len(names) == receipt["symbol_count"],
         "MANIFEST_READBACK_MISMATCH")
    return {"status": "IMAGE_BYTES_RECONCILED", "session": scope.day,
            "binding_sha256": persisted["sha"], "manifest_sha256": sha(manifest.raw),
            "state_sha256": row["state_sha"], "journal_head_sha256": row["journal_head"],
            "symbol_count": len(names), "session_binding_copied": copied == persisted}, selected


def check_capacity_manifest(scope: Scope, receipt: dict, row: dict, records,
                            manifest: FileEvidence, *, require_session_binding=False):
    result, _ = _capacity_snapshot(scope, receipt, row, records, manifest,
                                  require_session_binding=require_session_binding)
    return result


def reader_gate(scope: Scope, receipt: dict, row: dict, records: list, manifest: FileEvidence,
                ready: FileEvidence, session_manifest: FileEvidence, session_root: DirectoryPin,
                *, now: datetime, not_before: datetime, not_after: datetime,
                session_close: datetime):
    """Read-only ready/catalog prerequisite to the first SESSION consumer.

    The existing reader_launcher does NOT hold on READY_NOT_OBSERVED. The
    finite executor must enforce this gate before the internal SESSION effect.
    A successful PRE_OPEN process launch alone cannot enforce that transition.
    The separate finite window and session_close must come from accepted
    authority and the pinned actual calendar. A ready marker observed after
    open is valid under those conditions; open-10s is not an image constraint.
    Nothing here writes a marker, initializes SQLite, launches or retries.
    """
    result = check_capacity_manifest(scope, receipt, row, records, manifest)
    current, opening = _phase_clock(scope, receipt, now)
    before, after, closing = map(instant, (not_before, not_after, session_close))
    # This finite component is only for the regular 12/10 session. The source
    # calendar and its pin still require independent verification by the bridge.
    need(closing == opening + timedelta(hours=6, minutes=30), "READER_CALENDAR_CLOSE_MISMATCH")
    need(closing.astimezone(NY).date() == date.fromisoformat(scope.day) and opening < closing
         and opening - timedelta(seconds=90) <= before < after <= closing + timedelta(minutes=20),
         "READER_SESSION_EFFECT_WINDOW_INVALID")
    need(current.astimezone(NY).date() == date.fromisoformat(scope.day)
         and before <= current < after, "READER_SESSION_WINDOW_CLOSED")
    marker = _file(ready, scope.owner_uid)
    need(marker == {"epoch": scope.epoch, "session": scope.day}, "READER_READY_MISMATCH")
    catalog = _file(session_manifest, scope.owner_uid)
    need(type(ready.device) is int and type(session_manifest.device) is int
         and type(session_root.device) is int
         and ready.device == session_manifest.device == session_root.device,
         "READER_SESSION_DEVICE_MISMATCH")
    need(type(catalog) is dict and set(catalog) ==
         {"schema", "epoch", "session", "symbols", "device", "inode"}
         and catalog["schema"] == "MASSIVE_SESSION_V1" and catalog["epoch"] == scope.epoch
         and catalog["session"] == scope.day and type(catalog["device"]) is int
         and type(catalog["inode"]) is int and catalog["device"] == session_root.device
         and catalog["inode"] == session_root.inode and session_root.uid == scope.owner_uid
         and session_root.mode == 0o700, "READER_SESSION_ROOT_MISMATCH")
    need(catalog["symbols"] == strict_json(manifest.raw)["symbols"], "READER_SYMBOLS_MISMATCH")
    result.update(status="READER_PREREQUISITE_BYTES_RECONCILED", ready_sha256=sha(ready.raw),
                  session_manifest_sha256=sha(session_manifest.raw),
                  observed_at=current.isoformat(), not_before=before.isoformat(),
                  not_after=after.isoformat(), session_close=closing.isoformat())
    return result


def _phase_clock(scope: Scope, receipt: dict, now: datetime):
    """Pure clock checks; authority/calendar/runtime originals remain external."""
    scope.validate()
    current, opening = instant(now), instant(scope.session_open)
    need(current.astimezone(NY).date() == date.fromisoformat(scope.day),
         "IMAGE_PHASE_DAY_MISMATCH")
    need(current >= instant(receipt.get("published_at")), "IMAGE_PHASE_BEFORE_MANIFEST_PUBLISHED")
    return current, opening


def journal_root_gate(scope: Scope, epoch_catalog: FileEvidence, journal_root: DirectoryPin,
                      *, settings_journal_directory: str, expected_journal_directory: str):
    """Exact epoch.json/root evidence, separate from session_date=D/session.json.

    Paths and evidence must be actual readbacks from the same reviewed physical
    namespace as the worker's settings and bind mount. This pure predicate does
    not establish container/host identity, mount topology or filesystem locks.
    The executor must call it after durable claim and before writer/reader
    effects, then recheck identity/settings before the actual transition.
    """
    scope.validate()
    need(type(settings_journal_directory) is str and type(expected_journal_directory) is str
         and settings_journal_directory == expected_journal_directory,
         "JOURNAL_SETTINGS_ROOT_MISMATCH")
    path = Path(expected_journal_directory)
    need(path.is_absolute() and ".." not in path.parts and str(path) == expected_journal_directory,
         "JOURNAL_SETTINGS_ROOT_INVALID")
    need(isinstance(journal_root, DirectoryPin) and type(journal_root.device) is int
         and type(journal_root.inode) is int and journal_root.device >= 0 and journal_root.inode > 0
         and journal_root.uid == scope.owner_uid and journal_root.mode == 0o700,
         "JOURNAL_ROOT_IDENTITY_MISMATCH")
    catalog = _file(epoch_catalog, scope.owner_uid)
    need(type(epoch_catalog.device) is int and type(epoch_catalog.inode) is int
         and epoch_catalog.device == journal_root.device and epoch_catalog.inode > 0,
         "JOURNAL_EPOCH_FILE_IDENTITY_MISMATCH")
    need(catalog == {"schema": "MASSIVE_SESSION_ROOT_V1", "epoch": scope.epoch,
                     "device": journal_root.device, "inode": journal_root.inode},
         "JOURNAL_EPOCH_ROOT_MISMATCH")
    return {"status": "JOURNAL_ROOT_BYTES_RECONCILED", "epoch": scope.epoch,
            "epoch_catalog_sha256": sha(epoch_catalog.raw),
            "physical_namespace_verified": False}


def reader_process_launch_gate(scope: Scope, receipt: dict, row: dict, records: list,
                               manifest: FileEvidence, *, now: datetime):
    """PRE_OPEN process prerequisite; it grants no SESSION/consumer permission.

    The pinned OPS launcher can start PRE_OPEN before ready.json exists. This
    check therefore requires durable daily capacity and its exact manifest,
    but never manufactures ready.json or requires the later capture copy.
    Its internal SESSION transition needs a separately enforced fresh
    reader_gate; a pure pre-launch call cannot intercept that transition.
    """
    result = check_capacity_manifest(scope, receipt, row, records, manifest,
                                     require_session_binding=False)
    current, opening = _phase_clock(scope, receipt, now)
    need(opening - timedelta(hours=6) <= current < opening - timedelta(seconds=90),
         "READER_PROCESS_WINDOW_CLOSED")
    result.update(status="READER_PROCESS_PREREQUISITE_BYTES_RECONCILED",
                  phase="PRE_OPEN", observed_at=current.isoformat(),
                  session_consumer_authorized=False)
    return result


def _capture_times(scope: Scope):
    # Exact reviewed ShadowCalendar._details sets 10:00–10:01 New York,
    # independently of the regular-session opening. Never infer open+30min.
    day = date.fromisoformat(scope.day)
    local = datetime(day.year, day.month, day.day, 10, tzinfo=NY)
    return instant(local), instant(local + timedelta(minutes=1))


def capture_launch_gate(scope: Scope, receipt: dict, row: dict, records: list,
                        manifest: FileEvidence, *, now: datetime,
                        not_before: datetime, not_after: datetime):
    """Process-launch prerequisite in a separate verified finite effect window.

    not_before/not_after must be bound to real accepted authority by the
    executor's mandatory verifier. Supplying times alone grants no authority.
    A process may start before 10:00NY; no launch after 10:01NY can satisfy the
    reviewed collector's capture window. Cleanup budgets do not extend it.
    The copy is made by _capture, so it is optional before this launch.
    """
    result = check_capacity_manifest(scope, receipt, row, records, manifest,
                                     require_session_binding=False)
    current, opening = _phase_clock(scope, receipt, now)
    before, after = instant(not_before), instant(not_after)
    capture_open, capture_close = _capture_times(scope)
    need(before < after and before.astimezone(NY).date() == date.fromisoformat(scope.day)
         and (after - timedelta(microseconds=1)).astimezone(NY).date() == date.fromisoformat(scope.day),
         "CAPTURE_EFFECT_WINDOW_INVALID")
    need(before <= current < after and opening <= current < capture_close,
         "CAPTURE_LAUNCH_WINDOW_CLOSED")
    result.update(status="CAPTURE_LAUNCH_PREREQUISITE_BYTES_RECONCILED",
                  observed_at=current.isoformat(), capture_open=capture_open.isoformat(),
                  capture_close=capture_close.isoformat(),
                  effective_launch_not_after=min(after, capture_close).isoformat())
    return result


def after_first_cycle_gate(scope: Scope, receipt: dict, row: dict, records: list,
                           manifest: FileEvidence, *, now: datetime):
    """Copied evidence after a cycle; pre-capture case B can lack session copy.

    The executor must separately verify the real cycle result and preceding
    ready/catalog gate. This predicate is no substitute for either original.
    A copy that is present must agree even when it is not yet required.
    """
    result = check_capacity_manifest(scope, receipt, row, records, manifest,
                                     require_session_binding=False)
    current, _ = _phase_clock(scope, receipt, now)
    result.update(status="AFTER_FIRST_CYCLE_CAPACITY_BYTES_RECONCILED",
                  observed_at=current.isoformat(), cycle_result_verified=False)
    return result


def after_capture_gate(scope: Scope, receipt: dict, row: dict, records: list,
                       manifest: FileEvidence, *, now: datetime):
    """Require the exact session copy only after actual capture can occur.

    Binding equality does not prove that capture executed or succeeded. The
    executor still needs an actual COMPLETE capture result with ABI/provenance
    verification; no receipt, causal feed, SESSION gate or GO is issued here.
    """
    result, selected = _capacity_snapshot(scope, receipt, row, records, manifest,
                                         require_session_binding=False)
    current, _ = _phase_clock(scope, receipt, now)
    capture_open, _ = _capture_times(scope)
    need(current >= capture_open, "CAPTURE_COPY_CHECK_TOO_EARLY")
    session = row["state"].get("sessions", {}).get(scope.day, {})
    universe = session.get("universe")
    original = selected.get("universe:" + scope.day)
    # This code describes a read-only observation of a not-yet-committed fact.
    # It never grants a second physical capture or clears a consumed claim.
    need(original is not None and universe is not None and result["session_binding_copied"],
         "CAPTURE_NOT_YET_COMMITTED")
    need(capture_open <= instant(original.get("recorded_at")) <= current,
         "DB_CAPTURE_COMMIT_CLOCK")
    record = original.get("payload")
    causal = record.get("causal_list") if type(record) is dict else None
    need(type(record) is dict and record.get("type") == "CAUSAL_UNIVERSE"
         and record.get("session") == scope.day and type(causal) is dict
         and causal.get("status") == "AVAILABLE", "DB_CAPTURE_UNIVERSE_MISSING_OR_CHANGED")
    names = causal.get("symbols")
    need(type(names) is list and len(names) <= 550
         and all(type(name) is str and SYMBOL.fullmatch(name) for name in names)
         and len(names) == len(set(names)) and type(causal.get("n_cut")) is int
         and causal["n_cut"] == 550
         and all(type(causal.get(k)) is str and SHA.fullmatch(causal[k])
                 for k in ("list_sha256", "commitment_sha256")),
         "DB_CAPTURE_UNIVERSE_MISSING_OR_CHANGED")
    stored_causal = session.get("causal_list")
    need(type(universe) is list and universe == ["US:" + name for name in names]
         and session.get("universe_sha") == causal["list_sha256"]
         and type(stored_causal) is dict
         and stored_causal.get("list_sha256") == causal["list_sha256"]
         and stored_causal.get("commitment_sha256") == causal["commitment_sha256"],
         "DB_CAPTURE_UNIVERSE_MISSING_OR_CHANGED")
    result.update(status="AFTER_CAPTURE_BINDING_BYTES_RECONCILED",
                  observed_at=current.isoformat(), capture_result_verified=False,
                  causal_universe_committed=True, physical_retry_authorized=False)
    return result
