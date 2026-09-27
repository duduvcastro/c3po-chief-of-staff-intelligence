"""Offline durable receipt sequence. Not yet wired to the collector.

Raw/receipt files commit before the sequence transaction. Readers propose a
position; this module never acknowledges on behalf of the collector.
"""
import hashlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from .r2d2_v2_massive_spool import MassiveSpool
from .r2d2_v2_sources import canonical, _load_json, _open_directory, _read_file, SourceUnavailable


class MassiveJournal:
    def __init__(self, root, *, max_index_bytes=64*1024*1024):
        if type(max_index_bytes) is not int or max_index_bytes < 16384:
            raise ValueError('JOURNAL_INDEX_BUDGET')
        self.max_index_bytes = max_index_bytes
        self.read_only = False
        self.spool = MassiveSpool(root)
        self.path = Path(root) / 'sequence.sqlite3'
        if self.path.is_symlink():
            raise ValueError('JOURNAL_SYMLINK')
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS receipts (sequence INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL)')
        self.path.chmod(0o600)

    @classmethod
    def open_reader(cls, root):
        obj = cls.__new__(cls)
        obj.read_only = True
        root = Path(root).absolute()
        if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
            raise ValueError('JOURNAL_READER_ROOT')
        obj.spool = SimpleNamespace(root=root)
        obj.path = root / 'sequence.sqlite3'
        if obj.path.is_symlink() or not obj.path.is_file():
            raise ValueError('JOURNAL_READER_MISSING')
        with obj._connect() as db:
            db.execute('SELECT sequence,digest FROM receipts LIMIT 0')
        return obj

    @contextmanager
    def _connect(self):
        db = (sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=2)
              if self.read_only else sqlite3.connect(self.path, timeout=2))
        try:
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
        finally:
            db.close()

    def __call__(self, raw, receipt):
        if self.read_only:
            raise ValueError('JOURNAL_READ_ONLY')
        # A crash between these commits leaves orphan evidence, never an index
        # entry pointing at uncommitted bytes. Retrying the receipt is idempotent.
        self.spool(raw, receipt)
        digest = hashlib.sha256(canonical(receipt)).hexdigest()
        with self._connect() as db:
            db.execute('INSERT OR IGNORE INTO receipts(digest) VALUES (?)', (digest,))
            return db.execute('SELECT sequence FROM receipts WHERE digest=?', (digest,)).fetchone()[0]

    def _read_evidence(self, directory, name, budget, code):
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

    def page(self, after=0, *, through=None, limit=1024, byte_limit=4*1024*1024):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 4096:
            raise ValueError('JOURNAL_PAGE_LIMIT')
        if type(byte_limit) is not int or not 1 <= byte_limit <= 16*1024*1024:
            raise ValueError('JOURNAL_BYTE_LIMIT')
        with self._connect() as db:
            high = db.execute('SELECT COALESCE(MAX(sequence),0) FROM receipts').fetchone()[0]
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
