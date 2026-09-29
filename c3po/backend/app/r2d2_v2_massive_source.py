"""Standalone Massive event port; not a replacement for the EODHD source.

Only the collector transaction can commit the returned cursor. Composite feed
ordering and production source selection remain separate integration work.
"""
from .r2d2_v2_massive_maintenance import journal_access
import hashlib
from datetime import timedelta
import sqlite3
from .r2d2_v2_massive_events import journal_envelope
from .r2d2_v2_sources import SourceUnavailable, canonical, _require, _time


class MassiveEventSource:
    def __init__(self, journal):
        self.journal=journal

    def prepare_events(self, now, cursor, *, snapshot=None, read_clock=None, receipt_cutoff=None):
        try:
            with journal_access(self.journal.path.parent):
                return self._prepare_events_locked(now, cursor, snapshot=snapshot,
                                                   read_clock=read_clock, receipt_cutoff=receipt_cutoff)
        except (SourceUnavailable, OSError, ValueError):
            return dict(events=[],diagnostics=[{'code':'MASSIVE_SOURCE_UNVERIFIED'}],cursor=cursor)

    def _prepare_events_locked(self, now, cursor, *, snapshot=None, read_clock=None, receipt_cutoff=None):
        try:
            _require(type(cursor) is dict and set(cursor) <= {'massive_sequence'},'MASSIVE_CURSOR')
            after=cursor.get('massive_sequence',0)
            _require(snapshot is None or (type(snapshot) is dict and set(snapshot)=={'massive_through'}),'MASSIVE_SNAPSHOT')
            page=self.journal.page(after,through=snapshot['massive_through'] if snapshot else None,limit=4096)
            records=page['records']
            split_receipt=False
            if page['has_more'] and records:
                following=self.journal.page(page['after'],through=page['through'],limit=1)['records']
                split_receipt=bool(following and
                    _time(records[-1]['receipt']['event']['available_at']) ==
                    _time(following[0]['receipt']['event']['available_at']))
            _require(receipt_cutoff is None or receipt_cutoff.utcoffset() is not None and receipt_cutoff<=now,'MASSIVE_CUTOFF')
            events=[];last=None;position=after
            if after:
                preceding=self.journal.page(after-1,through=after,limit=1)['records']
                _require(len(preceding)==1,'MASSIVE_CURSOR_PREDECESSOR_MISSING')
                last=_time(preceding[0]['receipt']['event']['available_at'])
            for record in records:
                envelope=journal_envelope(record,now)
                at=_time(envelope['available_at'])
                _require(last is None or at>=last,'MASSIVE_RECEPTION_REVERSED')
                if receipt_cutoff is not None and at>receipt_cutoff:
                    break
                last=at
                position=record['sequence']
                events.append({**envelope['event'], **{k:envelope[k] for k in (
                    'event_id','source_id','source_at','sequence','provenance','manifest_sha','amendment_sha','self_sha256')},
                    'envelope_available_at':envelope['available_at'],
                    'envelope_sha256':hashlib.sha256(canonical(envelope)).hexdigest()})
            horizon=last
            if split_receipt and position==page['after']:
                # Continue a large receipt group in bounded, verified pages.
                # The composite raw feed must stay strictly before this group
                # until its final page is offered; reading never commits ACK.
                horizon=last-timedelta(microseconds=1)
            return dict(events=events,diagnostics=[],cursor={'massive_sequence':position},
                        raw_receipts={e['event_id']:e['envelope_sha256'] for e in events},
                        snapshot={'massive_through':page['through']},has_more=position<page['through'],
                        page={'cutoff_received_at':horizon.isoformat() if horizon is not None and position<page['through'] else None})
        except (SourceUnavailable, OSError, ValueError, TypeError, KeyError, OverflowError, sqlite3.Error):
            return dict(events=[],diagnostics=[{'code':'MASSIVE_SOURCE_UNVERIFIED'}],cursor=cursor)
