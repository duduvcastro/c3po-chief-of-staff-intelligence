import json
from datetime import timedelta
import pytest
from test_r2d2_v2_minute_bars import MINUTE,calendar
from test_r2d2_v2_massive_stream import bar
from app.r2d2_v2_massive_stream import MassiveStreamState
from app.r2d2_v2_massive_journal import MassiveJournal
from app.r2d2_v2_massive_events import journal_envelope
from app.r2d2_v2_sources import SourceUnavailable


def record(tmp_path,calendar):
 j=MassiveJournal(tmp_path);s=MassiveStreamState(['AAPL'],calendar,j)
 s.connected(MINUTE-timedelta(seconds=1))
 s.frame(json.dumps([bar()]).encode(),MINUTE+timedelta(seconds=65))
 return MassiveJournal(tmp_path).page()['records'][0]


def test_durable_frame_becomes_native_envelope_without_refreshing_time(tmp_path,calendar):
 r=record(tmp_path,calendar)
 first=journal_envelope(r,MINUTE+timedelta(seconds=66))
 later=journal_envelope(r,MINUTE+timedelta(seconds=200))
 assert first==later
 assert first['available_at']==(MINUTE+timedelta(seconds=65)).isoformat()
 assert first['event']['at']==MINUTE.isoformat()
 assert first['event']['type']=='BAR'


def test_mutated_receipt_refused(tmp_path,calendar):
 r=record(tmp_path,calendar);r['receipt']['event']['close']=123
 with pytest.raises(SourceUnavailable,match='RECEIPT_HASH'):
  journal_envelope(r,MINUTE+timedelta(seconds=70))


def test_future_receipt_refused(tmp_path,calendar):
 with pytest.raises(SourceUnavailable,match='FUTURE_RECEIPT'):
  journal_envelope(record(tmp_path,calendar),MINUTE+timedelta(seconds=60))


def test_gap_remains_gap_through_durable_boundary(tmp_path,calendar):
 j=MassiveJournal(tmp_path);s=MassiveStreamState(['AAPL'],calendar,j)
 at=MINUTE+timedelta(seconds=151);s.expire_minute(MINUTE,at)
 e=journal_envelope(j.page()['records'][0],at)
 assert e['event']['type']=='DATA_GAP' and 'close' not in e['event']
