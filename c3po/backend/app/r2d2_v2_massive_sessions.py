"""Epoch-bound session journal catalog. Preserves every prior session; no deletion."""
from datetime import date
from pathlib import Path
import os
import re
import secrets
import stat
import time

from .r2d2_v2_massive_journal import MassiveJournal
from .r2d2_v2_massive_maintenance import journal_access
from .r2d2_v2_sources import SourceUnavailable, canonical, _load_json, _open_directory, _require

MAX_SESSIONS = 256
_PARENT_FILES = {'epoch.json', 'maintenance.lock', 'producer.lock'}
READY_LOCK_WAIT_SECONDS = 30.0
READY_LOCK_POLL_SECONDS = 0.01
_UNREADY_FILES = {'session.json', 'maintenance.lock', 'producer.lock'}
_UNREADY_INDEX = {'sequence.sqlite3', 'sequence.sqlite3-journal', 'sequence.sqlite3-wal', 'sequence.sqlite3-shm'}
_TEMPORARY = re.compile(r'\.(session|ready)\.json\.[0-9a-f]{16}\.tmp')
_UNREADY_ENTRY_LIMIT = 32


def _session(value):
    _require(type(value) is str, 'MASSIVE_SESSION_DATE')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise SourceUnavailable('MASSIVE_SESSION_DATE') from None
    _require(parsed.isoformat() == value, 'MASSIVE_SESSION_DATE')
    return value


def _private_file(directory, name, limit=65536):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        before = os.fstat(fd)
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                 and before.st_uid == os.geteuid() and not before.st_mode & 0o077
                 and 0 < before.st_size <= limit, 'MASSIVE_SESSION_FILE_UNSAFE')
        chunks = []; remaining = limit + 1
        while remaining:
            data = os.read(fd, remaining)
            if not data: break
            chunks.append(data); remaining -= len(data)
        data = b''.join(chunks)
        after = os.fstat(fd)
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        _require(identity(before) == identity(after) and len(data) == before.st_size,
                 'MASSIVE_SESSION_FILE_CHANGED')
        return data
    finally:
        os.close(fd)


def _immutable(directory, name, value):
    data = canonical(value)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
    except FileExistsError:
        _require(_private_file(directory, name) == data, 'MASSIVE_SESSION_MANIFEST_CHANGED')
        return
    try:
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            _require(count > 0, 'MASSIVE_SESSION_MANIFEST_WRITE')
            view = view[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory)


def _atomic_immutable(directory, name, value):
    """Same bytes as _immutable, but a reader never observes a torn file.

    Writers of these names hold the exclusive catalog lock, so the existence
    check cannot race another cooperating writer. A crash leaves at most an
    unpublished private temporary file, never a partial manifest.
    """
    data = canonical(value)
    try:
        existing = _private_file(directory, name)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        _require(existing == data, 'MASSIVE_SESSION_MANIFEST_CHANGED')
        return
    temporary = '.' + name + '.' + secrets.token_hex(8) + '.tmp'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    published = False
    try:
        try:
            view = memoryview(data)
            while view:
                count = os.write(fd, view)
                _require(count > 0, 'MASSIVE_SESSION_MANIFEST_WRITE')
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            _require(False, 'MASSIVE_SESSION_MANIFEST_CHANGED')
        os.rename(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        published = True
    finally:
        if not published:
            try:
                os.unlink(temporary, dir_fd=directory)
            except OSError:
                pass
    os.fsync(directory)


def _empty_unready(child):
    """Ready is published before any append, so an unready session must hold
    no evidence. Anything beyond initialization artifacts stays fail-closed.
    Returns True when no index needs inspection (absent, or one empty file)."""
    count = 0
    index = set()
    index_size = None
    with os.scandir(child) as entries:
        for entry in entries:
            count += 1
            _require(count <= _UNREADY_ENTRY_LIMIT, 'MASSIVE_SESSION_NOT_READY')
            info = entry.stat(follow_symlinks=False)
            _require(info.st_uid == os.geteuid() and not info.st_mode & 0o077,
                     'MASSIVE_SESSION_FILE_UNSAFE')
            if entry.name in ('raw', 'receipts'):
                _require(stat.S_ISDIR(info.st_mode), 'MASSIVE_SESSION_FILE_UNSAFE')
                evidence = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=child)
                try:
                    _require(not os.listdir(evidence), 'MASSIVE_SESSION_NOT_READY')
                finally:
                    os.close(evidence)
                continue
            _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'MASSIVE_SESSION_FILE_UNSAFE')
            if entry.name in _UNREADY_INDEX:
                index.add(entry.name)
                if entry.name == 'sequence.sqlite3':
                    index_size = info.st_size
                continue
            _require(entry.name in _UNREADY_FILES or _TEMPORARY.fullmatch(entry.name) is not None,
                     'MASSIVE_SESSION_NOT_READY')
    return not index or (index == {'sequence.sqlite3'} and index_size == 0)


class SessionJournalRoot:
    """One private, existing parent directory belongs to exactly one epoch.

    Initialization is explicit. Readers never create catalogs, sessions or
    databases. Existing flat journals require a separate migration decision.
    """
    def __init__(self, root, epoch, *, create=False):
        _require(type(epoch) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}', epoch)
                 is not None, 'MASSIVE_SESSION_EPOCH')
        _require(type(create) is bool, 'MASSIVE_SESSION_POLICY')
        self.root = Path(root).absolute()
        self.epoch = epoch
        directory = _open_directory(self.root)
        try:
            info = os.fstat(directory)
            _require(info.st_uid == os.geteuid(), 'MASSIVE_SESSION_ROOT_OWNER')
            self._identity = (info.st_dev, info.st_ino)
            with journal_access(self.root, exclusive=create, create=create):
                if create:
                    # Never bless an existing flat journal or unexpected files.
                    existing = self._names(directory)
                    _require(not existing or 'epoch.json' in os.listdir(directory),
                             'MASSIVE_SESSION_EPOCH_MISSING')
                    _immutable(directory, 'epoch.json', {'schema': 'MASSIVE_SESSION_ROOT_V1', 'epoch': epoch,
                                                          'device': info.st_dev, 'inode': info.st_ino})
                self._verify(directory)
        finally:
            os.close(directory)

    def _verify(self, directory):
        info = os.fstat(directory)
        _require((info.st_dev, info.st_ino) == self._identity, 'MASSIVE_SESSION_ROOT_CHANGED')
        _require(_load_json(_private_file(directory, 'epoch.json')) ==
                 {'schema': 'MASSIVE_SESSION_ROOT_V1', 'epoch': self.epoch,
                  'device': info.st_dev, 'inode': info.st_ino}, 'MASSIVE_SESSION_EPOCH_MISMATCH')

    def _names(self, directory):
        sessions = []
        count = 0
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                _require(count <= MAX_SESSIONS + len(_PARENT_FILES), 'MASSIVE_SESSION_COUNT_LIMIT')
                info = entry.stat(follow_symlinks=False)
                if entry.name in _PARENT_FILES:
                    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                             and info.st_uid == os.geteuid() and not info.st_mode & 0o077,
                             'MASSIVE_SESSION_FILE_UNSAFE')
                    continue
                _require(entry.name.startswith('session_date='), 'MASSIVE_SESSION_LAYOUT')
                day = _session(entry.name[len('session_date='):])
                _require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                         and not info.st_mode & 0o077, 'MASSIVE_SESSION_DIRECTORY_UNSAFE')
                sessions.append(day)
        return tuple(sorted(sessions))

    def session_path(self, session):
        return self.root / ('session_date=' + _session(session))

    def _manifest(self, directory, session):
        child = os.open('session_date=' + session, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory)
        try:
            info = os.fstat(child)
            _require(info.st_uid == os.geteuid() and not info.st_mode & 0o077,
                     'MASSIVE_SESSION_DIRECTORY_UNSAFE')
            value = _load_json(_private_file(child, 'session.json'))
            _require(type(value) is dict and set(value) == {'schema', 'epoch', 'session', 'symbols', 'device', 'inode'}
                     and value['schema'] == 'MASSIVE_SESSION_V1' and value['epoch'] == self.epoch
                     and value['session'] == session and type(value['device']) is int
                     and type(value['inode']) is int and value['device'] == info.st_dev
                     and value['inode'] == info.st_ino, 'MASSIVE_SESSION_MANIFEST')
            symbols = value['symbols']
            _require(type(symbols) is list and 0 < len(symbols) <= 550
                     and all(type(s) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,19}', s) is not None
                             for s in symbols)
                     and symbols == sorted(set(symbols)), 'MASSIVE_SESSION_SYMBOLS')
            return value
        finally:
            os.close(child)

    def sessions(self):
        with journal_access(self.root):
            directory = _open_directory(self.root)
            try:
                self._verify(directory)
                sessions = self._names(directory)
                for day in sessions:
                    self._manifest(directory, day)
                return sessions
            finally:
                os.close(directory)

    def manifest(self, session):
        session = _session(session)
        with journal_access(self.root):
            directory = _open_directory(self.root)
            try:
                self._verify(directory)
                return self._manifest(directory, session)
            finally:
                os.close(directory)

    def prepare_session(self, session, symbols):
        session = _session(session)
        _require(type(symbols) in (list, tuple, set, frozenset) and 0 < len(symbols) <= 550
                 and all(type(s) is str and re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,19}', s) is not None
                         for s in symbols) and len(set(symbols)) == len(symbols), 'MASSIVE_SESSION_SYMBOLS')
        with journal_access(self.root, exclusive=True):
            directory = _open_directory(self.root)
            try:
                self._verify(directory)
                existing = self._names(directory)
                _require(session in existing or len(existing) < MAX_SESSIONS, 'MASSIVE_SESSION_COUNT_LIMIT')
                name = 'session_date=' + session
                try:
                    os.mkdir(name, 0o700, dir_fd=directory)
                    os.fsync(directory)
                except FileExistsError:
                    pass
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                try:
                    info = os.fstat(child)
                    _require(info.st_uid == os.geteuid() and not info.st_mode & 0o077,
                             'MASSIVE_SESSION_DIRECTORY_UNSAFE')
                    _atomic_immutable(child, 'session.json', {'schema': 'MASSIVE_SESSION_V1', 'epoch': self.epoch,
                                                      'session': session, 'symbols': sorted(symbols),
                                                      'device': info.st_dev, 'inode': info.st_ino})
                finally:
                    os.close(child)
            finally:
                os.close(directory)
        return self.session_path(session)

    def mark_ready(self, session):
        session = _session(session)
        # Readers hold the shared catalog lock for a whole poll. Wait a bounded
        # time for the exclusive lock instead of leaving the session unready.
        deadline = time.monotonic() + READY_LOCK_WAIT_SECONDS
        while True:
            try:
                return self._mark_ready(session)
            except SourceUnavailable as exc:
                if str(exc) != 'MASSIVE_MAINTENANCE_BUSY' or time.monotonic() >= deadline:
                    raise
            time.sleep(READY_LOCK_POLL_SECONDS)

    def _mark_ready(self, session):
        with journal_access(self.root, exclusive=True):
            directory = _open_directory(self.root)
            try:
                self._verify(directory)
                self._manifest(directory, session)
                # Verify initialized schema before publishing the ready marker.
                MassiveJournal.open_reader(self.session_path(session))
                child = os.open('session_date=' + session, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
                try:
                    _atomic_immutable(child, 'ready.json', {'epoch': self.epoch, 'session': session})
                finally:
                    os.close(child)
            finally:
                os.close(directory)

    def _readiness(self, directory, session):
        """True when published ready; False only for a verifiably empty unready session."""
        child = os.open('session_date=' + session, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory)
        try:
            info = os.fstat(child)
            _require(info.st_uid == os.geteuid() and not info.st_mode & 0o077,
                     'MASSIVE_SESSION_DIRECTORY_UNSAFE')
            try:
                ready = _load_json(_private_file(child, 'ready.json'))
            except FileNotFoundError:
                ready = None
            if ready is not None:
                self._manifest(directory, session)
                _require(ready == {'epoch': self.epoch, 'session': session}, 'MASSIVE_SESSION_READY_MISMATCH')
                return True
            try:
                os.stat('session.json', dir_fd=child, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                self._manifest(directory, session)
            settled = _empty_unready(child)
        finally:
            os.close(child)
        if not settled:
            # An initialized but unpublished index must verifiably hold no receipt.
            journal = MassiveJournal.open_reader(self.session_path(session), allow_uninitialized=True)
            with journal._connect() as db:
                _require(journal._bounds(db) == (0, 0), 'MASSIVE_SESSION_NOT_READY')
        return False

    def ready_sessions(self):
        """Published sessions only. A verifiably empty unready session is skipped;
        an unready session holding any evidence refuses the whole catalog."""
        with journal_access(self.root):
            directory = _open_directory(self.root)
            try:
                self._verify(directory)
                return tuple(day for day in self._names(directory) if self._readiness(directory, day))
            finally:
                os.close(directory)

    def ensure_session(self, session, symbols):
        journal = MassiveJournal(self.prepare_session(session, symbols))
        self.mark_ready(session)
        return journal

    def open_session(self, session):
        session = _session(session)
        with journal_access(self.root):
            directory = _open_directory(self.root)
            try:
                self._verify(directory)
                self._manifest(directory, session)
                path = self.session_path(session)
                child = os.open('session_date=' + session, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=directory)
                try:
                    try:
                        ready = _load_json(_private_file(child, 'ready.json'))
                    except FileNotFoundError:
                        raise SourceUnavailable('MASSIVE_SESSION_NOT_READY') from None
                    _require(ready == {'epoch': self.epoch, 'session': session},
                             'MASSIVE_SESSION_READY_MISMATCH')
                finally:
                    os.close(child)
                _require((path / 'sequence.sqlite3').exists(), 'MASSIVE_SESSION_NOT_READY')
                return MassiveJournal.open_reader(path)
            finally:
                os.close(directory)
