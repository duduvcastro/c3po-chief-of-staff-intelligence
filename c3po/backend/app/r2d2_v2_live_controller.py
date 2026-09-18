"""Leased subscription controller in the existing worker; no second connection.

OFF until operators install a private, hash-pinned policy after the head audit
and capacity acceptance. Policy receipts are operator attestations, not invented
cryptographic signatures. No live policy is shipped in this repository.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import stat
import uuid
from threading import Event, Thread
from time import monotonic
from typing import Any, Callable

from .maintenance_gate import job
from .r2d2_v2_calendar import ShadowCalendar
from .r2d2_v2_earnings_package import implementation_package_sha as current_package_sha
from .r2d2_v2_live_group import plan_live_group, GROUP_NAME
from .r2d2_v2_shadow import Release
from .r2d2_v2_shadow_worker import _release_bytes
from .r2d2_v2_store import ShadowIntegrityError, digest, utc

ORDER_SHA = "1ad8b90cfab651823eb677b830a0078d10c17447575c8d813c3883a718579d8e"
INTERVAL = 5.0
LEASE_SECONDS = 15.0
LIVE_JOURNAL_BYTES = 64 * 1048576
LIVE_RECORD_BYTES = 3072
LIVE_WITHDRAWAL_DELTA_BYTES = 32768
logger = logging.getLogger(__name__)


def read_policy(settings: Any, now: datetime) -> dict:
    path = str(settings.r2d2_v2_live_policy_file)
    data = _release_bytes(path)
    if hashlib.sha256(data).hexdigest() != settings.r2d2_v2_live_policy_sha:
        raise ShadowIntegrityError("LIVE_POLICY_HASH_MISMATCH")
    policy = json.loads(data)
    if (policy.get("schema") != "R2D2_V2_LIVE_POLICY_V1"
            or policy.get("order_sha") != ORDER_SHA
            or not re.fullmatch(r"[0-9a-f]{40}", str(policy.get("code_revision", "")))
            or policy.get("code_revision") != settings.build_sha
            or policy.get("package_sha") != current_package_sha()
            or any(not re.fullmatch(r"[0-9a-f]{64}", str(policy.get(k, "")))
                   for k in ("c8_receipt_sha", "head_go_sha"))
            or type(policy.get("capacity")) is not int
            or not 1 <= policy["capacity"] <= 550):
        raise ShadowIntegrityError("LIVE_POLICY_INVALID")
    start, end = utc(policy["valid_from"]), utc(policy["valid_until"])
    if not start <= now < end:
        raise ShadowIntegrityError("LIVE_POLICY_OUTSIDE_WINDOW")
    if policy.get("mode") == "PROOF":
        names = policy.get("symbols")
        if (not isinstance(names, list) or not names or any(not isinstance(s, str)
                or not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,19}", s) for s in names)
                or len(set(names)) != len(names) or len(names) < 2
                or digest(names) != policy.get("list_sha")
                or not re.fullmatch(r"[0-9a-f]{64}", str(policy.get("causal_list_receipt_sha", "")))
                or (end-start).total_seconds() != 60):
            raise ShadowIntegrityError("LIVE_PROOF_INVALID")
        day = start.date().isoformat()
        if day == "2026-09-16":
            session = ShadowCalendar().details(start.date())
            if (len(names) > 10 or policy.get("merged_on") != "2026-09-15"
                    or not session["open"] <= start < end <= session["close"]):
                raise ShadowIntegrityError("LIVE_WEDNESDAY_PROOF_INVALID")
        elif day == "2026-09-17":
            lo, hi = utc("2026-09-17T14:15:00Z"), utc("2026-09-17T15:00:00Z")
            if not lo <= start < end <= hi or len(names) > policy["capacity"]:
                raise ShadowIntegrityError("LIVE_THURSDAY_PROOF_INVALID")
        elif day == "2026-09-18":
            lo, hi = utc("2026-09-18T18:30:00Z"), utc("2026-09-18T19:45:00Z")
            if not lo <= start < end <= hi or len(names) > policy["capacity"]:
                raise ShadowIntegrityError("LIVE_FRIDAY_PROOF_INVALID")
        else:
            raise ShadowIntegrityError("LIVE_PROOF_DAY_INVALID")
    elif policy.get("mode") != "LIVE" or (end-start).total_seconds() > 90 * 86400:
        raise ShadowIntegrityError("LIVE_POLICY_MODE_INVALID")
    return policy


def read_live_inventory(settings: Any, policy: dict, now: datetime) -> tuple[Any, dict | None]:
    data = _release_bytes(settings.r2d2_v2_shadow_release_file)
    release = Release.verify(data, settings.r2d2_v2_shadow_release_sha, now=now,
                             build_sha=settings.build_sha, calendar=ShadowCalendar())
    if (release.mode != "CERTIFIED" or release.epoch != policy.get("epoch")
            or release.receipt_sha != policy.get("release_sha")):
        raise ShadowIntegrityError("LIVE_RELEASE_MISMATCH")
    import psycopg
    # A separate bounded READ ONLY connection; never initialize or migrate.
    with psycopg.connect(settings.database_url, connect_timeout=3,
                         options="-c default_transaction_read_only=on -c statement_timeout=3000 -c lock_timeout=1000",
                         tcp_user_timeout=5000) as connection:
        row = connection.execute("""SELECT CASE WHEN octet_length(state::text)<=8388608 THEN state END,
            state_sha FROM r2d2_v2_shadow_epochs WHERE epoch=%s""", (release.epoch,)).fetchone()
    if row is not None and row[0] is None:
        raise ShadowIntegrityError("LIVE_STATE_TOO_LARGE")
    return release, ({"state": row[0], "state_sha": row[1]} if row else None)


def compact_live_receipt(receipt: dict) -> dict:
    """Periodic evidence without repeatedly embedding the withdrawal history.

    The atomic status file keeps the full receipt. PROOF keeps its full journal.
    LIVE keeps linkage hashes, current group/feed evidence and the receipt time;
    history hashes are commitments, not a claim that the full history is here.
    """
    subscription = receipt.get("subscription") or {}
    compact = {key: receipt[key] for key in
               ("at", "policy_sha", "mode", "state_sha", "status", "readiness", "disk_written")
               if key in receipt}
    compact["schema"] = "R2D2_V2_LIVE_RECEIPT_COMPACT_V1"
    compact["full_receipt_sha256"] = digest(receipt)
    compact["subscription"] = {key: subscription[key] for key in
        ("status", "generation", "desired_count", "symbols_sha256", "incremental_count",
         "capacity", "provider_ack_verified", "readiness") if key in subscription}
    compact["subscription"]["feeds"] = {feed: {key: values[key] for key in
        ("connection_generation", "sent_count", "first_sent_at", "first_received_at",
         "last_received_at", "received_count") if key in values}
        for feed, values in subscription.get("feeds", {}).items() if feed in {"quote", "trade"}}
    withdrawals = subscription.get("withdrawals", [])
    compact["retained_withdrawal_count"] = len(withdrawals)
    compact["withdrawals_sha256"] = digest(withdrawals)
    if receipt.get("subscription_before_drop") is not None:
        compact["subscription_before_drop_sha256"] = digest(receipt["subscription_before_drop"])
    return compact


class LiveGroupController:
    def __init__(self, settings: Any, stream: Any, *,
                 inventory: Callable = read_live_inventory, policy_reader: Callable = read_policy,
                 clock: Callable = lambda: datetime.now(timezone.utc)) -> None:
        self.settings, self.stream = settings, stream
        self.inventory, self.policy_reader, self.clock = inventory, policy_reader, clock
        self.stop_event = Event()
        self.thread: Thread | None = None
        self.proof_started: float | None = None
        self.proof_used = False
        self.policy_identity: str | None = None
        self.last_receipt: dict = {"status": "OFF", "readiness": "BLOCKED"}
        self._persisted_withdrawals_sha: str | None = None
        self._persisted_withdrawal_hashes: set[str] = set()

    def _proof_claim(self) -> None:
        # Durable one-shot receipt, survives worker restart. Never remove this
        # latch automatically; a repeated invocation of the same policy fails.
        path = Path(self.settings.r2d2_v2_live_policy_file)
        if path.parent.stat().st_mode & 0o077:
            raise ShadowIntegrityError("LIVE_POLICY_DIRECTORY_NOT_PRIVATE")
        marker = path.with_name(path.name + "." + self.settings.r2d2_v2_live_policy_sha + ".used")
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write("PROOF_CLAIMED\n")
            out.flush()
            os.fsync(out.fileno())
        self.proof_used = True
        self.proof_started = monotonic()

    def step(self) -> dict:
        now = self.clock()
        started = monotonic()
        try:
            if self.stop_event.is_set():
                raise ShadowIntegrityError("LIVE_CONTROLLER_STOPPED")
            policy = self.policy_reader(self.settings, now)
            identity = self.settings.r2d2_v2_live_policy_sha
            if self.policy_identity is not None and self.policy_identity != identity:
                raise ShadowIntegrityError("LIVE_POLICY_CHANGED_RESTART_REQUIRED")
            self.policy_identity = identity
            state_sha = None
            ttl = min(LEASE_SECONDS, (utc(policy["valid_until"]) - now).total_seconds())
            if policy["mode"] == "PROOF":
                if self.proof_started is None:
                    if self.proof_used:
                        raise ShadowIntegrityError("LIVE_PROOF_ALREADY_USED")
                    if (now - utc(policy["valid_from"])).total_seconds() > 10:
                        raise ShadowIntegrityError("LIVE_PROOF_START_MISSED")
                    self._proof_claim()
                elapsed = (now - utc(policy["valid_from"])).total_seconds()
                duration = (utc(policy["valid_until"]) - utc(policy["valid_from"])).total_seconds() - 5
                if elapsed >= duration:
                    raise ShadowIntegrityError("LIVE_PROOF_EXPIRED")
                ttl = min(ttl, duration - elapsed)
                # Addition and withdrawal are automatic in the SAME bounded run.
                phase = min(2, int(elapsed / (duration / 3)))
                if self.proof_started is None or monotonic() - self.proof_started >= 60:
                    raise ShadowIntegrityError("LIVE_PROOF_EXPIRED")
                names = policy["symbols"][:-1] if phase != 1 else policy["symbols"]
                ttl = min(ttl, 60 - (monotonic() - self.proof_started))
            else:
                release, saved = self.inventory(self.settings, policy, now)
                if saved is None:
                    raise ShadowIntegrityError("LIVE_EPOCH_NOT_FOUND")
                plan = plan_live_group(saved, release, capacity=policy["capacity"])
                names, state_sha = plan["symbols"], plan["state_sha"]
            # DB/file I/O cannot extend an expired policy or refresh a stale plan.
            after = self.clock()
            if (monotonic()-started >= 10 or (after-now).total_seconds() >= 10
                    or after < now or after >= utc(policy["valid_until"])):
                raise ShadowIntegrityError("LIVE_REFRESH_TIMEOUT")
            self.policy_reader(self.settings, after)
            ttl = min(ttl, (utc(policy["valid_until"]) - after).total_seconds())
            if policy["mode"] == "PROOF":
                ttl = min(ttl, (utc(policy["valid_until"]) - after).total_seconds() - 5)
            if self.stop_event.is_set():
                raise ShadowIntegrityError("LIVE_CONTROLLER_STOPPED")
            status = self.stream.set_v2_group(names, capacity=policy["capacity"], ttl=ttl, stop_event=self.stop_event)
            receipt = {"at": after.isoformat(), "policy_sha": identity, "mode": policy["mode"],
                       "state_sha": state_sha, "status": "SUBSCRIPTION_REQUESTED", "readiness": "NOT_PROVEN",
                       "subscription": status, "disk_written": "REQUIRES_INDEPENDENT_SESSION_FILE_READ"}
        except Exception as exc:
            before_drop = self.stream.v2_status()
            self.stream.set_group(GROUP_NAME, [])
            if self.proof_used:
                self.proof_started = None
            code = str(exc) if isinstance(exc, (ShadowIntegrityError, ValueError)) else type(exc).__name__
            # Never expose connection strings, symbol lists or provider errors.
            if not re.fullmatch(r"[A-Z0-9_]{1,100}", code):
                code = "LIVE_CONTROLLER_FAILURE"
            if isinstance(exc, FileExistsError):
                code = "LIVE_PROOF_ALREADY_USED"
            elif isinstance(exc, FileNotFoundError):
                code = "LIVE_POLICY_OR_RELEASE_MISSING"
            elif isinstance(exc, json.JSONDecodeError):
                code = "LIVE_POLICY_OR_RELEASE_JSON_INVALID"
            receipt = {"at": now.isoformat(), "status": code, "readiness": "BLOCKED",
                       "subscription_before_drop": before_drop, "subscription": self.stream.v2_status()}
        self.last_receipt = receipt
        return receipt

    def _persist(self, receipt: dict) -> None:
        path = Path(self.settings.r2d2_v2_live_policy_file)
        info = path.parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
            raise ShadowIntegrityError("LIVE_POLICY_DIRECTORY_NOT_PRIVATE")
        target = path.with_name(path.name + ".status.json")
        temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "w") as out:
                json.dump(receipt, out, sort_keys=True)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp, target)
            if receipt.get("mode") in {"PROOF", "LIVE"} or self.proof_used or self.policy_identity:
                proof = self.proof_used or receipt.get("mode") == "PROOF"
                # UTC day comes from the actual observation clock, not policy
                # start or a resettable process uptime. Never delete old days.
                day = utc(receipt["at"]).date().isoformat()
                suffix = ".proof.ndjson" if proof else f".live.{day}.ndjson"
                record = receipt if proof else compact_live_receipt(receipt)
                encoded = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
                if not proof and len(encoded) > LIVE_RECORD_BYTES:
                    raise ShadowIntegrityError("LIVE_RECEIPT_TOO_LARGE")
                withdrawal_sha = None
                withdrawal_hashes: set[str] = set()
                if not proof:
                    withdrawals = receipt.get("subscription", {}).get("withdrawals", [])
                    if not isinstance(withdrawals, list) or len(withdrawals) > 16:
                        raise ShadowIntegrityError("LIVE_WITHDRAWAL_DELTA_INVALID")
                    withdrawal_sha = digest(withdrawals)
                    withdrawal_hashes = {digest(row) for row in withdrawals}
                    if withdrawal_sha != self._persisted_withdrawals_sha:
                        changed = [row for row in withdrawals
                                   if digest(row) not in self._persisted_withdrawal_hashes]
                        if changed or self._persisted_withdrawals_sha is not None:
                            delta = {"schema": "R2D2_V2_LIVE_WITHDRAWAL_DELTA_V1",
                                "at": receipt["at"], "policy_sha": receipt.get("policy_sha"),
                                "previous_withdrawals_sha256": self._persisted_withdrawals_sha,
                                "withdrawals_sha256": withdrawal_sha,
                                "retained_withdrawal_count": len(withdrawals),
                                "entries": changed, "entries_sha256": digest(changed)}
                            delta_bytes = (json.dumps(delta, sort_keys=True) + "\n").encode("utf-8")
                            if len(delta_bytes) > LIVE_WITHDRAWAL_DELTA_BYTES:
                                raise ShadowIntegrityError("LIVE_WITHDRAWAL_DELTA_TOO_LARGE")
                            encoded += delta_bytes
                limit = 1048576 if proof else LIVE_JOURNAL_BYTES
                journal = path.with_name(path.name + suffix)
                fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as out:
                    info = os.fstat(out.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size + len(encoded) > limit:
                        raise ShadowIntegrityError("LIVE_PROOF_RECEIPT_INVALID_OR_FULL")
                    out.write(encoded)
                    out.flush()
                    os.fsync(out.fileno())
                if not proof:
                    # Advance the bounded delta cache only after durable append.
                    self._persisted_withdrawals_sha = withdrawal_sha
                    self._persisted_withdrawal_hashes = withdrawal_hashes
        finally:
            temp.unlink(missing_ok=True)

    def _run(self) -> None:
        try:
            while not self.stop_event.is_set():
                try:
                    with job() as admitted:
                        if admitted:
                            result = self.step()
                            self._persist(result)
                            if self.proof_used and result.get("readiness") == "BLOCKED":
                                self.stop_event.wait(3)
                                self._persist({**result, "at": self.clock().isoformat(),
                                               "subscription": self.stream.v2_status()})
                                return
                        else:
                            self.stream.set_group(GROUP_NAME, [])
                    # No dependency on V1 run_cycle, scans, or position count.
                except Exception:
                    self.stream.set_group(GROUP_NAME, [])
                    logger.error("V2 subscription controller blocked; no exception payload exposed")
                    return  # Persistence failure must not repeatedly reinstall a lease.
                self.stop_event.wait(INTERVAL)
        finally:
            self.stream.set_group(GROUP_NAME, [])

    def start(self) -> None:
        if not self.settings.r2d2_v2_live_policy_file or not self.settings.r2d2_v2_live_policy_sha:
            return
        self.thread = Thread(target=self._run, name="r2d2-v2-live", daemon=True)
        try:
            self.thread.start()
        except Exception:
            self.stream.set_group(GROUP_NAME, [])
            logger.error("V2 subscription controller could not start")

    def stop(self) -> None:
        self.stop_event.set()
        self.stream.set_group(GROUP_NAME, [])
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
