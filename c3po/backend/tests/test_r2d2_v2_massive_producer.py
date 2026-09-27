import fcntl
from test_r2d2_v2_minute_bars import MINUTE,calendar
from app.r2d2_v2_massive_producer import run_producer
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_sources import SourceUnavailable
import pytest


class Socket:
 def send(self,value):pass
 def close(self):pass


def invoke(root,calendar,connector):
 return run_producer(root,['AAPL'],calendar,'offline-fixture-token',utcnow=lambda:MINUTE,
     monotonic=lambda:0,stop=lambda:True,connector=connector)


def test_single_owner_refuses_before_any_connection(tmp_path,calendar):
 root=tmp_path.resolve()
 with (root/'producer.lock').open('w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  def forbidden(*args,**kwargs):raise AssertionError('must not connect')
  with pytest.raises(SourceUnavailable,match='ALREADY_RUNNING'):invoke(root,calendar,forbidden)
 assert not (root/'sequence.sqlite3').exists()


def test_restart_emits_gap_and_single_connection_without_replay(tmp_path,calendar):
 root=tmp_path.resolve();calls=[]
 def connect(*args,**kwargs):calls.append(1);return Socket()
 assert invoke(root,calendar,connect)=={'status':'STOPPED','recovered_records':0}
 result=invoke(root,calendar,connect)
 assert result['status']=='STOPPED' and result['recovered_records']==1
 records=MassiveJournal.open_reader(root).page()['records']
 reasons=[r['receipt']['event']['reason'] for r in records]
 assert 'MASSIVE_PRODUCER_RESTART' in reasons
 assert all(r['receipt']['event']['type']=='DATA_GAP' for r in records)
 assert len(calls)==2


@pytest.mark.parametrize('kind', ['fifo', 'symlink', 'hardlink', 'public'])
def test_unsafe_lock_refuses_before_journal_or_connection(tmp_path, calendar, kind):
 import os
 root=tmp_path.resolve();lock=root/'producer.lock';external=root/'external'
 external.write_bytes(b'preserve');external.chmod(0o600)
 if kind=='fifo':os.mkfifo(lock,0o600)
 elif kind=='symlink':lock.symlink_to(external)
 elif kind=='hardlink':os.link(external,lock)
 else:lock.write_bytes(b'');lock.chmod(0o644)
 def forbidden(*args,**kwargs):raise AssertionError('must not connect')
 with pytest.raises(SourceUnavailable,match='LOCK_UNSAFE'):invoke(root,calendar,forbidden)
 assert not (root/'sequence.sqlite3').exists()
 assert external.read_bytes()==b'preserve'


def test_replaced_lock_after_acquire_refuses_before_journal(tmp_path,calendar,monkeypatch):
 root=tmp_path.resolve();original=fcntl.flock
 def swap(fd,operation):
  original(fd,operation)
  (root/'producer.lock').rename(root/'old.lock')
  (root/'producer.lock').touch(mode=0o600)
 monkeypatch.setattr('app.r2d2_v2_massive_producer.fcntl.flock',swap)
 def forbidden(*args,**kwargs):raise AssertionError('must not connect')
 with pytest.raises(SourceUnavailable,match='LOCK_CHANGED'):invoke(root,calendar,forbidden)
 assert not (root/'sequence.sqlite3').exists()
