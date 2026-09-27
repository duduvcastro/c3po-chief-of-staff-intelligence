import os
import pytest
from app.r2d2_v2_massive_maintenance import journal_access
from app.r2d2_v2_sources import SourceUnavailable


def test_shared_readers_coexist_and_exclude_maintenance(tmp_path):
 with journal_access(tmp_path,create=True):
  with journal_access(tmp_path):
   with pytest.raises(SourceUnavailable,match='BUSY'):
    with journal_access(tmp_path,exclusive=True):pytest.fail('exclusive entered')
 with journal_access(tmp_path,exclusive=True):pass


def test_exclusive_maintenance_excludes_all_other_users(tmp_path):
 with journal_access(tmp_path,exclusive=True,create=True):
  for exclusive in (False,True):
   with pytest.raises(SourceUnavailable,match='BUSY'):
    with journal_access(tmp_path,exclusive=exclusive):pytest.fail('user entered')
 with journal_access(tmp_path):pass


@pytest.mark.parametrize('kind',['symlink','hardlink','fifo','public'])
def test_unsafe_lock_refuses(tmp_path,kind):
 target=tmp_path/'outside';target.write_bytes(b'preserve');target.chmod(0o600)
 lock=tmp_path/'maintenance.lock'
 if kind=='symlink':lock.symlink_to(target)
 elif kind=='hardlink':os.link(target,lock)
 elif kind=='fifo':os.mkfifo(lock,0o600)
 else:lock.touch(mode=0o644)
 with pytest.raises(SourceUnavailable,match='UNSAFE'):
  with journal_access(tmp_path,create=True):pytest.fail('unsafe entered')
 assert target.read_bytes()==b'preserve'


def test_reader_does_not_create_missing_lock(tmp_path):
 with pytest.raises(SourceUnavailable,match='UNSAFE'):
  with journal_access(tmp_path):pytest.fail('missing lock entered')
 assert not (tmp_path/'maintenance.lock').exists()


def test_lock_replacement_detected_on_exit(tmp_path):
 with pytest.raises(SourceUnavailable,match='CHANGED'):
  with journal_access(tmp_path,create=True):
   (tmp_path/'maintenance.lock').rename(tmp_path/'old.lock')
   (tmp_path/'maintenance.lock').touch(mode=0o600)


def test_exception_releases_lock(tmp_path):
 with pytest.raises(RuntimeError):
  with journal_access(tmp_path,exclusive=True,create=True):raise RuntimeError('fixture')
 with journal_access(tmp_path,exclusive=True):pass


def test_journal_operations_refuse_exclusive_maintenance(tmp_path):
 from app.r2d2_v2_massive_journal import MassiveJournal
 journal=MassiveJournal(tmp_path)
 reader=MassiveJournal.open_reader(tmp_path)
 before={p.name for p in tmp_path.iterdir()}
 with journal_access(tmp_path,exclusive=True):
  for operation in (lambda:journal(b'raw',{}),lambda:reader.page(),
                    lambda:reader.retention_floor(),lambda:MassiveJournal.open_reader(tmp_path)):
   with pytest.raises(SourceUnavailable,match='BUSY'):operation()
 assert {p.name for p in tmp_path.iterdir()}==before
 assert journal.page()['records']==[]


def test_append_holds_lock_across_spool_and_index(tmp_path,monkeypatch):
 from app.r2d2_v2_massive_journal import MassiveJournal
 journal=MassiveJournal(tmp_path)
 original=journal.spool
 def spool(raw,receipt):
  with pytest.raises(SourceUnavailable,match='BUSY'):
   with journal_access(tmp_path,exclusive=True):pytest.fail('maintenance entered mid-append')
  return original(raw,receipt)
 monkeypatch.setattr(journal,'spool',type('Spool',(),{'root':tmp_path,'__call__':staticmethod(spool)})())
 journal(None,{'event':{'type':'DATA_GAP'}})
 with journal_access(tmp_path,exclusive=True):pass


def test_page_holds_lock_while_reading_evidence(tmp_path,monkeypatch):
 import hashlib
 from app.r2d2_v2_massive_journal import MassiveJournal
 journal=MassiveJournal(tmp_path)
 raw=b'raw'
 journal(raw,{'raw_sha256':hashlib.sha256(raw).hexdigest(),'raw_bytes':len(raw)})
 original=journal._read_evidence_locked
 calls=[]
 def read(*args):
  with pytest.raises(SourceUnavailable,match='BUSY'):
   with journal_access(tmp_path,exclusive=True):pytest.fail('maintenance entered mid-page')
  calls.append(args[0])
  return original(*args)
 monkeypatch.setattr(journal,'_read_evidence_locked',read)
 assert len(journal.page()['records'])==1
 assert calls==['receipts','raw']
 with journal_access(tmp_path,exclusive=True):pass


def test_retention_scan_holds_lock_between_pages(tmp_path,monkeypatch):
 from app.r2d2_v2_massive_journal import MassiveJournal
 from app.r2d2_v2_massive_retention import plan_retention
 journal=MassiveJournal(tmp_path)
 for i in range(3):journal(None,{'event':{'type':'DATA_GAP','session':'2026-09-25','fixture':i}})
 original=journal.page
 calls=[]
 def page(*args,**kwargs):
  result=original(*args,**kwargs)
  with pytest.raises(SourceUnavailable,match='BUSY'):
   with journal_access(tmp_path,exclusive=True):pytest.fail('maintenance entered between scan pages')
  calls.append(result['after'])
  return result
 monkeypatch.setattr(journal,'page',page)
 plan=plan_retention(journal,committed_sequence=3,retain_from_session='2026-09-26')
 assert plan['prune_through']==2
 assert len(calls)==2
 with journal_access(tmp_path,exclusive=True):pass


def test_committed_retention_refuses_before_database_read(tmp_path,monkeypatch):
 from app.r2d2_v2_massive_journal import MassiveJournal
 from app import r2d2_v2_massive_retention as retention
 journal=MassiveJournal(tmp_path)
 def forbidden(*args,**kwargs):pytest.fail('database read during maintenance')
 monkeypatch.setattr(retention,'_committed_snapshot',forbidden)
 with journal_access(tmp_path,exclusive=True):
  with pytest.raises(SourceUnavailable,match='BUSY'):
   retention.plan_committed_retention(journal,None,epoch=28,release_sha='a'*64,
                                      now=None,retain_from_session='2026-09-26')
