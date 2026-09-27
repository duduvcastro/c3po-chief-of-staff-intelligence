"""Restore in-memory minute identities from verified local evidence only.

Recovery never restores connection continuity or emits provider events. The
caller must establish a new connection and account for the interruption.
"""
from datetime import datetime, timedelta
from .r2d2_v2_sources import _require, _load_json, _time, canonical


def restore_stream(state, journal, *, session, now=None, max_records=500000):
    _require(type(max_records) is int and 0<max_records<=500000,'RECOVERY_LIMIT')
    _require(now is None or isinstance(now,datetime) and now.utcoffset() is not None,'RECOVERY_CLOCK')
    # The restart clock bounds resident identities, not the evidence scan.
    # Evicted history remains verified on disk and can never be filled later.
    cutoff=None if now is None else int((now.replace(second=0,microsecond=0)-timedelta(minutes=3)).timestamp()*1000)
    seen={};sealed=set();after=0;through=None;count=0
    while True:
        page=journal.page(after,through=through,limit=1024)
        through=page['through']
        for record in page['records']:
            count+=1
            _require(count<=max_records,'RECOVERY_LIMIT')
            receipt=record['receipt'];event=receipt['event']
            _require(event['session']==session,'RECOVERY_SESSION_MISMATCH')
            instrument=event['instrument_key']
            _require(instrument.startswith('US:') and instrument[3:] in state.symbols,'RECOVERY_UNIVERSE_MISMATCH')
            symbol=instrument[3:]
            minute=_time(receipt.get('minute',event['at'])).replace(second=0,microsecond=0)
            key=(symbol,int(minute.timestamp()*1000))
            if now is not None:
                _require(_time(event['available_at'])<=now and minute<=now,'RECOVERY_FUTURE_EVIDENCE')
            retain=cutoff is None or key[1]>=cutoff
            if event['type']=='DATA_GAP':
                if retain:sealed.add(key)
            else:
                _require(event['type']=='BAR','RECOVERY_EVENT_TYPE')
                raw=(journal.spool.root/'raw'/(receipt['raw_sha256']+'.json')).read_bytes()
                rows=_load_json(b'{"rows":'+raw+b'}')['rows']
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
    return {'records':count,'observed_minutes':len(seen),'sealed_minutes':len(sealed)}
