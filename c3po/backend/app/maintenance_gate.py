"""Cross-process admission barrier for a bounded, cooperative maintenance drain.

The installer owns two stable files on a shared filesystem. Applications only
open them read-only; flock provides the synchronization. A controller holds
admission exclusively before waiting for work to drain, and keeps both locks
until the maintenance action ends. Observation of an empty database is not a
substitute for this barrier. Callers must retain a lease for the FULL operation,
including any detached work, and reject new operations while admission is shut.

This module is a primitive, not a claim that every host workload participates.
"""
from __future__ import annotations

import fcntl
import os
import stat
import time
import uuid
import hashlib
from pathlib import Path
from threading import Lock
from contextlib import contextmanager
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterator

MODULE_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class MaintenanceBusy(RuntimeError):
    pass


_current: ContextVar[WorkLease | None] = ContextVar("maintenance_work", default=None)


def boot_identity() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def configured_directory() -> Path | None:
    value = os.environ.get("C3PO_MAINTENANCE_GATE_DIR")
    if value:
        return Path(value)
    if os.environ.get("C3PO_ENVIRONMENT") == "production":
        raise RuntimeError("Production maintenance admission is not configured")
    return None


def retain_work() -> WorkLease | None:
    parent = _current.get()
    directory = configured_directory()
    if parent is not None:
        try:
            return parent.retain()
        except RuntimeError:
            pass  # A copied context may outlive its original request/startup.
    return admit(directory) if directory else None


@contextmanager
def job() -> Iterator[bool]:
    """Admit one full operation, or yield False without starting its work."""
    try:
        lease = retain_work()
    except MaintenanceBusy:
        yield False
        return
    if lease is None:
        yield True
        return
    token = _current.set(lease)
    try:
        with lease:
            yield True
    finally:
        _current.reset(token)


@contextmanager
def startup_job() -> Iterator[None]:
    while True:
        with job() as admitted:
            if admitted:
                yield
                return
        time.sleep(1)


class MaintenanceExecutor(ThreadPoolExecutor):
    """Keep timed-out/orphaned futures admitted until actual completion."""
    def submit(self, fn, /, *args, **kwargs):
        lease = retain_work()
        def run():
            token = _current.set(lease)
            try:
                return fn(*args, **kwargs)
            finally:
                _current.reset(token)
        try:
            future = super().submit(run)
        except BaseException:
            if lease is not None:
                lease.close()
            raise
        if lease is not None:
            future.add_done_callback(lambda _: lease.close())
        return future


class MaintenanceMiddleware:
    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        with job() as admitted:
            if admitted:
                await self.app(scope, receive, send)
            elif scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1013})
            else:
                body = b'{"detail":"Maintenance in progress; retry shortly"}'
                await send({"type": "http.response.start", "status": 503,
                            "headers": [(b"content-type", b"application/json"), (b"retry-after", b"30")]})
                await send({"type": "http.response.body", "body": body})


def _open(directory: Path, name: str) -> int:
    if directory.is_symlink():
        raise ValueError("Maintenance directory must not be a symlink")
    path = directory / name
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        value = os.fstat(fd)
        current = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(value.st_mode) or value.st_nlink != 1
                or value.st_mode & 0o022
                or (value.st_dev, value.st_ino) != (current.st_dev, current.st_ino)):
            raise ValueError("Invalid maintenance lock file")
        return fd
    except BaseException:
        os.close(fd)
        raise


class _Work:
    def __init__(self, fd: int):
        self.fd = fd
        self.references = 1
        self.mutex = Lock()
        self.pid = os.getpid()


class WorkLease:
    """A live job; retain before scheduling a child, close on actual completion."""
    def __init__(self, work: _Work):
        self._work = work
        self._closed = False

    @property
    def active(self) -> bool:
        with self._work.mutex:
            return not self._closed and self._work.pid == os.getpid()

    def retain(self) -> WorkLease:
        with self._work.mutex:
            if self._closed or self._work.pid != os.getpid():
                raise RuntimeError("Cannot retain an expired or inherited work lease")
            self._work.references += 1
            return WorkLease(self._work)

    def close(self) -> None:
        with self._work.mutex:
            if self._closed:
                return
            if self._work.pid != os.getpid():
                raise RuntimeError("A work lease cannot be managed by a forked process")
            self._closed = True
            self._work.references -= 1
            if self._work.references == 0:
                os.close(self._work.fd)

    def __enter__(self) -> WorkLease:
        if self._closed:
            raise RuntimeError("Work lease already closed")
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def admit(directory: Path) -> WorkLease:
    gate = _open(directory, "admission.lock")
    work = None
    try:
        try:
            fcntl.flock(gate, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MaintenanceBusy("Maintenance is waiting for existing work") from None
        marker = directory / "reboot.pending"
        try:
            value = marker.read_text().strip()
        except FileNotFoundError:
            value = None
        if value is not None:
            # Persistent marker closes the gap between systemctl's acknowledgement
            # and actual shutdown. A new kernel boot automatically retires it.
            boot = boot_identity()
            try:
                uuid.UUID(value)
            except ValueError:
                raise MaintenanceBusy("Reboot marker needs reconciliation") from None
            if value == boot:
                raise MaintenanceBusy("Reboot has been requested")
        work = _open(directory, "work.lock")
        fcntl.flock(work, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return WorkLease(_Work(work))
    except BaseException:
        if work is not None:
            os.close(work)
        raise
    finally:
        os.close(gate)


class Drain:
    """Close admission first; try_drained never cancels or kills active work."""
    def __init__(self, directory: Path):
        self._gate = _open(directory, "admission.lock")
        self._work: int | None = None
        self._closed = False
        try:
            try:
                fcntl.flock(self._gate, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise MaintenanceBusy("Another admission or maintenance operation is active") from None
            self._work = _open(directory, "work.lock")
        except BaseException:
            os.close(self._gate)
            raise

    def try_drained(self) -> bool:
        if self._closed or self._work is None:
            raise RuntimeError("Drain already closed")
        try:
            fcntl.flock(self._work, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            if self._work is not None:
                os.close(self._work)
            os.close(self._gate)

    def __enter__(self) -> Drain:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
