"""Offline-testable AM connection state. No activation or network on import.

Sink must durably commit exact raw bytes/receipt before returning. A sink failure
propagates: callers must stop the stream instead of acknowledging lost evidence.
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from threading import RLock
from functools import wraps
from .r2d2_v2_sources import SourceUnavailable, _require, _load_json, _validate_event, canonical
from .r2d2_v2_minute_bars import massive_stream_minute, _SYMBOL, MAX_RESPONSE_BYTES

def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return call

class MassiveStreamState:
    def __init__(self, symbols, calendar, sink):
        _require(type(symbols) is list and 0 < len(symbols) <= 550 and
                 len(set(symbols)) == len(symbols) and all(isinstance(s,str) and _SYMBOL.fullmatch(s) for s in symbols), 'STREAM_SYMBOLS')
        self._lock = RLock()
        self.symbols = frozenset(symbols)
        self.calendar, self.sink = calendar, sink
        self.connected_at = None
        self.seen = {}
        self.sealed = set()
        self.reject_before_ms = None

    @serialized
    def connected(self, at):
        _require(isinstance(at,datetime) and at.utcoffset() is not None,'STREAM_CLOCK')
        self.connected_at = at
        # Historical keys remain sealed across connections. Never replay them.

    @serialized
    def gap(self, at, reason):
        _require(isinstance(at,datetime) and at.utcoffset() is not None,'STREAM_CLOCK')
        day = at.astimezone(ZoneInfo('America/New_York')).date()
        if not self.calendar.is_session(day):
            self.connected_at = None
            return
        session = self.calendar.details(day)
        if not session['open'] <= at < session['close']:
            self.connected_at = None
            return
        for symbol in sorted(self.symbols):
            event = dict(type='DATA_GAP',at=at.isoformat(),available_at=at.isoformat(),
                         session=at.astimezone(ZoneInfo('America/New_York')).date().isoformat(),
                         instrument_key='US:'+symbol,reason=reason)
            _validate_event(event,at)
            self.sink(None,{'event':event,'provenance':'MASSIVE_STREAM_LOCAL_GAP'})
        self.connected_at = None

    @serialized
    def expire_minute(self, minute, at):
        """Seal missing eligible minutes after the existing freshness deadline.

        The transport scheduler must call this even when no frames arrive.
        This does not claim that the market had zero trades.
        """
        _require(all(isinstance(t, datetime) and t.utcoffset() is not None
                     for t in (minute, at)), 'STREAM_CLOCK')
        _require(minute.second == 0 and minute.microsecond == 0, 'STREAM_MINUTE')
        _require(at > minute + timedelta(seconds=150), 'STREAM_NOT_EXPIRED')
        if self.reject_before_ms is not None and int(minute.timestamp()*1000)<self.reject_before_ms:
            return
        day = minute.astimezone(ZoneInfo('America/New_York')).date()
        if not self.calendar.is_session(day):
            return
        session = self.calendar.details(day)
        if not session['open'] <= minute < minute + timedelta(minutes=1) <= session['close']:
            return
        for symbol in sorted(self.symbols):
            key = (symbol, int(minute.timestamp() * 1000))
            if key in self.seen or key in self.sealed:
                continue
            event = dict(type='DATA_GAP', at=minute.isoformat(), available_at=at.isoformat(),
                         session=day.isoformat(), instrument_key='US:' + symbol,
                         reason='MASSIVE_MINUTE_NOT_OBSERVED')
            _validate_event(event, at)
            self.sink(None, {'event': event, 'minute': minute.isoformat(),
                             'provenance': 'MASSIVE_STREAM_LOCAL_GAP'})
            self.sealed.add(key)
        # Evidence stays in the durable journal. Retain only a recent in-memory
        # window; the watermark prevents evicted minutes from being filled.
        cutoff=int((minute-timedelta(minutes=2)).timestamp()*1000)
        self.reject_before_ms=max(self.reject_before_ms or cutoff,cutoff)
        self.seen={k:v for k,v in self.seen.items() if k[1]>=self.reject_before_ms}
        self.sealed={k for k in self.sealed if k[1]>=self.reject_before_ms}

    @serialized
    def frame(self, data, received_at):
        _require(self.connected_at is not None,'STREAM_DISCONNECTED')
        _require(type(data) is bytes and 0 < len(data) <= MAX_RESPONSE_BYTES,'STREAM_FRAME_SIZE')
        parsed = _load_json(b'{"rows":'+data+b'}')
        _require(set(parsed)=={'rows'} and type(parsed['rows']) is list and len(parsed['rows'])<=4096,'STREAM_FRAME')
        # Each receipt binds the whole frame, not reserialized provider data.
        import hashlib
        for index,row in enumerate(parsed['rows']):
            _require(type(row) is dict,'STREAM_ROW')
            if row.get('ev') == 'status':
                if row.get('status') in ('connected', 'auth_success', 'success'):
                    continue  # Provider acknowledgements do not imply a market-data gap.
                self.gap(received_at,'MASSIVE_STATUS');return
            _require(row.get('ev')=='AM','STREAM_UNEXPECTED_EVENT')
            if row.get('sym') not in self.symbols:
                continue  # Unsubscribed names cannot invalidate selected names.
            _require(type(row.get('s')) is int and row['s']>0 and row['s']%60000==0,'STREAM_TIMESTAMP')
            try:
                minute=datetime.fromtimestamp(row['s']/1000,timezone.utc)
            except (OverflowError, ValueError, OSError):
                raise SourceUnavailable('STREAM_TIMESTAMP') from None
            day = minute.astimezone(ZoneInfo('America/New_York')).date()
            if not self.calendar.is_session(day):
                continue
            session = self.calendar.details(day)
            if not session['open'] <= minute < session['close']:
                continue  # AM also carries extended-hours data; research is RTH.

            key=(row['sym'],row['s'])
            if self.reject_before_ms is not None and row['s']<self.reject_before_ms:
                continue
            if key in self.sealed:
                continue  # A declared gap must not be filled by a late frame.
            try:
                result=massive_stream_minute(canonical([row]),symbol=row['sym'],minute=minute,
                    received_at=received_at,now=received_at,calendar=self.calendar,connected_at=self.connected_at)
            except SourceUnavailable as exc:
                connection_gap = str(exc) == 'MINUTE_CONNECTION_GAP'
                event = dict(type='DATA_GAP',
                             at=(minute if connection_gap else received_at).isoformat(),
                             available_at=received_at.isoformat(),
                             session=(day if connection_gap else received_at.astimezone(ZoneInfo('America/New_York')).date()).isoformat(),
                             instrument_key='US:' + row['sym'],
                             reason='MINUTE_CONNECTION_GAP' if connection_gap else 'MASSIVE_INVALID_BAR')
                _validate_event(event, received_at)
                self.sink(data, dict(event=event, raw_sha256=hashlib.sha256(data).hexdigest(),
                                    raw_bytes=len(data), frame_index=index,
                                    provenance=('MASSIVE_STREAM_CONNECTION_GAP' if connection_gap
                                                else 'MASSIVE_STREAM_INVALID_ROW'),
                                    minute=minute.isoformat()))
                self.sealed.add(key)  # Seal only after evidence is durable.
                continue
            identity=canonical({k:row.get(k) for k in ('s','e','o','h','l','c','v')})
            if key in self.seen:
                if self.seen[key] != identity:
                    event = dict(type='DATA_GAP', at=minute.isoformat(),
                                 available_at=received_at.isoformat(), session=day.isoformat(),
                                 instrument_key='US:' + row['sym'], reason='MASSIVE_BAR_CONFLICT')
                    _validate_event(event, received_at)
                    self.sink(data, dict(event=event, raw_sha256=hashlib.sha256(data).hexdigest(),
                                        raw_bytes=len(data), frame_index=index,
                                        provenance='MASSIVE_STREAM_CONFLICT'))
                    self.sealed.add(key)
                    # Never replace a previously observed bar with corrected OHLC.
                    # Other symbols in the same provider frame remain independent.
                continue
            result.update(raw_sha256=hashlib.sha256(data).hexdigest(),raw_bytes=len(data),frame_index=index)
            self.sink(data,result)
            self.seen[key]=identity
            if result['event']['type']=='DATA_GAP':self.sealed.add(key)
