"""Offline durable receipt sequence. Not yet wired to the collector.

Raw/receipt files commit before the sequence transaction. Readers propose a
position; this module never acknowledges on behalf of the collector.
"""
import hashlib
import os
import sqlite3
import stat
from datetime import date, datetime, timedelta, timezone
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
        self.storage_stopped = False
        self._normal_index_limit = None
        self.spool = MassiveSpool(root)
        self.session = self._bound_session(self.spool.root)
        self.path = self.spool.root / 'sequence.sqlite3'
        with journal_access(self.path.parent, create=True):
            self._bind_index(create=True)
            with self._connect_locked() as db:
                if self._index_created:
                    # SQLite DDL otherwise autocommits before the first DML.
                    # Publish the complete schema or none of it. Unready
                    # catalog probes distinguish an empty in-flight schema.
                    db.execute('BEGIN IMMEDIATE')
                    db.execute('CREATE TABLE receipts (sequence INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL)')
                    db.execute("CREATE TABLE retention_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), pruned_through INTEGER NOT NULL CHECK(pruned_through>=0), retain_from_session TEXT NOT NULL DEFAULT '')")
                    db.execute("INSERT INTO retention_state VALUES (1,0,'')")
                    self._create_clock_schema(db)
                else:
                    # Missing state requires explicit reconciliation, not a reset.
                    self._bounds(db)

    @classmethod
    def open_reader(cls, root, *, allow_uninitialized=False):
        if type(allow_uninitialized) is not bool:
            raise ValueError('JOURNAL_READER_POLICY')
        obj = cls.__new__(cls)
        obj.read_only = True
        root = Path(root).absolute()
        if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
            raise ValueError('JOURNAL_READER_ROOT')
        obj.spool = SimpleNamespace(root=root)
        obj.session = cls._bound_session(root)
        obj.path = root / 'sequence.sqlite3'
        with journal_access(root):
            obj._bind_index(create=False)
            with obj._connect() as db:
                if allow_uninitialized and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
                    raise SourceUnavailable('MASSIVE_SESSION_NOT_READY')
                db.execute('SELECT sequence,digest FROM receipts LIMIT 0')
        return obj

    @staticmethod
    def _bound_session(root):
        if not root.name.startswith('session_date='):
            return None  # Explicit legacy flat journals retain their contract.
        value = root.name.removeprefix('session_date=')
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError('JOURNAL_SESSION_PATH')
        except ValueError:
            raise ValueError('JOURNAL_SESSION_PATH') from None
        return value

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
    def _connect(self, *, index_limit=None):
        with journal_access(self.path.parent):
            with self._connect_locked(index_limit=index_limit) as db:
                yield db

    @contextmanager
    def _connect_locked(self, *, index_limit=None):
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
                maximum = (self.max_index_bytes if index_limit is None else index_limit) // page_size
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
            try:
                return self._append_locked(raw, receipt)
            except (ValueError, sqlite3.Error) as exc:
                capacity = str(exc) in {'SPOOL_BUDGET_EXHAUSTED', 'SPOOL_LOW_DISK',
                                       'JOURNAL_INDEX_BUDGET_EXHAUSTED'} or (
                    isinstance(exc, sqlite3.Error) and getattr(exc, 'sqlite_errorcode', None) == getattr(sqlite3, 'SQLITE_FULL', 13))
                if not capacity or not hasattr(self, '_storage_symbols'):
                    raise
                self._persist_storage_failure(receipt, str(exc) if not isinstance(exc, sqlite3.Error)
                                              else 'JOURNAL_INDEX_BUDGET_EXHAUSTED')
                raise SourceUnavailable('MASSIVE_STORAGE_CAPACITY') from None

    def _append_locked(self, raw, receipt):
        if self.read_only:
            raise ValueError('JOURNAL_READ_ONLY')
        if self.session is not None and receipt.get('event', {}).get('session') != self.session:
            raise ValueError('JOURNAL_RECEIPT_SESSION_MISMATCH')
        # A crash between these commits leaves orphan evidence, never an index
        # entry pointing at uncommitted bytes. Retrying the receipt is idempotent.
        if self.storage_stopped:
            raise SourceUnavailable('MASSIVE_STORAGE_CAPACITY')
        with self._connect(index_limit=self._normal_index_limit) as db:
            self._check_receipt_session(db, receipt)
            self._require_clock_schema(db)
            if self._terminal_exists(db) and db.execute('SELECT 1 FROM terminal_receipts LIMIT 1').fetchone():
                self.storage_stopped = True
                raise SourceUnavailable('MASSIVE_STORAGE_CAPACITY')
        self.spool(raw, receipt)
        digest = hashlib.sha256(canonical(receipt)).hexdigest()
        with self._connect(index_limit=self._normal_index_limit) as db:
            self._check_receipt_session(db, receipt)
            db.execute('INSERT OR IGNORE INTO receipts(digest) VALUES (?)', (digest,))
            sequence = db.execute('SELECT sequence FROM receipts WHERE digest=?', (digest,)).fetchone()[0]
            self._insert_clock(db, sequence, receipt, digest)
            return sequence

    @staticmethod
    def _terminal_exists(db):
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='terminal_receipts'").fetchone() is not None

    def configure_storage_reserve(self, symbols, *, session):
        """Reserve bounded index pages before opening a provider connection.

        Terminal gap receipts live inside the existing 64MiB index budget and
        are inserted atomically. They never need the potentially full spool.
        """
        from .r2d2_v2_minute_bars import _SYMBOL
        if (type(symbols) is not list or not 0 < len(symbols) <= 550 or len(set(symbols)) != len(symbols)
                or not all(type(symbol) is str and _SYMBOL.fullmatch(symbol) for symbol in symbols)
                or type(session) is not str or date.fromisoformat(session).isoformat() != session
                or self.session is not None and session != self.session):
            raise ValueError('JOURNAL_STORAGE_RESERVE_SCOPE')
        if self.read_only:
            raise ValueError('JOURNAL_READ_ONLY')
        with journal_access(self.path.parent):
            with self._connect() as db:
                page_size = db.execute('PRAGMA page_size').fetchone()[0]
                # Four pages per <=1024-byte receipt plus small-tree roots;
                # normal appends cannot spend this reserve. No cap is raised.
                reserved = (len(symbols) + 2) * 4 * page_size
                normal = self.max_index_bytes - reserved
                if normal < 16384:
                    raise ValueError('JOURNAL_STORAGE_RESERVE_UNAVAILABLE')
                db.execute('CREATE TABLE IF NOT EXISTS terminal_receipts ('
                           'sequence INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL, '
                           'payload BLOB NOT NULL CHECK(length(payload)<=1024))')
                self.storage_stopped = db.execute('SELECT 1 FROM terminal_receipts LIMIT 1').fetchone() is not None
                if not self.storage_stopped and db.execute('PRAGMA page_count').fetchone()[0] * page_size > normal:
                    raise ValueError('JOURNAL_STORAGE_RESERVE_UNAVAILABLE')
            self._storage_symbols = tuple(sorted(symbols))
            self._storage_session = session
            self._normal_index_limit = normal

    def _persist_storage_failure(self, failed_receipt, reason):
        from .r2d2_v2_sources import _time, _validate_event
        from zoneinfo import ZoneInfo
        at = _time(failed_receipt['event']['available_at'])
        if at.astimezone(ZoneInfo('America/New_York')).date().isoformat() != self._storage_session:
            raise ValueError('JOURNAL_STORAGE_FAILURE_SESSION')
        batch = []
        for symbol in self._storage_symbols:
            event = {'type': 'DATA_GAP', 'at': at.isoformat(), 'available_at': at.isoformat(),
                     'session': self._storage_session, 'instrument_key': 'US:' + symbol,
                     'reason': 'MASSIVE_STORAGE_CAPACITY'}
            _validate_event(event, at)
            receipt = {'event': event, 'provenance': 'MASSIVE_STREAM_STORAGE_CAPACITY', 'failure': reason}
            data = canonical(receipt)
            if len(data) > 1024:
                raise ValueError('JOURNAL_TERMINAL_RECEIPT_LIMIT')
            batch.append((hashlib.sha256(data).hexdigest(), data))
        with self._connect() as db:
            if not self._terminal_exists(db):
                raise ValueError('JOURNAL_STORAGE_RESERVE_MISSING')
            if not db.execute('SELECT 1 FROM terminal_receipts LIMIT 1').fetchone():
                _, high = self._bounds(db)
                for index, (digest, data) in enumerate(batch, 1):
                    db.execute('INSERT INTO terminal_receipts(sequence,digest,payload) VALUES (?,?,?)',
                               (high + index, digest, data))
                    self._insert_clock(db, high + index, _load_json(data), digest)
        self.storage_stopped = True

    @staticmethod
    def _create_clock_schema(db):
        db.execute('CREATE TABLE receipt_clocks ('
                   'sequence INTEGER PRIMARY KEY, received_us INTEGER, proof BLOB NOT NULL CHECK(length(proof)=32))')

    @staticmethod
    def _require_clock_schema(db):
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='receipt_clocks'").fetchone() is None:
            raise ValueError('JOURNAL_CLOCK_MIGRATION_REQUIRED')

    @staticmethod
    def _receipt_us(receipt):
        from .r2d2_v2_sources import _time
        # Legacy generic evidence may lack a receipt clock. Preserve it as
        # unknown; it can never supply a verified reader frontier.
        if receipt.get('event', {}).get('available_at') is None:
            return None
        delta = _time(receipt['event']['available_at']) - datetime(1970, 1, 1, tzinfo=timezone.utc)
        return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds

    @staticmethod
    def _clock_proof(sequence, received, digest):
        return hashlib.sha256(canonical(['MASSIVE_RECEIPT_CLOCK_V1', sequence, received, digest])).digest()

    @classmethod
    def _insert_clock(cls, db, sequence, receipt, digest):
        cls._require_clock_schema(db)
        received = cls._receipt_us(receipt)
        proof = cls._clock_proof(sequence, received, digest)
        db.execute('INSERT OR IGNORE INTO receipt_clocks(sequence,received_us,proof) VALUES (?,?,?)',
                   (sequence, received, proof))
        if db.execute('SELECT received_us,proof FROM receipt_clocks WHERE sequence=?', (sequence,)).fetchone() != (received, proof):
            raise ValueError('JOURNAL_CLOCK_MISMATCH')

    def migrate_receipt_clocks(self):
        """Explicit offline migration: verify all retained evidence, then commit
        clocks atomically. Readers never create metadata or silently migrate.
        The same index cap applies; any failed verification rolls back the table.
        """
        if self.read_only:
            raise ValueError('JOURNAL_READ_ONLY')
        with journal_access(self.path.parent, exclusive=True):
            with self._connect_locked() as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='receipt_clocks'").fetchone():
                    raise ValueError('JOURNAL_CLOCK_MIGRATION_ALREADY_PRESENT')
                db.execute('BEGIN IMMEDIATE')
                self._create_clock_schema(db)
                floor, high = self._bounds(db)
                position = floor
                while position < high:
                    page = self._page_locked(position, through=high, limit=4096)
                    if not page['records']:
                        raise ValueError('JOURNAL_CLOCK_MIGRATION_NO_PROGRESS')
                    for record in page['records']:
                        if self._receipt_us(record['receipt']) is None:
                            raise ValueError('JOURNAL_CLOCK_MIGRATION_UNKNOWN_CLOCK')
                        self._insert_clock(db, record['sequence'], record['receipt'], record['receipt_sha256'])
                    position = page['after']
                return high - floor

    def receipt_horizon(self, after, *, through):
        """Strict lower frontier of every unread receipt in a frozen snapshot.

        Integer UTC clocks commit with their sequence, even when the wall clock
        reverses. A range completeness check and verified minimum witness keep
        missing/corrupt metadata from becoming a timeout frontier.
        """
        with journal_access(self.path.parent):
            with self._connect_locked() as db:
                self._require_clock_schema(db)
                floor, high = self._bounds(db)
                if (type(after) is not int or type(through) is not int
                        or not floor <= after <= through <= high):
                    raise ValueError('JOURNAL_HORIZON')
                joins = 'LEFT JOIN receipts r ON c.sequence=r.sequence '
                digest_column = 'r.digest'
                if self._terminal_exists(db):
                    joins += 'LEFT JOIN terminal_receipts t ON c.sequence=t.sequence '
                    digest_column = 'CASE WHEN r.digest IS NOT NULL AND t.digest IS NOT NULL THEN NULL ELSE COALESCE(r.digest,t.digest) END'
                # Primary-key lookups avoid materializing a UNION of the full
                # receipt history merely to verify a small unread suffix.
                rows = db.execute('SELECT c.sequence,c.received_us,c.proof,' + digest_column +
                                  ' FROM receipt_clocks c ' + joins +
                                  'WHERE c.sequence>? AND c.sequence<=? ORDER BY c.sequence', (after, through))
                minimum = None
                expected = after + 1
                # Verify every persisted binding, including non-minimal clocks:
                # a corrupt larger clock must not hide the real suffix minimum.
                # This is a streaming range scan, never an in-memory backlog.
                for sequence, received, proof, digest in rows:
                    if (sequence != expected or type(received) is not int or type(digest) is not str
                            or proof != self._clock_proof(sequence, received, digest)):
                        raise ValueError('JOURNAL_CLOCK_MISMATCH')
                    expected += 1
                    if minimum is None or received < minimum[1]:
                        minimum = (sequence, received)
                if expected != through + 1:
                    raise ValueError('JOURNAL_CLOCK_INCOMPLETE')
            if minimum is None:
                return None
            sequence, received = minimum
            if type(sequence) is not int or type(received) is not int:
                raise ValueError('JOURNAL_CLOCK_INVALID')
            witness = self._page_locked(sequence-1, through=sequence, limit=1)['records']
            if len(witness) != 1 or self._receipt_us(witness[0]['receipt']) != received:
                raise ValueError('JOURNAL_CLOCK_MISMATCH')
            return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=received-1)

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

    def _check_receipt_session(self, db, receipt):
        if self.session is not None and receipt.get('event', {}).get('session') != self.session:
            raise ValueError('JOURNAL_RECEIPT_SESSION_MISMATCH')
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
        relation = 'SELECT sequence FROM receipts'
        if MassiveJournal._terminal_exists(db):
            relation += ' UNION ALL SELECT sequence FROM terminal_receipts'
        low, high = db.execute('SELECT MIN(sequence),MAX(sequence) FROM (' + relation + ')').fetchone()
        if low is None:
            if floor != 0: raise ValueError('JOURNAL_RETENTION_STATE')
            high = 0
        elif low != floor + 1:
            raise ValueError('JOURNAL_SEQUENCE_GAP')
        return floor, high

    def retention_cutoff(self):
        with journal_access(self.path.parent):
            return self._retention_cutoff_locked()

    def _retention_cutoff_locked(self):
        with self._connect_locked() as db:
            self._bounds(db)
            return db.execute('SELECT retain_from_session FROM retention_state WHERE singleton=1').fetchone()[0]

    def retention_floor(self):
        with journal_access(self.path.parent):
            return self._retention_floor_locked()

    def _retention_floor_locked(self):
        with self._connect_locked() as db:
            return self._bounds(db)[0]

    def page(self, after=0, *, through=None, limit=1024, byte_limit=4*1024*1024):
        with journal_access(self.path.parent):
            return self._page_locked(after, through=through, limit=limit, byte_limit=byte_limit)

    def _page_locked(self, after=0, *, through=None, limit=1024, byte_limit=4*1024*1024):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 4096:
            raise ValueError('JOURNAL_PAGE_LIMIT')
        if type(byte_limit) is not int or not 1 <= byte_limit <= 16*1024*1024:
            raise ValueError('JOURNAL_BYTE_LIMIT')
        with self._connect_locked() as db:
            floor, high = self._bounds(db)
            if after < floor:
                raise ValueError('JOURNAL_CURSOR_PRUNED')
            through = high if through is None else through
            if type(through) is not int or not after <= through <= high:
                raise ValueError('JOURNAL_HORIZON')
            relation = 'SELECT sequence,digest,NULL AS payload FROM receipts'
            if self._terminal_exists(db):
                relation += ' UNION ALL SELECT sequence,digest,payload FROM terminal_receipts'
            has_clocks = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='receipt_clocks'").fetchone() is not None
            rows = db.execute('SELECT sequence,digest,payload FROM (' + relation + ') '
                              'WHERE sequence>? AND sequence<=? ORDER BY sequence LIMIT ?',
                              (after, through, limit)).fetchall()
            clocks = {sequence: (received, proof) for sequence, received, proof in db.execute(
                'SELECT sequence,received_us,proof FROM receipt_clocks WHERE sequence>? AND sequence<=?',
                (after, rows[-1][0] if rows else after))} if has_clocks else None
        result=[];used=0;position=after;verified_raw={}
        for sequence,digest,inline in rows:
            if sequence != position + 1:
                raise ValueError('JOURNAL_SEQUENCE_GAP')
            if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('JOURNAL_RECEIPT_HASH')
            if inline is None:
                path=self.spool.root/'receipts'/(digest+'.json')
                if path.is_symlink() or not path.is_file() or path.stat().st_size > byte_limit:
                    raise ValueError('JOURNAL_RECEIPT_LIMIT')
                data=self._read_evidence_locked('receipts', digest+'.json', byte_limit, 'JOURNAL_RECEIPT_LIMIT')
            else:
                if type(inline) is not bytes or not 0 < len(inline) <= min(1024, byte_limit):
                    raise ValueError('JOURNAL_TERMINAL_RECEIPT_LIMIT')
                data = inline
            if hashlib.sha256(data).hexdigest()!=digest:
                raise ValueError('JOURNAL_RECEIPT_HASH')
            if used + len(data) > byte_limit:
                break
            receipt=_load_json(data)
            if clocks is not None:
                received = self._receipt_us(receipt)
                if clocks.get(sequence) != (received, self._clock_proof(sequence, received, digest)):
                    raise ValueError('JOURNAL_CLOCK_MISMATCH')
            if inline is not None and (receipt.get('provenance') != 'MASSIVE_STREAM_STORAGE_CAPACITY'
                    or receipt.get('event', {}).get('type') != 'DATA_GAP'
                    or receipt.get('event', {}).get('reason') != 'MASSIVE_STORAGE_CAPACITY'
                    or receipt.get('raw_sha256') is not None):
                raise ValueError('JOURNAL_TERMINAL_RECEIPT_INVALID')
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
                    raw_data=self._read_evidence_locked('raw', raw_hash+'.json', size, 'JOURNAL_RAW_SIZE')
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
