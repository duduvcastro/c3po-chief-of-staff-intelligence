from datetime import date, datetime, timezone
import traceback
from urllib.parse import urlencode

import pytest

from app.market_data.massive import MassiveClient, MassiveResponseError
from app.market_data.http import MarketDataRequestError


class FakeHttp:
    def __init__(self, payloads: list[object]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_json(self, url: str, *, params: dict[str, object]) -> object:
        self.calls.append((url, params))
        return self.payloads.pop(0)


def test_massive_trades_preserve_participant_and_sip_timestamps_across_pages() -> None:
    http = FakeHttp([
        {
            "results": [{
                "id": "t1",
                "participant_timestamp": 1_517_562_000_015_577_000,
                "sip_timestamp": 1_517_562_000_016_036_600,
                "price": 171.55,
                "decimal_size": "100.5",
                "exchange": 11,
                "sequence_number": 1063,
                "conditions": [12, 41],
                "tape": 3,
            }],
            "next_url": "https://api.massive.com/v3/trades/AAPL?cursor=next",
        },
        {
            "results": [{
                "id": "t2",
                "participant_timestamp": 1_517_562_000_015_577_600,
                "sip_timestamp": 1_517_562_000_016_038_100,
                "price": 171.56,
                "size": 50,
            }],
        },
    ])
    client = MassiveClient(
        "https://api.massive.com",
        "secret-token",
        http,  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    trades = list(client.iter_trades("aapl", session_date=date(2018, 2, 2)))

    assert [trade["trade_id"] for trade in trades] == ["t1", "t2"]
    assert trades[0]["symbol"] == "AAPL"
    assert trades[0]["size"] == 100.5
    assert trades[0]["event_at"] == datetime.fromtimestamp(
        1_517_562_000_015_577_000 / 1_000_000_000,
        tz=timezone.utc,
    )
    assert trades[0]["available_at"] > trades[0]["event_at"]
    assert http.calls[0][1] == {
        "timestamp": "2018-02-02",
        "order": "asc",
        "sort": "timestamp",
        "limit": 50_000,
        "apiKey": "secret-token",
    }
    assert http.calls[1] == (
        "https://api.massive.com/v3/trades/AAPL?cursor=next",
        {"apiKey": "secret-token"},
    )


def test_massive_bounded_trade_window_preserves_raw_rows() -> None:
    raw = {
        "id": "t1",
        "participant_timestamp": 1_777_300_800_000_000_000,
        "sip_timestamp": 1_777_300_800_001_000_000,
        "price": 100.0,
        "size": 2,
        "conditions": [2],
    }
    http = FakeHttp([{"results": [raw]}])
    client = MassiveClient(
        "https://api.massive.com",
        "secret-token",
        http,  # type: ignore[arg-type]
        historical_access_authorized=True,
    )
    start = datetime(2026, 4, 28, 14, 0, tzinfo=timezone.utc)
    end = datetime(2026, 4, 28, 14, 10, tzinfo=timezone.utc)

    assert list(client.iter_raw_trades_between("AAPL", start_at=start, end_at=end)) == [raw]
    assert http.calls == [(
        "https://api.massive.com/v3/trades/AAPL",
        {
            "timestamp.gte": 1_777_384_800_000_000_000,
            "timestamp.lt": 1_777_385_400_000_000_000,
            "order": "asc",
            "sort": "timestamp",
            "limit": 50_000,
            "apiKey": "secret-token",
        },
    )]


def test_massive_trade_conditions_use_stocks_trade_filter() -> None:
    payload = {
        "id": 2,
        "asset_class": "stocks",
        "data_types": ["trade"],
        "update_rules": {"consolidated": {"updates_high_low": False}},
    }
    http = FakeHttp([{"results": [payload]}])
    client = MassiveClient(
        "https://api.massive.com",
        "secret-token",
        http,  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    assert client.trade_conditions() == [payload]
    assert http.calls == [(
        "https://api.massive.com/v3/reference/conditions",
        {
            "asset_class": "stocks",
            "data_type": "trade",
            "order": "asc",
            "sort": "id",
            "limit": 1_000,
            "apiKey": "secret-token",
        },
    )]


def test_massive_quotes_drop_incomplete_or_noncausal_bbo_rows() -> None:
    http = FakeHttp([{
        "results": [
            {
                "sequence_number": 1,
                "participant_timestamp": 1_517_562_000_015_000_000,
                "sip_timestamp": 1_517_562_000_016_000_000,
                "bid_price": 170.0,
                "ask_price": 170.1,
                "bid_size": 2,
                "ask_size": 3,
            },
            {
                "sequence_number": 2,
                "participant_timestamp": 1_517_562_000_015_000_000,
                "sip_timestamp": 1_517_562_000_016_000_000,
                "bid_price": 170.0,
                "ask_price": 0,
                "bid_size": 2,
                "ask_size": 0,
            },
            {
                "sequence_number": 3,
                "participant_timestamp": 1_517_562_000_017_000_000,
                "sip_timestamp": 1_517_562_000_016_000_000,
                "bid_price": 170.0,
                "ask_price": 170.1,
                "bid_size": 2,
                "ask_size": 3,
            },
        ],
    }])
    client = MassiveClient(
        "https://api.massive.com",
        "token",
        http,  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    quotes = list(client.iter_quotes("AAPL", session_date=date(2018, 2, 2)))

    assert len(quotes) == 1
    assert quotes[0]["quote_id"] == "1"
    assert quotes[0]["bid"] == 170.0
    assert quotes[0]["ask"] == 170.1


def test_massive_pagination_cannot_leave_configured_origin() -> None:
    client = MassiveClient(
        "https://api.massive.com",
        "token",
        FakeHttp([{"results": [], "next_url": "https://attacker.invalid/steal"}]),  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    with pytest.raises(MassiveResponseError, match="leave the configured origin"):
        list(client.iter_trades("AAPL", session_date=date(2026, 8, 21)))


def test_massive_rejects_unconfigured_token_and_unsafe_symbol() -> None:
    client = MassiveClient(
        "https://api.massive.com",
        "",
        FakeHttp([]),  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    with pytest.raises(ValueError, match="not configured"):
        list(client.iter_trades("AAPL", session_date=date(2026, 8, 21)))
    with pytest.raises(ValueError, match="invalid Massive stock symbol"):
        list(client.iter_trades("../AAPL", session_date=date(2026, 8, 21)))


def test_massive_redacts_api_key_from_rest_error_and_traceback() -> None:
    token = "massive/secret+token"

    class FailingHttp:
        def get_json(self, url: str, *, params: dict[str, object]) -> object:
            raise MarketDataRequestError(
                f"403 for {url}?{urlencode(params)}&cursor=next"
            )

    client = MassiveClient(
        "https://api.massive.com",
        token,
        FailingHttp(),  # type: ignore[arg-type]
        historical_access_authorized=True,
    )

    with pytest.raises(MassiveResponseError) as captured:
        list(client.iter_trades("AAPL", session_date=date(2026, 8, 21)))

    rendered_traceback = "".join(traceback.format_exception(captured.value))
    assert token not in str(captured.value)
    assert "massive%2Fsecret%2Btoken" not in str(captured.value)
    assert token not in rendered_traceback
    assert "[REDACTED]" in str(captured.value)


def test_massive_historical_rest_is_blocked_by_default() -> None:
    client = MassiveClient(
        "https://api.massive.com",
        "token",
        FakeHttp([]),  # type: ignore[arg-type]
    )

    with pytest.raises(MassiveResponseError, match="historical REST access is disabled"):
        list(client.iter_trades("AAPL", session_date=date(2026, 8, 21)))


def test_massive_news_sends_the_dot_spelling_and_the_window_date_and_reads_every_page() -> None:
    # owner 03/11/2026: the weekly news sentiment comes from /v2/reference/news (reference data: no Day D gate). The
    # application's BRK-B is Massive's BRK.B; the window goes out as its UTC date (the caller keeps the exact instant), newest
    # first explicitly, so a listing cut at its page limit keeps the latest articles
    http = FakeHttp([
        {"results": [{"id": "a1", "insights": [{"ticker": "BRK.B", "sentiment": "positive"}]}],
         "next_url": "https://api.massive.com/v2/reference/news?cursor=next"},
        {"results": [{"id": "a2"}, "not-an-article"]},
    ])
    client = MassiveClient("https://api.massive.com", "secret-token", http)  # type: ignore[arg-type]

    articles, truncated = client.news("brk-b", published_since=datetime(2026, 10, 27, 2, 30, tzinfo=timezone.utc))

    assert [article["id"] for article in articles] == ["a1", "a2"] and truncated is False
    assert http.calls == [
        ("https://api.massive.com/v2/reference/news",
         {"ticker": "BRK.B", "published_utc.gte": "2026-10-27", "order": "desc", "sort": "published_utc", "limit": 100,
          "apiKey": "secret-token"}),
        ("https://api.massive.com/v2/reference/news?cursor=next", {"apiKey": "secret-token"}),
    ]


def test_massive_news_is_cut_at_its_page_limit_and_says_so() -> None:
    from app.market_data.massive import MassivePageLimitError

    http = FakeHttp([
        {"results": [{"id": f"a{page}"}], "next_url": f"https://api.massive.com/v2/reference/news?cursor={page}"}
        for page in range(1, 4)
    ])
    client = MassiveClient("https://api.massive.com", "secret-token", http)  # type: ignore[arg-type]

    articles, truncated = client.news("AAPL", published_since=datetime(2026, 10, 27, tzinfo=timezone.utc), max_pages=2)

    assert [article["id"] for article in articles] == ["a1", "a2"] and truncated is True and len(http.calls) == 2
    assert issubclass(MassivePageLimitError, MassiveResponseError)  # every other caller still sees a MassiveResponseError


def test_massive_news_refuses_a_naive_window_an_unsafe_symbol_and_a_missing_token() -> None:
    client = MassiveClient("https://api.massive.com", "secret-token", FakeHttp([]))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="timezone-aware"):
        client.news("AAPL", published_since=datetime(2026, 10, 27))
    with pytest.raises(ValueError, match="invalid Massive stock symbol"):
        client.news("../AAPL", published_since=datetime(2026, 10, 27, tzinfo=timezone.utc))
    unconfigured = MassiveClient("https://api.massive.com", "", FakeHttp([]))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not configured"):
        unconfigured.news("AAPL", published_since=datetime(2026, 10, 27, tzinfo=timezone.utc))
    assert MassiveClient.news_ticker("brk-b") == "BRK.B" and MassiveClient.news_ticker("AAPL") == "AAPL"
