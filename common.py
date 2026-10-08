"""Shared strict byte and filesystem contracts for the new server epoch.

No installation, authority election or operational invocation occurs on import.
The V2 model is intentionally distinct from the consumed October 5--9 models.
"""
import hashlib
import json
import os
import re
import stat
from datetime import date, datetime, timezone
from pathlib import Path


class Hold(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise Hold(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def hash_value(value):
    return digest(canonical(value))


def sha(value):
    need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "HASH_FORMAT")
    need(value not in {"0" * 64, digest(b""), digest(b"{}"), digest(b"null")}, "HASH_SENTINEL")
    return value


def strict(raw, limit=1024 * 1024):
    need(type(raw) is bytes and 0 < len(raw) <= limit, "JSON_SIZE")
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    def invalid(_):
        raise Hold("JSON_NONFINITE")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    except (UnicodeError, ValueError) as error:
        if isinstance(error, Hold):
            raise
        raise Hold("JSON_INVALID") from None


def fields(value, keys, code):
    need(type(value) is dict and set(value) == set(keys), code)
    return value


def instant(value):
    try:
        need(type(value) is str, "TIME_FORMAT")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        need(result.tzinfo is not None, "TIME_NAIVE")
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise Hold("TIME_FORMAT") from None


def context(value):
    fields(value, ("model", "epoch", "session", "lane", "release_sha256"), "CONTEXT_FIELDS")
    need(value["model"] == "SERVER_EPOCH_V2", "CONTEXT_MODEL")
    need(type(value["epoch"]) is str and re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{7,95}", value["epoch"]), "CONTEXT_EPOCH")
    need(value["epoch"] != "R2D2-V2-SHADOW-2026-10-05", "CONSUMED_EPOCH")
    try:
        day = date.fromisoformat(value["session"])
        need(day.isoformat() == value["session"] and day >= date(2026, 10, 12), "CONSUMED_SESSION")
    except (TypeError, ValueError):
        raise Hold("CONTEXT_SESSION") from None
    need(value["lane"] in ("P", "S", "POST", "AM", "CAPACITY"), "CONTEXT_LANE")
    sha(value["release_sha256"])
    return value


def snapshot(st):
    return {"device": st.st_dev, "inode": st.st_ino, "uid": st.st_uid,
            "gid": st.st_gid, "mode": stat.S_IMODE(st.st_mode),
            "nlink": st.st_nlink, "size": st.st_size,
            "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns}


class PinnedDirectory:
    """Descriptors and before/after stat checks; no resolve-through-link acceptance.

    A parent may be a sticky temporary directory in fixtures. Production runtime
    separately pins every ancestor and rejects writable non-sticky ancestors.
    """
    def __init__(self, path, *, uid=None, mode=0o700, expected=None):
        self.path = Path(path).absolute()
        self.uid = os.getuid() if uid is None else uid
        for parent in (self.path, *self.path.parents):
            need(not stat.S_ISLNK(parent.lstat().st_mode), "ANCESTOR_LINK")
        self.fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        st = os.fstat(self.fd)
        need(st.st_uid == self.uid and stat.S_IMODE(st.st_mode) == mode, "ROOT_PERMISSION")
        self.identity = {k: snapshot(st)[k] for k in ("device", "inode", "uid", "gid", "mode")}
        if expected is not None:
            need(self.identity == expected, "ROOT_IDENTITY")

    def close(self):
        os.close(self.fd)

    def recheck(self):
        a, b = os.fstat(self.fd), self.path.lstat()
        need(not stat.S_ISLNK(b.st_mode) and a.st_dev == b.st_dev and a.st_ino == b.st_ino,
             "ROOT_REPLACED")
        need({k: snapshot(a)[k] for k in self.identity} == self.identity, "ROOT_CHANGED")

    @staticmethod
    def name(name):
        need(type(name) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", name)
             and name not in (".", ".."), "FILE_NAME")
        return name

    def read(self, name, *, pin=None, limit=1024 * 1024, modes=(0o400, 0o444, 0o600)):
        self.name(name); self.recheck()
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == self.uid
                 and stat.S_IMODE(before.st_mode) in modes and 0 < before.st_size <= limit,
                 "FILE_PERMISSION_OR_SIZE")
            chunks = []; left = limit + 1
            while left:
                chunk = os.read(fd, min(65536, left))
                if not chunk: break
                chunks.append(chunk); left -= len(chunk)
            raw = b"".join(chunks)
            need(0 < len(raw) <= limit and snapshot(before) == snapshot(os.fstat(fd)), "FILE_CHANGED")
            named = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            need(snapshot(named) == snapshot(before), "FILE_REPLACED")
            if pin is not None: need(digest(raw) == sha(pin), "FILE_HASH")
            self.recheck()
            return raw
        finally:
            os.close(fd)

    def exists(self, name):
        self.name(name); self.recheck()
        try:
            os.stat(name, dir_fd=self.fd, follow_symlinks=False)
            return True
        except FileNotFoundError:
            return False

    def create(self, name, raw):
        self.name(name); self.recheck()
        need(type(raw) is bytes and 0 < len(raw) <= 1024 * 1024, "OUTPUT_SIZE")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            need(os.fstat(fd).st_nlink == 1, "OUTPUT_LINK")
            view = memoryview(raw)
            while view:
                count = os.write(fd, view); need(count > 0, "OUTPUT_UNCERTAIN"); view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        need(self.read(name, pin=digest(raw), modes=(0o600,)) == raw, "OUTPUT_READBACK")
        return digest(raw)


def linked_receipt(raw, ctx, *, operation=None, request_sha256=None):
    value = strict(raw)
    need(value.get("schema") == "SERVER_FAMILY_RECEIPT_V2" and value.get("context") == context(ctx)
         and value.get("status") == "COMPLETE", "PREDECESSOR_INCOMPLETE")
    need(instant(value["started_UTC"]) <= instant(value["finished_UTC"]), "PREDECESSOR_TIME")
    if operation is not None: need(value["operation"] == operation, "PREDECESSOR_OPERATION")
    if request_sha256 is not None: need(value["request_sha256"] == sha(request_sha256), "PREDECESSOR_REQUEST")
    sha(value["request_sha256"])
    return value
