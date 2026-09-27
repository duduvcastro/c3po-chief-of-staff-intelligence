"""Append-only local evidence sink. No provider or host access.

One immutable receipt per content hash; raw bytes are committed first. Orphan
raw files after interruption are harmless. Existing bytes must match exactly.
"""
import hashlib
import os
import stat
from pathlib import Path
import secrets
from .r2d2_v2_sources import canonical

class MassiveSpool:
    def __init__(self, root, *, max_bytes=512*1024*1024, max_files=500_000, min_free_bytes=1024*1024*1024):
        if type(max_bytes) is not int or max_bytes <= 0 or type(max_files) is not int or max_files <= 0:
            raise ValueError('SPOOL_BUDGET')
        if type(min_free_bytes) is not int or min_free_bytes <= 0:
            raise ValueError('SPOOL_FREE_SPACE_FLOOR')
        self.min_free_bytes = min_free_bytes
        self.max_bytes, self.max_files = max_bytes, max_files
        self.used_bytes = self.used_files = 0
        self.root = Path(root).absolute()
        self._identities = {}
        root_fd = self._open_root(create=True)
        try:
            self._identities['root'] = self._identity(root_fd)
            for name in ('raw', 'receipts'):
                try:
                    os.mkdir(name, mode=0o700, dir_fd=root_fd)
                except FileExistsError:
                    pass
                child_fd = self._open_child(root_fd, name)
                try:
                    self._identities[name] = self._identity(child_fd)
                    # Count orphan/pending evidence without an unbounded list.
                    with os.scandir(child_fd) as entries:
                        for entry in entries:
                            info = entry.stat(follow_symlinks=False)
                            if not stat.S_ISREG(info.st_mode):
                                raise ValueError('SPOOL_EXISTING_TYPE')
                            self._reserve(info.st_size)
                finally:
                    os.close(child_fd)
            os.fsync(root_fd)
        finally:
            os.close(root_fd)

    @staticmethod
    def _identity(fd):
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
            raise ValueError('SPOOL_DIRECTORY')
        return info.st_dev, info.st_ino

    def _open_root(self, *, create=False):
        # Walk anchored descriptors; even mkdir must not follow an ancestor
        # symlink. No resolve(): resolving would silently authorize an alias.
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in self.root.parts[1:]:
                if part in ('.', '..'):
                    raise ValueError('SPOOL_ROOT')
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
            identity = self._identity(fd)
            if self._identities.get('root', identity) != identity:
                raise ValueError('SPOOL_ROOT_CHANGED')
            return fd
        except OSError as exc:
            os.close(fd)
            raise ValueError('SPOOL_ROOT') from exc
        except BaseException:
            os.close(fd)
            raise

    def _open_child(self, root_fd, name):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        except OSError as exc:
            raise ValueError('SPOOL_DIRECTORY') from exc
        try:
            identity = self._identity(fd)
            if self._identities.get(name, identity) != identity:
                raise ValueError('SPOOL_DIRECTORY_CHANGED')
            return fd
        except BaseException:
            os.close(fd)
            raise

    def _check_directories(self):
        root_fd = self._open_root()
        try:
            for name in ('raw', 'receipts'):
                fd = self._open_child(root_fd, name)
                os.close(fd)
        finally:
            os.close(root_fd)

    def _reserve(self, size):
        if self.used_bytes + size > self.max_bytes or self.used_files + 1 > self.max_files:
            raise ValueError('SPOOL_BUDGET_EXHAUSTED')
        # Keep reservation on errors. Only reopening/rescanning can recover it;
        # uncertainty must never create extra capacity in a running producer.
        self.used_bytes += size
        self.used_files += 1

    @staticmethod
    def _verify_existing(target, data, *, directory_fd):
        # Never block on a FIFO or follow a last-component symlink, including
        # a competing destination created between the existence check and link.
        try:
            fd = os.open(target, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory_fd)
        except OSError as exc:
            raise ValueError('SPOOL_CONTENT_CONFLICT') from exc
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != len(data):
                raise ValueError('SPOOL_CONTENT_CONFLICT')
            if stream.read(len(data) + 1) != data:
                raise ValueError('SPOOL_CONTENT_CONFLICT')

    def _commit(self, directory, data):
        digest = hashlib.sha256(data).hexdigest()
        self._check_directories()
        root_fd = self._open_root()
        try:
            directory_fd = self._open_child(root_fd, directory)
        finally:
            os.close(root_fd)
        target = digest + '.json'
        temporary = None
        try:
            try:
                os.stat(target, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                self._verify_existing(target, data, directory_fd=directory_fd)
                os.fsync(directory_fd)
                self._check_directories()
                return digest
            try:
                capacity = os.fstatvfs(directory_fd)
            except OSError as exc:
                raise ValueError('SPOOL_FREE_SPACE_UNVERIFIED') from exc
            if capacity.f_bavail * capacity.f_frsize < self.min_free_bytes + len(data):
                raise ValueError('SPOOL_LOW_DISK')
            self._reserve(len(data))
            name = '.pending-' + secrets.token_hex(16)
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory_fd)
            temporary = name
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target, src_dir_fd=directory_fd,
                        dst_dir_fd=directory_fd, follow_symlinks=False)
            except FileExistsError:
                self._verify_existing(target, data, directory_fd=directory_fd)
            os.fsync(directory_fd)
            self._check_directories()
            return digest
        finally:
            try:
                if temporary is not None:
                    os.unlink(temporary, dir_fd=directory_fd)
            finally:
                os.close(directory_fd)

    def __call__(self, raw, receipt):
        if raw is not None:
            if type(raw) is not bytes:
                raise ValueError('SPOOL_RAW_TYPE')
            digest = hashlib.sha256(raw).hexdigest()
            if receipt.get('raw_sha256') != digest or receipt.get('raw_bytes') != len(raw):
                raise ValueError('SPOOL_RAW_BINDING')
            self._commit('raw', raw)
        elif receipt.get('event', {}).get('type') != 'DATA_GAP':
            raise ValueError('SPOOL_MISSING_RAW')
        self._commit('receipts', canonical(receipt))
