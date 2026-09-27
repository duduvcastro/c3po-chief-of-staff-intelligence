"""Bounded single-connection protocol pump; caller owns connection authorization.

No network access on import. Socket injection enables offline tests. Does not
reconnect or retrieve historical minutes; any interruption marks a data gap.
"""
import json
from .r2d2_v2_sources import SourceUnavailable, _load_json, _require
from .r2d2_v2_minute_bars import MAX_RESPONSE_BYTES


def pump(socket, state, token, *, utcnow, monotonic, tick, stop, max_seconds=3600,
         auth_seconds=10, idle_seconds=75):
    _require(isinstance(token,str) and bool(token) and len(token)<=4096,'STREAM_AUTH_REQUIRED')
    _require(0<max_seconds<=8*3600 and 0<auth_seconds<=30 and 0<idle_seconds<90,'STREAM_LIMITS')
    started=monotonic();last=started;authenticated=False
    try:
        socket.send(json.dumps({'action':'auth','params':token}))
        while not stop():
            current=monotonic()
            if current-started>=max_seconds:
                state.gap(utcnow(),'MASSIVE_SESSION_LIMIT');return 'SESSION_LIMIT'
            if not authenticated and current-started>=auth_seconds:
                state.gap(utcnow(),'MASSIVE_AUTH_TIMEOUT');return 'AUTH_TIMEOUT'
            if authenticated and current-last>=idle_seconds:
                state.gap(utcnow(),'MASSIVE_STREAM_IDLE');return 'IDLE'
            tick(utcnow())  # Expiry progresses even without frames.
            try:
                frame=socket.recv(timeout=1)
            except TimeoutError:
                continue
            received=utcnow();last=monotonic()
            if isinstance(frame,str):frame=frame.encode('utf-8')
            _require(type(frame) is bytes and 0<len(frame)<=MAX_RESPONSE_BYTES,'STREAM_FRAME_SIZE')
            rows=_load_json(b'{"rows":'+frame+b'}').get('rows')
            _require(type(rows) is list and len(rows)<=4096,'STREAM_FRAME')
            for row in rows:
                _require(type(row) is dict,'STREAM_ROW')
                if row.get('ev')=='status':
                    status=row.get('status')
                    if status not in ('connected','auth_success','success'):
                        state.gap(received,'MASSIVE_PROVIDER_REFUSAL');return 'PROVIDER_REFUSAL'
                    if status=='auth_success' and not authenticated:
                        authenticated=True
                        state.connected(received)
                        socket.send(json.dumps({'action':'subscribe','params':','.join('AM.'+s for s in sorted(state.symbols))}))
                elif not authenticated:
                    raise SourceUnavailable('STREAM_DATA_BEFORE_AUTH')
            if authenticated:
                state.frame(frame,received)
        state.gap(utcnow(),'MASSIVE_STOPPED')
        return 'STOPPED'
    except Exception:
        # No provider exception text or credentials escape into diagnostics.
        state.gap(utcnow(),'MASSIVE_TRANSPORT_FAILURE')
        raise SourceUnavailable('MASSIVE_TRANSPORT_FAILURE') from None
    finally:
        try:socket.close()
        except Exception:pass


def run_connection(state, token, *, utcnow, monotonic, tick, stop,
                   connector=None, max_seconds=3600):
    """Open one real-time connection. Never retry or choose a delayed endpoint.

    This function is not installed into a worker or CLI by itself. The caller
    must enforce approved process ownership and prevent competing connections.
    """
    import logging
    _require(isinstance(token,str) and bool(token) and len(token)<=4096,'STREAM_AUTH_REQUIRED')
    _require(0<max_seconds<=8*3600,'STREAM_LIMITS')
    if connector is None:
        from websockets.sync.client import connect
        connector=connect
    # Dedicated disabled logger prevents protocol debug logs from recording auth.
    logger=logging.Logger('r2d2.massive.private_transport')
    logger.disabled=True
    try:
        socket=connector('wss://socket.massive.com/stocks',open_timeout=10,
                         close_timeout=3,ping_interval=15,ping_timeout=10,
                         max_size=MAX_RESPONSE_BYTES,max_queue=1,
                         compression=None,proxy=None,logger=logger)
    except Exception:
        state.gap(utcnow(),'MASSIVE_CONNECT_FAILURE')
        raise SourceUnavailable('MASSIVE_CONNECT_FAILURE') from None
    return pump(socket,state,token,utcnow=utcnow,monotonic=monotonic,tick=tick,
                stop=stop,max_seconds=max_seconds)
