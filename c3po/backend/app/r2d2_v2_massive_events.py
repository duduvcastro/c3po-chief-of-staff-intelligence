"""Translate a verified journal record into the existing event contract.

The journal reader must verify referenced raw bytes before calling this helper.
No receipt clock is refreshed, and no market data is synthesized here.
"""
import hashlib
from .r2d2_v2_sources import (
    AMENDMENT_SHA, EVENT_SCHEMA, MANIFEST_SHA, canonical,
    _require, _metadata, _time, _validate_event,
)


def journal_envelope(record, now):
    _require(type(record) is dict and set(record)=={'sequence','receipt_sha256','receipt'},
             'MASSIVE_JOURNAL_RECORD')
    _require(type(record['sequence']) is int and record['sequence']>0,'MASSIVE_JOURNAL_SEQUENCE')
    receipt=record['receipt']
    _require(type(receipt) is dict and type(receipt.get('event')) is dict,
             'MASSIVE_JOURNAL_EVENT')
    digest=hashlib.sha256(canonical(receipt)).hexdigest()
    _require(record['receipt_sha256']==digest,'MASSIVE_JOURNAL_RECEIPT_HASH')
    event=dict(receipt['event'])
    _require(event.get('type') in ('BAR','DATA_GAP'),'MASSIVE_JOURNAL_EVENT_TYPE')
    at=_time(event.get('available_at'))
    _require(at<=now,'MASSIVE_JOURNAL_FUTURE_RECEIPT')
    _validate_event(event,at)
    envelope=dict(schema=EVENT_SCHEMA,manifest_sha=MANIFEST_SHA,amendment_sha=AMENDMENT_SHA,
        source_id='massive-am-journal-v1',
        provenance={'producer':'massive-am-journal','version':'v1','payload_sha256':digest},
        source_at=at.isoformat(),available_at=at.isoformat(),sequence=record['sequence']-1,
        event_id='massive-'+digest,event=event)
    envelope['self_sha256']=hashlib.sha256(canonical(envelope)).hexdigest()
    _metadata(envelope,EVENT_SCHEMA,now)
    return envelope


def session_envelope(record, now, *, epoch, session):
    """Bind an otherwise identical receipt to its epoch/session continuity domain."""
    from .r2d2_v2_massive_sessions import _session
    import re
    _require(type(epoch) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}', epoch)
             is not None, 'MASSIVE_SESSION_EPOCH')
    _session(session)
    envelope = journal_envelope(record, now)
    _require(envelope['event']['session'] == session, 'MASSIVE_SESSION_RECEIPT_MISMATCH')
    epoch_sha = hashlib.sha256(epoch.encode()).hexdigest()
    envelope['source_id'] = 'massive-am-v2-' + epoch_sha[:32] + '-' + session
    envelope['provenance'] = {**envelope['provenance'], 'version': 'session-v2'}
    envelope.pop('self_sha256')
    envelope['self_sha256'] = hashlib.sha256(canonical(envelope)).hexdigest()
    _metadata(envelope, EVENT_SCHEMA, now)
    return envelope
