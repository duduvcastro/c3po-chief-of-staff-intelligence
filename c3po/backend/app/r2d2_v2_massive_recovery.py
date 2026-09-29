"""Restore in-memory minute identities from verified local evidence only.

Recovery never restores connection continuity or emits provider events. The
caller must establish a new connection and account for the interruption.
"""
from .r2d2_v2_massive_maintenance import journal_access
import hashlib
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from .r2d2_v2_minute_bars import MAX_RESPONSE_BYTES
from .r2d2_v2_sources import _require, _load_json, _time, canonical


def restore_stream(state, journal, *, session, now=None, max_records=500000, allow_prior_sessions=False):
    with journal_access(journal.spool.root):
        return _restore_stream_locked(state, journal, session=session, now=now,
                                      max_records=max_records, allow_prior_sessions=allow_prior_sessions)


def _restore_stream_locked(state, journal, *, session, now=None, max_records=500000, allow_prior_sessions=False):
    _require(type(max_records) is int and 0<max_records<=500000,'RECOVERY_LIMIT')
    _require(now is None or isinstance(now,datetime) and now.utcoffset() is not None,'RECOVERY_CLOCK')
    _require(type(allow_prior_sessions) is bool,'RECOVERY_SESSION_POLICY')
    if allow_prior_sessions:
        _require(now is not None and now.astimezone(ZoneInfo('America/New_York')).date().isoformat()==session,
                 'RECOVERY_SESSION_CLOCK')
    previous_session=None
    # The restart clock bounds resident identities, not the evidence scan.
    # Evicted history remains verified on disk and can never be filled later.
    cutoff=None if now is None else int((now.replace(second=0,microsecond=0)-timedelta(minutes=3)).timestamp()*1000)
    storage_stopped=False
    seen={};sealed=set();after=journal.retention_floor();through=None;count=0
    while True:
        page=journal.page(after,through=through,limit=1024)
        through=page['through']
        # Bounded by the journal page byte budget and discarded each page.
        verified_frames={}
        for record in page['records']:
            count+=1
            _require(count<=max_records,'RECOVERY_LIMIT')
            receipt=record['receipt'];event=receipt['event']
            event_session=event['session']
            _require(type(event_session) is str and date.fromisoformat(event_session).isoformat()==event_session,
                     'RECOVERY_SESSION_FORMAT')
            _require(event_session==session or allow_prior_sessions and event_session<session,
                     'RECOVERY_SESSION_MISMATCH')
            _require(previous_session is None or event_session>=previous_session,'RECOVERY_SESSION_REVERSED')
            previous_session=event_session
            instrument=event['instrument_key']
            # Historical daily lists may differ. Verify their evidence without
            # treating those instruments as members of today's stream state.
            _require(instrument.startswith('US:') and
                     (event_session!=session or instrument[3:] in state.symbols),
                     'RECOVERY_UNIVERSE_MISMATCH')
            symbol=instrument[3:]
            minute=_time(receipt.get('minute',event['at'])).replace(second=0,microsecond=0)
            key=(symbol,int(minute.timestamp()*1000))
            if now is not None:
                _require(_time(event['available_at'])<=now and minute<=now,'RECOVERY_FUTURE_EVIDENCE')
            retain=event_session==session and (cutoff is None or key[1]>=cutoff)
            if event['type']=='DATA_GAP':
                if event_session == session and event.get('reason') == 'MASSIVE_STORAGE_CAPACITY':
                    storage_stopped = True
                if retain:sealed.add(key)
            else:
                _require(event['type']=='BAR','RECOVERY_EVENT_TYPE')
                raw_hash=receipt['raw_sha256']
                if raw_hash not in verified_frames:
                    size=receipt['raw_bytes']
                    _require(type(size) is int and 0<size<=MAX_RESPONSE_BYTES,'RECOVERY_RAW_SIZE')
                    # The page verified the file earlier, but a pathname reopen
                    # here could read replaced bytes or block on a FIFO. Read
                    # through the anchored bounded helper and bind again.
                    raw=journal._read_evidence('raw',raw_hash+'.json',size,'RECOVERY_RAW_UNSAFE')
                    _require(len(raw)==size and hashlib.sha256(raw).hexdigest()==raw_hash,
                             'RECOVERY_RAW_HASH')
                    verified_frames[raw_hash]=_load_json(b'{"rows":'+raw+b'}')['rows']
                rows=verified_frames[raw_hash]
                index=receipt['frame_index']
                _require(type(index) is int and 0<=index<len(rows),'RECOVERY_FRAME_INDEX')
                row=rows[index]
                _require(row.get('sym')==symbol and row.get('s')==key[1],'RECOVERY_RAW_IDENTITY')
                identity=canonical({k:row.get(k) for k in ('s','e','o','h','l','c','v')})
                _require(key not in seen or seen[key]==identity,'RECOVERY_BAR_CONFLICT_WITHOUT_GAP')
                if retain:seen[key]=identity
        after=page['after']
        if not page['has_more']:break
    # All-or-nothing restore; a corrupt later page cannot expose partial state.
    with state._lock:
        _require(state.connected_at is None and not state.seen and not state.sealed,'RECOVERY_STATE_NOT_FRESH')
        state.seen=seen;state.sealed=sealed
        state.reject_before_ms=cutoff
        state.storage_stopped=storage_stopped
    return {'records':count,'observed_minutes':len(seen),'sealed_minutes':len(sealed)}
