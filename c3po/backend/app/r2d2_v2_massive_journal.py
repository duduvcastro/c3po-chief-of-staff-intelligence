"""Offline durable receipt sequence. Not yet wired to the collector.

Raw/receipt files commit before the sequence transaction. Readers propose a
position; this module never acknowledges on behalf of the collector.
"""
import hashlib
import os
import sqlite3
import stat
from datetime import date
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from .r2d2_v2_massive_spool import MassiveSpool
from .r2d2_v2_massive_maintenance import journal_access
from .r2d2_v2_sources import canonical, _load_json, _open_directory, _read_file, SourceUnavailable


class MassiveJournal:
    def __init__(self, root, *, max_index_bytes=64*1024*1024):
        if type(max_index_bytes) is not int or max_index_bytes < 16384:
            raise ValueError('JOURNAL_INDEX_BUDGET')
        self.max_index_bytes = max_index_bytes
        self.read_only = False
        self.spool = MassiveSpool(root)
        self.path = self.spool.root / 'sequence.sqlite3'
        with journal_access(self.path.parent, create=True):
            self._bind_index(create=True)
            with self._connect() as db:
                if self._index_created:
                    db.execute('CREATE TABLE receipts (sequence INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL)')
                    db.execute("CREATE TABLE retention_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), pruned_through INTEGER NOT NULL CHECK(pruned_through>=0), retain_from_session TEXT NOT NULL DEFAULT '')")
                    db.execute("INSERT INTO retention_state VALUES (1,0,'')")
                else:
                    # Missing state requires explicit reconciliation, not a reset.
                    self._bounds(db)

    @classmethod
    def open_reader(cls, root):
        obj = cls.__new__(cls)
        obj.read_only = True
        root = Path(root).absolute()
        if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
            raise ValueError('JOURNAL_READER_ROOT')
        obj.spool = SimpleNamespace(root=root)
        obj.path = root / 'sequence.sqlite3'
        with journal_access(root):
            obj._bind_index(create=False)
            with obj._connect() as db:
                db.execute('SELECT sequence,digest FROM receipts LIMIT 0')
        return obj

    @staticmethod
    def _file_identity(info):
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_mode & 0o077 or info.st_uid != os.geteuid()):
            raise ValueError('JOURNAL_INDEX_UNSAFE')
        return info.st_dev, info.st_ino

    def _bind_index(self, *, create):
        self._index_created = False
        root_fd = fd = None
        try:
            root_fd = _open_directory(self.path.parent)
            root_info = os.fstat(root_fd)
            if root_info.st_mode & 0o077 or root_info.st_uid != os.geteuid():
                raise ValueError('JOURNAL_ROOT_UNSAFE')
            self._root_identity = root_info.st_dev, root_info.st_ino
            if create:
                try:
                    fd = os.open(self.path.name, os.O_RDWR | os.O_CREAT | os.O_EXCL
                                 | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=root_fd)
                    self._index_created = True
                    os.fsync(fd)
                    os.fsync(root_fd)
                except FileExistsError:
                    pass
            if fd is None:
                fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW
                             | os.O_NONBLOCK, dir_fd=root_fd)
            self._index_identity = self._file_identity(os.fstat(fd))
        except (OSError, SourceUnavailable) as exc:
            raise ValueError('JOURNAL_INDEX_UNSAFE') from exc
        finally:
            if fd is not None: os.close(fd)
            if root_fd is not None: os.close(root_fd)

    def _check_index(self):
        # SQLite opens its database and rollback journal by pathname. These
        # checks reject unsafe persistent aliases and replacement at observable
        # boundaries; they are not a custom VFS or protection against arbitrary
        # concurrent mutation by another process running as the same user.
        root_fd = None
        try:
            root_fd = _open_directory(self.path.parent)
            info = os.fstat(root_fd)
            if ((info.st_dev, info.st_ino) != self._root_identity
                    or info.st_mode & 0o077 or info.st_uid != os.geteuid()):
                raise ValueError('JOURNAL_ROOT_CHANGED')
            info = os.stat(self.path.name, dir_fd=root_fd, follow_symlinks=False)
            if self._file_identity(info) != self._index_identity:
                raise ValueError('JOURNAL_INDEX_CHANGED')
            for suffix in ('-journal', '-wal', '-shm'):
                try:
                    sidecar = os.stat(self.path.name + suffix, dir_fd=root_fd,
                                      follow_symlinks=False)
                except FileNotFoundError:
                    continue
                self._file_identity(sidecar)
        except (OSError, SourceUnavailable) as exc:
            raise ValueError('JOURNAL_INDEX_UNSAFE') from exc
        finally:
            if root_fd is not None: os.close(root_fd)

    @contextmanager
    def _connect(self):
        with journal_access(self.path.parent):
            with self._connect_locked() as db:
                yield db

    @contextmanager
    def _connect_locked(self):
        self._check_index()
        # Both modes require the securely created index to exist. Never let
        # SQLite silently create a replacement if the bound file disappears.
        mode = 'ro' if self.read_only else 'rw'
        db = sqlite3.connect(self.path.as_uri() + '?mode=' + mode, uri=True, timeout=2)
        try:
            self._check_index()
            db.execute('PRAGMA synchronous=FULL')
            if not self.read_only:
                page_size = db.execute('PRAGMA page_size').fetchone()[0]
                maximum = self.max_index_bytes // page_size
                current = db.execute('PRAGMA page_count').fetchone()[0]
                if current > maximum:
                    raise ValueError('JOURNAL_INDEX_BUDGET_EXHAUSTED')
                actual = db.execute('PRAGMA max_page_count=' + str(maximum)).fetchone()[0]
                if actual != maximum:
                    raise ValueError('JOURNAL_INDEX_BUDGET_EXHAUSTED')
            with db:
                yield db
                self._check_index()
        finally:
            db.close()

    def __call__(self, raw, receipt):
        with journal_access(self.path.parent):
            return self._append_locked(raw, receipt)

    def _append_locked(self, raw, receipt):
        if self.read_only:
            raise ValueError('JOURNAL_READ_ONLY')
        # A crash between these commits leaves orphan evidence, never an index
        # entry pointing at uncommitted bytes. Retrying the receipt is idempotent.
        with self._connect() as db:
            self._check_receipt_session(db, receipt)
        self.spool(raw, receipt)
        digest = hashlib.sha256(canonical(receipt)).hexdigest()
        with self._connect() as db:
            self._check_receipt_session(db, receipt)
            db.execute('INSERT OR IGNORE INTO receipts(digest) VALUES (?)', (digest,))
            return db.execute('SELECT sequence FROM receipts WHERE digest=?', (digest,)).fetchone()[0]

    def _read_evidence(self, directory, name, budget, code):
        with journal_access(self.path.parent):
            return self._read_evidence_locked(directory, name, budget, code)

    def _read_evidence_locked(self, directory, name, budget, code):
        # Anchor every directory component and validate the opened descriptor.
        # Checking a pathname before read_bytes permits replacement with a FIFO
        # or symlink between stat and open, including in parent directories.
        root_fd = child_fd = None
        try:
            root_fd = _open_directory(self.spool.root.absolute())
            child_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            return _read_file(child_fd, name, budget)
        except (OSError, SourceUnavailable) as exc:
            raise ValueError(code) from exc
        finally:
            if child_fd is not None: os.close(child_fd)
            if root_fd is not None: os.close(root_fd)

    @staticmethod
    def _validate_cutoff(value):
        if type(value) is not str:
            raise ValueError('JOURNAL_RETENTION_STATE')
        if value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError('JOURNAL_RETENTION_STATE')
            except ValueError:
                raise ValueError('JOURNAL_RETENTION_STATE') from None
        return value

    @staticmethod
    def _check_receipt_session(db, receipt):
        row = db.execute('SELECT retain_from_session FROM retention_state WHERE singleton=1').fetchone()
        if row is None: raise ValueError('JOURNAL_RETENTION_STATE')
        cutoff = MassiveJournal._validate_cutoff(row[0])
        if cutoff:
            session = receipt.get('event', {}).get('session')
            try:
                valid = type(session) is str and date.fromisoformat(session).isoformat()==session
            except ValueError:
                valid = False
            if not valid or session < cutoff:
                raise ValueError('JOURNAL_RECEIPT_SESSION_PRUNED')

    @staticmethod
    def _bounds(db):
        state = db.execute('SELECT singleton,pruned_through,retain_from_session FROM retention_state').fetchall()
        if len(state) != 1 or state[0][0] != 1 or type(state[0][1]) is not int or state[0][1] < 0:
            raise ValueError('JOURNAL_RETENTION_STATE')
        MassiveJournal._validate_cutoff(state[0][2])
        floor = state[0][1]
        low, high = db.execute('SELECT MIN(sequence),MAX(sequence) FROM receipts').fetchone()
        if low is None:
            if floor != 0: raise ValueError('JOURNAL_RETENTION_STATE')
            high = 0
        elif low != floor + 1:
            raise ValueError('JOURNAL_SEQUENCE_GAP')
        return floor, high

    def retention_cutoff(self):
        with self._connect() as db:
            self._bounds(db)
            return db.execute('SELECT retain_from_session FROM retention_state WHERE singleton=1').fetchone()[0]

    def retention_floor(self):
        with self._connect() as db:
            return self._bounds(db)[0]

    def page(self, after=0, *, through=None, limit=1024, byte_limit=4*1024*1024):
        with journal_access(self.path.parent):
            return self._page_locked(after, through=through, limit=limit, byte_limit=byte_limit)

    def _page_locked(self, after=0, *, through=None, limit=1024, byte_limit=4*1024*1024):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 4096:
            raise ValueError('JOURNAL_PAGE_LIMIT')
        if type(byte_limit) is not int or not 1 <= byte_limit <= 16*1024*1024:
            raise ValueError('JOURNAL_BYTE_LIMIT')
        with self._connect() as db:
            floor, high = self._bounds(db)
            if after < floor:
                raise ValueError('JOURNAL_CURSOR_PRUNED')
            through = high if through is None else through
            if type(through) is not int or not after <= through <= high:
                raise ValueError('JOURNAL_HORIZON')
            rows = db.execute('SELECT sequence,digest FROM receipts WHERE sequence>? AND sequence<=? ORDER BY sequence LIMIT ?',
                              (after, through, limit)).fetchall()
        result=[];used=0;position=after;verified_raw={}
        for sequence,digest in rows:
            if sequence != position + 1:
                raise ValueError('JOURNAL_SEQUENCE_GAP')
            if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('JOURNAL_RECEIPT_HASH')
            path=self.spool.root/'receipts'/(digest+'.json')
            if path.is_symlink() or not path.is_file() or path.stat().st_size > byte_limit:
                raise ValueError('JOURNAL_RECEIPT_LIMIT')
            data=self._read_evidence('receipts', digest+'.json', byte_limit, 'JOURNAL_RECEIPT_LIMIT')
            if hashlib.sha256(data).hexdigest()!=digest:
                raise ValueError('JOURNAL_RECEIPT_HASH')
            if used + len(data) > byte_limit:
                break
            receipt=_load_json(data)
            raw_hash=receipt.get('raw_sha256');raw_cost=0
            if raw_hash is not None:
                if not isinstance(raw_hash,str) or len(raw_hash)!=64 or any(c not in '0123456789abcdef' for c in raw_hash):
                    raise ValueError('JOURNAL_RAW_HASH')
                raw_path=self.spool.root/'raw'/(raw_hash+'.json')
                from .r2d2_v2_minute_bars import MAX_RESPONSE_BYTES
                if raw_path.is_symlink() or not raw_path.is_file():
                    raise ValueError('JOURNAL_RAW_SIZE')
                size=raw_path.stat().st_size
                if not 0 < size <= MAX_RESPONSE_BYTES or size!=receipt.get('raw_bytes'):
                    raise ValueError('JOURNAL_RAW_SIZE')
                if raw_hash not in verified_raw:
                    raw_cost=size
                    if used+len(data)+raw_cost>byte_limit:
                        if not result:raise ValueError('JOURNAL_BYTE_LIMIT')
                        break
                    raw_data=self._read_evidence('raw', raw_hash+'.json', size, 'JOURNAL_RAW_SIZE')
                    if len(raw_data)!=size or hashlib.sha256(raw_data).hexdigest()!=raw_hash:
                        raise ValueError('JOURNAL_RAW_HASH')
                    verified_raw[raw_hash]=size
                elif verified_raw[raw_hash]!=size:
                    raise ValueError('JOURNAL_RAW_SIZE')
            elif receipt.get('event',{}).get('type')!='DATA_GAP':
                raise ValueError('JOURNAL_RAW_MISSING')
            result.append({'sequence':sequence,'receipt_sha256':digest,'receipt':receipt})
            used+=len(data)+raw_cost;position=sequence
        return {'records':result,'after':position,'through':through,'has_more':position<through}
