"""Private immutable files for the opt-in causal emitter. No I/O on import.

The configured absolute root must already exist, be owned by this user and be
private. Directory traversal uses file descriptors and refuses symlinks.
Publication is exclusive and durable; identical recovery never uses file mtime
as a timestamp. This module alone does not attest audit events or input coverage.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import os
from pathlib import Path
import stat
from uuid import uuid4

from .r2d2_v2_store import ShadowIntegrityError, canonical, validate_epoch

MAX_BYTES = 64 * 1024 * 1024
PUBLIC_FIELDS = {"schema", "epoch", "session", "manifest_sha", "amendment_sha",
    "list_sha256", "n_cut", "commitment_sha256", "build_audit_event_id", "built_at",
    "registry_sha256", "daily_contract_sha256", "counts", "coverage"}


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ShadowIntegrityError(code)


def _private(fd: int, *, directory: bool) -> os.stat_result:
    info = os.fstat(fd)
    _require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
             and info.st_uid == os.geteuid() and not info.st_mode & 0o077,
             "CAUSAL_FILE_NOT_PRIVATE")
    if not directory:
        _require(info.st_nlink == 1, "CAUSAL_FILE_HARDLINK")
    return info


@contextmanager
def _directory(root: Path, parts: tuple[str, ...]):
    root = Path(root)
    _require(root.is_absolute() and ".." not in root.parts, "CAUSAL_ROOT_INVALID")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root.anchor, flags)
    try:
        for name in root.parts[1:]:
            child = os.open(name, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        _private(fd, directory=True)
        for name in parts:
            _require(bool(name) and name not in (".", "..") and "/" not in name, "CAUSAL_PATH_INVALID")
            try:
                os.mkdir(name, mode=0o700, dir_fd=fd)
                os.fsync(fd)
            except FileExistsError:
                pass
            child = os.open(name, flags, dir_fd=fd)
            try:
                _private(child, directory=True)
            except Exception:
                os.close(child)
                raise
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _same_file(fd: int, leaf: str, data: bytes) -> None:
    file_fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = _private(file_fd, directory=False)
        _require(before.st_size == len(data), "CAUSAL_FILE_CONFLICT")
        chunks, remaining = [], len(data) + 1
        while remaining:
            chunk = os.read(file_fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(file_fd)
        current = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
        unchanged = all(getattr(before, key) == getattr(after, key) for key in
            ("st_ino", "st_dev", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode", "st_uid", "st_nlink"))
        _require(b"".join(chunks) == data and unchanged
                 and (current.st_ino, current.st_dev) == (after.st_ino, after.st_dev), "CAUSAL_FILE_CONFLICT")
        os.fsync(file_fd)
    finally:
        os.close(file_fd)


def _atomic_bytes(root: Path, parts: tuple[str, ...], data: bytes) -> str:
    if not parts:
        raise ShadowIntegrityError("CAUSAL_PATH_INVALID")
    _require(isinstance(data, bytes) and 0 < len(data) <= MAX_BYTES,
             "CAUSAL_FILE_SIZE_LIMIT")
    leaf = parts[-1]
    _require(bool(leaf) and leaf not in (".", "..") and "/" not in leaf, "CAUSAL_PATH_INVALID")
    with _directory(root, parts[:-1]) as fd:
        temp = ".causal-" + uuid4().hex + ".tmp"
        file_fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            with os.fdopen(file_fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp, leaf, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            except FileExistsError:
                _same_file(fd, leaf, data)
        finally:
            os.unlink(temp, dir_fd=fd)
        os.fsync(fd)
    return "/".join(parts)


class FileRelaySink:
    """Durable private relay publication; publishes only aggregate metadata.

    The root is the agreed relay channel, not the collector's spool. The
    receipt references its relative path, keeping host paths out of metadata.
    """
    def __init__(self, root: Path):
        self.root = root

    def __call__(self, artifact: dict) -> tuple[str, str]:
        _require(set(artifact) == PUBLIC_FIELDS and artifact["schema"] == "V2_CAUSAL_LIST_PUBLICATION_V1",
                 "CAUSAL_PUBLIC_FIELDS")
        epoch = artifact["epoch"]
        validate_epoch(epoch)
        day = date.fromisoformat(artifact["session"])
        _require(day.isoformat() == artifact["session"], "CAUSAL_SESSION_INVALID")
        reference = _atomic_bytes(self.root, ("causal_publications", epoch, day.isoformat() + ".json"), canonical(artifact))
        return "relay", reference


def write_private_envelope(root: Path, envelope: dict) -> str:
    """Store an envelope returned and validated by the emitter, never overwrite.

    This is only a filesystem primitive. It cannot replace the collector's
    independent validation or fabricate the missing publication/audit facts.
    """
    _require(set(envelope) == {"commitment", "audit_receipt", "publication_receipt"}, "CAUSAL_ENVELOPE_FIELDS")
    item = envelope["commitment"]
    epoch, day = item["epoch"], date.fromisoformat(item["session"])
    validate_epoch(epoch)
    _require(day.isoformat() == item["session"], "CAUSAL_SESSION_INVALID")
    return _atomic_bytes(root, ("causal_list", epoch, day.isoformat() + ".json"), canonical(envelope))
