"""Persistent F6 control-plane candidate, stdlib only.

No production adapter is registered in this revision. A missing adapter is a
hard HOLD, never a generic shell/provider/SQL/Docker fallback. Fixture callbacks
exercise the new control plane; Linux integration and physical acceptance remain
separate deliverables. This is explicitly not the binder rev8 wire protocol.
"""
from __future__ import annotations

import fcntl
import os
import stat
import time
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from decision_contracts import Hold, canonical, digest, instant, require, sha, strict_json


def private_file(root_fd, name, *, new=False):
    require(name and "/" not in name and name not in (".", ".."), "PRIVATE_NAME")
    flags = os.O_RDWR | os.O_NOFOLLOW
    if new:
        flags |= os.O_CREAT | os.O_EXCL
    fd = os.open(name, flags, 0o600, dir_fd=root_fd)
    info = os.fstat(fd)
    try:
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1,
                "PRIVATE_FILE_IDENTITY")
    except BaseException:
        os.close(fd)
        raise
    return fd


def write_all(fd, data):
    while data:
        written = os.write(fd, data)
        require(written > 0, "WRITE_UNCERTAIN")
        data = data[written:]


class Ledger:
    """Hash chained ledger + independent durable witness.

    The witness must live outside a rollback domain shared with this root. An
    in-memory fixture witness proves only the API. A missing/stale witness blocks
    every effect. No recovery/reset/re-election API exists here.
    """

    @staticmethod
    def create_fixture(root, election):
        require(election["mode"] == "FIXTURE", "NO_PRODUCTION_BOOTSTRAP")
        root = Path(root)
        root.mkdir(mode=0o700)
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            identity = {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid}
            entry = {"sequence": 0, "previous": "0" * 64, "kind": "GENESIS",
                     "election": election, "root_identity": identity}
            data = canonical(entry)
            jfd = private_file(fd, "ledger.jsonl", new=True)
            try:
                write_all(jfd, data)
                os.fsync(jfd)
            finally:
                os.close(jfd)
            lfd = private_file(fd, "ledger.lock", new=True)
            os.close(lfd)
            os.fsync(fd)
            return {"sequence": 0, "digest": digest(data), "root_identity": identity}
        finally:
            os.close(fd)

    def __init__(self, root, expected_election):
        self.root = Path(root).absolute()
        # Reject links at every ancestor, rather than resolve them into acceptance.
        for path in (self.root, *self.root.parents):
            require(not stat.S_ISLNK(path.lstat().st_mode), "STATE_ANCESTOR_LINK")
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                "STATE_ROOT_PERMISSION")
        self.identity = {"device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid}
        self.election = expected_election

    def close(self):
        os.close(self.fd)

    @contextmanager
    def locked(self, witness):
        lfd = private_file(self.fd, "ledger.lock")
        try:
            fcntl.flock(lfd, fcntl.LOCK_EX)
            jfd = private_file(self.fd, "ledger.jsonl")
            try:
                with os.fdopen(os.dup(jfd), "rb") as stream:
                    raw = stream.read(16 * 1024 * 1024 + 1)
                require(0 < len(raw) <= 16 * 1024 * 1024 and raw.endswith(b"\n"), "LEDGER_INCOMPLETE")
                entries = []
                previous = "0" * 64
                for sequence, line in enumerate(raw.splitlines(keepends=True)):
                    entry = strict_json(line)
                    require(canonical(entry) == line and entry["sequence"] == sequence
                            and entry["previous"] == previous, "LEDGER_CHAIN")
                    previous = digest(line)
                    entries.append(entry)
                require(entries[0]["kind"] == "GENESIS" and
                        entries[0]["election"] == self.election and
                        entries[0]["root_identity"] == self.identity, "LEDGER_ELECTION")
                anchor = {"sequence": len(entries) - 1, "digest": previous,
                          "root_identity": self.identity}
                require(witness.read() == anchor, "LEDGER_WITNESS_MISMATCH")
                yield jfd, entries, anchor
            finally:
                os.close(jfd)
        finally:
            os.close(lfd)

    def append(self, fd, entries, anchor, witness, fields):
        entry = dict(fields, sequence=len(entries), previous=anchor["digest"])
        data = canonical(entry)
        os.lseek(fd, 0, os.SEEK_END)
        write_all(fd, data)
        os.fsync(fd)
        os.fsync(self.fd)
        next_anchor = {"sequence": len(entries), "digest": digest(data),
                       "root_identity": self.identity}
        # Reservation reaches both stores before the first executor effect.
        require(witness.advance(anchor, next_anchor) == next_anchor, "WITNESS_ADVANCE_UNCERTAIN")
        entries.append(entry)
        anchor.clear()
        anchor.update(next_anchor)


PUBLIC_CODES = {"COMPLETE_FIXTURE", "HOLD_CONSUMED", "HOLD_INVALID_BUNDLE",
                "HOLD_WINDOW", "HOLD_CLOCK", "HOLD_RUNTIME", "HOLD_GATES",
                "HOLD_ADAPTER_UNAVAILABLE", "HOLD_RESULT", "HOLD_UNCERTAIN"}


class Controller:
    def __init__(self, ledger, witness, *, wall_clock, monotonic_clock=time.monotonic):
        self.ledger, self.witness = ledger, witness
        self.wall_clock, self.monotonic = wall_clock, monotonic_clock

    def _validate(self, bundle, authority, adapter, now):
        request, question, owner, bound = [bundle[k] for k in ("request", "question", "owner", "bound")]
        require(request["schema"] == "F6_REQUEST_CANDIDATE_V1", "HOLD_INVALID_BUNDLE")
        require(request["context"] == authority["context"], "HOLD_INVALID_BUNDLE")
        require(request["authority_slot"] == authority["slot"], "HOLD_INVALID_BUNDLE")
        require(question["request_sha256"] == owner["request_sha256"] ==
                bound["request_sha256"] == digest(canonical(request)), "HOLD_INVALID_BUNDLE")
        require(owner["question_sha256"] == bound["question_sha256"] == digest(canonical(question)),
                "HOLD_INVALID_BUNDLE")
        require(bound["owner_sha256"] == digest(canonical(owner)), "HOLD_INVALID_BUNDLE")
        require(owner["literal"] == "Assino" and owner["channel"] == "REGISTRO_PELA_FABLE",
                "HOLD_INVALID_BUNDLE")
        require(question["published_readback"] == "GET1_GET2_EXACT_UNEDITED" and
                owner["original_readback"] == "OWN_EXACT_UNEDITED", "HOLD_INVALID_BUNDLE")
        signed, published = instant(owner["signed_at_UTC"]), instant(question["published_UTC"])
        require(published <= signed < instant(request["start_UTC"]), "HOLD_INVALID_BUNDLE")
        require(authority["revoked"] is False and authority["accepted"] is True,
                "HOLD_INVALID_BUNDLE")
        require(request["operation"] == authority["operation"], "HOLD_INVALID_BUNDLE")
        require(type(request["budget_seconds"]) is int and 0 < request["budget_seconds"] <= 120,
                "HOLD_WINDOW")
        require(instant(request["start_UTC"]) <= now and
                now + timedelta(seconds=request["budget_seconds"])
                < instant(request["end_UTC"]), "HOLD_WINDOW")
        require(request["epoch"] == authority["epoch"] and request["session_date"] == authority["session_date"],
                "HOLD_INVALID_BUNDLE")
        require(bound["own_review"] == "ACCEPTED" and request["pins"] == authority["pins"],
                "HOLD_INVALID_BUNDLE")
        for value in request["pins"].values():
            sha(value)
        require(request["required_gates"] and
                all(bundle["gates"].get(k) == "OWN_COMPLETE" for k in request["required_gates"]),
                "HOLD_GATES")
        # Only explicit fixture adapters exist in r1. A production adapter requires
        # its own actual family ABI, source/registry/seal, proof and acceptance.
        require(authority["mode"] == "FIXTURE" and adapter is not None and
                adapter.mode == "FIXTURE" and adapter.operation == request["operation"],
                "HOLD_ADAPTER_UNAVAILABLE")
        require(adapter.recheck() == authority["pins"], "HOLD_RUNTIME")
        return request

    def invoke(self, authority, bundle, adapter=None):
        # The accepted authority defines the slot independently of malformed
        # request bytes. No changed nonce/BOUND can create another option.
        key = digest(canonical({"context": authority["context"], "slot": authority["slot"],
                                "epoch": authority["epoch"]}))
        with self.ledger.locked(self.witness) as (fd, entries, anchor):
            consumed = any(e.get("attempt_key") == key for e in entries)
            invocation = {"kind": "INVOCATION", "attempt_key": key,
                          "bundle_sha256": digest(canonical(bundle)),
                          "status": "HOLD_CONSUMED" if consumed else "RESERVED"}
            self.ledger.append(fd, entries, anchor, self.witness, invocation)
            if consumed:
                return {"verdict": "HOLD_CONSUMED", "effect_started": False}
            began_mono = self.monotonic()
            began_wall = instant(self.wall_clock())
            effect_started = False
            verdict = "HOLD_UNCERTAIN"
            try:
                request = self._validate(bundle, authority, adapter, began_wall)
                before = instant(self.wall_clock())
                elapsed = self.monotonic() - began_mono
                require(0 <= elapsed < request["budget_seconds"] and
                        abs((before - began_wall).total_seconds() - elapsed) <= 1,
                        "HOLD_CLOCK")
                self._validate(bundle, authority, adapter, before)
                effect_started = True
                result = adapter.run_once(request)
                finished = instant(self.wall_clock())
                elapsed = self.monotonic() - began_mono
                require(0 <= elapsed <= request["budget_seconds"] and
                        finished < instant(request["end_UTC"]) and
                        abs((finished - began_wall).total_seconds() - elapsed) <= 1,
                        "HOLD_CLOCK")
                require(result["schema"] == "F6_FIXTURE_RECEIPT_V1" and result["status"] == "COMPLETE"
                        and result["request_sha256"] == digest(canonical(request))
                        and result["context"] == request["context"], "HOLD_RESULT")
                verdict = "COMPLETE_FIXTURE"
            except Hold as error:
                verdict = str(error) if str(error) in PUBLIC_CODES else "HOLD_UNCERTAIN"
            except Exception:
                # Preserve the consumed reservation; do not expose exception data.
                verdict = "HOLD_UNCERTAIN"
            self.ledger.append(fd, entries, anchor, self.witness,
                               {"kind": "OUTCOME", "attempt_key": key,
                                "status": verdict, "effect_started": effect_started})
            return {"verdict": verdict, "effect_started": effect_started}


def reconcile_publication(prepared, rows, expected_author_id, context):
    """Read-only recovery of a possibly created POST; never sends another POST."""
    matches = [r for r in rows if r.get("body_sha256") == digest(prepared)]
    require(len(matches) == 1, "PUBLICATION_UNKNOWN_OR_AMBIGUOUS")
    row = matches[0]
    require(row["author_id"] == expected_author_id and row["context"] == context
            and row["created_at"] == row["updated_at"] and row["pages_complete"] is True
            and row["get1"] == row["get2"] == prepared, "PUBLICATION_READBACK")
    return {"verdict": "OWN_PUBLICATION_BYTES_ONLY", "id": row["id"],
            "body_sha256": digest(prepared), "executor_repeated": False}
