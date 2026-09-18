from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.config import Settings
from app.database import Database
from app.market_data.indices import INDICES, IndexQuotesService, quote_status
from app.market_data.live_markets import LiveMarketsService, MARKET_SPECS
from app.market_data.realtime import RealtimeMarketsService, MARKET_SPECS as REALTIME_SPECS

NOW = datetime(2026, 9, 17, 15, 30, tzinfo=timezone.utc)

class Http:
    def __init__(self):
        self.calls = []
        self.rows = [{"symbol": symbol, "price": 100, "previousClose": 100,
                      "changePercentage": 999, "timestamp": NOW.timestamp()} for symbol in INDICES]
        self.failed = False
    def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, params))
        assert "yahoo" not in url
        if self.failed:
            raise RuntimeError("secret-key-must-not-escape")
        return self.rows

def service():
    settings = Settings(fmp_api_token="test", auth_cookie_secure=False)
    http = Http()
    return settings, http, IndexQuotesService(settings, http)

class Clock(datetime):
    @classmethod
    def now(cls, tz=None): return NOW


def test_both_products_share_single_fmp_request_and_same_quote():
    settings, http, indices = service()
    live = LiveMarketsService(settings, http, indices=indices)
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    with patch('app.market_data.indices.datetime', Clock):
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(indices.quote, list(INDICES)*3))
        falcon = live.index_snapshot()
        luke = master._index_quote(REALTIME_SPECS['NASDAQ'])
    assert len(http.calls) == 1
    assert len(rows) == 18
    item = next(item for item in falcon.items if item.symbol=='NASDAQ')
    assert (item.price, item.as_of, item.change_percent) == (luke.value, luke.as_of, luke.change_percent)
    assert item.provider == luke.source == 'Financial Modeling Prep'
    assert item.change_percent == 0  # Valid zero; derive from matching previous close.
    assert {r.symbol:r.currency for r in rows}['Nikkei'] == 'JPY'
    assert {r.symbol:r.currency for r in rows}['DAX'] == 'EUR'

@pytest.mark.parametrize('symbol,as_of,status', [
    ('^IXIC', NOW-timedelta(seconds=20), 'live'),
    ('^BVSP', NOW-timedelta(minutes=16), 'delayed'),
    ('^IXIC', NOW-timedelta(hours=1), 'stale'),
    ('^N225', datetime(2026,9,17,6,25,tzinfo=timezone.utc), 'closed'),
    ('000001.SS', datetime(2026,9,17,7,tzinfo=timezone.utc), 'closed'),
    ('^N225', datetime(2026,9,16,6,25,tzinfo=timezone.utc), 'stale'),
])
def test_real_exchange_calendar_and_age(symbol,as_of,status):
    assert quote_status(INDICES[symbol],as_of,NOW)[0] == status

@pytest.mark.parametrize('now,as_of,expected', [
    ('2026-09-17T20:30:00+00:00', '2026-09-17T19:59:00+00:00', ('closed', 'CLOSED')),
    ('2026-09-17T21:30:00+00:00', '2026-09-17T19:59:00+00:00', ('closed', 'CLOSED')),
    ('2026-09-17T20:00:00+00:00', '2026-09-17T19:59:00+00:00', ('closed', 'CLOSED')),
    ('2026-09-17T19:59:00+00:00', '2026-09-17T19:59:00+00:00', ('live', 'REGULAR')),
    ('2026-01-15T20:30:00+00:00', '2026-01-15T20:29:00+00:00', ('live', 'REGULAR')),
    ('2026-01-15T21:30:00+00:00', '2026-01-15T20:59:00+00:00', ('closed', 'CLOSED')),
    # US holidays and early closes must not shorten the B3 session.
    ('2026-11-26T20:30:00+00:00', '2026-11-26T20:29:00+00:00', ('live', 'REGULAR')),
    ('2026-11-27T20:30:00+00:00', '2026-11-27T20:29:00+00:00', ('live', 'REGULAR')),
    ('2026-09-07T18:00:00+00:00', '2026-09-04T19:59:00+00:00', ('closed', 'CLOSED')),
    ('2026-09-17T20:30:00+00:00', '2026-09-16T19:59:00+00:00', ('stale', 'STALE')),
])
def test_b3_cash_close_tracks_us_dst_but_preserves_b3_sessions(now, as_of, expected):
    assert quote_status(INDICES['^BVSP'], datetime.fromisoformat(as_of), datetime.fromisoformat(now)) == expected


@pytest.mark.parametrize('hour', [20, 21])
def test_b3_intraday_after_summer_close_is_closed(hour):
    settings, http, indices = service()
    http.rows = [{'date': '2026-09-17 16:55:00', 'open': 100, 'high': 102,
                  'low': 99, 'close': 101, 'volume': 0}]
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    spec = next(s for s in MARKET_SPECS if s.symbol == 'IBOV')
    result = master._live_instrument_intraday(spec, NOW.replace(hour=hour))
    assert result.status == 'closed'

@pytest.mark.parametrize('mutation', [{'timestamp':None},{'timestamp':NOW.timestamp()+3600},{'price':float('nan')},{'price':0}])
def test_invalid_row_never_becomes_fresh_quote(mutation):
    settings,http,indices=service()
    http.rows[0].update(mutation)
    with patch('app.market_data.indices.datetime',Clock):
        with pytest.raises(RuntimeError,match='FMP index quote unavailable'):indices.quote('^BVSP')
        assert indices.quote('^IXIC').price==100


def test_failure_retains_real_timestamp_marks_stale_and_throttles_without_yahoo():
    _,http,indices=service()
    with patch('app.market_data.indices.datetime',Clock):
        original=indices.quote('^IXIC')
        http.failed=True;indices._expires=NOW-timedelta(seconds=1)
        stale=indices.quote('^IXIC');indices.quote('^NYA')
    assert stale.status=='stale' and stale.as_of==original.as_of
    assert len(http.calls)==2


def test_older_quote_cannot_overwrite_newer():
    _,http,indices=service()
    with patch('app.market_data.indices.datetime',Clock):
        original=indices.quote('^IXIC')
        for row in http.rows:row.update(timestamp=NOW.timestamp()-600,price=50)
        indices._expires=NOW-timedelta(seconds=1)
        result=indices.quote('^IXIC')
    assert result.price==original.price and result.as_of==original.as_of and result.status=='stale'

@pytest.mark.parametrize('symbol,local,expected', [
    ('IBOV','2026-09-17 12:20:00','2026-09-17T15:20:00+00:00'),
    ('NASDAQ','2026-09-17 11:20:00','2026-09-17T15:20:00+00:00'),
    ('Nikkei','2026-09-17 15:25:00','2026-09-17T06:25:00+00:00'),
    ('Shanghai','2026-09-17 15:00:00','2026-09-17T07:00:00+00:00'),
    ('DAX','2026-09-17 17:20:00','2026-09-17T15:20:00+00:00'),
])
def test_index_charts_use_fmp_exchange_local_dates(symbol,local,expected):
    settings,http,indices=service()
    http.rows=[{'date':local,'open':100,'high':102,'low':99,'close':101,'volume':0}]
    master=RealtimeMarketsService(settings,Database(settings),http,indices=indices)
    spec=next(s for s in MARKET_SPECS if s.symbol==symbol)
    result=master._live_instrument_intraday(spec,NOW)
    assert result.source=='Financial Modeling Prep Intraday 5m'
    assert result.points[-1].as_of.isoformat()==expected
    assert http.calls[0][0].endswith('/stable/historical-chart/5min')
