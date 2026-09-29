import json
from datetime import timedelta
import pytest
from test_r2d2_v2_minute_bars import MINUTE,calendar
from test_r2d2_v2_massive_stream import bar
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_stream import MassiveStreamState
from app.r2d2_v2_massive_recovery import restore_stream
from app.r2d2_v2_sources import SourceUnavailable


def test_restart_recovers_observed_and_missing_minutes_without_reemission(tmp_path,calendar):
 j=MassiveJournal(tmp_path);s=MassiveStreamState(['AAPL','MSFT'],calendar,j)
 s.connected(MINUTE-timedelta(seconds=1));s.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 s.expire_minute(MINUTE,MINUTE+timedelta(seconds=151));before=j.page()['through']
 restored=MassiveStreamState(['AAPL','MSFT'],calendar,MassiveJournal(tmp_path))
 result=restore_stream(restored,MassiveJournal.open_reader(tmp_path.resolve()),session=MINUTE.date().isoformat())
 assert result=={'records':2,'observed_minutes':1,'sealed_minutes':1}
 assert restored.connected_at is None and restored.seen==s.seen and restored.sealed==s.sealed
 restored.expire_minute(MINUTE,MINUTE+timedelta(seconds=155))
 assert j.page()['through']==before


def test_wrong_session_does_not_partially_restore(tmp_path,calendar):
 j=MassiveJournal(tmp_path);s=MassiveStreamState(['AAPL'],calendar,j)
 s.expire_minute(MINUTE,MINUTE+timedelta(seconds=151))
 restored=MassiveStreamState(['AAPL'],calendar,j)
 with pytest.raises(SourceUnavailable,match='SESSION_MISMATCH'):
  restore_stream(restored,j,session='2026-09-01')
 assert not restored.seen and not restored.sealed and restored.connected_at is None


def test_invalid_bar_recovery_seals_original_minute_not_reception_minute(tmp_path,calendar):
 j=MassiveJournal(tmp_path);s=MassiveStreamState(['AAPL'],calendar,j)
 s.connected(MINUTE-timedelta(seconds=1))
 s.frame(json.dumps([bar(o=-1)]).encode(),MINUTE+timedelta(seconds=65))
 restored=MassiveStreamState(['AAPL'],calendar,j)
 restore_stream(restored,j,session=MINUTE.date().isoformat())
 assert restored.sealed=={('AAPL',int(MINUTE.timestamp()*1000))}


def test_550_observations_recovered_without_duplicate_expiry(tmp_path,calendar):
 names=['S'+str(i) for i in range(550)];j=MassiveJournal(tmp_path)
 s=MassiveStreamState(names,calendar,j);s.connected(MINUTE-timedelta(seconds=1))
 s.frame(json.dumps([bar(n) for n in names]).encode(),MINUTE+timedelta(seconds=65))
 restored=MassiveStreamState(names,calendar,MassiveJournal(tmp_path))
 stats=restore_stream(restored,MassiveJournal.open_reader(tmp_path.resolve()),session=MINUTE.date().isoformat())
 assert stats['observed_minutes']==550 and restored.seen==s.seen
 assert restored.connected_at is None
 restored.expire_minute(MINUTE,MINUTE+timedelta(seconds=151))
 assert j.page()['through']==550


def test_restart_prunes_old_550_symbol_state_but_never_refills_it(tmp_path,calendar):
 names=['S'+str(i) for i in range(550)];j=MassiveJournal(tmp_path)
 s=MassiveStreamState(names,calendar,j)
 for offset in range(10):
  minute=MINUTE+timedelta(minutes=offset)
  s.expire_minute(minute,minute+timedelta(seconds=151))
 now=MINUTE+timedelta(minutes=12)
 restored=MassiveStreamState(names,calendar,j)
 stats=restore_stream(restored,j,session=MINUTE.date().isoformat(),now=now)
 assert stats['records']==5500 and stats['sealed_minutes']==550
 assert restored.reject_before_ms==int((MINUTE+timedelta(minutes=9)).timestamp()*1000)
 assert restored.connected_at is None
 before=j.page()['through']
 restored.connected(now)
 restored.frame(json.dumps([bar(n) for n in names]).encode(),now)
 restored.expire_minute(MINUTE,now)
 assert j.page()['through']==before


def test_restart_future_receipt_does_not_publish_partial_state(tmp_path,calendar):
 j=MassiveJournal(tmp_path);s=MassiveStreamState(['AAPL'],calendar,j)
 s.expire_minute(MINUTE,MINUTE+timedelta(seconds=151))
 restored=MassiveStreamState(['AAPL'],calendar,j)
 with pytest.raises(SourceUnavailable,match='FUTURE_EVIDENCE'):
  restore_stream(restored,j,session=MINUTE.date().isoformat(),now=MINUTE+timedelta(seconds=80))
 assert not restored.seen and not restored.sealed and restored.reject_before_ms is None


@pytest.mark.parametrize('replacement',['symlink','fifo','changed'])
def test_raw_replacement_after_page_verification_refuses_recovery(tmp_path,calendar,monkeypatch,replacement):
 import os
 journal=MassiveJournal(tmp_path);state=MassiveStreamState(['AAPL'],calendar,journal)
 state.connected(MINUTE-timedelta(seconds=1))
 state.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 original=journal.page
 def page(*args,**kwargs):
  result=original(*args,**kwargs)
  digest=result['records'][0]['receipt']['raw_sha256']
  path=tmp_path/'raw'/(digest+'.json');data=path.read_bytes();path.unlink()
  if replacement=='fifo':os.mkfifo(path,0o600)
  elif replacement=='symlink':
   outside=tmp_path/'outside';outside.write_bytes(data);outside.chmod(0o600);path.symlink_to(outside)
  else:path.write_bytes(b' '*len(data));path.chmod(0o600)
  return result
 monkeypatch.setattr(journal,'page',page)
 restored=MassiveStreamState(['AAPL'],calendar,journal)
 with pytest.raises((SourceUnavailable,ValueError),match='RECOVERY_RAW'):
  restore_stream(restored,journal,session=MINUTE.date().isoformat())
 assert not restored.seen and not restored.sealed and restored.reject_before_ms is None


def test_recovery_verifies_shared_frame_once_per_page(tmp_path,calendar,monkeypatch):
 names=['S'+str(i) for i in range(550)]
 journal=MassiveJournal(tmp_path);state=MassiveStreamState(names,calendar,journal)
 state.connected(MINUTE-timedelta(seconds=1))
 state.frame(json.dumps([bar(n) for n in names]).encode(),MINUTE+timedelta(seconds=65))
 original=journal._read_evidence_locked;reads=[]
 def read(directory,*args):
  if directory=='raw':reads.append(args)
  return original(directory,*args)
 monkeypatch.setattr(journal,'_read_evidence_locked',read)
 restored=MassiveStreamState(names,calendar,journal)
 result=restore_stream(restored,journal,session=MINUTE.date().isoformat())
 assert result['observed_minutes']==550
 assert len(reads)==2  # one page validation, one independent recovery validation


def test_explicit_next_session_recovery_verifies_history_without_restoring_old_minutes(tmp_path,calendar):
 j=MassiveJournal(tmp_path);state=MassiveStreamState(['AAPL'],calendar,j)
 state.connected(MINUTE-timedelta(seconds=1))
 state.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 state.expire_minute(MINUTE+timedelta(minutes=1),MINUTE+timedelta(minutes=3,seconds=31))
 now=MINUTE+timedelta(days=1)
 restored=MassiveStreamState(['AAPL'],calendar,j)
 before=j.page()['through']
 result=restore_stream(restored,j,session=now.date().isoformat(),now=now,allow_prior_sessions=True)
 assert result=={'records':2,'observed_minutes':0,'sealed_minutes':0}
 assert not restored.seen and not restored.sealed and restored.connected_at is None
 assert restored.reject_before_ms==int((now-timedelta(minutes=3)).timestamp()*1000)
 assert j.page()['through']==before
 restored.connected(now)
 restored.frame(json.dumps([bar()]).encode(),now)
 assert j.page()['through']==before


@pytest.mark.parametrize('current_symbol',['AAPL','MSFT'])
def test_next_session_recovery_still_refuses_corrupt_old_raw(tmp_path,calendar,current_symbol):
 j=MassiveJournal(tmp_path);state=MassiveStreamState(['AAPL'],calendar,j)
 state.connected(MINUTE-timedelta(seconds=1))
 state.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 record=j.page()['records'][0];path=tmp_path/'raw'/(record['receipt']['raw_sha256']+'.json')
 path.write_bytes(b'x'*path.stat().st_size)
 now=MINUTE+timedelta(days=1);restored=MassiveStreamState([current_symbol],calendar,j)
 with pytest.raises(ValueError,match='RAW_HASH'):
  restore_stream(restored,j,session=now.date().isoformat(),now=now,allow_prior_sessions=True)
 assert not restored.seen and not restored.sealed and restored.reject_before_ms is None


@pytest.mark.parametrize('now',[None,MINUTE])
def test_prior_session_policy_requires_bound_current_clock(tmp_path,calendar,now):
 j=MassiveJournal(tmp_path);state=MassiveStreamState(['AAPL'],calendar,j)
 with pytest.raises(SourceUnavailable,match='SESSION_CLOCK'):
  restore_stream(state,j,session=(MINUTE+timedelta(days=1)).date().isoformat(),now=now,allow_prior_sessions=True)
 assert state.reject_before_ms is None


def test_prior_session_policy_does_not_accept_future_session(tmp_path,calendar):
 j=MassiveJournal(tmp_path);state=MassiveStreamState(['AAPL'],calendar,j)
 state.expire_minute(MINUTE,MINUTE+timedelta(seconds=151))
 now=MINUTE-timedelta(days=1);restored=MassiveStreamState(['AAPL'],calendar,j)
 with pytest.raises(SourceUnavailable,match='SESSION_MISMATCH'):
  restore_stream(restored,j,session=now.date().isoformat(),now=now,allow_prior_sessions=True)
 assert not restored.seen and not restored.sealed


def test_prior_session_rotating_universe_is_verified_without_restoring_old_symbols(tmp_path,calendar):
 j=MassiveJournal(tmp_path);old=MassiveStreamState(['AAPL'],calendar,j)
 old.connected(MINUTE-timedelta(seconds=1))
 old.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 old.expire_minute(MINUTE+timedelta(minutes=1),MINUTE+timedelta(minutes=3,seconds=31))
 now=MINUTE+timedelta(days=1)
 restored=MassiveStreamState(['MSFT'],calendar,j)
 result=restore_stream(restored,j,session=now.date().isoformat(),now=now,allow_prior_sessions=True)
 assert result=={'records':2,'observed_minutes':0,'sealed_minutes':0}
 assert set(restored.symbols)=={'MSFT'}
 assert not restored.seen and not restored.sealed


def test_current_session_still_requires_current_universe_with_history_enabled(tmp_path,calendar):
 j=MassiveJournal(tmp_path);old=MassiveStreamState(['AAPL'],calendar,j)
 old.expire_minute(MINUTE,MINUTE+timedelta(seconds=151))
 restored=MassiveStreamState(['MSFT'],calendar,j)
 with pytest.raises(SourceUnavailable,match='UNIVERSE_MISMATCH'):
  restore_stream(restored,j,session=MINUTE.date().isoformat(),now=MINUTE+timedelta(minutes=2),allow_prior_sessions=True)
 assert not restored.seen and not restored.sealed and restored.reject_before_ms is None
