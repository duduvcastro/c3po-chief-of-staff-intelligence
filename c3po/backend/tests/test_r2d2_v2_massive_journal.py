import pytest
from app.r2d2_v2_massive_journal import MassiveJournal
from test_r2d2_v2_massive_spool import evidence


def test_restart_retry_and_snapshot_horizon(tmp_path):
 j=MassiveJournal(tmp_path);raw,receipt=evidence()
 assert j(raw,receipt)==1
 j=MassiveJournal(tmp_path);assert j(raw,receipt)==1
 first=j.page();assert first['after']==1
 assert j(None,{'event':{'type':'DATA_GAP','reason':'fixture'}})==2
 assert not j.page(after=1,through=first['through'])['records']
 assert j.page(after=1)['records'][0]['sequence']==2


def test_more_than_4096_receipts_without_legacy_file_scan(tmp_path):
 j=MassiveJournal(tmp_path)
 # Exercise the sequence reader beyond the legacy directory-count limit.
 for i in range(4100):
  j(None,{'event':{'type':'DATA_GAP','fixture':i}})
 cursor=0;seen=[]
 while True:
  page=j.page(cursor,limit=550)
  seen.extend(r['sequence'] for r in page['records']);cursor=page['after']
  if not page['has_more']:break
 assert seen==list(range(1,4101))


def test_corrupt_raw_refuses_page_without_acknowledgement(tmp_path):
 j=MassiveJournal(tmp_path);raw,r=evidence();j(raw,r)
 (tmp_path/'raw'/(r['raw_sha256']+'.json')).write_bytes(b'x'*len(raw))
 with pytest.raises(ValueError,match='RAW_HASH'):j.page()


def test_receipt_storage_failure_does_not_index(tmp_path,monkeypatch):
 j=MassiveJournal(tmp_path)
 def fail(*args):raise OSError('disk full')
 monkeypatch.setattr(j,'spool',fail)
 with pytest.raises(OSError):j(*evidence())
 assert j.page()['through']==0


def test_shared_raw_verified_once_within_page_byte_budget(tmp_path,monkeypatch):
 from pathlib import Path
 from app.r2d2_v2_sources import canonical
 j=MassiveJournal(tmp_path);raw,r=evidence();other={**r,'fixture':2}
 j(raw,r);j(raw,other);reads=[];original=j._read_evidence_locked
 def read(directory,*args):
  if directory=='raw':reads.append(directory)
  return original(directory,*args)
 monkeypatch.setattr(j,'_read_evidence_locked',read)
 budget=len(raw)+len(canonical(r))+len(canonical(other))
 assert len(j.page(byte_limit=budget)['records'])==2
 assert len(reads)==1
 with pytest.raises(ValueError,match='BYTE_LIMIT'):j.page(byte_limit=len(canonical(r))+len(raw)-1)


def test_database_digest_path_is_rejected_before_file_read(tmp_path):
 j=MassiveJournal(tmp_path);j(*evidence())
 with j._connect() as db:db.execute("UPDATE receipts SET digest='../outside'")
 with pytest.raises(ValueError,match='RECEIPT_HASH'):j.page()


def test_raw_fifo_refuses_without_opening(tmp_path):
 import os
 j=MassiveJournal(tmp_path);raw,r=evidence();j(raw,r)
 path=tmp_path/'raw'/(r['raw_sha256']+'.json');path.unlink();os.mkfifo(path,0o600)
 with pytest.raises(ValueError,match='RAW_SIZE'):j.page()


def test_sqlite_capacity_refuses_without_sequence_hole(tmp_path):
 import sqlite3
 j=MassiveJournal(tmp_path,max_index_bytes=32768)
 committed=0
 for i in range(500):
  receipt={'event':{'type':'DATA_GAP','fixture':i}}
  try:
   sequence=j(None,receipt)
  except sqlite3.OperationalError as exc:
   assert 'full' in str(exc).lower()
   break
  committed+=1
  assert sequence==committed
 else:
  pytest.fail('small index must exhaust')
 assert committed>0
 assert j.path.stat().st_size<=32768
 reader=MassiveJournal.open_reader(tmp_path)
 assert reader.page()['through']==committed
 # An interrupted/failed insertion may leave raw receipts; reopening must
 # preserve all committed sequence positions and accept an exact old retry.
 reopened=MassiveJournal(tmp_path,max_index_bytes=32768)
 assert reopened(None,{'event':{'type':'DATA_GAP','fixture':0}})==1
 assert reopened.page()['through']==committed


@pytest.mark.parametrize('replacement',['symlink','fifo','oversized'])
def test_raw_replaced_after_stat_refuses_without_cursor(tmp_path,monkeypatch,replacement):
 import os
 j=MassiveJournal(tmp_path);raw,r=evidence();j(raw,r)
 path=tmp_path/'raw'/(r['raw_sha256']+'.json');original=j._read_evidence_locked
 def read(directory,*args):
  if directory=='raw':
   path.unlink()
   if replacement=='fifo':os.mkfifo(path,0o600)
   elif replacement=='symlink':
    outside=tmp_path/'outside';outside.write_bytes(raw);path.symlink_to(outside)
   else:path.write_bytes(raw+b'x')
  return original(directory,*args)
 monkeypatch.setattr(j,'_read_evidence_locked',read)
 with pytest.raises(ValueError,match='RAW_SIZE'):j.page()
 with j._connect() as db:assert db.execute('SELECT MAX(sequence) FROM receipts').fetchone()[0]==1


def test_parent_replaced_by_symlink_before_read_refuses(tmp_path,monkeypatch):
 j=MassiveJournal(tmp_path);j(*evidence());original=j._read_evidence_locked
 def read(directory,*args):
  if directory=='receipts':
   (tmp_path/'receipts').rename(tmp_path/'moved')
   (tmp_path/'receipts').symlink_to(tmp_path/'moved',target_is_directory=True)
  return original(directory,*args)
 monkeypatch.setattr(j,'_read_evidence_locked',read)
 with pytest.raises(ValueError,match='RECEIPT_LIMIT'):j.page()


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'hardlink', 'public'])
def test_unsafe_existing_sqlite_refuses_before_connect(tmp_path, monkeypatch, kind):
 import os
 import app.r2d2_v2_massive_journal as module
 path=tmp_path/'sequence.sqlite3'
 outside=tmp_path/'outside';outside.write_bytes(b'preserve');outside.chmod(0o600)
 if kind=='symlink':path.symlink_to(outside)
 elif kind=='fifo':os.mkfifo(path,0o600)
 elif kind=='hardlink':os.link(outside,path)
 else:path.write_bytes(b'');path.chmod(0o644)
 def forbidden(*args,**kwargs):pytest.fail('unsafe index reached SQLite')
 monkeypatch.setattr(module.sqlite3,'connect',forbidden)
 with pytest.raises(ValueError,match='INDEX_UNSAFE'):MassiveJournal(tmp_path)
 assert outside.read_bytes()==b'preserve'


@pytest.mark.parametrize('suffix', ['-journal', '-wal', '-shm'])
def test_unsafe_sqlite_sidecar_refuses_before_connect(tmp_path, monkeypatch, suffix):
 import app.r2d2_v2_massive_journal as module
 journal=MassiveJournal(tmp_path)
 outside=tmp_path/'outside';outside.write_bytes(b'preserve')
 (tmp_path/('sequence.sqlite3'+suffix)).symlink_to(outside)
 def forbidden(*args,**kwargs):pytest.fail('unsafe sidecar reached SQLite')
 monkeypatch.setattr(module.sqlite3,'connect',forbidden)
 with pytest.raises(ValueError,match='INDEX_UNSAFE'):journal.page()
 assert outside.read_bytes()==b'preserve'


def test_reader_refuses_replaced_index(tmp_path):
 journal=MassiveJournal(tmp_path);journal(*evidence())
 reader=MassiveJournal.open_reader(tmp_path)
 path=tmp_path/'sequence.sqlite3';saved=tmp_path/'saved.sqlite3'
 path.rename(saved);path.write_bytes(saved.read_bytes());path.chmod(0o600)
 with pytest.raises(ValueError,match='INDEX_CHANGED'):reader.page()


def test_replaced_parent_refuses_bound_reader(tmp_path):
 root=tmp_path/'root';journal=MassiveJournal(root)
 reader=MassiveJournal.open_reader(root)
 root.rename(tmp_path/'old');MassiveJournal(root)
 with pytest.raises(ValueError,match='ROOT_CHANGED'):reader.page()
