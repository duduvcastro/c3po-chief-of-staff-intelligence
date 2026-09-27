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
 s.expire_minute(MINUTE,MINUTE+timedelta(seconds=91));before=j.page()['through']
 restored=MassiveStreamState(['AAPL','MSFT'],calendar,MassiveJournal(tmp_path))
 result=restore_stream(restored,MassiveJournal.open_reader(tmp_path.resolve()),session=MINUTE.date().isoformat())
 assert result=={'records':2,'observed_minutes':1,'sealed_minutes':1}
 assert restored.connected_at is None and restored.seen==s.seen and restored.sealed==s.sealed
 restored.expire_minute(MINUTE,MINUTE+timedelta(seconds=95))
 assert j.page()['through']==before


def test_wrong_session_does_not_partially_restore(tmp_path,calendar):
 j=MassiveJournal(tmp_path);s=MassiveStreamState(['AAPL'],calendar,j)
 s.expire_minute(MINUTE,MINUTE+timedelta(seconds=91))
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
 restored.expire_minute(MINUTE,MINUTE+timedelta(seconds=91))
 assert j.page()['through']==550


def test_restart_prunes_old_550_symbol_state_but_never_refills_it(tmp_path,calendar):
 names=['S'+str(i) for i in range(550)];j=MassiveJournal(tmp_path)
 s=MassiveStreamState(names,calendar,j)
 for offset in range(10):
  minute=MINUTE+timedelta(minutes=offset)
  s.expire_minute(minute,minute+timedelta(seconds=91))
 now=MINUTE+timedelta(minutes=11)
 restored=MassiveStreamState(names,calendar,j)
 stats=restore_stream(restored,j,session=MINUTE.date().isoformat(),now=now)
 assert stats['records']==5500 and stats['sealed_minutes']==1100
 assert restored.reject_before_ms==int((MINUTE+timedelta(minutes=8)).timestamp()*1000)
 assert restored.connected_at is None
 before=j.page()['through']
 restored.connected(now)
 restored.frame(json.dumps([bar(n) for n in names]).encode(),now)
 restored.expire_minute(MINUTE,now)
 assert j.page()['through']==before


def test_restart_future_receipt_does_not_publish_partial_state(tmp_path,calendar):
 j=MassiveJournal(tmp_path);s=MassiveStreamState(['AAPL'],calendar,j)
 s.expire_minute(MINUTE,MINUTE+timedelta(seconds=91))
 restored=MassiveStreamState(['AAPL'],calendar,j)
 with pytest.raises(SourceUnavailable,match='FUTURE_EVIDENCE'):
  restore_stream(restored,j,session=MINUTE.date().isoformat(),now=MINUTE+timedelta(seconds=80))
 assert not restored.seen and not restored.sealed and restored.reject_before_ms is None
