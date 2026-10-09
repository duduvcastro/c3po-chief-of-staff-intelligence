"""Offline candidate: finite, pinned Python transport for L12 Services.execute.

No operational registry, authority, receipt ABI or physical transport is supplied.
The caller's persistent L12 ledger consumes the attempt before this adapter.
All injected callbacks run in the bounded worker, including receipt verification.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import threading
import time
import types
from typing import Callable

MAX_SOURCE = 1024 * 1024
MAX_OUTPUT = 1024 * 1024
MAX_RECEIPT = 65536
MAX_PACKET = 100000
MAX_OPERATIONS = 64
TICK = 0.02


class RunnerError(RuntimeError):
    def __init__(self, code: str, *, uncertain: bool = False):
        self.code = code
        self.uncertain = uncertain
        # No child bytes, paths, credentials or exception strings in errors.
        super().__init__(code)


def need(ok, code, *, uncertain=False):
    if not ok:
        raise RunnerError(code, uncertain=uncertain)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(value):
    return (type(value) is str and len(value) == 64 and value != '0' * 64
            and all(c in '0123456789abcdef' for c in value))


def instant(value):
    need(isinstance(value, datetime) and value.tzinfo is not None
         and value.utcoffset() is not None, 'UTC_CLOCK_INVALID')
    return value.astimezone(timezone.utc)


def mono(value):
    need(type(value) in (int, float) and math.isfinite(value), 'MONOTONIC_CLOCK_INVALID')
    return float(value)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'


def deadline_guard(invocation, started, mark, last_mono, now, current):
    """Pure deadline predicate; physical clocks in the parent are stdlib only."""
    now, current = instant(now), mono(current)
    need(current >= last_mono and current >= mark, 'MONOTONIC_CLOCK_REGRESSED', uncertain=True)
    need(abs((now - started).total_seconds() - (current - mark)) <= 2,
         'CLOCK_DISCONTINUITY', uncertain=True)
    remaining = min((instant(invocation.deadline_utc) - now).total_seconds(),
                    mono(invocation.deadline_monotonic) - current)
    need(remaining > 0, 'RUNNER_DEADLINE', uncertain=True)
    return now, current, remaining


def directory_identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode))


def file_identity(info):
    return directory_identity(info) + (info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _canonical_path(path):
    need(type(path) is str and os.path.isabs(path) and '\x00' not in path
         and str(Path(path)) == path and '..' not in Path(path).parts, 'PATH_NOT_CANONICAL')


def _parents(path):
    # A symlink in an ancestor is not silently resolved into a different root.
    for parent in reversed(Path(path).parents):
        info = os.lstat(parent)
        need(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), 'ANCESTOR_CHANGED')


@dataclass(frozen=True)
class DirectoryPin:
    path: str
    identity: tuple[int, int, int, int, int]

    def open(self):
        _canonical_path(self.path)
        _parents(self.path)
        fd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            named = os.lstat(self.path)
            need(directory_identity(info) == self.identity == directory_identity(named)
                 and stat.S_ISDIR(info.st_mode) and self.identity[2] == os.getuid()
                 and self.identity[4] == 0o700, 'CWD_IDENTITY_CHANGED')
            return fd
        except BaseException:
            os.close(fd)
            raise


@dataclass(frozen=True)
class ExecutablePin:
    path: str
    identity: tuple[int, int, int, int, int, int, int, int, int]
    sha256: str

    def open(self):
        _canonical_path(self.path)
        _parents(self.path)
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and file_identity(before) == self.identity
                 and before.st_mode & 0o111 and not before.st_mode & 0o022
                 and before.st_uid in (0, os.getuid()) and pin(self.sha256), 'EXECUTABLE_IDENTITY_CHANGED')
            hasher = hashlib.sha256()
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
            need(hasher.hexdigest() == self.sha256
                 and file_identity(os.fstat(fd)) == self.identity
                 and file_identity(os.lstat(self.path)) == self.identity, 'EXECUTABLE_PIN_CHANGED')
            os.lseek(fd, 0, os.SEEK_SET)
            return fd
        except BaseException:
            os.close(fd)
            raise


@dataclass(frozen=True)
class Command:
    operation: str
    context: tuple[str, str, str, str]
    request_sha256: str
    bound_sha256: str
    argv: tuple[str, ...]
    source: bytes
    source_sha256: str
    stdin_sha256: str
    env: tuple[tuple[str, str], ...]
    cwd: DirectoryPin
    python: ExecutablePin
    current_pins: tuple[tuple[str, str], ...]
    stdout_limit: int
    stderr_limit: int
    execution_mode: str

    def body(self):
        return {'operation': self.operation, 'context': self.context,
                'request_sha256': self.request_sha256, 'bound_sha256': self.bound_sha256,
                'argv': self.argv, 'source_sha256': self.source_sha256,
                'stdin_sha256': self.stdin_sha256, 'env': self.env,
                'cwd': {'path': self.cwd.path, 'identity': self.cwd.identity},
                'python': {'path': self.python.path, 'identity': self.python.identity,
                           'sha256': self.python.sha256},
                'current_pins': self.current_pins, 'stdout_limit': self.stdout_limit,
                'stderr_limit': self.stderr_limit, 'execution_mode': self.execution_mode}

    def validate(self):
        need(type(self.cwd) is DirectoryPin and type(self.python) is ExecutablePin
             and type(self.cwd.path) is str and type(self.python.path) is str
             and type(self.cwd.identity) is tuple and len(self.cwd.identity) == 5
             and type(self.python.identity) is tuple and len(self.python.identity) == 9
             and all(type(x) is int for x in self.cwd.identity + self.python.identity)
             and pin(self.python.sha256), 'REGISTRY_PHYSICAL_PINS_INVALID')
        need(type(self.operation) is str and self.operation and len(self.operation) <= 100,
             'REGISTRY_OPERATION_INVALID')
        need(type(self.context) is tuple and len(self.context) == 4
             and all(type(x) is str and 0 < len(x) <= 100 for x in self.context), 'REGISTRY_CONTEXT_INVALID')
        need(pin(self.request_sha256) and pin(self.bound_sha256), 'REGISTRY_CONTEXT_PIN_INVALID')
        # This candidate supports only Python source on stdin. No shell, Docker,
        # SSH or historical executable ABI is guessed from an operation name.
        need(type(self.argv) is tuple and 4 <= len(self.argv) <= 100
             and all(type(x) is str and '\x00' not in x and len(x) <= 4096 for x in self.argv)
             and self.argv[:4] == (self.python.path, '-I', '-B', '-'),
             'REGISTRY_ARGV_INVALID')
        need(type(self.source) is bytes and 0 < len(self.source) <= MAX_SOURCE
             and pin(self.source_sha256) and pin(self.stdin_sha256)
             and digest(self.source) == self.source_sha256 == self.stdin_sha256,
             'REGISTRY_SOURCE_INPUT_PIN_CHANGED')
        need(type(self.env) is tuple and len(self.env) <= 16
             and all(type(row) is tuple and len(row) == 2 and all(type(x) is str for x in row)
                     for row in self.env)
             and len({k for k, _ in self.env}) == len(self.env)
             and all(k in {'PATH', 'LANG', 'LC_ALL', 'TZ'} and type(v) is str
                     and '\x00' not in v and len(v) <= 4096 for k, v in self.env), 'REGISTRY_ENV_INVALID')
        need(type(self.current_pins) is tuple and 0 < len(self.current_pins) <= 64
             and all(type(row) is tuple and len(row) == 2 and all(type(x) is str for x in row)
                     for row in self.current_pins)
             and len({k for k, _ in self.current_pins}) == len(self.current_pins)
             and all(type(k) is str and k and pin(v) for k, v in self.current_pins), 'REGISTRY_CURRENT_PINS_INVALID')
        need(all(type(n) is int and 0 < n <= MAX_OUTPUT
                 for n in (self.stdout_limit, self.stderr_limit)), 'REGISTRY_OUTPUT_LIMIT_INVALID')
        need(type(self.execution_mode) is str
             and self.execution_mode in ('FD_EXEC_LINUX', 'NAMED_EXEC_POSIX'), 'EXECUTION_MODE_UNAVAILABLE')


@dataclass(frozen=True)
class Registry:
    owner_uid: int
    commands: tuple[Command, ...]
    callback_pins: tuple[tuple[str, str, str], ...]
    containment: str = 'OWN_SESSION'

    def raw(self):
        # Public serialization is also pure/finite: do not call an overridden
        # body/validate method before the process-budget worker exists.
        need(type(self.commands) is tuple and 0 < len(self.commands) <= MAX_OPERATIONS
             and all(type(c) is Command for c in self.commands), 'REGISTRY_NOT_FINITE_UNIQUE')
        for command in self.commands:
            command.validate()
        self._callback_shape()
        need(type(self.owner_uid) is int and type(self.containment) is str
             and self.containment in ('OWN_SESSION', 'INHERITED_OUTER_GROUP'), 'REGISTRY_CONTAINMENT_INVALID')
        return canonical({'schema': 'L12_FINITE_PYTHON_REGISTRY_CANDIDATE_V1',
                          'owner_uid': self.owner_uid,
                          'callback_pins': self.callback_pins,
                          'containment': self.containment,
                          'commands': [c.body() for c in self.commands]})

    def _callback_shape(self):
        stages = ('AUTHORITY', 'RUNTIME', 'CURRENT_PINS', 'RECEIPT_ABI', 'RECEIPT_PROVENANCE')
        need(type(self.callback_pins) is tuple and len(self.callback_pins) == 5
             and all(type(x) is tuple and len(x) == 3 and all(type(v) is str for v in x)
                     for x in self.callback_pins)
             and tuple(x[0] for x in self.callback_pins) == stages
             and all(x[1] and len(x[1]) <= 200 and pin(x[2]) for x in self.callback_pins),
             'REGISTRY_CALLBACK_PINS_INVALID')

    def validate(self, expected_sha256):
        need(os.name == 'posix' and hasattr(os, 'fork'), 'POSIX_WORKER_UNAVAILABLE')
        need(type(self.owner_uid) is int and self.owner_uid == os.getuid(), 'REGISTRY_OWNER_CHANGED')
        need(type(self.commands) is tuple and 0 < len(self.commands) <= MAX_OPERATIONS
             and all(type(c) is Command and type(c.cwd) is DirectoryPin and type(c.python) is ExecutablePin
                     for c in self.commands)
             , 'REGISTRY_NOT_FINITE_UNIQUE')
        for command in self.commands:
            command.validate()
        need(len({c.operation for c in self.commands}) == len(self.commands), 'REGISTRY_NOT_FINITE_UNIQUE')
        need(type(self.containment) is str and self.containment in ('OWN_SESSION', 'INHERITED_OUTER_GROUP'),
             'REGISTRY_CONTAINMENT_INVALID')
        self._callback_shape()
        need(pin(expected_sha256) and digest(self.raw()) == expected_sha256, 'REGISTRY_PIN_CHANGED')


@dataclass(frozen=True)
class Binding:
    identity: str
    source_sha256: str
    callback: Callable

    def validate(self):
        need(type(self.identity) is str and self.identity and len(self.identity) <= 200
             and pin(self.source_sha256) and callable(self.callback), 'CALLBACK_BINDING_UNAVAILABLE')


@dataclass(frozen=True)
class Approval:
    stage: str
    registry_sha256: str
    command_sha256: str
    context: tuple[str, str, str, str]
    current_pins: tuple[tuple[str, str], ...]
    observed_at: datetime
    valid_until: datetime


@dataclass(frozen=True)
class ReceiptView:
    raw: bytes
    role: str
    context: tuple[str, str, str, str]
    status: str
    completed_at: datetime


@dataclass(frozen=True)
class Transport:
    stdout: bytes
    stderr: bytes
    returncode: int
    started_at: datetime
    completed_at: datetime
    registry_sha256: str
    command_sha256: str


class BoundedRunner:
    def __init__(self, registry, registry_sha256, *, authority_verifier, runtime_verifier,
                 pins_verifier, receipt_decoder, receipt_verifier):
        # These bindings require independent real source/runtime review; their
        # declarations here are not a signature, measurement or approval.
        self.registry, self.registry_sha256 = registry, registry_sha256
        self.bindings = (authority_verifier, runtime_verifier, pins_verifier, receipt_decoder, receipt_verifier)
        self._claims, self._lock = set(), threading.Lock()

    def _bindings_guard(self):
        need(type(self.bindings) is tuple and len(self.bindings) == 5
             and all(type(b) is Binding for b in self.bindings), 'CALLBACK_BINDING_UNAVAILABLE')
        for binding, registered in zip(self.bindings, self.registry.callback_pins):
            need(type(binding) is Binding, 'CALLBACK_BINDING_UNAVAILABLE')
            binding.validate()
            need((binding.identity, binding.source_sha256) == registered[1:], 'CALLBACK_PIN_CHANGED')

    def _guard(self, invocation, started, mark, last_mono):
        return deadline_guard(invocation, started, mark, last_mono,
                              datetime.now(timezone.utc), time.monotonic())

    def _approve(self, binding, stage, invocation, command, started, mark, last):
        now, last, _ = self._guard(invocation, started, mark, last)
        approval = binding.callback(invocation, command, self.registry_sha256, now)
        after, last, _ = self._guard(invocation, started, mark, last)
        need(isinstance(approval, Approval) and approval.stage == stage
             and approval.registry_sha256 == self.registry_sha256
             and approval.command_sha256 == digest(canonical(command.body()))
             and approval.context == command.context and approval.current_pins == command.current_pins
             and instant(approval.observed_at) <= after < instant(approval.valid_until)
             and (after - instant(approval.observed_at)).total_seconds() <= 5,
             'REAL_APPROVAL_INVALID', uncertain=True)
        return approval, last

    def _transport(self, invocation, command, bin_fd, started, mark, last):
        now, last, _ = self._guard(invocation, started, mark, last)
        # Inherit the worker's own session/group. The parent's final cleanup kills
        # that entire group, including descendants that retained its group.
        if command.execution_mode == 'FD_EXEC_LINUX':
            need(os.path.isdir('/proc/self/fd'), 'FD_EXEC_LINUX_UNAVAILABLE', uncertain=True)
            executable = f'/proc/self/fd/{bin_fd}'
        else:
            # Explicitly authorized named-path mode only, never an automatic
            # fallback when Linux FD execution is unavailable. A physical
            # immutable binary/root topology remains an external prerequisite.
            executable = command.python.path
        process = subprocess.Popen(command.argv, executable=executable,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=dict(command.env), shell=False, close_fds=True, pass_fds=(bin_fd,))
        selector = selectors.DefaultSelector()
        for stream, label in ((process.stdin, 'in'), (process.stdout, 'out'), (process.stderr, 'err')):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_WRITE if label == 'in' else selectors.EVENT_READ, label)
        offset, stdout, stderr = 0, bytearray(), bytearray()
        try:
            while selector.get_map():
                _, last, remaining = self._guard(invocation, started, mark, last)
                for key, _ in selector.select(min(TICK, remaining)):
                    stream, label = key.fileobj, key.data
                    if label == 'in':
                        try:
                            offset += os.write(stream.fileno(), command.source[offset:offset + 65536])
                        except BrokenPipeError:
                            need(False, 'CHILD_INPUT_INCOMPLETE', uncertain=True)
                        if offset == len(command.source):
                            selector.unregister(stream)
                            stream.close()
                    else:
                        chunk = os.read(stream.fileno(), 65536)
                        if not chunk:
                            selector.unregister(stream)
                            stream.close()
                            continue
                        output, limit = (stdout, command.stdout_limit) if label == 'out' else (stderr, command.stderr_limit)
                        need(len(output) + len(chunk) <= limit, 'CHILD_OUTPUT_LIMIT', uncertain=True)
                        output.extend(chunk)
            while process.poll() is None:
                _, last, remaining = self._guard(invocation, started, mark, last)
                time.sleep(min(TICK, remaining))
            completed, last, _ = self._guard(invocation, started, mark, last)
            need(process.returncode == 0, 'CHILD_NONZERO_EXIT', uncertain=True)
            return Transport(bytes(stdout), bytes(stderr), process.returncode, now, completed,
                             self.registry_sha256, digest(canonical(command.body()))), last
        finally:
            selector.close()
            for stream in (process.stdin, process.stdout, process.stderr):
                if not stream.closed:
                    stream.close()
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass

    def _worker(self, invocation, command, started, mark, write_fd):
        cwd_fd = bin_fd = None
        try:
            inherited = self.registry.containment == 'INHERITED_OUTER_GROUP'
            if inherited:
                # Only the independently reviewed one-operation outer watchdog
                # may own this group. It must kill the group before its terminal
                # ledger write and before any next operation.
                need(os.getppid() == os.getpgrp() == os.getsid(0), 'OUTER_GROUP_UNAVAILABLE', uncertain=True)
            else:
                os.setsid()
            expected_group, expected_session = os.getpgrp(), os.getsid(0)
            # A separate kernel timer prevents a parked group owner from
            # surviving indefinitely if its parent disappears during cleanup.
            # A small cleanup margin gives the parent the first deadline verdict.
            def emergency_group_stop(_signal, _frame):
                if inherited:
                    os.kill(os.getpid(), signal.SIGKILL)
                else:
                    os.killpg(os.getpgrp(), signal.SIGKILL)
            signal.signal(signal.SIGALRM, emergency_group_stop)
            _, _, remaining = self._guard(invocation, started, mark, mark)
            signal.setitimer(signal.ITIMER_REAL, remaining + 0.25)
            self.registry.validate(self.registry_sha256)
            self._bindings_guard()
            cwd_fd, bin_fd = command.cwd.open(), command.python.open()
            os.fchdir(cwd_fd)
            last = mark
            approvals = []
            for binding, stage in zip(self.bindings[:3], ('AUTHORITY', 'RUNTIME', 'CURRENT_PINS')):
                approval, last = self._approve(binding, stage, invocation, command, started, mark, last)
                approvals.append(approval)
            # Pure pins/time/freshness checks follow every callback and precede
            # the only child invocation. No second command/retry exists.
            self.registry.validate(self.registry_sha256)
            self._bindings_guard()
            need(directory_identity(os.fstat(cwd_fd)) == command.cwd.identity
                 == directory_identity(os.lstat(command.cwd.path)), 'CWD_IDENTITY_CHANGED')
            need(file_identity(os.fstat(bin_fd)) == command.python.identity
                 == file_identity(os.lstat(command.python.path)), 'EXECUTABLE_IDENTITY_CHANGED')
            now, last, _ = self._guard(invocation, started, mark, last)
            need(os.getpgrp() == expected_group and os.getsid(0) == expected_session,
                 'PROCESS_GROUP_CHANGED', uncertain=True)
            need(all(instant(a.observed_at) <= now < instant(a.valid_until)
                     and (now - instant(a.observed_at)).total_seconds() <= 5 for a in approvals),
                 'REAL_APPROVAL_EXPIRED', uncertain=True)
            transport, last = self._transport(invocation, command, bin_fd, started, mark, last)
            view = self.bindings[3].callback(transport, invocation, command)
            now, last, _ = self._guard(invocation, started, mark, last)
            need(isinstance(view, ReceiptView) and type(view.raw) is bytes
                 and 0 < len(view.raw) <= MAX_RECEIPT and view.role == command.operation
                 and view.context == command.context and view.status == 'COMPLETE'
                 and started <= instant(view.completed_at) <= now,
                 'RECEIPT_ABI_UNVERIFIED', uncertain=True)
            accepted = self.bindings[4].callback(view, transport, invocation, command)
            self._guard(invocation, started, mark, last)
            need(accepted is True, 'RECEIPT_PROVENANCE_UNVERIFIED', uncertain=True)
            packet = {'status': 'VERIFIED_ORIGINAL_ONLY', 'raw': base64.b64encode(view.raw).decode('ascii'),
                      'role': view.role, 'context': view.context, 'completed_at': instant(view.completed_at).isoformat()}
        except BaseException as error:
            packet = {'status': 'UNCERTAIN', 'code': error.code if isinstance(error, RunnerError) else 'WORKER_UNCERTAIN'}
        finally:
            for fd in (cwd_fd, bin_fd):
                if fd is not None:
                    os.close(fd)
        raw = canonical(packet)
        if len(raw) <= MAX_PACKET:
            offset = 0
            while offset < len(raw):
                offset += os.write(write_fd, raw[offset:])
        os.close(write_fd)
        # Keep the group owner alive until the parent kills the entire group.
        # An already exited empty group can yield EPERM under a local sandbox,
        # and cannot establish successful descendant cleanup. Parent cleanup is
        # unconditional for success, error and deadline.
        while True:
            signal.pause()

    @staticmethod
    def _cleanup(pid, containment='OWN_SESSION'):
        group_uncertain = False
        try:
            if containment == 'INHERITED_OUTER_GROUP':
                os.kill(pid, signal.SIGKILL)
            else:
                os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except PermissionError:
            # Cannot certify full group termination by only killing the worker.
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            group_uncertain = True
        # Never an unbounded wait if the OS cannot report termination.
        until = time.monotonic() + 0.5
        while time.monotonic() < until:
            try:
                waited, _ = os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                need(not group_uncertain, 'GROUP_CLEANUP_UNCERTAIN', uncertain=True)
                return
            if waited == pid:
                need(not group_uncertain, 'GROUP_CLEANUP_UNCERTAIN', uncertain=True)
                return
            time.sleep(0.005)
        raise RunnerError('WORKER_REAP_UNCERTAIN', uncertain=True)

    def run(self, invocation):
        cls = type(invocation)
        expected_fields = ('operation', 'context', 'request_sha256', 'bound_sha256',
                           'deadline_utc', 'deadline_monotonic', 'original_receipts')
        need(type(cls) is type and cls.__bases__ == (object,)
             and hasattr(cls, '__dataclass_fields__') and cls.__dataclass_params__.frozen
             and tuple(cls.__dataclass_fields__) == expected_fields
             and '__getattribute__' not in cls.__dict__ and '__getattr__' not in cls.__dict__
             and type(cls.__dict__.get('__dict__')) is types.GetSetDescriptorType
             and all(name not in cls.__dict__ or type(cls.__dict__[name]) in (tuple, str, int, float)
                     for name in expected_fields), 'FIXED_CORE_INVOCATION_REQUIRED')
        op, context = getattr(invocation, 'operation', None), getattr(invocation, 'context', None)
        need(type(op) is str and type(context) is tuple and len(context) == 4
             and all(type(x) is str and x for x in context), 'INVOCATION_SCOPE_UNIDENTIFIABLE')
        with self._lock:
            key = context + (op,)
            need(key not in self._claims, 'ATTEMPT_ALREADY_CONSUMED')
            self._claims.add(key)
        need(threading.active_count() == 1, 'POSIX_FORK_REQUIRES_SINGLE_THREAD')
        need(type(self.registry) is Registry, 'REGISTRY_TYPE_INVALID')
        self.registry.validate(self.registry_sha256)
        if self.registry.containment == 'INHERITED_OUTER_GROUP':
            need(os.getpid() == os.getpgrp() == os.getsid(0), 'OUTER_GROUP_UNAVAILABLE')
        self._bindings_guard()
        matches = [c for c in self.registry.commands if c.operation == op]
        need(len(matches) == 1, 'OPERATION_NOT_IN_REGISTRY')
        command = matches[0]
        need(context == command.context and invocation.request_sha256 == command.request_sha256
             and invocation.bound_sha256 == command.bound_sha256, 'INVOCATION_CONTEXT_PIN_CHANGED')
        need(not hasattr(invocation, 'argv') and not hasattr(invocation, 'stdin')
             and not hasattr(invocation, 'env'), 'INVOCATION_OVERRIDE_FORBIDDEN')
        need(type(invocation.deadline_utc) is datetime and type(invocation.deadline_utc.tzinfo) is timezone
             and type(invocation.deadline_monotonic) in (int, float), 'INVOCATION_CLOCK_PRIMITIVES_REQUIRED')
        started, mark = datetime.now(timezone.utc), time.monotonic()
        self._guard(invocation, started, mark, mark)
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            self._worker(invocation, command, started, mark, write_fd)
            os._exit(1)
        os.close(write_fd)
        os.set_blocking(read_fd, False)
        selector = selectors.DefaultSelector()
        selector.register(read_fd, selectors.EVENT_READ)
        data, last = bytearray(), mark
        try:
            while True:
                _, last, remaining = self._guard(invocation, started, mark, last)
                if not selector.select(min(TICK, remaining)):
                    continue
                chunk = os.read(read_fd, 65536)
                if not chunk:
                    break
                need(len(data) + len(chunk) <= MAX_PACKET, 'WORKER_PACKET_LIMIT', uncertain=True)
                data.extend(chunk)
            self._guard(invocation, started, mark, last)
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    need(key not in result, 'WORKER_PACKET_INVALID', uncertain=True)
                    result[key] = value
                return result
            packet = json.loads(bytes(data), object_pairs_hook=unique)
            need(type(packet) is dict, 'WORKER_PACKET_INVALID', uncertain=True)
            if packet.get('status') != 'VERIFIED_ORIGINAL_ONLY':
                allowed = {'RUNNER_DEADLINE', 'MONOTONIC_CLOCK_REGRESSED', 'CLOCK_DISCONTINUITY',
                           'REAL_APPROVAL_INVALID', 'REAL_APPROVAL_EXPIRED', 'CHILD_INPUT_INCOMPLETE',
                           'CHILD_OUTPUT_LIMIT', 'CHILD_NONZERO_EXIT', 'RECEIPT_ABI_UNVERIFIED',
                           'RECEIPT_PROVENANCE_UNVERIFIED', 'WORKER_UNCERTAIN', 'CWD_IDENTITY_CHANGED',
                           'EXECUTABLE_IDENTITY_CHANGED', 'EXECUTABLE_PIN_CHANGED', 'ANCESTOR_CHANGED',
                           'REGISTRY_PIN_CHANGED', 'REGISTRY_SOURCE_INPUT_PIN_CHANGED'}
                allowed |= {'OUTER_GROUP_UNAVAILABLE', 'PROCESS_GROUP_CHANGED'}
                code = packet.get('code')
                raise RunnerError(code if code in allowed else 'WORKER_UNCERTAIN', uncertain=True)
            need(set(packet) == {'status', 'raw', 'role', 'context', 'completed_at'}, 'WORKER_PACKET_INVALID', uncertain=True)
            raw = base64.b64decode(packet['raw'], validate=True)
            need(0 < len(raw) <= MAX_RECEIPT and packet['role'] == op and tuple(packet['context']) == context,
                 'WORKER_PACKET_INVALID', uncertain=True)
            view = ReceiptView(raw, op, context, 'COMPLETE', instant(datetime.fromisoformat(packet['completed_at'])))
            now, _, _ = self._guard(invocation, started, mark, last)
            need(started <= view.completed_at <= now, 'WORKER_PACKET_INVALID', uncertain=True)
        except RunnerError:
            raise
        except BaseException:
            raise RunnerError('WORKER_UNCERTAIN', uncertain=True) from None
        finally:
            selector.close()
            os.close(read_fd)
            self._cleanup(pid, self.registry.containment)
        # Successful transport/ABI before the deadline is insufficient when
        # process cleanup itself used up the remaining budget.
        self._guard(invocation, started, mark, last)
        return view

    def service(self, receipt_type):
        # Fixed core dataclass constructor only, never an arbitrary transport or
        # receipt callback in the unbounded parent. Structural ABI must agree.
        need(type(receipt_type) is type and receipt_type.__bases__ == (object,)
             and hasattr(receipt_type, '__dataclass_fields__')
             and tuple(receipt_type.__dataclass_fields__) == ('raw', 'role', 'context', 'status', 'completed_at')
             and receipt_type.__dataclass_params__.frozen
             and all(name not in receipt_type.__dict__ for name in receipt_type.__dataclass_fields__),
             'CORE_RECEIPT_TYPE_INVALID')
        def execute(invocation):
            view = self.run(invocation)
            # Avoid executing even a custom dataclass initializer or descriptor
            # in the parent after the bounded worker has returned.
            original = object.__new__(receipt_type)
            for name in receipt_type.__dataclass_fields__:
                object.__setattr__(original, name, getattr(view, name))
            return original
        return execute
