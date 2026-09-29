"""Asymmetric immutable feed fixtures with durable consumer checkpoints."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3
import pytest

from app.r2d2_v2_composite_source import CompositeEventSource
from app.r2d2_v2_sources import canonical, _load_json

BASE = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)
NOW = BASE + timedelta(minutes=45)


class MassiveBacklog:
    def __init__(self, *, hole=False):
        self.rows = []
        for n in range(550*40):
            if hole and n == 0:
                continue
            minute = BASE + timedelta(minutes=n//550)
            self.rows.append({'event_id': 'massive-bar-'+str(n), 'source_id': 'massive-fixture',
                'sequence': len(self.rows), 'envelope_sha256': 'a'*64, 'type': 'BAR',
                'instrument_key': 'US:S'+str(n%550), 'session': '2026-09-28',
                'at': minute.isoformat(), 'end_at': (minute+timedelta(minutes=1)).isoformat(),
                'available_at': (minute+timedelta(seconds=65)).isoformat(),
                'open': 100., 'high': 101., 'low': 99., 'close': 100.,
                'regular': True, 'coverage_complete': True})

    def prepare_events(self, now, cursor, *, snapshot=None, receipt_cutoff=None, event_limit=4096, **kwargs):
        start = cursor.get('n', 0); through = snapshot['through'] if snapshot else len(self.rows)
        rows = self.rows[start:min(start+event_limit, through)]
        if receipt_cutoff is not None:
            rows = [e for e in rows if datetime.fromisoformat(e['available_at']) <= receipt_cutoff]
        end = start+len(rows)
        cutoff = (datetime.fromisoformat(rows[-1]['available_at'])-timedelta(microseconds=1)).isoformat() if rows and end<through else None
        return {'events': rows, 'diagnostics': [], 'cursor': {'n': end},
            'snapshot': {'through': through}, 'has_more': end<through,
            'raw_receipts': {e['event_id']: e['envelope_sha256'] for e in rows},
            'page': {'cutoff_received_at': cutoff}}


class SlowRaw:
    def __init__(self, total=1000): self.total = total

    def prepare_events(self, now, cursor, *, snapshot=None, receipt_cutoff=None, **kwargs):
        n = cursor.get('n', 0); through = snapshot['through'] if snapshot else self.total
        stamp = BASE+timedelta(seconds=70+n)
        rows = []
        if n<through and (receipt_cutoff is None or stamp<=receipt_cutoff):
            rows = [{'event_id': 'quote-'+str(n), 'sequence': n, 'source_id': 'raw-fixture',
                'type': 'QUOTE', 'instrument_key': 'US:S0', 'session': '2026-09-28',
                'at': stamp.isoformat(), 'available_at': stamp.isoformat(),
                'bid_at': stamp.isoformat(), 'ask_at': stamp.isoformat(), 'bid': 100., 'ask': 100.,
                'regular': True, 'envelope_sha256': 'b'*64}]
        return {'events': rows, 'diagnostics': [], 'cursor': {'n': n+len(rows)},
            'snapshot': {'through': through}, 'has_more': n+len(rows)<through,
            'raw_receipts': {e['event_id']: e['envelope_sha256'] for e in rows}}


def test_550_symbols_40_minutes_with_one_second_raw_pages_drains_without_cap_loop(tmp_path):
    massive = MassiveBacklog(); raw = SlowRaw()
    source = CompositeEventSource(raw, massive)
    db = sqlite3.connect(tmp_path/'consumer.sqlite3')
    db.execute('CREATE TABLE checkpoint (body BLOB)')
    db.execute('INSERT INTO checkpoint VALUES (?)', (canonical({}),))
    db.execute('CREATE TABLE consumed (identity TEXT PRIMARY KEY, receipt TEXT NOT NULL)')
    db.commit()
    paused = resumed = 0; rolled_back = False; previous_massive = 0
    for attempt in range(1100):
        cursor = _load_json(db.execute('SELECT body FROM checkpoint').fetchone()[0])
        page = source.prepare_events(NOW, cursor)
        assert not page['diagnostics'], (attempt, page['diagnostics'])
        proposed = page['cursor']
        assert len(canonical(proposed)) <= source.MAX_CURSOR_BYTES
        assert len(canonical(proposed['barrier']['resolved'])) <= source.MAX_BARRIER_BYTES
        assert len(proposed['barrier']['resolved']) <= source.MAX_PROOFS
        assert proposed != cursor or not page['has_more'], 'permanent non-advancing backlog'
        stopped = proposed['massive']['n'] == previous_massive and previous_massive < len(massive.rows)
        if stopped:
            paused += 1
            assert not any(e['type']=='BAR' for e in page['events'])
            assert proposed['quote_trade']['n'] > cursor['quote_trade']['n']
            if not rolled_back:
                db.execute('UPDATE checkpoint SET body=?', (canonical(proposed),))
                db.executemany('INSERT INTO consumed VALUES (?,?)', page['raw_receipts'].items())
                db.rollback()
                assert _load_json(db.execute('SELECT body FROM checkpoint').fetchone()[0]) == cursor
                source = CompositeEventSource(raw, massive)
                assert source.prepare_events(NOW, cursor) == page
                rolled_back = True
        elif paused and proposed['massive']['n'] > previous_massive:
            resumed += 1
        assert not any(e['type']=='DATA_GAP' for e in page['events'])
        db.execute('UPDATE checkpoint SET body=?', (canonical(proposed),))
        db.executemany('INSERT INTO consumed VALUES (?,?)', page['raw_receipts'].items())
        db.commit()
        previous_massive = proposed['massive']['n']
        if not page['has_more']: break
    else:
        raise AssertionError('bounded fixture did not drain')
    assert paused and resumed and rolled_back
    assert proposed['massive']['n'] == 550*40 and proposed['quote_trade']['n'] == 1000
    assert db.execute('SELECT COUNT(*) FROM consumed').fetchone()[0] == 550*40+1000
    db.close()


def test_missing_early_bar_can_timeout_after_verified_horizon_without_full_drain():
    source = CompositeEventSource(SlowRaw(3), MassiveBacklog(hole=True))
    first = source.prepare_events(NOW, {})
    assert not first['diagnostics'] and first['has_more']
    gaps = [e for e in first['events'] if e['type']=='DATA_GAP']
    assert len(gaps)==1 and gaps[0]['reason']=='BAR_WAIT_TIMEOUT'
    assert gaps[0]['at']==BASE.isoformat()
    assert first['cursor']['quote_trade']=={'n': 1}
    assert first['cursor']['massive']['n']<len(source.massive.rows)
    assert source.prepare_events(NOW, {}) == first  # no read-side acknowledgement


def test_split_receipt_horizon_does_not_timeout_before_complete_deadline():
    class BeforeDeadline(MassiveBacklog):
        def prepare_events(self, *args, **kwargs):
            result = super().prepare_events(*args, **kwargs)
            result['page']['cutoff_received_at'] = (BASE+timedelta(seconds=150)-timedelta(microseconds=1)).isoformat()
            return result
    page = CompositeEventSource(SlowRaw(1), BeforeDeadline(hole=True)).prepare_events(NOW, {})
    assert not page['diagnostics']
    assert all(e['type']=='BAR' for e in page['events'])
    assert page['cursor']['quote_trade'] == {'n': 0}


@pytest.mark.parametrize('single_receipt_group',[False,True])
def test_large_retained_raw_cursor_uses_smaller_bar_prefix_instead_of_empty_stall(single_receipt_group):
    from hashlib import sha256
    massive=MassiveBacklog()
    for event in massive.rows:
        event['event_id']='massive-'+sha256(event['event_id'].encode()).hexdigest()
    if single_receipt_group:
        massive.rows=massive.rows[:5500]
        for event in massive.rows:
            event['type']='DATA_GAP';event['reason']='BACKLOG_EXPIRED'
            event['available_at']=(BASE+timedelta(minutes=12,seconds=31)).isoformat()
            for field in ('open','high','low','close','regular','coverage_complete','end_at'):event.pop(field)
    files={f'session_date=2026-09-28/feed=quote-part-{n:05}.ndjson':{
        'offset':123456789,'sequence':0,'device':16777234,'inode':123456789+n,
        'witness':'a'*64,'received_max':'2026-09-28T14:00:00+00:00'} for n in range(2500)}
    first_file=next(iter(files))
    class RetainedRaw(SlowRaw):
        def prepare_events(self,now,cursor,**kwargs):
            position=cursor.get('files',files)[first_file]['sequence']
            result=super().prepare_events(now,{'n':position},**kwargs)
            advanced=dict(files)
            advanced[first_file]={**files[first_file],'sequence':result['cursor']['n']}
            result['cursor']={'files':advanced}
            return result
    source=CompositeEventSource(RetainedRaw(5),massive)
    cursor={'version':2,'quote_trade':{'files':files},'massive':{},'barrier':{'resolved':{},'sequence':0}}
    initial=deepcopy(cursor)
    first=source.prepare_events(NOW,cursor)
    assert not first['diagnostics'] and first['events']
    assert 0<first['cursor']['massive']['n']<4096
    assert first['cursor']['quote_trade']['files'][first_file]['sequence']==1
    assert len(canonical(first['cursor']))<=source.MAX_CURSOR_BYTES
    assert cursor==initial and source.prepare_events(NOW,cursor)==first
    cursor=first['cursor'];seen={e['event_id'] for e in first['events']}
    for attempt in range(20):
        page=source.prepare_events(NOW,cursor)
        assert not page['diagnostics']
        assert page['cursor']!=cursor or not page['has_more']
        assert not seen.intersection(e['event_id'] for e in page['events'])
        seen.update(e['event_id'] for e in page['events'])
        assert len(canonical(page['cursor']))<=source.MAX_CURSOR_BYTES
        cursor=page['cursor']
        if not page['has_more']:break
    else:raise AssertionError('large raw cursor backlog stalled')
    assert cursor['massive']['n']==len(massive.rows)
    assert cursor['quote_trade']['files'][first_file]['sequence']==5
    assert len(seen)==len(massive.rows)+5
