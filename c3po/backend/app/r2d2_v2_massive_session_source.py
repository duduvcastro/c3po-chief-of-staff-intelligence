"""Bounded session-index reader. Cursor proposals are never acknowledgements."""
import hashlib
import sqlite3
from datetime import timedelta
from .r2d2_v2_massive_events import session_envelope
from .r2d2_v2_massive_maintenance import journal_access
from .r2d2_v2_massive_sessions import MAX_SESSIONS, SessionJournalRoot, _session
from .r2d2_v2_sources import SourceUnavailable, _require, _time, canonical


class MassiveSessionEventSource:
    minute_bar_enabled = True
    def __init__(self, journals):
        _require(isinstance(journals, SessionJournalRoot), 'MASSIVE_SESSION_ROOT_REQUIRED')
        self.journals = journals

    def _positions(self, value, *, empty=False):
        _require(type(value) is dict, 'MASSIVE_SESSION_CURSOR')
        if empty and not value:
            return {}
        _require(set(value) == {'version', 'epoch', 'sessions'} and type(value['version']) is int
                 and value['version'] == 2 and value['epoch'] == self.journals.epoch
                 and type(value['sessions']) is dict and len(value['sessions']) <= MAX_SESSIONS,
                 'MASSIVE_SESSION_CURSOR_MIGRATION_REQUIRED')
        for day, position in value['sessions'].items():
            _session(day)
            _require(type(position) is int and position >= 0, 'MASSIVE_SESSION_CURSOR')
        return dict(value['sessions'])

    def _cursor(self, positions):
        return {'version': 2, 'epoch': self.journals.epoch, 'sessions': positions}

    def prepare_events(self, now, cursor, *, snapshot=None, read_clock=None, receipt_cutoff=None, event_limit=4096):
        try:
            with journal_access(self.journals.root):
                return self._prepare(now, cursor, snapshot=snapshot, receipt_cutoff=receipt_cutoff, event_limit=event_limit)
        except (SourceUnavailable, OSError, ValueError, TypeError, KeyError, OverflowError, sqlite3.Error) as exc:
            code = ('RAW_APPEND_IN_PROGRESS' if str(exc) in
                    {'MASSIVE_SESSION_NOT_READY', 'MASSIVE_MAINTENANCE_BUSY'}
                    else 'MASSIVE_SESSION_SOURCE_UNVERIFIED')
            return dict(events=[], diagnostics=[{'code': code}], cursor=cursor)

    def _prepare(self, now, cursor, *, snapshot, receipt_cutoff, event_limit):
        _require(type(event_limit) is int and 1<=event_limit<=4096, 'MASSIVE_SESSION_EVENT_LIMIT')
        positions = self._positions(cursor, empty=True)
        names = self.journals.sessions()
        _require(set(positions) <= set(names), 'MASSIVE_SESSION_CURSOR_MISSING_JOURNAL')
        if snapshot is None:
            heads = {}
            # Bounds inspection touches only the small index metadata. Evidence
            # remains limited to one page from the oldest outstanding session.
            for day in names:
                journal = self.journals.open_session(day)
                with journal._connect() as db:
                    floor, high = journal._bounds(db)
                _require(floor == 0, 'MASSIVE_SESSION_UNAUTHORIZED_PRUNING')
                heads[day] = high
        else:
            heads = self._positions(snapshot)
            _require(set(heads) <= set(names) and set(positions) <= set(heads), 'MASSIVE_SESSION_SNAPSHOT')
        _require(receipt_cutoff is None or receipt_cutoff.utcoffset() is not None and receipt_cutoff <= now,
                 'MASSIVE_SESSION_CUTOFF')
        positions = {day: positions.get(day, 0) for day in heads}
        _require(all(positions[day] <= high for day, high in heads.items()), 'MASSIVE_SESSION_CURSOR_AHEAD')
        pending = sorted(day for day in heads if positions[day] < heads[day])
        if not pending:
            return dict(events=[], diagnostics=[], cursor=self._cursor(positions),
                        raw_receipts={}, snapshot=self._cursor(heads), has_more=False,
                        page={'cutoff_received_at': None})
        day = pending[0]
        journal = self.journals.open_session(day)
        instruments = {'US:' + symbol for symbol in self.journals.manifest(day)['symbols']}
        after = positions[day]
        page = journal.page(after, through=heads[day], limit=event_limit)
        records = page['records']
        _require(bool(records), 'MASSIVE_SESSION_PAGE_PROGRESS')
        split = False
        if page['has_more']:
            following = journal.page(page['after'], through=heads[day], limit=1)['records']
            split = bool(following and _time(records[-1]['receipt']['event']['available_at']) ==
                         _time(following[0]['receipt']['event']['available_at']))
        last = None
        if after:
            preceding = journal.page(after-1, through=after, limit=1)['records']
            _require(len(preceding) == 1, 'MASSIVE_SESSION_PREDECESSOR_MISSING')
            session_envelope(preceding[0], now, epoch=self.journals.epoch, session=day)
            last = _time(preceding[0]['receipt']['event']['available_at'])
        events = []
        for record in records:
            envelope = session_envelope(record, now, epoch=self.journals.epoch, session=day)
            _require(envelope['event']['instrument_key'] in instruments,
                     'MASSIVE_SESSION_UNIVERSE_MISMATCH')
            received = _time(envelope['available_at'])
            _require(last is None or received >= last, 'MASSIVE_SESSION_RECEPTION_REVERSED')
            if receipt_cutoff is not None and received > receipt_cutoff:
                break
            last = received
            positions[day] = record['sequence']
            events.append({**envelope['event'], **{key: envelope[key] for key in (
                'event_id', 'source_id', 'source_at', 'sequence', 'provenance', 'manifest_sha',
                'amendment_sha', 'self_sha256')}, 'envelope_available_at': envelope['available_at'],
                'envelope_sha256': hashlib.sha256(canonical(envelope)).hexdigest()})
        more = any(positions[key] < high for key, high in heads.items())
        horizon = last if last is not None else receipt_cutoff
        if split and positions[day] == page['after']:
            horizon = last - timedelta(microseconds=1)
        return dict(events=events, diagnostics=[], cursor=self._cursor(positions),
                    raw_receipts={event['event_id']: event['envelope_sha256'] for event in events},
                    snapshot=self._cursor(heads), has_more=more,
                    page={'cutoff_received_at': horizon.isoformat() if more and horizon is not None else None})
