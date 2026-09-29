"""Epoch-bound session journal catalog. Preserves every prior session; no deletion."""
from datetime import date
from pathlib import Path
import os
import re
import stat

from .r2d2_v2_massive_journal import MassiveJournal
from .r2d2_v2_massive_maintenance import journal_access
from .r2d2_v2_sources import canonical, _load_json, _open_directory, _require

MAX_SESSIONS = 256
_PARENT_FILES = {'epoch.json', 'maintenance.lock', 'producer.lock'}


def _session(value):
    _require(type(value) is str, 'MASSIVE_SESSION_DATE')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _require(False, 'MASSIVE_SESSION_DATE')
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
                    _immutable(child, 'session.json', {'schema': 'MASSIVE_SESSION_V1', 'epoch': self.epoch,
                                                      'session': session, 'symbols': sorted(symbols),
                                                      'device': info.st_dev, 'inode': info.st_ino})
                finally:
                    os.close(child)
            finally:
                os.close(directory)
        return self.session_path(session)

    def mark_ready(self, session):
        session = _session(session)
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
                    _immutable(child, 'ready.json', {'epoch': self.epoch, 'session': session})
                finally:
                    os.close(child)
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
                        _require(False, 'MASSIVE_SESSION_NOT_READY')
                    _require(ready == {'epoch': self.epoch, 'session': session},
                             'MASSIVE_SESSION_READY_MISMATCH')
                finally:
                    os.close(child)
                _require((path / 'sequence.sqlite3').exists(), 'MASSIVE_SESSION_NOT_READY')
                return MassiveJournal.open_reader(path)
            finally:
                os.close(directory)
