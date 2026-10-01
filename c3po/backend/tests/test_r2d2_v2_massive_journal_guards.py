"""Real tempfiles/SQLite/flock; synthetic effective UID only in owner mismatch test."""
import hashlib,os,sqlite3
from pathlib import Path
import pytest
from app.r2d2_v2_massive_sessions import SessionJournalRoot
from app.r2d2_v2_massive_maintenance import journal_access
from app.r2d2_v2_sources import SourceUnavailable
EPOCH='R2D2-V2-SHADOW-GUARD-PROOF'
DAY='2026-10-05'

def files(root):return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
@pytest.fixture
def catalog(tmp_path):
 root=tmp_path.resolve()/'journal';root.mkdir(mode=0o700)
 c=SessionJournalRoot(root,EPOCH,create=True);c.ensure_session(DAY,['AAPL']);return c

def test_owner_mismatch_refuses_even_with_actual_private_modes(catalog,monkeypatch):
 root=catalog.root;before=files(root);actual=os.geteuid()
 assert root.stat().st_uid==actual and root.stat().st_mode&0o777==0o700
 # Real file ownership remains untouched: simulate the reader's other namespace UID.
 with monkeypatch.context() as m:
  m.setattr(os,'geteuid',lambda:actual+1)
  with pytest.raises(SourceUnavailable,match='MASSIVE_SESSION_ROOT_OWNER'):SessionJournalRoot(root,EPOCH)
 assert files(root)==before

def test_private_root_and_index_guards_are_not_relaxed(catalog):
 root=catalog.root;before=files(root);root.chmod(0o750)
 try:
  with pytest.raises(SourceUnavailable,match='SOURCE_DIRECTORY_NOT_PRIVATE'):SessionJournalRoot(root,EPOCH)
 finally:root.chmod(0o700)
 index=catalog.session_path(DAY)/'sequence.sqlite3';index.chmod(0o640)
 try:
  with pytest.raises(ValueError,match='JOURNAL_INDEX_UNSAFE'):catalog.open_session(DAY)
 finally:index.chmod(0o600)
 assert files(root)==before

def test_wrong_path_refuses_without_creating_or_copying_catalog(catalog,tmp_path):
 wrong=tmp_path.resolve()/'wrong-mount';wrong.mkdir(mode=0o700);before=files(catalog.root)
 with pytest.raises(SourceUnavailable):SessionJournalRoot(wrong,EPOCH)
 assert list(wrong.iterdir())==[] and files(catalog.root)==before
 # Repointing an already bound object to another valid same-epoch directory also refuses identity.
 other=tmp_path.resolve()/'different-root';other.mkdir(mode=0o700);SessionJournalRoot(other,EPOCH,create=True)
 old=catalog.root;catalog.root=other
 try:
  with pytest.raises(SourceUnavailable,match='MASSIVE_SESSION_ROOT_CHANGED'):catalog.sessions()
 finally:catalog.root=old

def test_reader_sqlite_ro_and_shared_locks_preserve_evidence(catalog):
 before=files(catalog.root);reader=catalog.open_session(DAY);assert reader.read_only is True
 child=catalog.session_path(DAY)
 with journal_access(child):
  with journal_access(child):
   with reader._connect() as db:
    assert db.execute('SELECT COUNT(*) FROM receipts').fetchone()==(0,)
    with pytest.raises(sqlite3.OperationalError,match='readonly'):
     db.execute('CREATE TABLE must_not_exist(x)')
   with pytest.raises(SourceUnavailable,match='MASSIVE_MAINTENANCE_BUSY'):
    with journal_access(child,exclusive=True):pass
 with journal_access(child,exclusive=True):pass
 assert files(catalog.root)==before
