"""The six cash indices on EODHD (owner 03/11/2026: FMP is cut): one real-time batch through the frozen
EodhdClient.quotes for the cards, EodhdClient.intraday for the charts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.database import Database
from app.market_data.indices import CACHE_SECONDS, INDICES, PROVIDER, SHANGHAI_EODHD_CODE, IndexQuotesService, quote_status
from app.market_data.live_markets import LiveMarketsService, MARKET_SPECS
from app.market_data.realtime import RealtimeMarketsService, MARKET_SPECS as REALTIME_SPECS

NOW = datetime(2026, 9, 17, 15, 30, tzinfo=timezone.utc)


def _quote(code, **fields):
    """One record of EODHD's real-time batch, as it answers for an index (no currency field)."""
    return {"code": code, "timestamp": int(NOW.timestamp()), "gmtoffset": 0, "open": 99, "high": 101, "low": 98,
            "close": 100, "volume": 0, "previousClose": 100, "change": 0, "change_p": 999, **fields}


class Http:
    def __init__(self):
        self.calls = []
        self.rows = [_quote(spec.eodhd_code) for spec in INDICES.values()]
        self.bars = []
        self.failed = False
    def get_json(self, url, *, params=None, headers=None):
        self.calls.append((url, params))
        assert "yahoo" not in url and "financialmodelingprep" not in url
        if self.failed:
            raise RuntimeError("secret-key-must-not-escape")
        return self.bars if "/api/intraday/" in url else self.rows

def service():
    settings = Settings(eodhd_api_token="test", auth_cookie_secure=False)
    http = Http()
    return settings, http, IndexQuotesService(settings, http)

class Clock(datetime):
    @classmethod
    def now(cls, tz=None): return NOW


def test_both_products_share_single_eodhd_request_and_same_quote():
    settings, http, indices = service()
    live = LiveMarketsService(settings, http, indices=indices)
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    with patch('app.market_data.indices.datetime', Clock):
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(indices.quote, list(INDICES)*3))
        falcon = live.index_snapshot()
        luke = master._index_quote(REALTIME_SPECS['NASDAQ'])
    assert len(http.calls) == 1
    url, params = http.calls[0]
    assert url == 'https://eodhd.com/api/real-time/BVSP.INDX'  # one batch: the first code in the path, the rest in s
    assert params == {'api_token': 'test', 'fmt': 'json', 's': 'IXIC.INDX,NYA.INDX,N225.INDX,000001.SHG,GDAXI.INDX'}
    assert len(rows) == 18
    item = next(item for item in falcon.items if item.symbol=='NASDAQ')
    assert (item.price, item.as_of, item.change_percent) == (luke.value, luke.as_of, luke.change_percent)
    assert item.provider == luke.source == PROVIDER == 'EODHD'
    assert item.provider_symbol == '^IXIC'  # the symbol the application exposes does not change
    assert item.change_percent == 0  # Valid zero; derive from matching previous close (never the record's change_p).
    assert (item.open, item.low, item.high, item.previous_close) == (99, 98, 101, 100)
    # EODHD's batch carries no currency (its helper would say USD): every index keeps its own
    assert {r.symbol: r.currency for r in rows} == {'IBOV': 'BRL', 'NASDAQ': 'USD', 'NYSE': 'USD', 'Nikkei': 'JPY',
                                                   'Shanghai': 'CNY', 'DAX': 'EUR'}


def test_the_eodhd_codes_keep_the_exposed_symbols_and_shanghai_is_one_constant():
    assert {symbol: spec.eodhd_code for symbol, spec in INDICES.items()} == {
        '^BVSP': 'BVSP.INDX', '^IXIC': 'IXIC.INDX', '^NYA': 'NYA.INDX', '^N225': 'N225.INDX',
        '000001.SS': '000001.SHG', '^GDAXI': 'GDAXI.INDX'}  # SSEC.INDX answers nothing (probe of 03/11/2026)
    assert INDICES['000001.SS'].eodhd_code is SHANGHAI_EODHD_CODE
    assert {spec.symbol for spec in INDICES.values()} == {'IBOV', 'NASDAQ', 'NYSE', 'Nikkei', 'Shanghai', 'DAX'}


def test_one_batch_a_minute_at_most_six_billed_calls_each():
    _, http, indices = service()
    assert CACHE_SECONDS == 60
    later = NOW + timedelta(seconds=CACHE_SECONDS - 1)
    expired = NOW + timedelta(seconds=CACHE_SECONDS + 1)
    with patch('app.market_data.indices.datetime', Clock):
        indices.quote('^IXIC')
        assert indices._expires == NOW + timedelta(seconds=60)
    for moment, calls in ((later, 1), (expired, 2)):
        class At(datetime):
            @classmethod
            def now(cls, tz=None): return moment
        with patch('app.market_data.indices.datetime', At):
            indices.quote('^BVSP')
            pending = indices._refreshing
            if pending: assert pending.wait(2)
        assert len(http.calls) == calls


def test_without_an_eodhd_token_there_is_no_index_and_no_request():
    http = Http()
    settings = Settings(eodhd_api_token='', fmp_api_token='a-token-still-set', auth_cookie_secure=False)
    indices = IndexQuotesService(settings, http)
    with pytest.raises(RuntimeError, match='EODHD index quote unavailable'):
        indices.quote('^IXIC')
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    with pytest.raises(RuntimeError, match='EODHD index history unavailable'):
        master._fetch_index_intraday(next(s for s in MARKET_SPECS if s.symbol == 'NASDAQ'), NOW)
    assert http.calls == []

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
    http.bars = [{'timestamp': int(datetime(2026, 9, 17, 19, 55, tzinfo=timezone.utc).timestamp()), 'open': 100, 'high': 102,
                  'low': 99, 'close': 101, 'volume': 0}]  # 16:55 BRT
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    spec = next(s for s in MARKET_SPECS if s.symbol == 'IBOV')
    result = master._live_instrument_intraday(spec, NOW.replace(hour=hour))
    assert result.status == 'closed'

@pytest.mark.parametrize('mutation', [
    {'timestamp': None}, {'timestamp': 'NA'}, {'timestamp': ''},  # no observation time: the helper stamps its own clock
    {'timestamp': 0}, {'timestamp': -1},
    {'timestamp': NOW.timestamp() + 3600},  # future dated
    {'close': 'NA'}, {'close': 'NaN'}, {'close': 'inf'}, {'close': 0}, {'close': -5},
])
def test_invalid_row_never_becomes_fresh_quote(mutation):
    settings,http,indices=service()
    http.rows[0].update(mutation)
    with patch('app.market_data.indices.datetime',Clock):
        with pytest.raises(RuntimeError,match='EODHD index quote unavailable'):indices.quote('^BVSP')
        assert indices.quote('^IXIC').price==100


def test_a_record_without_its_timestamp_or_another_code_is_dropped():
    _, http, indices = service()
    del http.rows[0]['timestamp']
    http.rows.append(_quote('SSEC.INDX', close=3000))  # a code the indices do not ask for
    with patch('app.market_data.indices.datetime', Clock):
        with pytest.raises(RuntimeError, match='EODHD index quote unavailable'):
            indices.quote('^BVSP')
        assert indices.quote('000001.SS').price == 100
    assert set(indices._items) == set(INDICES) - {'^BVSP'}


def test_failure_retains_real_timestamp_marks_stale_and_throttles_without_yahoo():
    _,http,indices=service()
    with patch('app.market_data.indices.datetime',Clock):
        original=indices.quote('^IXIC')
        http.failed=True;indices._expires=NOW-timedelta(seconds=1)
        indices.quote('^IXIC')
        pending = indices._refreshing
        if pending: assert pending.wait(2)
        stale=indices.quote('^IXIC');indices.quote('^NYA')
    assert stale.status=='stale' and stale.as_of==original.as_of
    assert len(http.calls)==2


def test_older_quote_cannot_overwrite_newer():
    _,http,indices=service()
    with patch('app.market_data.indices.datetime',Clock):
        original=indices.quote('^IXIC')
        for row in http.rows:row.update(timestamp=NOW.timestamp()-600,close=50)
        indices._expires=NOW-timedelta(seconds=1)
        indices.quote('^IXIC')
        pending = indices._refreshing
        if pending: assert pending.wait(2)
        result=indices.quote('^IXIC')
    assert result.price==original.price and result.as_of==original.as_of and result.status=='stale'

@pytest.mark.parametrize('symbol,code,bar,expected', [
    ('IBOV', 'BVSP.INDX', '2026-09-17T15:20:00+00:00', '2026-09-17T15:20:00+00:00'),
    ('NASDAQ', 'IXIC.INDX', '2026-09-17T15:20:00+00:00', '2026-09-17T15:20:00+00:00'),
    ('Nikkei', 'N225.INDX', '2026-09-17T06:25:00+00:00', '2026-09-17T06:25:00+00:00'),
    ('Shanghai', '000001.SHG', '2026-09-17 07:00:00', '2026-09-17T07:00:00+00:00'),  # EODHD's UTC datetime, never local
    ('DAX', 'GDAXI.INDX', '2026-09-17T15:20:00+00:00', '2026-09-17T15:20:00+00:00'),
])
def test_index_charts_read_eodhd_bars_on_the_index_session(symbol, code, bar, expected):
    settings, http, indices = service()
    stamp = bar if ' ' in bar else int(datetime.fromisoformat(bar).timestamp())
    http.bars = [{'timestamp': stamp, 'open': 100, 'high': 102, 'low': 99, 'close': 101, 'volume': 0},
                 {'timestamp': int((NOW + timedelta(minutes=5)).timestamp()), 'close': 999}]  # a future bar never shows
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    spec = next(s for s in MARKET_SPECS if s.symbol == symbol)
    result = master._live_instrument_intraday(spec, NOW)
    assert result.source == 'EODHD Intraday 5m' and result.symbol == symbol and result.currency == spec.currency
    assert [point.as_of.isoformat() for point in result.points] == [expected]
    url, params = http.calls[0]
    assert url == f'https://eodhd.com/api/intraday/{code}' and params['interval'] == '5m'
    assert params['to'] - params['from'] == 7 * 24 * 3600


def test_a_requested_index_session_ends_at_the_index_s_own_midnight():
    settings, http, indices = service()
    http.bars = [{'timestamp': int(datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc).timestamp()), 'close': 101}]
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    spec = next(s for s in MARKET_SPECS if s.symbol == 'Nikkei')
    result = master._live_instrument_intraday(spec, NOW, requested_session_date=date(2026, 9, 16))
    assert result.session_date == '2026-09-16' and result.session_fidelity == 'exact'
    # the window closes at midnight in Tokyo (the session timezone), not in New York, the helper's default
    assert http.calls[0][1]['to'] == int(datetime(2026, 9, 17, tzinfo=ZoneInfo('Asia/Tokyo')).timestamp())


@pytest.mark.parametrize('symbol,last_bar,status,delay', [
    # probe of 03/11/2026: EODHD's index bars lag the session by hours; the chart says so from its last bar
    ('NASDAQ', datetime(2026, 9, 16, 19, 55, tzinfo=timezone.utc), 'stale', 1175),  # yesterday's close during today's session
    ('IBOV', datetime(2026, 9, 17, 13, 5, tzinfo=timezone.utc), 'stale', 145),  # 2 h 25 old inside the session
    ('IBOV', datetime(2026, 9, 17, 15, 15, tzinfo=timezone.utc), 'delayed', 15),
    ('NASDAQ', datetime(2026, 9, 17, 15, 29, tzinfo=timezone.utc), 'delayed', 1),  # never "live" from bars
])
def test_lagging_index_bars_are_never_presented_as_current(symbol, last_bar, status, delay):
    settings, http, indices = service()
    http.bars = [{'timestamp': int((last_bar - timedelta(minutes=5)).timestamp()), 'close': 100},
                 {'timestamp': int(last_bar.timestamp()), 'close': 101}]
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    result = master._live_instrument_intraday(next(s for s in MARKET_SPECS if s.symbol == symbol), NOW)
    assert (result.status, result.delay_minutes) == (status, delay)
    assert result.points[-1].as_of == last_bar and result.current == 101


def test_the_live_panel_names_eodhd_for_the_cash_indices():
    settings, http, indices = service()

    class OnlyIndices(Http):
        def get_json(self, url, *, params=None, headers=None):
            if '/api/real-time/BVSP.INDX' not in url:
                raise RuntimeError('not part of this test')  # every other source degrades on its own
            return super().get_json(url, params=params, headers=headers)

    only = OnlyIndices()
    response = LiveMarketsService(settings, only, indices=IndexQuotesService(settings, only)).snapshot()
    assert [item.symbol for item in response.groups['Index']] == ['IBOV', 'NASDAQ', 'NYSE', 'Nikkei', 'Shanghai', 'DAX']
    assert {item.provider for item in response.groups['Index']} == {'EODHD'}
    assert 'EODHD supplies the six cash indices' in response.methodology['global']
    assert 'FMP' not in response.methodology['global'] and not [error for error in response.errors if 'index' in error]


@pytest.mark.parametrize("symbol", ['^BVSP', '^IXIC'])
def test_preclose_quote_does_not_become_official_close(symbol):
    now = datetime(2026, 9, 17, 21, 0, tzinfo=timezone.utc)
    as_of = datetime(2026, 9, 17, 19, 45, tzinfo=timezone.utc)
    assert quote_status(INDICES[symbol], as_of, now) == ('stale', 'STALE')

@pytest.mark.parametrize("symbol,hour,minute", [('^N225',3,0), ('000001.SS',4,0)])
def test_lunch_break_is_not_session_close(symbol,hour,minute):
    now = datetime(2026, 9, 17, hour, minute, tzinfo=timezone.utc)
    assert quote_status(INDICES[symbol], now-timedelta(minutes=10), now) == ('delayed', 'BREAK')


def test_index_transport_has_separate_timeout_and_no_retry_budget():
    import httpx
    from app.market_data.http import JsonHttpClient

    requests = []
    def fail(request):
        requests.append(request)
        raise httpx.ReadTimeout('provider unavailable', request=request)

    with httpx.Client(transport=httpx.MockTransport(fail)) as transport:
        shared = JsonHttpClient(timeout=15, max_retries=2, client=transport)
        indices = IndexQuotesService(Settings(eodhd_api_token='test'), shared)
        with pytest.raises(RuntimeError, match='EODHD index quote unavailable'):
            indices.quote('^IXIC')
        assert len(requests) == 1
        assert requests[0].url.path == '/api/real-time/BVSP.INDX'
        assert set(requests[0].extensions['timeout'].values()) == {3.0}
        assert shared.timeout == 15 and shared.max_retries == 2
        with pytest.raises(RuntimeError, match='EODHD index quote unavailable'):
            indices.quote('^NYA')
        assert len(requests) == 1


def test_cached_readers_do_not_wait_for_single_inflight_refresh():
    from threading import Event
    _, http, indices = service()
    entered, release = Event(), Event()
    original_fetch = http.get_json
    def slow_fetch(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original_fetch(*args, **kwargs)

    with patch('app.market_data.indices.datetime', Clock):
        original = indices.quote('^IXIC')
        indices._expires = NOW - timedelta(seconds=1)
        http.get_json = slow_fetch
        with ThreadPoolExecutor(max_workers=2) as pool:
            refresh = pool.submit(indices.quote, '^IXIC')
            try:
                assert entered.wait(2)
                reader = pool.submit(indices.quote, '^IXIC')
                stale = reader.result(timeout=1)
                assert stale.status == 'live'  # Refresh alone must not flicker the freshness label.
                assert stale.as_of == original.as_of and stale.price == original.price
                assert refresh.result(timeout=1).as_of == original.as_of
            finally:
                pending = indices._refreshing
                release.set()
                if pending: assert pending.wait(2)
            assert refresh.result(timeout=2).status == 'live'
        assert len(http.calls) == 2


def test_realtime_lock_is_available_during_index_fetch():
    from threading import Event
    settings, http, indices = service()
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    entered, release = Event(), Event()
    marker = object()
    def slow_index(spec):
        entered.set()
        assert release.wait(5)
        return marker
    def lock_available():
        acquired = master._lock.acquire(timeout=0.5)
        if acquired:
            master._lock.release()
        return acquired
    with patch.object(master, '_index_quote', slow_index), \
         patch.object(master, '_build', return_value=marker) as build, \
         patch.object(master, '_apply_stream', side_effect=lambda market, result, now: result):
        with ThreadPoolExecutor(max_workers=2) as pool:
            request = pool.submit(master.snapshot, 'NASDAQ')
            try:
                assert entered.wait(2)
                assert pool.submit(lock_available).result(timeout=1)
                assert not request.done()
            finally:
                release.set()
            assert request.result(timeout=2) is marker
        assert build.call_args.kwargs['index'] is marker


def test_b3_ranking_preserves_its_observation_when_index_has_other_timestamp():
    from app.schemas import RealtimeMarketLeader
    settings, http, indices = service()
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    with patch('app.market_data.indices.datetime', Clock):
        index = master._index_quote(REALTIME_SPECS['B3'])
    observed = NOW - timedelta(minutes=17)
    row = RealtimeMarketLeader(symbol='PETR4', name='Petrobras', price=30,
        change_percent=1, volume=10000000, cash_volume=300000000, currency='BRL',
        exchange='B3', as_of=observed)
    with patch.object(master, '_b3_rows', return_value=[row]), \
         patch.object(master, '_enrich_b3_leader_groups', side_effect=lambda groups: groups):
        result = master._build('B3', NOW, index=index)
    assert result.index.as_of != observed
    for rows in (result.gainers, result.losers, result.volume_leaders, result.cash_leaders):
        assert all(item.as_of == observed for item in rows)
    assert result.gainers and result.volume_leaders


@pytest.mark.parametrize('field,value', [
    ('regularMarketTime', (NOW-timedelta(minutes=17)).timestamp()),
    ('timestamp', (NOW-timedelta(minutes=17)).timestamp()*1000),
    ('updatedAt', (NOW-timedelta(minutes=17)).isoformat()),
])
def test_brapi_scan_preserves_provider_observation(field, value):
    settings = Settings(brapi_token='test', auth_cookie_secure=False)
    class Scan:
        def get_json(self, *args, **kwargs):
            return {'stocks': [{'stock':'PETR4', 'close':30, 'change':1,
                'volume':10000000, field:value}]}
    master = RealtimeMarketsService(settings, Database(settings), Scan())
    row = master._b3_rows(NOW)[0]
    assert row.as_of == NOW-timedelta(minutes=17)


def test_first_index_failure_does_not_prevent_security_rankings():
    from app.schemas import RealtimeMarketLeader
    settings, http, indices = service()
    http.failed = True
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    row = RealtimeMarketLeader(symbol='PETR4', name='Petrobras', price=30,
        change_percent=1, volume=10000000, cash_volume=300000000, currency='BRL',
        exchange='B3', as_of=NOW)
    with patch.object(master, '_b3_rows', return_value=[row]), \
         patch.object(master, '_enrich_b3_leader_groups', side_effect=lambda groups: groups):
        result = master.snapshot('B3')
    assert result.index is None
    assert result.gainers[0].symbol == 'PETR4'
    assert result.universe_size == 1
    assert result.errors == ['Index quote unavailable']
    assert 'secret-key' not in result.model_dump_json()


def test_history_failure_is_cached_without_logging_credentials(caplog):
    settings, http, indices = service()
    http.failed = True
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    spec = next(s for s in MARKET_SPECS if s.symbol == 'NASDAQ')
    for _ in range(2):
        with pytest.raises(RuntimeError, match='EODHD index history unavailable'):
            master._index_intraday(spec, NOW)
    assert len(http.calls) == 1
    assert 'secret-key' not in caplog.text
    assert 'RuntimeError' in caplog.text
    with pytest.raises(RuntimeError):
        master._index_intraday(spec, master._index_history_failures[(spec.provider_symbol, NOW.date())]+timedelta(seconds=1))
    assert len(http.calls) == 2


def test_cold_batch_has_one_total_deadline_even_with_slow_drip():
    from threading import Event
    from time import monotonic
    _, http, indices = service()
    entered, release = Event(), Event()
    def drip(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return []
    http.get_json = drip
    start = monotonic()
    try:
        for symbol in INDICES:
            with pytest.raises(RuntimeError): indices.quote(symbol)
        assert entered.is_set()
        assert monotonic()-start < 4.0  # Six symbols share one 3s deadline.
    finally:
        pending = indices._refreshing
        release.set()
        if pending: assert pending.wait(2)


def test_history_fetch_outside_shared_lock_bounded_and_failure_clock_after_fetch():
    from threading import Event
    from time import monotonic
    settings, http, indices = service()
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    entered, release = Event(), Event()
    calls = []
    def drip(*args, **kwargs):
        calls.append(1);entered.set()
        assert release.wait(10)
        raise RuntimeError('secret-key')
    http.get_json = drip
    start = monotonic()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(master.instrument_intraday, 'NASDAQ')
            assert entered.wait(2)
            assert master._lock.acquire(timeout=0.2)
            master._lock.release()
            with pytest.raises(RuntimeError): request.result(timeout=4)
        assert monotonic()-start < 4
        with pytest.raises(RuntimeError): master.instrument_intraday('NASDAQ')
        assert len(calls) == 1
    finally:
        pending = next(iter(master._index_history_pending.values()), (None, 0))[0]
        failure_time = datetime.now(timezone.utc)
        release.set()
        if pending: assert pending.wait(2)
    assert all(expiry >= failure_time+timedelta(seconds=29) for expiry in master._index_history_failures.values())
    with pytest.raises(RuntimeError): master.instrument_intraday('NASDAQ')
    assert len(calls) == 1


def test_history_same_key_waits_and_different_key_progresses():
    from threading import Event
    from time import sleep
    from types import SimpleNamespace
    settings, http, indices = service()
    master = RealtimeMarketsService(settings, Database(settings), http, indices=indices)
    entered, release = Event(), Event()
    calls = []
    def fetch(spec, now, **kwargs):
        calls.append(spec.provider_symbol)
        if spec.symbol == 'NASDAQ':
            entered.set()
            assert release.wait(5)
        return SimpleNamespace(symbol=spec.symbol)
    with patch.object(master, '_fetch_index_intraday', fetch), ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(master.instrument_intraday, 'NASDAQ')
        assert entered.wait(1)
        second = pool.submit(master.instrument_intraday, 'NASDAQ')
        other = pool.submit(master.instrument_intraday, 'IBOV')
        try:
            assert other.result(timeout=1).symbol == 'IBOV'
            sleep(0.05)
            assert not second.done()
        finally:
            release.set()
        assert first.result(timeout=1).symbol == second.result(timeout=1).symbol == 'NASDAQ'
    assert calls.count('^IXIC') == 1
    assert not master._index_history_pending


def test_deadline_http_aborts_slow_drip_and_allows_next_request():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread, Event
    from time import monotonic
    from app.market_data.http import DeadlineJsonHttpClient, MarketDataRequestError
    stopped = Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Length', '100000')
            self.end_headers()
            try:
                while not stopped.wait(0.03):
                    self.wfile.write(b' ')
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True);thread.start()
    client = DeadlineJsonHttpClient(timeout=0.2)
    try:
        for _ in range(2):
            start = monotonic()
            with pytest.raises(MarketDataRequestError, match='TimeoutError'):
                client.get_json(f'http://127.0.0.1:{server.server_port}/')
            assert monotonic()-start < 1.0
    finally:
        stopped.set();server.shutdown();server.server_close();thread.join(timeout=2)
